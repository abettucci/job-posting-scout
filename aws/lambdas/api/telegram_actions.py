"""Asynchronous document actions invoked by the Telegram bot Lambda.

The bot invokes the API Lambda with ``InvocationType="Event"`` and a payload
``{"telegram_action", "user_id", "job_id", "chat_id"}``. This module reuses the
same generation helpers as the HTTP endpoints, then sends the PDF to the chat.
Every AI call goes through ``build_ai_client``, so the free providers are tried
first and paid fallbacks respect ``AI_PAID_DAILY_BUDGET_USD``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ai_router import build_ai_client
from routers import resume as resume_api
from telegram import TelegramClient

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "No pude generar el documento. Probá de nuevo más tarde o usá la app."


def run_action(event: Dict[str, Any], db: Any, cfg: Any) -> Dict[str, Any]:
    action = str(event.get("telegram_action") or "")
    user_id = str(event.get("user_id") or "")
    job_id = str(event.get("job_id") or "")
    chat_id = event.get("chat_id")
    if action not in ("tailor", "cover") or not (user_id and job_id and chat_id):
        logger.warning("telegram action rejected: missing or unknown fields")
        return {"ok": False}

    tg = TelegramClient(cfg.telegram_bot_token)
    try:
        if not db.get_user_job(user_id, job_id):
            tg.send_message(chat_id, "Job no encontrado.", parse_mode=None)
            return {"ok": False}
        saved = db.get_resume(user_id)
        if not saved:
            tg.send_message(chat_id, "No encontré un CV guardado en la app.", parse_mode=None)
            return {"ok": False}

        resume = resume_api.ResumeData(**saved)
        ai = build_ai_client(cfg)
        job_description = resume_api._resolve_job_description(db, user_id, None, job_id)
        company, role = resume_api._history_context(db, user_id, job_id)
        caption = f"{role} @ {company}"[:200]

        if action == "tailor":
            tailored = resume_api._tailor_with_claude(ai, resume, job_description)
            tailored = resume_api._review_tailored_resume(ai, resume, tailored, job_description)
            resume_api._save_history_artifact(
                db, user_id, "tailored_cv", company=company, role=role,
                job_id=job_id, template="typst-silver", resume=tailored.model_dump(),
            )
            pdf = resume_api._compile_one_page(resume_api._typst_silver, tailored)
            tg.send_document(chat_id, "cv-tailored.pdf", pdf, caption=f"CV: {caption}")
            tg.send_message(
                chat_id,
                f"Podés revisarlo y exportarlo en la app: {cfg.frontend_url.rstrip('/')}/resume?tailor_job_id={job_id}",
                parse_mode=None,
            )
        else:
            letter = resume_api._generate_cover_letter(ai, resume, job_description)
            letter = resume_api._review_cover_letter(ai, letter, resume, job_description)
            resume_api._save_history_artifact(
                db, user_id, "cover_letter", company=company, role=role, job_id=job_id, content=letter,
            )
            pdf = resume_api._compile_typst(resume_api._typst_cover_letter(resume, letter))
            tg.send_document(chat_id, "cover-letter.pdf", pdf, caption=f"Cover letter: {caption}")
        return {"ok": True}
    except Exception as exc:
        # Log only the exception type: prompts, resumes and upstream bodies must not reach logs.
        logger.error("telegram action failed action=%s error=%s", action, type(exc).__name__)
        tg.send_message(chat_id, _FAILURE_MESSAGE, parse_mode=None)
        return {"ok": False}

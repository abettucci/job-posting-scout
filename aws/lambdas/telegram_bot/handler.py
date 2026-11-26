"""Telegram Bot webhook Lambda.

Commands:
  /start <code>  — link Telegram account using the 6-digit code from the frontend
  /status        — show linked account info
  /pause         — deactivate all searches for this user
  /resume        — reactivate all searches for this user
  /jobs [n]      — list the top unapplied, undismissed jobs
  /dismiss <id>  — dismiss a job
  /apply <id>    — mark a job as applied
  /tailor <id>   — generate a tailored CV PDF (async, via the API Lambda)
  /cover <id>    — generate a cover letter PDF (async, via the API Lambda)
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import sys
import random
import string
from pathlib import Path
from typing import Any, Dict

_SHARED_LAMBDA = str(Path(__file__).resolve().parent / "shared")
_SHARED_LOCAL = str(Path(__file__).resolve().parent.parent / "shared")
for _p in [_SHARED_LAMBDA, _SHARED_LOCAL]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import boto3

from config import get_config
from db import DynamoDBClient
from telegram import TelegramClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")


def lambda_handler(event, context):
    # Validate the secret token Telegram sends in the header
    headers = event.get("headers") or {}
    incoming_secret = headers.get("x-telegram-bot-api-secret-token") or headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )
    if _WEBHOOK_SECRET and incoming_secret != _WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret")
        return {"statusCode": 403, "body": "Forbidden"}

    cfg = get_config()
    db = DynamoDBClient(
        users_table=cfg.users_table,
        searches_table=cfg.searches_table,
        profiles_table=cfg.profiles_table,
        jobs_table=cfg.jobs_table,
        telegram_codes_table=cfg.telegram_codes_table,
        region=cfg.region,
    )
    tg = TelegramClient(cfg.telegram_bot_token)

    body = json.loads(event.get("body") or "{}")
    if body.get("callback_query"):
        try:
            _handle_callback(tg, db, body["callback_query"])
        except Exception as e:
            logger.error(f"Callback error: {type(e).__name__}")
        return {"statusCode": 200, "body": "ok"}
    message = body.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text.startswith("/"):
        return {"statusCode": 200, "body": "ok"}

    parts = text.split(maxsplit=1)
    command = parts[0].lower().split("@")[0]
    args = parts[1] if len(parts) > 1 else ""

    try:
        if command == "/start":
            _handle_start(tg, db, chat_id, args)
        elif command == "/status":
            _handle_status(tg, db, chat_id)
        elif command == "/pause":
            _handle_toggle(tg, db, chat_id, active=False)
        elif command == "/resume":
            _handle_toggle(tg, db, chat_id, active=True)
        elif command == "/jobs":
            _handle_jobs(tg, db, chat_id, args)
        elif command == "/dismiss":
            _handle_job_flag(tg, db, chat_id, args, field="dismissed")
        elif command == "/apply":
            _handle_job_flag(tg, db, chat_id, args, field="applied")
        elif command in ("/tailor", "/cover"):
            _handle_document(tg, db, chat_id, args, action="tailor" if command == "/tailor" else "cover")
        else:
            tg.send_message(
                chat_id,
                "Commands: /start <code>, /status, /pause, /resume, /jobs [n], "
                "/dismiss <job_id>, /apply <job_id>, /tailor <job_id>, /cover <job_id>",
                parse_mode=None,
            )
    except Exception as e:
        logger.error(f"Handler error: {e}")
        tg.send_message(chat_id, "An error occurred. Please try again.")

    return {"statusCode": 200, "body": "ok"}


def _handle_start(tg: TelegramClient, db: DynamoDBClient, chat_id: int, args: str):
    code = args.strip()
    if not code or len(code) != 6 or not code.isdigit():
        tg.send_message(
            chat_id,
            "Welcome to LinkedIn Job Scout!\n\n"
            "To link your account, go to Settings in the app and use the code shown there.\n"
            "Then send: /start <6-digit-code>",
        )
        return

    user_id = db.consume_telegram_code(code)
    if not user_id:
        tg.send_message(chat_id, "Code invalid or expired. Please generate a new one in the app.")
        return

    db.update_user(user_id, {"telegram_chat_id": str(chat_id)})
    tg.send_message(
        chat_id,
        "Account linked! You'll receive job notifications here.\n\n"
        "Commands: /pause to mute, /resume to re-enable, /status to check.",
    )


def _user_for_chat(db: DynamoDBClient, chat_id: int):
    users = db.get_all_linked_users()
    return next((u for u in users if str(u.get("telegram_chat_id")) == str(chat_id)), None)


_CALLBACK_ACTIONS = {"apply", "dismiss", "tailor", "cover"}


def _short_id(job_id: str) -> str:
    """Telegram callback_data is capped at 64 bytes, and job ids can be longer."""
    return hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:12]


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _job_message(index: int, job: Dict) -> str:
    title = _esc(job.get("title") or "Sin título")
    url = str(job.get("url") or "")
    head = f'<a href="{html.escape(url, quote=True)}">{title}</a>' if url.startswith("https://") else f"<b>{title}</b>"
    meta = " · ".join(
        _esc(part) for part in [job.get("company"), job.get("location"), f"score {job.get('score', '?')}"] if part
    )
    return f"<b>{index}.</b> {head}\n{meta}"


def _job_keyboard(job_id: str) -> Dict:
    s = _short_id(job_id)
    return {"inline_keyboard": [
        [{"text": "✅ Aplicar", "callback_data": f"apply:{s}"},
         {"text": "🗑 Descartar", "callback_data": f"dismiss:{s}"}],
        [{"text": "📄 CV", "callback_data": f"tailor:{s}"},
         {"text": "✉️ Cover", "callback_data": f"cover:{s}"}],
    ]}


def _handle_jobs(tg: TelegramClient, db: DynamoDBClient, chat_id: int, args: str):
    user = _user_for_chat(db, chat_id)
    if not user:
        tg.send_message(chat_id, "No account linked. Go to Settings in the app to link.", parse_mode=None)
        return
    n = int(args.strip()) if args.strip().isdigit() else 5
    n = max(1, min(n, 10))
    threshold = int(user.get("score_threshold") or 50)
    # Score 0 marks postings that were never evaluated, so they are not shown as matches.
    items, _ = db.get_user_jobs(
        user_id=user["user_id"], min_score=max(1, threshold), limit=n, applied=False, dismissed=False,
    )
    if not items:
        tg.send_message(chat_id, f"No hay jobs pendientes con score ≥ {threshold}.", parse_mode=None)
        return
    tg.send_message(chat_id, f"<b>{len(items)} jobs pendientes</b> (score ≥ {threshold})", parse_mode="HTML")
    for index, job in enumerate(items, start=1):
        tg.send_message(
            chat_id, _job_message(index, job), parse_mode="HTML",
            reply_markup=_job_keyboard(job["job_id"]),
        )


def _handle_callback(tg: TelegramClient, db: DynamoDBClient, callback: Dict):
    callback_id = callback.get("id", "")
    chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
    action, _, short = str(callback.get("data") or "").partition(":")
    if not callback_id or not chat_id or action not in _CALLBACK_ACTIONS or not short:
        tg.answer_callback_query(callback_id, "Acción no válida")
        return
    user = _user_for_chat(db, chat_id)
    if not user:
        tg.answer_callback_query(callback_id, "Cuenta no vinculada")
        return
    # Look the job up among the user's recent postings, so a stale button still resolves.
    candidates, _ = db.get_user_jobs(user_id=user["user_id"], min_score=0, limit=100)
    job = next((j for j in candidates if _short_id(str(j.get("job_id", ""))) == short), None)
    if not job:
        tg.answer_callback_query(callback_id, "Job no encontrado")
        return
    job_id = job["job_id"]
    if action == "apply":
        ok = db.set_job_applied(user["user_id"], job_id, True)
        tg.answer_callback_query(callback_id, "Marcado como aplicado" if ok else "Job no encontrado")
    elif action == "dismiss":
        ok = db.set_job_dismissed(user["user_id"], job_id, True)
        tg.answer_callback_query(callback_id, "Descartado" if ok else "Job no encontrado")
    else:
        tg.answer_callback_query(callback_id, "Generando…")
        _handle_document(tg, db, chat_id, job_id, action=action)


def _handle_job_flag(tg: TelegramClient, db: DynamoDBClient, chat_id: int, args: str, field: str):
    user = _user_for_chat(db, chat_id)
    if not user:
        tg.send_message(chat_id, "No account linked. Go to Settings in the app to link.", parse_mode=None)
        return
    job_id = args.strip()
    if not job_id:
        tg.send_message(chat_id, f"Usage: /{'dismiss' if field == 'dismissed' else 'apply'} <job_id>", parse_mode=None)
        return
    if field == "dismissed":
        ok = db.set_job_dismissed(user["user_id"], job_id, True)
        done = "Job descartado."
    else:
        ok = db.set_job_applied(user["user_id"], job_id, True)
        done = "Job marcado como aplicado."
    tg.send_message(chat_id, done if ok else "Job no encontrado.", parse_mode=None)


def _handle_document(tg: TelegramClient, db: DynamoDBClient, chat_id: int, args: str, action: str):
    user = _user_for_chat(db, chat_id)
    if not user:
        tg.send_message(chat_id, "No account linked. Go to Settings in the app to link.", parse_mode=None)
        return
    job_id = args.strip()
    if not job_id:
        tg.send_message(chat_id, f"Usage: /{action} <job_id>", parse_mode=None)
        return
    if not db.get_user_job(user["user_id"], job_id):
        tg.send_message(chat_id, "Job no encontrado.", parse_mode=None)
        return
    # The API Lambda has the AI router, typst and a 30s budget; the webhook has 15s.
    # Invoke it asynchronously and let it send the PDF to this chat when ready.
    boto3.client("lambda", region_name=os.environ.get("AWS_REGION")).invoke(
        FunctionName=os.environ["API_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({
            "telegram_action": action,
            "user_id": user["user_id"],
            "job_id": job_id,
            "chat_id": chat_id,
        }).encode(),
    )
    tg.send_message(chat_id, "Generando el documento. Te lo envío acá cuando esté listo.", parse_mode=None)


def _handle_status(tg: TelegramClient, db: DynamoDBClient, chat_id: int):
    users = db.get_all_linked_users()
    user = next((u for u in users if str(u.get("telegram_chat_id")) == str(chat_id)), None)
    if not user:
        tg.send_message(chat_id, "No account linked. Go to Settings in the app to link.")
        return

    searches = db.get_user_searches(user["user_id"])
    active = sum(1 for s in searches if s.get("active"))
    tg.send_message(
        chat_id,
        f"Account: {user['email']}\nActive searches: {active}/{len(searches)}\nScore threshold: {user.get('score_threshold', 75)}/100",
    )


def _handle_toggle(tg: TelegramClient, db: DynamoDBClient, chat_id: int, active: bool):
    users = db.get_all_linked_users()
    user = next((u for u in users if str(u.get("telegram_chat_id")) == str(chat_id)), None)
    if not user:
        tg.send_message(chat_id, "No account linked.")
        return

    searches = db.get_user_searches(user["user_id"])
    for s in searches:
        db.update_search(user["user_id"], s["search_id"], {"active": active})

    verb = "resumed" if active else "paused"
    tg.send_message(chat_id, f"All searches {verb}.")

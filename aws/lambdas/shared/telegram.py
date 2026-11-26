"""Telegram API client — raw requests with exponential-backoff retry."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self._session = requests.Session()

    def _call(self, method: str, data: Dict, retries: int = 3) -> Optional[Dict]:
        url = _BASE.format(token=self.token, method=method)
        for attempt in range(retries):
            try:
                resp = self._session.post(url, json=data, timeout=30)
                resp.raise_for_status()
                result = resp.json()
                if not result.get("ok"):
                    logger.error(f"Telegram error [{method}]: {result.get('description')}")
                    return None
                return result.get("result")
            except (requests.ConnectionError, requests.Timeout) as e:
                wait = 2 ** attempt
                logger.warning(f"Telegram connection error (attempt {attempt+1}/{retries}): {e}. Retry in {wait}s")
                if attempt < retries - 1:
                    time.sleep(wait)
            except requests.RequestException as e:
                logger.error(f"Telegram request error [{method}]: {e}")
                return None
        return None

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False,
        reply_markup: Optional[Dict] = None,
    ) -> Optional[Dict]:
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
        if parse_mode:  # pass None for user-supplied text (titles may contain Markdown characters)
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self._call("sendMessage", data)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> Optional[Dict]:
        data: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text[:200]
        return self._call("answerCallbackQuery", data)

    def send_document(self, chat_id: int, filename: str, content: bytes, mime_type: str = "application/pdf",
                      caption: str = "") -> Optional[Dict]:
        """Upload a file (e.g. a generated PDF) to the chat. Uses multipart, so it bypasses _call."""
        url = _BASE.format(token=self.token, method="sendDocument")
        try:
            resp = self._session.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (filename, content, mime_type)},
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                logger.error(f"Telegram error [sendDocument]: {result.get('description')}")
                return None
            return result.get("result")
        except requests.RequestException as e:
            logger.error(f"Telegram sendDocument error: {e}")
            return None

    def set_webhook(self, url: str, secret_token: str) -> Optional[Dict]:
        return self._call(
            "setWebhook",
            {"url": url, "secret_token": secret_token, "allowed_updates": ["message"]},
        )


def format_job_notification(job: Dict, score_result: Dict) -> str:
    score = score_result["score"]
    recommendation = score_result.get("recommendation", "MAYBE")

    badge = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    rec_emoji = "🚀" if recommendation == "APPLY" else "🤔" if recommendation == "MAYBE" else "❌"

    reasons_text = "\n".join(score_result.get("reasons", [])[:5])
    summary = score_result.get("summary", "")

    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    url = job.get("url", "")

    msg = f"""{badge} *Match: {score}/100* {rec_emoji}

*{title}*
🏢 {company}
📍 {location}

{reasons_text}

_{summary}_

[Ver publicación]({url})"""
    return msg

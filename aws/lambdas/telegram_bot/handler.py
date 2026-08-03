"""Telegram Bot webhook Lambda.

Commands:
  /start <code>  — link Telegram account using the 6-digit code from the frontend
  /status        — show linked account info
  /pause         — deactivate all searches for this user
  /resume        — reactivate all searches for this user
"""

from __future__ import annotations

import json
import logging
import os
import sys
import random
import string
from pathlib import Path

_SHARED = str(Path(__file__).resolve().parent.parent / "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

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
        else:
            tg.send_message(chat_id, "Commands: /start <code>, /status, /pause, /resume")
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

from __future__ import annotations

import random
import string
from typing import Any, Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/telegram", tags=["telegram"])

    @router.post("/start-link")
    def start_link(user=Depends(get_current_user)):
        """Generate a 6-digit code the user sends to the bot via /start <code>.
        The bot then sets telegram_chat_id directly on the user record.
        The frontend polls /auth/me to detect the change."""
        code = _generate_code()
        for _ in range(3):
            if db.save_telegram_code(code, user["user_id"]):
                break
            code = _generate_code()
        return {
            "code": code,
            "expires_in_minutes": 10,
        }

    return router

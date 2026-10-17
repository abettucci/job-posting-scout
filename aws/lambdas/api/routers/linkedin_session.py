from __future__ import annotations

import json
from typing import Any, Callable

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

_COOKIE_SECRET_NAME = "linkedin-job-scout/linkedin-cookies"


class LinkedInSessionUpdate(BaseModel):
    li_at: str

    @field_validator("li_at")
    @classmethod
    def validate_li_at(cls, value: str) -> str:
        value = value.strip()
        if not 16 <= len(value) <= 4096 or any(character.isspace() for character in value):
            raise ValueError("Paste a valid LinkedIn li_at session value")
        return value


def _cookies_for_session(li_at: str) -> list[dict[str, object]]:
    # Playwright restores this cookie before visiting linkedin.com. Do not log
    # this value or return it from the API: it is an account session credential.
    return [{
        "name": "li_at",
        "value": li_at,
        "domain": ".www.linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }]


def make_router(db: Any, cfg: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/linkedin", tags=["linkedin"])

    @router.get("/session-status")
    def session_status(user=Depends(get_current_user)):
        return {
            "blocked_until": user.get("linkedin_auth_blocked_until"),
            "needs_reconnect": bool(user.get("linkedin_auth_incident_open")),
        }

    @router.put("/session")
    def update_session(body: LinkedInSessionUpdate, user=Depends(get_current_user)):
        try:
            client = boto3.client("secretsmanager", region_name=cfg.region)
            secret_value = json.dumps(_cookies_for_session(body.li_at))
            try:
                client.put_secret_value(SecretId=_COOKIE_SECRET_NAME, SecretString=secret_value)
            except client.exceptions.ResourceNotFoundException:
                client.create_secret(Name=_COOKIE_SECRET_NAME, SecretString=secret_value)
            db.update_user(user["user_id"], {
                "linkedin_auth_incident_open": False,
                "linkedin_auth_blocked_until": None,
            })
            return {"updated": True}
        except Exception:
            # Keep the session value out of application logs and error details.
            raise HTTPException(503, "Could not securely update the LinkedIn session") from None

    return router

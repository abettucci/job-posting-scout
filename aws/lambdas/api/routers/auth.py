from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def make_router(db: Any, cfg: Any, get_current_user: Callable = None) -> APIRouter:
    from auth import hash_password, verify_password, create_token, safe_user

    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/signup")
    def signup(body: SignupRequest):
        email = body.email.lower()
        existing = db.get_user_by_email(email)
        if existing:
            raise HTTPException(409, "Email already registered")

        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "email": email,
            "password_hash": hash_password(body.password),
            "score_threshold": 75,
            "created_at": datetime.utcnow().isoformat(),
        }
        if not db.create_user(user):
            raise HTTPException(500, "Error creating user")

        token = create_token(user_id, cfg.jwt_secret)
        return {"token": token, "user": safe_user(user)}

    @router.post("/login")
    def login(body: LoginRequest):
        user = db.get_user_by_email(body.email.lower())
        if not user or not verify_password(body.password, user.get("password_hash", "")):
            raise HTTPException(401, "Invalid credentials")

        token = create_token(user["user_id"], cfg.jwt_secret)
        return {"token": token, "user": safe_user(user)}

    @router.get("/me")
    def me(user=Depends(get_current_user)):
        return safe_user(user)

    return router

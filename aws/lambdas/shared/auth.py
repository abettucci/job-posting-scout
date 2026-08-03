from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str, secret: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, secret: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def make_get_current_user(db, jwt_secret: str):
    """Factory that returns a FastAPI dependency for the current user."""

    def get_current_user(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    ) -> Dict[str, Any]:
        if not creds:
            raise HTTPException(401, "Token requerido")
        user_id = decode_token(creds.credentials, jwt_secret)
        if not user_id:
            raise HTTPException(401, "Token inválido o expirado")
        user = db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(401, "Usuario no encontrado")
        return user

    return get_current_user


def safe_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "telegram_chat_id": user.get("telegram_chat_id"),
        "score_threshold": user.get("score_threshold", 75),
        "created_at": user.get("created_at"),
    }

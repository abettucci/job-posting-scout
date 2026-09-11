from __future__ import annotations

from typing import Any, Callable, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

# Kept in sync by hand with shared/seniority.py's SENIORITY_LEVELS (same
# small-constant-duplication pattern used in routers/searches.py).
_SENIORITY_LEVELS = ["internship", "entry", "associate", "mid", "senior", "staff", "director", "executive"]


class ProfileUpdate(BaseModel):
    must_have: Optional[List[str]] = None
    nice_to_have: Optional[List[str]] = None
    deal_breakers: Optional[List[str]] = None
    prefer: Optional[List[str]] = None
    score_threshold: Optional[int] = None
    seniority: Optional[str] = None  # "" clears the preference; one of _SENIORITY_LEVELS otherwise
    eligible_regions: Optional[List[str]] = None  # free text, e.g. ["Argentina", "LATAM", "Worldwide"]

    @field_validator("seniority")
    @classmethod
    def validate_seniority(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _SENIORITY_LEVELS:
            raise ValueError(f"seniority must be one of: {_SENIORITY_LEVELS}")
        return v


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])

    @router.get("")
    def get_profile(user=Depends(get_current_user)):
        profile = db.get_profile(user["user_id"]) or {}
        profile["score_threshold"] = user.get("score_threshold", 75)
        return profile

    @router.put("")
    def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
        data = body.model_dump(exclude_none=True)
        threshold = data.pop("score_threshold", None)

        if data:
            db.upsert_profile(user["user_id"], data)

        if threshold is not None:
            db.update_user(user["user_id"], {"score_threshold": threshold})

        return {"updated": True}

    return router

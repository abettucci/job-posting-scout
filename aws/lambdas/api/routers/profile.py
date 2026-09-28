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
    # `seniority` is kept for older profiles. New profiles can choose more than
    # one level (for example junior/entry *and* mid) without letting Senior
    # postings slip through a broad "Mid-Senior" source bucket.
    target_seniorities: Optional[List[str]] = None
    # An explicit requirement cap is more reliable than guessing a candidate's
    # experience from free-form CV dates. Zero clears the cap.
    max_required_years: Optional[int] = None
    eligible_regions: Optional[List[str]] = None  # free text, e.g. ["Argentina", "LATAM", "Worldwide"]

    @field_validator("seniority")
    @classmethod
    def validate_seniority(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _SENIORITY_LEVELS:
            raise ValueError(f"seniority must be one of: {_SENIORITY_LEVELS}")
        return v

    @field_validator("target_seniorities")
    @classmethod
    def validate_target_seniorities(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is None:
            return values
        unique = []
        for value in values:
            if value not in _SENIORITY_LEVELS:
                raise ValueError(f"target_seniorities must contain only: {_SENIORITY_LEVELS}")
            if value not in unique:
                unique.append(value)
        return unique

    @field_validator("max_required_years")
    @classmethod
    def validate_max_required_years(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 0 <= value <= 40:
            raise ValueError("max_required_years must be between 0 and 40")
        return value


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])

    @router.get("")
    def get_profile(user=Depends(get_current_user)):
        profile = db.get_profile(user["user_id"]) or {}
        # Migrate the old one-value preference lazily in the response. A later
        # Save Profile persists the new list; no destructive data migration is
        # needed for existing accounts.
        if "target_seniorities" not in profile:
            profile["target_seniorities"] = [profile["seniority"]] if profile.get("seniority") else []
        profile.setdefault("max_required_years", None)
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

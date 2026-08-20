from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, field_validator

_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}


class SearchCreate(BaseModel):
    url: Optional[str] = None          # LinkedIn URL; optional for ATS sources
    label: str
    source: str = "linkedin"           # "linkedin" | ATS name
    ats_slug: str = ""                 # company slug for ATS sources (e.g. "stripe")
    keywords: str = ""                 # comma-separated keyword filter
    location_filter: str = ""         # location filter string

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed = {"linkedin"} | _ATS_SOURCES
        if v not in allowed:
            raise ValueError(f"source must be one of: {sorted(allowed)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str], info: Any) -> Optional[str]:
        if v:
            try:
                HttpUrl(v)
            except Exception:
                raise ValueError("Invalid URL format")
        return v


class SearchPatch(BaseModel):
    active: bool


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/searches", tags=["searches"])

    @router.get("")
    def list_searches(user=Depends(get_current_user)):
        return db.get_user_searches(user["user_id"])

    @router.post("")
    def create_search(body: SearchCreate, user=Depends(get_current_user)):
        source = body.source

        if source == "linkedin":
            if not body.url:
                raise HTTPException(400, "url is required for LinkedIn searches")
            effective_url = str(body.url)
        else:
            if not body.ats_slug.strip():
                raise HTTPException(400, f"ats_slug is required for {source} searches")
            # Construct a canonical URL for display purposes
            slug = body.ats_slug.strip().lower()
            url_map = {
                "greenhouse": f"https://boards.greenhouse.io/{slug}",
                "lever": f"https://jobs.lever.co/{slug}",
                "ashby": f"https://jobs.ashbyhq.com/{slug}",
                "workable": f"https://apply.workable.com/{slug}",
                "smartrecruiters": f"https://careers.smartrecruiters.com/{slug}",
            }
            effective_url = body.url or url_map.get(source, f"https://{source}.com/{slug}")

        search = {
            "user_id": user["user_id"],
            "search_id": str(uuid.uuid4()),
            "url": effective_url,
            "label": body.label.strip(),
            "source": source,
            "ats_slug": body.ats_slug.strip().lower(),
            "keywords": body.keywords.strip(),
            "location_filter": body.location_filter.strip(),
            "active": True,
            "created_at": datetime.utcnow().isoformat(),
        }
        if not db.create_search(search):
            raise HTTPException(500, "Error creating search")
        return search

    @router.patch("/{search_id}")
    def patch_search(search_id: str, body: SearchPatch, user=Depends(get_current_user)):
        ok = db.update_search(user["user_id"], search_id, {"active": body.active})
        if not ok:
            raise HTTPException(500, "Error updating search")
        return {"search_id": search_id, "active": body.active}

    @router.delete("/{search_id}")
    def delete_search(search_id: str, user=Depends(get_current_user)):
        ok = db.delete_search(user["user_id"], search_id)
        if not ok:
            raise HTTPException(500, "Error deleting search")
        return {"deleted": search_id}

    return router

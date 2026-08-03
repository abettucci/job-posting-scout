from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl


class SearchCreate(BaseModel):
    url: HttpUrl
    label: str


class SearchPatch(BaseModel):
    active: bool


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/searches", tags=["searches"])

    @router.get("")
    def list_searches(user=Depends(get_current_user)):
        return db.get_user_searches(user["user_id"])

    @router.post("")
    def create_search(body: SearchCreate, user=Depends(get_current_user)):
        search = {
            "user_id": user["user_id"],
            "search_id": str(uuid.uuid4()),
            "url": str(body.url),
            "label": body.label.strip(),
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

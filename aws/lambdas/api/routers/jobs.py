from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Query


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.get("")
    def list_jobs(
        min_score: int = Query(0, ge=0, le=100),
        limit: int = Query(20, ge=1, le=100),
        user=Depends(get_current_user),
    ):
        items, next_key = db.get_user_jobs(
            user_id=user["user_id"],
            min_score=min_score,
            limit=limit,
        )
        return {"items": items, "count": len(items)}

    return router

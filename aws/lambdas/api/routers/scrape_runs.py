from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, Query


def make_router(db: Any, get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/scrape-runs", tags=["scrape-runs"])

    @router.get("")
    def list_scrape_runs(
        limit: int = Query(default=8, ge=1, le=30),
        user=Depends(get_current_user),
    ):
        return db.get_scrape_runs(user["user_id"], limit=limit)

    return router

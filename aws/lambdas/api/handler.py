from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
_SHARED = str(Path(__file__).resolve().parent.parent / "shared")
for p in [_HERE, _SHARED]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_config
from db import DynamoDBClient
from auth import make_get_current_user

from routers import auth, searches, profile, telegram_link, jobs, interviews

_cfg = get_config()
_db = DynamoDBClient(
    users_table=_cfg.users_table,
    searches_table=_cfg.searches_table,
    profiles_table=_cfg.profiles_table,
    jobs_table=_cfg.jobs_table,
    telegram_codes_table=_cfg.telegram_codes_table,
    interviews_table=_cfg.interviews_table,
    region=_cfg.region,
)
get_current_user = make_get_current_user(_db, _cfg.jwt_secret)

app = FastAPI(title="LinkedIn Job Scout API", version="1.0.0")

_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
if _cfg.frontend_url:
    _origins.append(_cfg.frontend_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.make_router(_db, _cfg, get_current_user))
app.include_router(searches.make_router(_db, get_current_user))
app.include_router(profile.make_router(_db, get_current_user))
app.include_router(telegram_link.make_router(_db, get_current_user))
app.include_router(jobs.make_router(_db, get_current_user))
app.include_router(interviews.make_router(_db, get_current_user))


@app.get("/health")
def health():
    return {"status": "ok"}


try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = None

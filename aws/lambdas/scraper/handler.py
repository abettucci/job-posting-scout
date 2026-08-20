"""Scraper Lambda — runs on EventBridge schedule.

Pipeline per user:
  1. Get all active searches (LinkedIn or ATS source)
  2. LinkedIn: scrape via Playwright (shared browser session)
     ATS: fetch directly from public API (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)
  3. Dedup against DynamoDB per user
  4. Score new jobs with Claude Haiku against user profile
  5. Notify via Telegram if score >= threshold
  6. Save all new jobs to DynamoDB
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_SHARED_LAMBDA = str(Path(__file__).resolve().parent / "shared")
_SHARED_LOCAL = str(Path(__file__).resolve().parent.parent / "shared")
for _p in [_SHARED_LAMBDA, _SHARED_LOCAL]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import get_config
from db import DynamoDBClient
from telegram import TelegramClient, format_job_notification
from scorer import score_job

from anthropic import Anthropic
from linkedin import run_scraper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_MAX_SCORER_CALLS = int(os.environ.get("MAX_SCORER_CALLS_PER_RUN", "150"))

# ── ATS provider dispatch ─────────────────────────────────────────────────────

_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}


async def _fetch_ats(source: str, slug: str, label: str, keywords: str, location_filter: str) -> List[Dict]:
    """Dispatch to the appropriate ATS provider and return normalized job dicts."""
    if source == "greenhouse":
        from providers.greenhouse import fetch_jobs
    elif source == "lever":
        from providers.lever import fetch_jobs
    elif source == "ashby":
        from providers.ashby import fetch_jobs
    elif source == "workable":
        from providers.workable import fetch_jobs
    elif source == "smartrecruiters":
        from providers.smartrecruiters import fetch_jobs
    else:
        logger.warning(f"Unknown ATS source: {source}")
        return []
    return await fetch_jobs(slug=slug, company_name=label, keywords=keywords, location_filter=location_filter)


# ── Lambda entry point ────────────────────────────────────────────────────────

def lambda_handler(event, context):
    asyncio.run(_main())
    return {"statusCode": 200, "body": "done"}


async def _main():
    cfg = get_config()
    db = DynamoDBClient(
        users_table=cfg.users_table,
        searches_table=cfg.searches_table,
        profiles_table=cfg.profiles_table,
        jobs_table=cfg.jobs_table,
        telegram_codes_table=cfg.telegram_codes_table,
        region=cfg.region,
    )
    tg = TelegramClient(cfg.telegram_bot_token)
    anthropic = Anthropic(api_key=cfg.anthropic_api_key)

    users = db.get_all_linked_users()
    if not users:
        logger.info("No linked users — nothing to do")
        return
    logger.info(f"Processing {len(users)} users")

    # ── Build per-source search maps ──────────────────────────────────────────

    # LinkedIn: { url: [user, ...] }
    linkedin_url_to_users: Dict[str, List] = {}

    # ATS: { (source, slug, keywords, location_filter): {label, users} }
    # Deduplicates identical ATS searches across users (shared fetch).
    ats_key_to_info: Dict[Tuple, Dict] = {}

    for user in users:
        searches = db.get_active_searches(user["user_id"])
        for s in searches:
            source = s.get("source") or "linkedin"
            if source == "linkedin":
                url = s.get("url", "")
                if url:
                    linkedin_url_to_users.setdefault(url, []).append(user)
            elif source in _ATS_SOURCES:
                slug = s.get("ats_slug", "").strip()
                if not slug:
                    logger.warning(f"ATS search {s.get('search_id')} has no ats_slug — skipping")
                    continue
                key = (source, slug, s.get("keywords", ""), s.get("location_filter", ""))
                if key not in ats_key_to_info:
                    ats_key_to_info[key] = {"label": s.get("label", slug), "users": []}
                if user not in ats_key_to_info[key]["users"]:
                    ats_key_to_info[key]["users"].append(user)

    # ── LinkedIn scraping (existing Playwright flow) ──────────────────────────

    linkedin_jobs: List[Dict] = []
    if linkedin_url_to_users:
        try:
            linkedin_jobs = await run_scraper(
                search_urls=list(linkedin_url_to_users.keys()),
                email=cfg.linkedin_email,
                password=cfg.linkedin_password,
                region=cfg.region,
            )
            logger.info(f"LinkedIn scraper returned {len(linkedin_jobs)} jobs")
        except Exception as e:
            logger.error(f"LinkedIn scraper failed: {e}")

    # ── ATS fetching (concurrent, zero-auth HTTP) ─────────────────────────────

    ats_results: Dict[Tuple, Tuple[List[Dict], List]] = {}  # key → (jobs, users)

    async def _fetch_and_store(key: Tuple, info: Dict):
        source, slug, keywords, location_filter = key
        try:
            jobs = await _fetch_ats(source, slug, info["label"], keywords, location_filter)
            ats_results[key] = (jobs, info["users"])
            logger.info(f"ATS {source}/{slug}: {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"ATS {source}/{slug} failed: {e}")
            ats_results[key] = ([], info["users"])

    if ats_key_to_info:
        await asyncio.gather(*[_fetch_and_store(k, v) for k, v in ats_key_to_info.items()])

    # ── Process jobs: dedup → score → notify → save ───────────────────────────

    scorer_calls = 0
    total_notified = 0

    def process_job_for_user(user: Dict, job: Dict):
        nonlocal scorer_calls, total_notified
        user_id = user["user_id"]
        job_id = job.get("job_id")
        if not job_id or db.is_job_seen(user_id, job_id):
            return

        profile = db.get_profile(user_id) or {}
        if not profile:
            _save_unscored(db, user_id, job)
            return

        if scorer_calls >= _MAX_SCORER_CALLS:
            logger.warning(f"Claude cap reached. Saving '{job.get('title')}' unscored.")
            _save_unscored(db, user_id, job)
            return

        result = score_job(anthropic, job, profile)
        scorer_calls += 1
        threshold = int(user.get("score_threshold", 75))
        should_notify = result["score"] >= threshold and not result["deal_breaker"]

        if should_notify:
            chat_id = user.get("telegram_chat_id")
            if chat_id:
                tg.send_message(int(chat_id), format_job_notification(job, result))
                total_notified += 1

        _save_scored_job(db, user_id, job, result, notified=should_notify)

    # LinkedIn jobs → all users (existing behavior: shared searches)
    for job in linkedin_jobs:
        for user in users:
            process_job_for_user(user, job)

    # ATS jobs → only the users who subscribed to that specific search
    for key, (jobs, subscribed_users) in ats_results.items():
        for job in jobs:
            for user in subscribed_users:
                process_job_for_user(user, job)

    logger.info(f"Done. scorer_calls={scorer_calls}/{_MAX_SCORER_CALLS}, notified={total_notified}.")


def _save_scored_job(db: DynamoDBClient, user_id: str, job: dict, result: dict, notified: bool):
    db.save_job({
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", "")[:6000],
        "score": result["score"],
        "summary": result.get("summary", ""),
        "reasons": result.get("reasons", []),
        "deal_breaker": result.get("deal_breaker", False),
        "recommendation": result.get("recommendation", "MAYBE"),
        "notified": notified,
        "timestamp": datetime.utcnow().isoformat(),
    })


def _save_unscored(db: DynamoDBClient, user_id: str, job: dict):
    db.save_job({
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", "")[:6000],
        "score": 0,
        "summary": "",
        "reasons": [],
        "deal_breaker": False,
        "recommendation": "SKIP",
        "notified": False,
        "timestamp": datetime.utcnow().isoformat(),
    })

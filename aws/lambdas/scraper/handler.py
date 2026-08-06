"""Scraper Lambda — runs on EventBridge schedule.

Pipeline per user:
  1. Get all active searches for the user
  2. Scrape LinkedIn (shared browser session)
  3. Dedup against DynamoDB
  4. Score new jobs with Claude Haiku
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

# Hard cap on Claude API calls per Lambda invocation. Prevents runaway spend if
# search URLs or user count grows unexpectedly. Jobs beyond the cap are saved
# without a score (recommendation=SKIP, no Telegram notification).
_MAX_SCORER_CALLS = int(os.environ.get("MAX_SCORER_CALLS_PER_RUN", "150"))


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

    # Collect all unique search URLs across all users (to avoid redundant browser passes)
    url_to_users: dict[str, list] = {}
    for user in users:
        searches = db.get_active_searches(user["user_id"])
        for s in searches:
            url = s["url"]
            if url not in url_to_users:
                url_to_users[url] = []
            url_to_users[url].append(user)

    if not url_to_users:
        logger.info("No active searches")
        return

    all_urls = list(url_to_users.keys())
    logger.info(f"Scraping {len(all_urls)} unique search URLs")

    raw_jobs = await run_scraper(
        search_urls=all_urls,
        email=cfg.linkedin_email,
        password=cfg.linkedin_password,
        region=cfg.region,
    )
    logger.info(f"Scraper returned {len(raw_jobs)} total raw jobs")

    # Build a mapping: url → list of raw jobs (one set per URL)
    # Since run_scraper returns all jobs flat, we need to track which URL produced which job.
    # We redesign: run_scraper returns per-url batches. For now, process all jobs for all users.
    # Each job is deduped per-user independently.

    total_notified = 0
    scorer_calls = 0

    for job in raw_jobs:
        job_id = job.get("job_id")
        if not job_id:
            continue

        # Find which users need to see this job (their search URL produced it)
        # Since we collapsed URLs, every user with active searches might be interested.
        # A proper production system would map job → source URL → users; for now we check all users.
        for user in users:
            user_id = user["user_id"]

            if db.is_job_seen(user_id, job_id):
                continue

            profile = db.get_profile(user_id) or {}
            if not profile:
                logger.info(f"User {user_id} has no profile — skipping scoring")
                _save_unscored(db, user_id, job)
                continue

            if scorer_calls >= _MAX_SCORER_CALLS:
                logger.warning(
                    f"Claude API cap reached ({_MAX_SCORER_CALLS} calls). "
                    f"Saving job '{job.get('title')}' for user {user_id} without score."
                )
                _save_unscored(db, user_id, job)
                continue

            result = score_job(anthropic, job, profile)
            scorer_calls += 1
            threshold = int(user.get("score_threshold", 75))
            should_notify = result["score"] >= threshold and not result["deal_breaker"]

            if should_notify:
                chat_id = user.get("telegram_chat_id")
                if chat_id:
                    msg = format_job_notification(job, result)
                    tg.send_message(int(chat_id), msg)
                    total_notified += 1

            _save_scored_job(db, user_id, job, result, notified=should_notify)

    logger.info(f"Done. scorer_calls={scorer_calls}/{_MAX_SCORER_CALLS}, notified={total_notified}.")


def _save_scored_job(db: DynamoDBClient, user_id: str, job: dict, result: dict, notified: bool):
    db.save_job({
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
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
        "score": 0,
        "summary": "",
        "reasons": [],
        "deal_breaker": False,
        "recommendation": "SKIP",
        "notified": False,
        "timestamp": datetime.utcnow().isoformat(),
    })

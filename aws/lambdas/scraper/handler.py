"""Scraper Lambda — runs on EventBridge schedule.

Pipeline per user:
  1. Get all active searches (LinkedIn, ATS, aggregator, or multi_board source)
  2. LinkedIn: scrape via Playwright (shared browser session)
     ATS: fetch directly from public API, one company per search (Greenhouse,
          Lever, Ashby, Workable, SmartRecruiters)
     Aggregator: fetch directly from public API, global feed filtered by
          keywords (RemoteOK, WorkingNomads, Remotive, Arbeitnow), or HTML
          scraping for sources with no public API (CompuJobs, OnlineJobs.ph)
     Multi-board: one profile-shaped search (job_title + seniority) fanned out
          into an auto-built LinkedIn URL plus a keyword search on every
          aggregator above — see "Multi-board fan-out" below
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode

_SHARED_LAMBDA = str(Path(__file__).resolve().parent / "shared")
_SHARED_LOCAL = str(Path(__file__).resolve().parent.parent / "shared")
for _p in [_SHARED_LAMBDA, _SHARED_LOCAL]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import get_config
from db import DynamoDBClient
from telegram import TelegramClient, format_job_notification
from scorer import ScoringRouter, ScoringUnavailableError, score_job
from seniority import (
    SENIORITY_LEVELS,
    SENIORITY_TO_LINKEDIN_F_E,
    extract_company_size_hint,
    extract_experience_mentions,
    extract_region_scope,
    extract_requirements,
)

from linkedin import run_scraper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_MAX_SCORER_CALLS = int(os.environ.get("MAX_SCORER_CALLS_PER_RUN", "150"))
_MAX_PENDING_RETRIES_PER_RUN = int(os.environ.get("MAX_PENDING_RETRIES_PER_RUN", "50"))


def _is_senior_title(title: str) -> bool:
    """Keep title-level Senior roles out of Telegram without regex matching."""
    return "senior" in (title or "").casefold()


def _should_notify(job: Dict, result: Dict, threshold: int) -> bool:
    """Strict, notification-only gate; jobs remain saved regardless of outcome."""
    return (
        result["score"] >= threshold
        and not result["deal_breaker"]
        and not _is_senior_title(job.get("title", ""))
        # This is produced by the scoring model from the full posting text,
        # rather than inferred by a location regex.
        and result.get("notification_location_allowed") is True
    )


def _scoring_router(cfg) -> ScoringRouter:
    return ScoringRouter(
        anthropic_api_key=cfg.anthropic_api_key,
        fallback_base_url=cfg.omniroute_base_url,
        fallback_api_key=cfg.omniroute_api_key,
        fallback_model=cfg.omniroute_model,
    )

# ── ATS provider dispatch ─────────────────────────────────────────────────────

_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday", "deel"}


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
    elif source == "workday":
        from providers.workday import fetch_jobs
    elif source == "deel":
        from providers.deel import fetch_jobs
    else:
        logger.warning(f"Unknown ATS source: {source}")
        return []
    return await fetch_jobs(slug=slug, company_name=label, keywords=keywords, location_filter=location_filter)


# ── Aggregator provider dispatch ──────────────────────────────────────────────
# Unlike ATS sources (one company board per slug), aggregators are global job
# feeds — a single fetch returns postings from many companies, so there is no
# slug to key on. Keywords act as the primary filter to keep volume sane.

_AGGREGATOR_SOURCES = {"remoteok", "workingnomads", "remotive", "arbeitnow", "compujobs", "onlinejobs", "yc", "freehire"}


async def _fetch_aggregator(source: str, keywords: str, location_filter: str) -> List[Dict]:
    """Dispatch to the appropriate aggregator provider and return normalized job dicts."""
    if source == "remoteok":
        from providers.remoteok import fetch_jobs
    elif source == "workingnomads":
        from providers.workingnomads import fetch_jobs
    elif source == "remotive":
        from providers.remotive import fetch_jobs
    elif source == "arbeitnow":
        from providers.arbeitnow import fetch_jobs
    elif source == "compujobs":
        from providers.compujobs import fetch_jobs
    elif source == "onlinejobs":
        from providers.onlinejobs import fetch_jobs
    elif source == "yc":
        from providers.yc import fetch_jobs
    elif source == "freehire":
        from providers.freehire import fetch_jobs
    else:
        logger.warning(f"Unknown aggregator source: {source}")
        return []
    return await fetch_jobs(keywords=keywords, location_filter=location_filter)


# ── Multi-board fan-out ───────────────────────────────────────────────────────
# A multi_board search has no source-specific plumbing of its own: it expands
# into one LinkedIn URL (built from job_title/seniority/location) plus one
# keyword search per aggregator, and rides the existing LinkedIn/aggregator
# fetch paths above unchanged. Seniority is only applied to LinkedIn, which has
# a native "Experience level" filter (f_E) — RemoteOK/WorkingNomads/Remotive/
# Arbeitnow have no structured seniority field, and keyword_match's OR-across-
# comma semantics would make appending it as a keyword widen the match instead
# of narrowing it (e.g. "python developer, senior" matches either term, not
# both), so it is deliberately left out of the aggregator keyword string.
# Company size is not applied anywhere: none of these sources expose it as a
# queryable filter without a paid third-party company-database lookup.

_MULTI_BOARD_SOURCE = "multi_board"


def _build_linkedin_url(job_title: str, seniority: str, location_filter: str) -> str:
    params = {"keywords": job_title}
    if location_filter:
        params["location"] = location_filter
    f_e = SENIORITY_TO_LINKEDIN_F_E.get(seniority)
    if f_e:
        params["f_E"] = f_e
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


# ── Requirement extraction & hard-filters (seniority, remote region) ─────────
# Runs for every job regardless of profile, so seniority_level/
# min_years_experience/region_scope are always persisted (useful even before a
# profile exists). Each hard-filter only fires when the candidate has declared
# the matching preference AND the posting's own text yielded a confident signal.

def _enrich_job(job: Dict) -> Dict:
    extracted = extract_requirements(job.get("title", ""), job.get("description", ""))
    region_scope = extract_region_scope(job.get("location", ""), job.get("description", ""))
    experience_mentions = extract_experience_mentions(job.get("description", ""))

    # LinkedIn-sourced company size (from linkedin.py's fetch_linkedin_company_size,
    # already attached to the job dict — LinkedIn jobs only) wins over recomputing
    # from the posting's own text, since it's LinkedIn's own self-reported figure
    # rather than a regex guess. Aggregator/ATS jobs never carry a pre-set
    # company_size_source, so they always fall to the description-based guess.
    if job.get("company_size_hint") and job.get("company_size_source") == "linkedin":
        company_size_hint = job["company_size_hint"]
        company_size_source = "linkedin"
        company_size_raw = job.get("company_size_raw")
    else:
        company_size_hint = extract_company_size_hint(job.get("description", ""))
        company_size_source = "description" if company_size_hint else None
        company_size_raw = None

    return {
        **job,
        **extracted,
        "region_scope": region_scope,
        "company_size_hint": company_size_hint,
        "company_size_source": company_size_source,
        "company_size_raw": company_size_raw,
        "experience_mentions": experience_mentions,
    }


def _seniority_mismatch(job: Dict, profile: Dict) -> Dict | None:
    """Hard-filter check: if the candidate declared a seniority level in their
    profile and the job's own extracted level is different, skip
    Claude entirely and return a synthetic deal-breaker result (same shape as
    score_job()'s return value). The title classifier deliberately separates
    Mid, Senior, and Staff/Principal, so an explicitly labelled "Senior"
    posting must not pass a Mid-level preference just because LinkedIn groups
    both under its broad native "Mid-Senior" bucket."""
    candidate_level = profile.get("seniority")
    job_level = job.get("seniority_level")
    if not candidate_level or not job_level:
        return None
    if candidate_level not in SENIORITY_LEVELS or job_level not in SENIORITY_LEVELS:
        return None
    if candidate_level == job_level:
        return None
    return {
        "score": 0,
        "deal_breaker": True,
        "reasons": [f"❌ Seniority mismatch: posting reads as '{job_level}', your profile is '{candidate_level}'"],
        "summary": "Filtered automatically before scoring — seniority does not match your preference.",
        "recommendation": "SKIP",
    }


def _region_mismatch(job: Dict, profile: Dict) -> Dict | None:
    """Hard-filter check: if the candidate declared eligible regions and the
    job's own text confidently names a specific place that isn't among them
    (e.g. "remote — Germany only" for a candidate who only listed Argentina),
    skip Claude entirely. A "worldwide" or "latam" job never triggers this —
    only "restricted" does, and even then only if none of the candidate's
    declared regions appears anywhere in the job's own location/description
    text (so adding e.g. "Germany" to the profile later immediately widens
    what passes, no code change needed). An unclear job (region_scope is None)
    is never filtered — same "don't penalize missing data" rule as seniority."""
    eligible = profile.get("eligible_regions") or []
    if not eligible or job.get("region_scope") != "restricted":
        return None
    haystack = f"{job.get('location', '')} {job.get('description', '')}".lower()
    if any(region.strip().lower() in haystack for region in eligible if region.strip()):
        return None
    return {
        "score": 0,
        "deal_breaker": True,
        "reasons": [f"❌ Region restricted: posting doesn't look open to {', '.join(eligible)}"],
        "summary": "Filtered automatically before scoring — remote region restriction.",
        "recommendation": "SKIP",
    }


# ── Lambda entry point ────────────────────────────────────────────────────────

def lambda_handler(event, context):
    mode = (event or {}).get("mode", "scrape")
    if mode == "rescore":
        user_id = (event or {}).get("user_id")
        if not user_id:
            logger.error("rescore mode requires a user_id")
            return {"statusCode": 400, "body": "user_id required for rescore"}
        asyncio.run(_rescore(user_id))
    else:
        asyncio.run(_main())
    return {"statusCode": 200, "body": "done"}


async def _rescore(user_id: str):
    """Re-score this user's already-saved jobs that never got a real score
    (score == 0, saved via _save_unscored — e.g. because their profile was
    still empty at scrape time). Does not re-fetch from any source: title,
    company, location, url, description, and posted_date are already in
    DynamoDB, so this only re-runs the Claude Haiku scoring pass and
    overwrites those rows in place. Never re-notifies via Telegram — this is
    a backfill of old jobs, not a "new job found" event."""
    cfg = get_config()
    db = DynamoDBClient(
        users_table=cfg.users_table,
        searches_table=cfg.searches_table,
        profiles_table=cfg.profiles_table,
        jobs_table=cfg.jobs_table,
        telegram_codes_table=cfg.telegram_codes_table,
        region=cfg.region,
    )
    scorer = _scoring_router(cfg)

    profile = db.get_profile(user_id)
    if not profile:
        logger.warning(f"rescore: user {user_id} has no profile — nothing to score against")
        return

    unscored: List[Dict] = []
    last_key = None
    while True:
        items, last_key = db.get_user_jobs(user_id=user_id, min_score=0, limit=100, last_key=last_key)
        unscored.extend(j for j in items if j.get("score", 0) == 0)
        if not last_key:
            break

    logger.info(f"rescore: {len(unscored)} unscored jobs found for user {user_id}")

    scored = 0
    for job in unscored:
        job = _enrich_job(job)

        mismatch = _seniority_mismatch(job, profile) or _region_mismatch(job, profile)
        if mismatch:
            _save_scored_job(db, user_id, job, mismatch, notified=False)
            continue

        if scored >= _MAX_SCORER_CALLS:
            logger.warning(f"rescore: Claude cap ({_MAX_SCORER_CALLS}) reached, stopping early")
            break
        try:
            result = score_job(scorer, job, profile)
        except ScoringUnavailableError as exc:
            _save_pending_scoring(db, user_id, job, str(exc))
            logger.warning("rescore: scoring unavailable; keeping remaining jobs pending")
            break
        scored += 1
        _save_scored_job(db, user_id, job, result, notified=False)

    logger.info(f"rescore: done. scored {scored}/{len(unscored)} jobs for user {user_id}.")


async def _main():
    cfg = get_config()
    db = DynamoDBClient(
        users_table=cfg.users_table,
        searches_table=cfg.searches_table,
        profiles_table=cfg.profiles_table,
        jobs_table=cfg.jobs_table,
        telegram_codes_table=cfg.telegram_codes_table,
        company_size_cache_table=cfg.company_size_cache_table,
        region=cfg.region,
    )
    tg = TelegramClient(cfg.telegram_bot_token)
    scorer = _scoring_router(cfg)

    users = db.get_all_linked_users()
    if not users:
        logger.info("No linked users — nothing to do")
        return
    logger.info(f"Processing {len(users)} users")

    # Retry only jobs that were explicitly deferred after all configured
    # providers failed. They were saved but never treated as a SKIP, so a quota
    # outage cannot silently lose an otherwise good opportunity.
    await _retry_pending_scoring(db, users, scorer, tg)

    # ── Build per-source search maps ──────────────────────────────────────────

    # LinkedIn: { url: [user, ...] }
    linkedin_url_to_users: Dict[str, List] = {}

    # ATS: { (source, slug, keywords, location_filter): {label, users} }
    # Deduplicates identical ATS searches across users (shared fetch).
    ats_key_to_info: Dict[Tuple, Dict] = {}

    # Aggregator: { (source, keywords, location_filter): {label, users} }
    # Deduplicates identical aggregator searches across users (shared fetch).
    aggregator_key_to_info: Dict[Tuple, Dict] = {}

    for user in users:
        searches = db.get_active_searches(user["user_id"])
        for s in searches:
            source = s.get("source") or "linkedin"
            if source == "linkedin":
                url = s.get("url", "")
                if url:
                    linkedin_url_to_users.setdefault(url, []).append(user)
            elif source in _ATS_SOURCES:
                slug = (s.get("url", "") if source in {"workday", "deel"} else s.get("ats_slug", "")).strip()
                if not slug:
                    logger.warning(f"ATS search {s.get('search_id')} has no board reference — skipping")
                    continue
                key = (source, slug, s.get("keywords", ""), s.get("location_filter", ""))
                if key not in ats_key_to_info:
                    ats_key_to_info[key] = {"label": s.get("label", slug), "users": []}
                if user not in ats_key_to_info[key]["users"]:
                    ats_key_to_info[key]["users"].append(user)
            elif source in _AGGREGATOR_SOURCES:
                keywords = s.get("keywords", "").strip()
                if not keywords:
                    logger.warning(f"Aggregator search {s.get('search_id')} has no keywords — skipping")
                    continue
                key = (source, keywords, s.get("location_filter", ""))
                if key not in aggregator_key_to_info:
                    aggregator_key_to_info[key] = {"label": s.get("label", source), "users": []}
                if user not in aggregator_key_to_info[key]["users"]:
                    aggregator_key_to_info[key]["users"].append(user)
            elif source == _MULTI_BOARD_SOURCE:
                job_title = s.get("job_title", "").strip()
                if not job_title:
                    logger.warning(f"Multi-board search {s.get('search_id')} has no job_title — skipping")
                    continue
                seniority = s.get("seniority", "").strip()
                location_filter = s.get("location_filter", "")

                # 1) LinkedIn — auto-built URL, folded into the existing LinkedIn flow
                li_url = _build_linkedin_url(job_title, seniority, location_filter)
                linkedin_url_to_users.setdefault(li_url, []).append(user)

                # 2) Every aggregator board — folded into the existing aggregator flow
                for agg_source in _AGGREGATOR_SOURCES:
                    key = (agg_source, job_title, location_filter)
                    if key not in aggregator_key_to_info:
                        aggregator_key_to_info[key] = {"label": s.get("label", job_title), "users": []}
                    if user not in aggregator_key_to_info[key]["users"]:
                        aggregator_key_to_info[key]["users"].append(user)

    # ── LinkedIn scraping (existing Playwright flow) ──────────────────────────

    linkedin_results: Dict[str, List[Dict]] = {}  # url → jobs
    if linkedin_url_to_users:
        try:
            linkedin_results = await run_scraper(
                search_urls=list(linkedin_url_to_users.keys()),
                email=cfg.linkedin_email,
                password=cfg.linkedin_password,
                region=cfg.region,
                cache_get=db.get_company_size_cache,
                cache_put=db.save_company_size_cache,
            )
            logger.info(f"LinkedIn scraper returned {sum(len(v) for v in linkedin_results.values())} jobs "
                        f"across {len(linkedin_results)} searches")
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

    # ── Aggregator fetching (concurrent, zero-auth HTTP) ──────────────────────

    aggregator_results: Dict[Tuple, Tuple[List[Dict], List]] = {}  # key → (jobs, users)

    async def _fetch_and_store_aggregator(key: Tuple, info: Dict):
        source, keywords, location_filter = key
        try:
            jobs = await _fetch_aggregator(source, keywords, location_filter)
            aggregator_results[key] = (jobs, info["users"])
            logger.info(f"Aggregator {source} ({keywords!r}): {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Aggregator {source} ({keywords!r}) failed: {e}")
            aggregator_results[key] = ([], info["users"])

    if aggregator_key_to_info:
        await asyncio.gather(*[_fetch_and_store_aggregator(k, v) for k, v in aggregator_key_to_info.items()])

    # ── Process jobs: dedup → score → notify → save ───────────────────────────

    scorer_calls = 0
    total_notified = 0

    def process_job_for_user(user: Dict, job: Dict):
        nonlocal scorer_calls, total_notified
        user_id = user["user_id"]
        job_id = job.get("job_id")
        if not job_id or db.is_job_seen(user_id, job_id):
            return

        job = _enrich_job(job)

        profile = db.get_profile(user_id) or {}
        if not profile:
            _save_unscored(db, user_id, job)
            return

        mismatch = _seniority_mismatch(job, profile) or _region_mismatch(job, profile)
        if mismatch:
            _save_scored_job(db, user_id, job, mismatch, notified=False)
            return

        if scorer_calls >= _MAX_SCORER_CALLS:
            logger.warning(f"Claude cap reached. Saving '{job.get('title')}' unscored.")
            _save_unscored(db, user_id, job)
            return

        try:
            result = score_job(scorer, job, profile)
        except ScoringUnavailableError as exc:
            _save_pending_scoring(db, user_id, job, str(exc))
            _notify_scoring_outage(db, tg, user)
            return
        _notify_scoring_recovery(db, tg, user)
        scorer_calls += 1
        threshold = int(user.get("score_threshold", 75))
        should_notify = _should_notify(job, result, threshold)

        if should_notify:
            chat_id = user.get("telegram_chat_id")
            if chat_id:
                tg.send_message(int(chat_id), format_job_notification(job, result))
                total_notified += 1

        _save_scored_job(db, user_id, job, result, notified=should_notify)

    # LinkedIn jobs → only the users who subscribed to that specific search URL
    for url, jobs in linkedin_results.items():
        subscribed_users = linkedin_url_to_users.get(url, [])
        for job in jobs:
            for user in subscribed_users:
                process_job_for_user(user, job)

    # ATS jobs → only the users who subscribed to that specific search
    for key, (jobs, subscribed_users) in ats_results.items():
        for job in jobs:
            for user in subscribed_users:
                process_job_for_user(user, job)

    # Aggregator jobs → only the users who subscribed to that specific search
    for key, (jobs, subscribed_users) in aggregator_results.items():
        for job in jobs:
            for user in subscribed_users:
                process_job_for_user(user, job)

    logger.info(f"Done. scorer_calls={scorer_calls}/{_MAX_SCORER_CALLS}, notified={total_notified}.")


def _save_scored_job(db: DynamoDBClient, user_id: str, job: dict, result: dict, notified: bool):
    payload = {
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", "")[:6000],
        "posted_date": job.get("posted_date"),
        "seniority_level": job.get("seniority_level"),
        "min_years_experience": job.get("min_years_experience"),
        "region_scope": job.get("region_scope"),
        "company_size_hint": job.get("company_size_hint"),
        "company_size_source": job.get("company_size_source"),
        "company_size_raw": job.get("company_size_raw"),
        "experience_mentions": job.get("experience_mentions", []),
        "score": result["score"],
        "summary": result.get("summary", ""),
        "reasons": result.get("reasons", []),
        "deal_breaker": result.get("deal_breaker", False),
        "recommendation": result.get("recommendation", "MAYBE"),
        "notified": notified,
        "scoring_status": "scored",
        "scoring_provider": result.get("scoring_provider", "unknown"),
        "notification_location_allowed": result.get("notification_location_allowed"),
        "notification_location_reason": result.get("notification_location_reason", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Preserve queue choices if a saved job is reprocessed.
    for field in ("applied", "applied_at", "dismissed", "dismissed_at"):
        if field in job:
            payload[field] = job[field]
    db.save_job(payload)


def _save_unscored(db: DynamoDBClient, user_id: str, job: dict):
    db.save_job({
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", "")[:6000],
        "posted_date": job.get("posted_date"),
        "seniority_level": job.get("seniority_level"),
        "min_years_experience": job.get("min_years_experience"),
        "region_scope": job.get("region_scope"),
        "company_size_hint": job.get("company_size_hint"),
        "company_size_source": job.get("company_size_source"),
        "company_size_raw": job.get("company_size_raw"),
        "experience_mentions": job.get("experience_mentions", []),
        "score": 0,
        "summary": "",
        "reasons": [],
        "deal_breaker": False,
        "recommendation": "SKIP",
        "notified": False,
        "scoring_status": "profile_missing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _save_pending_scoring(db: DynamoDBClient, user_id: str, job: dict, error: str):
    """Persist an unscored job for automatic retry without exposing provider internals."""
    prior_attempts = int(job.get("scoring_attempts", 0) or 0)
    payload = {
        "user_id": user_id,
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", "")[:6000],
        "posted_date": job.get("posted_date"),
        "seniority_level": job.get("seniority_level"),
        "min_years_experience": job.get("min_years_experience"),
        "region_scope": job.get("region_scope"),
        "company_size_hint": job.get("company_size_hint"),
        "company_size_source": job.get("company_size_source"),
        "company_size_raw": job.get("company_size_raw"),
        "experience_mentions": job.get("experience_mentions", []),
        "score": 0,
        "summary": "",
        "reasons": ["Scoring pending — provider temporarily unavailable"],
        "deal_breaker": False,
        "recommendation": "MAYBE",
        "notified": False,
        "scoring_status": "pending",
        "scoring_attempts": prior_attempts + 1,
        # Keep this coarse and safe: no API response, credential, or provider
        # payload is stored in the job record.
        "scoring_error_class": error.split(":", 1)[0][:80],
        "timestamp": job.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    }
    for field in ("applied", "applied_at", "dismissed", "dismissed_at"):
        if field in job:
            payload[field] = job[field]
    db.save_job(payload)


def _notify_scoring_outage(db: DynamoDBClient, tg: TelegramClient, user: Dict):
    """Open one user-visible incident instead of alerting once per job."""
    if user.get("scoring_incident_open"):
        return
    chat_id = user.get("telegram_chat_id")
    if not chat_id:
        return
    message = (
        "⚠️ *Job Scout — scoring pausado*\n\n"
        "No se pueden evaluar matches nuevos porque todos los proveedores de IA "
        "configurados están temporalmente indisponibles o sin cuota.\n\n"
        "Los postings nuevos se guardan como pendientes y se reintentarán "
        "automáticamente. Te voy a avisar cuando el servicio se recupere."
    )
    if tg.send_message(int(chat_id), message):
        db.update_user(
            user["user_id"],
            {
                "scoring_incident_open": True,
                "scoring_incident_started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        # The in-memory user is shared through this run, so suppress duplicates
        # before the next DynamoDB read too.
        user["scoring_incident_open"] = True


def _notify_scoring_recovery(db: DynamoDBClient, tg: TelegramClient, user: Dict):
    """Close an open incident only after a scoring request succeeds."""
    if not user.get("scoring_incident_open"):
        return
    chat_id = user.get("telegram_chat_id")
    if chat_id:
        tg.send_message(
            int(chat_id),
            "✅ *Job Scout — scoring recuperado*\n\n"
            "Las evaluaciones volvieron a funcionar. Los postings pendientes "
            "se están reintentando automáticamente.",
        )
    db.update_user(
        user["user_id"],
        {
            "scoring_incident_open": False,
            "scoring_incident_recovered_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    user["scoring_incident_open"] = False


async def _retry_pending_scoring(
    db: DynamoDBClient, users: List[Dict], scorer: ScoringRouter, tg: TelegramClient
):
    """Retry deferred jobs before fetching new ones; stop on a global outage."""
    retried = 0
    for user in users:
        if retried >= _MAX_PENDING_RETRIES_PER_RUN:
            break
        profile = db.get_profile(user["user_id"]) or {}
        if not profile:
            continue
        items: List[Dict] = []
        last_key = None
        while True:
            page, last_key = db.get_user_jobs(
                user_id=user["user_id"], min_score=0, limit=100, last_key=last_key
            )
            items.extend(page)
            if not last_key:
                break
        pending = [
            job for job in items
            if job.get("scoring_status") == "pending"
            # Jobs saved by versions before the resilient router used this
            # neutral marker for an LLM outage. Recover them automatically too.
            or "Error al puntuar" in job.get("reasons", [])
        ]
        for job in pending:
            if retried >= _MAX_PENDING_RETRIES_PER_RUN:
                break
            job = _enrich_job(job)
            mismatch = _seniority_mismatch(job, profile) or _region_mismatch(job, profile)
            if mismatch:
                _save_scored_job(db, user["user_id"], job, mismatch, notified=False)
                continue
            try:
                result = score_job(scorer, job, profile)
            except ScoringUnavailableError as exc:
                _save_pending_scoring(db, user["user_id"], job, str(exc))
                _notify_scoring_outage(db, tg, user)
                logger.warning("Pending scoring paused: no provider is currently available")
                return
            _notify_scoring_recovery(db, tg, user)
            threshold = int(user.get("score_threshold", 75))
            should_notify = _should_notify(job, result, threshold)
            if should_notify and user.get("telegram_chat_id"):
                tg.send_message(int(user["telegram_chat_id"]), format_job_notification(job, result))
            _save_scored_job(db, user["user_id"], job, result, notified=should_notify)
            retried += 1
    if retried:
        logger.info("Retried %s deferred scoring jobs", retried)

"""Remotive aggregator provider — public remotive.com/api/remote-jobs endpoint.
No auth required. Global remote-jobs feed (not company-scoped): a single call
returns the current listing, filtered client-side by keywords/location like
the ATS providers.

API terms require attribution and cap request frequency (~4/day):
https://remotive.com/api-documentation
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://remotive.com/api/remote-jobs"


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_API_URL, headers={"User-Agent": "LinkedInJobScout/1.0"})
        resp.raise_for_status()
        data = resp.json()

    raw_jobs = data.get("jobs") or []
    if not isinstance(raw_jobs, list):
        logger.warning("remotive: unexpected jobs field")
        return []

    jobs: List[Dict] = []
    for j in raw_jobs:
        native_id = j.get("id")
        title = (j.get("title") or "").strip()
        job_url = (j.get("url") or "").strip()
        company = (j.get("company_name") or "").strip()
        loc = (j.get("candidate_required_location") or "").strip() or "Remote"
        desc = strip_html(j.get("description") or "")
        job_id = f"remotive:{native_id}"

        if not title or not job_url:
            continue
        if not keyword_match(f"{title} {desc}", keywords):
            continue
        if not location_match(loc, location_filter):
            continue

        jobs.append({
            "job_id": job_id,
            "title": title,
            "company": company,
            "location": loc,
            "url": job_url,
            "description": desc[:6000],
        })

    logger.info(f"remotive: {len(jobs)} jobs (after filters)")
    return jobs

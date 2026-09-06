"""Arbeitnow aggregator provider — public arbeitnow.com/api/job-board-api endpoint.
No auth required. Global jobs feed (not company-scoped, mostly EU/DE-focused
with a "remote" flag per posting), filtered client-side by keywords/location
like the ATS providers.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://www.arbeitnow.com/api/job-board-api"


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_API_URL, headers={"User-Agent": "LinkedInJobScout/1.0"})
        resp.raise_for_status()
        data = resp.json()

    raw_jobs = data.get("data") or []
    if not isinstance(raw_jobs, list):
        logger.warning("arbeitnow: unexpected data field")
        return []

    jobs: List[Dict] = []
    for j in raw_jobs:
        slug = j.get("slug") or ""
        title = (j.get("title") or "").strip()
        job_url = (j.get("url") or "").strip()
        company = (j.get("company_name") or "").strip()
        loc = (j.get("location") or "").strip()
        if j.get("remote"):
            loc = f"{loc} (Remote)".strip() if loc else "Remote"
        desc = strip_html(j.get("description") or "")
        job_id = f"arbeitnow:{slug}"

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

    logger.info(f"arbeitnow: {len(jobs)} jobs (after filters)")
    return jobs

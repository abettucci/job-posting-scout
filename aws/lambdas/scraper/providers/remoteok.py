"""RemoteOK aggregator provider — public remoteok.com/api endpoint.
No auth required. Global remote-jobs feed (not company-scoped): every call
returns the same ~100 most recent postings across all companies, filtered
client-side by keywords/location like the ATS providers.

API terms require attribution: https://remoteok.com/api
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://remoteok.com/api"


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_API_URL, headers={"User-Agent": "LinkedInJobScout/1.0"})
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        logger.warning("remoteok: unexpected response type")
        return []

    jobs: List[Dict] = []
    for j in data:
        native_id = j.get("id")
        if not native_id:  # first array entry is a legal notice, not a job
            continue

        title = (j.get("position") or "").strip()
        job_url = (j.get("url") or j.get("apply_url") or "").strip()
        company = (j.get("company") or "").strip()
        loc = (j.get("location") or "").strip() or "Remote"
        desc = strip_html(j.get("description") or "")
        job_id = f"remoteok:{native_id}"

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

    logger.info(f"remoteok: {len(jobs)} jobs (after filters)")
    return jobs

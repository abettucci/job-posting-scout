"""WorkingNomads aggregator provider — public workingnomads.com/api/exposed_jobs endpoint.
No auth required. Global remote-jobs feed (not company-scoped): a single call
returns the current listing, filtered client-side by keywords/location like
the ATS providers. The feed has no stable numeric id, so the job's own URL
(unique per posting) is used as the identifier.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_API_URL, headers={"User-Agent": "LinkedInJobScout/1.0"})
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        logger.warning("workingnomads: unexpected response type")
        return []

    jobs: List[Dict] = []
    for j in data:
        title = (j.get("title") or "").strip()
        job_url = (j.get("url") or "").strip()
        company = (j.get("company_name") or "").strip()
        loc = (j.get("location") or "").strip() or "Remote"
        desc = strip_html(j.get("description") or "")
        job_id = f"workingnomads:{job_url}"
        posted_date = normalize_posted_date(j.get("pub_date"))

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
            "posted_date": posted_date,
        })

    logger.info(f"workingnomads: {len(jobs)} jobs (after filters)")
    return jobs

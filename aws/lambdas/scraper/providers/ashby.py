"""Ashby ATS provider — public posting-api.ashbyhq.com endpoint.
No auth required. Ported from santifer/career-ops providers/ashby.mjs.
Note: Ashby has ~10s server-side latency floor; uses a longer timeout.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match

logger = logging.getLogger(__name__)

_TIMEOUT = 45
_RETRIES = 2


def _api_url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"


async def fetch_jobs(
    slug: str,
    company_name: str = "",
    keywords: str = "",
    location_filter: str = "",
) -> List[Dict]:
    url = _api_url(slug)
    last_err: Exception | None = None

    for attempt in range(_RETRIES + 1):
        if attempt > 0:
            backoff = 1.0 * (2 ** (attempt - 1)) + random.random() * 0.5
            await asyncio.sleep(backoff)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "LinkedInJobScout/1.0"})
                resp.raise_for_status()
                data = resp.json()
            break
        except Exception as e:
            last_err = e
            logger.warning(f"ashby/{slug}: attempt {attempt + 1} failed: {e}")
    else:
        raise last_err  # type: ignore[misc]

    company = company_name or slug
    raw_jobs = data.get("jobs") or data.get("jobPostings") or []
    if not isinstance(raw_jobs, list):
        logger.warning(f"ashby/{slug}: unexpected jobs field")
        return []

    jobs: List[Dict] = []
    for j in raw_jobs:
        if not j.get("isListed", True):  # respect unlisted flag when present
            continue
        title = (j.get("title") or "").strip()
        job_url = (j.get("jobUrl") or j.get("applicationLink") or "").strip()
        loc = (j.get("locationName") or "").strip()
        desc = (j.get("descriptionHtml") or j.get("description") or "")
        if "<" in desc:
            from ._utils import strip_html
            desc = strip_html(desc)
        native_id = j.get("id") or ""
        job_id = f"ashby:{slug}:{native_id}"

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

    logger.info(f"ashby/{slug}: {len(jobs)} jobs (after filters)")
    return jobs

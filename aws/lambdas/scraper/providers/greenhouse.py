"""Greenhouse ATS provider — public boards-api.greenhouse.io endpoint.
No auth required. Ported from santifer/career-ops providers/greenhouse.mjs.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = {
    "boards-api.greenhouse.io",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "job-boards.eu.greenhouse.io",
}


def _api_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


async def fetch_jobs(
    slug: str,
    company_name: str = "",
    keywords: str = "",
    location_filter: str = "",
) -> List[Dict]:
    url = _api_url(slug)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "LinkedInJobScout/1.0"})
        resp.raise_for_status()
        data = resp.json()

    company = company_name or slug
    jobs: List[Dict] = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        job_url = (j.get("absolute_url") or "").strip()
        loc = (j.get("location") or {}).get("name") or ""
        content_html = j.get("content") or ""
        desc = strip_html(content_html)
        job_id = f"greenhouse:{slug}:{j['id']}"

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

    logger.info(f"greenhouse/{slug}: {len(jobs)} jobs (after filters)")
    return jobs

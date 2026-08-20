"""Lever ATS provider — public api.lever.co/v0/postings endpoint.
No auth required. Ported from santifer/career-ops providers/lever.mjs.
Ships full descriptionPlain for free (no extra per-job request).
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match

logger = logging.getLogger(__name__)


def _api_url(slug: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}?mode=json"


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

    if not isinstance(data, list):
        logger.warning(f"lever/{slug}: unexpected response type {type(data)}")
        return []

    company = company_name or slug
    jobs: List[Dict] = []
    for j in data:
        title = (j.get("text") or "").strip()
        job_url = (j.get("hostedUrl") or "").strip()
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        desc = (j.get("descriptionPlain") or "").strip()
        native_id = j.get("id") or ""
        job_id = f"lever:{slug}:{native_id}"

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

    logger.info(f"lever/{slug}: {len(jobs)} jobs (after filters)")
    return jobs

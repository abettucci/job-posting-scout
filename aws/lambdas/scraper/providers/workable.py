"""Workable provider — public widget API endpoint.
apply.workable.com/api/v1/widget/accounts/{slug}?details=true
Ships full description + published_on for free. No auth required.
Ported from santifer/career-ops providers/workable.mjs.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_SLUG_SAFE_RE = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _api_url(slug: str) -> str:
    if not _SLUG_SAFE_RE.match(slug):
        raise ValueError(f"workable: unsafe slug: {slug!r}")
    return f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


async def fetch_jobs(
    slug: str,
    company_name: str = "",
    keywords: str = "",
    location_filter: str = "",
) -> List[Dict]:
    url = _api_url(slug)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://apply.workable.com",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    company = company_name or data.get("name") or slug
    jobs: List[Dict] = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        job_url = (j.get("url") or j.get("shortlink") or "").strip()
        city = j.get("city") or ""
        country = j.get("country") or ""
        remote = j.get("telecommuting", False)
        loc = "Remote" if remote else ", ".join(p for p in [city, country] if p)
        desc_raw = j.get("description") or ""
        desc = strip_html(desc_raw) if "<" in desc_raw else desc_raw
        native_id = j.get("shortcode") or ""
        job_id = f"workable:{slug}:{native_id}"

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

    logger.info(f"workable/{slug}: {len(jobs)} jobs (after filters)")
    return jobs

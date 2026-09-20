"""FreeHire aggregator provider — public, zero-auth JSON API.

FreeHire exposes structured technical jobs from several ATSs.  It is used as an
additional feed, not as a replacement for a user's direct company searches.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://freehire.me/api/v1/jobs/search"
_PAGE_SIZE = 100
_MAX_PAGES = 3


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Return a bounded, normalized result set from FreeHire's public search API.

    The upstream full-text query is deliberately broad (comma-separated app
    keywords do not mean an exact phrase); the established local matcher keeps
    its semantics consistent with every other aggregator.
    """
    jobs: List[Dict] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for page in range(_MAX_PAGES):
            params = {
                "q": " ".join(k.strip() for k in keywords.split(",") if k.strip()),
                "limit": _PAGE_SIZE,
                "offset": page * _PAGE_SIZE,
                "work_mode": "remote",
            }
            response = await client.get(_API_URL, params=params, headers={"User-Agent": "JobPostingScout/1.0"})
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(items, list) or not items:
                break

            for item in items:
                slug = str(item.get("public_slug") or "").strip()
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if not slug or slug in seen or not title or not url:
                    continue
                if item.get("work_mode") != "remote":
                    continue
                seen.add(slug)
                description = strip_html(str(item.get("description") or ""))
                skills = ", ".join(str(s) for s in item.get("skills", []) if s)
                location = str(item.get("location") or "").strip()
                if not location:
                    location = "Remote" if item.get("work_mode") == "remote" else ""
                if not keyword_match(f"{title} {description} {skills}", keywords):
                    continue
                if not location_match(location, location_filter):
                    continue
                jobs.append({
                    "job_id": f"freehire:{slug}",
                    "title": title,
                    "company": str(item.get("company") or "").strip() or "Unknown company",
                    "location": location,
                    "url": url,
                    "description": description[:6000],
                    "posted_date": normalize_posted_date(item.get("posted_at")),
                })

            meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
            if len(items) < _PAGE_SIZE or page * _PAGE_SIZE + len(items) >= int(meta.get("total", 0) or 0):
                break

    logger.info("freehire: %s jobs (after filters)", len(jobs))
    return jobs

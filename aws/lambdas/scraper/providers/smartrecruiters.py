"""SmartRecruiters provider — public postings API.
api.smartrecruiters.com/v1/companies/{slug}/postings
Paginated (100/page). No auth required.
Ported from santifer/career-ops providers/smartrecruiters.mjs.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from ._utils import keyword_match, location_match

logger = logging.getLogger(__name__)

_PAGE_SIZE = 100
_MAX_PAGES = 20  # safety cap — 2000 postings


def _page_url(slug: str, offset: int = 0) -> str:
    return (
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        f"?limit={_PAGE_SIZE}&offset={offset}&status=PUBLIC"
    )


async def fetch_jobs(
    slug: str,
    company_name: str = "",
    keywords: str = "",
    location_filter: str = "",
) -> List[Dict]:
    company = company_name or slug
    jobs: List[Dict] = []
    offset = 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for page in range(_MAX_PAGES):
            resp = await client.get(
                _page_url(slug, offset),
                headers={"User-Agent": "LinkedInJobScout/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("content", [])
            if not batch:
                break

            for j in batch:
                title = (j.get("name") or "").strip()
                job_url = (
                    f"https://careers.smartrecruiters.com/{slug}/{j.get('id', '')}"
                )
                loc_obj = j.get("location") or {}
                city = loc_obj.get("city") or ""
                country = loc_obj.get("country") or ""
                remote = loc_obj.get("remote", False)
                loc = "Remote" if remote else ", ".join(p for p in [city, country] if p)
                native_id = j.get("id") or ""
                job_id = f"smartrecruiters:{slug}:{native_id}"

                if not title:
                    continue
                # SmartRecruiters list endpoint doesn't ship description
                # (separate per-job request needed); pass title-only to filter
                if not keyword_match(title, keywords):
                    continue
                if not location_match(loc, location_filter):
                    continue

                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": loc,
                    "url": job_url,
                    "description": "",  # populated later by scorer from title/company
                })

            total = data.get("totalFound", 0)
            offset += _PAGE_SIZE
            if offset >= total:
                break

    logger.info(f"smartrecruiters/{slug}: {len(jobs)} jobs (after filters)")
    return jobs

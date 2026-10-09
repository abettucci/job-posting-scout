"""Dixcover Hub provider using its public WordPress Remote category feed."""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_POSTS_URL = "https://jobs.smartyacad.com/wp-json/wp/v2/posts"
_REMOTE_CATEGORY_ID = 13
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}


def _rendered(value: Any) -> str:
    return str(value.get("rendered") or "") if isinstance(value, dict) else str(value or "")


def _location(description: str) -> str:
    lower = description.casefold()
    if re.search(r"\b(argentina|buenos aires)\b", lower):
        return "Argentina"
    if re.search(r"\b(worldwide|global|work from anywhere)\b", lower):
        return "Remote — Worldwide"
    if re.search(r"\b(nigeria|lagos|abuja)\b", lower):
        return "Remote — Nigeria"
    return "Remote — eligibility not specified"


def _company(title: str) -> str:
    parts = re.split(r"\s+(?:at|@)\s+", title, flags=re.IGNORECASE, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 and parts[1].strip() else "Unknown company"


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    params = {"categories": _REMOTE_CATEGORY_ID, "per_page": 30, "orderby": "date", "order": "desc"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(_POSTS_URL, params=params, headers=_HEADERS)
        response.raise_for_status()
        items = response.json()
    if not isinstance(items, list):
        logger.warning("dixcover: unexpected response type")
        return []

    jobs: List[Dict] = []
    for item in items:
        post_id = str(item.get("id") or "").strip()
        title = strip_html(html.unescape(_rendered(item.get("title"))))
        description = strip_html(_rendered(item.get("content")))
        url = str(item.get("link") or "").strip()
        location = _location(description)
        if not post_id or not title or not url:
            continue
        if not keyword_match(f"{title} {description}", keywords) or not location_match(location, location_filter):
            continue
        jobs.append({
            "job_id": f"dixcover:{post_id}",
            "title": title,
            "company": _company(title),
            "location": location,
            "url": url,
            "description": description[:6000],
            "posted_date": normalize_posted_date(item.get("date_gmt") or item.get("date")),
        })

    logger.info("dixcover: %s jobs (after filters)", len(jobs))
    return jobs

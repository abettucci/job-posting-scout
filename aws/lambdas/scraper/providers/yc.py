"""Y Combinator Startup Jobs provider.

Uses the public, server-rendered YC job listing pages only — no account or
application flow. The provider combines the Buenos Aires listing with
worldwide-remote jobs from the general listing, so it is useful from Argentina
without requiring a country filter in each search.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from typing import Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ._utils import keyword_match, location_match

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ycombinator.com"
_LISTING_URLS = (
    f"{_BASE_URL}/jobs",
    f"{_BASE_URL}/jobs/location/buenos-aires",
)
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}


def _is_worldwide_remote(location: str) -> bool:
    """Keep genuinely location-agnostic remote roles from YC's global page.

    YC also labels country-bound roles as ``Remote (US)`` or ``Remote (CA)``;
    those are intentionally excluded. Buenos Aires jobs come from their own
    location page and are included regardless of whether they are hybrid.
    """
    normalized = " ".join(location.lower().split())
    if "remote" not in normalized:
        return False
    return (
        normalized == "remote"
        or "worldwide" in normalized
        or "global" in normalized
        or "remote (worldwide)" in normalized
    )


def _extract_postings(page_html: str) -> List[Dict]:
    """Read the React page payload rather than depending on presentation CSS."""
    soup = BeautifulSoup(page_html, "html.parser")
    root = soup.find(attrs={"data-page": True})
    if not root:
        logger.warning("yc: page did not contain a data-page payload")
        return []
    try:
        data = json.loads(html.unescape(str(root["data-page"])))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning(f"yc: could not parse listing payload: {exc}")
        return []
    postings = data.get("props", {}).get("jobPostings", [])
    return postings if isinstance(postings, list) else []


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Return public YC jobs in Buenos Aires or available worldwide remotely.

    YC exposes a concise company one-liner in its listing payload, but not the
    full role description. It is retained as the description so the existing
    scorer has contextual text while keeping requests bounded to the two public
    listing pages.
    """
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        responses = await asyncio.gather(
            *(client.get(url, headers=_HEADERS) for url in _LISTING_URLS),
            return_exceptions=True,
        )

    all_postings: List[tuple[Dict, bool]] = []
    for url, response in zip(_LISTING_URLS, responses):
        if isinstance(response, Exception):
            logger.warning(f"yc: listing fetch failed for {url}: {response}")
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(f"yc: listing fetch failed for {url}: {exc}")
            continue
        is_buenos_aires_page = url.endswith("/buenos-aires")
        all_postings.extend((posting, is_buenos_aires_page) for posting in _extract_postings(response.text))

    jobs: List[Dict] = []
    seen_ids: set[str] = set()
    for posting, is_buenos_aires_page in all_postings:
        native_id = posting.get("id")
        title = str(posting.get("title") or "").strip()
        company = str(posting.get("companyName") or "").strip()
        location = str(posting.get("location") or "").strip()
        url_path = str(posting.get("url") or "").strip()
        if not native_id or not title or not location or not url_path:
            continue
        if not is_buenos_aires_page and not _is_worldwide_remote(location):
            continue
        if not location_match(location, location_filter):
            continue

        job_id = f"yc:{native_id}"
        if job_id in seen_ids:
            continue
        description = " ".join(filter(None, [
            str(posting.get("companyOneLiner") or "").strip(),
            str(posting.get("type") or "").strip(),
            str(posting.get("prettyRole") or "").strip(),
            str(posting.get("roleSpecificType") or "").strip(),
            str(posting.get("minExperience") or "").strip(),
        ]))
        if not keyword_match(f"{title} {company} {description}", keywords):
            continue

        seen_ids.add(job_id)
        jobs.append({
            "job_id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "url": urljoin(_BASE_URL, url_path),
            "description": description[:6000],
            "posted_date": None,
        })

    logger.info(f"yc: {len(jobs)} Buenos Aires or worldwide-remote jobs (after filters)")
    return jobs

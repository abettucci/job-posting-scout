"""OnlineJobs.ph aggregator provider — onlinejobs.ph, a Philippines-focused
remote/virtual-assistant job board. No public API; HTML scraping, confirmed
server-rendered (no JS execution needed) with no anti-bot wall observed.

Two real limitations of the source site itself (not a scraping shortcut):
  - Employer identity is anonymized on both the search results and the job
    detail page, so `company` is always empty here.
  - No location field is shown anywhere on a listing; every posting on this
    site is inherently "remote from the Philippines (or open to it)", so
    `location` is hardcoded to "Remote" rather than left blank.

Unlike CompuJobs, the search endpoint is cheap enough per request (one page,
no per-job detail fetch — the listing already embeds the full description)
that we fan out one request per comma-separated keyword term to honor the
same OR-across-terms semantics the rest of the app promises, capped at
_MAX_TERMS to bound request volume for a search with many synonyms.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.onlinejobs.ph/jobseekers/jobsearch"
_BASE_URL = "https://www.onlinejobs.ph"
_HEADERS = {"User-Agent": "LinkedInJobScout/1.0"}
_MAX_TERMS = 3


def _parse_listing_page(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict] = []

    for anchor in soup.select("a[href*='/jobseekers/job/']"):
        box = anchor.find("div", class_="jobpost-cat-box")
        if not box:
            continue

        h4 = box.find("h4")
        if not h4:
            continue
        badge = h4.find("span")
        if badge:
            badge.extract()
        title = h4.get_text(strip=True)

        desc_el = box.find("div", class_="desc")
        if desc_el:
            for see_more in desc_el.find_all("a"):
                see_more.extract()  # drop the trailing "See More" link, keep only the excerpt text
        description = strip_html(str(desc_el)) if desc_el else ""

        # data-temp has no explicit timezone; normalize_posted_date's "naive
        # strings are assumed UTC" convention is applied here same as every
        # other provider, but this site is Philippines-based (UTC+8) so the
        # timestamp is likely actually PHT — posted_date may run up to ~8h
        # ahead of the true UTC instant. Same best-effort caveat as elsewhere.
        date_el = box.find("p", attrs={"data-temp": True})
        posted_raw = date_el.get("data-temp") if date_el else None
        posted_date = normalize_posted_date(posted_raw.replace(" ", "T", 1)) if posted_raw else None

        href = anchor.get("href") or ""
        match = re.search(r"(\d+)$", href.rstrip("/"))
        if not title or not href or not match:
            continue

        jobs.append({
            "job_id": f"onlinejobs:{match.group(1)}",
            "title": title,
            "company": "",
            "location": "Remote",
            "url": _BASE_URL + href if href.startswith("/") else href,
            "description": description[:6000],
            "posted_date": posted_date,
        })

    return jobs


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    terms = [t.strip() for t in keywords.split(",") if t.strip()][:_MAX_TERMS] or [""]

    seen: Dict[str, Dict] = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for term in terms:
            try:
                resp = await client.get(_SEARCH_URL, params={"jobkeyword": term}, headers=_HEADERS)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"onlinejobs: search failed for term {term!r}: {e}")
                continue
            for job in _parse_listing_page(resp.text):
                seen[job["job_id"]] = job

    jobs = [
        j for j in seen.values()
        if keyword_match(f"{j['title']} {j['description']}", keywords) and location_match(j["location"], location_filter)
    ]

    logger.info(f"onlinejobs: {len(jobs)} jobs (after filters)")
    return jobs

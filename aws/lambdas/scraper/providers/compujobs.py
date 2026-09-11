"""CompuJobs aggregator provider — compujobs.co.za, a South African WP Job
Manager job board. No public API; HTML scraping of the WordPress "WorkScout"
theme markup, confirmed server-rendered (no JS execution needed) with no
anti-bot wall as of the research done for this integration.

The search form only supports a single query string (no OR-across-terms
syntax), so only the first comma-separated term of `keywords` is sent
server-side; the full multi-term OR match is still enforced client-side via
`keyword_match`, same as every other aggregator provider.

The listing page doesn't include the job description or posted date, only
title/company/location — those two fields require one extra GET per job
(the job's own detail page), which carries schema.org JSON-LD with both.
Volume here is low (a dozen-ish results per search), so the extra requests
are bounded and cheap; _MAX_DETAIL_FETCHES caps it regardless in case a
broader/empty query ever returns far more.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.compujobs.co.za/search-jobs/"
_HEADERS = {"User-Agent": "LinkedInJobScout/1.0"}
_MAX_DETAIL_FETCHES = 30


async def _fetch_detail(client: httpx.AsyncClient, url: str) -> tuple[str, Optional[str]]:
    """Return (description, posted_date) scraped from the job's own detail
    page's schema.org JobPosting JSON-LD block. Best-effort: any failure
    just means those two fields stay empty/None for this job."""
    try:
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"compujobs: detail fetch failed for {url}: {e}")
        return "", None

    soup = BeautifulSoup(resp.text, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("@type") != "JobPosting":
            continue
        desc = strip_html(data.get("description") or "")
        posted = normalize_posted_date(data.get("datePosted"))
        return desc, posted
    return "", None


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    primary_term = keywords.split(",")[0].strip() if keywords else ""

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_SEARCH_URL, params={"search_keywords": primary_term}, headers=_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        listings = soup.select("li[data-title]")
        jobs: List[Dict] = []

        for li in listings[:_MAX_DETAIL_FETCHES]:
            title = (li.get("data-title") or "").strip()
            company = (li.get("data-company") or "").strip()
            loc = (li.get("data-address") or "").strip()
            job_id_raw = li.get("data-job_id") or ""
            link_el = li.find("a", href=True)
            job_url = (link_el["href"] if link_el else "").strip()

            if not title or not job_url:
                continue
            if not location_match(loc, location_filter):
                continue

            job_id = f"compujobs:{job_id_raw or re.sub(r'[^a-zA-Z0-9]+', '-', job_url)}"
            desc, posted_date = await _fetch_detail(client, job_url)

            if not keyword_match(f"{title} {desc}", keywords):
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

    logger.info(f"compujobs: {len(jobs)} jobs (after filters)")
    return jobs

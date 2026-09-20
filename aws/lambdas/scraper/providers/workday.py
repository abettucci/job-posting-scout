"""Workday public CXS careers provider.

Every Workday customer owns a tenant and a public career-site path.  This
adapter only accepts those public ``*.myworkdayjobs.com`` URLs; it never uses
the authenticated Workday HR API.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20
_MAX_PAGES = 100


def parse_board_url(board_url: str) -> Tuple[str, str, str, str]:
    """Return origin, tenant, site and a normalized board URL or raise ValueError."""
    parsed = urlparse((board_url or "").strip())
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or not host.endswith(".myworkdayjobs.com"):
        raise ValueError("Workday URL must use an https *.myworkdayjobs.com public careers host")
    tenant = host.split(".", 1)[0]
    # Normal public URLs are /en-US/External.  The locale is optional, and the
    # career-site is always the final supplied path segment.
    if not tenant or not parts:
        raise ValueError("Workday URL must include its public career-site path")
    site = parts[-1]
    if site.lower() in {"job", "jobs", "search"}:
        raise ValueError("Paste the Workday career-site URL, not an individual job URL")
    origin = f"https://{host}"
    normalized = f"{origin}/{'/'.join(parts)}"
    return origin, tenant, site, normalized


def _listing_url(origin: str, tenant: str, site: str) -> str:
    return f"{origin}/wday/cxs/{tenant}/{site}/jobs"


async def fetch_jobs(slug: str, company_name: str = "", keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Fetch a public Workday CXS board, pagination and job details included."""
    origin, tenant, site, board_url = parse_board_url(slug)
    listing_url = _listing_url(origin, tenant, site)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobPostingScout/1.0)",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": board_url + "/",
    }
    jobs: List[Dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for page in range(_MAX_PAGES):
            response = await client.post(
                listing_url,
                headers=headers,
                json={"appliedFacets": {}, "limit": _PAGE_SIZE, "offset": page * _PAGE_SIZE, "searchText": ""},
            )
            response.raise_for_status()
            payload = response.json()
            postings = payload.get("jobPostings", []) if isinstance(payload, dict) else []
            if not isinstance(postings, list) or not postings:
                break

            for posting in postings:
                title = str(posting.get("title") or "").strip()
                external_path = str(posting.get("externalPath") or "").strip()
                job_key = str(posting.get("jobReqId") or posting.get("jobPostingId") or external_path).strip()
                if not title or not external_path or not job_key or job_key in seen:
                    continue
                seen.add(job_key)
                listing_location = str(posting.get("locationsText") or "").strip()
                bullets = " ".join(str(value) for value in posting.get("bulletFields", []) if value)
                if not location_match(listing_location, location_filter):
                    continue

                # CXS detail carries the complete description; the public
                # careers-page URL itself renders HTML instead of this JSON.
                detail_url = f"{origin}/wday/cxs/{tenant}/{site}{external_path}"
                public_url = urljoin(board_url + "/", external_path.lstrip("/"))
                description = ""
                location = listing_location
                try:
                    detail_response = await client.get(detail_url, headers=headers)
                    detail_response.raise_for_status()
                    detail = detail_response.json().get("jobPostingInfo", {})
                    description = strip_html(str(detail.get("jobDescription") or ""))
                    location = str(detail.get("location") or location or "").strip()
                    posted_at = detail.get("startDate") or posting.get("postedOn")
                except Exception as exc:
                    logger.info("workday/%s: detail unavailable for %s: %s", tenant, job_key, type(exc).__name__)
                    posted_at = posting.get("postedOn")

                if not keyword_match(f"{title} {bullets} {description}", keywords):
                    continue
                if not location_match(location, location_filter):
                    continue
                jobs.append({
                    "job_id": f"workday:{tenant}:{site}:{job_key}",
                    "title": title,
                    "company": company_name or tenant,
                    "location": location,
                    "url": public_url,
                    "description": description[:6000],
                    "posted_date": normalize_posted_date(posted_at),
                })

            total = int(payload.get("total", 0) or 0)
            if len(postings) < _PAGE_SIZE or page * _PAGE_SIZE + len(postings) >= total:
                break

    logger.info("workday/%s/%s: %s jobs (after filters)", tenant, site, len(jobs))
    return jobs

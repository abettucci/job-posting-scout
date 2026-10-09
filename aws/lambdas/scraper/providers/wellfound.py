"""Wellfound aggregator provider using only public job and detail pages.

Wellfound renders a public Next.js job index and includes a JSON-LD JobPosting
on each public detail page.  This provider deliberately uses ordinary GET
requests only: no account, private API, proxy, or challenge-bypass mechanism.
"""
from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Dict, Iterable, List

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_BASE_URL = "https://wellfound.com"
_INDEX_URL = f"{_BASE_URL}/jobs"
_MAX_DETAIL_FETCHES = 25
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _listing_entities(document: str) -> Dict[str, Dict[str, Any]]:
    match = _NEXT_DATA_RE.search(document)
    if not match:
        return {}
    try:
        payload = json.loads(html.unescape(match.group(1)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    state = payload.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})
    return state if isinstance(state, dict) else {}


def _job_posting(document: str) -> Dict[str, Any]:
    for match in _JSON_LD_RE.finditer(document):
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for node in _walk_json(payload):
            kind = node.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                return node
    return {}


def _names(value: Any) -> List[str]:
    if isinstance(value, list):
        names: List[str] = []
        for child in value:
            names.extend(_names(child))
        return names
    if isinstance(value, dict):
        address = value.get("address")
        return _names(value.get("name")) or _names(address)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _listing_location(listing: Dict[str, Any]) -> str:
    places = _names(listing.get("acceptedRemoteLocationNames"))
    if listing.get("remote"):
        return f"Remote — {', '.join(places)}" if places else "Remote"
    places = _names(listing.get("locationNames"))
    return ", ".join(places)


def _listing_timestamp(listing: Dict[str, Any]) -> int:
    try:
        return int(listing.get("liveStartAt") or 0)
    except (TypeError, ValueError):
        return 0


def _detail_location(posting: Dict[str, Any], fallback: str) -> str:
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        places = _names(posting.get("applicantLocationRequirements"))
        return f"Remote — {', '.join(places)}" if places else "Remote"
    places = _names(posting.get("jobLocation"))
    return ", ".join(places) or fallback


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Return bounded normalized Wellfound jobs from public HTML pages."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(_INDEX_URL, headers=_HEADERS)
        response.raise_for_status()
        entities = _listing_entities(response.text)

        listings = [
            value for key, value in entities.items()
            if key.startswith("JobListing:") and isinstance(value, dict)
        ]
        listings.sort(key=_listing_timestamp, reverse=True)

        jobs: List[Dict] = []
        seen: set[str] = set()
        detail_fetches = 0
        for listing in listings:
            job_id = str(listing.get("id") or "").strip()
            title = str(listing.get("title") or "").strip()
            slug = str(listing.get("slug") or "").strip()
            if not job_id or not title or job_id in seen:
                continue
            seen.add(job_id)

            startup_ref = listing.get("startup", {}).get("__ref", "") if isinstance(listing.get("startup"), dict) else ""
            startup = entities.get(startup_ref, {}) if startup_ref else {}
            company = str(startup.get("name") or "").strip() or "Unknown company"
            preview = " ".join(
                str(value) for value in (
                    startup.get("highConcept"), listing.get("primaryRole"), listing.get("compensation")
                ) if value
            )
            location = _listing_location(listing)
            if not keyword_match(f"{title} {company} {preview}", keywords):
                continue
            if not location_match(location, location_filter):
                continue
            if detail_fetches >= _MAX_DETAIL_FETCHES:
                break
            detail_fetches += 1

            detail_url = f"{_BASE_URL}/jobs/{job_id}-{slug}" if slug else f"{_BASE_URL}/jobs/{job_id}"
            try:
                detail_response = await client.get(detail_url, headers=_HEADERS)
                detail_response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("wellfound: skipping unavailable detail %s: %s", job_id, exc)
                continue
            posting = _job_posting(detail_response.text)
            description = strip_html(str(posting.get("description") or ""))
            if not description:
                continue
            actual_title = str(posting.get("title") or title).strip()
            actual_company = str((posting.get("hiringOrganization") or {}).get("name") or company).strip() or company
            actual_location = _detail_location(posting, location)
            if not keyword_match(f"{actual_title} {actual_company} {description}", keywords):
                continue
            if not location_match(actual_location, location_filter):
                continue
            jobs.append({
                "job_id": f"wellfound:{job_id}",
                "title": actual_title,
                "company": actual_company,
                "location": actual_location,
                "url": detail_url,
                "description": description[:6000],
                "posted_date": normalize_posted_date(posting.get("datePosted") or listing.get("liveStartAt")),
            })

    logger.info("wellfound: %s jobs (after filters)", len(jobs))
    return jobs

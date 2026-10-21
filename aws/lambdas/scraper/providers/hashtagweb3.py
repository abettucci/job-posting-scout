"""Hashtag Web3 public-job-index adapter.

The board server-renders its current index in Next.js Flight data and exposes
a public JobPosting JSON-LD document at each listing path.  We use only those
ordinary public pages, with bounded detail requests and no account or private
endpoint.
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

_BASE_URL = "https://hashtagweb3.com"
_INDEX_URL = f"{_BASE_URL}/jobs"
_MAX_DETAIL_FETCHES = 30
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}
_NEXT_FLIGHT_RE = re.compile(
    r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)', re.DOTALL
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _index_jobs(document: str) -> List[Dict[str, Any]]:
    """Extract ``initialJobs`` from the public Next Flight payload."""
    decoder = json.JSONDecoder()
    for match in _NEXT_FLIGHT_RE.finditer(document):
        try:
            frame = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        marker = '"initialJobs":'
        offset = frame.find(marker)
        if offset < 0:
            continue
        array_start = frame.find("[", offset + len(marker))
        if array_start < 0:
            continue
        try:
            value, _ = decoder.raw_decode(frame[array_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return [job for job in value if isinstance(job, dict)]
    return []


def _posting(document: str) -> Dict[str, Any]:
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
        return [name for child in value for name in _names(child)]
    if isinstance(value, dict):
        return _names(value.get("name")) or _names(value.get("address"))
    return [value.strip()] if isinstance(value, str) and value.strip() else []


def _location(posting: Dict[str, Any], fallback: str = "") -> str:
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        regions = _names(posting.get("applicantLocationRequirements"))
        return f"Remote — {', '.join(regions)}" if regions else "Remote"
    return ", ".join(_names(posting.get("jobLocation"))) or fallback


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Return public Hashtag Web3 listings with full public descriptions."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        index_response = await client.get(_INDEX_URL, headers=_HEADERS)
        index_response.raise_for_status()
        listings = _index_jobs(index_response.text)
        if not listings:
            raise ValueError("public index did not contain initialJobs")

        jobs: List[Dict] = []
        for listing in listings:
            slug = str(listing.get("slug") or "").strip()
            listing_id = str(listing.get("id") or slug).strip()
            title = str(listing.get("title") or "").strip()
            company = str(listing.get("company") or "").strip() or "Unknown company"
            preview_location = str(listing.get("location") or "").strip()
            if not slug or not listing_id or not title:
                continue
            # The index deliberately contains no description excerpt. The
            # detail page is therefore authoritative for both keywords and
            # location; rejecting here would drop e.g. a Python role whose
            # title is simply "Backend Engineer".
            try:
                detail_response = await client.get(f"{_BASE_URL}/{slug}", headers=_HEADERS)
                detail_response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("hashtagweb3: skipping unavailable detail %s: %s", slug, exc)
                continue
            posting = _posting(detail_response.text)
            description = strip_html(str(posting.get("description") or ""))
            actual_location = _location(posting, preview_location)
            if not description:
                continue
            if not keyword_match(f"{title} {company} {description}", keywords):
                continue
            if not location_match(actual_location, location_filter):
                continue
            application_url = str(listing.get("link") or "").strip() or f"{_BASE_URL}/{slug}"
            jobs.append({
                "job_id": f"hashtagweb3:{listing_id}",
                "title": str(posting.get("title") or title).strip() or title,
                "company": str((posting.get("hiringOrganization") or {}).get("name") or company).strip() or company,
                "location": actual_location,
                "url": application_url,
                "description": description[:6000],
                "posted_date": normalize_posted_date(posting.get("datePosted") or listing.get("date")),
                "source_url": f"{_BASE_URL}/{slug}",
                "valid_through": normalize_posted_date(posting.get("validThrough")),
            })
            if len(jobs) >= _MAX_DETAIL_FETCHES:
                break

    logger.info("hashtagweb3: %s jobs (after filters)", len(jobs))
    return jobs

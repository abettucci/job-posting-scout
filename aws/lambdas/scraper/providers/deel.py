"""Deel-hosted public careers provider.

Deel hosts one public board per organization at ``jobs.deel.com/<org>``.  This
adapter deliberately uses only the public sitemap, board, and job overview
pages.  It never calls Deel's disallowed ``/api/`` routes or an application
form endpoint.
"""
from __future__ import annotations

import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_HOST = "jobs.deel.com"
_MAX_JOBS = 250
_DETAIL_PATH = re.compile(r"^/([a-z0-9][a-z0-9-]*)/job-details/([^/]+)/overview/?$", re.I)
_JSON_LD_SCRIPT = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S
)


def parse_board_url(board_url: str) -> Tuple[str, str]:
    """Return a canonical public board URL and organization slug.

    ``/job-boards/<org>`` is accepted because Deel redirects that historical
    form to ``/<org>``.  Individual job and application URLs are rejected.
    """
    parsed = urlparse((board_url or "").strip())
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or host != _HOST:
        raise ValueError("Deel URL must use the public https://jobs.deel.com host")
    if parts[:1] == ["job-boards"]:
        parts = parts[1:]
    if len(parts) != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", parts[0], re.I):
        raise ValueError("Paste a public Deel company board URL, e.g. https://jobs.deel.com/acme")
    organization = parts[0].lower()
    return f"https://{_HOST}/{organization}", organization


def _detail_urls_from_sitemap(xml: str, organization: str) -> List[str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    urls: List[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
            continue
        candidate = element.text.strip()
        match = _DETAIL_PATH.match(urlparse(candidate).path)
        if match and match.group(1).lower() == organization:
            urls.append(candidate.rstrip("/"))
    return urls


def _detail_urls_from_board_html(document: str, organization: str) -> List[str]:
    """Read public ItemList JSON-LD, with href extraction as a small fallback."""
    urls: List[str] = []
    for item in _json_ld_objects(document):
        for value in _walk_json(item):
            if isinstance(value, str) and _is_detail_url(value, organization):
                urls.append(value.rstrip("/"))
    pattern = re.compile(r'''href=["']([^"']+/job-details/[^"']+/overview/?)["']''', re.I)
    for match in pattern.finditer(document):
        candidate = html.unescape(match.group(1))
        if candidate.startswith("/"):
            candidate = f"https://{_HOST}{candidate}"
        if _is_detail_url(candidate, organization):
            urls.append(candidate.rstrip("/"))
    return urls


def _is_detail_url(value: str, organization: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != _HOST:
        return False
    match = _DETAIL_PATH.match(parsed.path)
    return bool(match and match.group(1).lower() == organization)


def _json_ld_objects(document: str) -> Iterable[Any]:
    for raw in _JSON_LD_SCRIPT.findall(document):
        try:
            yield json.loads(html.unescape(raw).strip())
        except (json.JSONDecodeError, TypeError):
            continue


def _walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _job_posting(document: str) -> Dict[str, Any]:
    for object_ in _json_ld_objects(document):
        for candidate in _walk_json(object_):
            if not isinstance(candidate, dict):
                continue
            kind = candidate.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item).lower() == "jobposting" for item in kinds):
                return candidate
    return {}


def _location(posting: Dict[str, Any]) -> str:
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return "Remote"
    values = posting.get("jobLocation")
    if not isinstance(values, list):
        values = [values]
    locations: List[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        address = value.get("address", value)
        if isinstance(address, str):
            locations.append(address)
        elif isinstance(address, dict):
            parts = [address.get(key) for key in ("addressLocality", "addressRegion", "addressCountry")]
            rendered = ", ".join(str(part).strip() for part in parts if part)
            if rendered:
                locations.append(rendered)
    return " / ".join(dict.fromkeys(locations))


async def fetch_jobs(slug: str, company_name: str = "", keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Fetch a single Deel-hosted board through allowed public pages only."""
    board_url, organization = parse_board_url(slug)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobPostingScout/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        detail_urls: List[str] = []
        try:
            sitemap = await client.get(f"{board_url}/sitemap.xml", headers=headers)
            sitemap.raise_for_status()
            detail_urls = _detail_urls_from_sitemap(sitemap.text, organization)
        except Exception as exc:
            logger.info("deel/%s: sitemap unavailable: %s", organization, type(exc).__name__)

        # The public board embeds an ItemList JSON-LD.  It covers boards whose
        # sitemap is temporarily unavailable and gives us a safe no-API fallback.
        if not detail_urls:
            board = await client.get(board_url, headers=headers)
            board.raise_for_status()
            detail_urls = _detail_urls_from_board_html(board.text, organization)

        jobs: List[Dict] = []
        seen: set[str] = set()
        for detail_url in detail_urls[:_MAX_JOBS]:
            match = _DETAIL_PATH.match(urlparse(detail_url).path)
            if not match:
                continue
            job_key = match.group(2)
            if job_key in seen:
                continue
            seen.add(job_key)
            try:
                response = await client.get(detail_url, headers=headers)
                response.raise_for_status()
                posting = _job_posting(response.text)
            except Exception as exc:
                logger.info("deel/%s: detail unavailable for %s: %s", organization, job_key, type(exc).__name__)
                continue
            title = str(posting.get("title") or "").strip()
            description = strip_html(str(posting.get("description") or ""))
            location = _location(posting)
            if not title or not keyword_match(f"{title} {description}", keywords):
                continue
            if not location_match(location, location_filter):
                continue
            hiring_org = posting.get("hiringOrganization")
            posted_company = hiring_org.get("name") if isinstance(hiring_org, dict) else ""
            jobs.append({
                "job_id": f"deel:{organization}:{job_key}",
                "title": title,
                "company": str(posted_company or company_name or organization).strip(),
                "location": location,
                "url": detail_url,
                "description": description[:6000],
                "posted_date": normalize_posted_date(posting.get("datePosted")),
            })
    logger.info("deel/%s: %s jobs (after filters)", organization, len(jobs))
    return jobs

"""JustJoin.IT provider backed by its public candidate listings API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from ._utils import keyword_match, location_match, normalize_posted_date, strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://justjoin.it/api/candidate-api/offers"
_MAX_DETAIL_FETCHES = 25
_COUNTRY_NAMES = {"AR": "Argentina", "PL": "Poland", "US": "United States", "GB": "United Kingdom"}
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}


def _skill_names(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(
        str(item.get("name") if isinstance(item, dict) else item).strip()
        for item in value if item and str(item.get("name") if isinstance(item, dict) else item).strip()
    )


def _location(item: Dict[str, Any]) -> str:
    city = str(item.get("city") or "").strip()
    country_code = str(item.get("countryCode") or "").upper()
    country = _COUNTRY_NAMES.get(country_code, country_code)
    if str(item.get("workplaceType") or "").casefold() == "remote":
        place = ", ".join(part for part in (city, country) if part)
        return f"Remote — {place}" if place else "Remote"
    return ", ".join(part for part in (city, country) if part)


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(_API_URL, headers=_HEADERS)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            logger.warning("justjoin: unexpected response type")
            return []

        jobs: List[Dict] = []
        for item in items[:_MAX_DETAIL_FETCHES]:
            slug = str(item.get("slug") or "").strip()
            guid = str(item.get("guid") or slug).strip()
            title = str(item.get("title") or "").strip()
            company = str(item.get("companyName") or "").strip() or "Unknown company"
            location = _location(item)
            skills = _skill_names(item.get("requiredSkills"))
            if not slug or not guid or not title:
                continue
            if not keyword_match(f"{title} {company} {skills}", keywords) or not location_match(location, location_filter):
                continue
            try:
                detail_response = await client.get(f"{_API_URL}/{slug}", headers=_HEADERS)
                detail_response.raise_for_status()
                detail = detail_response.json()
            except httpx.HTTPError as exc:
                logger.info("justjoin: skipping unavailable detail %s: %s", slug, exc)
                continue
            if not isinstance(detail, dict):
                continue
            description = strip_html(str(detail.get("body") or ""))
            combined_skills = ", ".join(filter(None, (skills, _skill_names(detail.get("requiredSkills")), _skill_names(detail.get("niceToHaveSkills")))))
            actual_location = _location({**item, **detail})
            if not description or not keyword_match(f"{title} {company} {combined_skills} {description}", keywords):
                continue
            if not location_match(actual_location, location_filter):
                continue
            jobs.append({
                "job_id": f"justjoin:{guid}",
                "title": title,
                "company": company,
                "location": actual_location,
                "url": f"https://justjoin.it/job-offer/{slug}",
                "description": description[:6000],
                "posted_date": normalize_posted_date(detail.get("publishedAt") or item.get("publishedAt")),
            })

    logger.info("justjoin: %s jobs (after filters)", len(jobs))
    return jobs

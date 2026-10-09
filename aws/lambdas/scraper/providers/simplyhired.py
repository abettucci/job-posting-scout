"""SimplyHired provider using its public server-rendered search and detail pages.

This intentionally does not authenticate, call private endpoints, rotate
identities, or bypass a challenge page. A normal public response that becomes
unavailable is allowed to fail in isolation and is shown in scrape telemetry.
"""
from __future__ import annotations

import logging
from typing import Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ._utils import keyword_match, location_match, strip_html

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.simplyhired.com"
_SEARCH_URL = f"{_BASE_URL}/search"
_MAX_QUERIES = 2
_MAX_DETAIL_FETCHES = 25
_HEADERS = {"User-Agent": "JobPostingScout/1.0 (+https://github.com/abettucci/job-posting-scout)"}


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _search_cards(document: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(document, "html.parser")
    cards: List[Dict[str, str]] = []
    for card in soup.select("[data-testid='searchSerpJob']"):
        link = card.select_one("[data-testid='searchSerpJobTitle'] a[href]")
        title = _text(link)
        href = link.get("href", "") if link else ""
        job_key = str(card.get("data-jobkey") or "").strip()
        if not title or not href or not job_key:
            continue
        location = _text(card.select_one("[data-testid='searchSerpJobLocation']"))
        remote = _text(card.select_one("[data-testid*='remote' i]"))
        if remote and remote.casefold() in {"remote", "fully remote"}:
            location = "Remote" if not location else f"Remote — {location}"
        cards.append({
            "job_id": job_key,
            "title": title,
            "company": _text(card.select_one("[data-testid='companyName']")) or "Unknown company",
            "location": location,
            "url": urljoin(_BASE_URL, href),
        })
    return cards


def _detail_description(document: str) -> str:
    soup = BeautifulSoup(document, "html.parser")
    node = soup.select_one("[data-testid='viewJobBodyJobFullDescriptionContent']")
    return strip_html(str(node)) if node else ""


async def fetch_jobs(keywords: str = "", location_filter: str = "") -> List[Dict]:
    """Fetch a small, keyword-bounded set of public SimplyHired postings."""
    terms = [part.strip() for part in keywords.split(",") if part.strip()][:_MAX_QUERIES]
    if not terms:
        return []
    candidates: List[Dict[str, str]] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for term in terms:
            response = await client.get(_SEARCH_URL, params={"q": term, "l": "remote"}, headers=_HEADERS)
            response.raise_for_status()
            for card in _search_cards(response.text):
                if card["job_id"] in seen:
                    continue
                seen.add(card["job_id"])
                if keyword_match(f"{card['title']} {card['company']}", keywords) and location_match(card["location"], location_filter):
                    candidates.append(card)

        jobs: List[Dict] = []
        for card in candidates[:_MAX_DETAIL_FETCHES]:
            try:
                response = await client.get(card["url"], headers=_HEADERS)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("simplyhired: skipping unavailable detail %s: %s", card["job_id"], exc)
                continue
            description = _detail_description(response.text)
            if not description or not keyword_match(f"{card['title']} {card['company']} {description}", keywords):
                continue
            jobs.append({
                "job_id": f"simplyhired:{card['job_id']}",
                "title": card["title"],
                "company": card["company"],
                "location": card["location"],
                "url": card["url"],
                "description": description[:6000],
                "posted_date": None,
            })

    logger.info("simplyhired: %s jobs (after filters)", len(jobs))
    return jobs

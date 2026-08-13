"""LinkedIn job scraper using Playwright.

Manages session cookies stored in AWS Secrets Manager.
Extracts job listings from saved search URLs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import boto3
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

_COOKIES_SECRET_PREFIX = "linkedin-job-scout/linkedin-cookies"


async def _random_delay(min_ms: int = 1500, max_ms: int = 4000):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _extract_job_id(url: str) -> Optional[str]:
    try:
        path = urlparse(url).path
        # e.g. /jobs/view/1234567890
        parts = path.rstrip("/").split("/")
        return parts[-1] if parts[-1].isdigit() else None
    except Exception:
        return None


async def scrape_search(page: Page, search_url: str, max_jobs: int = 30) -> List[Dict]:
    """Navigate to a LinkedIn search URL and extract job data."""
    logger.info(f"Scraping: {search_url}")
    jobs: List[Dict] = []

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
        await _random_delay()

        # Check if redirected to any auth/login page
        _auth_patterns = ("linkedin.com/login", "linkedin.com/checkpoint", "linkedin.com/authwall", "linkedin.com/uas/login", "linkedin.com/signup")
        if any(p in page.url for p in _auth_patterns):
            logger.warning(f"LinkedIn session expired (redirected to {page.url}) — need re-authentication")
            return []

        # Wait for job cards
        await page.wait_for_selector(".jobs-search-results__list-item", timeout=15_000)

        cards = await page.query_selector_all(".jobs-search-results__list-item")
        logger.info(f"Found {len(cards)} job cards")

        for card in cards[:max_jobs]:
            try:
                # Click the card to load the detail pane
                await card.click()
                await _random_delay(800, 2000)

                # Extract metadata from card
                title_el = await card.query_selector(".job-card-list__title")
                company_el = await card.query_selector(".job-card-container__primary-description")
                location_el = await card.query_selector(".job-card-container__metadata-item")
                link_el = await card.query_selector("a.job-card-list__title")

                title = (await title_el.inner_text()).strip() if title_el else ""
                company = (await company_el.inner_text()).strip() if company_el else ""
                location = (await location_el.inner_text()).strip() if location_el else ""
                href = await link_el.get_attribute("href") if link_el else ""

                job_id = await _extract_job_id(href or "")
                if not job_id:
                    continue

                # Extract description from the detail pane
                desc_el = await page.query_selector(".jobs-description__content")
                description = (await desc_el.inner_text()).strip() if desc_el else ""

                full_url = f"https://www.linkedin.com/jobs/view/{job_id}"

                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": full_url,
                    "description": description[:6000],
                })
            except Exception as e:
                logger.warning(f"Error extracting card: {e}")
                continue

    except Exception as e:
        logger.error(f"scrape_search error for {search_url}: {e}")

    logger.info(f"Extracted {len(jobs)} jobs from {search_url}")
    return jobs


async def login(page: Page, email: str, password: str) -> bool:
    """Perform LinkedIn login and return True on success."""
    _login_urls = [
        "https://www.linkedin.com/login",
        "https://www.linkedin.com/uas/login",
    ]
    # Selectors LinkedIn uses for the username field (may vary by region/A-B test)
    _username_selectors = ["#username", "input[name='session_key']", "input[autocomplete='username']"]

    for login_url in _login_urls:
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
            logger.info(f"Login page loaded: {page.url}")

            # Find whichever username selector is present
            username_sel = None
            for sel in _username_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=8_000)
                    username_sel = sel
                    break
                except Exception:
                    continue

            if not username_sel:
                # Log page title and a snippet so we know what LinkedIn is showing
                try:
                    title = await page.title()
                    html_snippet = (await page.content())[:800]
                    logger.warning(
                        f"No username selector found on {page.url} — "
                        f"title={title!r} html_start={html_snippet!r}"
                    )
                except Exception:
                    logger.warning(f"No username selector found on {page.url} — trying next URL")
                continue

            await page.fill(username_sel, email)
            await _random_delay(500, 1200)

            password_sel = "#password" if username_sel == "#username" else "input[name='session_password']"
            try:
                await page.wait_for_selector(password_sel, timeout=5_000)
            except Exception:
                password_sel = "input[type='password']"
            await page.fill(password_sel, password)
            await _random_delay(500, 1000)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("domcontentloaded", timeout=20_000)

            _auth_patterns = ("linkedin.com/login", "linkedin.com/authwall", "linkedin.com/uas/login")
            if any(p in page.url for p in _auth_patterns):
                logger.error(f"Login failed — still on auth page: {page.url}")
                return False
            logger.info(f"Login succeeded, landed on: {page.url}")
            return True
        except Exception as e:
            logger.error(f"Login attempt via {login_url} failed: {e}")
            continue

    return False


def _load_cookies(secret_name: str, region: str) -> Optional[List[Dict]]:
    try:
        sm = boto3.client("secretsmanager", region_name=region)
        response = sm.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception as e:
        # Includes ResourceNotFoundException (first run) and parse errors
        logger.warning(f"Could not load cookies ({type(e).__name__}): {e}")
        return None


def _save_cookies(cookies: List[Dict], secret_name: str, region: str):
    sm = boto3.client("secretsmanager", region_name=region)
    value = json.dumps(cookies)
    try:
        sm.put_secret_value(SecretId=secret_name, SecretString=value)
    except sm.exceptions.ResourceNotFoundException:
        try:
            sm.create_secret(Name=secret_name, SecretString=value)
        except Exception as e:
            logger.error(f"Failed to create cookie secret: {e}")
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")


async def run_scraper(
    search_urls: List[str],
    email: str,
    password: str,
    region: str,
    secret_name: str = _COOKIES_SECRET_PREFIX,
    max_jobs_per_search: int = 30,
) -> List[Dict]:
    """Main entry point — launches browser, manages session, scrapes all URLs."""
    all_jobs: List[Dict] = []

    async with async_playwright() as p:
        _args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ]
        # --single-process is required in Lambda (seccomp prevents forking)
        # but hurts reliability outside Lambda
        if os.environ.get("LAMBDA_TASK_ROOT"):
            _args.append("--single-process")

        browser: Browser = await p.chromium.launch(headless=True, args=_args)
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # Restore cookies if available
        cookies = _load_cookies(secret_name, region)
        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"Restored {len(cookies)} cookies")

        page: Page = await context.new_page()

        # Check session validity
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20_000)
        _auth_patterns = ("linkedin.com/login", "linkedin.com/checkpoint", "linkedin.com/authwall", "linkedin.com/uas/login", "linkedin.com/signup")
        if any(p in page.url for p in _auth_patterns) or "feed" not in page.url:
            logger.info(f"Session not valid (url={page.url}) — re-authenticating")
            ok = await login(page, email, password)
            if not ok:
                logger.error("Authentication failed — aborting scraper")
                await browser.close()
                return []
            # Save fresh cookies
            new_cookies = await context.cookies()
            _save_cookies(new_cookies, secret_name, region)

        for url in search_urls:
            jobs = await scrape_search(page, url, max_jobs=max_jobs_per_search)
            all_jobs.extend(jobs)
            await _random_delay(3000, 6000)  # pause between searches

        # Persist updated cookies
        final_cookies = await context.cookies()
        _save_cookies(final_cookies, secret_name, region)

        await browser.close()

    return all_jobs

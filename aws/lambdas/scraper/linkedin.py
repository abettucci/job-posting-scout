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

from seniority import _EMPLOYEE_COUNT_RE, _parse_employee_count

logger = logging.getLogger(__name__)

_COOKIES_SECRET_PREFIX = "linkedin-job-scout/linkedin-cookies"

# Phrases that show up on LinkedIn's bot-detection / verification interstitials.
# If we see these, no selector will ever match — it's not a markup change,
# it's LinkedIn blocking the automated session (common from cloud/Lambda IPs).
# Shared between login() and fetch_linkedin_company_size() so both surfaces
# use the same definition of "this is a challenge page, not a real miss".
_CHALLENGE_INDICATORS = (
    "verify you're a human", "quick security check", "unusual activity",
    "captcha", "checkpoint/challenge", "let's do a quick",
)

# LinkedIn has changed the list-item wrapper across its jobs UI revisions.
# Keep these selectors specific to job cards; do not fall back to generic
# links or list items that could silently produce unrelated page content.
_JOB_CARD_SELECTORS = (
    ".jobs-search-results__list-item",
    ".jobs-search-results-list__list-item",
    ".scaffold-layout__list-item",
    "li[data-occludable-job-id]",
    ".job-card-container",
)

_JOB_TITLE_SELECTORS = (
    ".job-card-list__title",
    ".job-card-container__link",
    "strong",
    "a[href*='/jobs/view/']",
)
_JOB_COMPANY_SELECTORS = (
    ".job-card-container__primary-description",
    ".job-card-container__company-name",
    ".artdeco-entity-lockup__subtitle",
    "a[href*='/company/']",
)
_JOB_LOCATION_SELECTORS = (
    ".job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption",
    "[class*='metadata']",
    "[class*='location']",
)
_JOB_LINK_SELECTOR = "a[href*='/jobs/view/']"

_NO_RESULTS_INDICATORS = (
    "no matching jobs found",
    "no jobs found",
    "there are no jobs matching your search",
    "no results found",
)


class LinkedInAuthenticationError(RuntimeError):
    """The shared LinkedIn session cannot be used from this runtime.

    This is intentionally distinct from a listing/search failure: the caller
    can open a bounded cooldown and report a useful source status instead of
    spending the full Lambda timeout retrying the same login page.
    """


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


async def _first_matching_element(root, selectors):
    """Return the first matching descendant, tolerating selector drift."""
    for selector in selectors:
        element = await root.query_selector(selector)
        if element:
            return element
    return None


async def _cards_from_job_links(page: Page):
    """Build card handles from canonical job links when LinkedIn changes its
    surrounding list-item classes. The chosen ancestor must contain exactly
    one distinct /jobs/view/<id> link, which avoids treating the whole results
    list as a card.
    """
    links = await page.query_selector_all(_JOB_LINK_SELECTOR)
    cards = []
    seen_job_ids = set()
    for link in links:
        if not await link.is_visible():
            continue
        href = await link.get_attribute("href") or ""
        job_id = await _extract_job_id(href)
        if not job_id or job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)
        ancestor = await link.evaluate_handle("""anchor => {
          const jobLinks = node => [...node.querySelectorAll("a[href*='/jobs/view/']")]
            .map(link => {
              try { return new URL(link.href, location.href).pathname; }
              catch { return link.getAttribute('href') || ''; }
            });
          let node = anchor.parentElement;
          let best = node || anchor;
          for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
            const ids = new Set(jobLinks(node));
            const textLength = (node.innerText || '').trim().length;
            if (ids.size > 1 || textLength > 1800) break;
            if (ids.size === 1 && textLength > 0) best = node;
          }
          return best;
        }""")
        card = ancestor.as_element()
        if card:
            cards.append(card)
    return cards


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

        # Wait for any known job-card wrapper. LinkedIn has changed the outer
        # list markup more than once, so a single legacy selector made valid
        # searches look like scraper failures.
        selector_group = ", ".join((*_JOB_CARD_SELECTORS, _JOB_LINK_SELECTOR))
        try:
            await page.wait_for_selector(selector_group, state="visible", timeout=15_000)
        except Exception:
            title = ""
            body_text = ""
            try:
                title = await page.title()
                body_text = (await page.locator("body").inner_text(timeout=2_000)).lower()
            except Exception:
                pass

            lowered_url = page.url.lower()
            challenge = any(indicator in body_text for indicator in _CHALLENGE_INDICATORS)
            no_results = any(indicator in body_text for indicator in _NO_RESULTS_INDICATORS)
            selector_counts = {}
            for selector in _JOB_CARD_SELECTORS:
                try:
                    selector_counts[selector] = await page.locator(selector).count()
                except Exception:
                    selector_counts[selector] = -1
            try:
                job_link_count = await page.locator(_JOB_LINK_SELECTOR).count()
            except Exception:
                job_link_count = -1

            if challenge or any(part in lowered_url for part in ("/checkpoint", "/authwall", "/login")):
                reason = "challenge_or_auth"
            elif no_results:
                reason = "no_results"
            else:
                reason = "job_cards_not_found"

            logger.warning(
                "LinkedIn search produced no visible job cards: reason=%s final_url=%s "
                "title=%r challenge=%s no_results=%s job_link_count=%s selector_counts=%s",
                reason,
                page.url,
                title[:160],
                challenge,
                no_results,
                job_link_count,
                selector_counts,
            )
            if job_link_count <= 0:
                return []

        cards = []
        selected_selector = None
        for selector in _JOB_CARD_SELECTORS:
            locator = page.locator(selector)
            for index in range(await locator.count()):
                candidate = locator.nth(index)
                if await candidate.is_visible():
                    handle = await candidate.element_handle()
                    if handle:
                        selected_selector = selector
                        cards.append(handle)
            if cards:
                break

        if not cards:
            cards = await _cards_from_job_links(page)
            if cards:
                selected_selector = f"{_JOB_LINK_SELECTOR} (unique-link ancestor)"

        if not cards:
            logger.warning(
                "LinkedIn card selectors and job-link fallback matched no cards: final_url=%s selectors=%s job_link_count=%s",
                page.url,
                _JOB_CARD_SELECTORS,
                await page.locator(_JOB_LINK_SELECTOR).count(),
            )
            return []
        logger.info("Found %s job cards using selector %s", len(cards), selected_selector)

        for card in cards[:max_jobs]:
            try:
                # Click the card to load the detail pane
                await card.click()
                await _random_delay(800, 2000)

                # Extract metadata from card
                title_el = await _first_matching_element(card, _JOB_TITLE_SELECTORS)
                company_el = await _first_matching_element(card, _JOB_COMPANY_SELECTORS)
                location_el = await _first_matching_element(card, _JOB_LOCATION_SELECTORS)
                link_el = await card.query_selector(_JOB_LINK_SELECTOR)
                is_link_card = await card.evaluate("element => element.tagName === 'A'")
                if is_link_card:
                    link_el = card

                title = (await title_el.inner_text()).strip() if title_el else ""
                company = (await company_el.inner_text()).strip() if company_el else ""
                location = (await location_el.inner_text()).strip() if location_el else ""
                href = await link_el.get_attribute("href") if link_el else ""
                if not title and link_el:
                    title = (await link_el.inner_text()).strip()

                # Company's own LinkedIn page (for company-size enrichment,
                # see fetch_linkedin_company_size). None is a common, non-error
                # outcome — the job just keeps its description-based size hint.
                company_link_el = (
                    await page.query_selector(".jobs-unified-top-card__company-name a")
                    or await card.query_selector("a[href*='/company/']")
                )
                company_linkedin_url = None
                if company_link_el:
                    company_href = await company_link_el.get_attribute("href")
                    if company_href:
                        company_linkedin_url = company_href.split("?")[0]
                        if company_linkedin_url.startswith("/"):
                            company_linkedin_url = f"https://www.linkedin.com{company_linkedin_url}"

                job_id = await _extract_job_id(href or "")
                if not job_id:
                    continue

                # Extract description from the detail pane
                desc_el = await _first_matching_element(page, (
                    ".jobs-description__content",
                    ".jobs-box__html-content",
                    ".jobs-description-content__text",
                    ".jobs-description",
                ))
                description = (await desc_el.inner_text()).strip() if desc_el else ""

                full_url = f"https://www.linkedin.com/jobs/view/{job_id}"

                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": full_url,
                    "description": description[:6000],
                    "company_linkedin_url": company_linkedin_url,
                })
            except Exception as e:
                logger.warning(f"Error extracting card: {e}")
                continue

    except Exception as e:
        logger.error(f"scrape_search error for {search_url}: {e}")

    logger.info(f"Extracted {len(jobs)} jobs from {search_url}")
    return jobs


_COMPANY_SIZE_SELECTORS = [
    ".org-about-company-module__company-size-definition-text",
    "[data-test-id='about-us__size'] dd",
    ".org-page-details__definition-text",
]


async def fetch_linkedin_company_size(page: Page, company_url: str) -> Optional[Dict[str, object]]:
    """Navigate the already-authenticated `page` to a LinkedIn company's About
    page and extract the employee-count range LinkedIn displays there (e.g.
    "1,001-5,000 employees"). Never opens a second login flow — reuses
    whatever session `page` already has.

    Returns {"size_hint": "startup"|"midsize"|"enterprise"|None, "raw_range": str|None}
    on a successful page load — a None size_hint with the page having loaded
    fine is a valid, cacheable negative result (no employee-count text found
    anywhere on the page). Raises on navigation failure or a detected
    challenge page — callers must NOT cache a raised error, since it may be
    transient (network hiccup) or session-related (next run may work).

    Always an estimate — LinkedIn's own self-reported bucket, not an audited
    headcount. Same "never present as verified" philosophy as
    seniority.py's extract_company_size_hint().
    """
    about_url = company_url.split("?")[0].rstrip("/")
    if not about_url.endswith("/about"):
        about_url = f"{about_url}/about/"

    await page.goto(about_url, wait_until="domcontentloaded", timeout=20_000)
    await _random_delay(1000, 2000)

    html = await page.content()
    if any(ind in html.lower() for ind in _CHALLENGE_INDICATORS):
        raise RuntimeError(f"challenge page served on {page.url} — treat as transient, do not cache")

    text = None
    for sel in _COMPANY_SIZE_SELECTORS:
        el = await page.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            break
    if not text:
        # Markup-drift-resistant fallback: scan the whole page body for an
        # "N employees"/"N-N employees" mention instead of depending solely
        # on one exact class name (LinkedIn restyles this page periodically,
        # same lesson as the login() selector list).
        body_text = await page.inner_text("body")
        match = _EMPLOYEE_COUNT_RE.search(body_text)
        text = match.group(0) if match else None

    if not text:
        return {"size_hint": None, "raw_range": None}
    return {"size_hint": _parse_employee_count(text), "raw_range": text}


async def login(page: Page, email: str, password: str) -> bool:
    """Perform LinkedIn login and return True on success."""
    _login_urls = [
        "https://www.linkedin.com/login",
        "https://www.linkedin.com/uas/login",
    ]
    # Selectors LinkedIn uses for the username field (may vary by region/A-B test)
    _username_selectors = [
        "#username",
        "input[name='session_key']",
        "input[autocomplete='username']",
        "input[type='email']",
        "form.login__form input[type='text']",
        "#session_key",
        "input[name='email']",
        "input[autocomplete='off'][name*='session' i]",
        "form input[type='text']:visible",
    ]

    for login_url in _login_urls:
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
            # Wait for scripts to finish executing — LinkedIn renders the form with JS.
            # "networkidle" catches client-side hydration better than "load", which
            # fires before React/JS-rendered form widgets necessarily mount.
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            logger.info(f"Login page loaded: {page.url}")

            # Wait once for the complete selector family instead of waiting up
            # to 15 seconds for each historic selector. A blocked/half-rendered
            # login page otherwise burns several minutes of a Lambda run.
            username_sel = None
            try:
                selector_group = ", ".join(_username_selectors)
                await page.wait_for_selector(selector_group, state="visible", timeout=12_000)
                for sel in _username_selectors:
                    if await page.locator(sel).first.is_visible():
                        username_sel = sel
                        break
            except Exception:
                pass

            if not username_sel:
                # Keep enough diagnostic context for CloudWatch without dumping
                # a full third-party sign-in page into logs.
                try:
                    title = await page.title()
                    html = await page.content()
                    lowered = html.lower()
                    logger.warning(
                        "LinkedIn login unavailable at %s (title=%r, challenge=%s, form=%s, inputs=%s)",
                        page.url,
                        title,
                        any(ind in lowered for ind in _CHALLENGE_INDICATORS),
                        "<form" in lowered,
                        lowered.count("<input"),
                    )
                except Exception:
                    logger.warning(f"LinkedIn login unavailable at {page.url}")
                # Both paths are served by the same auth application today;
                # trying the legacy URL repeats the same blocked state.
                return False

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
            return False

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


def _company_cache_key(company_url: str) -> Optional[str]:
    try:
        parts = urlparse(company_url).path.rstrip("/").split("/")
        return parts[-1] if parts and parts[-1] else None  # slug after /company/
    except Exception:
        return None


def _apply_company_size(jobs: List[Dict], result: Dict[str, object]) -> None:
    for job in jobs:
        job["company_size_hint"] = result["size_hint"]
        job["company_size_source"] = "linkedin"
        job["company_size_raw"] = result.get("raw_range")


async def _enrich_with_company_size(
    page: Page,
    jobs: List[Dict],
    cache_get,
    cache_put,
    max_lookups: int,
) -> None:
    """Mutates `jobs` in place, adding company_size_hint/source/raw wherever a
    LinkedIn-sourced result is available. Dedupes by company within this run
    first (many postings share an employer), then checks the cross-run cache,
    so a popular employer costs at most one company-page visit per run and at
    most one per cache TTL across all runs. Every failure mode (no company
    URL, cache miss with the cap reached, a transient fetch error, or a
    challenge page) just leaves the job with its existing description-based
    regex hint — never blocks or fails the overall scrape."""
    by_company: Dict[str, List[Dict]] = {}
    for job in jobs:
        url = job.get("company_linkedin_url")
        key = _company_cache_key(url) if url else None
        if key:
            by_company.setdefault(key, []).append(job)

    lookups_done = 0
    for key, company_jobs in by_company.items():
        cached = cache_get(key) if cache_get else None
        if cached is not None:
            logger.info(f"company-size cache hit for {key}")
            _apply_company_size(company_jobs, cached)
            continue
        if lookups_done >= max_lookups:
            logger.info(f"company-size lookup cap reached ({max_lookups}) — skipping {key}")
            continue

        url = company_jobs[0]["company_linkedin_url"]
        try:
            result = await fetch_linkedin_company_size(page, url)
        except Exception as e:
            logger.warning(f"company-size lookup failed for {url}: {e}")
            continue  # transient/challenge — do not cache, next run retries

        lookups_done += 1
        if cache_put:
            ttl_days = 30 if result.get("size_hint") else 7
            cache_put(key, result.get("size_hint"), result.get("raw_range"), ttl_days=ttl_days)
        if result.get("size_hint"):
            _apply_company_size(company_jobs, result)
        await _random_delay(1500, 3500)


async def run_scraper(
    search_urls: List[str],
    email: str,
    password: str,
    region: str,
    secret_name: str = _COOKIES_SECRET_PREFIX,
    max_jobs_per_search: int = 30,
    cache_get=None,
    cache_put=None,
    max_company_lookups: int = 25,
) -> Dict[str, List[Dict]]:
    """Main entry point — launches browser, manages session, scrapes all URLs.

    Returns a {search_url: jobs} mapping (not a flat list) so callers can scope
    each URL's results to only the users who subscribed to that specific search.
    """
    results: Dict[str, List[Dict]] = {}

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
                logger.error("LinkedIn authentication unavailable — aborting LinkedIn source")
                await browser.close()
                raise LinkedInAuthenticationError("LinkedIn sign-in is unavailable from the scraper runtime")
            # Save fresh cookies
            new_cookies = await context.cookies()
            _save_cookies(new_cookies, secret_name, region)

        for url in search_urls:
            jobs = await scrape_search(page, url, max_jobs=max_jobs_per_search)
            results[url] = jobs
            await _random_delay(3000, 6000)  # pause between searches

        if cache_get and cache_put:
            all_jobs = [job for jobs in results.values() for job in jobs]
            await _enrich_with_company_size(page, all_jobs, cache_get, cache_put, max_company_lookups)

        # Persist updated cookies
        final_cookies = await context.cookies()
        _save_cookies(final_cookies, secret_name, region)

        await browser.close()

    return results

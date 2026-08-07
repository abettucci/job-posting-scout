"""
Local test script for the LinkedIn scraper.

Usage:
  cd aws/lambdas
  pip install playwright anthropic boto3 requests
  playwright install chromium
  python ../../test_scraper_local.py

  # To upload your LinkedIn session cookies to AWS so Lambda can use them:
  python ../../test_scraper_local.py --save-cookies

Environment variables (or edit the CONFIG block below):
  LINKEDIN_EMAIL, LINKEDIN_PASSWORD, ANTHROPIC_API_KEY
  LINKEDIN_SEARCH_URL  — a LinkedIn job search URL to scrape
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# ── path setup (works both from repo root and aws/lambdas/) ──────────────────
_HERE = Path(__file__).resolve().parent
for candidate in [
    _HERE / "aws/lambdas/scraper",
    _HERE / "aws/lambdas/shared",
    _HERE / "scraper",
    _HERE / "shared",
]:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# ── CONFIG — edit here or set env vars ───────────────────────────────────────
CONFIG = {
    "linkedin_email":    os.environ.get("LINKEDIN_EMAIL", ""),
    "linkedin_password": os.environ.get("LINKEDIN_PASSWORD", ""),
    "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    # Paste any LinkedIn job search URL here
    "search_url": os.environ.get(
        "LINKEDIN_SEARCH_URL",
        "https://www.linkedin.com/jobs/search/?keywords=python%20developer&location=Argentina&f_TPR=r86400",
    ),
    # Candidate profile used for Claude scoring
    "profile": {
        "title": "Software Engineer",
        "skills": "Python, AWS, FastAPI, Docker, SQL",
        "experience_years": 5,
        "desired_role": "Backend engineer at a tech startup or scale-up",
        "location_preference": "Remote or Argentina",
        "deal_breakers": "Java-only shops, roles requiring 10+ years",
    },
    "score_threshold": 70,
    "max_jobs": 10,
    "dry_run": False,   # True = skip Claude scoring (faster, free)
    # AWS settings for --save-cookies
    "aws_region":       os.environ.get("AWS_REGION", "us-east-2"),
    "cookies_secret":   "linkedin-job-scout/linkedin-cookies",
}
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _save_cookies_to_aws(cookies: list, secret_name: str, region: str):
    import boto3
    sm = boto3.client("secretsmanager", region_name=region)
    value = json.dumps(cookies)
    try:
        sm.put_secret_value(SecretId=secret_name, SecretString=value)
        print(f"\n✅  Saved {len(cookies)} cookies to Secrets Manager: {secret_name}")
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(Name=secret_name, SecretString=value)
        print(f"\n✅  Created secret and saved {len(cookies)} cookies: {secret_name}")
    except Exception as e:
        print(f"\n❌  Failed to save cookies: {e}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-cookies", action="store_true",
                        help="Log in locally and upload session cookies to AWS Secrets Manager for Lambda use")
    args = parser.parse_args()

    cfg = CONFIG

    if not cfg["linkedin_email"] or not cfg["linkedin_password"]:
        print("\n❌  Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD (env vars or CONFIG block)\n")
        sys.exit(1)

    if args.save_cookies:
        print(f"\n🍪  Mode: save cookies to AWS Secrets Manager ({cfg['cookies_secret']})")
        print(f"🔑  LinkedIn: {cfg['linkedin_email']}\n")
    else:
        print(f"\n🔍  Search URL: {cfg['search_url']}")
        print(f"👤  Profile:    {cfg['profile']['desired_role']}")
        print(f"📊  Threshold:  {cfg['score_threshold']}/100")
        print(f"🤖  Dry run:    {cfg['dry_run']}\n")

    # ── 1. Scrape ─────────────────────────────────────────────────────────────
    from linkedin import scrape_search
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # headless=False so you can watch
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        # Log in
        logger.info("Logging in to LinkedIn...")
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30_000)

        # Wait for the form — if it doesn't appear, take a screenshot and pause
        try:
            await page.wait_for_selector("#username", timeout=15_000)
        except Exception:
            await page.screenshot(path="linkedin_login_error.png")
            print(f"\n⚠️  Login form not found. Current URL: {page.url}")
            print("   Screenshot saved to linkedin_login_error.png")
            print("   LinkedIn may be showing a CAPTCHA or challenge page.")
            print("   Complete it manually in the browser window, then press Enter...")
            input()

        await page.fill("#username", cfg["linkedin_email"])
        await page.fill("#password", cfg["linkedin_password"])
        await page.click('button[type="submit"]')

        # Wait for redirect to feed or checkpoint
        try:
            await page.wait_for_url(lambda url: "feed" in url or "mynetwork" in url or "checkpoint" in url or "challenge" in url, timeout=20_000)
        except Exception:
            pass

        if "checkpoint" in page.url or "challenge" in page.url:
            await page.screenshot(path="linkedin_challenge.png")
            print(f"\n⚠️  LinkedIn is asking for verification. URL: {page.url}")
            print("   Screenshot saved to linkedin_challenge.png")
            print("   Complete the verification in the browser window, then press Enter...")
            input()

        if "feed" not in page.url and "mynetwork" not in page.url:
            print(f"\n⚠️  Login might have failed — current URL: {page.url}")
            print("   Check the browser window. Press Enter to continue anyway...")
            input()

        # If --save-cookies: export and upload to AWS, then exit
        if args.save_cookies:
            cookies = await ctx.cookies()
            await browser.close()
            _save_cookies_to_aws(cookies, cfg["cookies_secret"], cfg["aws_region"])
            print("   Lambda will use these cookies on the next scraper run (no login needed).\n")
            return

        logger.info(f"Logged in. Scraping up to {cfg['max_jobs']} jobs...")
        jobs = await scrape_search(page, cfg["search_url"], max_jobs=cfg["max_jobs"])
        await browser.close()

    if not jobs:
        print("\n⚠️  No jobs found. Possible causes:")
        print("   • Login failed / LinkedIn showed a CAPTCHA")
        print("   • CSS selectors changed (LinkedIn updates frequently)")
        print("   • Search URL has no results\n")
        return

    print(f"\n✅  Scraped {len(jobs)} jobs\n")

    # ── 2. Score with Claude ──────────────────────────────────────────────────
    results = []
    if cfg["dry_run"]:
        logger.info("Dry run — skipping Claude scoring")
        for job in jobs:
            results.append({"job": job, "score": None, "summary": "(dry run)", "recommendation": "?"})
    else:
        if not cfg["anthropic_api_key"]:
            print("❌  Set ANTHROPIC_API_KEY to enable scoring (or set dry_run=True)\n")
            sys.exit(1)

        from anthropic import Anthropic
        from scorer import score_job

        client = Anthropic(api_key=cfg["anthropic_api_key"])
        logger.info(f"Scoring {len(jobs)} jobs with Claude Haiku...")

        for i, job in enumerate(jobs, 1):
            result = score_job(client, job, cfg["profile"])
            results.append({"job": job, **result})
            status = "🟢" if result["score"] >= cfg["score_threshold"] else "🔴"
            print(f"  {status} [{i:2d}/{len(jobs)}] {result['score']:3d}/100  "
                  f"{job.get('company','?'):25s}  {job.get('title','?')[:50]}")

    # ── 3. Print summary ──────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("RESULTS ABOVE THRESHOLD")
    print("─" * 70)
    above = [r for r in results if r.get("score") and r["score"] >= cfg["score_threshold"]]
    if not above:
        print("  None — try lowering score_threshold or changing the search URL")
    for r in sorted(above, key=lambda x: x["score"], reverse=True):
        j = r["job"]
        print(f"\n  Score:   {r['score']}/100  ({r.get('recommendation','?')})")
        print(f"  Title:   {j.get('title','?')}")
        print(f"  Company: {j.get('company','?')}")
        print(f"  URL:     {j.get('url','?')}")
        print(f"  Summary: {r.get('summary','')}")
        if r.get("reasons"):
            for reason in r["reasons"]:
                print(f"    • {reason}")

    print("\n" + "─" * 70)
    print(f"Total: {len(jobs)} scraped  |  {len(above)} above threshold ({cfg['score_threshold']})\n")

    # ── 4. Save to JSON ───────────────────────────────────────────────────────
    out = Path("scraper_test_output.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"📄  Full output saved to {out}\n")


if __name__ == "__main__":
    asyncio.run(main())

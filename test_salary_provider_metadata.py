"""Fixtures verifying that provider normalization retains eligibility evidence."""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/scraper"))
# All network calls below use fixture clients, like the other provider tests.
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=None))
from providers import onlinejobs, remoteok, remotive  # noqa: E402
from providers._utils import location_match  # noqa: E402


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class Client:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, *_args, **_kwargs):
        return Response(self.data)


class SalaryProviderTests(unittest.TestCase):
    def test_onlinejobs_is_country_remote_not_worldwide(self):
        document = '''<a href="/jobseekers/job/Backend-123"><div class="jobpost-cat-box">
          <h4>Backend Engineer</h4><div class="desc">Python development</div>
          <p data-temp="2026-10-31 12:00:00">Created</p></div></a>'''
        job = onlinejobs._parse_listing_page(document)[0]
        self.assertEqual(job["location"], "Remote — Philippines")
        self.assertFalse(location_match(job["location"], "Argentina, Worldwide"))
        self.assertTrue(location_match(job["location"], "Philippines"))
        self.assertTrue(job["posted_date"].startswith("2026-10-31"))

    def test_remoteok_keeps_salary_currency_even_outside_description(self):
        row = {"id": "1", "position": "Engineer", "url": "https://example.test/1",
               "location": "Remote", "description": "Build APIs", "salary_currency": "PHP"}
        with patch("providers.remoteok.httpx.AsyncClient", return_value=Client([row])):
            job = asyncio.run(remoteok.fetch_jobs())[0]
        self.assertEqual(job["salary_currency"], "PHP")

    def test_remotive_keeps_salary_field_even_outside_description(self):
        row = {"id": "1", "title": "Engineer", "url": "https://example.test/1",
               "description": "Build APIs", "salary": "PHP 60000"}
        with patch("providers.remotive.httpx.AsyncClient", return_value=Client({"jobs": [row]})):
            job = asyncio.run(remotive.fetch_jobs())[0]
        self.assertEqual(job["salary"], "PHP 60000")


if __name__ == "__main__":
    unittest.main()

"""Focused, network-free checks for the two public source adapters."""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/scraper"))
# The local lightweight verification environment intentionally has no Lambda
# dependencies installed. Providers only need this placeholder until each test
# replaces AsyncClient with its deterministic async fixture.
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=None))

from providers import deel, freehire, workday  # noqa: E402


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FreeHireClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, *_args, **_kwargs):
        return Response({
            "data": [{
                "public_slug": "go-engineer-acme-1",
                "title": "Go Engineer",
                "company": "Acme",
                "location": "Remote — Worldwide",
                "url": "https://example.test/jobs/go-engineer-acme-1",
                "description": "Build Go services",
                "skills": ["Go", "PostgreSQL"],
                "work_mode": "remote",
                "posted_at": "2026-09-20T12:00:00Z",
            }],
            "meta": {"total": 1},
        })


class WorkdayClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, *_args, **kwargs):
        self.asserted_payload = kwargs["json"]
        return Response({
            "total": 1,
            "jobPostings": [{
                "title": "Backend Engineer",
                "externalPath": "/job/Remote/Backend-Engineer_R-1",
                "jobReqId": "R-1",
                "locationsText": "Remote — Worldwide",
                "postedOn": "Posted today",
                "bulletFields": ["Engineering"],
            }],
        })

    async def get(self, *_args, **_kwargs):
        return Response({"jobPostingInfo": {
            "jobDescription": "<p>Build Python services</p>",
            "location": "Remote — Worldwide",
            "startDate": "2026-09-19T00:00:00Z",
        }})


class DeelClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, *_args, **_kwargs):
        if url.endswith("/sitemap.xml"):
            return TextResponse("""
                <urlset><url><loc>https://jobs.deel.com/acme/job-details/job-123/overview</loc></url></urlset>
            """)
        if url.endswith("/job-details/job-123/overview"):
            return TextResponse("""
                <script type="application/ld+json">{
                  "@context": "https://schema.org", "@type": "JobPosting",
                  "title": "Backend Engineer", "description": "<p>Build Python services</p>",
                  "datePosted": "2026-09-20T12:00:00Z", "jobLocationType": "TELECOMMUTE",
                  "hiringOrganization": {"name": "Acme"}
                }</script>
            """)
        raise AssertionError(url)


class TextResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FailingResponse:
    text = ""

    def raise_for_status(self):
        raise RuntimeError("not found")


class FallbackDeelClient(DeelClient):
    async def get(self, url, *_args, **_kwargs):
        if url.endswith("/sitemap.xml"):
            return FailingResponse()
        if url == "https://jobs.deel.com/acme":
            return TextResponse("""
                <script type="application/ld+json">{
                  "@type": "ItemList",
                  "itemListElement": [{"url": "https://jobs.deel.com/acme/job-details/job-123/overview"}]
                }</script>
            """)
        return await super().get(url, *_args, **_kwargs)


class ProviderSourceTests(unittest.TestCase):
    def test_freehire_normalizes_structured_public_job(self):
        with patch("providers.freehire.httpx.AsyncClient", return_value=FreeHireClient()):
            jobs = asyncio.run(freehire.fetch_jobs("go", "Remote"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "freehire:go-engineer-acme-1")
        self.assertEqual(jobs[0]["company"], "Acme")
        self.assertIn("2026-09-20", jobs[0]["posted_date"])

    def test_workday_parses_public_board_and_fetches_detail(self):
        with patch("providers.workday.httpx.AsyncClient", return_value=WorkdayClient()):
            jobs = asyncio.run(workday.fetch_jobs(
                "https://acme.wd5.myworkdayjobs.com/en-US/External", "Acme", "python", "Remote"
            ))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "workday:acme:External:R-1")
        self.assertEqual(jobs[0]["url"], "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Remote/Backend-Engineer_R-1")
        self.assertIn("Python services", jobs[0]["description"])

    def test_workday_rejects_non_public_board_url(self):
        with self.assertRaises(ValueError):
            workday.parse_board_url("https://example.com/careers")

    def test_deel_reads_public_sitemap_and_job_overview(self):
        with patch("providers.deel.httpx.AsyncClient", return_value=DeelClient()):
            jobs = asyncio.run(deel.fetch_jobs("https://jobs.deel.com/job-boards/acme", "", "python", "Remote"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "deel:acme:job-123")
        self.assertEqual(jobs[0]["company"], "Acme")
        self.assertEqual(jobs[0]["location"], "Remote")

    def test_deel_rejects_job_or_non_deel_urls(self):
        with self.assertRaises(ValueError):
            deel.parse_board_url("https://jobs.deel.com/acme/job-details/123/overview")
        with self.assertRaises(ValueError):
            deel.parse_board_url("https://example.com/acme")

    def test_deel_falls_back_to_public_board_json_ld(self):
        with patch("providers.deel.httpx.AsyncClient", return_value=FallbackDeelClient()):
            jobs = asyncio.run(deel.fetch_jobs("https://jobs.deel.com/acme"))
        self.assertEqual([job["job_id"] for job in jobs], ["deel:acme:job-123"])


if __name__ == "__main__":
    unittest.main()

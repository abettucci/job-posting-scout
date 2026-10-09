"""Network-free checks for the additional public job-source adapters."""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/scraper"))
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=None))

from providers import dixcover, justjoin, wellfound  # noqa: E402


class Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class WellfoundClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, *_args, **_kwargs):
        if url == "https://wellfound.com/jobs":
            state = {"JobListing:42": {
                "id": "42", "slug": "backend-engineer", "title": "Backend Engineer",
                "remote": True, "acceptedRemoteLocationNames": [], "liveStartAt": 1720000000,
                "startup": {"__ref": "Startup:1"},
            }, "Startup:1": {"name": "Acme", "highConcept": "Python data platform"}}
            document = f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": {"apolloState": {"data": state}}}})}</script>'
            return Response(text=document)
        if url == "https://wellfound.com/jobs/42-backend-engineer":
            return Response(text='''<script type="application/ld+json">{
              "@type":"JobPosting", "title":"Backend Engineer", "datePosted":"2026-10-08T00:00:00Z",
              "jobLocationType":"TELECOMMUTE", "hiringOrganization":{"name":"Acme"},
              "description":"<p>Build Python APIs with PostgreSQL.</p>"
            }</script>''')
        raise AssertionError(url)


class JustJoinClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, *_args, **_kwargs):
        if url == "https://justjoin.it/api/candidate-api/offers":
            return Response(payload={"data": [{
                "guid": "offer-1", "slug": "backend-engineer", "title": "Backend Engineer",
                "companyName": "Acme", "workplaceType": "remote", "requiredSkills": ["Python"],
                "publishedAt": "2026-10-08T00:00:00Z",
            }]})
        if url.endswith("/backend-engineer"):
            return Response(payload={"body": "<p>Build Python services with PostgreSQL.</p>", "workplaceType": "remote"})
        raise AssertionError(url)


class DixcoverClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, *_args, **_kwargs):
        self.url = url
        return Response(payload=[{
            "id": 99, "title": {"rendered": "Python Engineer at Acme"},
            "content": {"rendered": "<p>Worldwide remote Python engineering role.</p>"},
            "link": "https://jobs.smartyacad.com/python-engineer/", "date_gmt": "2026-10-08T00:00:00",
        }])


class AdditionalProviderSourceTests(unittest.TestCase):
    def test_wellfound_reads_public_index_and_job_posting(self):
        with patch("providers.wellfound.httpx.AsyncClient", return_value=WellfoundClient()):
            jobs = asyncio.run(wellfound.fetch_jobs("python", "Remote"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "wellfound:42")
        self.assertEqual(jobs[0]["location"], "Remote")
        self.assertIn("PostgreSQL", jobs[0]["description"])

    def test_justjoin_reads_public_listing_and_detail(self):
        with patch("providers.justjoin.httpx.AsyncClient", return_value=JustJoinClient()):
            jobs = asyncio.run(justjoin.fetch_jobs("python", "Remote"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "justjoin:offer-1")
        self.assertEqual(jobs[0]["company"], "Acme")

    def test_dixcover_reads_public_remote_category(self):
        with patch("providers.dixcover.httpx.AsyncClient", return_value=DixcoverClient()):
            jobs = asyncio.run(dixcover.fetch_jobs("python", "Worldwide"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "dixcover:99")
        self.assertEqual(jobs[0]["location"], "Remote — Worldwide")


if __name__ == "__main__":
    unittest.main()

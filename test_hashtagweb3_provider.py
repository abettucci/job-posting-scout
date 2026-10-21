"""Fixture-based tests for Hashtag Web3's public Next.js pages."""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/scraper"))
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=None, HTTPError=Exception))

from providers import hashtagweb3  # noqa: E402


class Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def flight_document(items):
    frame = "prefix " + json.dumps({"initialJobs": items}) + " suffix"
    encoded = json.dumps(frame)[1:-1]
    return f'<script>self.__next_f.push([1,"{encoded}"])</script>'


class HashtagWeb3Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, *_args, **_kwargs):
        if url == "https://hashtagweb3.com/jobs":
            return Response(flight_document([{
                "id": "job-1", "slug": "eng1", "title": "Backend Engineer", "company": "Acme",
                "link": "https://jobs.example.test/acme/backend", "location": "Remote",
                "date": "2026-10-19T00:00:00Z",
            }]))
        if url == "https://hashtagweb3.com/eng1":
            return Response('''<script type="application/ld+json">{
              "@type":"JobPosting", "title":"Backend Engineer", "datePosted":"2026-10-19T00:00:00Z",
              "jobLocationType":"TELECOMMUTE", "hiringOrganization":{"name":"Acme"},
              "description":"<p>Build Python services with PostgreSQL.</p>"
            }</script>''')
        raise AssertionError(url)


class HashtagWeb3ProviderTests(unittest.TestCase):
    def test_reads_public_index_and_detail(self):
        with patch("providers.hashtagweb3.httpx.AsyncClient", return_value=HashtagWeb3Client()):
            jobs = asyncio.run(hashtagweb3.fetch_jobs("python", "Worldwide"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "hashtagweb3:job-1")
        self.assertEqual(jobs[0]["url"], "https://jobs.example.test/acme/backend")
        self.assertEqual(jobs[0]["location"], "Remote")
        self.assertIn("PostgreSQL", jobs[0]["description"])

    def test_fails_healthily_when_public_index_shape_changes(self):
        with patch("providers.hashtagweb3.httpx.AsyncClient", return_value=HashtagWeb3Client()):
            self.assertEqual(hashtagweb3._index_jobs("<html>no data</html>"), [])


if __name__ == "__main__":
    unittest.main()

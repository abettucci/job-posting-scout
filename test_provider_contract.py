"""Network-free contract checks every provider must pass at the boundary."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/scraper"))

from providers.contract import ProviderContractError, fetch_with_contract, normalize_jobs  # noqa: E402


class ProviderContractTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_valid_rows(self):
        jobs = normalize_jobs("fixture", [
            {"job_id": "a", "title": " Backend Engineer ", "company": " Acme ", "url": "https://example.test/a"},
            {"job_id": "a", "title": "Duplicate", "company": "Acme", "url": "https://example.test/a"},
        ])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Backend Engineer")
        self.assertEqual(jobs[0]["description"], "")

    def test_rejects_invalid_source_rows(self):
        with self.assertRaises(ProviderContractError):
            normalize_jobs("fixture", [{"job_id": "a", "title": "Role", "url": "not-a-url"}])

    def test_wraps_fetch_errors_with_source_context(self):
        async def broken():
            raise TimeoutError("network")

        with self.assertRaisesRegex(ProviderContractError, "fixture request failed"):
            asyncio.run(fetch_with_contract("fixture", broken))


if __name__ == "__main__":
    unittest.main()

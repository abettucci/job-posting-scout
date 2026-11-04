"""Network- and dependency-free tests for discovery freshness and salary guards."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/shared"))
from job_policy import age_mismatch, local_salary_currency, posting_mismatch  # noqa: E402

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
REGIONS = ["Argentina", "LATAM", "Worldwide"]


class PostingAgeTests(unittest.TestCase):
    def test_age_uses_original_date_not_recent_scrape(self):
        result = age_mismatch({"posted_date": "2026-05-01", "timestamp": NOW.isoformat()}, NOW)
        self.assertTrue(result["deal_breaker"])
        self.assertIn("2026-05-01", result["reasons"][0])

    def test_republished_date_does_not_hide_old_creation_date(self):
        self.assertIsNotNone(age_mismatch({"posted_date": NOW.isoformat(), "date_created": "2026-01-01"}, NOW))

    def test_exact_90_day_boundary_is_allowed_but_one_second_older_is_not(self):
        cutoff = NOW - timedelta(days=90)
        self.assertIsNone(age_mismatch({"posted_date": cutoff.isoformat()}, NOW))
        self.assertIsNotNone(age_mismatch({"posted_date": (cutoff - timedelta(seconds=1)).isoformat()}, NOW))

    def test_timezone_and_epoch_milliseconds_are_supported(self):
        cutoff = NOW - timedelta(days=91)
        for value in (cutoff.timestamp(), int(cutoff.timestamp() * 1000), "2026-08-01T23:00:00-03:00"):
            with self.subTest(value=value):
                self.assertIsNotNone(age_mismatch({"posted_date": value}, NOW))

    def test_unknown_date_is_not_invented(self):
        for value in (None, "n/a", "", "yesterday"):
            self.assertIsNone(age_mismatch({"posted_date": value}, NOW))

    def test_discovery_date_is_lower_bound_when_publication_date_missing(self):
        self.assertIsNotNone(age_mismatch({"timestamp": "2026-01-01T00:00:00Z"}, NOW))
        self.assertIsNone(age_mismatch({"posted_date": NOW.isoformat(), "timestamp": "2026-01-01"}, NOW))


class SalaryRegionTests(unittest.TestCase):
    def test_local_currency_cannot_hide_behind_remote_or_worldwide_label(self):
        for location in ("Remote", "Worldwide", "LATAM"):
            for salary in ("Salary: PHP 60,000/month", "Pay: 60000 PHP", "₱60,000"):
                with self.subTest(location=location, salary=salary):
                    result = posting_mismatch({"location": location, "description": salary}, REGIONS, NOW)
                    self.assertTrue(result["deal_breaker"])
                    self.assertIn("philippines", result["reasons"][0])

    def test_php_programming_language_is_not_salary(self):
        for description in ("PHP developer", "PHP 8.3 required", "PHP 8 and Laravel", "PHP, Python, AWS", "8 PHP projects"):
            with self.subTest(description=description):
                self.assertIsNone(local_salary_currency({"description": description}))
                self.assertIsNone(posting_mismatch({"description": description}, REGIONS, NOW))

    def test_currency_metadata_survives_separate_salary_field(self):
        for job in ({"salary_currency": "PHP"}, {"salary": {"currency": "PHP", "value": 60000}}, {"salary": "PHP 60000"}):
            self.assertIsNotNone(posting_mismatch(job, REGIONS, NOW))

    def test_usd_and_eur_do_not_imply_a_work_country(self):
        for salary in ("USD 4000", "EUR 5000", "$4000", "€5000"):
            self.assertIsNone(posting_mismatch({"location": "Remote", "salary": salary}, REGIONS, NOW))

    def test_explicit_country_preference_and_alias_are_respected(self):
        job = {"location": "Remote", "salary_currency": "PHP"}
        for preference in ("Philippines", "Filipinas", "PH"):
            self.assertIsNone(posting_mismatch(job, [preference], NOW))
        self.assertIsNotNone(posting_mismatch(job, ["Worldwide"], NOW))

    def test_latam_currencies_match_latam_but_not_worldwide_alone(self):
        for code in ("ARS", "BRL", "MXN", "COP", "CLP", "UYU", "PEN"):
            with self.subTest(code=code):
                self.assertIsNone(posting_mismatch({"salary_currency": code}, REGIONS, NOW))
                self.assertIsNotNone(posting_mismatch({"salary_currency": code}, ["Worldwide"], NOW))

    def test_legacy_onlinejobs_rows_are_not_globally_remote(self):
        for job in ({"job_id": "onlinejobs:123", "location": "Remote"},
                    {"url": "https://www.onlinejobs.ph/jobseekers/job/123", "location": "Remote"}):
            self.assertIsNotNone(posting_mismatch(job, REGIONS, NOW))
            self.assertIsNone(posting_mismatch(job, ["Philippines"], NOW))

    def test_explicit_job_location_outweighs_currency_fallback(self):
        self.assertIsNone(posting_mismatch({"location": "Argentina", "salary_currency": "GBP"}, ["Argentina"], NOW))
        self.assertIsNotNone(posting_mismatch({"location": "US Remote", "description": "Join us"}, REGIONS, NOW))


if __name__ == "__main__":
    unittest.main()

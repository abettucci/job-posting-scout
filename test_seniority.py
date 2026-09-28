"""Regression checks for deterministic seniority and experience filtering."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/shared"))

from seniority import extract_requirements  # noqa: E402


class SeniorityExtractionTests(unittest.TestCase):
    def test_neutral_title_defaults_to_entry_when_no_more_than_five_years(self):
        self.assertEqual(
            extract_requirements("Software Engineer", "Requires 3+ years of professional experience"),
            {"seniority_level": "entry", "min_years_experience": 3},
        )

    def test_neutral_title_with_more_than_five_years_defaults_to_mid(self):
        self.assertEqual(
            extract_requirements("Platform Engineer", "7 years of relevant experience required"),
            {"seniority_level": "mid", "min_years_experience": 7},
        )

    def test_explicit_high_seniority_title_wins_over_years(self):
        result = extract_requirements("Senior Specialist", "Requires 2 years of experience")
        self.assertEqual(result["seniority_level"], "staff")
        self.assertEqual(result["min_years_experience"], 2)


if __name__ == "__main__":
    unittest.main()

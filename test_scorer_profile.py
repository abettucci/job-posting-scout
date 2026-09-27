"""Focused, dependency-free checks for scoring-profile prompt construction."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/shared"))
sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=object))
sys.modules.setdefault("requests", types.SimpleNamespace())

import scorer  # noqa: E402


class ScorerProfileTests(unittest.TestCase):
    def test_eligible_regions_are_visible_to_the_scorer(self):
        profile = {"must_have": ["Python"], "eligible_regions": ["Argentina", "LATAM"]}
        text = scorer._profile_to_text(profile)
        self.assertIn("Eligible work regions: Argentina, LATAM", text)

        prompt = scorer._build_prompt(
            {"title": "Backend Engineer", "company": "Acme", "location": "Argentina", "description": "Remote"},
            profile,
        )
        self.assertIn("Eligible work regions: Argentina, LATAM", prompt)
        self.assertIn("explicit technical \"must-have\"", prompt)


if __name__ == "__main__":
    unittest.main()

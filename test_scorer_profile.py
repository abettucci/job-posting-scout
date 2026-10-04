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
    def test_resume_skills_are_the_candidate_skill_source(self):
        profile = {"must_have": ["remote"]}
        resume = {"skills": {"languages": ["Python"], "frameworks": ["FastAPI"], "tools": ["AWS"], "other": ["Python"]}}

        enriched = scorer.with_resume_skills(profile, resume)

        self.assertEqual(enriched["candidate_skills"], ["Python", "FastAPI", "AWS"])
        self.assertEqual(enriched["must_have"], ["remote"])
        self.assertIn("Candidate skills from CV: Python, FastAPI, AWS", scorer._profile_to_text(enriched))

    def test_missing_required_skills_force_skip(self):
        result = scorer._normalize_result(
            {
                "score": 88,
                "deal_breaker": False,
                "missing_required_skills": ["DynamoDB", "dynamodb", "Kafka"],
                "reasons": ["✅ Python experience matches"],
                "recommendation": "APPLY",
            },
            provider="test",
        )

        self.assertTrue(result["deal_breaker"])
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertLess(result["score"], 50)
        self.assertEqual(result["missing_required_skills"], ["DynamoDB", "Kafka"])
        self.assertTrue(result["reasons"][0].startswith("❌ Required technology"))

    def test_eligible_regions_are_visible_to_the_scorer(self):
        profile = {"must_have": ["Python"], "eligible_regions": ["Argentina", "LATAM"]}
        text = scorer._profile_to_text(profile)
        self.assertIn("Eligible work regions: Argentina, LATAM", text)

        prompt = scorer._build_prompt(
            {"title": "Backend Engineer", "company": "Acme", "location": "Argentina", "description": "Remote"},
            profile,
        )
        self.assertIn("Eligible work regions: Argentina, LATAM", prompt)
        self.assertIn("Candidate skills from CV", prompt)


if __name__ == "__main__":
    unittest.main()

"""Network-free checks for the resume tailoring integrity guard."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/api"))

from routers._resume_integrity import (  # noqa: E402
    incomplete_tailored_payload_reason,
    resume_has_renderable_content,
    select_hidden_keywords,
)


ORIGINAL = {
    "name": "Agustin Ignacio Bettucci",
    "email": "agustin@example.com",
    "phone": "",
    "location": "Buenos Aires, Argentina",
    "linkedin": "linkedin.com/in/agustin",
    "github": "github.com/agustin",
    "website": "",
    "summary": "Data engineer with production cloud-platform experience.",
    "experience": [{"title": "Data Engineer", "company": "Acme", "bullets": ["Built pipelines"]}],
    "education": [{"degree": "Engineering", "school": "ITBA"}],
    "skills": {"languages": ["Python"], "frameworks": [], "tools": ["AWS"], "other": []},
    "projects": [{"name": "ETL", "description": "Automated pipeline"}],
    "certifications": [],
}


class ResumeIntegrityTests(unittest.TestCase):
    def test_rejects_name_only_tailoring_response(self):
        self.assertIn("omitted", incomplete_tailored_payload_reason(ORIGINAL, {"name": ORIGINAL["name"]}))

    def test_accepts_complete_tailoring_response(self):
        tailored = {**ORIGINAL, "summary": "Cloud data engineer focused on AWS reliability."}
        self.assertIsNone(incomplete_tailored_payload_reason(ORIGINAL, tailored))

    def test_detects_non_renderable_resume(self):
        self.assertFalse(resume_has_renderable_content({"name": "Agustin", "skills": {}}))
        self.assertFalse(resume_has_renderable_content({"experience": [{"title": "", "bullets": []}]}))
        self.assertTrue(resume_has_renderable_content(ORIGINAL))

    def test_rejects_name_only_parsing_response(self):
        self.assertFalse(resume_has_renderable_content({"name": ORIGINAL["name"], "skills": {}}))

    def test_hidden_keywords_only_use_terms_from_original_resume(self):
        original = {**ORIGINAL, "summary": "Built APIs with Python and AWS Lambda.", "skills": {"tools": ["Docker"]}}
        tailored = {**original, "summary": "Backend engineer.", "skills": {"tools": ["Docker"]}}
        job = "Looking for Python, AWS, Docker, Kubernetes and C# experience."
        self.assertEqual(select_hidden_keywords(original, tailored, job), ["Python", "AWS"])

    def test_hidden_keywords_skip_terms_already_visible(self):
        original = {**ORIGINAL, "summary": "Python and Terraform."}
        tailored = {**original, "summary": "Engineer.", "skills": {"tools": ["Terraform"]}}
        self.assertEqual(select_hidden_keywords(original, tailored, "Python and Terraform required."), ["Python"])

    def test_hidden_keywords_respect_word_boundaries(self):
        original = {**ORIGINAL, "summary": "Worked with Golang and Java."}
        tailored = {**original, "summary": "Engineer."}
        self.assertEqual(select_hidden_keywords(original, tailored, "Go and Java role"), ["Java"])


if __name__ == "__main__":
    unittest.main()

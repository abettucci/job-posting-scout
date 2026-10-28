"""Tests for runtime configuration sourced from Lambda environment variables."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/shared"))

import config  # noqa: E402


class ConfigEnvironmentTests(unittest.TestCase):
    def test_reads_static_credentials_from_environment(self):
        values = {
            "TELEGRAM_BOT_TOKEN": "telegram-test",
            "WAWEB_SIDECAR_URL": "https://sidecar.example",
            "WAWEB_SHARED_SECRET": "wa-test",
            "GEMINI_API_KEY": "gemini-test",
            "GROQ_API_KEY": "groq-test",
            "OPENROUTER_API_KEY": "openrouter-test",
            "ANTHROPIC_API_KEY": "anthropic-test",
            "OMNIROUTE_BASE_URL": "https://omniroute.example",
            "OMNIROUTE_API_KEY": "omni-test",
            "OMNIROUTE_MODEL": "auto",
            "JWT_SECRET": "jwt-test",
            "LINKEDIN_EMAIL": "linkedin@example.test",
            "LINKEDIN_PASSWORD": "linkedin-test",
        }
        with patch.dict("os.environ", values, clear=True):
            cfg = config.get_config()

        for name, value in values.items():
            self.assertEqual(getattr(cfg, name.lower()), value)

    def test_missing_optional_keys_default_to_empty_values(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = config.get_config()

        self.assertEqual(cfg.gemini_api_key, "")
        self.assertEqual(cfg.groq_api_key, "")
        self.assertEqual(cfg.openrouter_api_key, "")
        self.assertEqual(cfg.anthropic_api_key, "")
        self.assertEqual(cfg.omniroute_model, "auto")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for the free-first AI provider cascade."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent / "aws/lambdas/shared"))
sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=object))
if not hasattr(sys.modules.get("requests"), "post"):
    sys.modules["requests"] = types.SimpleNamespace(
        post=MagicMock(),
        HTTPError=type("HTTPError", (Exception,), {}),
    )

import ai_router  # noqa: E402

if not hasattr(ai_router.requests, "post"):
    ai_router.requests.post = MagicMock()
if not hasattr(ai_router.requests, "HTTPError"):
    ai_router.requests.HTTPError = type("HTTPError", (Exception,), {})


class _Response:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class AIRouterTests(unittest.TestCase):
    def test_uses_gemini_first_when_it_is_configured(self):
        router = ai_router.AIProviderRouter(
            gemini_api_key="test-gemini", gemini_free_tier_confirmed=True
        )
        with patch.object(ai_router.requests, "post", return_value=_Response({
            "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}], "role": "model"}}]
        })) as post:
            response = router.messages.create(
                model="ignored",
                max_tokens=64,
                system="Return only JSON.",
                messages=[{"role": "user", "content": "Hello"}],
            )

        self.assertEqual(router.last_provider, "gemini")
        self.assertEqual(response.content[0].text, '{"ok":true}')
        self.assertEqual(post.call_args.args[0], ai_router._GEMINI_URL.format(model="gemini-3.8-flash"))
        self.assertEqual(post.call_args.kwargs["json"]["generationConfig"]["responseMimeType"], "application/json")

    def test_falls_through_free_providers_before_haiku(self):
        anthropic_response = types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text='{"ok":true}')],
            stop_reason="end_turn",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        anthropic_client = types.SimpleNamespace(
            messages=types.SimpleNamespace(create=MagicMock(return_value=anthropic_response))
        )
        fake_table = types.SimpleNamespace(update_item=MagicMock())
        fake_boto3 = types.SimpleNamespace(
            resource=MagicMock(return_value=types.SimpleNamespace(Table=MagicMock(return_value=fake_table)))
        )
        with patch.dict(sys.modules, {"boto3": fake_boto3}), patch.object(ai_router.requests, "post", side_effect=[
            _Response(status_code=429),
            _Response(status_code=503),
        ]) as post, patch.object(ai_router, "Anthropic", return_value=anthropic_client):
            router = ai_router.AIProviderRouter(
                gemini_api_key="g",
                groq_api_key="q",
                openrouter_api_key="o",
                anthropic_api_key="a",
                gemini_free_tier_confirmed=True,
                usage_table_name="test-usage",
            )
            response = router.messages.create(
                max_tokens=32,
                timeout=10,
                system="Return JSON",
                messages=[{"role": "user", "content": "test"}],
            )

        self.assertEqual(router.last_provider, "anthropic")
        self.assertEqual(response.content[0].text, '{"ok":true}')
        self.assertEqual(
            [call.args[0] for call in post.call_args_list],
            [
                ai_router._GEMINI_URL.format(model=ai_router._GEMINI_MODEL),
                ai_router._OPENROUTER_URL,
            ],
        )
        anthropic_client.messages.create.assert_called_once()
        self.assertEqual(anthropic_client.messages.create.call_args.kwargs["model"], "claude-haiku-5-5")
        self.assertEqual(fake_table.update_item.call_count, 2)

    def test_gemini_is_skipped_unless_free_tier_is_explicitly_confirmed(self):
        router = ai_router.AIProviderRouter(gemini_api_key="g")
        with self.assertRaises(ai_router.AIProviderUnavailableError):
            router.messages.create(messages=[{"role": "user", "content": "Hello"}], max_tokens=10)

    def test_paid_fallback_fails_closed_without_usage_table(self):
        anthropic_response = types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="ok")], stop_reason="end_turn"
        )
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=MagicMock(return_value=anthropic_response)))
        with patch.object(ai_router, "Anthropic", return_value=client):
            router = ai_router.AIProviderRouter(anthropic_api_key="a")
            with self.assertRaises(ai_router.AIProviderUnavailableError):
                router.messages.create(system="write text", messages=[{"role": "user", "content": "hi"}])
        client.messages.create.assert_not_called()

    def test_skips_missing_providers(self):
        router = ai_router.AIProviderRouter()
        with self.assertRaises(ai_router.AIProviderUnavailableError):
            router.messages.create(messages=[{"role": "user", "content": "Hello"}], max_tokens=10)


if __name__ == "__main__":
    unittest.main()

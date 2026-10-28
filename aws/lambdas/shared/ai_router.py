"""Cost-aware provider routing for Anthropic-compatible text generation calls."""
from __future__ import annotations

import logging
import json
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import requests
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-3.8-flash"
_GROQ_MODEL = "openai/gpt-oss-120b"
_OPENROUTER_MODEL = "openrouter/free"
_ANTHROPIC_MODEL = "claude-haiku-5-5"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# USD per million tokens. Keep this conservative and revisit when providers
# change prices; paid requests are reserved against a daily DynamoDB ceiling.
_PAID_RATES = {
    "anthropic": (0.10, 0.50),
    "groq": (0.15, 0.60),
}


class AIProviderUnavailableError(RuntimeError):
    """No configured AI provider completed the request."""


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type", "text") == "text":
                    parts.append(str(item.get("text") or ""))
            elif getattr(item, "type", "text") == "text":
                parts.append(str(getattr(item, "text", "") or ""))
        return "".join(parts)
    return ""


def _is_json_request(system: str, messages: List[Dict[str, Any]]) -> bool:
    text = system + "\n" + "\n".join(_as_text(message.get("content")) for message in messages)
    return "json" in text.casefold()


class _Messages:
    def __init__(self, router: "AIProviderRouter"):
        self._router = router

    def create(self, **kwargs: Any) -> Any:
        return self._router.create(**kwargs)


class AIProviderRouter:
    """Drop-in subset of Anthropic's messages API with a deterministic cascade.

    Order: explicitly confirmed Gemini free tier, OpenRouter Free, then paid
    Haiku followed by Groq. Groq is treated as paid because its configured
    model has a published per-token price. Providers without keys are skipped. Errors are
    logged without prompts, resumes, API keys, or upstream response bodies.
    """

    def __init__(
        self,
        *,
        gemini_api_key: str = "",
        groq_api_key: str = "",
        openrouter_api_key: str = "",
        anthropic_api_key: str = "",
        daily_paid_budget_usd: float = 1.0,
        usage_table_name: str = "",
        gemini_free_tier_confirmed: bool = False,
    ):
        self._gemini_api_key = gemini_api_key
        self._groq_api_key = groq_api_key
        self._openrouter_api_key = openrouter_api_key
        self._daily_paid_budget_usd = max(0.0, float(daily_paid_budget_usd))
        self._usage_table_name = usage_table_name
        self._gemini_free_tier_confirmed = gemini_free_tier_confirmed
        self._anthropic = (
            Anthropic(api_key=anthropic_api_key, max_retries=0)
            if anthropic_api_key
            else None
        )
        self.messages = _Messages(self)
        self.last_provider: Optional[str] = None
        self.last_model: Optional[str] = None

    def create(self, **kwargs: Any) -> Any:
        self.last_provider = None
        self.last_model = None
        requested_timeout = max(1.0, float(kwargs.pop("timeout", 30.0) or 30.0))
        active = []
        if self._gemini_api_key and self._gemini_free_tier_confirmed:
            active.append(("gemini", _GEMINI_MODEL))
        if self._openrouter_api_key:
            active.append(("openrouter", _OPENROUTER_MODEL))
        if self._anthropic:
            active.append(("anthropic", _ANTHROPIC_MODEL))
        if self._groq_api_key:
            active.append(("groq", _GROQ_MODEL))
        if not active:
            raise AIProviderUnavailableError("no AI provider configured")

        # Keep API requests within the synchronous gateway budget, while still
        # giving each configured provider a chance to respond.
        total_budget = min(28.0, requested_timeout * len(active))
        deadline = time.monotonic() + total_budget
        errors = []
        for index, (provider, model) in enumerate(active):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append(f"{provider}:deadline")
                break
            providers_left = len(active) - index
            provider_timeout = max(1.0, min(requested_timeout, remaining / providers_left))
            reservation = None
            try:
                if provider in _PAID_RATES:
                    reservation = self._reserve_paid_budget(provider, kwargs)
                if provider == "gemini":
                    result = self._call_gemini(model, provider_timeout, kwargs)
                elif provider in {"groq", "openrouter"}:
                    result = self._call_openai_compatible(provider, model, provider_timeout, kwargs)
                else:
                    anthropic_kwargs = dict(kwargs)
                    anthropic_kwargs["model"] = model
                    anthropic_kwargs["timeout"] = provider_timeout
                    result = self._anthropic.messages.create(**anthropic_kwargs)
                text = _as_text(getattr(result, "content", []))
                if _is_json_request(_as_text(kwargs.get("system") or ""), kwargs.get("messages") or []):
                    try:
                        json.loads(text)
                    except (TypeError, ValueError):
                        raise ValueError("provider returned malformed JSON") from None
                self.last_provider = provider
                self.last_model = model
                if reservation:
                    self._settle_paid_budget(reservation, provider, kwargs, result)
                logger.info("AI provider succeeded provider=%s model=%s", provider, model)
                return result
            except Exception as exc:
                errors.append(f"{provider}:{type(exc).__name__}")
                logger.warning("AI provider failed provider=%s error=%s", provider, type(exc).__name__)

        raise AIProviderUnavailableError(", ".join(errors) or "provider deadline exceeded")

    def _call_gemini(self, model: str, timeout: float, kwargs: Dict[str, Any]) -> Any:
        messages = kwargs.get("messages") or []
        system = _as_text(kwargs.get("system") or "")
        contents = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            content = _as_text(message.get("content"))
            if content:
                contents.append({"role": role, "parts": [{"text": content}]})
        if not contents:
            raise ValueError("empty message")
        generation_config: Dict[str, Any] = {"maxOutputTokens": int(kwargs.get("max_tokens") or 1024)}
        if _is_json_request(system, messages):
            generation_config["responseMimeType"] = "application/json"
        body: Dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        response = requests.post(
            _GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": self._gemini_api_key, "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
        if not text.strip():
            raise ValueError("Gemini returned empty text")
        finish_reason = str(candidate.get("finishReason") or "").casefold()
        stop_reason = "max_tokens" if finish_reason in {"max_tokens", "max_tokens_reached"} else "end_turn"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)

    def _call_openai_compatible(
        self, provider: str, model: str, timeout: float, kwargs: Dict[str, Any]
    ) -> Any:
        messages = kwargs.get("messages") or []
        system = _as_text(kwargs.get("system") or "")
        chat_messages = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        for message in messages:
            content = _as_text(message.get("content"))
            if content:
                chat_messages.append({"role": message.get("role", "user"), "content": content})
        if not chat_messages:
            raise ValueError("empty message")
        body: Dict[str, Any] = {
            "model": model,
            "max_tokens": int(kwargs.get("max_tokens") or 1024),
            "messages": chat_messages,
        }
        if _is_json_request(system, messages):
            body["response_format"] = {"type": "json_object"}
        if provider == "groq":
            url, api_key = _GROQ_URL, self._groq_api_key
        else:
            url, api_key = _OPENROUTER_URL, self._openrouter_api_key
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://job-posting-scout.vercel.app"
            headers["X-Title"] = "Job Posting Scout"
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"{provider} returned no choices")
        choice = choices[0]
        content = _as_text((choice.get("message") or {}).get("content"))
        if not content.strip():
            raise ValueError(f"{provider} returned empty text")
        stop_reason = "max_tokens" if choice.get("finish_reason") == "length" else "end_turn"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=content)],
            stop_reason=stop_reason,
            usage=payload.get("usage") or {},
        )

    def _reserve_paid_budget(self, provider: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically reserve a conservative daily cost estimate before paid use.

        Fail closed when the budget table isn't configured/reachable. Failed
        upstream calls retain the reservation because a timeout can happen
        after a provider has processed and billed a request.
        """
        if not self._usage_table_name or self._daily_paid_budget_usd <= 0:
            raise AIProviderUnavailableError("paid AI budget is disabled")
        import boto3
        from datetime import datetime, timedelta, timezone

        prompt_chars = len(_as_text(kwargs.get("system") or ""))
        prompt_chars += sum(len(_as_text(message.get("content"))) for message in kwargs.get("messages") or [])
        estimated_input_tokens = int(prompt_chars / 2.5) + 1
        max_output_tokens = int(kwargs.get("max_tokens") or 1024)
        input_rate, output_rate = _PAID_RATES[provider]
        estimated_usd = (estimated_input_tokens * input_rate + max_output_tokens * output_rate) / 1_000_000
        reserve_microusd = max(1, int(estimated_usd * 1_000_000 + 0.999999))
        budget_microusd = int(self._daily_paid_budget_usd * 1_000_000)
        if reserve_microusd > budget_microusd:
            raise AIProviderUnavailableError("paid AI request exceeds the daily budget")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = boto3.resource("dynamodb").Table(self._usage_table_name)
        try:
            table.update_item(
                Key={"day": day},
                UpdateExpression="SET #ttl = if_not_exists(#ttl, :ttl) ADD committed_microusd :reserve, reserved_microusd :reserve",
                ConditionExpression="attribute_not_exists(committed_microusd) OR committed_microusd <= :remaining",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":ttl": int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp()),
                    ":reserve": reserve_microusd,
                    ":remaining": budget_microusd - reserve_microusd,
                },
            )
        except Exception as exc:
            logger.warning("Paid AI budget reservation denied provider=%s error=%s", provider, type(exc).__name__)
            raise AIProviderUnavailableError("paid AI daily budget exhausted or unavailable") from None
        return {"table": table, "day": day, "reserved_microusd": reserve_microusd}

    def _settle_paid_budget(self, reservation: Dict[str, Any], provider: str, kwargs: Dict[str, Any], result: Any) -> None:
        usage = getattr(result, "usage", None) or {}
        if not isinstance(usage, dict):
            usage = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
        if input_tokens is None or output_tokens is None:
            # Keep the full conservative reservation if the provider omits usage.
            logger.info("Paid AI usage unavailable provider=%s; keeping cost reservation", provider)
            return
        input_rate, output_rate = _PAID_RATES[provider]
        actual_microusd = int((int(input_tokens) * input_rate + int(output_tokens) * output_rate) + 0.999999)
        reserved = reservation["reserved_microusd"]
        try:
            reservation["table"].update_item(
                Key={"day": reservation["day"]},
                UpdateExpression="ADD committed_microusd :commit_adjustment, reserved_microusd :refund, spent_microusd :spent",
                ExpressionAttributeValues={
                    ":commit_adjustment": reserved - actual_microusd,
                    ":refund": -reserved,
                    ":spent": actual_microusd,
                },
            )
            logger.info(
                "Paid AI usage provider=%s input_tokens=%s output_tokens=%s estimated_usd=%.6f",
                provider, input_tokens, output_tokens, actual_microusd / 1_000_000,
            )
        except Exception as exc:
            # The initial reservation remains counted, so a settlement outage
            # cannot silently free budget that may already have been spent.
            logger.warning("Paid AI usage settlement failed provider=%s error=%s", provider, type(exc).__name__)


def build_ai_client(config: Any) -> AIProviderRouter:
    """Build the common provider cascade from Lambda configuration."""
    return AIProviderRouter(
        gemini_api_key=getattr(config, "gemini_api_key", ""),
        groq_api_key=getattr(config, "groq_api_key", ""),
        openrouter_api_key=getattr(config, "openrouter_api_key", ""),
        anthropic_api_key=getattr(config, "anthropic_api_key", ""),
        daily_paid_budget_usd=getattr(config, "ai_paid_daily_budget_usd", 1.0),
        usage_table_name=getattr(config, "ai_usage_table", ""),
        gemini_free_tier_confirmed=getattr(config, "gemini_free_tier_confirmed", False),
    )
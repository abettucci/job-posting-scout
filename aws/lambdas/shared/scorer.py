"""Claude Haiku job scorer. Returns a structured score for a job against a user profile."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from anthropic import Anthropic
import requests

logger = logging.getLogger(__name__)

_SYSTEM = """You are a recruiter assistant. Given a candidate profile and a job description,
score how well the job matches the candidate. Respond ONLY with valid JSON, no markdown, no explanation."""

_PROMPT = """\
Candidate profile:
{profile_text}

---
Job:
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

---
Return JSON with this exact structure:
{{
  "score": <integer 0-100>,
  "deal_breaker": <true if any deal_breaker condition is met, false otherwise>,
  "reasons": ["<short reason 1>", "<short reason 2>", ...],
  "summary": "<3-line plain-text summary of the role>",
  "recommendation": "<APPLY | SKIP | MAYBE>",
  "notification_location_allowed": <true | false>,
  "notification_location_reason": "<short explanation>"
}}

Rules:
- score 0-100: 100 = perfect match on must_have + nice_to_have + prefer
- deal_breaker = true if any deal_breaker from the profile is present (overrides score)
- reasons: max 5 bullet points, each starting with ✅ (match) or ❌ (mismatch)
- summary: 3 short lines describing the role (no opinions)
- recommendation: APPLY if score >= 70 and not deal_breaker, SKIP if score < 50 or deal_breaker, MAYBE otherwise
- notification_location_allowed is a strict delivery rule, independent of score:
  set true only when the posting is explicitly worldwide/global remote, or
  explicitly Argentina/Buenos Aires. Read both Location and Description.
  Set false for any country/region-specific remote role (for example
  “remote in Poland”, “remote USA”, “US only”) and for ambiguous locations.
  A bare “Remote” is allowed only when the posting does not state or imply a
  country/region restriction elsewhere in its description.
"""


def _profile_to_text(profile: Dict) -> str:
    lines = []
    if profile.get("must_have"):
        lines.append("Must have: " + ", ".join(profile["must_have"]))
    if profile.get("nice_to_have"):
        lines.append("Nice to have: " + ", ".join(profile["nice_to_have"]))
    if profile.get("deal_breakers"):
        lines.append("Deal breakers: " + ", ".join(profile["deal_breakers"]))
    if profile.get("prefer"):
        lines.append("Prefer: " + ", ".join(profile["prefer"]))
    return "\n".join(lines)


def _extract_json(raw: str) -> Dict[str, Any]:
    """Pull a JSON object out of a model response that may be wrapped in a
    markdown fence and/or preceded/followed by stray prose.

    Haiku mostly obeys "respond ONLY with JSON", but occasionally prepends a
    sentence or wraps the object in ```json fences (or both), which made the
    original strict `json.loads(raw.strip())` fail with
    "Expecting value: line 1 column 1 (char 0)" on otherwise-valid responses.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("empty response from model")

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost {...} span, in case the model added a
    # leading/trailing sentence around the JSON object without a fence.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in response: {raw[:200]!r}")
    return json.loads(raw[start : end + 1])


class ScoringUnavailableError(RuntimeError):
    """No configured scoring provider could complete this request."""


class ScoringRouter:
    """Use the primary scorer first, then an owner-configured compatible fallback.

    The fallback is intentionally opt-in. It does not create accounts, rotate
    identities, or attempt to bypass any provider's quota or usage policy.
    """

    def __init__(
        self,
        anthropic_api_key: str,
        fallback_base_url: str = "",
        fallback_api_key: str = "",
        fallback_model: str = "auto",
    ):
        self._anthropic = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None
        self._fallback_base_url = fallback_base_url.rstrip("/")
        self._fallback_api_key = fallback_api_key
        self._fallback_model = fallback_model

    @property
    def fallback_enabled(self) -> bool:
        return bool(self._fallback_base_url and self._fallback_api_key)

    def score(self, job: Dict, profile: Dict) -> Dict[str, Any]:
        prompt = _build_prompt(job, profile)
        errors: list[str] = []

        if self._anthropic:
            try:
                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    system=_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                if response.stop_reason == "max_tokens":
                    logger.warning("Primary scoring response truncated for %r", job.get("title"))
                return _normalize_result(_extract_json(response.content[0].text), provider="anthropic")
            except Exception as exc:
                errors.append(f"anthropic:{type(exc).__name__}")
                logger.warning("Primary scorer unavailable for %r: %s", job.get("title"), type(exc).__name__)

        if self.fallback_enabled:
            try:
                return self._score_openai_compatible(prompt)
            except Exception as exc:
                errors.append(f"fallback:{type(exc).__name__}")
                logger.warning("Fallback scorer unavailable for %r: %s", job.get("title"), type(exc).__name__)

        detail = ", ".join(errors) if errors else "no scoring provider configured"
        raise ScoringUnavailableError(detail)

    def complete_json(self, system: str, prompt: str, max_tokens: int = 900) -> Dict[str, Any]:
        """Run a small structured assistant task through the same failover chain.

        Keeping this beside scoring means interactive discovery receives the
        same graceful provider fallback as the scheduled scraper, without any
        credential rotation or hidden extra provider account.
        """
        errors: list[str] = []
        if self._anthropic:
            try:
                response = self._anthropic.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _extract_json(response.content[0].text)
            except Exception as exc:
                errors.append(f"anthropic:{type(exc).__name__}")
                logger.warning("Primary structured assistant unavailable: %s", type(exc).__name__)

        if self.fallback_enabled:
            try:
                endpoint = self._fallback_base_url
                if not endpoint.endswith("/chat/completions"):
                    endpoint = f"{endpoint}/chat/completions" if endpoint.endswith("/v1") else f"{endpoint}/v1/chat/completions"
                response = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self._fallback_api_key}", "Content-Type": "application/json"},
                    json={"model": self._fallback_model, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                    timeout=30,
                )
                response.raise_for_status()
                return _extract_json(response.json()["choices"][0]["message"]["content"])
            except Exception as exc:
                errors.append(f"fallback:{type(exc).__name__}")
                logger.warning("Fallback structured assistant unavailable: %s", type(exc).__name__)

        raise ScoringUnavailableError(", ".join(errors) if errors else "no scoring provider configured")

    def _score_openai_compatible(self, prompt: str) -> Dict[str, Any]:
        # OmniRoute and many self-hosted gateways expose this standard path.
        endpoint = self._fallback_base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = (
                f"{endpoint}/chat/completions"
                if endpoint.endswith("/v1")
                else f"{endpoint}/v1/chat/completions"
            )
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self._fallback_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._fallback_model,
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=45,
        )
        response.raise_for_status()
        body = response.json()
        raw = body["choices"][0]["message"]["content"]
        return _normalize_result(_extract_json(raw), provider="fallback")


def _build_prompt(job: Dict, profile: Dict) -> str:
    return _PROMPT.format(
        profile_text=_profile_to_text(profile),
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "")[:4000]),
    )


def _normalize_result(result: Dict[str, Any], provider: str) -> Dict[str, Any]:
    result["score"] = max(0, min(100, int(result.get("score", 0))))
    result["deal_breaker"] = bool(result.get("deal_breaker", False))
    result.setdefault("reasons", [])
    result.setdefault("summary", "")
    result.setdefault("recommendation", "MAYBE")
    # Fail closed: a malformed or older model response must never turn an
    # ambiguous location into a Telegram notification.
    result["notification_location_allowed"] = result.get("notification_location_allowed") is True
    result["notification_location_reason"] = str(
        result.get("notification_location_reason", "")
    )[:240]
    result["scoring_provider"] = provider
    return result


def score_job(router: ScoringRouter, job: Dict, profile: Dict) -> Dict[str, Any]:
    """Score through the configured routing chain or raise when it is unavailable."""
    return router.score(job, profile)

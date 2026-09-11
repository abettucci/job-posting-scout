"""Claude Haiku job scorer. Returns a structured score for a job against a user profile."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from anthropic import Anthropic

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
  "recommendation": "<APPLY | SKIP | MAYBE>"
}}

Rules:
- score 0-100: 100 = perfect match on must_have + nice_to_have + prefer
- deal_breaker = true if any deal_breaker from the profile is present (overrides score)
- reasons: max 5 bullet points, each starting with ✅ (match) or ❌ (mismatch)
- summary: 3 short lines describing the role (no opinions)
- recommendation: APPLY if score >= 70 and not deal_breaker, SKIP if score < 50 or deal_breaker, MAYBE otherwise
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


def score_job(client: Anthropic, job: Dict, profile: Dict) -> Dict[str, Any]:
    prompt = _PROMPT.format(
        profile_text=_profile_to_text(profile),
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "")[:4000]),  # cap tokens
    )

    raw = None
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "max_tokens":
            logger.warning(f"score_job response truncated (max_tokens) for '{job.get('title')}'")
        raw = response.content[0].text
        result = _extract_json(raw)
        # Normalize
        result["score"] = max(0, min(100, int(result.get("score", 0))))
        result["deal_breaker"] = bool(result.get("deal_breaker", False))
        result.setdefault("reasons", [])
        result.setdefault("summary", "")
        result.setdefault("recommendation", "MAYBE")
        return result
    except Exception as e:
        logger.error(
            f"score_job error for '{job.get('title')}': {e} — raw response: {raw[:500] if raw else None!r}"
        )
        return {
            "score": 0,
            "deal_breaker": False,
            "reasons": ["Error al puntuar"],
            "summary": "",
            "recommendation": "SKIP",
        }

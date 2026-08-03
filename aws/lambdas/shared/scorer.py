"""Claude Haiku job scorer. Returns a structured score for a job against a user profile."""

from __future__ import annotations

import json
import logging
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


def score_job(client: Anthropic, job: Dict, profile: Dict) -> Dict[str, Any]:
    prompt = _PROMPT.format(
        profile_text=_profile_to_text(profile),
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "")[:4000]),  # cap tokens
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        # Normalize
        result["score"] = max(0, min(100, int(result.get("score", 0))))
        result["deal_breaker"] = bool(result.get("deal_breaker", False))
        result.setdefault("reasons", [])
        result.setdefault("summary", "")
        result.setdefault("recommendation", "MAYBE")
        return result
    except Exception as e:
        logger.error(f"score_job error for '{job.get('title')}': {e}")
        return {
            "score": 0,
            "deal_breaker": False,
            "reasons": ["Error al puntuar"],
            "summary": "",
            "recommendation": "SKIP",
        }

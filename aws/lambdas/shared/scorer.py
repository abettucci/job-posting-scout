"""Claude Haiku job scorer. Returns a structured score for a job against a user profile."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from ai_router import AIProviderRouter, AIProviderUnavailableError

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
  "missing_required_skills": ["<explicit required technical skill not evidenced by the CV>", ...],
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
- "Eligible work regions" lists where the candidate can work remotely. Treat an
  explicit job location that matches one of those regions as a positive
  availability match; never say the candidate's location preference is
  unspecified when that field is present.
- "Candidate skills from CV" is the source of truth for technologies the
  candidate has actually listed. Compare every explicit technical requirement
  marked must-have, required, mandatory, essential, or minimum qualification
  against that list. Put every missing technology in missing_required_skills.
  Do not include nice-to-have or preferred technologies in that array.
- If missing_required_skills is non-empty, set deal_breaker=true,
  recommendation=SKIP, score below 50, and include a ❌ reason. Never infer
  that a generic backend/Python match implies C#, .NET, EF Core, or another
  distinct required stack. Do not report missing skills when the candidate has
  no saved CV skills.
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
    if profile.get("candidate_skills"):
        lines.append("Candidate skills from CV: " + ", ".join(profile["candidate_skills"]))
    if profile.get("must_have"):
        lines.append("Must have: " + ", ".join(profile["must_have"]))
    if profile.get("nice_to_have"):
        lines.append("Nice to have: " + ", ".join(profile["nice_to_have"]))
    if profile.get("deal_breakers"):
        lines.append("Deal breakers: " + ", ".join(profile["deal_breakers"]))
    if profile.get("prefer"):
        lines.append("Prefer: " + ", ".join(profile["prefer"]))
    if profile.get("eligible_regions"):
        lines.append("Eligible work regions: " + ", ".join(profile["eligible_regions"]))
    if profile.get("target_seniorities"):
        lines.append("Target seniority levels: " + ", ".join(profile["target_seniorities"]))
    if profile.get("max_required_years"):
        lines.append(f"Maximum required experience: {profile['max_required_years']} years")
    return "\n".join(lines)


def with_resume_skills(profile: Dict[str, Any], resume: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a scoring profile enriched only with skills the candidate saved.

    Job preferences (``must_have``, ``nice_to_have`` and ``prefer``) describe
    what the person wants from a role. They must not be confused with evidence
    of experience. The saved resume is the single source of truth for the
    latter, which lets the scorer reject an explicitly-required technology the
    candidate has not claimed without asking them to maintain the same list in
    two places.
    """
    enriched = dict(profile or {})
    skills = (resume or {}).get("skills")
    if not isinstance(skills, dict):
        enriched["candidate_skills"] = []
        return enriched

    seen = set()
    candidate_skills = []
    for group in ("languages", "frameworks", "tools", "other"):
        values = skills.get(group, [])
        if not isinstance(values, list):
            continue
        for value in values:
            name = str(value or "").strip()
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                candidate_skills.append(name)
    enriched["candidate_skills"] = candidate_skills
    return enriched


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
    """Use configured free providers first and Haiku only as the final fallback."""

    def __init__(
        self,
        anthropic_api_key: str = "",
        fallback_base_url: str = "",
        fallback_api_key: str = "",
        fallback_model: str = "auto",
        gemini_api_key: str = "",
        groq_api_key: str = "",
        openrouter_api_key: str = "",
        daily_paid_budget_usd: float = 1.0,
        usage_table_name: str = "",
        gemini_free_tier_confirmed: bool = False,
    ):
        # Legacy OmniRoute parameters remain accepted for deployment compatibility,
        # but do not change the requested free-first order.
        self._ai = AIProviderRouter(
            gemini_api_key=gemini_api_key,
            groq_api_key=groq_api_key,
            openrouter_api_key=openrouter_api_key,
            anthropic_api_key=anthropic_api_key,
            daily_paid_budget_usd=daily_paid_budget_usd,
            usage_table_name=usage_table_name,
            gemini_free_tier_confirmed=gemini_free_tier_confirmed,
        )

    @property
    def fallback_enabled(self) -> bool:
        return bool(self._ai._gemini_api_key or self._ai._groq_api_key or self._ai._openrouter_api_key)

    def score(self, job: Dict, profile: Dict) -> Dict[str, Any]:
        prompt = _build_prompt(job, profile)
        try:
            response = self._ai.messages.create(
                max_tokens=1024,
                timeout=18.0,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            if response.stop_reason == "max_tokens":
                logger.warning("Scoring response truncated for %r", job.get("title"))
            return _normalize_result(
                _extract_json(response.content[0].text),
                provider=self._ai.last_provider or "unknown",
            )
        except Exception as exc:
            detail = str(exc) if isinstance(exc, AIProviderUnavailableError) else type(exc).__name__
            logger.warning("Scoring request unavailable: %s", detail)
            raise ScoringUnavailableError(detail) from None

    def complete_json(self, system: str, prompt: str, max_tokens: int = 900) -> Dict[str, Any]:
        """Run a small structured assistant task through the same failover chain.

        Keeping this beside scoring means interactive discovery receives the
        same graceful provider fallback as the scheduled scraper, without any
        credential rotation or hidden extra provider account.
        """
        try:
            response = self._ai.messages.create(
                max_tokens=max_tokens,
                timeout=18.0,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return _extract_json(response.content[0].text)
        except Exception as exc:
            detail = str(exc) if isinstance(exc, AIProviderUnavailableError) else type(exc).__name__
            raise ScoringUnavailableError(detail) from None


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
    missing_required_skills = result.get("missing_required_skills", [])
    if not isinstance(missing_required_skills, list):
        missing_required_skills = []
    seen_skills = set()
    normalized_missing_skills = []
    for value in missing_required_skills:
        skill = str(value or "").strip()
        if not skill or skill.casefold() in seen_skills:
            continue
        seen_skills.add(skill.casefold())
        normalized_missing_skills.append(skill)
        if len(normalized_missing_skills) == 12:
            break
    result["missing_required_skills"] = normalized_missing_skills
    reasons = result.get("reasons", [])
    result["reasons"] = reasons if isinstance(reasons, list) else []
    if result["missing_required_skills"]:
        result["deal_breaker"] = True
        result["score"] = min(result["score"], 49)
        result["recommendation"] = "SKIP"
        missing_reason = "❌ Required technology not listed in your CV: " + ", ".join(result["missing_required_skills"])
        if not any("required technology not listed" in str(reason).casefold() for reason in result["reasons"]):
            result["reasons"] = [missing_reason, *result["reasons"]][:5]
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
"""Shared seniority vocabulary for multi-board searches and job-posting
requirement extraction.

Single source of truth for the API's search validation (routers/searches.py),
the profile's seniority preference (routers/profile.py), the scraper's
LinkedIn URL builder, and its posting-text extractor (scraper/handler.py), so
none of these can drift out of sync on valid values or LinkedIn's filter codes.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

# Ordered for display in a dropdown, junior → senior. LinkedIn's own "Mid-Senior
# level" bucket deliberately covers both mid-level and IC "Senior" titles —
# Director/Executive are reserved for actual management/exec titles, not senior
# ICs — and extract_requirements() below follows that same convention.
SENIORITY_LEVELS = ["internship", "entry", "associate", "mid_senior", "director", "executive"]

# LinkedIn Jobs Search "Experience level" filter codes (the f_E query param).
# This is the only one of the multi-board sources with a native, structured
# seniority filter — RemoteOK/WorkingNomads/Remotive/Arbeitnow have no such
# field, so seniority is not applied to them (see handler.py comment).
SENIORITY_TO_LINKEDIN_F_E = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}

# Ordered most-specific-first so e.g. "Director of Engineering" matches
# "director" before the broader "mid_senior" patterns get a chance to match on
# an unrelated "senior" substring elsewhere in the same title.
_SENIORITY_PATTERNS = [
    ("executive", re.compile(r"\b(chief\s+\w+\s+officer|cto|ceo|cfo|coo|president)\b", re.I)),
    ("director", re.compile(r"\b(director|vp|vice\s+president|head\s+of)\b", re.I)),
    ("internship", re.compile(r"\b(intern(ship)?|trainee|new\s+grad|graduate\s+program)\b", re.I)),
    ("entry", re.compile(r"\b(entry[\s-]?level|junior|jr\.?)\b", re.I)),
    ("associate", re.compile(r"\bassociate\b", re.I)),
    ("mid_senior", re.compile(r"\b(senior|sr\.?|semi[\s-]?senior|mid[\s-]?level|mid[\s-]?senior|lead|staff|principal)\b", re.I)),
]

# "3+ years", "3-5 years", "minimum of 3 years experience", etc. Best-effort —
# free-form description text, not a structured field like posted_date's source
# APIs, so this can miss or misfire; callers must treat a None as "unknown",
# never as "no requirement".
_YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:to|-)?\s*(?:\d{1,2})?\s*years?\s*(?:of\s+)?(?:experience|exp\b)", re.I)


def extract_requirements(title: str, description: str) -> Dict[str, Optional[object]]:
    """Best-effort extraction of a seniority level and required years of
    experience from a job posting's own text. Title is checked for seniority
    (titles are structured and far less noisy than prose); description is
    checked for a years-of-experience mention (titles essentially never state
    this). Returns {"seniority_level": str|None, "min_years_experience": int|None}
    — never raises, since this runs inline in the save path for every job.
    """
    seniority_level: Optional[str] = None
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(title or ""):
            seniority_level = level
            break

    min_years_experience: Optional[int] = None
    match = _YEARS_RE.search(description or "")
    if match:
        years = int(match.group(1))
        if 0 < years <= 20:  # sanity bound against stray digits unrelated to experience
            min_years_experience = years

    return {"seniority_level": seniority_level, "min_years_experience": min_years_experience}

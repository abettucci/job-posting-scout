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


# ── Remote region-scope extraction ────────────────────────────────────────────
# A "Remote" job is frequently remote-within-one-country, not remote-worldwide
# (e.g. arbeitnow's own location field is a bare city like "München" with a
# "(Remote)" suffix appended by our provider code — that's "remote if you live
# in/near Munich", not "remote from anywhere"). None of the 9 sources expose a
# structured "eligible countries" field except Remotive's candidate_required_
# location (already folded into our "location" string, so it's covered by the
# same checks below rather than needing special-casing).
#
# Checked in order: an explicit worldwide/global claim wins outright; then a
# LATAM/Argentina mention; then a curated list of specific non-LATAM countries,
# "-only" phrases, and major non-LATAM tech-hub cities (this last group exists
# specifically to catch the "City (Remote)" pattern above without needing a
# full geo database). Anything matching none of these is left as None (unknown)
# rather than guessed — see extract_requirements()'s docstring for why callers
# must never treat None as "restricted".

_WORLDWIDE_RE = re.compile(r"\b(worldwide|world[\s-]?wide|anywhere|global|remote[\s-]?first)\b", re.I)

_LATAM_RE = re.compile(
    r"\b(latam|latin\s+america|south\s+america|argentina|brazil|brasil|chile|colombia|"
    r"uruguay|paraguay|bolivia|per[uú]|ecuador|venezuela|m[eé]xico|mexico)\b", re.I,
)

_RESTRICTED_RE = re.compile(
    r"\b("
    # specific non-LATAM countries commonly seen on these boards
    r"germany|deutschland|france|united\s+kingdom|uk|poland|netherlands|spain|espa[nñ]a|italy|italia|"
    r"portugal|ireland|sweden|switzerland|austria|belgium|denmark|norway|finland|canada|"
    r"united\s+states|usa|u\.s\.a?\.?|australia|india|philippines|japan|singapore|south\s+africa"
    r"|"
    # explicit restriction phrasing
    r"us[\s-]?only|usa[\s-]?only|uk[\s-]?only|eu[\s-]?only|europe[\s-]?only|emea[\s-]?only|apac[\s-]?only|"
    r"must\s+be\s+(?:based|located|residing)\s+in|authorized\s+to\s+work\s+in"
    r"|"
    # major non-LATAM cities — catches "City (Remote)" postings with no country named
    r"berlin|munich|m[uü]nchen|hamburg|frankfurt|cologne|k[oö]ln|stuttgart|d[uü]sseldorf|"
    r"amsterdam|rotterdam|paris|warsaw|warszawa|krak[oó]w|madrid|barcelona|milan|milano|rome|roma|"
    r"dublin|vienna|wien|zurich|z[uü]rich|geneva|brussels|copenhagen|stockholm|oslo|helsinki|"
    r"london|manchester|toronto|vancouver|sydney|melbourne"
    r")\b", re.I,
)


def extract_region_scope(location: str, description: str) -> Optional[str]:
    """Best-effort classification of a posting's remote eligibility: "worldwide",
    "latam", "restricted" (tied to a specific non-LATAM place), or None (no
    clear signal either way — never treat None as "restricted", it means
    unknown, not incompatible)."""
    text = f"{location or ''} {description or ''}"
    if _WORLDWIDE_RE.search(text):
        return "worldwide"
    if _LATAM_RE.search(text):
        return "latam"
    if _RESTRICTED_RE.search(text):
        return "restricted"
    return None


# ── Company-size hint (best-effort, from the posting's own text only) ────────
# Deliberately NOT sourced from Glassdoor/Trustpilot/Crunchbase/levels.fyi/Sacra/
# PitchBook: none of those has a free API, several (Glassdoor, Trustpilot,
# levels.fyi) block scraping outright in their ToS, and doing an HTTP lookup
# per job against third-party sites during a bulk scrape run is exactly the
# "no automated fetch" line the codebase already drew for the same sites in
# the interview company-research feature (see resume/page.tsx's
# companyResearchLinks — plain search links for a human to open, no scraping).
# This is a much weaker signal (just regex over the posting's own text) but
# it's free, instant, and carries zero ToS/anti-bot risk. Always label it as
# an estimate in the UI — never present it as a verified employee count.
_STARTUP_SIZE_RE = re.compile(
    r"\b(pre-seed|seed[\s-]stage|seed[\s-]funded|series\s+a\b|series\s+b\b|"
    r"early[\s-]stage\s+startup|founding\s+(?:team|engineer|member)|small\s+but\s+mighty|"
    r"1[\s-]?(?:to|-)[\s-]?10\s+employees|11[\s-]?(?:to|-)[\s-]?50\s+employees)\b",
    re.I,
)
_MIDSIZE_RE = re.compile(
    r"\b(series\s+c\b|series\s+d\b|scale[\s-]?up|growth[\s-]stage|"
    r"51[\s-]?(?:to|-)[\s-]?200\s+employees|201[\s-]?(?:to|-)[\s-]?500\s+employees|"
    r"201[\s-]?(?:to|-)[\s-]?1,?000\s+employees)\b",
    re.I,
)
_ENTERPRISE_RE = re.compile(
    r"\b(fortune\s+(?:100|500|1000)|publicly\s+traded|nyse:|nasdaq:|multinational\s+corporation|"
    r"\d[\d,]{3,}\+?\s+employees|thousands\s+of\s+employees|global\s+enterprise)\b",
    re.I,
)


def extract_company_size_hint(description: str) -> Optional[str]:
    """Best-effort "startup" / "midsize" / "enterprise" guess from the posting's
    own description text. Returns None when there's no confident signal —
    callers must treat None as "unknown", not as any particular size."""
    text = description or ""
    if _ENTERPRISE_RE.search(text):
        return "enterprise"
    if _MIDSIZE_RE.search(text):
        return "midsize"
    if _STARTUP_SIZE_RE.search(text):
        return "startup"
    return None

"""Shared seniority vocabulary for multi-board searches and job-posting
requirement extraction.

Single source of truth for the API's search validation (routers/searches.py),
the profile's seniority preference (routers/profile.py), the scraper's
LinkedIn URL builder, and its posting-text extractor (scraper/handler.py), so
none of these can drift out of sync on valid values or LinkedIn's filter codes.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# Ordered for display in a dropdown, junior → senior. Older versions of this
# app copied LinkedIn's own "Mid-Senior level" f_E bucket, which lumps
# mid-level, "Senior", "Lead", "Staff", and "Principal" ICs together — that
# made a "Mid-Senior" filter next to useless (a plain "Senior X Developer"
# title would show up under a filter that visually reads "Mid-Senior", which
# users reasonably read as excluding plain "Senior"). "mid"/"senior"/"staff"
# split that bucket into three explicit levels; Director/Executive remain
# reserved for actual management/exec titles, not senior ICs.
SENIORITY_LEVELS = ["internship", "entry", "associate", "mid", "senior", "staff", "director", "executive"]

# LinkedIn Jobs Search "Experience level" filter codes (the f_E query param).
# LinkedIn itself has no separate "Senior"/"Staff" bucket — its own "Mid-Senior
# level" filter (f_E=4) is the closest native match for all three of our
# mid/senior/staff levels, so all three map to the same LinkedIn code; the
# finer split only exists in our own extraction/filtering, not LinkedIn's.
# This is the only one of the multi-board sources with a native, structured
# seniority filter — RemoteOK/WorkingNomads/Remotive/Arbeitnow have no such
# field, so seniority is not applied to them (see handler.py comment).
SENIORITY_TO_LINKEDIN_F_E = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid": "4",
    "senior": "4",
    "staff": "4",
    "director": "5",
    "executive": "6",
}

# Ordered most-specific-first (first match wins) so e.g. "Director of
# Engineering" matches "director" before a broader pattern gets a chance, and
# "Senior Staff Engineer" or "Lead Engineer" resolve to "staff" (the more
# senior IC tier) rather than "senior". A bare "Mid-Senior" title (still used
# by some postings verbatim) resolves to "senior", since it explicitly names
# that tier — see the "senior" pattern below.
_SENIORITY_PATTERNS = [
    ("executive", re.compile(r"\b(chief\s+\w+\s+officer|cto|ceo|cfo|coo|president)\b", re.I)),
    ("director", re.compile(r"\b(director|vp|vice\s+president|head\s+of)\b", re.I)),
    ("internship", re.compile(r"\b(intern(ship)?|trainee|new\s+grad|graduate\s+program)\b", re.I)),
    ("entry", re.compile(r"\b(entry[\s-]?level|junior|jr\.?)\b", re.I)),
    ("associate", re.compile(r"\bassociate\b", re.I)),
    ("staff", re.compile(r"\b(staff|principal|lead)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|semi[\s-]?senior|mid[\s-]?senior)\b", re.I)),
    ("mid", re.compile(r"\bmid[\s-]?level\b", re.I)),
]

# "3+ years", "3-5 years", "minimum of 3 years experience", etc. Best-effort —
# free-form description text, not a structured field like posted_date's source
# APIs, so this can miss or misfire; callers must treat a None as "unknown",
# never as "no requirement".
_YEARS_RE = re.compile(
    r"\b(?:at\s+least|minimum\s+of|minimum:?)?\s*"
    r"(\d{1,2})\+?\s*(?:to|-)?\s*(?:\d{1,2})?\s*years?\s*"
    r"(?:of\s+)?(?:hands-on\s+|commercial\s+|professional\s+|relevant\s+|practical\s+)?"
    r"(?:experience|exp\b)",
    re.I,
)


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
    years_found = [
        int(match.group(1))
        for match in _YEARS_RE.finditer(description or "")
        if 0 < int(match.group(1)) <= 20
    ]
    if years_found:
        # A posting can list several requirements (e.g. 3 years Python and 5
        # years backend). The smallest explicit experience bar is the honest
        # overall minimum; the per-skill details remain in experience_mentions.
        min_years_experience = min(years_found)

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
    r"united\s+states|usa|u\.s\.a?\.?|australia|india|philippines|japan|singapore|south\s+africa|"
    r"gauteng|western\s+cape|kwazulu[\s-]?natal"
    r"|"
    # explicit restriction phrasing
    r"us[\s-]?only|usa[\s-]?only|uk[\s-]?only|eu[\s-]?only|europe[\s-]?only|emea[\s-]?only|apac[\s-]?only|"
    r"must\s+be\s+(?:based|located|residing)\s+in|authorized\s+to\s+work\s+in"
    r"|"
    # major non-LATAM cities — catches "City (Remote)" postings with no country named
    r"berlin|munich|m[uü]nchen|hamburg|frankfurt|cologne|k[oö]ln|stuttgart|d[uü]sseldorf|werne|"
    r"amsterdam|rotterdam|paris|warsaw|warszawa|krak[oó]w|wroc[lł]aw|gda[nń]sk|pozna[nń]|"
    r"madrid|barcelona|milan|milano|rome|roma|"
    r"dublin|vienna|wien|zurich|z[uü]rich|geneva|brussels|copenhagen|stockholm|oslo|helsinki|"
    r"london|manchester|toronto|vancouver|sydney|melbourne|johannesburg|cape\s+town|durban"
    r")\b", re.I,
)


def extract_region_scope(location: str, description: str) -> Optional[str]:
    """Best-effort classification of a posting's remote eligibility: "worldwide",
    "latam", "restricted" (tied to a specific non-LATAM place), or None (no
    clear signal either way — never treat None as "restricted", it means
    unknown, not incompatible).

    "worldwide" and "latam" are checked ONLY against `location` — that field
    is short and intentional (e.g. "Worldwide", "Remote - Anywhere"). Neither
    is checked against `description`: unstructured marketing prose reliably
    contains false positives for both — a stray "we are a global company"
    sentence for "worldwide" (seen misclassifying a London-based posting),
    and a stray "help build the best fintech app in Latin America" (talking
    about the product's market, not the hire's location) for "latam" (seen
    misclassifying the same London posting as LATAM-eligible). "restricted"
    is lower false-positive risk — it keys off specific country names, which
    postings rarely namedrop by accident — so it still checks the combined
    location+description text, same as before.
    """
    location = location or ""
    combined = f"{location} {description or ''}"

    if _WORLDWIDE_RE.search(location):
        return "worldwide"
    if _LATAM_RE.search(location):
        return "latam"
    if _RESTRICTED_RE.search(combined):
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
# Phrase-based regexes are qualitative signals only (funding stage, structural
# wording) — deliberately NO literal employee-count numbers here. Numbers are
# all handled by _parse_employee_count below instead, so a range like
# "1,001-5,000 employees" can't get double-matched by an open-ended numeric
# clause in the wrong bucket (e.g. the old _ENTERPRISE_RE numeric clause used
# to match on the "5,000" half of that exact range and misclassify it).
_STARTUP_SIZE_RE = re.compile(
    r"\b(pre-seed|seed[\s-]stage|seed[\s-]funded|series\s+a\b|series\s+b\b|"
    r"early[\s-]stage\s+startup|founding\s+(?:team|engineer|member)|small\s+but\s+mighty|"
    r"bootstrapped|venture[\s-]?backed|angel[\s-]?(?:funded|backed)|pre[\s-]?series\s+a|"
    r"y\s*combinator|yc\s*[sw]\d{2}\b)\b",
    re.I,
)
_MIDSIZE_RE = re.compile(
    r"\b(series\s+c\b|series\s+d\b|scale[\s-]?up|growth[\s-]stage|"
    r"medium[\s-]?sized?\s+(?:company|business)|hundreds\s+of\s+employees)\b",
    re.I,
)
_ENTERPRISE_RE = re.compile(
    r"\b(fortune\s+(?:100|500|1000)|publicly\s+traded|publicly\s+listed|nyse:|nasdaq:|"
    r"multinational(?:\s+corporation)?|unicorn|s&p\s*500|ftse\s*100|government\s+contractor|"
    r"thousands\s+of\s+employees|global\s+enterprise)\b",
    re.I,
)

# Generic numeric fallback: matches ranges ("51-200 employees", "1,001-5,000
# employees") and single figures ("150 employees", "2,500+ employees") without
# needing to enumerate every phrasing. Buckets align with LinkedIn's own
# company-size ranges (1-10, 11-50, 51-200, 201-500, 501-1,000, 1,001-5,000,
# 5,001-10,000, 10,001+), so this same bucketing is reused by
# linkedin.py's fetch_linkedin_company_size for LinkedIn's self-reported range.
_EMPLOYEE_COUNT_RE = re.compile(
    r"(\d[\d,]{0,6})\s*(?:\+|-|to)\s*(\d[\d,]{0,6})?\s*\+?\s*employees\b"
    r"|(\d[\d,]{0,6})\+?\s+employees\b",
    re.I,
)


def _bucket_employee_count(low: int, high: Optional[int] = None) -> Optional[str]:
    n = high if high is not None else low
    if n <= 200:
        return "startup"
    if n <= 5000:
        return "midsize"
    return "enterprise"


def _parse_employee_count(text: str) -> Optional[str]:
    match = _EMPLOYEE_COUNT_RE.search(text)
    if not match:
        return None
    try:
        nums = [int(g.replace(",", "")) for g in match.groups() if g]
    except ValueError:
        return None
    if not nums or any(n <= 0 or n > 2_000_000 for n in nums):
        return None
    return _bucket_employee_count(min(nums), max(nums))


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
    return _parse_employee_count(text)


# ── Per-skill/task experience mentions (best-effort) ──────────────────────────
# extract_requirements() above only returns one overall min_years_experience
# number for the whole posting. This instead pulls out *every* "N years ...
# experience" mention individually, tied to whatever skill/task it's next to
# (e.g. "3+ years with Python", "4+ years of Quality Assurance experience"),
# so a posting can show multiple {years, context} pairs instead of a single
# number. Two shapes are matched:
#   - "<skill/phrase> ... N years[’] experience"   (skill BEFORE "experience")
#   - "N years [of ...] experience in/with/as/building/leading/managing <phrase>"
# (skill/phrase AFTER "experience"). The word "experience" itself is required
# in both — this is what rules out unrelated "N years" mentions like "For over
# 35 years, the experts at Mitratech have been focused..." (company history,
# not a requirement) from being picked up. Best-effort like every other
# extractor in this module: expect noise on dense bullet-list postings, and
# never treat a missing mention as "requires 0 years" — it means unknown.
_EXPERIENCE_REVERSE_RE = re.compile(
    r"\b(\d{1,2})\+?\s*years[^a-zA-Z]{0,6}\s*([^,.;\n\d]{1,35}?)\s*experience\b", re.I,
)
_EXPERIENCE_FORWARD_RE = re.compile(
    r"\b(\d{1,2})\+?(?:\s*(?:to|-)\s*\d{1,2}\+?)?\s*years?[^a-zA-Z]{0,6}"
    r"(?:of\s+)?(?:hands-on\s+|commercial\s+|professional\s+|relevant\s+|practical\s+)*"
    r"experience\s+(?:in|with|as|building|leading|managing|working\s+(?:with|on|in))\s+"
    r"([^,.;\n\d]{2,45})",
    re.I,
)
_EXPERIENCE_LEADING_STOPWORDS = {
    "of", "a", "an", "the", "and", "or", "is", "in", "with", "as", "to", "for", "on", "at",
}
_EXPERIENCE_TRAILING_JUNK_RE = re.compile(
    r"\s+(is\s+(a\s+)?(required|mandatory|must|a\s+plus)|required|requirements?|at\s+least)\b.*$",
    re.I,
)
_MAX_EXPERIENCE_MENTIONS = 8


def _clean_experience_context(raw: str) -> Optional[str]:
    context = re.sub(r"\s+", " ", raw).strip(" .,;:-()")
    context = _EXPERIENCE_TRAILING_JUNK_RE.sub("", context).strip()
    context = re.sub(r"\s*\([^)]*$", "", context)  # drop an unmatched trailing "("
    words = context.split()
    while words and words[0].lower() in _EXPERIENCE_LEADING_STOPWORDS:
        words = words[1:]
    while words and words[-1].lower() in ("and", "or", "&", "with", "in", "as"):
        words = words[:-1]
    if not words:
        return None
    if len(words) > 6:
        return " ".join(words[:6]) + "…"
    return " ".join(words)


def extract_experience_mentions(description: str) -> List[Dict[str, object]]:
    """Best-effort list of every distinct "N years ... experience" mention in
    a job description, each as {"years": int, "context": str}. Capped at
    _MAX_EXPERIENCE_MENTIONS; near-duplicate mentions for the same year count
    are collapsed, keeping the longer/more descriptive context."""
    if not description:
        return []

    mentions: List[Dict[str, object]] = []
    seen: List[tuple] = []

    for pattern in (_EXPERIENCE_REVERSE_RE, _EXPERIENCE_FORWARD_RE):
        for m in pattern.finditer(description):
            years = int(m.group(1))
            if not (0 < years <= 20):
                continue
            context = _clean_experience_context(m.group(2))
            if not context or len(context) < 2:
                continue

            duplicate = False
            for i, (seen_years, seen_context) in enumerate(seen):
                if seen_years == years and (
                    context.lower() in seen_context.lower() or seen_context.lower() in context.lower()
                ):
                    if len(context) > len(seen_context):
                        seen[i] = (years, context)
                        mentions[i] = {"years": years, "context": context}
                    duplicate = True
                    break
            if duplicate:
                continue

            seen.append((years, context))
            mentions.append({"years": years, "context": context})
            if len(mentions) >= _MAX_EXPERIENCE_MENTIONS:
                return mentions

    return mentions

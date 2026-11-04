"""Deterministic discovery guards shared by ingestion and historical listings.

Salary currency is a fallback eligibility signal, not a conversion rule. USD
and EUR are deliberately excluded: global remote roles commonly pay in them.
An explicit eligible job location wins over a currency hint, never over a
source known to recruit in one country (e.g. OnlineJobs.ph).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable
from urllib.parse import urlparse

MAX_POSTING_AGE_DAYS = 90
_COUNTRIES = {
    "philippines": ("philippines", "filipinas", "ph", "phl"),
    "india": ("india",), "poland": ("poland", "polonia", "pl"),
    "south africa": ("south africa", "sudafrica", "sudáfrica"),
    "nigeria": ("nigeria",), "pakistan": ("pakistan", "pakistán"),
    "bangladesh": ("bangladesh",), "indonesia": ("indonesia",),
    "malaysia": ("malaysia", "malasia"), "vietnam": ("vietnam",),
    "thailand": ("thailand", "tailandia"),
    "united kingdom": ("united kingdom", "uk", "reino unido"),
    "australia": ("australia",), "canada": ("canada", "canadá"),
    "japan": ("japan", "japón", "japon"), "singapore": ("singapore", "singapur"),
    "new zealand": ("new zealand", "nueva zelanda"),
    "switzerland": ("switzerland", "suiza"),
    "sweden": ("sweden", "suecia"), "norway": ("norway", "noruega"),
    "denmark": ("denmark", "dinamarca"),
    "argentina": ("argentina", "buenos aires"),
    "brazil": ("brazil", "brasil"), "mexico": ("mexico", "méxico"),
    "colombia": ("colombia",), "chile": ("chile",),
    "uruguay": ("uruguay",), "peru": ("peru", "perú"),
    "united states": ("united states", "usa", "us", "estados unidos"),
    "germany": ("germany", "deutschland", "alemania"),
}
_LOCAL_CURRENCIES = {
    "PHP": "philippines", "INR": "india", "PLN": "poland", "ZAR": "south africa",
    "NGN": "nigeria", "PKR": "pakistan", "BDT": "bangladesh", "IDR": "indonesia",
    "MYR": "malaysia", "VND": "vietnam", "THB": "thailand", "GBP": "united kingdom",
    "AUD": "australia", "CAD": "canada", "JPY": "japan", "SGD": "singapore",
    "NZD": "new zealand", "CHF": "switzerland", "SEK": "sweden", "NOK": "norway",
    "DKK": "denmark", "ARS": "argentina", "BRL": "brazil", "MXN": "mexico",
    "COP": "colombia", "CLP": "chile", "UYU": "uruguay", "PEN": "peru",
}
_LATAM_COUNTRIES = {"argentina", "brazil", "mexico", "colombia", "chile", "uruguay", "peru"}


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.I) is not None


def _date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            epoch = float(value)
            dt = datetime.fromtimestamp(epoch / 1000 if epoch > 10**11 else epoch, tz=timezone.utc)
        else:
            try:
                dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError:
                dt = parsedate_to_datetime(str(value))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _skip(reason: str, summary: str) -> Dict:
    return {"score": 0, "deal_breaker": True, "reasons": [reason],
            "summary": summary, "recommendation": "SKIP", "scoring_status": "filtered"}


def age_mismatch(job: Dict, now: datetime | None = None) -> Dict | None:
    # Discovery timestamp is only a lower-bound fallback when no original
    # publication date exists. Re-scraping must never rejuvenate an old date.
    source_dates = [dt for key in ("posted_date", "date_created", "datePosted", "dateCreated", "created_at")
                    if (dt := _date(job.get(key))) is not None]
    published = min(source_dates) if source_dates else _date(job.get("timestamp"))
    if published and published < (now or datetime.now(timezone.utc)) - timedelta(days=MAX_POSTING_AGE_DAYS):
        return _skip(f"❌ Posting older than {MAX_POSTING_AGE_DAYS} days (published {published.date().isoformat()})",
                     "Filtered automatically — posting is older than the maximum discovery age.")
    return None


def local_salary_currency(job: Dict) -> str | None:
    for key in ("salary_currency", "currency"):
        code = str(job.get(key) or "").upper().strip()
        if code in _LOCAL_CURRENCIES:
            return code
    salary = job.get("salary") or job.get("baseSalary") or job.get("compensation") or ""
    if isinstance(salary, dict):
        code = str(salary.get("currency") or "").upper().strip()
        if code in _LOCAL_CURRENCIES:
            return code
    text = f"{salary} {job.get('description') or ''}"
    if "₱" in text:
        return "PHP"
    codes = "|".join(_LOCAL_CURRENCIES)
    # A currency needs an amount. "PHP developer" and "PHP 8.3" are not a
    # Philippines salary. Requiring >=100 (or k) avoids language-version hits.
    for match in re.finditer(rf"\b({codes})\s*[:$]?\s*(\d[\d,.]*)(k)?\b", text, re.I):
        amount = match[2].replace(",", "").rstrip(".")
        try:
            if match[3] or float(amount) >= 100:
                return match[1].upper()
        except ValueError:
            continue
    for match in re.finditer(rf"\b(\d[\d,.]*)(k)?\s*({codes})\b", text, re.I):
        try:
            if match[2] or float(match[1].replace(",", "").rstrip(".")) >= 100:
                return match[3].upper()
        except ValueError:
            continue
    return None


def region_mismatch(job: Dict, eligible_regions: Iterable[str] = ()) -> Dict | None:
    preferences = [str(region).casefold().strip() for region in eligible_regions if str(region).strip()]
    if not preferences:
        return None
    location = str(job.get("location") or "")
    countries = {country for country, aliases in _COUNTRIES.items() if any(_contains(location, alias) for alias in aliases)}
    source_ph = (str(job.get("job_id") or "").startswith("onlinejobs:")
                 or (urlparse(str(job.get("url") or "")).hostname or "").lower() in {"onlinejobs.ph", "www.onlinejobs.ph"})
    if source_ph:
        countries = {"philippines"}
    currency = local_salary_currency(job)
    # Explicit locations carry more weight than salary denominations. Generic
    # Remote is not explicit worldwide eligibility and does not waive a hint.
    if not countries and currency:
        countries = {_LOCAL_CURRENCIES[currency]}
    if not countries:
        return None
    latam_preference = any(any(_contains(region, term) for term in ("latam", "latin america", "south america", "latinoamérica", "latinoamerica")) for region in preferences)
    for country in countries:
        if country in _LATAM_COUNTRIES and latam_preference:
            return None
        if any(_contains(region, alias) for alias in _COUNTRIES[country] for region in preferences):
            return None
    evidence = ", ".join(sorted(countries))
    if currency:
        evidence += f"; salary {currency}"
    return _skip(f"❌ Region/currency mismatch: {evidence}; allowed locations: {', '.join(preferences)}",
                 "Filtered automatically — the posting targets a location outside your preferences.")


def posting_mismatch(job: Dict, eligible_regions: Iterable[str] = (), now: datetime | None = None) -> Dict | None:
    return age_mismatch(job, now) or region_mismatch(job, eligible_regions)

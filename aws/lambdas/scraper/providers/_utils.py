"""Shared helpers for ATS provider modules."""
from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import List, Optional, Union


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities (named and numeric, e.g. &#8217;)."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def keyword_match(text: str, keywords: str) -> bool:
    """Return True if any keyword (comma-separated) appears in text (case-insensitive)."""
    if not keywords.strip():
        return True
    kws = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    haystack = text.lower()
    return any(kw in haystack for kw in kws)


def location_match(job_location: str, location_filter: str) -> bool:
    if not location_filter.strip():
        return True
    return location_filter.strip().lower() in job_location.lower()


def normalize_posted_date(value: Union[str, int, float, None], unit: str = "s") -> Optional[str]:
    """Normalize a provider's native posting-date field to a UTC ISO string.

    Accepts an epoch number (`unit="s"` or `"ms"`) or an ISO-ish string (with or
    without a timezone offset — naive strings are assumed UTC). Returns None on
    any missing/unparseable input rather than raising, since this runs inside
    per-job scraper loops where one bad date must never drop the job.
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if unit == "ms" else value
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        # Keep the UTC offset in the output — the frontend does `new Date(posted_date)`,
        # and a JS Date parses a timestamp with no offset as *local* time, not UTC.
        # Stripping tzinfo here used to silently corrupt every displayed date by the
        # viewer's UTC offset.
        return dt.isoformat()
    except (ValueError, TypeError, OSError):
        return None

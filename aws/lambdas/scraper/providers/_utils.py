"""Shared helpers for ATS provider modules."""
from __future__ import annotations

import re
from typing import List


def strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", html)
    entities = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
                "&#39;": "'", "&nbsp;": " ", "&ndash;": "–", "&mdash;": "—"}
    for ent, char in entities.items():
        text = text.replace(ent, char)
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

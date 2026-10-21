"""Small, enforced contract shared by every job-source adapter.

Providers are deliberately allowed to use different public transports (a JSON
feed, an ATS endpoint, or ordinary HTML).  What reaches the rest of the
pipeline must nevertheless have one predictable shape.  Keeping this check at
the provider boundary makes a broken source visible in the scrape report
instead of quietly persisting half-formed rows.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Iterable, List
from urllib.parse import urlparse


class ProviderContractError(RuntimeError):
    """A source returned a response that cannot safely become a job row."""


def normalize_jobs(source: str, jobs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate, normalize and de-duplicate provider output.

    A source may have zero matches for a narrowly-filtered search; that is
    healthy.  It may not return a non-list value or listings without a stable
    identifier/title/application URL.  Those are integration failures and
    should surface as such in source telemetry.
    """
    if not isinstance(jobs, list):
        raise ProviderContractError(f"{source} returned {type(jobs).__name__}, expected a list")

    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(jobs):
        if not isinstance(raw, dict):
            raise ProviderContractError(f"{source} job #{index} is not an object")
        job = dict(raw)
        job_id = str(job.get("job_id") or "").strip()
        title = str(job.get("title") or "").strip()
        url = str(job.get("url") or "").strip()
        if not job_id or not title or not url:
            raise ProviderContractError(f"{source} job #{index} is missing job_id, title, or url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderContractError(f"{source} job #{index} has an invalid application URL")
        if job_id in seen:
            continue
        seen.add(job_id)
        job.update({
            "job_id": job_id,
            "title": title,
            "company": str(job.get("company") or "Unknown company").strip() or "Unknown company",
            "location": str(job.get("location") or "").strip(),
            "url": url,
            "description": str(job.get("description") or "").strip()[:6000],
        })
        normalized.append(job)
    return normalized


async def fetch_with_contract(
    source: str,
    fetcher: Callable[..., Awaitable[List[Dict[str, Any]]]],
    *args: Any,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Run an adapter and enforce the common output contract."""
    try:
        jobs = await fetcher(*args, **kwargs)
    except ProviderContractError:
        raise
    except Exception as exc:  # preserve the provider name in dashboard/Telegram
        raise ProviderContractError(f"{source} request failed: {type(exc).__name__}") from exc
    return normalize_jobs(source, jobs)

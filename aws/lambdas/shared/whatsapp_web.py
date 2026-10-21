"""Outbound WhatsApp Web notifications through the configured sidecar."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class WhatsAppWebClient:
    def __init__(self, sidecar_url: str, shared_secret: str):
        self.sidecar_url = (sidecar_url or "").rstrip("/")
        self.shared_secret = shared_secret or ""
        self._session = requests.Session()

    def send_message(self, phone: str, text: str) -> bool:
        """Send to a private chat. The sidecar appends @c.us to the phone."""
        digits = re.sub(r"\D", "", str(phone or ""))
        if not self.sidecar_url or not self.shared_secret:
            logger.warning("WhatsApp notification skipped: sidecar configuration is missing")
            return False
        if not 8 <= len(digits) <= 15:
            logger.warning("WhatsApp notification skipped: phone number is invalid")
            return False

        parsed = urlparse(self.sidecar_url)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            logger.error("WhatsApp notification skipped: sidecar URL must use HTTPS")
            return False

        try:
            response = self._session.post(
                f"{self.sidecar_url}/send",
                json={"chat_id": digits, "chat_type": "private", "text": text},
                headers={"Authorization": f"Bearer {self.shared_secret}"},
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("ok") is not True:
                logger.warning("WhatsApp sidecar did not confirm message delivery")
                return False
            return True
        except (requests.RequestException, ValueError) as exc:
            # Avoid logging the URL, phone, response body, or shared secret.
            logger.warning("WhatsApp sidecar delivery failed (%s)", type(exc).__name__)
            return False


def format_job_notification(job: dict, score_result: dict) -> str:
    score = int(score_result.get("score", 0))
    recommendation = score_result.get("recommendation", "MAYBE")
    badge = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    rec_emoji = "🚀" if recommendation == "APPLY" else "🤔" if recommendation == "MAYBE" else "❌"
    reasons = "\n".join(score_result.get("reasons", [])[:5])
    summary = score_result.get("summary", "")
    return (
        f"{badge} Match: {score}/100 {rec_emoji}\n\n"
        f"{job.get('title', '')}\n"
        f"🏢 {job.get('company', '')}\n"
        f"📍 {job.get('location', '')}\n\n"
        f"{reasons}\n\n{summary}\n\n"
        f"Ver publicación: {job.get('url', '')}"
    )

"""
Auth for the voice-tool endpoints Vapi calls directly. These aren't
protected by normal user auth (Vapi isn't a logged-in user) -- instead,
Vapi is configured to send a shared secret in a custom header on every
tool call, and we reject anything that doesn't match. This is the only
thing standing between your Booking Service and the open internet, so
treat the secret like any other credential: env var only, never
hardcoded, rotate if it ever leaks.

In Vapi's tool config, set this under the tool's server config, e.g.:
  "server": {
    "url": "https://your-app.up.railway.app/api/v1/voice-tools/check-availability",
    "headers": { "x-vapi-secret": "<the same value as VAPI_SHARED_SECRET>" }
  }
"""

import logging

from fastapi import Header, HTTPException, status

from app.core.config import settings  # assumes Milestone 1's pydantic-settings config

logger = logging.getLogger(__name__)


async def verify_vapi_secret(x_vapi_secret: str = Header(...)) -> None:
    if x_vapi_secret != settings.VAPI_SHARED_SECRET:
        # Diagnostic-only logging -- never logs either full value. Just
        # enough to distinguish "wrong length" (whitespace/truncation)
        # from "right length, wrong content" (genuinely different
        # secret) from "looks like the OLD secret specifically" (stale
        # config somewhere not yet updated), all visible in Railway logs
        # without exposing the actual credential anywhere.
        def fingerprint(s: str) -> str:
            if len(s) <= 8:
                return f"(len={len(s)}) {s[:2]}...{s[-2:]}"
            return f"(len={len(s)}) {s[:4]}...{s[-4:]}"

        logger.warning(
            "verify_vapi_secret: mismatch. received=%s expected=%s",
            fingerprint(x_vapi_secret),
            fingerprint(settings.VAPI_SHARED_SECRET),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing tool credentials.",
        )


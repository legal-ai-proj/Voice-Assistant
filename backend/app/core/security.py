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

from fastapi import Header, HTTPException, status

from app.core.config import settings  # assumes Milestone 1's pydantic-settings config


async def verify_vapi_secret(x_vapi_secret: str = Header(...)) -> None:
    if x_vapi_secret != settings.VAPI_SHARED_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing tool credentials.",
        )

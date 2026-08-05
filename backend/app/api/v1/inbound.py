"""
Inbound call handler for Vapi.

When a phone call comes in on the Vapi number, Vapi hits this endpoint
BEFORE connecting the caller to the assistant. We respond with
assistantOverrides that inject today's date as a variable, so the model
always knows what day it is without anyone having to manually update it.

Configure this in Vapi:
  Phone Number → Server URL → https://<railway-url>/api/v1/inbound-call
  (no auth needed -- Vapi sends its own call ID, not our shared secret)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["inbound"])

# Branch timezone -- America/Chicago for Barber Shop On Main.
# When multi-tenant, derive this from the phone number → branch lookup.
BRANCH_TZ = ZoneInfo("America/Chicago")


@router.post("/inbound-call")
async def inbound_call(request: Request) -> dict:
    """Vapi POSTs here when a call comes in. We respond with
    assistantOverrides to inject {{current_date}} dynamically."""
    today = datetime.now(BRANCH_TZ).strftime("%A, %B %-d, %Y")
    # e.g. "Wednesday, August 5, 2026" -- readable by the model,
    # so it can handle "tomorrow", "next Monday" etc. without asking
    return {
        "assistantOverrides": {
            "variableValues": {
                "current_date": today,
            }
        }
    }

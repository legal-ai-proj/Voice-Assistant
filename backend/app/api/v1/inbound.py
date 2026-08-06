"""
Inbound call handler for Vapi.

Vapi hits this endpoint BEFORE connecting the caller to the assistant.
We do three things simultaneously:

1. Resolve which branch this call is for (via the Vapi phone number in
   the payload -- each branch has its own Vapi number so multi-tenancy
   works without any hardcoding here).
2. Inject today's date in the branch's local timezone.
3. Fire a background task that pre-warms both caches simultaneously:
   - get_business_info (branch facts: name, hours, services, staff)
   - check_availability for all services x next 7 days
   so every tool call for the rest of the conversation returns instantly
   from cache instead of making the caller wait for a DB round-trip.

The response is returned immediately (fire-and-forget background task)
so the call connects with zero added latency from the warm-up work.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from app.core.database import AsyncSessionLocal
from app.repositories.business_info_repository import get_branch_by_vapi_phone
from app.services.booking_service import pre_warm_availability
from app.services.business_info_service import get_business_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["inbound"])

# Fallback branch ID and timezone if phone number lookup fails
# (e.g. direct test calls not from a registered Vapi number)
_FALLBACK_BRANCH_ID = 1
_FALLBACK_TZ = ZoneInfo("America/Chicago")


async def _warm_caches(branch_id: int, tz_name: str) -> None:
    """Pre-warm business info + availability caches in parallel.
    Runs as a fire-and-forget background task so the call connects
    immediately without waiting for this to finish."""
    try:
        async with AsyncSessionLocal() as db:
            await asyncio.gather(
                get_business_info(db, branch_id),
                pre_warm_availability(db, branch_id, days_ahead=7),
                return_exceptions=True,
            )
    except Exception:
        # Never let a warm-up failure affect the live call
        logger.exception("inbound: cache pre-warm failed for branch %s", branch_id)


@router.post("/inbound-call")
async def inbound_call(request: Request) -> dict:
    """Vapi POSTs here when a call comes in, before the caller hears anything.
    Resolves the branch from the called Vapi number, injects today's date,
    and kicks off parallel cache pre-warming in the background."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    # Vapi sends the called number as message.phoneNumber.number or
    # phoneNumber.number depending on the event format
    called_number = (
        (payload.get("message") or {}).get("phoneNumber", {}).get("number")
        or payload.get("phoneNumber", {}).get("number")
        or payload.get("to")
    )

    branch_id = _FALLBACK_BRANCH_ID
    tz = _FALLBACK_TZ

    if called_number:
        try:
            async with AsyncSessionLocal() as db:
                branch = await get_branch_by_vapi_phone(db, called_number)
                if branch:
                    branch_id = branch.id
                    tz = ZoneInfo(branch.timezone)
                else:
                    logger.warning(
                        "inbound: no branch found for Vapi number %s, using fallback branch %s",
                        called_number,
                        _FALLBACK_BRANCH_ID,
                    )
        except Exception:
            logger.exception("inbound: branch lookup failed, using fallback")

    today = datetime.now(tz).strftime("%A, %B %-d, %Y")

    # Fire pre-warming in background -- response returns immediately
    asyncio.create_task(_warm_caches(branch_id, str(tz)))

    return {
        "assistantOverrides": {
            "variableValues": {
                "current_date": today,
            }
        }
    }

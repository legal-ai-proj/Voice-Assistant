"""
Inbound call handler for Vapi.

When a phone call comes in on the Vapi number, Vapi hits this endpoint
BEFORE connecting the caller to the assistant. We respond with
assistantOverrides that inject today's date, AND kick off background
pre-warming of both the business info cache and the availability cache
so tool calls during the conversation return instantly from cache
instead of making the caller wait for DB round-trips.

The pre-warming happens in the background -- we return the assistant
overrides immediately without waiting for it, so the call connects
without any added latency from the warm-up work.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.services.booking_service import pre_warm_availability
from app.services.business_info_service import get_business_info

router = APIRouter(prefix="/api/v1", tags=["inbound"])

BRANCH_ID = 1
BRANCH_TZ = ZoneInfo("America/Chicago")


async def _warm_caches() -> None:
    """Pre-warm business info AND availability caches simultaneously.
    Runs as a fire-and-forget background task so the call connects
    immediately without waiting for this to finish."""
    async with AsyncSessionLocal() as db:
        await asyncio.gather(
            get_business_info(db, BRANCH_ID),
            pre_warm_availability(db, BRANCH_ID, days_ahead=7),
            return_exceptions=True,
        )


@router.post("/inbound-call")
async def inbound_call(request: Request) -> dict:
    """Vapi POSTs here when a call comes in. We:
    1. Respond immediately with today's date variable injection
    2. Fire background cache pre-warming for business info + availability
       across all services × next 7 days so the first tool calls return
       from cache, not from a live DB round-trip mid-conversation."""
    today = datetime.now(BRANCH_TZ).strftime("%A, %B %-d, %Y")

    # Background task -- don't await, don't block the response
    asyncio.create_task(_warm_caches())

    return {
        "assistantOverrides": {
            "variableValues": {
                "current_date": today,
            }
        }
    }

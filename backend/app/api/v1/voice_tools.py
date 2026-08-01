"""
Voice-tool endpoints -- the FastAPI side of every Vapi tool defined in
the assistant's config (check_availability first; create_appointment,
reschedule_appointment, etc. follow the same pattern). These are the
ONLY way the voice agent ever touches booking data -- Vapi never
queries Supabase directly, per the platform's core architecture rule.

branch_id is a URL path parameter, not part of the request body the
model fills in. Each branch's Vapi assistant has its tool config
pointed at a URL with its own branch_id already baked in, so the model
never sees, generates, or can get this value wrong.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_vapi_secret
from app.schemas.availability import CheckAvailabilityRequest, CheckAvailabilityResponse
from app.services.booking_service import (
    NoEligibleStaffError,
    ServiceNotFoundError,
    check_availability,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/voice-tools",
    tags=["voice-tools"],
    dependencies=[Depends(verify_vapi_secret)],
)


@router.post("/check-availability/{branch_id}", response_model=CheckAvailabilityResponse)
async def check_availability_endpoint(
    branch_id: UUID,
    payload: CheckAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
) -> CheckAvailabilityResponse:
    try:
        return await check_availability(
            db=db,
            branch_id=branch_id,
            service_id=payload.service_id,
            target_date=payload.date,
            staff_id=payload.staff_id,
        )
    except ServiceNotFoundError:
        # Never expose internal exception details to the caller (Vapi,
        # and by extension the model reading this response). Log the
        # real detail server-side, return a clean message the voice
        # agent can safely relay or fall back on.
        logger.warning(
            "check_availability: unknown service",
            extra={"branch_id": str(branch_id), "payload": payload.model_dump(mode="json")},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That service isn't recognized for this branch.",
        )
    except NoEligibleStaffError:
        logger.info(
            "check_availability: no eligible staff",
            extra={"branch_id": str(branch_id), "payload": payload.model_dump(mode="json")},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No staff available for that service right now.",
        )
    except Exception:
        logger.exception("check_availability: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong checking availability. Please try again shortly.",
        )


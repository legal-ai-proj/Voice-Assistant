"""
Voice-tool endpoints -- the FastAPI side of every Vapi tool defined in
the assistant's config. These are the ONLY way the voice agent ever
touches booking data -- Vapi never queries Supabase directly, per the
platform's core architecture rule.

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
from app.schemas.appointments import CreateAppointmentRequest, CreateAppointmentResponse
from app.schemas.availability import CheckAvailabilityRequest, CheckAvailabilityResponse
from app.schemas.business_info import BusinessInfoResponse
from app.services.appointment_service import (
    BranchNotFoundError as AppointmentBranchNotFoundError,
)
from app.services.appointment_service import (
    ServiceNotFoundError as AppointmentServiceNotFoundError,
)
from app.services.appointment_service import (
    SlotNoLongerAvailableError,
    create_appointment,
)
from app.services.booking_service import (
    NoEligibleStaffError,
    ServiceNotFoundError,
    check_availability,
)
from app.services.business_info_service import BranchNotFoundError, get_business_info

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/voice-tools",
    tags=["voice-tools"],
    dependencies=[Depends(verify_vapi_secret)],
)


@router.get("/business-info/{branch_id}", response_model=BusinessInfoResponse)
async def business_info_endpoint(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> BusinessInfoResponse:
    """Called once at the start of a call (per the prompt) to fetch
    live business facts -- name, hours, services, staff, products,
    policies -- instead of relying on static prompt-injected values."""
    try:
        return await get_business_info(db, branch_id)
    except BranchNotFoundError:
        logger.warning("business_info: unknown branch", extra={"branch_id": str(branch_id)})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This branch isn't recognized.",
        )
    except Exception:
        logger.exception("business_info: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong fetching business info. Please try again shortly.",
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


@router.post("/create-appointment/{branch_id}", response_model=CreateAppointmentResponse)
async def create_appointment_endpoint(
    branch_id: UUID,
    payload: CreateAppointmentRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateAppointmentResponse:
    """The write side. Re-validates the slot server-side before
    committing anything -- never trust that a slot checked a moment ago
    via check_availability is still open."""
    try:
        return await create_appointment(
            db=db,
            branch_id=branch_id,
            service_id=payload.service_id,
            target_date=payload.date,
            start_time=payload.start_time,
            staff_id=payload.staff_id,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
        )
    except AppointmentBranchNotFoundError:
        logger.warning("create_appointment: unknown branch", extra={"branch_id": str(branch_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This branch isn't recognized.")
    except AppointmentServiceNotFoundError:
        logger.warning(
            "create_appointment: unknown service",
            extra={"branch_id": str(branch_id), "payload": payload.model_dump(mode="json")},
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That service isn't recognized.")
    except SlotNoLongerAvailableError:
        # Not a server error -- a legitimate race condition. The agent
        # should offer to check availability again, not treat this as a
        # generic failure.
        logger.info(
            "create_appointment: slot no longer available",
            extra={"branch_id": str(branch_id), "payload": payload.model_dump(mode="json")},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time was just taken. Please check availability again for another slot.",
        )
    except Exception:
        logger.exception("create_appointment: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong booking that appointment. Please try again shortly.",
        )



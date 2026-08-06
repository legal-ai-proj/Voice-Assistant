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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_vapi_secret
from app.schemas.appointment_management import (
    CancelAppointmentRequest,
    CancelAppointmentResponse,
    LookupAppointmentRequest,
    LookupAppointmentResponse,
    RescheduleAppointmentRequest,
    RescheduleAppointmentResponse,
    TakeMessageRequest,
    TakeMessageResponse,
)
from app.schemas.appointments import (
    CreateAppointmentRequest,
    CreateAppointmentResponse,
    CreateAppointmentsRequest,
    CreateAppointmentsResponse,
)
from app.services.appointments_multi_service import (
    BranchNotFoundError as MultiBranchNotFoundError,
    ServiceNotFoundError as MultiServiceNotFoundError,
    SlotNotAvailableError as MultiSlotNotAvailableError,
    create_appointments,
)
from app.schemas.availability import CheckAvailabilityRequest, CheckAvailabilityResponse
from app.schemas.business_info import BusinessInfoResponse
from app.services import appointment_management_service as mgmt
from app.services.appointment_service import (
    BranchNotFoundError as AppointmentBranchNotFoundError,
)
from app.services.appointment_service import (
    ServiceNotFoundError as AppointmentServiceNotFoundError,
)
from app.services.appointment_service import (
    CustomerDoubleBookedError,
    SlotNoLongerAvailableError,
    create_appointment,
)
from app.services.booking_service import (
    NoEligibleStaffError,
    ServiceNotFoundError,
    check_availability,
)
from app.services.business_info_service import BranchNotFoundError, get_business_info
from app.services.call_ingestion_service import process_end_of_call

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/voice-tools",
    tags=["voice-tools"],
    dependencies=[Depends(verify_vapi_secret)],
)


@router.get("/business-info/{branch_id}", response_model=BusinessInfoResponse)
async def business_info_endpoint(
    branch_id: int,
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
    branch_id: int,
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
    branch_id: int,
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
    except CustomerDoubleBookedError:
        logger.info(
            "create_appointment: customer already has an overlapping appointment",
            extra={"branch_id": str(branch_id), "payload": payload.model_dump(mode="json")},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This customer already has another appointment that overlaps this time. Please choose a different time.",
        )
    except Exception:
        logger.exception("create_appointment: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong booking that appointment. Please try again shortly.",
        )


@router.post("/lookup-appointment/{branch_id}", response_model=LookupAppointmentResponse)
async def lookup_appointment_endpoint(
    branch_id: int,
    payload: LookupAppointmentRequest,
    db: AsyncSession = Depends(get_db),
) -> LookupAppointmentResponse:
    """Find a caller's upcoming appointments by phone -- the dependency
    reschedule/cancel both rely on to know WHICH appointment to touch."""
    try:
        return await mgmt.lookup_appointment(db, branch_id, payload.customer_phone)
    except mgmt.BranchNotFoundError:
        logger.warning("lookup_appointment: unknown branch", extra={"branch_id": str(branch_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This branch isn't recognized.")
    except Exception:
        logger.exception("lookup_appointment: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong looking that up. Please try again shortly.",
        )


@router.post("/reschedule-appointment/{branch_id}", response_model=RescheduleAppointmentResponse)
async def reschedule_appointment_endpoint(
    branch_id: int,
    payload: RescheduleAppointmentRequest,
    db: AsyncSession = Depends(get_db),
) -> RescheduleAppointmentResponse:
    """Move an existing appointment. Re-validates the new slot server-side."""
    try:
        return await mgmt.reschedule_appointment(
            db, branch_id, payload.appointment_id, payload.date, payload.start_time, payload.service_id
        )
    except mgmt.AppointmentNotFoundError:
        logger.info("reschedule: appointment not found", extra={"branch_id": str(branch_id)})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="I couldn't find that appointment to reschedule.",
        )
    except mgmt.ServiceChangeNotAllowedError:
        logger.info("reschedule: service change not allowed", extra={"branch_id": str(branch_id)})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That service change isn't possible on this appointment — the caller should cancel and rebook.",
        )
    except mgmt.SlotNoLongerAvailableError:
        logger.info("reschedule: new slot unavailable", extra={"branch_id": str(branch_id)})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That new time isn't available. Please check availability for another slot.",
        )
    except mgmt.CustomerDoubleBookedError:
        logger.info(
            "reschedule: customer already has an overlapping appointment", extra={"branch_id": str(branch_id)}
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That new time overlaps another appointment this customer already has. Please choose a different time.",
        )
    except Exception:
        logger.exception("reschedule_appointment: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong rescheduling. Please try again shortly.",
        )


@router.post("/cancel-appointment/{branch_id}", response_model=CancelAppointmentResponse)
async def cancel_appointment_endpoint(
    branch_id: int,
    payload: CancelAppointmentRequest,
    db: AsyncSession = Depends(get_db),
) -> CancelAppointmentResponse:
    """Soft-cancel an appointment (status -> 'cancelled', never deleted)."""
    try:
        return await mgmt.cancel_appointment(db, branch_id, payload.appointment_id)
    except mgmt.AppointmentNotFoundError:
        logger.info("cancel: appointment not found", extra={"branch_id": str(branch_id)})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="I couldn't find that appointment to cancel.",
        )
    except mgmt.AlreadyCancelledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That appointment is already cancelled.",
        )
    except Exception:
        logger.exception("cancel_appointment: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong cancelling. Please try again shortly.",
        )


@router.post("/take-message/{branch_id}", response_model=TakeMessageResponse)
async def take_message_endpoint(
    branch_id: int,
    payload: TakeMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> TakeMessageResponse:
    """Save a message for staff follow-up."""
    try:
        return await mgmt.take_message(
            db, branch_id, payload.caller_name, payload.caller_phone, payload.message_body
        )
    except mgmt.BranchNotFoundError:
        logger.warning("take_message: unknown branch", extra={"branch_id": str(branch_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This branch isn't recognized.")
    except Exception:
        logger.exception("take_message: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong saving that message. Please try again shortly.",
        )


@router.post("/create-appointments/{branch_id}", response_model=CreateAppointmentsResponse)
async def create_appointments_endpoint(
    branch_id: int,
    payload: CreateAppointmentsRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateAppointmentsResponse:
    """Book multiple services in one call. Same barber for all services,
    sequential times, single atomic transaction. Use this instead of
    calling create-appointment multiple times when the caller wants more
    than one service in the same visit."""
    try:
        return await create_appointments(db, branch_id, payload)
    except MultiBranchNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")
    except MultiServiceNotFoundError as e:
        logger.warning("create_appointments: service not found: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MultiSlotNotAvailableError as e:
        logger.info("create_appointments: slot unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception:
        logger.exception("create_appointments: unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong booking those appointments. Please try again.",
        )


@router.post("/webhook/end-of-call/{branch_id}")
async def end_of_call_webhook(
    branch_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Vapi's end-of-call-report lands here after every call. Distinct
    from the tools above: this is Vapi calling US, not the model calling
    a tool mid-call. Logs the raw payload first (never loses a call),
    then extracts and writes a clean call_logs row. Always returns 200
    with a status body -- a 500 would just trigger Vapi retries."""
    payload = await request.json()
    result = await process_end_of_call(db, branch_id, payload)
    return result

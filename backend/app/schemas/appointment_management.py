"""
Request/response contracts for the appointment-management voice tools:
lookup_appointment, reschedule_appointment, cancel_appointment, and
take_message. All follow the same conventions as the existing tools --
branch_id comes from the URL path (never the model), and date/time
imports are aliased to avoid the Pydantic field/type shadowing bug.
"""

from datetime import date as date_type
from datetime import time as time_type

from pydantic import BaseModel, Field, field_validator

from app.schemas.validators import empty_str_to_none


# ---- lookup_appointment ------------------------------------------------

class LookupAppointmentRequest(BaseModel):
    customer_phone: str = Field(..., description="The caller's phone number -- the identity key used to find their bookings.")


class AppointmentSummary(BaseModel):
    appointment_id: int
    service_name: str
    staff_name: str | None
    date: date_type
    start_time: time_type
    status: str


class LookupAppointmentResponse(BaseModel):
    found: bool
    customer_name: str | None
    appointments: list[AppointmentSummary]
    message: str = Field(
        ...,
        description="Short, speakable summary -- e.g. 'I found one upcoming "
        "appointment: a haircut with Marco on Wednesday at 2 PM' or 'I don't "
        "see any upcoming appointments under that number.'",
    )


# ---- reschedule_appointment -------------------------------------------

class RescheduleAppointmentRequest(BaseModel):
    appointment_id: int = Field(..., description="The appointment to move, from a prior lookup_appointment call.")
    date: date_type = Field(..., description="New date, YYYY-MM-DD, already resolved from any relative phrase.")
    start_time: time_type = Field(..., description="New start time, HH:MM, from a slot returned by check_availability.")
    service_id: int | None = Field(
        default=None,
        description="Only include if the caller also wants a DIFFERENT service than "
        "originally booked. Omit to keep the same service. Changing the service can "
        "change the appointment length, so re-run check_availability for the new "
        "service before confirming a time.",
    )

    _coerce_service_id = field_validator("service_id", mode="before")(empty_str_to_none)


class RescheduleAppointmentResponse(BaseModel):
    appointment_id: int
    confirmed: bool
    service_name: str
    staff_name: str
    date: date_type
    start_time: time_type
    message: str


# ---- cancel_appointment -----------------------------------------------

class CancelAppointmentRequest(BaseModel):
    appointment_id: int = Field(..., description="The appointment to cancel, from a prior lookup_appointment call.")


class CancelAppointmentResponse(BaseModel):
    appointment_id: int
    cancelled: bool
    message: str


# ---- take_message ------------------------------------------------------

class TakeMessageRequest(BaseModel):
    caller_name: str | None = Field(default=None, description="The caller's name, if given.")
    caller_phone: str | None = Field(default=None, description="The caller's callback number, confirmed back to them.")
    message_body: str = Field(..., description="The message to pass along to staff, in the caller's own words.")


class TakeMessageResponse(BaseModel):
    message_id: int
    saved: bool
    message: str = Field(..., description="Short speakable confirmation -- e.g. 'Got it, I've passed that along.'")

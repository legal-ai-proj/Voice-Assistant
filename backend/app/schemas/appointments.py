"""
Request/response contract for the create_appointment voice tool -- the
write side of the loop. This is the tool that actually commits a
booking, so it re-validates availability server-side before writing
anything (never trust that a slot checked a minute ago via
check_availability is still open -- another caller or a web booking
could have taken it in the meantime).
"""

from datetime import date as date_type
from datetime import time as time_type

from pydantic import BaseModel, Field, field_validator

from app.schemas.validators import empty_str_to_none


class CreateAppointmentRequest(BaseModel):
    service_id: int
    date: date_type = Field(..., description="Exact calendar date, YYYY-MM-DD, already resolved from any relative phrase.")
    start_time: time_type = Field(..., description="Exact start time, HH:MM, from a slot returned by check_availability.")
    staff_id: int | None = Field(default=None, description="Omit for 'any barber' -- omitting lets the server pick any eligible, available staff member.")
    customer_name: str = Field(..., description="The caller's name, as given during the call.")
    customer_phone: str = Field(..., description="The caller's phone number, confirmed during the call.")

    _coerce_staff_id = field_validator("staff_id", mode="before")(empty_str_to_none)


class CreateAppointmentResponse(BaseModel):
    appointment_id: int
    confirmed: bool
    staff_id: int = Field(
        ...,
        description="The staff member actually assigned. Reuse this exact value as staff_id "
        "for all subsequent services in the same visit.",
    )
    staff_name: str
    service_name: str
    date: date_type
    start_time: time_type
    end_time: time_type = Field(
        ...,
        description="When this appointment ends. Use this as the start_time for the NEXT "
        "service in the same visit -- do not use the same start_time as this appointment.",
    )
    message: str = Field(
        ...,
        description="Short, speakable confirmation for the voice agent to read back.",
    )


# ---- Multi-service booking (single tool call for multiple services) ----

class ServiceBooking(BaseModel):
    """One service within a multi-service booking request."""
    service_id: int = Field(..., description="Integer ID from get_business_info.")
    start_time: time_type = Field(
        ...,
        description="HH:MM start time. For the first service use the slot from check_availability. "
        "For each subsequent service, the server calculates the start time automatically "
        "from the previous service's end -- you do not need to calculate it yourself.",
    )


class CreateAppointmentsRequest(BaseModel):
    """Book multiple services in one API call. Server assigns the same barber
    to all, books them sequentially, and returns all confirmations at once."""
    services: list[ServiceBooking] = Field(
        ...,
        description="List of services to book in visit order. Minimum 1 entry. "
        "For the first service provide the chosen start_time. For subsequent services "
        "the server will use each previous service's end_time automatically.",
    )
    date: date_type = Field(..., description="Exact calendar date, YYYY-MM-DD.")
    staff_id: int | None = Field(default=None, description="Omit for any available barber.")
    customer_name: str
    customer_phone: str

    _coerce_staff_id = field_validator("staff_id", mode="before")(empty_str_to_none)


class ServiceBookingResult(BaseModel):
    appointment_id: int
    service_name: str
    staff_id: int
    staff_name: str
    date: date_type
    start_time: time_type
    end_time: time_type


class CreateAppointmentsResponse(BaseModel):
    confirmed: bool
    bookings: list[ServiceBookingResult]
    message: str = Field(
        ...,
        description="Single speakable confirmation for all booked services. "
        "e.g. 'Done — men's haircut at 10 and hot towel shave at 10:30 with Abe on Saturday.'",
    )

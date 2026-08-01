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
from uuid import UUID

from pydantic import BaseModel, Field


class CreateAppointmentRequest(BaseModel):
    service_id: UUID
    date: date_type = Field(..., description="Exact calendar date, YYYY-MM-DD, already resolved from any relative phrase.")
    start_time: time_type = Field(..., description="Exact start time, HH:MM, from a slot returned by check_availability.")
    staff_id: UUID | None = Field(default=None, description="Omit for 'any barber' -- omitting lets the server pick any eligible, available staff member.")
    customer_name: str = Field(..., description="The caller's name, as given during the call.")
    customer_phone: str = Field(..., description="The caller's phone number, confirmed during the call.")


class CreateAppointmentResponse(BaseModel):
    appointment_id: UUID
    confirmed: bool
    staff_name: str
    service_name: str
    date: date_type
    start_time: time_type
    message: str = Field(
        ...,
        description="Short, speakable confirmation for the voice agent to read back -- "
        "e.g. 'You're all set: a Men's Haircut with Marco on Wednesday, August 5th at 10:00 AM.' "
        "Only ever generated when confirmed is true.",
    )

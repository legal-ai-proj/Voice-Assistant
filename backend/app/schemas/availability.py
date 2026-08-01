"""
Request/response contract for the check_availability voice tool.
This must stay in sync with the tool's JSON schema registered in Vapi
(see the "check_availability" tool config discussed in the prompt doc).
"""

from datetime import date as date_type
from datetime import time as time_type
from uuid import UUID

from pydantic import BaseModel, Field


class CheckAvailabilityRequest(BaseModel):
    branch_id: UUID
    service_id: UUID
    date: date_type = Field(
        ...,
        description="Resolved calendar date (YYYY-MM-DD). Vapi must "
        "resolve any relative date the caller gives -- 'next Monday', "
        "etc. -- using {{current_date}} before calling this tool. This "
        "endpoint does not do relative-date math itself.",
    )
    staff_id: UUID | None = Field(
        default=None,
        description="Omit for 'any barber' -- results are merged across all active staff who can perform this service.",
    )


class AvailableSlot(BaseModel):
    staff_id: UUID
    staff_name: str
    start_time: time_type


class CheckAvailabilityResponse(BaseModel):
    date: date_type
    service_name: str
    duration_minutes: int
    slots: list[AvailableSlot]
    message: str = Field(
        ...,
        description="Short, speakable summary for the voice agent to "
        "read back -- e.g. 'Marco has 10:00, 10:30, and 11:15 open' or "
        "'Nothing's open that day, closest is Tuesday.' The agent "
        "should prefer this field over re-deriving language from `slots`.",
    )


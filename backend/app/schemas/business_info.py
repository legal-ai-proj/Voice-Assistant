"""
Request/response contract for the get_business_info voice tool. This
replaces the old approach of injecting business facts as {{variables}}
baked into the static prompt -- instead, the agent calls this once at
the start of a call and gets live data straight from Supabase. No
request body needed; branch_id comes from the URL path, same as
check_availability.

IMPORTANT: services and staff both include `id` -- the actual UUID
needed as `service_id`/`staff_id` when calling check_availability,
create_appointment, or reschedule_appointment. Without this, the model
has no legitimate way to reference a specific service/staff member in
those calls except by guessing with the name, which fails UUID
validation. This was a real bug found via a live call: the model
passed the literal string "Men's Haircut" as service_id and got a
uuid_parsing error, then couldn't recover from the failure.
"""


from pydantic import BaseModel, Field


class DayHours(BaseModel):
    day: str  # "Monday", "Tuesday", ...
    open_time: str | None  # "09:00" or null if closed
    close_time: str | None
    is_closed: bool


class ServiceInfo(BaseModel):
    id: int = Field(..., description="Use this exact value as service_id in other tool calls -- never the name.")
    name: str
    price_min: float
    price_max: float | None = Field(
        default=None,
        description="null means a fixed price (price_min is the exact price), not a range",
    )


class StaffInfo(BaseModel):
    id: int = Field(..., description="Use this exact value as staff_id in other tool calls -- never the name.")
    name: str
    role: str


class ProductInfo(BaseModel):
    name: str
    price_min: float
    price_max: float | None = None


class PoliciesInfo(BaseModel):
    cancellation_policy: str | None = Field(
        default=None, description="null means this hasn't been confirmed yet -- do not invent one"
    )
    deposit_policy: str | None = None


class BusinessInfoResponse(BaseModel):
    business_name: str
    business_type: str
    address: str | None = Field(
        default=None,
        description="Speak this naturally as written — do not split into individual digits or letters. e.g. '307 North Main Avenue, San Antonio, TX 78205' should be spoken as 'three oh seven North Main Avenue'.",
    )
    phone: str | None
    hours: list[DayHours]
    services: list[ServiceInfo]
    staff: list[StaffInfo]
    products: list[ProductInfo]
    policies: PoliciesInfo


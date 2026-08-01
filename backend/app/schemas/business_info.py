"""
Request/response contract for the get_business_info voice tool. This
replaces the old approach of injecting business facts as {{variables}}
baked into the static prompt -- instead, the agent calls this once at
the start of a call and gets live data straight from Supabase. No
request body needed; branch_id comes from the URL path, same as
check_availability.
"""

from pydantic import BaseModel, Field


class DayHours(BaseModel):
    day: str  # "Monday", "Tuesday", ...
    open_time: str | None  # "09:00" or null if closed
    close_time: str | None
    is_closed: bool


class ServiceInfo(BaseModel):
    name: str
    duration_minutes: int
    price_min: float
    price_max: float | None = Field(
        default=None,
        description="null means a fixed price (price_min is the exact price), not a range",
    )


class StaffInfo(BaseModel):
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
    address: str | None
    phone: str | None
    hours: list[DayHours]
    services: list[ServiceInfo]
    staff: list[StaffInfo]
    products: list[ProductInfo]
    policies: PoliciesInfo

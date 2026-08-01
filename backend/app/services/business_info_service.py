"""
Business info service -- assembles everything the voice agent needs to
know about a branch, fetched live. This is what replaces static
{{variable}} injection in the prompt: the agent calls this once at the
start of a call and treats the response as its grounded context for
everything else in the conversation.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import business_info_repository as repo
from app.schemas.business_info import (
    BusinessInfoResponse,
    DayHours,
    PoliciesInfo,
    ProductInfo,
    ServiceInfo,
    StaffInfo,
)

_DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


class BranchNotFoundError(Exception):
    pass


async def get_business_info(db: AsyncSession, branch_id: UUID) -> BusinessInfoResponse:
    branch_and_chain = await repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found or inactive")
    branch, chain = branch_and_chain

    hours_rows = await repo.get_branch_hours(db, branch_id)
    hours = [
        DayHours(
            day=_DAY_NAMES[h.day_of_week],
            open_time=h.open_time.strftime("%H:%M") if h.open_time else None,
            close_time=h.close_time.strftime("%H:%M") if h.close_time else None,
            is_closed=h.is_closed,
        )
        for h in hours_rows
    ]

    services = [
        ServiceInfo(
            name=s.name,
            duration_minutes=s.duration_minutes,
            price_min=float(s.price_min),
            price_max=float(s.price_max) if s.price_max is not None else None,
        )
        for s in await repo.get_active_services(db, branch_id)
    ]

    staff = [StaffInfo(name=s.name, role=s.role) for s in await repo.get_active_staff(db, branch_id)]

    products = [
        ProductInfo(
            name=p.name,
            price_min=float(p.price_min),
            price_max=float(p.price_max) if p.price_max is not None else None,
        )
        for p in await repo.get_active_products(db, branch_id)
    ]

    settings = await repo.get_branch_settings(db, branch_id)
    policies = PoliciesInfo(
        cancellation_policy=settings.cancellation_policy if settings else None,
        deposit_policy=settings.deposit_policy if settings else None,
    )

    return BusinessInfoResponse(
        business_name=chain.name,
        business_type=chain.vertical,
        address=branch.address,
        phone=branch.phone,
        hours=hours,
        services=services,
        staff=staff,
        products=products,
        policies=policies,
    )

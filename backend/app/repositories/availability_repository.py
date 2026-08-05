"""
Data access layer for availability computation. Contains only queries --
no business logic (that lives in services/booking_service.py). Every
function here takes an AsyncSession and returns plain data or ORM rows;
none of them know *why* they're being called.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import (
    Appointment,
    Branch,
    BranchHours,
    Service,
    Staff,
    StaffHours,
    StaffService,
    StaffTimeOff,
)


async def get_branch(db: AsyncSession, branch_id: int) -> Branch | None:
    result = await db.execute(select(Branch).where(Branch.id == branch_id))
    return result.scalar_one_or_none()


async def get_service(db: AsyncSession, service_id: int, branch_id: int) -> Service | None:
    result = await db.execute(
        select(Service).where(
            Service.id == service_id,
            Service.branch_id == branch_id,
            Service.active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_eligible_staff(db: AsyncSession, branch_id: int, service_id: int, staff_id: int | None) -> list[Staff]:
    """Active staff at this branch who can perform this service. If
    staff_id is given, narrows to just that one (still validates they
    can actually perform the service -- never silently ignore that)."""
    query = (
        select(Staff)
        .join(StaffService, StaffService.staff_id == Staff.id)
        .where(
            Staff.branch_id == branch_id,
            Staff.active.is_(True),
            StaffService.service_id == service_id,
        )
    )
    if staff_id is not None:
        query = query.where(Staff.id == staff_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_branch_hours_for_day(db: AsyncSession, branch_id: int, day_of_week: int) -> BranchHours | None:
    result = await db.execute(
        select(BranchHours).where(
            BranchHours.branch_id == branch_id,
            BranchHours.day_of_week == day_of_week,
        )
    )
    return result.scalar_one_or_none()


async def get_staff_hours_for_day(db: AsyncSession, staff_id: int, day_of_week: int) -> StaffHours | None:
    """Returns None if the staff member has no override -- caller
    should fall back to branch hours in that case."""
    result = await db.execute(
        select(StaffHours).where(
            StaffHours.staff_id == staff_id,
            StaffHours.day_of_week == day_of_week,
        )
    )
    return result.scalar_one_or_none()


async def get_staff_time_off(db: AsyncSession, staff_id: int, target_date: date) -> StaffTimeOff | None:
    result = await db.execute(
        select(StaffTimeOff).where(
            StaffTimeOff.staff_id == staff_id,
            StaffTimeOff.start_date <= target_date,
            StaffTimeOff.end_date >= target_date,
        )
    )
    return result.scalar_one_or_none()


async def get_booked_appointments(db: AsyncSession, staff_id: int, target_date: date) -> list[Appointment]:
    """Existing, non-cancelled appointments for one staff member on one
    date -- these are the windows a new slot must not overlap."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.staff_id == staff_id,
            Appointment.status == "booked",
            Appointment.start_time >= target_date,
            Appointment.start_time < date.fromordinal(target_date.toordinal() + 1),
        )
    )
    return list(result.scalars().all())

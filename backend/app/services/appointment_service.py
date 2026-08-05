"""
Create Appointment service -- the write side of the two-way loop.
Never trusts that a slot checked via check_availability a moment ago is
still open: re-validates against live data in the same request before
writing anything. This is what actually prevents double-booking when
two callers (or a phone caller and a web booking) go for the same slot
at nearly the same time.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import appointment_repository as write_repo
from app.repositories import availability_repository as avail_repo
from app.repositories import business_info_repository as info_repo
from app.schemas.appointments import CreateAppointmentResponse
from app.services.booking_service import _get_working_window, _overlaps_any, combine_aware


class ServiceNotFoundError(Exception):
    pass


class BranchNotFoundError(Exception):
    pass


class SlotNoLongerAvailableError(Exception):
    """Raised when the requested slot -- or any eligible staff member's
    version of it -- is no longer actually open by the time we tried to
    book it. The caller should be told to pick a different time, not
    have this silently succeed against stale data."""

    pass


class CustomerDoubleBookedError(Exception):
    """Raised when the requested time would overlap another active
    appointment THIS SAME CUSTOMER already has, even with a different
    staff member. Staff-level availability alone doesn't catch this --
    two different barbers can both be free at 10:30, but the same
    caller obviously can't be in two chairs at once."""

    pass


async def create_appointment(
    db: AsyncSession,
    branch_id: int,
    service_id: int,
    target_date: date,
    start_time: time,
    staff_id: int | None,
    customer_name: str,
    customer_phone: str,
) -> CreateAppointmentResponse:
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found or inactive")
    branch, chain = branch_and_chain

    service = await avail_repo.get_service(db, service_id, branch_id)
    if service is None:
        raise ServiceNotFoundError(f"Service {service_id} not found or inactive for branch {branch_id}")

    candidate_staff = await avail_repo.get_eligible_staff(db, branch_id, service_id, staff_id)
    if not candidate_staff:
        raise SlotNoLongerAvailableError("No eligible staff for this service")

    day_of_week = (target_date.weekday() + 1) % 7
    requested_start = combine_aware(target_date, start_time, branch.timezone)
    requested_end = requested_start + timedelta(minutes=service.duration_minutes)

    chosen_staff = None
    for staff in candidate_staff:
        window = await _get_working_window(db, branch_id, staff.id, day_of_week)
        if window is None:
            continue
        open_time, close_time = window
        if not (open_time <= start_time and requested_end.time() <= close_time):
            continue  # requested time falls outside working hours

        if await avail_repo.get_staff_time_off(db, staff.id, target_date):
            continue

        booked = await avail_repo.get_booked_appointments(db, staff.id, target_date)
        busy_windows = [(a.start_time, a.end_time) for a in booked]
        if _overlaps_any(requested_start, requested_end, busy_windows, buffer_minutes=0):
            continue  # someone else booked this exact window since it was last checked

        chosen_staff = staff
        break

    if chosen_staff is None:
        raise SlotNoLongerAvailableError(
            f"The {start_time} slot on {target_date} is no longer available for this service"
        )

    customer = await write_repo.get_or_create_customer(db, chain.id, customer_phone, customer_name)

    # This customer's OWN other appointments on this date -- checked
    # separately from staff-level availability, since two different
    # staff being free at the same time doesn't mean this customer can
    # be in two places at once.
    existing = await write_repo.get_customer_appointments_on_date(db, customer.id, target_date, branch.timezone)
    existing_windows = [(a.start_time, a.end_time) for a in existing]
    if _overlaps_any(requested_start, requested_end, existing_windows, buffer_minutes=0):
        raise CustomerDoubleBookedError(
            f"Customer {customer.id} already has an overlapping appointment on {target_date}"
        )

    appointment = await write_repo.insert_appointment(
        db,
        branch_id=branch_id,
        staff_id=chosen_staff.id,
        customer_id=customer.id,
        start_time=requested_start,
        end_time=requested_end,
    )

    await write_repo.insert_customer_service(
        db,
        customer_id=customer.id,
        chain_id=chain.id,
        branch_id=branch_id,
        appointment_id=appointment.id,
        service_id=service.id,
        staff_id=chosen_staff.id,
        price_at_booking=float(service.price_min),  # snapshot; exact final price confirmed in person if it's a range
        performed_at=requested_start,
    )

    await db.commit()

    return CreateAppointmentResponse(
        appointment_id=appointment.id,
        confirmed=True,
        staff_id=chosen_staff.id,
        staff_name=chosen_staff.name,
        service_name=service.name,
        date=target_date,
        start_time=start_time,
        end_time=requested_end.astimezone(ZoneInfo(branch.timezone)).time(),
        message=(
            f"You're all set: a {service.name} with {chosen_staff.name} on "
            f"{target_date.strftime('%A, %B %-d')} at {start_time.strftime('%-I:%M %p')}."
        ),
    )

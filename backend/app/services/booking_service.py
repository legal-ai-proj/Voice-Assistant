"""
Booking Service -- the single source of truth for availability logic.
Both the web booking widget and the Vapi voice tool call into this same
function, which is what actually prevents double-booking between
channels. Nothing outside this module should compute availability by
hand.
"""

from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import availability_repository as repo
from app.schemas.availability import AvailableSlot, CheckAvailabilityResponse

SLOT_INCREMENT_MINUTES = 15


def combine_aware(target_date: date, t: time, tz_name: str) -> datetime:
    """Build a timezone-aware datetime from a date + time in a branch's
    local timezone. Postgres returns timestamptz values as tz-aware, so
    everything we construct in Python for comparison against them must
    be tz-aware too -- mixing naive and aware datetimes raises TypeError.
    Defaults to UTC if the branch's tz string is somehow invalid, rather
    than falling back to naive (which would just reintroduce the bug)."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.combine(target_date, t, tzinfo=tz)


class ServiceNotFoundError(Exception):
    pass


class NoEligibleStaffError(Exception):
    pass


async def check_availability(
    db: AsyncSession,
    branch_id: UUID,
    service_id: UUID,
    target_date: date,
    staff_id: UUID | None,
    booking_buffer_minutes: int = 0,
) -> CheckAvailabilityResponse:
    service = await repo.get_service(db, service_id, branch_id)
    if service is None:
        raise ServiceNotFoundError(f"Service {service_id} not found or inactive for branch {branch_id}")

    eligible_staff = await repo.get_eligible_staff(db, branch_id, service_id, staff_id)
    if not eligible_staff:
        raise NoEligibleStaffError(
            f"No active staff at branch {branch_id} can perform service {service_id}"
            + (f" (requested staff {staff_id} specifically)" if staff_id else "")
        )

    day_of_week = (target_date.weekday() + 1) % 7  # Python: Mon=0..Sun=6 -> our schema: Sun=0..Sat=6

    # Branch timezone is needed so the datetimes we build for overlap
    # comparison are tz-aware, matching what Postgres returns for the
    # existing appointments' timestamptz columns.
    branch = await repo.get_branch(db, branch_id)
    tz_name = branch.timezone if branch else "UTC"

    all_slots: list[AvailableSlot] = []
    for staff in eligible_staff:
        window = await _get_working_window(db, branch_id, staff.id, day_of_week)
        if window is None:
            continue  # closed that day, either at branch or staff level

        if await repo.get_staff_time_off(db, staff.id, target_date):
            continue  # staff is off that day entirely

        booked = await repo.get_booked_appointments(db, staff.id, target_date)
        busy_windows = [(a.start_time, a.end_time) for a in booked]

        open_time, close_time = window
        for slot_start in _iter_slots(target_date, open_time, close_time, service.duration_minutes, tz_name):
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)
            if _overlaps_any(slot_start, slot_end, busy_windows, booking_buffer_minutes):
                continue
            all_slots.append(AvailableSlot(staff_id=staff.id, staff_name=staff.name, start_time=slot_start.time()))

    all_slots.sort(key=lambda s: s.start_time)

    return CheckAvailabilityResponse(
        date=target_date,
        service_name=service.name,
        duration_minutes=service.duration_minutes,
        slots=all_slots,
        message=_build_speakable_message(all_slots, service.name, target_date),
    )


async def _get_working_window(
    db: AsyncSession, branch_id: UUID, staff_id: UUID, day_of_week: int
) -> tuple[time, time] | None:
    """Staff-level hours override branch hours if present for that day.
    Returns None if closed (either explicitly, or no hours configured
    at all for that day -- fails closed, never assumes open)."""
    staff_hours = await repo.get_staff_hours_for_day(db, staff_id, day_of_week)
    if staff_hours is not None:
        if staff_hours.is_off or staff_hours.start_time is None or staff_hours.end_time is None:
            return None
        return staff_hours.start_time, staff_hours.end_time

    branch_hours = await repo.get_branch_hours_for_day(db, branch_id, day_of_week)
    if branch_hours is None or branch_hours.is_closed or branch_hours.open_time is None:
        return None
    return branch_hours.open_time, branch_hours.close_time


def _iter_slots(target_date: date, open_time: time, close_time: time, duration_minutes: int, tz_name: str):
    cursor = combine_aware(target_date, open_time, tz_name)
    end_of_day = combine_aware(target_date, close_time, tz_name)
    last_possible_start = end_of_day - timedelta(minutes=duration_minutes)
    while cursor <= last_possible_start:
        yield cursor
        cursor += timedelta(minutes=SLOT_INCREMENT_MINUTES)


def _overlaps_any(
    slot_start: datetime,
    slot_end: datetime,
    busy_windows: list[tuple[datetime, datetime]],
    buffer_minutes: int,
) -> bool:
    buffer = timedelta(minutes=buffer_minutes)
    for busy_start, busy_end in busy_windows:
        if slot_start < (busy_end + buffer) and (slot_end + buffer) > busy_start:
            return True
    return False


def _build_speakable_message(slots: list[AvailableSlot], service_name: str, target_date: date) -> str:
    if not slots:
        return f"Nothing's open for {service_name} on {target_date.strftime('%A, %B %-d')}."
    times = ", ".join(s.start_time.strftime("%-I:%M %p") for s in slots[:5])
    return f"For {service_name} on {target_date.strftime('%A, %B %-d')}, open times include {times}."

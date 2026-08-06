"""
Multi-service booking service. Books multiple services for the same visit
in a single transaction -- same barber, sequential times, one DB round-trip.

This eliminates the pattern of calling create_appointment N times for N
services, which introduced ECONNRESET risk on each call and required the
model to track end_time between calls. One call, one transaction, one
confirmation message back.

If any service in the list fails (slot gone, staff not eligible, etc.),
the whole transaction rolls back -- no partial bookings that leave the
customer with a haircut but no beard trim.
"""

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import appointment_repository as write_repo
from app.repositories import availability_repository as avail_repo
from app.repositories import business_info_repository as info_repo
from app.schemas.appointments import (
    CreateAppointmentsRequest,
    CreateAppointmentsResponse,
    ServiceBookingResult,
)
from app.services.booking_service import _get_working_window, _overlaps_any, combine_aware


class BranchNotFoundError(Exception):
    pass


class ServiceNotFoundError(Exception):
    pass


class SlotNotAvailableError(Exception):
    pass


async def create_appointments(
    db: AsyncSession,
    branch_id: int,
    payload: CreateAppointmentsRequest,
) -> CreateAppointmentsResponse:
    """Book all services in payload.services atomically.
    Same staff member for all. Each service starts where the previous ends."""

    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found")
    branch, chain = branch_and_chain
    tz_name = branch.timezone

    # Resolve customer once
    customer = await write_repo.get_or_create_customer(
        db, chain.id, payload.customer_phone, payload.customer_name
    )

    bookings: list[ServiceBookingResult] = []
    busy_windows = []  # grows as we book each service in this visit

    # The chosen staff member -- resolved on the first service, reused for all
    chosen_staff = None

    # Track current start time -- first service uses payload start_time,
    # subsequent services use the previous service's end_time automatically
    next_start: time | None = None

    for i, svc_booking in enumerate(payload.services):
        service = await avail_repo.get_service(db, svc_booking.service_id, branch_id)
        if service is None:
            raise ServiceNotFoundError(
                f"Service {svc_booking.service_id} not found for branch {branch_id}"
            )

        # First service uses the caller-provided start_time.
        # Subsequent services start exactly where the previous ended.
        start_time = svc_booking.start_time if i == 0 else next_start
        if start_time is None:
            start_time = svc_booking.start_time

        slot_start = combine_aware(payload.date, start_time, tz_name)
        slot_end = slot_start + timedelta(minutes=service.duration_minutes)
        day_of_week = (payload.date.weekday() + 1) % 7

        if chosen_staff is None:
            # Pick a staff member for the first service — reuse for all others
            candidates = await avail_repo.get_eligible_staff(
                db, branch_id, service.id, payload.staff_id
            )
            if not candidates:
                raise SlotNotAvailableError(f"No eligible staff for service {service.name}")

            for candidate in candidates:
                window = await _get_working_window(db, branch_id, candidate.id, day_of_week)
                if window is None:
                    continue
                open_t, close_t = window
                if not (open_t <= start_time and slot_end.time() <= close_t):
                    continue
                if await avail_repo.get_staff_time_off(db, candidate.id, payload.date):
                    continue

                existing = await avail_repo.get_booked_appointments(db, candidate.id, payload.date)
                existing_windows = [(a.start_time, a.end_time) for a in existing]
                all_busy = existing_windows + busy_windows

                if _overlaps_any(slot_start, slot_end, all_busy, buffer_minutes=0):
                    continue

                chosen_staff = candidate
                break

            if chosen_staff is None:
                raise SlotNotAvailableError(
                    f"No available staff for {service.name} at {start_time} on {payload.date}"
                )
        else:
            # Reuse the same staff — just validate they're free at this new time
            window = await _get_working_window(db, branch_id, chosen_staff.id, day_of_week)
            if window is None:
                raise SlotNotAvailableError(
                    f"{chosen_staff.name} isn't working when the {service.name} would be scheduled"
                )
            open_t, close_t = window
            if not (open_t <= start_time and slot_end.time() <= close_t):
                raise SlotNotAvailableError(
                    f"{service.name} at {start_time} falls outside {chosen_staff.name}'s working hours"
                )

            existing = await avail_repo.get_booked_appointments(db, chosen_staff.id, payload.date)
            existing_windows = [(a.start_time, a.end_time) for a in existing]
            all_busy = existing_windows + busy_windows
            if _overlaps_any(slot_start, slot_end, all_busy, buffer_minutes=0):
                raise SlotNotAvailableError(
                    f"{chosen_staff.name} is no longer available at {start_time} for {service.name}"
                )

        # Book it
        appointment = await write_repo.insert_appointment(
            db,
            branch_id=branch_id,
            staff_id=chosen_staff.id,
            customer_id=customer.id,
            start_time=slot_start,
            end_time=slot_end,
        )
        await write_repo.insert_customer_service(
            db,
            customer_id=customer.id,
            chain_id=chain.id,
            branch_id=branch_id,
            appointment_id=appointment.id,
            service_id=service.id,
            staff_id=chosen_staff.id,
            price_at_booking=float(service.price_min),
            performed_at=slot_start,
        )

        bookings.append(ServiceBookingResult(
            appointment_id=appointment.id,
            service_name=service.name,
            staff_id=chosen_staff.id,
            staff_name=chosen_staff.name,
            date=payload.date,
            start_time=ZoneInfo(tz_name) and slot_start.astimezone(ZoneInfo(tz_name)).time(),
            end_time=slot_end.astimezone(ZoneInfo(tz_name)).time(),
        ))

        # Next service starts exactly when this one ends
        next_start = slot_end.astimezone(ZoneInfo(tz_name)).time()
        # Track this booking so the next service's overlap check sees it
        busy_windows.append((slot_start, slot_end))

    await db.commit()

    # Build one speakable summary for all bookings
    if len(bookings) == 1:
        b = bookings[0]
        message = (
            f"Done — {b.service_name} with {b.staff_name} on "
            f"{payload.date.strftime('%A, %B %-d')} at {b.start_time.strftime('%-I:%M %p')}."
        )
    else:
        parts = ", ".join(
            f"{b.service_name} at {b.start_time.strftime('%-I:%M %p')}" for b in bookings
        )
        message = (
            f"Done — {parts} with {bookings[0].staff_name} on "
            f"{payload.date.strftime('%A, %B %-d')}."
        )

    return CreateAppointmentsResponse(
        confirmed=True,
        bookings=bookings,
        message=message,
    )

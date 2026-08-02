"""
Appointment-management service layer: lookup, reschedule, cancel, and
take_message. Reschedule re-validates the new slot server-side (same
race-condition protection as create_appointment) before moving anything.
Cancel is a soft status change ('cancelled'), never a hard delete, so
the record survives for reporting and no-show tracking.
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import appointment_management_repository as mgmt_repo
from app.repositories import availability_repository as avail_repo
from app.repositories import business_info_repository as info_repo
from app.schemas.appointment_management import (
    AppointmentSummary,
    CancelAppointmentResponse,
    LookupAppointmentResponse,
    RescheduleAppointmentResponse,
    TakeMessageResponse,
)
from app.services.booking_service import _get_working_window, _overlaps_any, combine_aware


class BranchNotFoundError(Exception):
    pass


class AppointmentNotFoundError(Exception):
    pass


class SlotNoLongerAvailableError(Exception):
    pass


class AlreadyCancelledError(Exception):
    pass


def _fmt_date(d: date) -> str:
    return d.strftime("%A, %B %-d")


def _fmt_time(t: time) -> str:
    return t.strftime("%-I:%M %p")


async def lookup_appointment(db: AsyncSession, branch_id: UUID, customer_phone: str) -> LookupAppointmentResponse:
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found or inactive")
    _, chain = branch_and_chain

    customer, rows = await mgmt_repo.find_upcoming_appointments_by_phone(
        db, branch_id, chain.id, customer_phone, datetime.now(timezone.utc)
    )

    if customer is None or not rows:
        return LookupAppointmentResponse(
            found=False,
            customer_name=customer.name if customer else None,
            appointments=[],
            message="I don't see any upcoming appointments under that number.",
        )

    summaries = [
        AppointmentSummary(
            appointment_id=appt.id,
            service_name=svc.name,
            staff_name=staff.name if staff else None,
            date=appt.start_time.date(),
            start_time=appt.start_time.time(),
            status=appt.status,
        )
        for appt, svc, staff in rows
    ]

    if len(summaries) == 1:
        s = summaries[0]
        with_staff = f" with {s.staff_name}" if s.staff_name else ""
        msg = f"I found one upcoming appointment: a {s.service_name}{with_staff} on {_fmt_date(s.date)} at {_fmt_time(s.start_time)}."
    else:
        msg = f"I found {len(summaries)} upcoming appointments under that number."

    return LookupAppointmentResponse(
        found=True, customer_name=customer.name, appointments=summaries, message=msg
    )


async def reschedule_appointment(
    db: AsyncSession, branch_id: UUID, appointment_id: UUID, target_date: date, start_time: time
) -> RescheduleAppointmentResponse:
    appointment = await mgmt_repo.get_appointment(db, appointment_id)
    if appointment is None or appointment.branch_id != branch_id or appointment.status != "booked":
        raise AppointmentNotFoundError(f"No active appointment {appointment_id} at branch {branch_id}")

    service = await mgmt_repo.get_service_for_appointment(db, appointment_id)
    if service is None:
        raise AppointmentNotFoundError(f"Could not resolve service for appointment {appointment_id}")

    day_of_week = (target_date.weekday() + 1) % 7
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    tz_name = branch_and_chain[0].timezone if branch_and_chain else "UTC"
    new_start = combine_aware(target_date, start_time, tz_name)
    new_end = new_start + timedelta(minutes=service.duration_minutes)

    # The appointment keeps its assigned staff member; re-validate that
    # THAT staff member is free at the new time (excluding this same
    # appointment's current slot, so moving it by 15 min doesn't collide
    # with itself).
    staff_id = appointment.staff_id
    if staff_id is None:
        raise SlotNoLongerAvailableError("Appointment has no assigned staff to re-validate against")

    window = await _get_working_window(db, branch_id, staff_id, day_of_week)
    if window is None:
        raise SlotNoLongerAvailableError("Staff isn't working at the requested new time")
    open_time, close_time = window
    if not (open_time <= start_time and new_end.time() <= close_time):
        raise SlotNoLongerAvailableError("Requested new time is outside working hours")

    if await avail_repo.get_staff_time_off(db, staff_id, target_date):
        raise SlotNoLongerAvailableError("Staff is off on the requested new date")

    booked = await avail_repo.get_booked_appointments(db, staff_id, target_date)
    busy = [(a.start_time, a.end_time) for a in booked if a.id != appointment_id]
    if _overlaps_any(new_start, new_end, busy, buffer_minutes=0):
        raise SlotNoLongerAvailableError("That new time was just taken")

    await mgmt_repo.update_appointment_time(db, appointment, new_start, new_end)
    await db.commit()

    staff_row = await mgmt_repo.get_staff(db, staff_id)
    staff_name = staff_row.name if staff_row else "your barber"

    return RescheduleAppointmentResponse(
        appointment_id=appointment.id,
        confirmed=True,
        service_name=service.name,
        staff_name=staff_name,
        date=target_date,
        start_time=start_time,
        message=f"Done — I've moved your {service.name} with {staff_name} to {_fmt_date(target_date)} at {_fmt_time(start_time)}.",
    )


async def cancel_appointment(db: AsyncSession, branch_id: UUID, appointment_id: UUID) -> CancelAppointmentResponse:
    appointment = await mgmt_repo.get_appointment(db, appointment_id)
    if appointment is None or appointment.branch_id != branch_id:
        raise AppointmentNotFoundError(f"No appointment {appointment_id} at branch {branch_id}")
    if appointment.status == "cancelled":
        raise AlreadyCancelledError(f"Appointment {appointment_id} is already cancelled")

    await mgmt_repo.set_appointment_status(db, appointment, "cancelled")
    await db.commit()

    return CancelAppointmentResponse(
        appointment_id=appointment.id,
        cancelled=True,
        message="Okay, I've cancelled that appointment for you.",
    )


async def take_message(
    db: AsyncSession, branch_id: UUID, caller_name: str | None, caller_phone: str | None, message_body: str
) -> TakeMessageResponse:
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found or inactive")

    msg = await mgmt_repo.insert_message(db, branch_id, caller_name, caller_phone, message_body)
    await db.commit()

    return TakeMessageResponse(
        message_id=msg.id,
        saved=True,
        message="Got it — I've passed that along to the team.",
    )

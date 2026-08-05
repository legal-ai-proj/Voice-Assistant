"""
Appointment-management service layer: lookup, reschedule, cancel, and
take_message. Reschedule re-validates the new slot server-side (same
race-condition protection as create_appointment) before moving anything.
Cancel is a soft status change ('cancelled'), never a hard delete, so
the record survives for reporting and no-show tracking.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import appointment_management_repository as mgmt_repo
from app.repositories import appointment_repository as write_repo
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


class CustomerDoubleBookedError(Exception):
    """Raised when a reschedule would overlap another active appointment
    THIS SAME CUSTOMER already has, even with a different staff member."""

    pass


class ServiceChangeNotAllowedError(Exception):
    """The requested new service is invalid, or the appointment's barber
    can't perform it -- the caller should cancel and rebook instead."""

    pass


class AlreadyCancelledError(Exception):
    pass


def _fmt_date(d: date) -> str:
    return d.strftime("%A, %B %-d")


def _fmt_time(t: time) -> str:
    return t.strftime("%-I:%M %p")


async def lookup_appointment(db: AsyncSession, branch_id: int, customer_phone: str) -> LookupAppointmentResponse:
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    if branch_and_chain is None:
        raise BranchNotFoundError(f"Branch {branch_id} not found or inactive")
    branch, chain = branch_and_chain

    # Times are stored in UTC (timestamptz); convert to the branch's own
    # timezone before showing them to the caller, so a booking made for
    # 1 PM local reads back as "1 PM", not the stored UTC hour.
    try:
        branch_tz = ZoneInfo(branch.timezone)
    except Exception:
        branch_tz = ZoneInfo("UTC")

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

    summaries = []
    for appt, svc, staff in rows:
        # appt.start_time is tz-aware UTC from Postgres; shift to local.
        local_start = appt.start_time.astimezone(branch_tz)
        summaries.append(
            AppointmentSummary(
                appointment_id=appt.id,
                service_name=svc.name,
                staff_name=staff.name if staff else None,
                date=local_start.date(),
                start_time=local_start.time(),
                status=appt.status,
            )
        )

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
    db: AsyncSession,
    branch_id: int,
    appointment_id: int,
    target_date: date,
    start_time: time,
    new_service_id: int | None = None,
) -> RescheduleAppointmentResponse:
    appointment = await mgmt_repo.get_appointment(db, appointment_id)
    if appointment is None or appointment.branch_id != branch_id or appointment.status != "booked":
        raise AppointmentNotFoundError(f"No active appointment {appointment_id} at branch {branch_id}")

    current_service = await mgmt_repo.get_service_for_appointment(db, appointment_id)
    if current_service is None:
        raise AppointmentNotFoundError(f"Could not resolve service for appointment {appointment_id}")

    # If the caller is also changing the service, switch to the new one --
    # and crucially use ITS duration for slot re-validation, since a
    # 15-min beard trim becoming a 45-min fade needs a bigger window and
    # would otherwise silently create a scheduling conflict.
    service_changed = new_service_id is not None and new_service_id != current_service.id
    if service_changed:
        service = await avail_repo.get_service(db, new_service_id, branch_id)
        if service is None:
            raise ServiceChangeNotAllowedError(f"Service {new_service_id} not found or inactive at branch {branch_id}")
    else:
        service = current_service

    staff_id = appointment.staff_id
    if staff_id is None:
        raise SlotNoLongerAvailableError("Appointment has no assigned staff to re-validate against")

    # If the service changed, confirm the appointment's assigned barber
    # can actually perform the new service -- don't silently keep a
    # barber booked for something they don't do.
    if service_changed:
        eligible = await avail_repo.get_eligible_staff(db, branch_id, service.id, staff_id)
        if not eligible:
            raise ServiceChangeNotAllowedError(
                "The barber on this appointment doesn't perform the new service; "
                "the caller should cancel and rebook with an eligible barber."
            )

    day_of_week = (target_date.weekday() + 1) % 7
    branch_and_chain = await info_repo.get_branch_with_chain(db, branch_id)
    tz_name = branch_and_chain[0].timezone if branch_and_chain else "UTC"
    new_start = combine_aware(target_date, start_time, tz_name)
    new_end = new_start + timedelta(minutes=service.duration_minutes)

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

    # This customer's OWN other appointments on this date, excluding the
    # one being rescheduled -- catches the case where rescheduling would
    # overlap something else the same customer already has booked, even
    # with a different staff member. A real call hit this exactly:
    # rescheduled two of one customer's appointments to the same
    # overlapping time because each staff member individually had that
    # slot open.
    customer_appts = await write_repo.get_customer_appointments_on_date(
        db, appointment.customer_id, target_date, tz_name, exclude_appointment_id=appointment_id
    )
    customer_windows = [(a.start_time, a.end_time) for a in customer_appts]
    if _overlaps_any(new_start, new_end, customer_windows, buffer_minutes=0):
        raise CustomerDoubleBookedError(
            f"Customer {appointment.customer_id} already has an overlapping appointment on {target_date}"
        )

    # Update the appointment row (new end_time reflects the possibly-new duration)...
    await mgmt_repo.update_appointment_time(db, appointment, new_start, new_end)

    # ...and if the service changed, update the customer_services record
    # so the appointment and its recorded service/price stay in sync.
    if service_changed:
        await mgmt_repo.update_appointment_service(
            db,
            appointment_id=appointment_id,
            new_service_id=service.id,
            new_price=float(service.price_min),
            performed_at=new_start,
        )

    await db.commit()

    staff_row = await mgmt_repo.get_staff(db, staff_id)
    staff_name = staff_row.name if staff_row else "your barber"

    if service_changed:
        msg = (
            f"Done — I've updated your appointment to a {service.name} with {staff_name} "
            f"on {_fmt_date(target_date)} at {_fmt_time(start_time)}."
        )
    else:
        msg = f"Done — I've moved your {service.name} with {staff_name} to {_fmt_date(target_date)} at {_fmt_time(start_time)}."

    return RescheduleAppointmentResponse(
        appointment_id=appointment.id,
        confirmed=True,
        service_name=service.name,
        staff_name=staff_name,
        date=target_date,
        start_time=start_time,
        message=msg,
    )


async def cancel_appointment(db: AsyncSession, branch_id: int, appointment_id: int) -> CancelAppointmentResponse:
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
    db: AsyncSession, branch_id: int, caller_name: str | None, caller_phone: str | None, message_body: str
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

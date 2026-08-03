"""
Data access for create_appointment -- the write side. Two things live
here: finding-or-creating a customer by phone (the identity key, per
the platform's design), and the actual appointment/customer_service
inserts.
"""

import uuid
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Appointment, Customer, CustomerService
from app.services.booking_service import combine_aware


async def get_customer_appointments_on_date(
    db: AsyncSession, customer_id: UUID, target_date: date, tz_name: str, exclude_appointment_id: UUID | None = None
) -> list[Appointment]:
    """All of this customer's other active (booked) appointments on a
    given date -- used to prevent double-booking the SAME PERSON into
    two overlapping slots, even with two different staff members. A
    real call did exactly this: rescheduled two of one customer's
    appointments (with different barbers) to the same overlapping time,
    since staff-level availability checks alone don't catch it -- Abe
    being free at 10:30 and Marco being free at 10:30 doesn't mean the
    CALLER can be in both chairs at once.

    Uses combine_aware (not datetime.combine) for the day-boundary
    comparison, since Appointment.start_time is tz-aware (timestamptz)
    -- comparing against a naive datetime would raise the same
    offset-naive/aware TypeError fixed earlier in booking_service.py."""
    from datetime import time as time_type

    day_start = combine_aware(target_date, time_type.min, tz_name)
    day_end = day_start + timedelta(days=1)

    query = select(Appointment).where(
        Appointment.customer_id == customer_id,
        Appointment.status == "booked",
        Appointment.start_time >= day_start,
        Appointment.start_time < day_end,
    )
    if exclude_appointment_id is not None:
        query = query.where(Appointment.id != exclude_appointment_id)

    result = await db.execute(query)
    return list(result.scalars().all())
    result = await db.execute(select(Customer).where(Customer.chain_id == chain_id, Customer.phone == phone))
    customer = result.scalar_one_or_none()
    if customer is not None:
        # Update the name if it changed -- callers occasionally correct
        # a mis-heard name on a later call; don't silently keep the old one.
        if name and customer.name != name:
            customer.name = name
        return customer

    customer = Customer(id=uuid.uuid4(), chain_id=chain_id, phone=phone, name=name)
    db.add(customer)
    await db.flush()  # populate customer.id without committing yet
    return customer


async def insert_appointment(
    db: AsyncSession,
    branch_id: UUID,
    staff_id: UUID,
    customer_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> Appointment:
    appointment = Appointment(
        id=uuid.uuid4(),
        branch_id=branch_id,
        staff_id=staff_id,
        customer_id=customer_id,
        start_time=start_time,
        end_time=end_time,
        status="booked",
        source="voice",
    )
    db.add(appointment)
    await db.flush()
    return appointment


async def insert_customer_service(
    db: AsyncSession,
    customer_id: UUID,
    chain_id: UUID,
    branch_id: UUID,
    appointment_id: UUID,
    service_id: UUID,
    staff_id: UUID,
    price_at_booking: float,
    performed_at: datetime,
) -> CustomerService:
    row = CustomerService(
        id=uuid.uuid4(),
        customer_id=customer_id,
        chain_id=chain_id,
        branch_id=branch_id,
        appointment_id=appointment_id,
        service_id=service_id,
        staff_id=staff_id,
        price_at_booking=price_at_booking,
        performed_at=performed_at,
    )
    db.add(row)
    await db.flush()
    return row

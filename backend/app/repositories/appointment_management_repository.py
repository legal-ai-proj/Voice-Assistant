"""
Data access for the appointment-management tools. Queries only, no
business logic. Reschedule/cancel operate on existing appointment rows;
lookup finds them by the caller's phone (the identity key).
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import (
    Appointment,
    Customer,
    CustomerService,
    Message,
    Service,
    Staff,
)


async def find_upcoming_appointments_by_phone(
    db: AsyncSession, branch_id: UUID, chain_id: UUID, phone: str, now: datetime
) -> tuple[Customer | None, list[tuple[Appointment, Service, Staff | None]]]:
    """Returns the matched customer (if any) and their upcoming, still-booked
    appointments at this branch, each joined with its service and staff."""
    cust_result = await db.execute(
        select(Customer).where(Customer.chain_id == chain_id, Customer.phone == phone)
    )
    customer = cust_result.scalar_one_or_none()
    if customer is None:
        return None, []

    result = await db.execute(
        select(Appointment, Service, Staff)
        .join(Service, Service.id == CustomerService.service_id)
        .join(CustomerService, CustomerService.appointment_id == Appointment.id)
        .outerjoin(Staff, Staff.id == Appointment.staff_id)
        .where(
            Appointment.branch_id == branch_id,
            Appointment.customer_id == customer.id,
            Appointment.status == "booked",
            Appointment.start_time >= now,
        )
        .order_by(Appointment.start_time)
    )
    rows = [(appt, svc, staff) for appt, svc, staff in result.all()]
    return customer, rows


async def get_appointment(db: AsyncSession, appointment_id: UUID) -> Appointment | None:
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    return result.scalar_one_or_none()


async def get_staff(db: AsyncSession, staff_id: UUID) -> Staff | None:
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    return result.scalar_one_or_none()


async def get_service_for_appointment(db: AsyncSession, appointment_id: UUID) -> Service | None:
    result = await db.execute(
        select(Service)
        .join(CustomerService, CustomerService.service_id == Service.id)
        .where(CustomerService.appointment_id == appointment_id)
    )
    return result.scalars().first()


async def update_appointment_time(
    db: AsyncSession, appointment: Appointment, start_time: datetime, end_time: datetime
) -> None:
    appointment.start_time = start_time
    appointment.end_time = end_time
    await db.flush()


async def set_appointment_status(db: AsyncSession, appointment: Appointment, status: str) -> None:
    appointment.status = status
    await db.flush()


async def insert_message(
    db: AsyncSession, branch_id: UUID, caller_name: str | None, caller_phone: str | None, body: str
) -> Message:
    msg = Message(
        id=uuid.uuid4(),
        branch_id=branch_id,
        caller_name=caller_name,
        caller_phone=caller_phone,
        message_body=body,
        status="new",
    )
    db.add(msg)
    await db.flush()
    return msg

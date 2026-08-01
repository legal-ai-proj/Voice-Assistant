"""
Data access for create_appointment -- the write side. Two things live
here: finding-or-creating a customer by phone (the identity key, per
the platform's design), and the actual appointment/customer_service
inserts.
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Appointment, Customer, CustomerService


async def get_or_create_customer(db: AsyncSession, chain_id: UUID, phone: str, name: str) -> Customer:
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

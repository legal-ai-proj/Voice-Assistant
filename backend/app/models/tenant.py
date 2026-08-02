"""
SQLAlchemy models for the tables the Booking Service depends on. These
mirror the Supabase schema exactly (see the Milestone 2 migrations) --
column names, types, and nullability must stay in sync with the live
database.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import ForeignKey, String, Boolean, Integer, Numeric, Date, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Chain(Base):
    __tablename__ = "chains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    vertical: Mapped[str] = mapped_column(String)


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    name: Mapped[str] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    hours: Mapped[list["BranchHours"]] = relationship(back_populates="branch")
    staff: Mapped[list["Staff"]] = relationship(back_populates="branch")
    services: Mapped[list["Service"]] = relationship(back_populates="branch")


class BranchHours(Base):
    __tablename__ = "branch_hours"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0 = Sunday ... 6 = Saturday
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    branch: Mapped["Branch"] = relationship(back_populates="hours")


class BranchSettings(Base):
    __tablename__ = "branch_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    cancellation_policy: Mapped[str | None] = mapped_column(String)
    deposit_policy: Mapped[str | None] = mapped_column(String)
    booking_buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped["Branch"] = relationship(back_populates="staff")
    hours: Mapped[list["StaffHours"]] = relationship(back_populates="staff")
    time_off: Mapped[list["StaffTimeOff"]] = relationship(back_populates="staff")


class StaffHours(Base):
    """Optional override of branch_hours for one staff member. If a
    staff member has no rows here for a given day, they follow the
    branch's hours for that day instead."""

    __tablename__ = "staff_hours"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_off: Mapped[bool] = mapped_column(Boolean, default=False)

    staff: Mapped["Staff"] = relationship(back_populates="hours")


class StaffTimeOff(Base):
    __tablename__ = "staff_time_off"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String)

    staff: Mapped["Staff"] = relationship(back_populates="time_off")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_min: Mapped[float] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped["Branch"] = relationship(back_populates="services")


class StaffService(Base):
    """Which staff can perform which service -- the booking-eligibility
    join table (distinct from staff_specialties, which is descriptive)."""

    __tablename__ = "staff_services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    price_min: Mapped[float] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("chain_id", "phone", name="customers_chain_id_phone_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    phone: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="booked")
    source: Mapped[str] = mapped_column(String, default="voice")


class CustomerService(Base):
    """One row per service actually rendered on a visit -- doubles as
    the appointment<->service join and the queryable per-customer,
    per-branch, per-chain service history (see the schema design
    conversation: chain_id/branch_id are intentionally denormalized)."""

    __tablename__ = "customer_services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("appointments.id"))
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    price_at_booking: Mapped[float] = mapped_column(Numeric(10, 2))
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class Message(Base):
    """A message left for staff follow-up (the take_message tool)."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    caller_name: Mapped[str | None] = mapped_column(String)
    caller_phone: Mapped[str | None] = mapped_column(String)
    message_body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="new")


class CallLog(Base):
    """Structured record of a completed call (transcript, summary,
    outcome). Written by the end-of-call webhook handler."""

    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("appointments.id"))
    transcript: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(String)
    sentiment: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_url: Mapped[str | None] = mapped_column(String)
    outcome: Mapped[str | None] = mapped_column(String)
    cost: Mapped[float | None] = mapped_column(Numeric(10, 4))


class CallIngestionLog(Base):
    """Raw + extracted record of every Vapi webhook received. Logged
    FIRST, before any parsing/writing, so a call never vanishes even if
    downstream processing fails. See the Milestone 2 schema design."""

    __tablename__ = "call_ingestion_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    vapi_call_id: Mapped[str | None] = mapped_column(String)
    chain_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    processing_status: Mapped[str] = mapped_column(String, default="pending")
    processing_message: Mapped[str | None] = mapped_column(String)
    tables_written: Mapped[dict | None] = mapped_column(JSONB)
    customer_name: Mapped[str | None] = mapped_column(String)
    customer_phone: Mapped[str | None] = mapped_column(String)
    requested_date: Mapped[date | None] = mapped_column(Date)
    requested_time: Mapped[time | None] = mapped_column(Time)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("appointments.id"))
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)


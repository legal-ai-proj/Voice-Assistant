"""
SQLAlchemy models mirroring the Supabase schema.
All PKs are now bigint generated always as identity -- mapped as
Mapped[int] with init=False so SQLAlchemy never tries to insert a value
(the DB generates it). FK columns are plain int.
"""

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, Numeric, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Chain(Base):
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    vertical: Mapped[str] = mapped_column(String)


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chains.id"))
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    branch: Mapped["Branch"] = relationship(back_populates="hours")


class BranchSettings(Base):
    __tablename__ = "branch_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    cancellation_policy: Mapped[str | None] = mapped_column(String)
    deposit_policy: Mapped[str | None] = mapped_column(String)
    booking_buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped["Branch"] = relationship(back_populates="staff")
    hours: Mapped[list["StaffHours"]] = relationship(back_populates="staff")
    time_off: Mapped[list["StaffTimeOff"]] = relationship(back_populates="staff")


class StaffHours(Base):
    __tablename__ = "staff_hours"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_off: Mapped[bool] = mapped_column(Boolean, default=False)

    staff: Mapped["Staff"] = relationship(back_populates="hours")


class StaffTimeOff(Base):
    __tablename__ = "staff_time_off"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String)

    staff: Mapped["Staff"] = relationship(back_populates="time_off")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_min: Mapped[float] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped["Branch"] = relationship(back_populates="services")


class StaffService(Base):
    __tablename__ = "staff_services"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    service_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("services.id"))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    price_min: Mapped[float] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("chain_id", "phone", name="customers_chain_id_phone_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chains.id"))
    phone: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"))
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="booked")
    source: Mapped[str] = mapped_column(String, default="voice")


class CustomerService(Base):
    __tablename__ = "customer_services"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"))
    chain_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chains.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    appointment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("appointments.id"))
    service_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("services.id"))
    staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    price_at_booking: Mapped[float] = mapped_column(Numeric(10, 2))
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    caller_name: Mapped[str | None] = mapped_column(String)
    caller_phone: Mapped[str | None] = mapped_column(String)
    message_body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="new")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branches.id"))
    customer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("customers.id"))
    appointment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("appointments.id"))
    transcript: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(String)
    sentiment: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_url: Mapped[str | None] = mapped_column(String)
    outcome: Mapped[str | None] = mapped_column(String)
    cost: Mapped[float | None] = mapped_column(Numeric(10, 4))


class CallIngestionLog(Base):
    __tablename__ = "call_ingestion_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    vapi_call_id: Mapped[str | None] = mapped_column(String)
    chain_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("chains.id"))
    branch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("branches.id"))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    processing_status: Mapped[str] = mapped_column(String, default="pending")
    processing_message: Mapped[str | None] = mapped_column(String)
    tables_written: Mapped[dict | None] = mapped_column(JSONB)
    customer_name: Mapped[str | None] = mapped_column(String)
    customer_phone: Mapped[str | None] = mapped_column(String)
    requested_date: Mapped[date | None] = mapped_column(Date)
    requested_time: Mapped[time | None] = mapped_column(Time)
    appointment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("appointments.id"))
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)

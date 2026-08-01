"""
SQLAlchemy models for the tables that the Booking Service's availability
logic depends on. These mirror the Supabase schema exactly (see the
Milestone 2 migrations) -- column names, types, and nullability must
stay in sync with the live database.

Only the tables needed for check_availability are modeled here.
Customer/appointment-write models live in a separate module once
create_appointment is built.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import ForeignKey, String, Boolean, Integer, Numeric, Date, Time
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    name: Mapped[str] = mapped_column(String)
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


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("staff.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="booked")

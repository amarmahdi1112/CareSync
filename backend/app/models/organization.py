"""Legacy-compatible organization mapping."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.auth import User


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)
    organization_type: Mapped[str] = mapped_column(String(50), default="daycare")
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    primary_contact_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20))
    street_address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(50))
    postal_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(50), default="Canada")
    license_number: Mapped[str] = mapped_column(String(100), index=True)
    licensed_capacity: Mapped[int] = mapped_column(Integer)
    opening_time: Mapped[str] = mapped_column(String(10), default="07:00")
    closing_time: Mapped[str] = mapped_column(String(10), default="18:00")
    age_groups_served: Mapped[str] = mapped_column(Text, default="[]")
    logo_url: Mapped[str | None] = mapped_column(String(500))
    website: Mapped[str | None] = mapped_column(String(255))
    secondary_contact_name: Mapped[str | None] = mapped_column(String(255))
    secondary_contact_phone: Mapped[str | None] = mapped_column(String(20))
    secondary_contact_email: Mapped[str | None] = mapped_column(String(255))
    business_number: Mapped[str | None] = mapped_column(String(100))
    tax_id: Mapped[str | None] = mapped_column(String(100))
    insurance_provider: Mapped[str | None] = mapped_column(String(255))
    insurance_policy_number: Mapped[str | None] = mapped_column(String(100))
    insurance_expiry_date: Mapped[date | None] = mapped_column(Date)
    accreditation_status: Mapped[str] = mapped_column(String(50), default="none")
    accreditation_body: Mapped[str | None] = mapped_column(String(255))
    accreditation_expiry_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    programs_offered: Mapped[str] = mapped_column(Text, default="[]")
    billing_email: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(100), default="America/Edmonton")
    social_media: Mapped[str | None] = mapped_column(Text)
    subscription_plan: Mapped[str] = mapped_column(String(50), default="trial")
    subscription_expires_at: Mapped[date | None] = mapped_column(Date)
    trial_ends_at: Mapped[date | None] = mapped_column(Date)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    license_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
    notification_preferences: Mapped[str | None] = mapped_column(Text)
    system_preferences: Mapped[str | None] = mapped_column(Text)

    users: Mapped[list[User]] = relationship(back_populates="organization")

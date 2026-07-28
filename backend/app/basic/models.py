"""CareSync Basic persistence model.
These mappings are intentionally independent from ``generated_legacy``.  The
legacy mappings remain available to the explicitly enabled compatibility API;
new Basic databases are created exclusively from Alembic revisions targeting
this metadata.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.basic.programs import DAYCARE_PROGRAM_TYPE, OUT_OF_SCHOOL_CARE_PROGRAM_TYPE


def utc_now() -> datetime:
    return datetime.now(UTC)


def _lowercase_sha256_check(column_name: str) -> str:
    """Return a SQLite/PostgreSQL-portable lowercase SHA-256 check."""

    remainder = column_name
    for character in "0123456789abcdef":
        remainder = f"replace({remainder},'{character}','')"
    return (
        f"length({column_name}) = 64 AND {column_name} = lower({column_name}) "
        f"AND length({remainder}) = 0"
    )


def _opaque_storage_reference_check(column_name: str) -> str:
    """Return shallow portable traversal guards for private object keys.

    The vault parser applies the strict character allowlist.  Keeping the DB
    expression shallow avoids SQLite parser-stack exhaustion from deeply nested
    ``replace`` calls while still rejecting absolute and traversal-like keys.
    """

    return (
        f"{column_name} IS NULL OR (length({column_name}) BETWEEN 1 AND 500 "
        f"AND substr({column_name},1,1) NOT IN ('.','/','-','_') "
        f"AND {column_name} NOT LIKE '%//%' "
        f"AND {column_name} NOT IN ('.','..') "
        f"AND {column_name} NOT LIKE './%' AND {column_name} NOT LIKE '../%' "
        f"AND {column_name} NOT LIKE '%/./%' AND {column_name} NOT LIKE '%/../%' "
        f"AND {column_name} NOT LIKE '%/.' AND {column_name} NOT LIKE '%/..' "
        f"AND {column_name} NOT LIKE '%/')"
    )


def _media_type_check(column_name: str) -> str:
    """Mirror the strict lower-case ``type/subtype`` API media-type shape."""

    remainder = column_name
    for character in "abcdefghijklmnopqrstuvwxyz0123456789!#$&^_.+-/":
        remainder = f"replace({remainder},'{character}','')"
    first_remainder = f"substr({column_name},1,1)"
    for character in "abcdefghijklmnopqrstuvwxyz0123456789":
        first_remainder = f"replace({first_remainder},'{character}','')"
    valid_subtype_prefixes = " OR ".join(
        f"{column_name} LIKE '%/{character}%'"
        for character in "abcdefghijklmnopqrstuvwxyz0123456789"
    )
    return (
        f"{column_name} IS NULL OR (length({column_name}) BETWEEN 3 AND 100 "
        f"AND length({remainder}) = 0 AND length({first_remainder}) = 0 "
        f"AND length({column_name}) - length(replace({column_name},'/','')) = 1 "
        f"AND {column_name} NOT LIKE '%/' AND ({valid_subtype_prefixes}))"
    )


class BasicBase(DeclarativeBase):
    """Declarative base owned by the clean Basic migration history."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )


class User(TimestampMixin, BasicBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(email_verified_at IS NULL AND email_verification_method IS NULL) OR "
            "(email_verified_at IS NOT NULL AND email_verification_method IS NOT NULL)",
            name="ck_users_email_verification_pair",
        ),
        CheckConstraint("auth_version > 0", name="ck_users_auth_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verification_method: Mapped[str | None] = mapped_column(String(50))


class Organization(TimestampMixin, BasicBase):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','suspended','archived')",
            name="ck_organizations_status",
        ),
        CheckConstraint(
            "verification_status IN ('pending','under_review','verified','rejected')",
            name="ck_organizations_verification_status",
        ),
        CheckConstraint(
            "(verification_status = 'verified' AND verified_at IS NOT NULL AND "
            "verification_method IS NOT NULL) OR "
            "(verification_status IN ('pending','under_review','rejected') AND "
            "verified_at IS NULL AND "
            "verification_method IS NULL)",
            name="ck_organizations_verification_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending", nullable=False, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_method: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    timezone: Mapped[str] = mapped_column(String(100), default="America/Edmonton", nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Role(TimestampMixin, BasicBase):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_roles_org_id_id"),
        UniqueConstraint("organization_id", "key", name="uq_roles_org_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OrganizationMembership(TimestampMixin, BasicBase):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="RESTRICT",
            name="fk_memberships_org_role",
        ),
        UniqueConstraint("organization_id", "id", name="uq_memberships_org_id_id"),
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        CheckConstraint(
            "status IN ('invited','active','suspended','revoked')",
            name="ck_memberships_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OnboardingState(TimestampMixin, BasicBase):
    __tablename__ = "organization_onboarding"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','in_progress','complete')", name="ck_onboarding_status"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    current_step: Mapped[str] = mapped_column(String(50), default="organization", nullable=False)
    completed_steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    draft: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Facility(TimestampMixin, BasicBase):
    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_facilities_org_id_id"),
        UniqueConstraint("organization_id", "license_number", name="uq_facilities_org_license"),
        CheckConstraint("status IN ('draft','active','inactive')", name="ck_facilities_status"),
        CheckConstraint(
            "verification_status IN ('pending','under_review','verified','rejected')",
            name="ck_facilities_verification_status",
        ),
        CheckConstraint(
            "(verification_status = 'verified' AND verified_at IS NOT NULL AND "
            "verification_method IS NOT NULL) OR "
            "(verification_status IN ('pending','under_review','rejected') AND "
            "verified_at IS NULL AND "
            "verification_method IS NULL)",
            name="ck_facilities_verification_evidence",
        ),
        CheckConstraint("licensed_capacity >= 0", name="ck_facilities_capacity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending", nullable=False, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_method: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    street_address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(50), default="Alberta", nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(100), default="America/Edmonton", nullable=False)
    licensed_capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opening_time: Mapped[time | None] = mapped_column(Time)
    closing_time: Mapped[time | None] = mapped_column(Time)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    shift_clock_radius_meters: Mapped[int] = mapped_column(Integer, default=150, nullable=False)


class Program(TimestampMixin, BasicBase):
    __tablename__ = "facility_programs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="CASCADE",
            name="fk_programs_org_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_programs_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "id",
            name="uq_programs_org_facility_id",
        ),
        UniqueConstraint(
            "organization_id", "facility_id", "name", name="uq_programs_facility_name"
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "program_type",
            name="uq_programs_facility_type",
        ),
        CheckConstraint(
            f"program_type IN ('{DAYCARE_PROGRAM_TYPE}','{OUT_OF_SCHOOL_CARE_PROGRAM_TYPE}')",
            name="ck_programs_program_type",
        ),
        CheckConstraint("capacity >= 0", name="ck_programs_capacity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    program_type: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_age_months: Mapped[int | None] = mapped_column(Integer)
    maximum_age_months: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Room(TimestampMixin, BasicBase):
    __tablename__ = "rooms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="CASCADE",
            name="fk_rooms_org_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["facility_programs.organization_id", "facility_programs.id"],
            ondelete="RESTRICT",
            name="fk_rooms_org_program",
        ),
        UniqueConstraint("organization_id", "id", name="uq_rooms_org_id_id"),
        UniqueConstraint("organization_id", "facility_id", "id", name="uq_rooms_org_facility_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "program_id",
            "id",
            name="uq_rooms_org_facility_program_id",
        ),
        UniqueConstraint("organization_id", "facility_id", "name", name="uq_rooms_facility_name"),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity"),
        CheckConstraint(
            "(minimum_age_months IS NULL AND maximum_age_months IS NULL) OR "
            "(minimum_age_months IS NOT NULL AND maximum_age_months IS NOT NULL)",
            name="ck_rooms_age_range_pair",
        ),
        CheckConstraint(
            "minimum_age_months IS NULL OR minimum_age_months >= 0",
            name="ck_rooms_minimum_age",
        ),
        CheckConstraint(
            "maximum_age_months IS NULL OR maximum_age_months >= minimum_age_months",
            name="ck_rooms_age_range_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    program_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    age_group: Mapped[str | None] = mapped_column(String(100))
    minimum_age_months: Mapped[int | None] = mapped_column(Integer)
    maximum_age_months: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MembershipRoomAssignment(TimestampMixin, BasicBase):
    __tablename__ = "membership_room_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="CASCADE",
            name="fk_member_room_assignments_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_member_room_assignments_room",
        ),
        UniqueConstraint("organization_id", "id", name="uq_member_room_assignments_org_id"),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "room_id",
            name="uq_member_room_assignments_membership_room",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class StaffInvitation(TimestampMixin, BasicBase):
    __tablename__ = "staff_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="RESTRICT",
            name="fk_staff_invitations_role",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_invitations_org_id"),
        UniqueConstraint("token_hash", name="uq_staff_invitations_token_hash"),
        CheckConstraint(
            "accepted_at IS NULL OR revoked_at IS NULL",
            name="ck_staff_invitations_single_terminal_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class StaffInvitationRoom(BasicBase):
    __tablename__ = "staff_invitation_rooms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "invitation_id"],
            ["staff_invitations.organization_id", "staff_invitations.id"],
            ondelete="CASCADE",
            name="fk_staff_invitation_rooms_invitation",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_invitation_rooms_room",
        ),
        UniqueConstraint(
            "organization_id",
            "invitation_id",
            "room_id",
            name="uq_staff_invitation_rooms_invitation_room",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    invitation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PasswordResetChallenge(TimestampMixin, BasicBase):
    __tablename__ = "password_reset_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="CASCADE",
            name="fk_password_reset_challenges_membership",
        ),
        UniqueConstraint("organization_id", "id", name="uq_password_reset_challenges_org_id"),
        UniqueConstraint("token_hash", name="uq_password_reset_challenges_token_hash"),
        CheckConstraint(
            "consumed_at IS NULL OR revoked_at IS NULL",
            name="ck_password_reset_challenges_single_terminal_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class Family(TimestampMixin, BasicBase):
    __tablename__ = "families"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_families_org_id_id"),
        UniqueConstraint("organization_id", "file_number", name="uq_families_org_file_number"),
        CheckConstraint(
            "status IN ('pending','active','inactive','archived')", name="ck_families_status"
        ),
        CheckConstraint("version > 0", name="ck_families_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_number: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    additional_notes: Mapped[str | None] = mapped_column(Text)
    photo_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    field_trip_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_medical_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Guardian(TimestampMixin, BasicBase):
    __tablename__ = "guardians"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="CASCADE",
            name="fk_guardians_org_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_guardians_created_operation",
        ),
        ForeignKeyConstraint(
            ["organization_id", "retired_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_guardians_retired_operation",
        ),
        UniqueConstraint("organization_id", "id", name="uq_guardians_org_id_id"),
        UniqueConstraint("organization_id", "family_id", "id", name="uq_guardians_org_family_id"),
        Index(
            "uq_guardians_current_primary_slot",
            "organization_id",
            "family_id",
            "is_primary",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            sqlite_where=text("retired_at IS NULL"),
        ),
        CheckConstraint(
            "(retired_at IS NULL AND retired_operation_id IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
            name="ck_guardians_retirement_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    cell_phone: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    home_phone: Mapped[str | None] = mapped_column(String(30))
    work_phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorized_pickup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    @property
    def guardian_type(self) -> str:
        return "primary" if self.is_primary else "secondary"


class EmergencyContact(TimestampMixin, BasicBase):
    __tablename__ = "emergency_contacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="CASCADE",
            name="fk_contacts_org_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_contacts_created_operation",
        ),
        ForeignKeyConstraint(
            ["organization_id", "retired_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_contacts_retired_operation",
        ),
        UniqueConstraint("organization_id", "id", name="uq_contacts_org_id_id"),
        UniqueConstraint("organization_id", "family_id", "id", name="uq_contacts_org_family_id"),
        CheckConstraint(
            "(retired_at IS NULL AND retired_operation_id IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
            name="ck_contacts_retirement_pair",
        ),
        Index(
            "ix_contacts_current_family",
            "organization_id",
            "family_id",
            unique=False,
            postgresql_where=text("retired_at IS NULL"),
            sqlite_where=text("retired_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship: Mapped[str] = mapped_column(String(100), nullable=False)
    cell_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    home_phone: Mapped[str | None] = mapped_column(String(30))
    authorized_pickup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Child(TimestampMixin, BasicBase):
    __tablename__ = "children"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="CASCADE",
            name="fk_children_org_family",
        ),
        UniqueConstraint("organization_id", "id", name="uq_children_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "id",
            name="uq_children_org_family_id",
        ),
        CheckConstraint("version > 0", name="ck_children_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(30))
    age_group: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    health_care_number: Mapped[str | None] = mapped_column(String(100))
    allergies: Mapped[str | None] = mapped_column(Text)
    medical_conditions: Mapped[str | None] = mapped_column(Text)
    medications: Mapped[str | None] = mapped_column(Text)
    immunization_up_to_date: Mapped[bool | None] = mapped_column(Boolean)
    doctor_name: Mapped[str | None] = mapped_column(String(255))
    doctor_phone: Mapped[str | None] = mapped_column(String(30))


class ChildProfilePhoto(TimestampMixin, BasicBase):
    """Normalized profile image kept with the database backup boundary."""

    __tablename__ = "child_profile_photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="CASCADE",
            name="fk_child_profile_photos_org_child",
        ),
        UniqueConstraint("organization_id", "id", name="uq_child_profile_photos_org_id"),
        UniqueConstraint("organization_id", "child_id", name="uq_child_profile_photos_org_child"),
        CheckConstraint(
            "content_type IN ('image/jpeg','image/webp')",
            name="ck_child_profile_photos_content_type",
        ),
        CheckConstraint("size_bytes > 0", name="ck_child_profile_photos_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_child_profile_photos_dimensions"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))


class Enrollment(TimestampMixin, BasicBase):
    __tablename__ = "enrollments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_enrollments_org_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="CASCADE",
            name="fk_enrollments_org_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["facility_programs.organization_id", "facility_programs.id"],
            ondelete="RESTRICT",
            name="fk_enrollments_org_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id"],
            [
                "facility_programs.organization_id",
                "facility_programs.facility_id",
                "facility_programs.id",
            ],
            ondelete="RESTRICT",
            name="fk_enrollments_facility_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "room_id"],
            ["rooms.organization_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_enrollments_org_room",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id", "room_id"],
            [
                "rooms.organization_id",
                "rooms.facility_id",
                "rooms.program_id",
                "rooms.id",
            ],
            ondelete="RESTRICT",
            name="fk_enrollments_facility_program_room",
        ),
        UniqueConstraint("organization_id", "id", name="uq_enrollments_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "child_id",
            "id",
            name="uq_enrollments_attendance_identity",
        ),
        CheckConstraint(
            "status IN ('pending','active','paused','ended')", name="ck_enrollments_status"
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_enrollment_dates"),
        CheckConstraint(
            "(program_id IS NULL AND room_id IS NULL AND placement_effective_date IS NULL) OR "
            "(program_id IS NOT NULL AND room_id IS NOT NULL "
            "AND placement_effective_date IS NOT NULL)",
            name="ck_enrollment_placement_pair",
        ),
        CheckConstraint(
            "status <> 'pending' OR program_id IS NULL",
            name="ck_enrollment_pending_unassigned",
        ),
        CheckConstraint("version > 0", name="ck_enrollments_version"),
        Index(
            "uq_enrollments_one_open_org_child",
            "organization_id",
            "child_id",
            unique=True,
            postgresql_where=text("status IN ('pending','active','paused')"),
            sqlite_where=text("status IN ('pending','active','paused')"),
        ),
        Index(
            "ix_enrollments_open_room_interval",
            "organization_id",
            "room_id",
            "status",
            "placement_effective_date",
            "end_date",
            postgresql_where=text(
                "room_id IS NOT NULL AND status IN ('pending','active','paused')"
            ),
            sqlite_where=text("room_id IS NOT NULL AND status IN ('pending','active','paused')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    program_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    placement_effective_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    def is_current_on(self, facility_date: date) -> bool:
        return (
            self.status == "active"
            and self.program_id is not None
            and self.room_id is not None
            and self.placement_effective_date is not None
            and self.start_date <= facility_date
            and self.placement_effective_date <= facility_date
            and (self.end_date is None or self.end_date >= facility_date)
        )


class AdmissionApplication(TimestampMixin, BasicBase):
    """One prospective child and primary-contact admissions lifecycle head."""

    __tablename__ = "admission_applications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_applications_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "reference",
            name="uq_admission_applications_org_reference",
        ),
        Index(
            "ix_admission_applications_org_status_updated",
            "organization_id",
            "status",
            "updated_at",
        ),
        CheckConstraint(
            "source = 'administrator_entry'",
            name="ck_admission_applications_source",
        ),
        CheckConstraint(
            "status IN ('draft','submitted','under_review','waitlisted','offered',"
            "'accepted','declined','withdrawn')",
            name="ck_admission_applications_status",
        ),
        CheckConstraint("version > 0", name="ck_admission_applications_version"),
        CheckConstraint(
            "(status = 'draft' AND submitted_at IS NULL) OR "
            "(status <> 'draft' AND submitted_at IS NOT NULL)",
            name="ck_admission_applications_submission",
        ),
        CheckConstraint(
            "(status IN ('accepted','declined','withdrawn') AND terminal_at IS NOT NULL) "
            "OR (status NOT IN ('accepted','declined','withdrawn') AND terminal_at IS NULL)",
            name="ck_admission_applications_terminal",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reference: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(
        String(40), default="administrator_entry", server_default="administrator_entry"
    )
    status: Mapped[str] = mapped_column(
        String(30), default="draft", server_default="draft", nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    child_first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    child_last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    child_normalized_name: Mapped[str] = mapped_column(String(220), nullable=False)
    child_date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    contact_first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_relationship: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_normalized_email: Mapped[str | None] = mapped_column(String(320))
    contact_telephone: Mapped[str | None] = mapped_column(String(30))
    contact_normalized_telephone: Mapped[str | None] = mapped_column(String(30))
    internal_note: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionApplicationPreference(BasicBase):
    """Temporal ranked preference; retired rows remain historical facts."""

    __tablename__ = "admission_application_preferences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_preferences_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_admission_preferences_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id"],
            [
                "facility_programs.organization_id",
                "facility_programs.facility_id",
                "facility_programs.id",
            ],
            ondelete="RESTRICT",
            name="fk_admission_preferences_program",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_preferences_org_id"
        ),
        Index(
            "ix_admission_preferences_application",
            "organization_id",
            "application_id",
        ),
        Index(
            "uq_admission_preferences_current_rank",
            "organization_id",
            "application_id",
            "current_rank",
            unique=True,
        ),
        Index(
            "uq_admission_preferences_current_lane",
            "organization_id",
            "application_id",
            "current_lane_key",
            unique=True,
        ),
        CheckConstraint("rank > 0", name="ck_admission_preferences_rank"),
        CheckConstraint(
            "application_version > 0",
            name="ck_admission_preferences_application_version",
        ),
        CheckConstraint(
            "(retired_at IS NULL AND retired_by_user_id IS NULL "
            "AND retired_operation_id IS NULL AND current_rank = rank "
            "AND current_lane_key IS NOT NULL) OR "
            "(retired_at IS NOT NULL AND retired_by_user_id IS NOT NULL "
            "AND retired_operation_id IS NOT NULL AND current_rank IS NULL "
            "AND current_lane_key IS NULL)",
            name="ck_admission_preferences_current",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    current_rank: Mapped[int | None] = mapped_column(Integer)
    current_lane_key: Mapped[str | None] = mapped_column(String(80))
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    application_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionWaitlistEntry(TimestampMixin, BasicBase):
    """One current deterministic queue record per application."""

    __tablename__ = "admission_waitlist_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_waitlist_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "current_application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_waitlist_current_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id"],
            [
                "facility_programs.organization_id",
                "facility_programs.facility_id",
                "facility_programs.id",
            ],
            ondelete="RESTRICT",
            name="fk_admission_waitlist_program",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_waitlist_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "current_application_id",
            name="uq_admission_waitlist_current_application",
        ),
        Index(
            "ix_admission_waitlist_application",
            "organization_id",
            "application_id",
        ),
        Index(
            "ix_admission_waitlist_lane_priority",
            "organization_id",
            "facility_id",
            "program_id",
            "priority_at",
            "id",
        ),
        CheckConstraint(
            "status IN ('active','offered','closed')",
            name="ck_admission_waitlist_status",
        ),
        CheckConstraint("version > 0", name="ck_admission_waitlist_version"),
        CheckConstraint(
            "closure_reason IS NULL OR closure_reason IN "
            "('facts_changed','review_reopened','application_declined',"
            "'application_withdrawn','offer_declined','application_accepted')",
            name="ck_admission_waitlist_closure_reason",
        ),
        CheckConstraint(
            "(status IN ('active','offered') AND current_application_id = application_id "
            "AND closure_reason IS NULL AND closed_at IS NULL) OR "
            "(status = 'closed' AND current_application_id IS NULL "
            "AND closure_reason IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_admission_waitlist_current",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    current_application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    priority_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    closure_reason: Mapped[str | None] = mapped_column(String(40))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionOffer(TimestampMixin, BasicBase):
    """A non-financial program offer with one open slot per application."""

    __tablename__ = "admission_offers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_offers_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "open_application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_offers_open_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id"],
            [
                "facility_programs.organization_id",
                "facility_programs.facility_id",
                "facility_programs.id",
            ],
            ondelete="RESTRICT",
            name="fk_admission_offers_program",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_offers_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "open_application_id",
            name="uq_admission_offers_open_application",
        ),
        Index(
            "ix_admission_offers_application",
            "organization_id",
            "application_id",
        ),
        CheckConstraint(
            "status IN ('open','accepted','declined','withdrawn')",
            name="ck_admission_offers_status",
        ),
        CheckConstraint(
            "prior_application_status IN ('under_review','waitlisted')",
            name="ck_admission_offers_prior_status",
        ),
        CheckConstraint("version > 0", name="ck_admission_offers_version"),
        CheckConstraint(
            "(status = 'open' AND open_application_id = application_id "
            "AND withdrawn_at IS NULL AND declined_at IS NULL AND accepted_at IS NULL) OR "
            "(status = 'withdrawn' AND open_application_id IS NULL "
            "AND withdrawn_at IS NOT NULL AND declined_at IS NULL AND accepted_at IS NULL) OR "
            "(status = 'declined' AND open_application_id IS NULL "
            "AND declined_at IS NOT NULL AND withdrawn_at IS NULL AND accepted_at IS NULL) OR "
            "(status = 'accepted' AND open_application_id IS NULL "
            "AND accepted_at IS NOT NULL AND withdrawn_at IS NULL AND declined_at IS NULL)",
            name="ck_admission_offers_current",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    open_application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposed_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    respond_by_date: Mapped[date | None] = mapped_column(Date)
    prior_application_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    issued_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionConversionLink(BasicBase):
    """Immutable link from one accepted offer to canonical childcare records."""

    __tablename__ = "admission_conversion_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_conversion_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "offer_id"],
            ["admission_offers.organization_id", "admission_offers.id"],
            ondelete="RESTRICT",
            name="fk_admission_conversion_offer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="RESTRICT",
            name="fk_admission_conversion_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_admission_conversion_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "enrollment_id"],
            ["enrollments.organization_id", "enrollments.id"],
            ondelete="RESTRICT",
            name="fk_admission_conversion_enrollment",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_conversion_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "application_id",
            name="uq_admission_conversion_application",
        ),
        UniqueConstraint(
            "organization_id", "offer_id", name="uq_admission_conversion_offer"
        ),
        UniqueConstraint(
            "organization_id",
            "enrollment_id",
            name="uq_admission_conversion_enrollment",
        ),
        Index(
            "ix_admission_conversion_application",
            "organization_id",
            "application_id",
        ),
        CheckConstraint(
            "resolution_mode IN "
            "('create_family_and_child','reuse_family_create_child','reuse_child')",
            name="ck_admission_conversion_resolution",
        ),
        CheckConstraint(
            "length(review_proof_digest) = 64",
            name="ck_admission_conversion_review_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    offer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resolution_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    acceptance_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    review_proof_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    converted_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    converted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AdmissionApplicationEvent(BasicBase):
    """Append-only PII-free application version timeline."""

    __tablename__ = "admission_application_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["admission_applications.organization_id", "admission_applications.id"],
            ondelete="RESTRICT",
            name="fk_admission_events_application",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_admission_events_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "application_id",
            "application_version",
            name="uq_admission_events_application_version",
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_admission_events_operation",
        ),
        Index(
            "ix_admission_events_timeline",
            "organization_id",
            "application_id",
            "application_version",
        ),
        CheckConstraint(
            "application_version > 0",
            name="ck_admission_events_application_version",
        ),
        CheckConstraint(
            "to_status IN ('draft','submitted','under_review','waitlisted','offered',"
            "'accepted','declined','withdrawn')",
            name="ck_admission_events_to_status",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('draft','submitted','under_review','waitlisted','offered',"
            "'accepted','declined','withdrawn')",
            name="ck_admission_events_from_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_version: Mapped[int] = mapped_column(Integer, nullable=False)
    command: Mapped[str] = mapped_column(String(80), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildcareCommandSlot(BasicBase):
    """Internal cross-table discriminator for one organization operation."""

    __tablename__ = "childcare_command_slots"
    __table_args__ = (
        CheckConstraint(
            "entry_kind IN ('receipt','absence_claim')",
            name="ck_childcare_command_slots_kind",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    entry_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildcareCommandReconciliationProof(BasicBase):
    """Actor-scoped proof that one reconciliation result is terminal."""

    __tablename__ = "childcare_command_reconciliation_proofs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "client_operation_id",
            name="uq_childcare_command_reconciliation_proofs_identity_operation",
        ),
        Index(
            "ix_childcare_command_reconciliation_proofs_actor_window",
            "organization_id",
            "actor_user_id",
            "finalized_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildcareCommandReconciliationBudgetEntry(BasicBase):
    """One permanent quota charge per actor operation, so retries cost zero."""

    __tablename__ = "childcare_command_reconciliation_budget_entries"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    charged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildcareCommandReconciliationBudget(BasicBase):
    """Atomic hourly and daily reconciliation counters."""

    __tablename__ = "childcare_command_reconciliation_budgets"
    __table_args__ = (
        CheckConstraint(
            "window_kind IN ('hour','day')",
            name="ck_childcare_command_reconciliation_budgets_kind",
        ),
        CheckConstraint(
            "operation_count >= 1 AND ((window_kind = 'hour' AND operation_count <= 120) "
            "OR (window_kind = 'day' AND operation_count <= 500))",
            name="ck_childcare_command_reconciliation_budgets_count",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    window_kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    operation_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ChildcareCommandReceipt(BasicBase):
    """Immutable tenant command receipt without duplicated child or family PII."""

    __tablename__ = "childcare_command_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_childcare_command_receipts_facility",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_childcare_command_receipts_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_childcare_command_receipts_operation",
        ),
        CheckConstraint(
            "length(request_hash) = 64",
            name="ck_childcare_command_receipts_hash",
        ),
        CheckConstraint(
            "committed_version > 0",
            name="ck_childcare_command_receipts_version",
        ),
        CheckConstraint(
            "target_type IN ('family','child','enrollment','authority_person',"
            "'authority_evidence','authority_evidence_object','release_authorization',"
            "'release_rule','consent','release_activation','attendance_release',"
            "'admission_application','admission_waitlist','admission_offer')",
            name="ck_childcare_command_receipts_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    committed_version: Mapped[int] = mapped_column(Integer, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ChildcareCommandClaim(BasicBase):
    """Global no-write authority for an operation finalized before any receipt."""

    __tablename__ = "childcare_command_claims"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_childcare_command_claims_operation",
        ),
        Index(
            "ix_childcare_command_claims_actor_window",
            "organization_id",
            "actor_user_id",
            "claimed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AttendanceDay(TimestampMixin, BasicBase):
    __tablename__ = "attendance_days"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_attendance_days_org_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_attendance_days_room_snapshot",
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_attendance_days_org_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "child_id", "enrollment_id"],
            [
                "enrollments.organization_id",
                "enrollments.facility_id",
                "enrollments.child_id",
                "enrollments.id",
            ],
            ondelete="RESTRICT",
            name="fk_attendance_days_enrollment_identity",
        ),
        UniqueConstraint("organization_id", "id", name="uq_attendance_days_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "child_id",
            "id",
            name="uq_attendance_days_release_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "child_id",
            "service_date",
            name="uq_attendance_days_child_date",
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "room_id",
            "child_id",
            "enrollment_id",
            "service_date",
            "id",
            name="uq_attendance_days_care_identity",
        ),
        CheckConstraint("status IN ('present','absent')", name="ck_attendance_days_status"),
        CheckConstraint("version > 0", name="ck_attendance_days_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="present", nullable=False)
    absence_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AttendanceInterval(TimestampMixin, BasicBase):
    __tablename__ = "attendance_intervals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "attendance_day_id"],
            ["attendance_days.organization_id", "attendance_days.id"],
            ondelete="CASCADE",
            name="fk_attendance_intervals_org_day",
        ),
        UniqueConstraint("organization_id", "id", name="uq_attendance_intervals_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "attendance_day_id",
            "id",
            name="uq_attendance_intervals_release_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "attendance_day_id",
            "sequence",
            name="uq_attendance_intervals_day_sequence",
        ),
        CheckConstraint("sequence > 0", name="ck_attendance_intervals_sequence"),
        CheckConstraint(
            "checked_out_at IS NULL OR checked_out_at >= checked_in_at",
            name="ck_attendance_interval_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    attendance_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceEvent(BasicBase):
    __tablename__ = "attendance_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "attendance_day_id"],
            ["attendance_days.organization_id", "attendance_days.id"],
            ondelete="CASCADE",
            name="fk_attendance_events_org_day",
        ),
        UniqueConstraint("organization_id", "id", name="uq_attendance_events_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "attendance_day_id",
            "id",
            name="uq_attendance_events_release_identity",
        ),
        Index(
            "uq_attendance_events_client_operation",
            "organization_id",
            "client_operation_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    attendance_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    client_operation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class DailyCareRecord(TimestampMixin, BasicBase):
    """Current projection of one room-scoped daily care fact.

    The mutable projection makes current-day reads inexpensive. Every mutation
    is independently preserved in ``daily_care_record_events`` and application
    access has no DELETE privilege on this table.
    """

    __tablename__ = "daily_care_records"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "organization_id",
                "facility_id",
                "room_id",
                "child_id",
                "enrollment_id",
                "service_date",
                "attendance_day_id",
            ],
            [
                "attendance_days.organization_id",
                "attendance_days.facility_id",
                "attendance_days.room_id",
                "attendance_days.child_id",
                "attendance_days.enrollment_id",
                "attendance_days.service_date",
                "attendance_days.id",
            ],
            ondelete="RESTRICT",
            name="fk_daily_care_records_attendance_identity",
        ),
        UniqueConstraint("organization_id", "id", name="uq_daily_care_records_org_id"),
        CheckConstraint(
            "care_type IN ('feeding','diaper','toilet','sleep','mood','activity')",
            name="ck_daily_care_records_type",
        ),
        CheckConstraint("version > 0", name="ck_daily_care_records_version"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= occurred_at",
            name="ck_daily_care_records_time_order",
        ),
        CheckConstraint(
            "care_type = 'sleep' OR ended_at IS NULL",
            name="ck_daily_care_records_end_only_for_sleep",
        ),
        CheckConstraint(
            "(voided_at IS NULL AND voided_by_user_id IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by_user_id IS NOT NULL AND "
            "void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_daily_care_records_void_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attendance_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    care_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)


Index(
    "ix_daily_care_records_room_day_time",
    DailyCareRecord.organization_id,
    DailyCareRecord.room_id,
    DailyCareRecord.service_date,
    DailyCareRecord.occurred_at,
)
Index(
    "ix_daily_care_records_child_day",
    DailyCareRecord.organization_id,
    DailyCareRecord.child_id,
    DailyCareRecord.service_date,
)
Index(
    "uq_daily_care_records_open_sleep",
    DailyCareRecord.organization_id,
    DailyCareRecord.attendance_day_id,
    unique=True,
    sqlite_where=(
        (DailyCareRecord.care_type == "sleep")
        & DailyCareRecord.ended_at.is_(None)
        & DailyCareRecord.voided_at.is_(None)
    ),
    postgresql_where=(
        (DailyCareRecord.care_type == "sleep")
        & DailyCareRecord.ended_at.is_(None)
        & DailyCareRecord.voided_at.is_(None)
    ),
)


class DailyCareRecordEvent(BasicBase):
    """Append-only mutation history for one daily care projection."""

    __tablename__ = "daily_care_record_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "care_record_id"],
            ["daily_care_records.organization_id", "daily_care_records.id"],
            ondelete="RESTRICT",
            name="fk_daily_care_record_events_org_record",
        ),
        UniqueConstraint("organization_id", "id", name="uq_daily_care_record_events_org_id"),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_daily_care_record_events_operation",
        ),
        CheckConstraint(
            "event_type IN "
            "('recorded','sleep_finished','corrected','voided','auto_finished_at_checkout')",
            name="ck_daily_care_record_events_type",
        ),
        CheckConstraint(
            "event_type NOT IN ('corrected','voided') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_daily_care_record_events_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    care_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class MedicationPlan(TimestampMixin, BasicBase):
    """Current projection of a facility-scoped written medication plan.

    ``authorization_*`` stores evidence that a separate written authorization
    was reviewed.  It is deliberately not a signature or consent substitute.
    Every projection mutation is preserved in ``medication_plan_events``.
    """

    __tablename__ = "medication_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_medication_plans_org_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_medication_plans_org_child",
        ),
        UniqueConstraint("organization_id", "id", name="uq_medication_plans_org_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "child_id",
            "id",
            name="uq_medication_plans_administration_identity",
        ),
        CheckConstraint(
            "route IN ('oral','topical','inhaled','injected','other')",
            name="ck_medication_plans_route",
        ),
        CheckConstraint(
            "medication_kind IN ('non_emergency','emergency')",
            name="ck_medication_plans_kind",
        ),
        CheckConstraint(
            "storage_method IN ('locked_inaccessible','emergency_accessible_per_plan')",
            name="ck_medication_plans_storage_method",
        ),
        CheckConstraint(
            "(medication_kind = 'non_emergency' AND storage_method = 'locked_inaccessible' "
            "AND emergency_plan_reference IS NULL) OR "
            "(medication_kind = 'emergency' AND "
            "storage_method = 'emergency_accessible_per_plan' AND "
            "emergency_plan_reference IS NOT NULL AND "
            "length(trim(emergency_plan_reference)) > 0)",
            name="ck_medication_plans_storage_safety",
        ),
        CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_medication_plans_status",
        ),
        CheckConstraint(
            "authorization_status IN ('not_recorded','verified','revoked')",
            name="ck_medication_plans_authorization_status",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_medication_plan_dates",
        ),
        CheckConstraint("version > 0", name="ck_medication_plans_version"),
        CheckConstraint(
            "(authorization_status = 'not_recorded' AND authorization_guardian_id IS NULL "
            "AND authorization_guardian_name IS NULL "
            "AND signed_authorization_reference IS NULL "
            "AND authorization_signed_at IS NULL AND authorization_valid_until IS NULL "
            "AND authorization_verified_at IS NULL "
            "AND authorization_verified_by_user_id IS NULL "
            "AND authorization_revoked_at IS NULL "
            "AND authorization_revoked_by_user_id IS NULL "
            "AND authorization_revocation_reason IS NULL) OR "
            "(authorization_status = 'verified' AND authorization_guardian_id IS NOT NULL "
            "AND authorization_guardian_name IS NOT NULL "
            "AND signed_authorization_reference IS NOT NULL "
            "AND length(trim(signed_authorization_reference)) > 0 "
            "AND authorization_signed_at IS NOT NULL "
            "AND authorization_verified_at IS NOT NULL "
            "AND authorization_verified_by_user_id IS NOT NULL "
            "AND authorization_revoked_at IS NULL "
            "AND authorization_revoked_by_user_id IS NULL "
            "AND authorization_revocation_reason IS NULL) OR "
            "(authorization_status = 'revoked' AND authorization_guardian_id IS NOT NULL "
            "AND authorization_guardian_name IS NOT NULL "
            "AND signed_authorization_reference IS NOT NULL "
            "AND length(trim(signed_authorization_reference)) > 0 "
            "AND authorization_signed_at IS NOT NULL "
            "AND authorization_verified_at IS NOT NULL "
            "AND authorization_verified_by_user_id IS NOT NULL "
            "AND authorization_revoked_at IS NOT NULL "
            "AND authorization_revoked_by_user_id IS NOT NULL "
            "AND authorization_revocation_reason IS NOT NULL "
            "AND length(trim(authorization_revocation_reason)) > 0)",
            name="ck_medication_plans_authorization_evidence",
        ),
        CheckConstraint(
            "status <> 'active' OR (authorization_status = 'verified' "
            "AND original_labelled_container_verified_at IS NOT NULL "
            "AND original_labelled_container_verified_by_user_id IS NOT NULL "
            "AND label_directions_verified_at IS NOT NULL "
            "AND label_directions_verified_by_user_id IS NOT NULL)",
            name="ck_medication_plans_active_evidence",
        ),
        CheckConstraint(
            "(archived_at IS NULL AND archived_by_user_id IS NULL AND archive_reason IS NULL) OR "
            "(status = 'archived' AND archived_at IS NOT NULL "
            "AND archived_by_user_id IS NOT NULL AND archive_reason IS NOT NULL "
            "AND length(trim(archive_reason)) > 0)",
            name="ck_medication_plans_archive_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str] = mapped_column(String(255), nullable=False)
    route: Mapped[str] = mapped_column(String(30), nullable=False)
    label_directions: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_times: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    as_needed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    medication_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_method: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_plan_reference: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    authorization_status: Mapped[str] = mapped_column(
        String(30), default="not_recorded", nullable=False
    )
    authorization_guardian_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    authorization_guardian_name: Mapped[str | None] = mapped_column(String(255))
    signed_authorization_reference: Mapped[str | None] = mapped_column(String(255))
    authorization_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_valid_until: Mapped[date | None] = mapped_column(Date)
    authorization_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    authorization_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    authorization_revocation_reason: Mapped[str | None] = mapped_column(Text)
    original_labelled_container_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    original_labelled_container_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    label_directions_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label_directions_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    archive_reason: Mapped[str | None] = mapped_column(Text)


Index(
    "ix_medication_plans_child_facility_status",
    MedicationPlan.organization_id,
    MedicationPlan.child_id,
    MedicationPlan.facility_id,
    MedicationPlan.status,
)


class MedicationPlanEvent(BasicBase):
    __tablename__ = "medication_plan_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "medication_plan_id"],
            ["medication_plans.organization_id", "medication_plans.id"],
            ondelete="RESTRICT",
            name="fk_medication_plan_events_org_plan",
        ),
        UniqueConstraint("organization_id", "id", name="uq_medication_plan_events_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_medication_plan_events_operation"
        ),
        CheckConstraint(
            "event_type IN ('created','updated','authorization_verified',"
            "'authorization_revoked','activated','archived')",
            name="ck_medication_plan_events_type",
        ),
        CheckConstraint(
            "event_type NOT IN ('updated','authorization_revoked','archived') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_plan_events_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    medication_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class MedicationAdministration(TimestampMixin, BasicBase):
    """Attendance-linked medication administration/refusal/omission fact."""

    __tablename__ = "medication_administrations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "child_id", "medication_plan_id"],
            [
                "medication_plans.organization_id",
                "medication_plans.facility_id",
                "medication_plans.child_id",
                "medication_plans.id",
            ],
            ondelete="RESTRICT",
            name="fk_medication_administrations_plan_identity",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "facility_id",
                "room_id",
                "child_id",
                "enrollment_id",
                "service_date",
                "attendance_day_id",
            ],
            [
                "attendance_days.organization_id",
                "attendance_days.facility_id",
                "attendance_days.room_id",
                "attendance_days.child_id",
                "attendance_days.enrollment_id",
                "attendance_days.service_date",
                "attendance_days.id",
            ],
            ondelete="RESTRICT",
            name="fk_medication_administrations_attendance_identity",
        ),
        UniqueConstraint("organization_id", "id", name="uq_medication_administrations_org_id"),
        CheckConstraint(
            "outcome IN ('administered','refused','omitted')",
            name="ck_medication_administrations_outcome",
        ),
        CheckConstraint(
            "(outcome = 'administered' AND amount IS NOT NULL "
            "AND length(trim(amount)) > 0 AND reason IS NULL) OR "
            "(outcome IN ('refused','omitted') AND amount IS NULL "
            "AND reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_administrations_outcome_evidence",
        ),
        CheckConstraint("version > 0", name="ck_medication_administrations_version"),
        CheckConstraint(
            "length(trim(staff_name_snapshot)) > 0 AND length(trim(staff_initials_snapshot)) > 0",
            name="ck_medication_administrations_staff_snapshot",
        ),
        CheckConstraint(
            "(voided_at IS NULL AND voided_by_user_id IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by_user_id IS NOT NULL "
            "AND void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_medication_administrations_void_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attendance_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    medication_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scheduled_for: Mapped[time | None] = mapped_column(Time)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    staff_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    staff_initials_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)


Index(
    "ix_medication_administrations_room_day_time",
    MedicationAdministration.organization_id,
    MedicationAdministration.room_id,
    MedicationAdministration.service_date,
    MedicationAdministration.occurred_at,
)
Index(
    "uq_medication_administrations_schedule_slot",
    MedicationAdministration.organization_id,
    MedicationAdministration.medication_plan_id,
    MedicationAdministration.service_date,
    MedicationAdministration.scheduled_for,
    unique=True,
    sqlite_where=(
        MedicationAdministration.scheduled_for.is_not(None)
        & MedicationAdministration.voided_at.is_(None)
    ),
    postgresql_where=(
        MedicationAdministration.scheduled_for.is_not(None)
        & MedicationAdministration.voided_at.is_(None)
    ),
)


class MedicationAdministrationEvent(BasicBase):
    __tablename__ = "medication_administration_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "medication_administration_id"],
            ["medication_administrations.organization_id", "medication_administrations.id"],
            ondelete="RESTRICT",
            name="fk_medication_administration_events_org_record",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_medication_administration_events_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_medication_administration_events_operation",
        ),
        CheckConstraint(
            "event_type IN ('recorded','corrected','voided')",
            name="ck_medication_administration_events_type",
        ),
        CheckConstraint(
            "event_type NOT IN ('corrected','voided') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_administration_events_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    medication_administration_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class IncidentRecord(TimestampMixin, BasicBase):
    """Internal incident projection; CareSync never performs external submission."""

    __tablename__ = "incident_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_incident_records_org_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_incident_records_room_snapshot",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "facility_id",
                "room_id",
                "child_id",
                "enrollment_id",
                "service_date",
                "attendance_day_id",
            ],
            [
                "attendance_days.organization_id",
                "attendance_days.facility_id",
                "attendance_days.room_id",
                "attendance_days.child_id",
                "attendance_days.enrollment_id",
                "attendance_days.service_date",
                "attendance_days.id",
            ],
            ondelete="RESTRICT",
            name="fk_incident_records_attendance_identity",
        ),
        UniqueConstraint("organization_id", "id", name="uq_incident_records_org_id"),
        CheckConstraint(
            "category IN ('injury','illness','missing_child','unauthorized_release',"
            "'allegation','emergency','other')",
            name="ck_incident_records_category",
        ),
        CheckConstraint(
            "severity IN ('minor','moderate','serious','critical')",
            name="ck_incident_records_severity",
        ),
        CheckConstraint(
            "medical_attention IN ('none','first_aid','medical_practitioner','emergency_services')",
            name="ck_incident_records_medical_attention",
        ),
        CheckConstraint(
            "parent_notification_status IN "
            "('pending','notified','unable_to_reach','not_applicable')",
            name="ck_incident_records_parent_notification_status",
        ),
        CheckConstraint(
            "(parent_notification_status = 'notified' AND parent_notified_at IS NOT NULL "
            "AND parent_notification_notes IS NOT NULL "
            "AND length(trim(parent_notification_notes)) > 0) OR "
            "(parent_notification_status = 'unable_to_reach' AND parent_notified_at IS NULL "
            "AND parent_notification_notes IS NOT NULL "
            "AND length(trim(parent_notification_notes)) > 0) OR "
            "(parent_notification_status IN ('pending','not_applicable') "
            "AND parent_notified_at IS NULL AND parent_notification_notes IS NULL)",
            name="ck_incident_records_parent_notification_evidence",
        ),
        CheckConstraint(
            "status IN ('draft','under_review','finalized')",
            name="ck_incident_records_status",
        ),
        CheckConstraint(
            "reportability_assessment IN "
            "('unassessed','not_reportable','other_reportable','critical')",
            name="ck_incident_records_reportability",
        ),
        CheckConstraint(
            "external_report_status IN ('not_assessed','not_required','pending','recorded')",
            name="ck_incident_records_external_status",
        ),
        CheckConstraint(
            "(child_id IS NULL AND enrollment_id IS NULL AND attendance_day_id IS NULL) OR "
            "(child_id IS NOT NULL AND enrollment_id IS NOT NULL "
            "AND attendance_day_id IS NOT NULL)",
            name="ck_incident_records_child_attendance_pair",
        ),
        CheckConstraint("version > 0", name="ck_incident_records_version"),
        CheckConstraint(
            "(status IN ('draft','under_review') AND finalized_at IS NULL "
            "AND finalized_by_user_id IS NULL AND reportability_assessment = 'unassessed' "
            "AND external_report_status = 'not_assessed') OR "
            "(status = 'finalized' AND finalized_at IS NOT NULL "
            "AND finalized_by_user_id IS NOT NULL "
            "AND reportability_assessment <> 'unassessed' "
            "AND ((reportability_assessment = 'not_reportable' "
            "AND external_report_status = 'not_required') OR "
            "(reportability_assessment IN ('other_reportable','critical') "
            "AND external_report_status IN ('pending','recorded'))))",
            name="ck_incident_records_finalization_state",
        ),
        CheckConstraint(
            "(external_report_status <> 'recorded' AND external_reported_at IS NULL "
            "AND external_confirmation_reference IS NULL "
            "AND external_submission_channel IS NULL AND external_submitted_by_name IS NULL "
            "AND external_report_recorded_by_user_id IS NULL) OR "
            "(external_report_status = 'recorded' AND external_reported_at IS NOT NULL "
            "AND external_confirmation_reference IS NOT NULL "
            "AND length(trim(external_confirmation_reference)) > 0 "
            "AND external_submission_channel IN "
            "('alberta_licensing_portal','child_care_connect_then_portal') "
            "AND external_submitted_by_name IS NOT NULL "
            "AND length(trim(external_submitted_by_name)) > 0 "
            "AND external_report_recorded_by_user_id IS NOT NULL)",
            name="ck_incident_records_external_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    enrollment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    attendance_day_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    immediate_actions: Mapped[str] = mapped_column(Text, nullable=False)
    medical_attention: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_notification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_notification_notes: Mapped[str | None] = mapped_column(Text)
    authorities_contacted: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    staff_present: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    reportability_assessment: Mapped[str] = mapped_column(
        String(30), default="unassessed", nullable=False
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    external_report_status: Mapped[str] = mapped_column(
        String(30), default="not_assessed", nullable=False, index=True
    )
    external_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_confirmation_reference: Mapped[str | None] = mapped_column(String(255))
    external_submission_channel: Mapped[str | None] = mapped_column(String(60))
    external_submitted_by_name: Mapped[str | None] = mapped_column(String(255))
    external_report_recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


Index(
    "ix_incident_records_room_day_time",
    IncidentRecord.organization_id,
    IncidentRecord.room_id,
    IncidentRecord.service_date,
    IncidentRecord.occurred_at,
)


class IncidentRecordEvent(BasicBase):
    __tablename__ = "incident_record_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "incident_record_id"],
            ["incident_records.organization_id", "incident_records.id"],
            ondelete="RESTRICT",
            name="fk_incident_record_events_org_record",
        ),
        UniqueConstraint("organization_id", "id", name="uq_incident_record_events_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_incident_record_events_operation"
        ),
        CheckConstraint(
            "event_type IN ('drafted','updated','submitted_for_review','returned_to_draft',"
            "'finalized','external_report_recorded')",
            name="ck_incident_record_events_type",
        ),
        CheckConstraint(
            "event_type NOT IN ('updated','returned_to_draft','finalized') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_incident_record_events_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    incident_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditEvent(BasicBase):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_audit_events_org_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_audit_events_org_id_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AtsJob(TimestampMixin, BasicBase):
    __tablename__ = "ats_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_ats_jobs_org_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_jobs_org_id"),
        CheckConstraint("status IN ('draft','open','paused','closed')", name="ck_ats_jobs_status"),
        CheckConstraint("openings > 0", name="ck_ats_jobs_openings"),
        CheckConstraint("version > 0", name="ck_ats_jobs_version"),
        CheckConstraint(
            "(status = 'open' AND published_at IS NOT NULL) OR status <> 'open'",
            name="ck_ats_jobs_open_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    openings: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AtsCandidate(TimestampMixin, BasicBase):
    __tablename__ = "ats_candidates"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ats_candidates_org_id"),
        UniqueConstraint("organization_id", "email", name="uq_ats_candidates_org_email"),
        CheckConstraint(
            "status IN ('prospect','active','withdrawn','archived')",
            name="ck_ats_candidates_status",
        ),
        CheckConstraint(
            "onboarding_status IN ('not_started','in_progress','submitted','complete')",
            name="ck_ats_candidates_onboarding_status",
        ),
        CheckConstraint(
            "certification_verification_status IN ('unverified','pending','verified','rejected')",
            name="ck_ats_candidates_certification_status",
        ),
        CheckConstraint(
            "candidate_type IS NULL OR candidate_type IN ('certified_educator','student')",
            name="ck_ats_candidates_candidate_type",
        ),
        CheckConstraint(
            "(certification_verification_status = 'verified' AND "
            "certification_verified_at IS NOT NULL AND "
            "certification_verified_by_user_id IS NOT NULL) OR "
            "certification_verification_status <> 'verified'",
            name="ck_ats_candidates_certification_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="prospect", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    claimed_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    onboarding_status: Mapped[str] = mapped_column(
        String(30), default="not_started", nullable=False
    )
    certification_type: Mapped[str | None] = mapped_column(String(120))
    certification_number: Mapped[str | None] = mapped_column(String(120))
    certification_expiry_date: Mapped[date | None] = mapped_column(Date)
    certification_verification_status: Mapped[str] = mapped_column(
        String(30), default="unverified", nullable=False
    )
    certification_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certification_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    certification_review_note: Mapped[str | None] = mapped_column(Text)
    work_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    certification_provenance: Mapped[str | None] = mapped_column(String(30))
    certification_candidate_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    work_history_provenance: Mapped[str | None] = mapped_column(String(30))
    work_history_candidate_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    candidate_type: Mapped[str | None] = mapped_column(String(30))
    institution: Mapped[str | None] = mapped_column(String(180))
    program: Mapped[str | None] = mapped_column(String(180))
    expected_graduation_date: Mapped[date | None] = mapped_column(Date)


class AtsApplication(TimestampMixin, BasicBase):
    __tablename__ = "ats_applications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["ats_jobs.organization_id", "ats_jobs.id"],
            ondelete="RESTRICT",
            name="fk_ats_applications_org_job",
        ),
        ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["ats_candidates.organization_id", "ats_candidates.id"],
            ondelete="RESTRICT",
            name="fk_ats_applications_org_candidate",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_applications_org_id"),
        UniqueConstraint(
            "organization_id", "job_id", "candidate_id", name="uq_ats_applications_job_candidate"
        ),
        CheckConstraint(
            "status IN ('invited','applied','screening','interview','offer',"
            "'accepted','rejected','withdrawn','hired')",
            name="ck_ats_applications_status",
        ),
        CheckConstraint("version > 0", name="ck_ats_applications_version"),
        CheckConstraint(
            "source IN ('private_invitation','marketplace_application','employer_interest')",
            name="ck_ats_applications_source",
        ),
        CheckConstraint(
            "candidate_consent_status IN ('requested','accepted','declined')",
            name="ck_ats_applications_consent",
        ),
        CheckConstraint(
            "status <> 'hired' OR hire_handoff_requested_at IS NOT NULL",
            name="ck_ats_applications_hire_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="invited", nullable=False, index=True)
    stage_notes: Mapped[str | None] = mapped_column(Text)
    hire_handoff_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hire_handoff_requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="private_invitation", nullable=False)
    candidate_consent_status: Mapped[str] = mapped_column(
        String(20), default="accepted", nullable=False
    )


class AtsCandidateInvitation(TimestampMixin, BasicBase):
    __tablename__ = "ats_candidate_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="RESTRICT",
            name="fk_ats_invitations_org_application",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_invitations_org_id"),
        UniqueConstraint("token_digest", name="uq_ats_invitations_token"),
        CheckConstraint("expires_at > created_at", name="ck_ats_invitations_expiry"),
        CheckConstraint(
            "NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_ats_invitations_terminal",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AtsOffer(TimestampMixin, BasicBase):
    __tablename__ = "ats_offers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="RESTRICT",
            name="fk_ats_offers_org_application",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_offers_org_id"),
        UniqueConstraint(
            "organization_id", "application_id", "version", name="uq_ats_offers_application_version"
        ),
        Index(
            "uq_ats_offers_client_operation",
            "organization_id",
            "client_operation_id",
            unique=True,
        ),
        CheckConstraint("version > 0", name="ck_ats_offers_version"),
        CheckConstraint(
            "status IN ('draft','sent','accepted','declined','withdrawn','superseded')",
            name="ck_ats_offers_status",
        ),
        CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL", name="ck_ats_offers_sent_evidence"
        ),
        CheckConstraint(
            "status <> 'accepted' OR accepted_at IS NOT NULL", name="ck_ats_offers_accept_evidence"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    client_operation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    position_title: Mapped[str] = mapped_column(String(180), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    compensation: Mapped[str | None] = mapped_column(String(255))
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AtsEvent(BasicBase):
    __tablename__ = "ats_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ats_events_org_id"),
        CheckConstraint("length(trim(event_type)) > 0", name="ck_ats_events_type"),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, default=uuid4, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AtsStaffProvisioning(BasicBase):
    __tablename__ = "ats_staff_provisionings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="RESTRICT",
            name="fk_ats_provisioning_application",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_ats_provisioning_membership",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_provisioning_org_id"),
        UniqueConstraint(
            "organization_id", "application_id", name="uq_ats_provisioning_application"
        ),
        UniqueConstraint("organization_id", "operation_id", name="uq_ats_provisioning_operation"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    candidate_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provisioned_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provisioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    membership_created: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ScheduledStaffShift(TimestampMixin, BasicBase):
    """A planned rota interval, distinct from server-recorded clock evidence."""

    __tablename__ = "staff_scheduled_shifts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_room",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supersedes_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_supersedes",
        ),
        UniqueConstraint("organization_id", "id", name="uq_scheduled_shifts_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_scheduled_shifts_create_operation",
        ),
        CheckConstraint(
            "status IN ('draft','published','cancelled')",
            name="ck_scheduled_shifts_status",
        ),
        CheckConstraint(
            "response_status IN ('pending','acknowledged','declined','alternate_proposed')",
            name="ck_scheduled_shifts_response",
        ),
        CheckConstraint(
            "scheduled_end_at > scheduled_start_at",
            name="ck_scheduled_shifts_interval",
        ),
        CheckConstraint(
            "(status = 'draft' AND published_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_scheduled_shifts_lifecycle",
        ),
        CheckConstraint(
            "(response_status = 'alternate_proposed' AND proposed_start_at IS NOT NULL "
            "AND proposed_end_at IS NOT NULL AND proposed_end_at > proposed_start_at) OR "
            "(response_status <> 'alternate_proposed' AND proposed_start_at IS NULL "
            "AND proposed_end_at IS NULL)",
            name="ck_scheduled_shifts_proposal",
        ),
        CheckConstraint(
            "(response_status = 'pending' AND responded_at IS NULL "
            "AND response_note IS NULL) OR "
            "(response_status <> 'pending' AND responded_at IS NOT NULL)",
            name="ck_scheduled_shifts_response_time",
        ),
        CheckConstraint(
            "availability_override_reason IS NULL OR "
            "length(trim(availability_override_reason)) > 0",
            name="ck_scheduled_shifts_availability_override",
        ),
        CheckConstraint(
            "(origin_type IS NULL AND origin_id IS NULL AND origin_occurrence_key IS NULL) OR "
            "(origin_type IS NOT NULL AND origin_id IS NOT NULL "
            "AND origin_occurrence_key IS NOT NULL "
            "AND length(trim(origin_occurrence_key)) > 0)",
            name="ck_scheduled_shifts_origin_triplet",
        ),
        CheckConstraint(
            "origin_type IS NULL OR origin_type IN ('rotation','open_shift','swap')",
            name="ck_scheduled_shifts_origin_type",
        ),
        CheckConstraint(
            "supersedes_schedule_id IS NULL OR supersedes_schedule_id <> id",
            name="ck_scheduled_shifts_not_self_superseding",
        ),
        CheckConstraint(
            "supersedes_schedule_id IS NULL OR "
            "(origin_type IS NOT NULL AND origin_type IN ('open_shift','swap'))",
            name="ck_scheduled_shifts_supersedes_origin",
        ),
        CheckConstraint(
            "origin_type <> 'rotation' OR supersedes_schedule_id IS NULL",
            name="ck_scheduled_shifts_rotation_not_replacement",
        ),
        CheckConstraint(
            "origin_type <> 'swap' OR supersedes_schedule_id IS NOT NULL",
            name="ck_scheduled_shifts_swap_replacement",
        ),
        Index(
            "uq_scheduled_shifts_origin_occurrence",
            "organization_id",
            "origin_type",
            "origin_id",
            "origin_occurrence_key",
            unique=True,
            postgresql_where=text("origin_type IS NOT NULL"),
            sqlite_where=text("origin_type IS NOT NULL"),
        ),
        Index(
            "uq_scheduled_shifts_supersedes",
            "organization_id",
            "supersedes_schedule_id",
            unique=True,
            postgresql_where=text("supersedes_schedule_id IS NOT NULL"),
            sqlite_where=text("supersedes_schedule_id IS NOT NULL"),
        ),
        Index(
            "ix_scheduled_shifts_membership_window",
            "organization_id",
            "membership_id",
            "scheduled_start_at",
            "scheduled_end_at",
        ),
        Index(
            "ix_scheduled_shifts_facility_window",
            "organization_id",
            "facility_id",
            "scheduled_start_at",
            "scheduled_end_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    response_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    response_note: Mapped[str | None] = mapped_column(Text)
    proposed_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    availability_override_reason: Mapped[str | None] = mapped_column(Text)
    origin_type: Mapped[str | None] = mapped_column(String(20), index=True)
    origin_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    origin_occurrence_key: Mapped[str | None] = mapped_column(String(200))
    supersedes_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)


class ScheduledStaffShiftEvent(BasicBase):
    """Immutable idempotency and decision ledger for rota mutations."""

    __tablename__ = "staff_scheduled_shift_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "scheduled_shift_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shift_events_shift",
        ),
        UniqueConstraint("organization_id", "id", name="uq_scheduled_shift_events_org_id"),
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_scheduled_shift_events_operation",
        ),
        CheckConstraint(
            "event_type IN "
            "('created','updated','published','cancelled','acknowledged','declined',"
            "'alternate_proposed','alternate_accepted','alternate_rejected')",
            name="ck_scheduled_shift_events_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    scheduled_shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class StaffAvailabilityProfile(TimestampMixin, BasicBase):
    """A staff-owned recurring weekly availability declaration for one facility."""

    __tablename__ = "staff_availability_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_availability_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_availability_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_availability_org_id"),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "facility_id",
            name="uq_staff_availability_scope",
        ),
        CheckConstraint(
            "is_specified OR (json_array_length(windows) = 0 AND note IS NULL)",
            name="ck_staff_availability_tombstone",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    is_specified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class StaffTimeOffRequest(TimestampMixin, BasicBase):
    """An explicit interval of requested or approved leave."""

    __tablename__ = "staff_time_off_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_time_off_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_time_off_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_time_off_org_id"),
        UniqueConstraint(
            "organization_id", "create_operation_id", name="uq_staff_time_off_create_operation"
        ),
        CheckConstraint(
            "status IN ('pending','approved','declined','cancelled')",
            name="ck_staff_time_off_status",
        ),
        CheckConstraint(
            "category IN ('vacation','sick','personal','medical','bereavement','unpaid','other')",
            name="ck_staff_time_off_category",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_staff_time_off_interval"),
        CheckConstraint(
            "(status = 'pending' AND decided_at IS NULL AND decided_by_user_id IS NULL "
            "AND response_note IS NULL AND cancelled_at IS NULL "
            "AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL) OR "
            "(status IN ('approved','declined') AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL AND cancelled_at IS NULL "
            "AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancelled_by_user_id IS NOT NULL AND cancellation_reason IS NOT NULL "
            "AND length(trim(cancellation_reason)) > 0)",
            name="ck_staff_time_off_lifecycle",
        ),
        Index(
            "ix_staff_time_off_membership_window",
            "organization_id",
            "membership_id",
            "starts_at",
            "ends_at",
        ),
        Index(
            "ix_staff_time_off_facility_window",
            "organization_id",
            "facility_id",
            "starts_at",
            "ends_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    response_note: Mapped[str | None] = mapped_column(Text)
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)


class StaffShiftTemplate(TimestampMixin, BasicBase):
    """A reusable facility-local shift shape; never itself a scheduled shift."""

    __tablename__ = "staff_shift_templates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_templates_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_templates_room",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_shift_templates_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_shift_templates_create_operation",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_staff_shift_templates_weekday"),
        CheckConstraint("end_local > start_local", name="ck_staff_shift_templates_interval"),
        CheckConstraint("length(trim(name)) > 0", name="ck_staff_shift_templates_name"),
        CheckConstraint(
            "(is_active AND deactivated_at IS NULL AND deactivated_by_user_id IS NULL) OR "
            "(NOT is_active AND deactivated_at IS NOT NULL "
            "AND deactivated_by_user_id IS NOT NULL)",
            name="ck_staff_shift_templates_lifecycle",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_local: Mapped[time] = mapped_column(Time, nullable=False)
    end_local: Mapped[time] = mapped_column(Time, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class StaffCoverageTargetProfile(TimestampMixin, BasicBase):
    """Weekly minimum staffing targets for a facility or one room."""

    __tablename__ = "staff_coverage_target_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_coverage_targets_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_coverage_targets_room",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_coverage_targets_org_id"),
        Index(
            "uq_staff_coverage_targets_facility",
            "organization_id",
            "facility_id",
            unique=True,
            postgresql_where=text("room_id IS NULL"),
            sqlite_where=text("room_id IS NULL"),
        ),
        Index(
            "uq_staff_coverage_targets_room",
            "organization_id",
            "facility_id",
            "room_id",
            unique=True,
            postgresql_where=text("room_id IS NOT NULL"),
            sqlite_where=text("room_id IS NOT NULL"),
        ),
        CheckConstraint(
            "is_specified OR json_array_length(windows) = 0",
            name="ck_staff_coverage_targets_tombstone",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    is_specified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class StaffWorkforceEvent(BasicBase):
    """Immutable exact-operation ledger for workforce planning mutations."""

    __tablename__ = "staff_workforce_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_staff_workforce_events_org_id"),
        UniqueConstraint(
            "organization_id", "operation_id", name="uq_staff_workforce_events_operation"
        ),
        CheckConstraint(
            "entity_type IN ('staff_availability','staff_time_off','staff_shift_template',"
            "'staff_coverage_target','staff_rotation_pattern','staff_open_shift',"
            "'staff_open_shift_engagement','staff_substitute_profile','staff_shift_swap')",
            name="ck_staff_workforce_events_entity",
        ),
        CheckConstraint(
            "event_type IN ('replaced','removed','requested','approved','declined','cancelled',"
            "'created','updated','deactivated','activated','retired','generated','posted',"
            "'filled','interested','offered','withdrawn','rejected','converted','superseded',"
            "'accepted','counterparty_accepted')",
            name="ck_staff_workforce_events_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class StaffRotationPattern(TimestampMixin, BasicBase):
    """A validated, versioned facility-local source for draft rota occurrences."""

    __tablename__ = "staff_rotation_patterns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_rotation_patterns_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_rotation_patterns_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_rotation_patterns_create_operation",
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "name",
            "version",
            name="uq_staff_rotation_patterns_version",
        ),
        Index(
            "uq_staff_rotation_patterns_active_name",
            "organization_id",
            "facility_id",
            "name",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_staff_rotation_patterns_name"),
        CheckConstraint("version > 0", name="ck_staff_rotation_patterns_version"),
        CheckConstraint(
            "cycle_length_weeks >= 1 AND cycle_length_weeks <= 8",
            name="ck_staff_rotation_patterns_cycle",
        ),
        CheckConstraint(
            "json_array_length(slots) >= 1 AND json_array_length(slots) <= 500",
            name="ck_staff_rotation_patterns_slots",
        ),
        CheckConstraint(
            "status IN ('draft','active','retired')",
            name="ck_staff_rotation_patterns_status",
        ),
        CheckConstraint(
            "(status = 'draft' AND snapshot_digest IS NULL "
            "AND activation_operation_id IS NULL AND activated_at IS NULL "
            "AND activated_by_user_id IS NULL AND retirement_operation_id IS NULL "
            "AND retired_at IS NULL AND retired_by_user_id IS NULL "
            "AND retirement_reason IS NULL) OR "
            "(status = 'active' AND snapshot_digest IS NOT NULL "
            "AND length(snapshot_digest) = 64 AND activation_operation_id IS NOT NULL "
            "AND activated_at IS NOT NULL AND activated_by_user_id IS NOT NULL "
            "AND retirement_operation_id IS NULL AND retired_at IS NULL "
            "AND retired_by_user_id IS NULL AND retirement_reason IS NULL) OR "
            "(status = 'retired' AND snapshot_digest IS NOT NULL "
            "AND length(snapshot_digest) = 64 AND activation_operation_id IS NOT NULL "
            "AND activated_at IS NOT NULL AND activated_by_user_id IS NOT NULL "
            "AND retirement_operation_id IS NOT NULL AND retired_at IS NOT NULL "
            "AND retired_by_user_id IS NOT NULL AND retirement_reason IS NOT NULL "
            "AND length(trim(retirement_reason)) > 0)",
            name="ck_staff_rotation_patterns_lifecycle",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_week_start: Mapped[date] = mapped_column(Date, nullable=False)
    slots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    snapshot_digest: Mapped[str | None] = mapped_column(String(64))
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    activation_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retirement_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retirement_reason: Mapped[str | None] = mapped_column(Text)


class StaffOpenShift(TimestampMixin, BasicBase):
    """A facility coverage opportunity that is not an assignment until filled."""

    __tablename__ = "staff_open_shifts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_room",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_source_schedule",
        ),
        ForeignKeyConstraint(
            ["organization_id", "result_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_result_schedule",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_open_shifts_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_open_shifts_create_operation",
        ),
        CheckConstraint(
            "status IN ('draft','open','filled','cancelled')",
            name="ck_staff_open_shifts_status",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_staff_open_shifts_interval"),
        CheckConstraint(
            "source_schedule_id IS NULL OR result_schedule_id IS NULL "
            "OR source_schedule_id <> result_schedule_id",
            name="ck_staff_open_shifts_distinct_schedules",
        ),
        CheckConstraint(
            "(status = 'draft' AND posted_at IS NULL AND posted_by_user_id IS NULL "
            "AND post_operation_id IS NULL AND filled_at IS NULL "
            "AND filled_by_user_id IS NULL AND result_schedule_id IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND cancellation_reason IS NULL) OR "
            "(status = 'open' AND posted_at IS NOT NULL AND posted_by_user_id IS NOT NULL "
            "AND post_operation_id IS NOT NULL AND filled_at IS NULL "
            "AND filled_by_user_id IS NULL AND result_schedule_id IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND cancellation_reason IS NULL) OR "
            "(status = 'filled' AND posted_at IS NOT NULL AND posted_by_user_id IS NOT NULL "
            "AND post_operation_id IS NOT NULL AND filled_at IS NOT NULL "
            "AND filled_by_user_id IS NOT NULL AND result_schedule_id IS NOT NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND cancellation_reason IS NULL) OR "
            "(status = 'cancelled' AND filled_at IS NULL AND filled_by_user_id IS NULL "
            "AND result_schedule_id IS NULL AND cancelled_at IS NOT NULL "
            "AND cancelled_by_user_id IS NOT NULL AND cancellation_reason IS NOT NULL "
            "AND length(trim(cancellation_reason)) > 0 "
            "AND ((posted_at IS NULL AND posted_by_user_id IS NULL "
            "AND post_operation_id IS NULL) OR (posted_at IS NOT NULL "
            "AND posted_by_user_id IS NOT NULL AND post_operation_id IS NOT NULL)))",
            name="ck_staff_open_shifts_lifecycle",
        ),
        Index(
            "uq_staff_open_shifts_result_schedule",
            "organization_id",
            "result_schedule_id",
            unique=True,
            postgresql_where=text("result_schedule_id IS NOT NULL"),
            sqlite_where=text("result_schedule_id IS NOT NULL"),
        ),
        Index(
            "uq_staff_open_shifts_active_source",
            "organization_id",
            "source_schedule_id",
            unique=True,
            postgresql_where=text("source_schedule_id IS NOT NULL AND status IN ('draft','open')"),
            sqlite_where=text("source_schedule_id IS NOT NULL AND status IN ('draft','open')"),
        ),
        Index(
            "ix_staff_open_shifts_facility_window",
            "organization_id",
            "facility_id",
            "starts_at",
            "ends_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    source_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    result_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    post_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)


class StaffOpenShiftEngagement(TimestampMixin, BasicBase):
    """A staff interest or targeted offer; only accepted offers create assignments."""

    __tablename__ = "staff_open_shift_engagements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "open_shift_id"],
            ["staff_open_shifts.organization_id", "staff_open_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_open_shift",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_interest_id"],
            ["staff_open_shift_engagements.organization_id", "staff_open_shift_engagements.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_source_interest",
        ),
        ForeignKeyConstraint(
            ["organization_id", "converted_offer_id"],
            ["staff_open_shift_engagements.organization_id", "staff_open_shift_engagements.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_converted_offer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "result_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_result_schedule",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_open_shift_engagements_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_open_shift_engagements_create_operation",
        ),
        CheckConstraint("kind IN ('interest','offer')", name="ck_staff_open_engagements_kind"),
        CheckConstraint(
            "status IN ('pending','withdrawn','rejected','converted','superseded',"
            "'accepted','declined')",
            name="ck_staff_open_engagements_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND terminal_at IS NULL AND terminal_by_user_id IS NULL) OR "
            "(status <> 'pending' AND terminal_at IS NOT NULL "
            "AND terminal_by_user_id IS NOT NULL)",
            name="ck_staff_open_engagements_terminal",
        ),
        CheckConstraint(
            "status <> 'pending' OR terminal_reason IS NULL",
            name="ck_staff_open_engagements_pending_reason",
        ),
        CheckConstraint(
            "(kind = 'interest' AND status IN "
            "('pending','withdrawn','rejected','converted','superseded') "
            "AND expires_at IS NULL AND source_interest_id IS NULL "
            "AND result_schedule_id IS NULL "
            "AND ((status = 'converted' AND converted_offer_id IS NOT NULL) OR "
            "(status <> 'converted' AND converted_offer_id IS NULL))) OR "
            "(kind = 'offer' AND status IN "
            "('pending','withdrawn','superseded','accepted','declined') "
            "AND expires_at IS NOT NULL AND converted_offer_id IS NULL "
            "AND ((status = 'accepted' AND result_schedule_id IS NOT NULL) OR "
            "(status <> 'accepted' AND result_schedule_id IS NULL)))",
            name="ck_staff_open_engagements_kind_lifecycle",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_staff_open_engagements_expiry",
        ),
        CheckConstraint(
            "source_interest_id IS NULL OR source_interest_id <> id",
            name="ck_staff_open_engagements_source_not_self",
        ),
        CheckConstraint(
            "converted_offer_id IS NULL OR converted_offer_id <> id",
            name="ck_staff_open_engagements_result_not_self",
        ),
        Index(
            "uq_staff_open_engagements_pending",
            "organization_id",
            "open_shift_id",
            "membership_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "uq_staff_open_engagements_source_interest",
            "organization_id",
            "source_interest_id",
            unique=True,
            postgresql_where=text("source_interest_id IS NOT NULL"),
            sqlite_where=text("source_interest_id IS NOT NULL"),
        ),
        Index(
            "uq_staff_open_engagements_converted_offer",
            "organization_id",
            "converted_offer_id",
            unique=True,
            postgresql_where=text("converted_offer_id IS NOT NULL"),
            sqlite_where=text("converted_offer_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    open_shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_interest_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    converted_offer_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    result_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    terminal_reason: Mapped[str | None] = mapped_column(Text)


class StaffSubstituteProfile(TimestampMixin, BasicBase):
    """A staff-owned, facility-scoped proactive coverage opt-in projection."""

    __tablename__ = "staff_substitute_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_substitute_profiles_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_substitute_profiles_facility",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_substitute_profiles_org_id"),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "membership_id",
            name="uq_staff_substitute_profiles_scope",
        ),
        CheckConstraint(
            "is_specified OR (NOT is_opted_in AND note IS NULL)",
            name="ck_staff_substitute_profiles_tombstone",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    is_specified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_opted_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class StaffShiftSwapRequest(TimestampMixin, BasicBase):
    """A whole-shift cover or reciprocal trade proposal requiring manager approval."""

    __tablename__ = "staff_shift_swap_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requester_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "counterparty_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requester_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_schedule",
        ),
        ForeignKeyConstraint(
            ["organization_id", "counterparty_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_schedule",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requester_replacement_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_replacement",
        ),
        ForeignKeyConstraint(
            ["organization_id", "counterparty_replacement_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_replacement",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_shift_swaps_org_id"),
        UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_shift_swaps_create_operation",
        ),
        CheckConstraint("kind IN ('cover','trade')", name="ck_staff_shift_swaps_kind"),
        CheckConstraint(
            "status IN ('pending_counterparty','pending_manager','approved','declined',"
            "'cancelled','rejected')",
            name="ck_staff_shift_swaps_status",
        ),
        CheckConstraint(
            "requester_membership_id <> counterparty_membership_id",
            name="ck_staff_shift_swaps_distinct_memberships",
        ),
        CheckConstraint(
            "(counterparty_responded_at IS NULL AND "
            "counterparty_responded_by_user_id IS NULL) OR "
            "(counterparty_responded_at IS NOT NULL AND "
            "counterparty_responded_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_counterparty_pair",
        ),
        CheckConstraint(
            "(manager_decided_at IS NULL AND manager_decided_by_user_id IS NULL) OR "
            "(manager_decided_at IS NOT NULL AND manager_decided_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_manager_pair",
        ),
        CheckConstraint(
            "(cancelled_at IS NULL AND cancelled_by_user_id IS NULL) OR "
            "(cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_cancel_pair",
        ),
        CheckConstraint(
            "counterparty_response_note IS NULL OR counterparty_responded_at IS NOT NULL",
            name="ck_staff_shift_swaps_counterparty_note_evidence",
        ),
        CheckConstraint(
            "status <> 'declined' OR (counterparty_response_note IS NOT NULL "
            "AND length(trim(counterparty_response_note)) > 0)",
            name="ck_staff_shift_swaps_decline_reason",
        ),
        CheckConstraint(
            "manager_decision_reason IS NULL OR manager_decided_at IS NOT NULL",
            name="ck_staff_shift_swaps_manager_reason_evidence",
        ),
        CheckConstraint(
            "(kind = 'cover' AND counterparty_schedule_id IS NULL "
            "AND counterparty_schedule_updated_at IS NULL) OR "
            "(kind = 'trade' AND counterparty_schedule_id IS NOT NULL "
            "AND counterparty_schedule_updated_at IS NOT NULL "
            "AND counterparty_schedule_id <> requester_schedule_id)",
            name="ck_staff_shift_swaps_originals",
        ),
        CheckConstraint(
            "(status = 'pending_counterparty' AND counterparty_responded_at IS NULL "
            "AND counterparty_responded_by_user_id IS NULL "
            "AND manager_decided_at IS NULL AND manager_decided_by_user_id IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND requester_replacement_schedule_id IS NULL "
            "AND counterparty_replacement_schedule_id IS NULL) OR "
            "(status = 'pending_manager' AND counterparty_responded_at IS NOT NULL "
            "AND counterparty_responded_by_user_id IS NOT NULL "
            "AND manager_decided_at IS NULL AND manager_decided_by_user_id IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND requester_replacement_schedule_id IS NULL "
            "AND counterparty_replacement_schedule_id IS NULL) OR "
            "(status = 'approved' AND counterparty_responded_at IS NOT NULL "
            "AND counterparty_responded_by_user_id IS NOT NULL "
            "AND manager_decided_at IS NOT NULL AND manager_decided_by_user_id IS NOT NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND requester_replacement_schedule_id IS NOT NULL "
            "AND ((kind = 'cover' AND counterparty_replacement_schedule_id IS NULL) OR "
            "(kind = 'trade' AND counterparty_replacement_schedule_id IS NOT NULL))) OR "
            "(status = 'declined' AND counterparty_responded_at IS NOT NULL "
            "AND counterparty_responded_by_user_id IS NOT NULL "
            "AND manager_decided_at IS NULL AND manager_decided_by_user_id IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND requester_replacement_schedule_id IS NULL "
            "AND counterparty_replacement_schedule_id IS NULL) OR "
            "(status = 'rejected' AND counterparty_responded_at IS NOT NULL "
            "AND counterparty_responded_by_user_id IS NOT NULL "
            "AND manager_decided_at IS NOT NULL AND manager_decided_by_user_id IS NOT NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
            "AND requester_replacement_schedule_id IS NULL "
            "AND counterparty_replacement_schedule_id IS NULL) OR "
            "(status = 'cancelled' AND manager_decided_at IS NULL "
            "AND manager_decided_by_user_id IS NULL AND cancelled_at IS NOT NULL "
            "AND cancelled_by_user_id IS NOT NULL "
            "AND requester_replacement_schedule_id IS NULL "
            "AND counterparty_replacement_schedule_id IS NULL)",
            name="ck_staff_shift_swaps_lifecycle",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (manager_decision_reason IS NOT NULL "
            "AND length(trim(manager_decision_reason)) > 0)",
            name="ck_staff_shift_swaps_rejection_reason",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancellation_reason IS NOT NULL "
            "AND length(trim(cancellation_reason)) > 0) OR "
            "(status <> 'cancelled' AND cancellation_reason IS NULL)",
            name="ck_staff_shift_swaps_cancellation_reason",
        ),
        Index(
            "ix_staff_shift_swaps_facility_status",
            "organization_id",
            "facility_id",
            "status",
        ),
        Index("ix_staff_shift_swaps_org", "organization_id"),
        Index("ix_staff_shift_swaps_facility", "facility_id"),
        Index("ix_staff_shift_swaps_kind", "kind"),
        Index("ix_staff_shift_swaps_status", "status"),
        Index("ix_staff_shift_swaps_requester_member", "requester_membership_id"),
        Index("ix_staff_shift_swaps_counterparty_member", "counterparty_membership_id"),
        Index("ix_staff_shift_swaps_requester_sched", "requester_schedule_id"),
        Index("ix_staff_shift_swaps_counterparty_sched", "counterparty_schedule_id"),
        Index("ix_staff_shift_swaps_requester_repl", "requester_replacement_schedule_id"),
        Index(
            "ix_staff_shift_swaps_counterparty_repl",
            "counterparty_replacement_schedule_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_counterparty", nullable=False)
    requester_membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    counterparty_membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requester_schedule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requester_schedule_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    counterparty_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    counterparty_schedule_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    requester_replacement_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    counterparty_replacement_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    counterparty_response_note: Mapped[str | None] = mapped_column(Text)
    manager_decision_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    create_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    counterparty_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counterparty_responded_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    manager_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_decided_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class StaffShift(TimestampMixin, BasicBase):
    __tablename__ = "staff_shifts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_shifts_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_shifts_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "scheduled_shift_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shifts_scheduled_shift",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_shifts_org_id"),
        CheckConstraint("status IN ('open','closed')", name="ck_staff_shifts_status"),
        CheckConstraint(
            "(status = 'open' AND clocked_out_at IS NULL) OR "
            "(status = 'closed' AND clocked_out_at IS NOT NULL)",
            name="ck_staff_shifts_terminal",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    scheduled_shift_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    clocked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clocked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffShiftEvent(BasicBase):
    __tablename__ = "staff_shift_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "shift_id"],
            ["staff_shifts.organization_id", "staff_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_events_shift",
        ),
        UniqueConstraint("organization_id", "id", name="uq_staff_shift_events_org_id"),
        UniqueConstraint("organization_id", "operation_id", name="uq_staff_shift_events_operation"),
        CheckConstraint(
            "event_type IN ('clock_in','clock_out')", name="ck_staff_shift_events_type"
        ),
        CheckConstraint(
            "accuracy_meters >= 0 AND distance_meters >= 0", name="ck_staff_shift_events_distance"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    server_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    accuracy_meters: Mapped[float | None] = mapped_column(Numeric(8, 2))
    distance_meters: Mapped[float | None] = mapped_column(Numeric(10, 2))
    radius_meters: Mapped[int | None] = mapped_column(Integer)


class StaffRoomPresenceSession(TimestampMixin, BasicBase):
    """One server-confirmed interval where a clocked-in member served one room."""

    __tablename__ = "staff_room_presence_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "staff_shift_id"],
            ["staff_shifts.organization_id", "staff_shifts.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_shift",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_room",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_room_presence_sessions_org_id"
        ),
        Index(
            "uq_room_presence_sessions_open_membership",
            "organization_id",
            "membership_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
        Index(
            "uq_room_presence_sessions_open_shift",
            "organization_id",
            "staff_shift_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
        Index(
            "ix_room_presence_sessions_room_live",
            "organization_id",
            "facility_id",
            "room_id",
            "ended_at",
        ),
        CheckConstraint(
            "source IN ('scheduled_room','single_assignment','staff_selected')",
            name="ck_room_presence_sessions_source",
        ),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN "
            "('moved','staff_ended','clocked_out','access_revoked')",
            name="ck_room_presence_sessions_end_reason",
        ),
        CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL AND end_operation_id IS NULL "
            "AND ended_by_user_id IS NULL) OR "
            "(ended_at IS NOT NULL AND end_reason IS NOT NULL "
            "AND end_operation_id IS NOT NULL AND ended_by_user_id IS NOT NULL)",
            name="ck_room_presence_sessions_terminal_bundle",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_room_presence_sessions_time_order",
        ),
        CheckConstraint(
            "(ended_at IS NULL AND version = 1) OR "
            "(ended_at IS NOT NULL AND version = 2)",
            name="ck_room_presence_sessions_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    staff_shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(30))
    start_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    end_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    started_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_started_by",
        ),
        nullable=False,
    )
    ended_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_ended_by",
        ),
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class StaffRoomPresenceEvent(BasicBase):
    """Append-only receipt and decision ledger for room-presence commands."""

    __tablename__ = "staff_room_presence_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_events_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "staff_shift_id"],
            ["staff_shifts.organization_id", "staff_shifts.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_events_shift",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_events_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "from_session_id"],
            ["staff_room_presence_sessions.organization_id", "staff_room_presence_sessions.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_events_from_session",
        ),
        ForeignKeyConstraint(
            ["organization_id", "to_session_id"],
            ["staff_room_presence_sessions.organization_id", "staff_room_presence_sessions.id"],
            ondelete="RESTRICT",
            name="fk_room_presence_events_to_session",
        ),
        UniqueConstraint("organization_id", "id", name="uq_room_presence_events_org_id"),
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_room_presence_events_operation",
        ),
        Index(
            "ix_room_presence_events_membership_time",
            "organization_id",
            "membership_id",
            "occurred_at",
        ),
        CheckConstraint(
            "event_type IN ('started','moved','ended','clock_started_presence',"
            "'clock_ended_presence','access_revoked_presence')",
            name="ck_room_presence_events_type",
        ),
        CheckConstraint(
            "(event_type IN ('started','clock_started_presence') "
            "AND from_session_id IS NULL AND to_session_id IS NOT NULL) OR "
            "(event_type = 'moved' AND from_session_id IS NOT NULL "
            "AND to_session_id IS NOT NULL AND from_session_id <> to_session_id) OR "
            "(event_type IN ('ended','clock_ended_presence','access_revoked_presence') "
            "AND from_session_id IS NOT NULL AND to_session_id IS NULL)",
            name="ck_room_presence_events_transition",
        ),
        CheckConstraint(
            _lowercase_sha256_check("request_sha256"),
            name="ck_room_presence_events_request_sha256",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_events_actor",
        ),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    staff_shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    to_session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    request_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    intent: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class RoomOperationalExceptionHead(TimestampMixin, BasicBase):
    """Current head of one operational configured-target exception episode."""

    __tablename__ = "room_operational_exception_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_room_operational_exceptions_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_room_operational_exceptions_room",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_room_operational_exceptions_org_id"
        ),
        Index(
            "uq_room_operational_exceptions_unresolved",
            "organization_id",
            "scope_kind",
            "scope_id",
            "condition_code",
            unique=True,
            postgresql_where=text("state <> 'resolved'"),
            sqlite_where=text("state <> 'resolved'"),
        ),
        Index(
            "ix_room_operational_exceptions_facility_state",
            "organization_id",
            "facility_id",
            "state",
            "last_changed_at",
        ),
        CheckConstraint(
            "scope_kind IN ('facility','room')",
            name="ck_room_operational_exceptions_scope",
        ),
        CheckConstraint(
            "(scope_kind = 'facility' AND room_id IS NULL AND scope_id = facility_id) OR "
            "(scope_kind = 'room' AND room_id IS NOT NULL AND scope_id = room_id)",
            name="ck_room_operational_exceptions_scope_identity",
        ),
        CheckConstraint(
            "condition_code IN "
            "('confirmed_children_above_configured_room_capacity',"
            "'confirmed_staff_below_configured_room_target',"
            "'open_shift_staff_without_current_room',"
            "'present_child_without_active_room','source_integrity_unknown')",
            name="ck_room_operational_exceptions_condition",
        ),
        CheckConstraint(
            "state IN ('open','acknowledged','resolved')",
            name="ck_room_operational_exceptions_state",
        ),
        CheckConstraint(
            _lowercase_sha256_check("current_fingerprint_sha256"),
            name="ck_room_operational_exceptions_fingerprint",
        ),
        CheckConstraint(
            "(state = 'open' AND acknowledged_at IS NULL "
            "AND acknowledged_by_user_id IS NULL AND acknowledgement_reason IS NULL "
            "AND resolved_at IS NULL) OR "
            "(state = 'acknowledged' AND acknowledged_at IS NOT NULL "
            "AND acknowledged_by_user_id IS NOT NULL "
            "AND length(trim(acknowledgement_reason)) >= 5 "
            "AND resolved_at IS NULL) OR "
            "(state = 'resolved' AND resolved_at IS NOT NULL AND ("
            "(acknowledged_at IS NULL AND acknowledged_by_user_id IS NULL "
            "AND acknowledgement_reason IS NULL) OR "
            "(acknowledged_at IS NOT NULL AND acknowledged_by_user_id IS NOT NULL "
            "AND length(trim(acknowledgement_reason)) >= 5)))",
            name="ck_room_operational_exceptions_state_bundle",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_room_operational_exceptions_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    condition_code: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    current_fingerprint_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    current_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_operational_exceptions_acknowledged_by",
        ),
    )
    acknowledgement_reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class RoomOperationalExceptionEvent(BasicBase):
    """Append-only lifecycle and human acknowledgement evidence."""

    __tablename__ = "room_operational_exception_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "exception_id"],
            [
                "room_operational_exception_heads.organization_id",
                "room_operational_exception_heads.id",
            ],
            ondelete="RESTRICT",
            name="fk_room_operational_exception_events_head",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_room_operational_exception_events_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_room_operational_exception_events_operation",
        ),
        Index(
            "ix_room_operational_exception_events_timeline",
            "organization_id",
            "exception_id",
            "occurred_at",
        ),
        CheckConstraint(
            "event_type IN ('opened','materially_changed','acknowledged','resolved')",
            name="ck_room_operational_exception_events_type",
        ),
        CheckConstraint(
            "(event_type = 'acknowledged' AND actor_user_id IS NOT NULL "
            "AND reason IS NOT NULL AND length(trim(reason)) >= 5) OR "
            "(event_type <> 'acknowledged' AND reason IS NULL)",
            name="ck_room_operational_exception_events_acknowledgement",
        ),
        CheckConstraint(
            _lowercase_sha256_check("current_fingerprint_sha256"),
            name="ck_room_operational_exception_events_current_fingerprint",
        ),
        CheckConstraint(
            "previous_fingerprint_sha256 IS NULL OR "
            + _lowercase_sha256_check("previous_fingerprint_sha256"),
            name="ck_room_operational_exception_events_previous_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    exception_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_operational_exception_events_actor",
        ),
    )
    cause_entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    cause_entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    previous_fingerprint_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    current_fingerprint_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class RealtimeEvent(BasicBase):
    __tablename__ = "realtime_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_realtime_events_org_id"),
        CheckConstraint("length(trim(event_type)) > 0", name="ck_realtime_events_type"),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, default=uuid4, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PublicJobCatalogEvent(BasicBase):
    """Public-safe catalog invalidation bound to one canonical realtime event.

    The table deliberately contains no listing copy, employer-authored text, or
    candidate data.  Candidates use it only to discover that the canonical
    marketplace projection must be refreshed.
    """

    __tablename__ = "public_job_catalog_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_public_job_catalog_event_id"),
        UniqueConstraint(
            "listing_id",
            "listing_version",
            name="uq_public_job_catalog_listing_version",
        ),
        CheckConstraint(
            "public_status IN ('open','paused','closed')",
            name="ck_public_job_catalog_status",
        ),
        CheckConstraint(
            "event_type IN ('job.updated','job.status_changed')",
            name="ck_public_job_catalog_event_type",
        ),
        CheckConstraint(
            "listing_version > 0",
            name="ck_public_job_catalog_version",
        ),
    )

    sequence_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("realtime_events.sequence_id", ondelete="RESTRICT"),
        primary_key=True,
        autoincrement=False,
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("realtime_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    public_status: Mapped[str] = mapped_column(String(20), nullable=False)
    listing_version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RealtimeTicket(BasicBase):
    __tablename__ = "realtime_tickets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_realtime_tickets_org_id"),
        UniqueConstraint("token_digest", name="uq_realtime_tickets_digest"),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="CASCADE",
            name="fk_realtime_tickets_membership",
        ),
        CheckConstraint("expires_at > created_at", name="ck_realtime_tickets_expiry"),
        CheckConstraint("auth_version > 0", name="ck_realtime_tickets_auth_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketplaceRealtimeTicket(BasicBase):
    """Single-use candidate-owned ticket; never grants tenant membership."""

    __tablename__ = "marketplace_realtime_tickets"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_marketplace_realtime_tickets_digest"),
        CheckConstraint("expires_at > created_at", name="ck_marketplace_realtime_tickets_expiry"),
        CheckConstraint(
            "auth_version > 0",
            name="ck_marketplace_realtime_tickets_auth_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketplaceProfile(TimestampMixin, BasicBase):
    __tablename__ = "marketplace_profiles"
    __table_args__ = (
        CheckConstraint(
            "certification_verification_status IN ('unverified','pending','verified','rejected')",
            name="ck_marketplace_profiles_certification_status",
        ),
        CheckConstraint(
            "candidate_type IS NULL OR candidate_type IN ('certified_educator','student')",
            name="ck_marketplace_profiles_candidate_type",
        ),
        CheckConstraint(
            "candidate_type <> 'student' OR (certification_type IS NULL AND "
            "certification_number IS NULL AND certification_expiry_date IS NULL AND "
            "certification_provenance IS NULL)",
            name="ck_marketplace_profiles_student_no_certificate",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(String(180), nullable=False)
    candidate_type: Mapped[str | None] = mapped_column(String(30), index=True)
    institution: Mapped[str | None] = mapped_column(String(180))
    program: Mapped[str | None] = mapped_column(String(180))
    expected_graduation_date: Mapped[date | None] = mapped_column(Date)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(30))
    bio: Mapped[str | None] = mapped_column(Text)
    certification_type: Mapped[str | None] = mapped_column(String(120))
    certification_number: Mapped[str | None] = mapped_column(String(120))
    certification_expiry_date: Mapped[date | None] = mapped_column(Date)
    certification_verification_status: Mapped[str] = mapped_column(
        String(30), default="unverified", nullable=False
    )
    work_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    certification_provenance: Mapped[str | None] = mapped_column(String(30))
    certification_candidate_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    work_history_provenance: Mapped[str | None] = mapped_column(String(30))
    work_history_candidate_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class MarketplaceProfilePhoto(TimestampMixin, BasicBase):
    """Candidate-private normalized image; never part of public discovery."""

    __tablename__ = "marketplace_profile_photos"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('image/jpeg','image/webp')",
            name="ck_marketplace_profile_photos_content_type",
        ),
        CheckConstraint("size_bytes > 0", name="ck_marketplace_profile_photos_size"),
        CheckConstraint(
            "width > 0 AND height > 0", name="ck_marketplace_profile_photos_dimensions"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))


class MarketplaceJob(BasicBase):
    __tablename__ = "marketplace_jobs"
    listing_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    openings: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketplaceApplicationLink(TimestampMixin, BasicBase):
    __tablename__ = "marketplace_application_links"
    __table_args__ = (
        UniqueConstraint("user_id", "application_id", name="uq_marketplace_links_user_application"),
        UniqueConstraint("user_id", "listing_id", name="uq_marketplace_links_user_listing"),
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="CASCADE",
            name="fk_marketplace_links_application",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    listing_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    listing_title: Mapped[str] = mapped_column(String(180), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    listing_location: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketplaceInterest(TimestampMixin, BasicBase):
    __tablename__ = "marketplace_interests"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_marketplace_interests_org_id"),
        UniqueConstraint(
            "organization_id",
            "profile_user_id",
            "job_id",
            name="uq_marketplace_interests_profile_job",
        ),
        CheckConstraint(
            "status IN ('requested','accepted','declined','withdrawn')",
            name="ck_marketplace_interests_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["ats_jobs.organization_id", "ats_jobs.id"],
            ondelete="CASCADE",
            name="fk_marketplace_interests_job",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    profile_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AtsInterview(TimestampMixin, BasicBase):
    __tablename__ = "ats_interviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="RESTRICT",
            name="fk_ats_interviews_application",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ats_interviews_org_id"),
        CheckConstraint(
            "status IN ('requested','confirmed','declined','cancelled',"
            "'candidate_proposed','proposal_declined')",
            name="ck_ats_interviews_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    location_or_link: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_proposal_note: Mapped[str | None] = mapped_column(Text)


class MarketplaceOnboardingState(TimestampMixin, BasicBase):
    __tablename__ = "marketplace_onboarding_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started','in_progress','review','complete')",
            name="ck_marketplace_onboarding_status",
        ),
        CheckConstraint(
            "current_step IN ('candidate_type','certificate','student_details',"
            "'work_experience','review','complete')",
            name="ck_marketplace_onboarding_step",
        ),
        CheckConstraint("version > 0", name="ck_marketplace_onboarding_version"),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_started", nullable=False)
    current_step: Mapped[str] = mapped_column(String(30), default="candidate_type", nullable=False)
    completed_steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketplaceDocumentAnalysis(TimestampMixin, BasicBase):
    __tablename__ = "marketplace_document_analyses"
    __table_args__ = (
        CheckConstraint(
            "document_kind IN ('certificate','resume')", name="ck_marketplace_analysis_kind"
        ),
        CheckConstraint(
            "status IN ('uploaded','analyzed','confirmed','failed','discarded')",
            name="ck_marketplace_analysis_status",
        ),
        CheckConstraint(
            "file_size_bytes > 0 AND page_count > 0", name="ck_marketplace_analysis_file"
        ),
        CheckConstraint(
            "overall_confidence IS NULL OR (overall_confidence >= 0 AND overall_confidence <= 1)",
            name="ck_marketplace_analysis_confidence",
        ),
        CheckConstraint(
            "raw_document_retained = false", name="ck_marketplace_analysis_no_retention"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    temporary_path: Mapped[str | None] = mapped_column(Text)
    raw_document_retained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ocr_engine: Mapped[str | None] = mapped_column(String(50))
    ocr_model: Mapped[str | None] = mapped_column(String(80))
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    field_confidences: Mapped[dict[str, float] | None] = mapped_column(JSON)
    overall_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(80))


class MarketplaceCredentialDocument(TimestampMixin, BasicBase):
    """Candidate-owned, immutable original credential evidence with version history."""

    __tablename__ = "marketplace_credential_documents"
    __table_args__ = (
        UniqueConstraint("analysis_id", name="uq_marketplace_credentials_analysis"),
        UniqueConstraint("user_id", "version_number", name="uq_marketplace_credentials_version"),
        CheckConstraint(
            "status IN ('uploaded','analyzed','confirmed','superseded','rejected','failed')",
            name="ck_marketplace_credentials_status",
        ),
        CheckConstraint(
            "content_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_marketplace_credentials_content_type",
        ),
        CheckConstraint("size_bytes > 0", name="ck_marketplace_credentials_size"),
        CheckConstraint("version_number > 0", name="ck_marketplace_credentials_version"),
        CheckConstraint(
            "(is_current = false) OR (status = 'confirmed' AND confirmed_at IS NOT NULL)",
            name="ck_marketplace_credentials_current_confirmed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_document_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    holder_name: Mapped[str | None] = mapped_column(String(200))
    certificate_type: Mapped[str | None] = mapped_column(String(120))
    certificate_number: Mapped[str | None] = mapped_column(String(120))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketplaceCredentialNotification(TimestampMixin, BasicBase):
    """Persistent employer notification created when connected talent updates credentials."""

    __tablename__ = "marketplace_credential_notifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "credential_id", name="uq_marketplace_credential_notifications_org"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_credential_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_certificate_type: Mapped[str | None] = mapped_column(String(120))
    certificate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AtsJobScreeningTerms(TimestampMixin, BasicBase):
    """0030 structured job duties, isolated from the retained 0028 job mapping."""

    __tablename__ = "ats_job_screening_terms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["ats_jobs.organization_id", "ats_jobs.id"],
            ondelete="CASCADE",
            name="fk_job_screening_terms_job",
        ),
        CheckConstraint(
            "position_shape IN ('educator_only','driver_only','educator_driver')",
            name="ck_job_screening_terms_position_shape",
        ),
        CheckConstraint(
            "driving_requirement IN ('not_applicable','preferred','required')",
            name="ck_job_screening_terms_driving_requirement",
        ),
        CheckConstraint(
            "vehicle_expectation IN ('none','organization_vehicle','personal_vehicle','either')",
            name="ck_job_screening_terms_vehicle_expectation",
        ),
        CheckConstraint(
            "minimum_driving_experience_months >= 0",
            name="ck_job_screening_terms_experience",
        ),
        CheckConstraint(
            "(position_shape = 'educator_only' AND driving_requirement = 'not_applicable' "
            "AND vehicle_expectation = 'none') OR "
            "(position_shape <> 'educator_only' AND driving_requirement <> 'not_applicable' "
            "AND vehicle_expectation <> 'none')",
            name="ck_job_screening_terms_pair",
        ),
        CheckConstraint(
            "position_shape <> 'driver_only' OR driving_requirement = 'required'",
            name="ck_job_screening_terms_driver_required",
        ),
        CheckConstraint("version > 0", name="ck_job_screening_terms_version"),
    )

    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    position_shape: Mapped[str] = mapped_column(String(30), nullable=False)
    driving_requirement: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_expectation: Mapped[str] = mapped_column(String(30), nullable=False)
    required_licence_jurisdiction: Mapped[str | None] = mapped_column(String(20))
    required_licence_jurisdiction_other: Mapped[str | None] = mapped_column(String(100))
    required_licence_class: Mapped[str | None] = mapped_column(String(30))
    minimum_driving_experience_months: Mapped[int] = mapped_column(Integer, nullable=False)
    service_area: Mapped[str | None] = mapped_column(String(500))
    service_windows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    mileage_policy: Mapped[str | None] = mapped_column(Text)
    driving_time_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    screening_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class MarketplaceJobScreeningTerms(BasicBase):
    """Public-safe projection of structured duties for an open marketplace listing."""

    __tablename__ = "marketplace_job_screening_terms"

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_jobs.listing_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position_shape: Mapped[str] = mapped_column(String(30), nullable=False)
    driving_requirement: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_expectation: Mapped[str] = mapped_column(String(30), nullable=False)
    required_licence_jurisdiction: Mapped[str | None] = mapped_column(String(20))
    required_licence_jurisdiction_other: Mapped[str | None] = mapped_column(String(100))
    required_licence_class: Mapped[str | None] = mapped_column(String(30))
    minimum_driving_experience_months: Mapped[int] = mapped_column(Integer, nullable=False)
    service_area: Mapped[str | None] = mapped_column(String(500))
    service_windows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    mileage_policy: Mapped[str | None] = mapped_column(Text)
    driving_time_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    screening_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)


class AtsApplicationScreeningSnapshot(TimestampMixin, BasicBase):
    """Candidate-consented pathway and job-duty snapshot bound to an application."""

    __tablename__ = "ats_application_screening_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="CASCADE",
            name="fk_application_screening_snapshot_application",
        ),
        CheckConstraint(
            "pathway IN ('educator','student_educator','driver','educator_driver')",
            name="ck_application_screening_snapshot_pathway",
        ),
        CheckConstraint(
            "screening_profile_version > 0",
            name="ck_application_screening_snapshot_profile_version",
        ),
        CheckConstraint(
            "job_terms_version > 0",
            name="ck_application_screening_snapshot_job_terms_version",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    candidate_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    pathway: Mapped[str] = mapped_column(String(30), nullable=False)
    screening_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_terms_version: Mapped[int] = mapped_column(Integer, nullable=False)
    driver_declaration_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    job_terms_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AtsOfferScreeningTerms(TimestampMixin, BasicBase):
    """Exact structured duties and digest for one immutable offer version."""

    __tablename__ = "ats_offer_screening_terms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "offer_id"],
            ["ats_offers.organization_id", "ats_offers.id"],
            ondelete="CASCADE",
            name="fk_offer_screening_terms_offer",
        ),
        CheckConstraint(
            "position_shape IN ('educator_only','driver_only','educator_driver')",
            name="ck_offer_screening_terms_position_shape",
        ),
        CheckConstraint(
            "driving_requirement IN ('not_applicable','preferred','required')",
            name="ck_offer_screening_terms_driving_requirement",
        ),
        CheckConstraint(
            "vehicle_expectation IN ('none','organization_vehicle','personal_vehicle','either')",
            name="ck_offer_screening_terms_vehicle_expectation",
        ),
        CheckConstraint(
            "minimum_driving_experience_months >= 0",
            name="ck_offer_screening_terms_experience",
        ),
        CheckConstraint(
            "(position_shape = 'educator_only' AND driving_requirement = 'not_applicable' "
            "AND vehicle_expectation = 'none') OR "
            "(position_shape <> 'educator_only' AND driving_requirement <> 'not_applicable' "
            "AND vehicle_expectation <> 'none')",
            name="ck_offer_screening_terms_pair",
        ),
        CheckConstraint(
            "position_shape <> 'driver_only' OR driving_requirement = 'required'",
            name="ck_offer_screening_terms_driver_required",
        ),
        CheckConstraint(
            _lowercase_sha256_check("terms_digest"),
            name="ck_offer_screening_terms_digest",
        ),
        CheckConstraint("offer_version > 0", name="ck_offer_screening_terms_version"),
    )

    offer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    offer_version: Mapped[int] = mapped_column(Integer, nullable=False)
    position_shape: Mapped[str] = mapped_column(String(30), nullable=False)
    driving_requirement: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_expectation: Mapped[str] = mapped_column(String(30), nullable=False)
    required_licence_jurisdiction: Mapped[str | None] = mapped_column(String(20))
    required_licence_jurisdiction_other: Mapped[str | None] = mapped_column(String(100))
    required_licence_class: Mapped[str | None] = mapped_column(String(30))
    minimum_driving_experience_months: Mapped[int] = mapped_column(Integer, nullable=False)
    service_area: Mapped[str | None] = mapped_column(String(500))
    service_windows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    mileage_policy: Mapped[str | None] = mapped_column(Text)
    driving_time_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    screening_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    terms_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class MarketplaceScreeningProfile(TimestampMixin, BasicBase):
    """Candidate-declared pathway facts; never an operational readiness decision."""

    __tablename__ = "marketplace_screening_profiles"
    __table_args__ = (
        CheckConstraint(
            "pathway IN ('educator','student_educator','driver','educator_driver')",
            name="ck_marketplace_screening_profiles_pathway",
        ),
        CheckConstraint(
            "vehicle_access IN ('none','organization_vehicle_only','personal_vehicle','either')",
            name="ck_marketplace_screening_profiles_vehicle_access",
        ),
        CheckConstraint(
            "preferred_service_radius_km IS NULL OR "
            "(preferred_service_radius_km >= 0 AND preferred_service_radius_km <= 1000)",
            name="ck_marketplace_screening_profiles_radius",
        ),
        CheckConstraint(
            "candidate_provided = true",
            name="ck_marketplace_screening_profiles_candidate_provided",
        ),
        CheckConstraint(
            "(pathway IN ('driver','educator_driver') AND willing_to_drive = true AND (("
            "licence_jurisdiction IS NOT NULL AND licence_class IS NOT NULL "
            "AND vehicle_access <> 'none') OR (licence_jurisdiction IS NULL "
            "AND licence_jurisdiction_other IS NULL AND licence_class IS NULL "
            "AND vehicle_access = 'none' AND preferred_service_radius_km IS NULL))) OR "
            "(pathway IN ('educator','student_educator') AND willing_to_drive = false "
            "AND licence_jurisdiction IS NULL AND licence_jurisdiction_other IS NULL "
            "AND licence_class IS NULL AND vehicle_access = 'none' "
            "AND preferred_service_radius_km IS NULL)",
            name="ck_marketplace_screening_profiles_driver_declaration",
        ),
        CheckConstraint(
            "(licence_jurisdiction = 'OTHER' AND licence_jurisdiction_other IS NOT NULL) OR "
            "(licence_jurisdiction IS NULL AND licence_jurisdiction_other IS NULL) OR "
            "(licence_jurisdiction IS NOT NULL AND licence_jurisdiction <> 'OTHER' "
            "AND licence_jurisdiction_other IS NULL)",
            name="ck_marketplace_screening_profiles_jurisdiction_other",
        ),
        CheckConstraint("version > 0", name="ck_marketplace_screening_profiles_version"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    pathway: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    willing_to_drive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    licence_jurisdiction: Mapped[str | None] = mapped_column(String(20))
    licence_jurisdiction_other: Mapped[str | None] = mapped_column(String(100))
    licence_class: Mapped[str | None] = mapped_column(String(30))
    vehicle_access: Mapped[str] = mapped_column(String(30), default="none", nullable=False)
    preferred_service_radius_km: Mapped[int | None] = mapped_column(Integer)
    candidate_provided: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class StaffScreeningDocument(TimestampMixin, BasicBase):
    """A candidate-owned logical HR-vault document with immutable source versions."""

    __tablename__ = "staff_screening_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_staff_screening_documents_user_id"),
        CheckConstraint(
            "status IN ('uploaded','analysis_pending','candidate_review','confirmed',"
            "'expired','superseded','withdrawn')",
            name="ck_staff_screening_documents_status",
        ),
        CheckConstraint(
            "current_version_number > 0",
            name="ck_staff_screening_documents_current_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="candidate_review", nullable=False)
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class StaffScreeningDocumentVersion(BasicBase):
    """Encrypted original metadata. Storage references never cross the HTTP boundary."""

    __tablename__ = "staff_screening_document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["staff_screening_documents.user_id", "staff_screening_documents.id"],
            ondelete="CASCADE",
            name="fk_screening_versions_owner_document",
        ),
        UniqueConstraint("user_id", "id", name="uq_screening_versions_user_id"),
        UniqueConstraint(
            "document_id", "version_number", name="uq_screening_versions_document_version"
        ),
        CheckConstraint("version_number > 0", name="ck_screening_versions_version"),
        CheckConstraint("byte_size > 0", name="ck_screening_versions_size"),
        CheckConstraint(
            "media_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_screening_versions_media_type",
        ),
        CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_screening_versions_content_sha256",
        ),
        CheckConstraint(
            _lowercase_sha256_check("ciphertext_sha256"),
            name="ck_screening_versions_ciphertext_sha256",
        ),
        CheckConstraint(
            _opaque_storage_reference_check("storage_reference"),
            name="ck_screening_versions_storage_reference",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_coverage: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class StaffScreeningCandidateConfirmation(BasicBase):
    """Append-only candidate transcription bound to one immutable encrypted source version."""

    __tablename__ = "staff_screening_candidate_confirmations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "document_version_id"],
            ["staff_screening_document_versions.user_id", "staff_screening_document_versions.id"],
            ondelete="RESTRICT",
            name="fk_screening_confirmations_owner_version",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date",
            name="ck_screening_confirmations_date_order",
        ),
        CheckConstraint(
            "(subject_name_match = true AND mismatch_resolution = 'matched') OR "
            "(subject_name_match = false AND "
            "mismatch_resolution = 'candidate_attests_same_person')",
            name="ck_screening_confirmations_name_resolution",
        ),
    )

    document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_name_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mismatch_resolution: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    candidate_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class StaffScreeningApplicationShare(BasicBase):
    """Candidate consent to disclose one exact encrypted version to one application."""

    __tablename__ = "staff_screening_application_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["ats_applications.organization_id", "ats_applications.id"],
            ondelete="CASCADE",
            name="fk_screening_shares_application",
        ),
        ForeignKeyConstraint(
            ["candidate_user_id", "document_version_id"],
            ["staff_screening_document_versions.user_id", "staff_screening_document_versions.id"],
            ondelete="RESTRICT",
            name="fk_screening_shares_candidate_version",
        ),
        UniqueConstraint("organization_id", "id", name="uq_screening_shares_org_id"),
        UniqueConstraint(
            "organization_id",
            "application_id",
            "id",
            name="uq_screening_shares_org_application_id",
        ),
        Index(
            "uq_screening_shares_active_version",
            "candidate_user_id",
            "application_id",
            "document_version_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL"),
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= shared_at",
            name="ck_screening_shares_revoked_order",
        ),
        CheckConstraint(
            "screening_profile_version > 0", name="ck_screening_shares_profile_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    screening_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffScreeningEmployerReview(BasicBase):
    """Append-only employer decision for one claimed coverage class."""

    __tablename__ = "staff_screening_employer_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "application_id", "share_id"],
            [
                "staff_screening_application_shares.organization_id",
                "staff_screening_application_shares.application_id",
                "staff_screening_application_shares.id",
            ],
            ondelete="RESTRICT",
            name="fk_screening_reviews_application_share",
        ),
        UniqueConstraint(
            "share_id",
            "requirement_class",
            "review_sequence",
            name="uq_screening_reviews_sequence",
        ),
        CheckConstraint(
            "requirement_class IN ('criminal_record_check','vulnerable_sector_search')",
            name="ck_screening_reviews_requirement",
        ),
        CheckConstraint(
            "decision IN ('accepted','rejected')", name="ck_screening_reviews_decision"
        ),
        CheckConstraint("review_sequence > 0", name="ck_screening_reviews_sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    share_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    requirement_class: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    reviewer_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    review_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AtsOfferAcknowledgment(BasicBase):
    """Candidate acceptance bound to the immutable version and digest they saw."""

    __tablename__ = "ats_offer_acknowledgments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "offer_id"],
            ["ats_offers.organization_id", "ats_offers.id"],
            ondelete="RESTRICT",
            name="fk_offer_acknowledgments_offer",
        ),
        UniqueConstraint("organization_id", "offer_id", name="uq_offer_acknowledgments_offer"),
        CheckConstraint("offer_version > 0", name="ck_offer_acknowledgments_version"),
        CheckConstraint(
            _lowercase_sha256_check("terms_digest"),
            name="ck_offer_acknowledgments_terms_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    offer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    candidate_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    offer_version: Mapped[int] = mapped_column(Integer, nullable=False)
    terms_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    driver_terms_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class UserNotification(BasicBase):
    """Server-authored, user-owned notification ledger across tenant contexts."""

    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_user_notifications_event"),
        CheckConstraint(
            "category IN ('hiring','credential','assignment','operations','system')",
            name="ck_user_notifications_category",
        ),
        CheckConstraint(
            "severity IN ('info','success','warning','critical')",
            name="ck_user_notifications_severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_path: Mapped[str | None] = mapped_column(String(500))
    action_entity_type: Mapped[str | None] = mapped_column(String(60))
    action_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class UserNotificationPreference(TimestampMixin, BasicBase):
    """Fixed server-validated notification switches; no arbitrary preference blob."""

    __tablename__ = "user_notification_preferences"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    hiring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credential_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assignment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    operations_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )


class PushSubscription(TimestampMixin, BasicBase):
    """User-owned native/browser delivery address; never serialized back to clients."""

    __tablename__ = "notification_push_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_push_subscriptions_user_device"),
        Index(
            "uq_push_subscriptions_active_address",
            "transport",
            "address_digest",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        CheckConstraint("transport IN ('expo','web_push')", name="ck_push_subscriptions_transport"),
        CheckConstraint(
            "platform IN ('android','ios','web')", name="ck_push_subscriptions_platform"
        ),
        CheckConstraint(
            "status IN ('active','revoked','invalid')", name="ck_push_subscriptions_status"
        ),
        CheckConstraint(
            "(status = 'active' AND delivery_address IS NOT NULL) OR "
            "(status <> 'active' AND delivery_address IS NULL)",
            name="ck_push_subscriptions_active_address",
        ),
        CheckConstraint(
            "(transport = 'expo' AND web_push_public_key IS NULL "
            "AND web_push_auth_secret IS NULL) OR "
            "(transport = 'web_push' AND web_push_public_key IS NOT NULL "
            "AND web_push_auth_secret IS NOT NULL)",
            name="ck_push_subscriptions_transport_keys",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_address: Mapped[str | None] = mapped_column(Text)
    address_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    web_push_public_key: Mapped[str | None] = mapped_column(Text)
    web_push_auth_secret: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(TimestampMixin, BasicBase):
    """Retry-safe, PII-free push delivery outbox owned by one notification recipient."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "subscription_id", name="uq_notification_deliveries_target"
        ),
        CheckConstraint(
            "status IN ('pending','processing','retry','receipt_pending','sent','dead',"
            "'cancelled','suppressed')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempts"),
        CheckConstraint(
            "receipt_attempt_count >= 0",
            name="ck_notification_deliveries_receipt_attempts",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_push_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    receipt_attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class UserRealtimeEvent(BasicBase):
    """User-private invalidation stream for inbox and delivery state changes."""

    __tablename__ = "user_realtime_events"
    __table_args__ = (
        CheckConstraint("length(trim(event_type)) > 0", name="ck_user_realtime_events_type"),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, default=uuid4, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class UserRealtimeTicket(BasicBase):
    """Single-use ticket for the user-private notification WebSocket."""

    __tablename__ = "user_realtime_tickets"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_user_realtime_tickets_digest"),
        CheckConstraint("expires_at > created_at", name="ck_user_realtime_tickets_expiry"),
        CheckConstraint("auth_version > 0", name="ck_user_realtime_tickets_auth_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyAuthorityPerson(TimestampMixin, BasicBase):
    """Stable family-scoped authority identity with exact current-fact provenance."""

    __tablename__ = "family_authority_people"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="RESTRICT",
            name="fk_authority_people_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "source_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            ondelete="RESTRICT",
            name="fk_authority_people_guardian",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "source_emergency_contact_id"],
            [
                "emergency_contacts.organization_id",
                "emergency_contacts.family_id",
                "emergency_contacts.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_people_contact",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_people_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "last_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_people_last_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "retired_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_people_retired_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "id", "current_person_version_id"],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
            name="fk_authority_people_current_version",
        ),
        UniqueConstraint("organization_id", "id", name="uq_authority_people_org_id"),
        UniqueConstraint(
            "organization_id", "family_id", "id", name="uq_authority_people_org_family_id"
        ),
        Index(
            "ix_authority_people_family_status",
            "organization_id",
            "family_id",
            "status",
        ),
        Index(
            "uq_authority_people_source_guardian",
            "organization_id",
            "family_id",
            "source_guardian_id",
            unique=True,
            postgresql_where=text("source_guardian_id IS NOT NULL"),
            sqlite_where=text("source_guardian_id IS NOT NULL"),
        ),
        Index(
            "uq_authority_people_source_contact",
            "organization_id",
            "family_id",
            "source_emergency_contact_id",
            unique=True,
            postgresql_where=text("source_emergency_contact_id IS NOT NULL"),
            sqlite_where=text("source_emergency_contact_id IS NOT NULL"),
        ),
        CheckConstraint("version > 0", name="ck_authority_people_version"),
        CheckConstraint("status IN ('active','retired')", name="ck_authority_people_status"),
        CheckConstraint(
            "source_guardian_id IS NULL OR source_emergency_contact_id IS NULL",
            name="ck_authority_people_one_source",
        ),
        CheckConstraint(
            "(status = 'active' AND current_person_version_id IS NOT NULL "
            "AND retired_at IS NULL AND retired_operation_id IS NULL) OR "
            "(status = 'retired' AND current_person_version_id IS NULL "
            "AND retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
            name="ck_authority_people_lifecycle",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )
    current_person_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    source_guardian_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    source_emergency_contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class FamilyAuthorityPersonVersion(BasicBase):
    """Append-only person facts with a one-way close transition."""

    __tablename__ = "family_authority_person_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_person_versions_person",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_person_versions_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "closed_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_person_versions_closed_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_authority_person_versions_org_id"),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "person_id",
            "id",
            name="uq_authority_person_versions_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "person_id",
            "version_number",
            name="uq_authority_person_versions_number",
        ),
        UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_person_versions_created_operation",
        ),
        Index(
            "uq_authority_person_versions_open",
            "organization_id",
            "family_id",
            "person_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
            sqlite_where=text("closed_at IS NULL"),
        ),
        CheckConstraint("version_number > 0", name="ck_authority_person_versions_number"),
        CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="ck_authority_person_versions_names",
        ),
        CheckConstraint(
            "(middle_name IS NULL OR length(trim(middle_name)) > 0) AND "
            "(preferred_name IS NULL OR length(trim(preferred_name)) > 0) AND "
            "(email IS NULL OR length(trim(email)) > 0) AND "
            "(primary_phone IS NULL OR length(trim(primary_phone)) > 0)",
            name="ck_authority_person_versions_optional_facts",
        ),
        CheckConstraint(
            "relationship_kind IN ('parent','legal_guardian','foster_parent','grandparent',"
            "'adult_sibling','aunt_uncle','family_friend','caseworker',"
            "'transport_provider','other')",
            name="ck_authority_person_versions_relationship",
        ),
        CheckConstraint(
            "(relationship_kind = 'other' AND relationship_detail IS NOT NULL "
            "AND length(trim(relationship_detail)) > 0) OR "
            "(relationship_kind <> 'other' AND relationship_detail IS NULL)",
            name="ck_authority_person_versions_relationship_detail",
        ),
        CheckConstraint(
            "(closed_at IS NULL AND closed_operation_id IS NULL) OR "
            "(closed_at IS NOT NULL AND closed_operation_id IS NOT NULL)",
            name="ck_authority_person_versions_closure",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    relationship_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    relationship_detail: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    primary_phone: Mapped[str | None] = mapped_column(String(30))
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class FamilyAuthorityEvidenceObject(BasicBase):
    """Exact private upload metadata with a one-way quarantine lifecycle."""

    __tablename__ = "family_authority_evidence_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="RESTRICT",
            name="fk_authority_evidence_objects_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_authority_evidence_objects_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "uploaded_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_objects_upload_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_authority_evidence_objects_org_id"),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "id",
            name="uq_authority_evidence_objects_org_family_id",
        ),
        UniqueConstraint(
            "organization_id",
            "uploaded_operation_id",
            name="uq_authority_evidence_objects_upload_op",
        ),
        UniqueConstraint(
            "organization_id",
            "storage_reference",
            name="uq_authority_evidence_objects_reference",
        ),
        Index(
            "ix_authority_evidence_objects_family_status",
            "organization_id",
            "family_id",
            "status",
        ),
        CheckConstraint(
            "evidence_kind IN ('identity_document','custody_document','court_order',"
            "'signed_consent','signed_release_delegation','other_document')",
            name="ck_authority_evidence_objects_kind",
        ),
        CheckConstraint("object_version = 1", name="ck_authority_evidence_objects_version"),
        CheckConstraint(
            "status IN ('quarantined','clean','rejected')",
            name="ck_authority_evidence_objects_status",
        ),
        CheckConstraint(
            "storage_reference IS NULL OR (length(storage_reference) BETWEEN 1 AND 500 "
            "AND substr(storage_reference,1,1) NOT IN ('/','.') "
            "AND storage_reference NOT LIKE '%//%' "
            "AND storage_reference NOT IN ('.','..') "
            "AND storage_reference NOT LIKE './%' "
            "AND storage_reference NOT LIKE '../%' "
            "AND storage_reference NOT LIKE '%/./%' "
            "AND storage_reference NOT LIKE '%/../%' "
            "AND storage_reference NOT LIKE '%/.' "
            "AND storage_reference NOT LIKE '%/..' "
            "AND storage_reference NOT LIKE '%/')",
            name="ck_authority_evidence_objects_reference",
        ),
        CheckConstraint(
            "media_type IN ('application/pdf','image/jpeg','image/png')",
            name="ck_authority_evidence_objects_media_type",
        ),
        CheckConstraint(
            "byte_size BETWEEN 1 AND 52428800",
            name="ck_authority_evidence_objects_byte_size",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256) "
            "AND content_sha256 NOT LIKE '% %'",
            name="ck_authority_evidence_objects_sha256",
        ),
        CheckConstraint(
            "original_filename IS NULL OR "
            "length(trim(original_filename)) BETWEEN 1 AND 255",
            name="ck_authority_evidence_objects_filename",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    evidence_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    object_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), default="quarantined", server_default="quarantined", nullable=False
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class FamilyAuthorityEvidenceObjectAssessment(BasicBase):
    """Append-only upload quarantine and terminal scanner decisions."""

    __tablename__ = "family_authority_evidence_object_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_object_id"],
            [
                "family_authority_evidence_objects.organization_id",
                "family_authority_evidence_objects.family_id",
                "family_authority_evidence_objects.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_object_assessments_object",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_authority_object_assessments_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_object_assessments_operation",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_authority_object_assessments_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "evidence_object_id",
            "id",
            name="uq_authority_object_assessments_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "evidence_object_id",
            "version_number",
            name="uq_authority_object_assessments_version",
        ),
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_authority_object_assessments_operation",
        ),
        Index(
            "ix_authority_object_assessments_current",
            "organization_id",
            "evidence_object_id",
            "version_number",
        ),
        CheckConstraint(
            "(version_number = 1 AND decision = 'quarantined' "
            "AND scanner_engine IS NULL AND scanner_version IS NULL "
            "AND scanner_signature IS NULL AND reason_code IS NULL) OR "
            "(version_number = 2 AND decision = 'clean' "
            "AND scanner_engine IS NOT NULL AND length(trim(scanner_engine)) > 0 "
            "AND scanner_version IS NOT NULL AND length(trim(scanner_version)) > 0 "
            "AND scanner_signature IS NULL "
            "AND reason_code IS NULL) OR "
            "(version_number = 2 AND decision = 'rejected' "
            "AND scanner_engine IS NOT NULL AND length(trim(scanner_engine)) > 0 "
            "AND scanner_version IS NOT NULL AND length(trim(scanner_version)) > 0 "
            "AND (scanner_signature IS NULL OR length(trim(scanner_signature)) > 0) "
            "AND reason_code IN ('malware_detected','invalid_document'))",
            name="ck_authority_object_assessments_transition",
        ),
        CheckConstraint(
            "decision IN ('quarantined','clean','rejected')",
            name="ck_authority_object_assessments_decision",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    evidence_object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    scanner_engine: Mapped[str | None] = mapped_column(String(80))
    scanner_version: Mapped[str | None] = mapped_column(String(160))
    scanner_signature: Mapped[str | None] = mapped_column(String(160))
    reason_code: Mapped[str | None] = mapped_column(String(80))
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class FamilyAuthorityEvidence(BasicBase):
    """Immutable private evidence asset with no review state or public URL."""

    __tablename__ = "family_authority_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="RESTRICT",
            name="fk_authority_evidence_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "recorded_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_recorder_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_object_id"],
            [
                "family_authority_evidence_objects.organization_id",
                "family_authority_evidence_objects.family_id",
                "family_authority_evidence_objects.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_object",
        ),
        UniqueConstraint("organization_id", "id", name="uq_authority_evidence_org_id"),
        UniqueConstraint(
            "organization_id", "family_id", "id", name="uq_authority_evidence_org_family_id"
        ),
        UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_evidence_created_operation",
        ),
        Index(
            "uq_authority_evidence_object",
            "organization_id",
            "evidence_object_id",
            unique=True,
            postgresql_where=text("evidence_object_id IS NOT NULL"),
            sqlite_where=text("evidence_object_id IS NOT NULL"),
        ),
        CheckConstraint(
            "evidence_kind IN ('identity_document','custody_document','court_order',"
            "'guardian_attestation','signed_consent','signed_release_delegation',"
            "'staff_witness','other_document')",
            name="ck_authority_evidence_kind",
        ),
        CheckConstraint(
            "length(trim(source_label)) > 0", name="ck_authority_evidence_source_label"
        ),
        CheckConstraint(
            "(storage_reference IS NULL AND media_type IS NULL AND byte_size IS NULL "
            "AND content_sha256 IS NULL) OR "
            "(storage_reference IS NOT NULL AND media_type IS NOT NULL "
            "AND byte_size IS NOT NULL AND byte_size > 0 AND content_sha256 IS NOT NULL)",
            name="ck_authority_evidence_storage_tuple",
        ),
        CheckConstraint(
            "storage_reference IS NULL OR (length(storage_reference) BETWEEN 1 AND 500 "
            "AND substr(storage_reference,1,1) NOT IN ('/','.') "
            "AND storage_reference NOT LIKE '%//%' "
            "AND storage_reference NOT IN ('.','..') "
            "AND storage_reference NOT LIKE './%' "
            "AND storage_reference NOT LIKE '../%' "
            "AND storage_reference NOT LIKE '%/./%' "
            "AND storage_reference NOT LIKE '%/../%' "
            "AND storage_reference NOT LIKE '%/.' "
            "AND storage_reference NOT LIKE '%/..' "
            "AND storage_reference NOT LIKE '%/')",
            name="ck_authority_evidence_storage_reference",
        ),
        CheckConstraint(
            "media_type IS NULL OR "
            "media_type IN ('application/pdf','image/jpeg','image/png')",
            name="ck_authority_evidence_media_type",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size BETWEEN 1 AND 52428800",
            name="ck_authority_evidence_byte_size",
        ),
        CheckConstraint(
            "content_sha256 IS NULL OR (length(content_sha256) = 64 "
            "AND content_sha256 = lower(content_sha256) "
            "AND content_sha256 NOT LIKE '% %')",
            name="ck_authority_evidence_sha256",
        ),
        CheckConstraint(
            "issued_at IS NULL OR expires_at IS NULL OR expires_at > issued_at",
            name="ck_authority_evidence_expiry",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    evidence_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_label: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_reference: Mapped[str | None] = mapped_column(String(500))
    media_type: Mapped[str | None] = mapped_column(String(100))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    content_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    evidence_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    recorded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class FamilyAuthorityEvidenceAssessment(BasicBase):
    """Immutable human assessment in an evidence asset's bounded state machine."""

    __tablename__ = "family_authority_evidence_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_assessments_evidence",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "superseded_by_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_assessments_superseding_evidence",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_authority_evidence_assessments_actor_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_authority_evidence_assessments_created_op",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_authority_evidence_assessments_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "evidence_id",
            "id",
            name="uq_authority_evidence_assessments_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "evidence_id",
            "version_number",
            name="uq_authority_evidence_assessments_version",
        ),
        UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_evidence_assessments_created_operation",
        ),
        Index(
            "ix_authority_evidence_assessments_current",
            "organization_id",
            "evidence_id",
            "version_number",
        ),
        CheckConstraint(
            "(version_number = 2 AND decision IN ('reviewed','rejected')) OR "
            "(version_number = 3 AND decision IN ('invalidated','superseded'))",
            name="ck_authority_evidence_assessments_transition",
        ),
        CheckConstraint(
            "decision IN ('reviewed','rejected','invalidated','superseded')",
            name="ck_authority_evidence_assessments_decision",
        ),
        CheckConstraint(
            "(decision = 'reviewed' AND assessed_epistemic_status IS NOT NULL AND "
            "assessed_epistemic_status IN "
            "('reported','document_observed') AND reason_code IS NULL) OR "
            "(decision = 'rejected' AND assessed_epistemic_status IS NULL AND "
            "reason_code IS NOT NULL AND reason_code IN "
            "('insufficient_evidence','information_mismatch','unreadable',"
            "'unsupported','entered_in_error','other')) OR "
            "(decision = 'invalidated' AND assessed_epistemic_status IS NULL AND "
            "reason_code IS NOT NULL AND reason_code IN "
            "('authority_changed','document_revoked',"
            "'information_corrected','entered_in_error','other')) OR "
            "(decision = 'superseded' AND assessed_epistemic_status IS NULL "
            "AND reason_code = 'superseded')",
            name="ck_authority_evidence_assessments_outcome",
        ),
        CheckConstraint(
            "(reason_code = 'other' AND confidential_note IS NOT NULL AND "
            "length(trim(confidential_note)) BETWEEN 1 AND 1000) OR "
            "((reason_code IS NULL OR reason_code <> 'other') AND confidential_note IS NULL)",
            name="ck_authority_evidence_assessments_note",
        ),
        CheckConstraint(
            "(decision = 'superseded' AND superseded_by_evidence_id IS NOT NULL AND "
            "superseded_by_evidence_id <> evidence_id) OR "
            "(decision <> 'superseded' AND superseded_by_evidence_id IS NULL)",
            name="ck_authority_evidence_assessments_supersession",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    assessed_epistemic_status: Mapped[str | None] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(32))
    confidential_note: Mapped[str | None] = mapped_column(Text)
    superseded_by_evidence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildAuthorityHead(TimestampMixin, BasicBase):
    """Monotonic authority revision; absence projects as unreviewed revision zero."""

    __tablename__ = "child_authority_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_child_authority_heads_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_child_authority_heads_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "last_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_child_authority_heads_last_op",
        ),
        UniqueConstraint("organization_id", "child_id", name="uq_child_authority_heads_org_child"),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "child_id",
            name="uq_child_authority_heads_org_family_child",
        ),
        CheckConstraint("revision > 0", name="ck_child_authority_heads_revision"),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    last_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ChildReleaseAuthorization(TimestampMixin, BasicBase):
    """Finite, reviewed positive grant for one child and recipient."""

    __tablename__ = "child_release_authorizations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_release_authorizations_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "recipient_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_recipient",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "grantor_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_grantor",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "grantor_person_id", "grantor_person_version_id"],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_grantor_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "basis_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_evidence",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "basis_evidence_id",
                "basis_evidence_assessment_id",
            ],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_evidence_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "revoked_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_authorizations_revoked_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_release_authorizations_org_id"),
        UniqueConstraint(
            "organization_id",
            "family_id",
            "child_id",
            "recipient_person_id",
            "id",
            name="uq_release_authorizations_snapshot_identity",
        ),
        Index(
            "ix_release_authorizations_lane",
            "organization_id",
            "child_id",
            "recipient_person_id",
            "effective_from",
            "effective_until",
        ),
        CheckConstraint(
            "verification_policy_code IN ('government_photo_id','documented_familiarity',"
            "'government_photo_id_or_documented_familiarity',"
            "'government_photo_id_and_secondary_check')",
            name="ck_release_authorizations_verification_policy",
        ),
        CheckConstraint(
            "grantor_authority_basis IN ('guardian_record','reviewed_custody_evidence',"
            "'reviewed_delegation_evidence')",
            name="ck_release_authorizations_grantor_basis",
        ),
        CheckConstraint(
            "effective_until > effective_from",
            name="ck_release_authorizations_window",
        ),
        CheckConstraint("version > 0", name="ck_release_authorizations_version"),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_operation_id IS NULL "
            "AND revocation_reason_code IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_operation_id IS NOT NULL "
            "AND revocation_reason_code IS NOT NULL "
            "AND revocation_reason_code IN ('authority_withdrawn','safety_change',"
            "'superseded','entered_in_error'))",
            name="ck_release_authorizations_revocation",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    recipient_person_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    verification_policy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    grantor_person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grantor_person_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grantor_authority_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    basis_evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    basis_evidence_assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    revocation_reason_code: Mapped[str | None] = mapped_column(String(32))


class ChildReleaseRule(TimestampMixin, BasicBase):
    """Finite release restriction that composes independently from positive grants."""

    __tablename__ = "child_release_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_release_rules_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "scope_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_scope_person",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "directing_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_directing_person",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "directing_person_id",
                "directing_person_version_id",
            ],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_directing_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "basis_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_evidence",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "basis_evidence_id",
                "basis_evidence_assessment_id",
            ],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_evidence_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "revoked_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_rules_revoked_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_release_rules_org_id"),
        Index(
            "ix_release_rules_lane",
            "organization_id",
            "child_id",
            "rule_kind",
            "scope_kind",
            "scope_person_id",
            "effective_from",
            "effective_until",
        ),
        CheckConstraint(
            "rule_kind IN ('deny','manager_review')",
            name="ck_release_rules_kind",
        ),
        CheckConstraint(
            "scope_kind IN ('all_recipients','specific_person')",
            name="ck_release_rules_scope_kind",
        ),
        CheckConstraint(
            "(scope_kind = 'all_recipients' AND scope_person_id IS NULL) OR "
            "(scope_kind = 'specific_person' AND scope_person_id IS NOT NULL)",
            name="ck_release_rules_scope_shape",
        ),
        CheckConstraint(
            "rule_kind <> 'named_recipient_only' OR scope_kind = 'specific_person'",
            name="ck_release_rules_named_scope",
        ),
        CheckConstraint(
            "(directing_person_id IS NULL AND directing_person_version_id IS NULL) OR "
            "(directing_person_id IS NOT NULL AND directing_person_version_id IS NOT NULL)",
            name="ck_release_rules_directing_pair",
        ),
        CheckConstraint(
            "authority_basis_code IN ('guardian_record','reviewed_custody_evidence')",
            name="ck_release_rules_authority_basis",
        ),
        CheckConstraint(
            "(rule_kind = 'deny' AND safe_explanation_code = 'release_restricted') OR "
            "(rule_kind = 'supervised_only' AND safe_explanation_code = "
            "'supervision_required') OR "
            "(rule_kind = 'named_recipient_only' AND safe_explanation_code = "
            "'named_recipient_only') OR "
            "(rule_kind = 'manager_review' AND safe_explanation_code = "
            "'manager_review_required')",
            name="ck_release_rules_safe_code",
        ),
        CheckConstraint("length(trim(confidential_reason)) > 0", name="ck_release_rules_reason"),
        CheckConstraint("effective_until > effective_from", name="ck_release_rules_window"),
        CheckConstraint("version > 0", name="ck_release_rules_version"),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_operation_id IS NULL "
            "AND revocation_reason_code IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_operation_id IS NOT NULL "
            "AND revocation_reason_code IS NOT NULL "
            "AND revocation_reason_code IN ('authority_withdrawn','safety_change',"
            "'superseded','entered_in_error'))",
            name="ck_release_rules_revocation",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    rule_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_person_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    directing_person_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    directing_person_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    authority_basis_code: Mapped[str] = mapped_column(String(40), nullable=False)
    basis_evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    basis_evidence_assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    safe_explanation_code: Mapped[str] = mapped_column(String(40), nullable=False)
    confidential_reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    revocation_reason_code: Mapped[str | None] = mapped_column(String(32))


class ConsentPolicyVersion(BasicBase):
    """Immutable, finite policy language for one bounded consent purpose."""

    __tablename__ = "consent_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_consent_policy_versions_created_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_consent_policy_versions_org_id"),
        UniqueConstraint(
            "organization_id",
            "purpose_code",
            "id",
            name="uq_consent_policy_versions_purpose_id",
        ),
        UniqueConstraint(
            "organization_id",
            "purpose_code",
            "version_number",
            name="uq_consent_policy_versions_number",
        ),
        Index(
            "ix_consent_policy_versions_lane",
            "organization_id",
            "purpose_code",
            "effective_from",
            "effective_until",
        ),
        CheckConstraint(
            "purpose_code IN ('off_site_activity','emergency_health_care',"
            "'medication_administration','internal_media','external_media','marketing',"
            "'research','optional_service','information_sharing')",
            name="ck_consent_policy_versions_purpose",
        ),
        CheckConstraint(
            "version_number BETWEEN 1 AND 2147483647",
            name="ck_consent_policy_versions_number",
        ),
        CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(content_reference)) > 0 "
            "AND length(content_text) BETWEEN 1 AND 20000 "
            "AND length(trim(content_text)) > 0",
            name="ck_consent_policy_versions_content",
        ),
        CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_consent_policy_versions_sha256",
        ),
        CheckConstraint(
            "signer_authority_requirement IN ('guardian_record','legal_decision_maker')",
            name="ck_consent_policy_versions_signer",
        ),
        CheckConstraint(
            "effective_until > effective_from", name="ck_consent_policy_versions_window"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    purpose_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    signer_authority_requirement: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ChildConsentDecision(TimestampMixin, BasicBase):
    """Reviewed consent decision bound to an exact policy and signer fact version."""

    __tablename__ = "child_consent_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "purpose_code", "policy_version_id"],
            [
                "consent_policy_versions.organization_id",
                "consent_policy_versions.purpose_code",
                "consent_policy_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_policy",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "signer_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_signer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "signer_person_id", "signer_person_version_id"],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_signer_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_evidence",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "evidence_id",
                "evidence_assessment_id",
            ],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_evidence_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "signer_authority_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_signer_authority_evidence",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "signer_authority_evidence_id",
                "signer_authority_evidence_assessment_id",
            ],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_signer_authority_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "scope_facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_created_op",
        ),
        ForeignKeyConstraint(
            ["organization_id", "withdrawn_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_child_consent_decisions_withdrawn_op",
        ),
        UniqueConstraint("organization_id", "id", name="uq_child_consent_decisions_org_id"),
        Index(
            "ix_child_consent_decisions_lane",
            "organization_id",
            "child_id",
            "purpose_code",
            "effective_from",
            "effective_until",
        ),
        CheckConstraint(
            "purpose_code IN ('off_site_activity','emergency_health_care',"
            "'medication_administration','internal_media','external_media','marketing',"
            "'research','optional_service','information_sharing')",
            name="ck_child_consent_decisions_purpose",
        ),
        CheckConstraint(
            "signer_authority_basis IN ('guardian_record','reviewed_custody_evidence')",
            name="ck_child_consent_decisions_signer_basis",
        ),
        CheckConstraint(
            "evidence_id <> signer_authority_evidence_id",
            name="ck_child_consent_decisions_distinct_evidence",
        ),
        CheckConstraint(
            "decision IN ('granted','declined')", name="ck_child_consent_decisions_decision"
        ),
        CheckConstraint(
            "scope_kind IN ('policy','facility','named_activity')",
            name="ck_child_consent_decisions_scope_kind",
        ),
        CheckConstraint(
            "(scope_kind = 'policy' AND scope_facility_id IS NULL "
            "AND scope_reference IS NULL) OR "
            "(scope_kind = 'facility' AND scope_facility_id IS NOT NULL "
            "AND scope_reference IS NULL) OR "
            "(scope_kind = 'named_activity' AND scope_facility_id IS NULL "
            "AND scope_reference IS NOT NULL AND length(trim(scope_reference)) > 0)",
            name="ck_child_consent_decisions_scope_shape",
        ),
        CheckConstraint(
            "effective_until > effective_from", name="ck_child_consent_decisions_window"
        ),
        CheckConstraint("version > 0", name="ck_child_consent_decisions_version"),
        CheckConstraint(
            "(withdrawn_at IS NULL AND withdrawn_operation_id IS NULL "
            "AND withdrawal_reason_code IS NULL) OR "
            "(withdrawn_at IS NOT NULL AND withdrawn_operation_id IS NOT NULL "
            "AND withdrawal_reason_code IS NOT NULL "
            "AND withdrawal_reason_code IN ('signer_withdrew','authority_changed',"
            "'superseded','entered_in_error'))",
            name="ck_child_consent_decisions_withdrawal",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    purpose_code: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signer_person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signer_person_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signer_authority_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signer_authority_evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    signer_authority_evidence_assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_facility_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    scope_reference: Mapped[str | None] = mapped_column(String(160))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    withdrawn_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    withdrawal_reason_code: Mapped[str | None] = mapped_column(String(32))


class FacilityReleaseCheckoutActivation(BasicBase):
    """Immutable per-facility decision to enable normal verified release."""

    __tablename__ = "facility_release_checkout_activations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_release_checkout_activations_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "activated_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_release_checkout_activations_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "activated_by_role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="RESTRICT",
            name="fk_release_checkout_activations_role",
        ),
        ForeignKeyConstraint(
            ["organization_id", "activation_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_checkout_activations_operation",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_release_checkout_activations_org_id"
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            name="uq_release_checkout_activations_facility",
        ),
        UniqueConstraint(
            "organization_id",
            "activation_operation_id",
            name="uq_release_checkout_activations_operation",
        ),
        CheckConstraint(
            "activated_by_role_key IN ('owner','administrator')",
            name="ck_release_checkout_activations_privileged_role",
        ),
        CheckConstraint(
            "activation_policy_version = 'normal_verified_release_v1'",
            name="ck_release_checkout_activations_policy_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    activated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    activated_by_membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activated_by_role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activated_by_role_key: Mapped[str] = mapped_column(String(50), nullable=False)
    activation_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activation_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AttendanceReleaseSnapshot(BasicBase):
    """Immutable facts committed with one normal verified release checkout."""

    __tablename__ = "attendance_release_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_facility",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "child_id", "attendance_day_id"],
            [
                "attendance_days.organization_id",
                "attendance_days.facility_id",
                "attendance_days.child_id",
                "attendance_days.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_day_identity",
        ),
        ForeignKeyConstraint(
            ["organization_id", "attendance_day_id", "attendance_interval_id"],
            [
                "attendance_intervals.organization_id",
                "attendance_intervals.attendance_day_id",
                "attendance_intervals.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_interval_identity",
        ),
        ForeignKeyConstraint(
            ["organization_id", "attendance_day_id", "checkout_event_id"],
            [
                "attendance_events.organization_id",
                "attendance_events.attendance_day_id",
                "attendance_events.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_event_identity",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "recipient_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_recipient",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id", "evidence_assessment_id"],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_evidence_assessment",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "recipient_person_id",
                "recipient_person_version_id",
            ],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_recipient_version",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "child_id",
                "recipient_person_id",
                "authorization_id",
            ],
            [
                "child_release_authorizations.organization_id",
                "child_release_authorizations.family_id",
                "child_release_authorizations.child_id",
                "child_release_authorizations.recipient_person_id",
                "child_release_authorizations.id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_authorization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "client_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_release_snapshots_operation",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_actor_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_actor_membership_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_actor_role",
        ),
        ForeignKeyConstraint(
            ["organization_id", "staff_shift_id"],
            ["staff_shifts.organization_id", "staff_shifts.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_staff_shift",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_room",
        ),
        ForeignKeyConstraint(
            ["organization_id", "room_assignment_id"],
            ["membership_room_assignments.organization_id", "membership_room_assignments.id"],
            ondelete="RESTRICT",
            name="fk_release_snapshots_room_assignment",
        ),
        UniqueConstraint("organization_id", "id", name="uq_release_snapshots_org_id"),
        UniqueConstraint(
            "organization_id", "attendance_interval_id", name="uq_release_snapshots_interval"
        ),
        UniqueConstraint("organization_id", "checkout_event_id", name="uq_release_snapshots_event"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_release_snapshots_operation"
        ),
        CheckConstraint(
            "authorization_version > 0 AND authority_revision > 0 "
            "AND evidence_assessment_version = 2",
            name="ck_release_snapshots_versions",
        ),
        CheckConstraint(
            "attendance_day_version >= 1",
            name="ck_release_snapshots_attendance_day_version",
        ),
        CheckConstraint(
            " AND ".join(
                _lowercase_sha256_check(column_name)
                for column_name in (
                    "restriction_digest_sha256",
                    "evidence_digest_sha256",
                    "request_hash",
                )
            ),
            name="ck_release_snapshots_hashes",
        ),
        CheckConstraint(
            "verification_method IN ('government_photo_id','documented_familiarity',"
            "'government_photo_id_and_secondary_check')",
            name="ck_release_snapshots_verification_method",
        ),
        CheckConstraint(
            "verification_result IN ('verified','documented_familiarity')",
            name="ck_release_snapshots_verification_result",
        ),
        CheckConstraint("committed_at >= requested_at", name="ck_release_snapshots_time_order"),
        CheckConstraint(
            "release_mode = 'normal' AND override_reason_code IS NULL "
            "AND override_justification IS NULL",
            name="ck_release_snapshots_normal_only",
        ),
        CheckConstraint(
            "scope_basis IN ('organization_role','room_assignment') AND "
            "((scope_basis = 'organization_role' AND room_assignment_id IS NULL) OR "
            "(scope_basis = 'room_assignment' AND room_assignment_id IS NOT NULL))",
            name="ck_release_snapshots_scope_basis",
        ),
        CheckConstraint(
            "(verification_policy_code = 'government_photo_id' "
            "AND verification_method = 'government_photo_id' "
            "AND verification_result = 'verified') OR "
            "(verification_policy_code = 'documented_familiarity' "
            "AND verification_method = 'documented_familiarity' "
            "AND verification_result = 'documented_familiarity') OR "
            "(verification_policy_code = 'government_photo_id_or_documented_familiarity' "
            "AND ((verification_method = 'government_photo_id' "
            "AND verification_result = 'verified') OR "
            "(verification_method = 'documented_familiarity' "
            "AND verification_result = 'documented_familiarity')))",
            name="ck_release_snapshots_executable_verification_policy",
        ),
        CheckConstraint(
            "checked_out_at >= requested_at AND committed_at = checked_out_at",
            name="ck_release_snapshots_checkout_time_order",
        ),
        CheckConstraint(
            "decision_policy_version = 'release-context-v1'",
            name="ck_release_snapshots_decision_policy_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    attendance_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attendance_day_version: Mapped[int] = mapped_column(Integer, nullable=False)
    attendance_interval_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    checkout_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recipient_person_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recipient_person_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recipient_display_name: Mapped[str] = mapped_column(String(302), nullable=False)
    recipient_relationship: Mapped[str] = mapped_column(String(120), nullable=False)
    authorization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authorization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_assessment_version: Mapped[int] = mapped_column(Integer, nullable=False)
    authority_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    restriction_digest_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_result: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_policy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    decision_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_role_key: Mapped[str] = mapped_column(String(50), nullable=False)
    staff_shift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scope_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    room_assignment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    release_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    override_reason_code: Mapped[str | None] = mapped_column(String(32))
    override_justification: Mapped[str | None] = mapped_column(Text)


class StaffDriverCapabilityVersion(BasicBase):
    """Append-only staff declaration used as input to driver review, never dispatch authority."""

    __tablename__ = "staff_driver_capability_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_driver_capability_membership",
        ),
        UniqueConstraint(
            "organization_id", "membership_id", "id", name="uq_driver_capability_identity"
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "version_number",
            name="uq_driver_capability_version",
        ),
        CheckConstraint("version_number > 0", name="ck_driver_capability_version"),
        CheckConstraint(
            "status IN ('declared','withdrawn')", name="ck_driver_capability_status"
        ),
        CheckConstraint(
            "vehicle_access IN ('none','organization_vehicle_only','personal_vehicle','either')",
            name="ck_driver_capability_vehicle_access",
        ),
        CheckConstraint(
            "source_kind IN ('screening_profile','staff_self','manager_recorded',"
            "'offer_acceptance')",
            name="ck_driver_capability_source",
        ),
        CheckConstraint(
            "(status='declared' AND willing_to_drive=true "
            "AND licence_jurisdiction IS NOT NULL AND licence_class IS NOT NULL "
            "AND vehicle_access<>'none') OR "
            "(status='withdrawn' AND willing_to_drive=false "
            "AND licence_jurisdiction IS NULL AND licence_jurisdiction_other IS NULL "
            "AND licence_class IS NULL AND vehicle_access='none' "
            "AND preferred_service_radius_km IS NULL)",
            name="ck_driver_capability_declaration",
        ),
        CheckConstraint(
            "(licence_jurisdiction='OTHER' AND licence_jurisdiction_other IS NOT NULL "
            "AND length(trim(licence_jurisdiction_other))>0) OR "
            "(licence_jurisdiction IS NULL AND licence_jurisdiction_other IS NULL) OR "
            "(licence_jurisdiction IS NOT NULL AND licence_jurisdiction<>'OTHER' "
            "AND licence_jurisdiction_other IS NULL)",
            name="ck_driver_capability_jurisdiction_other",
        ),
        CheckConstraint(
            "preferred_service_radius_km IS NULL OR "
            "preferred_service_radius_km BETWEEN 0 AND 1000",
            name="ck_driver_capability_radius",
        ),
        CheckConstraint(
            "(source_kind='screening_profile' AND source_screening_profile_version IS NOT NULL) "
            "OR (source_kind<>'screening_profile' "
            "AND source_screening_profile_version IS NULL)",
            name="ck_driver_capability_profile_source",
        ),
        CheckConstraint(
            "effective_at<=recorded_at", name="ck_driver_capability_recorded_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    willing_to_drive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    licence_jurisdiction: Mapped[str | None] = mapped_column(String(20))
    licence_jurisdiction_other: Mapped[str | None] = mapped_column(String(100))
    licence_class: Mapped[str | None] = mapped_column(String(30))
    vehicle_access: Mapped[str] = mapped_column(String(30), nullable=False)
    preferred_service_radius_km: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_screening_profile_version: Mapped[int | None] = mapped_column(Integer)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class StaffDriverQualificationVersion(BasicBase):
    """Append-only qualification fact for one staff membership and qualification lane."""

    __tablename__ = "staff_driver_qualification_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_driver_qualification_membership",
        ),
        ForeignKeyConstraint(
            ["source_screening_document_version_id"],
            ["staff_screening_document_versions.id"],
            ondelete="RESTRICT",
            name="fk_driver_qualification_screening_source",
        ),
        UniqueConstraint(
            "organization_id", "membership_id", "id", name="uq_driver_qualification_identity"
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "qualification_type",
            "version_number",
            name="uq_driver_qualification_version",
        ),
        CheckConstraint("version_number > 0", name="ck_driver_qualification_version"),
        CheckConstraint(
            "qualification_type IN ('driver_licence','driver_abstract','police_check',"
            "'vulnerable_sector_search','first_aid','vehicle_insurance_permission')",
            name="ck_driver_qualification_type",
        ),
        CheckConstraint(
            "status IN ('declared','verified','rejected','expired','revoked')",
            name="ck_driver_qualification_status",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date>=issue_date",
            name="ck_driver_qualification_date_order",
        ),
        CheckConstraint(
            "identifier_last4 IS NULL OR length(trim(identifier_last4)) BETWEEN 2 AND 8",
            name="ck_driver_qualification_identifier",
        ),
        CheckConstraint(
            "evidence_reference_sha256 IS NULL OR "
            + _lowercase_sha256_check("evidence_reference_sha256"),
            name="ck_driver_qualification_evidence_digest",
        ),
        CheckConstraint(
            "qualification_type<>'driver_licence' OR "
            "(jurisdiction IS NOT NULL AND qualification_class IS NOT NULL)",
            name="ck_driver_qualification_licence_fields",
        ),
        CheckConstraint(
            "qualification_type<>'driver_licence' OR expiry_date IS NOT NULL",
            name="ck_driver_qualification_licence_expiry",
        ),
        CheckConstraint(
            "effective_at<=recorded_at", name="ck_driver_qualification_recorded_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    qualification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(20))
    qualification_class: Mapped[str | None] = mapped_column(String(40))
    identifier_last4: Mapped[str | None] = mapped_column(String(8))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_screening_document_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True)
    )
    evidence_reference_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class StaffDriverAuthorizationDecision(BasicBase):
    """Append-only employer authorization; authorization alone never permits dispatch."""

    __tablename__ = "staff_driver_authorization_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_driver_authorization_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "capability_version_id"],
            [
                "staff_driver_capability_versions.organization_id",
                "staff_driver_capability_versions.membership_id",
                "staff_driver_capability_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_authorization_capability",
        ),
        UniqueConstraint(
            "organization_id", "membership_id", "id", name="uq_driver_authorization_identity"
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "decision_sequence",
            name="uq_driver_authorization_sequence",
        ),
        CheckConstraint("decision_sequence > 0", name="ck_driver_authorization_sequence"),
        CheckConstraint(
            "decision IN ('needs_review','authorized','denied','revoked')",
            name="ck_driver_authorization_decision",
        ),
        CheckConstraint(
            "length(trim(reason_code))>0", name="ck_driver_authorization_reason"
        ),
        CheckConstraint(
            "authorization_valid_until IS NULL OR authorization_valid_from IS NULL OR "
            "authorization_valid_until>authorization_valid_from",
            name="ck_driver_authorization_window",
        ),
        CheckConstraint(
            "(decision='authorized' AND authorization_valid_from IS NOT NULL "
            "AND authorization_valid_until IS NOT NULL "
            "AND authorization_valid_from>=reviewed_at) OR "
            "(decision<>'authorized' AND authorization_valid_from IS NULL "
            "AND authorization_valid_until IS NULL)",
            name="ck_driver_authorization_authorized_window",
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_driver_authorization_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    decision_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    qualification_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    authorization_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class TransportVehicle(BasicBase):
    """Logical organization or staff-personal vehicle with one-way retirement."""

    __tablename__ = "transport_vehicles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "staff_owner_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_transport_vehicle_staff_owner",
        ),
        UniqueConstraint("organization_id", "id", name="uq_transport_vehicle_identity"),
        CheckConstraint(
            "owner_kind IN ('organization','staff_personal')",
            name="ck_transport_vehicle_owner_kind",
        ),
        CheckConstraint(
            "(owner_kind='organization' AND staff_owner_membership_id IS NULL) OR "
            "(owner_kind='staff_personal' AND staff_owner_membership_id IS NOT NULL)",
            name="ck_transport_vehicle_owner",
        ),
        CheckConstraint(
            "(retired_at IS NULL AND retired_by_user_id IS NULL "
            "AND retirement_reason_code IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_by_user_id IS NOT NULL "
            "AND retirement_reason_code IS NOT NULL "
            "AND length(trim(retirement_reason_code))>0)",
            name="ck_transport_vehicle_retirement",
        ),
        CheckConstraint(
            "retired_at IS NULL OR retired_at>=created_at",
            name="ck_transport_vehicle_retirement_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    owner_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    staff_owner_membership_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retirement_reason_code: Mapped[str | None] = mapped_column(String(80))


class TransportVehicleVersion(BasicBase):
    """Append-only physical and registration facts for a logical vehicle."""

    __tablename__ = "transport_vehicle_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["transport_vehicles.organization_id", "transport_vehicles.id"],
            ondelete="RESTRICT",
            name="fk_transport_vehicle_version_vehicle",
        ),
        UniqueConstraint(
            "organization_id", "vehicle_id", "id", name="uq_transport_vehicle_version_identity"
        ),
        UniqueConstraint(
            "organization_id",
            "vehicle_id",
            "version_number",
            name="uq_transport_vehicle_version_number",
        ),
        CheckConstraint("version_number > 0", name="ck_transport_vehicle_version_number"),
        CheckConstraint(
            "length(trim(make))>0 AND length(trim(model))>0",
            name="ck_transport_vehicle_version_description",
        ),
        CheckConstraint(
            "model_year BETWEEN 1900 AND 2100", name="ck_transport_vehicle_version_year"
        ),
        CheckConstraint(
            "length(trim(plate_token)) BETWEEN 2 AND 24 "
            "AND length(trim(plate_jurisdiction)) BETWEEN 2 AND 20",
            name="ck_transport_vehicle_version_plate",
        ),
        CheckConstraint(
            "passenger_capacity BETWEEN 1 AND 30 AND child_passenger_capacity>=0 "
            "AND child_passenger_capacity<passenger_capacity",
            name="ck_transport_vehicle_version_capacity",
        ),
        CheckConstraint(
            "effective_at<=recorded_at", name="ck_transport_vehicle_version_recorded_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    vehicle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String(40))
    plate_token: Mapped[str] = mapped_column(String(24), nullable=False)
    plate_jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    passenger_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    child_passenger_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    wheelchair_accessible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class TransportVehicleEvidenceVersion(BasicBase):
    """Append-only encrypted source metadata for registration, insurance, and inspections."""

    __tablename__ = "transport_vehicle_evidence_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id", "vehicle_version_id"],
            [
                "transport_vehicle_versions.organization_id",
                "transport_vehicle_versions.vehicle_id",
                "transport_vehicle_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_transport_vehicle_evidence_vehicle_version",
        ),
        UniqueConstraint(
            "organization_id",
            "vehicle_id",
            "id",
            name="uq_transport_vehicle_evidence_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "vehicle_id",
            "evidence_type",
            "version_number",
            name="uq_transport_vehicle_evidence_version",
        ),
        CheckConstraint("version_number > 0", name="ck_transport_vehicle_evidence_version"),
        CheckConstraint(
            "evidence_type IN ('registration','insurance','inspection','maintenance')",
            name="ck_transport_vehicle_evidence_type",
        ),
        CheckConstraint(
            "status IN ('provided','verified','rejected','expired','revoked')",
            name="ck_transport_vehicle_evidence_status",
        ),
        CheckConstraint("byte_size>0", name="ck_transport_vehicle_evidence_size"),
        CheckConstraint(
            "media_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_transport_vehicle_evidence_media_type",
        ),
        CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_transport_vehicle_evidence_content_sha256",
        ),
        CheckConstraint(
            _lowercase_sha256_check("ciphertext_sha256"),
            name="ck_transport_vehicle_evidence_ciphertext_sha256",
        ),
        CheckConstraint(
            _opaque_storage_reference_check("storage_reference"),
            name="ck_transport_vehicle_evidence_storage_reference",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date>=issue_date",
            name="ck_transport_vehicle_evidence_date_order",
        ),
        CheckConstraint(
            "evidence_type NOT IN ('registration','insurance','inspection') "
            "OR expiry_date IS NOT NULL",
            name="ck_transport_vehicle_evidence_expiry",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    vehicle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    vehicle_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    ciphertext_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class StaffDriverReadinessDecision(BasicBase):
    """Append-only fail-closed evaluation bound to exact staff and vehicle versions."""

    __tablename__ = "staff_driver_readiness_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_driver_readiness_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "capability_version_id"],
            [
                "staff_driver_capability_versions.organization_id",
                "staff_driver_capability_versions.membership_id",
                "staff_driver_capability_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_readiness_capability",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "authorization_decision_id"],
            [
                "staff_driver_authorization_decisions.organization_id",
                "staff_driver_authorization_decisions.membership_id",
                "staff_driver_authorization_decisions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_readiness_authorization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id", "vehicle_version_id"],
            [
                "transport_vehicle_versions.organization_id",
                "transport_vehicle_versions.vehicle_id",
                "transport_vehicle_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_readiness_vehicle_version",
        ),
        UniqueConstraint(
            "organization_id", "membership_id", "id", name="uq_driver_readiness_identity"
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "decision_sequence",
            name="uq_driver_readiness_sequence",
        ),
        CheckConstraint("decision_sequence > 0", name="ck_driver_readiness_sequence"),
        CheckConstraint(
            "decision IN ('incomplete','needs_review','blocked')",
            name="ck_driver_readiness_decision",
        ),
        CheckConstraint(
            "(vehicle_id IS NULL AND vehicle_version_id IS NULL) OR "
            "(vehicle_id IS NOT NULL AND vehicle_version_id IS NOT NULL)",
            name="ck_driver_readiness_vehicle_pair",
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_driver_readiness_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    decision_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authorization_decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vehicle_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    vehicle_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    vehicle_evidence_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class TransportRegistryCommandReceipt(BasicBase):
    """Actor-private exact-retry receipt for one bounded 0032 registry command."""

    __tablename__ = "transport_registry_command_receipts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "client_operation_id",
            name="uq_transport_registry_receipt_operation",
        ),
        CheckConstraint(
            "command_kind IN ('driver_declaration','qualification_evidence',"
            "'qualification_review','driver_authorization','vehicle_create',"
            "'vehicle_version','vehicle_retire','vehicle_evidence',"
            "'vehicle_evidence_review','readiness_evaluation')",
            name="ck_transport_registry_receipt_command",
        ),
        CheckConstraint(
            _lowercase_sha256_check("request_sha256"),
            name="ck_transport_registry_receipt_request_sha256",
        ),
        CheckConstraint(
            "result_kind IN ('driver_capability','driver_qualification',"
            "'driver_authorization','vehicle','vehicle_version','vehicle_evidence',"
            "'driver_readiness')",
            name="ck_transport_registry_receipt_result_kind",
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_transport_registry_receipt_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    request_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    result_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class StaffDriverQualificationEvidenceObject(BasicBase):
    """Immutable encrypted evidence metadata bound to one declared qualification version."""

    __tablename__ = "staff_driver_qualification_evidence_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "qualification_version_id"],
            [
                "staff_driver_qualification_versions.organization_id",
                "staff_driver_qualification_versions.membership_id",
                "staff_driver_qualification_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_qualification_evidence_version",
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "qualification_version_id",
            name="uq_driver_qualification_evidence_version",
        ),
        CheckConstraint("byte_size>0", name="ck_driver_qualification_evidence_size"),
        CheckConstraint(
            "media_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_driver_qualification_evidence_media_type",
        ),
        CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_driver_qualification_evidence_content_sha256",
        ),
        CheckConstraint(
            _lowercase_sha256_check("ciphertext_sha256"),
            name="ck_driver_qualification_evidence_ciphertext_sha256",
        ),
        CheckConstraint(
            _opaque_storage_reference_check("storage_reference"),
            name="ck_driver_qualification_evidence_storage_reference",
        ),
        CheckConstraint(
            "length(trim(scanner_engine))>0 AND length(trim(scanner_version))>0",
            name="ck_driver_qualification_evidence_scan_provenance",
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_driver_qualification_evidence_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    qualification_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    ciphertext_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    scanner_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(160), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class StaffDriverQualificationReviewDecision(BasicBase):
    """Independent employer review linking disclosed evidence to its derived fact version."""

    __tablename__ = "staff_driver_qualification_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "source_qualification_version_id"],
            [
                "staff_driver_qualification_versions.organization_id",
                "staff_driver_qualification_versions.membership_id",
                "staff_driver_qualification_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_qualification_review_source",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "result_qualification_version_id"],
            [
                "staff_driver_qualification_versions.organization_id",
                "staff_driver_qualification_versions.membership_id",
                "staff_driver_qualification_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_driver_qualification_review_result",
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            "result_qualification_version_id",
            name="uq_driver_qualification_review_result",
        ),
        CheckConstraint(
            "decision IN ('verified','rejected')",
            name="ck_driver_qualification_review_decision",
        ),
        CheckConstraint(
            "source_qualification_version_id<>result_qualification_version_id",
            name="ck_driver_qualification_review_distinct_versions",
        ),
        CheckConstraint(
            "length(trim(reason_code))>0", name="ck_driver_qualification_review_reason"
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_driver_qualification_review_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    source_qualification_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    result_qualification_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class TransportVehicleEvidenceReviewDecision(BasicBase):
    """Independent employer review of one encrypted vehicle evidence version."""

    __tablename__ = "transport_vehicle_evidence_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id", "source_evidence_version_id"],
            [
                "transport_vehicle_evidence_versions.organization_id",
                "transport_vehicle_evidence_versions.vehicle_id",
                "transport_vehicle_evidence_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_review_source",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id", "result_evidence_version_id"],
            [
                "transport_vehicle_evidence_versions.organization_id",
                "transport_vehicle_evidence_versions.vehicle_id",
                "transport_vehicle_evidence_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_review_result",
        ),
        UniqueConstraint(
            "organization_id",
            "vehicle_id",
            "result_evidence_version_id",
            name="uq_vehicle_evidence_review_result",
        ),
        CheckConstraint(
            "decision IN ('verified','rejected')",
            name="ck_vehicle_evidence_review_decision",
        ),
        CheckConstraint(
            "source_evidence_version_id<>result_evidence_version_id",
            name="ck_vehicle_evidence_review_distinct_versions",
        ),
        CheckConstraint(
            "length(trim(reason_code))>0", name="ck_vehicle_evidence_review_reason"
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_vehicle_evidence_review_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    vehicle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    source_evidence_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    result_evidence_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class TransportVehicleEvidenceScanFact(BasicBase):
    """Authoritative clean-scan provenance for one encrypted vehicle evidence version."""

    __tablename__ = "transport_vehicle_evidence_scan_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id", "evidence_version_id"],
            [
                "transport_vehicle_evidence_versions.organization_id",
                "transport_vehicle_evidence_versions.vehicle_id",
                "transport_vehicle_evidence_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_scan_version",
        ),
        UniqueConstraint(
            "organization_id",
            "vehicle_id",
            "evidence_version_id",
            name="uq_vehicle_evidence_scan_version",
        ),
        CheckConstraint(
            "decision='clean' AND scanner_signature IS NULL",
            name="ck_vehicle_evidence_scan_clean_only",
        ),
        CheckConstraint(
            "length(trim(scanner_engine))>0 AND length(trim(scanner_version))>0",
            name="ck_vehicle_evidence_scan_provenance",
        ),
        CheckConstraint(
            "operational_driver_ready=false AND dispatch_authorized=false",
            name="ck_vehicle_evidence_scan_not_operational",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    vehicle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    evidence_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    scanner_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(160), nullable=False)
    scanner_signature: Mapped[str | None] = mapped_column(String(160))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operational_driver_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    dispatch_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


Index(
    "uq_marketplace_credentials_current",
    MarketplaceCredentialDocument.user_id,
    unique=True,
    postgresql_where=MarketplaceCredentialDocument.is_current.is_(True),
    sqlite_where=MarketplaceCredentialDocument.is_current.is_(True),
)


Index(
    "uq_staff_shifts_open_membership",
    StaffShift.organization_id,
    StaffShift.membership_id,
    unique=True,
    postgresql_where=StaffShift.status == "open",
    sqlite_where=StaffShift.status == "open",
)


Index(
    "uq_staff_shifts_scheduled_link",
    StaffShift.organization_id,
    StaffShift.scheduled_shift_id,
    unique=True,
    postgresql_where=StaffShift.scheduled_shift_id.is_not(None),
    sqlite_where=StaffShift.scheduled_shift_id.is_not(None),
)


# ---------------------------------------------------------------------------
# 0033 billing ledger
# ---------------------------------------------------------------------------
#
# These tables intentionally do not reuse the mutable legacy invoicing
# mappings.  Every object below is an append-only fact.  Current balances and
# lifecycle labels are projections over issued documents, settled payments,
# allocations, and credits; no posted finance row needs an UPDATE.


class Billing0033RolePermissionBackup(BasicBase):
    """Private release backup retained only for exact Alembic metadata parity."""

    __tablename__ = "billing_0033_role_permission_backups"

    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BillingManualActivation(BasicBase):
    """Immutable owner-reviewed boundary for private, off-platform billing."""

    __tablename__ = "billing_manual_activations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_manual_activation_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "activated_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_manual_activation_actor",
        ),
        ForeignKeyConstraint(
            ["organization_id", "activated_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_bill_manual_activation_membership",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_bill_manual_activation_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            name="uq_bill_manual_activation_org",
        ),
        CheckConstraint(
            "activation_policy_version='private_local_manual_billing_v1'",
            name="ck_bill_manual_activation_policy",
        ),
        CheckConstraint(
            "review_attestation='I reviewed the private manual billing boundary and "
            "understand that CareSync will only record off-platform payments.'",
            name="ck_bill_manual_activation_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    activated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activated_by_membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activation_policy_version: Mapped[str] = mapped_column(
        String(50),
        default="private_local_manual_billing_v1",
        server_default=text("'private_local_manual_billing_v1'"),
        nullable=False,
    )
    review_attestation: Mapped[str] = mapped_column(String(180), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingSandboxSourceAttestation(BasicBase):
    """Migration/test-owned proof that a source row contains synthetic data only."""

    __tablename__ = "billing_sandbox_source_attestations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_sandbox_source_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "attested_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_sandbox_source_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_sandbox_source_org_id"),
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            name="uq_bill_sandbox_source_identity",
        ),
        CheckConstraint(
            "source_type IN ('organization','family','guardian','child','enrollment',"
            "'facility','program')",
            name="ck_bill_sandbox_source_type",
        ),
        CheckConstraint(
            "marker='TEST_SYNTHETIC_ONLY'", name="ck_bill_sandbox_source_marker"
        ),
        CheckConstraint(
            "reason_code='disposable_test_fixture'", name="ck_bill_sandbox_source_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    marker: Mapped[str] = mapped_column(
        String(40),
        default="TEST_SYNTHETIC_ONLY",
        server_default=text("'TEST_SYNTHETIC_ONLY'"),
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(
        String(50),
        default="disposable_test_fixture",
        server_default=text("'disposable_test_fixture'"),
        nullable=False,
    )
    attested_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


def _billing_effect_constraints(prefix: str):
    return (
        ForeignKeyConstraint(
            ["organization_id", "client_operation_id", "request_hash"],
            [
                "billing_command_preparations.organization_id",
                "billing_command_preparations.client_operation_id",
                "billing_command_preparations.request_hash",
            ],
            ondelete="RESTRICT",
            name=f"fk_bill_{prefix}_preparation",
        ),
        CheckConstraint(
            _lowercase_sha256_check("request_hash"),
            name=f"ck_bill_{prefix}_request_hash",
        ),
    )


class BillingCommandEffectMixin:
    """Exact operation/digest provenance copied into every immutable effect."""

    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class BillingAccount(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_accounts"
    __table_args__ = (
        *_billing_effect_constraints("account"),
        ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            ondelete="RESTRICT",
            name="fk_bill_account_family",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "payer_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            ondelete="RESTRICT",
            name="fk_bill_account_payer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "opened_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_account_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_account_org_id"),
        UniqueConstraint(
            "organization_id", "family_id", "id", name="uq_bill_account_org_family_id"
        ),
        UniqueConstraint("organization_id", "family_id", name="uq_bill_account_family"),
        UniqueConstraint("organization_id", "account_number", name="uq_bill_account_number"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_account_operation"
        ),
        CheckConstraint("currency='CAD'", name="ck_bill_account_currency"),
        CheckConstraint("status='open'", name="ck_bill_account_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    payer_guardian_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    account_number: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default=text("'open'"), nullable=False
    )
    opened_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingAccountPayerVersion(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_account_payer_versions"
    __table_args__ = (
        *_billing_effect_constraints("payer_ver"),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "billing_account_id"],
            [
                "billing_accounts.organization_id",
                "billing_accounts.family_id",
                "billing_accounts.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_payer_ver_account",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "payer_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            ondelete="RESTRICT",
            name="fk_bill_payer_ver_guardian",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_payer_ver_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_payer_ver_org_id"),
        UniqueConstraint(
            "organization_id",
            "billing_account_id",
            "id",
            name="uq_bill_payer_ver_account_id",
        ),
        UniqueConstraint(
            "organization_id",
            "billing_account_id",
            "version_number",
            name="uq_bill_payer_ver_number",
        ),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_payer_ver_operation"
        ),
        CheckConstraint("version_number>0", name="ck_bill_payer_ver_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payer_guardian_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingRatePlan(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_rate_plans"
    __table_args__ = (
        *_billing_effect_constraints("rate_plan"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_rate_plan_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "program_id"],
            [
                "facility_programs.organization_id",
                "facility_programs.facility_id",
                "facility_programs.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_rate_plan_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_rate_plan_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_rate_plan_org_id"),
        UniqueConstraint("organization_id", "code", name="uq_bill_rate_plan_code"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_rate_plan_operation"
        ),
        CheckConstraint("length(trim(name))>0", name="ck_bill_rate_plan_name"),
        CheckConstraint("length(trim(code))>0", name="ck_bill_rate_plan_code"),
        CheckConstraint(
            "program_type IN ('daycare','out_of_school_care')",
            name="ck_bill_rate_plan_program_type",
        ),
        CheckConstraint("charge_kind='core_care'", name="ck_bill_rate_plan_charge_kind"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    program_type: Mapped[str] = mapped_column(String(40), nullable=False)
    charge_kind: Mapped[str] = mapped_column(
        String(30), default="core_care", server_default=text("'core_care'"), nullable=False
    )
    age_group: Mapped[str | None] = mapped_column(String(100))
    facility_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingRatePlanVersion(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_rate_plan_versions"
    __table_args__ = (
        *_billing_effect_constraints("rate_ver"),
        ForeignKeyConstraint(
            ["organization_id", "rate_plan_id"],
            ["billing_rate_plans.organization_id", "billing_rate_plans.id"],
            ondelete="RESTRICT",
            name="fk_bill_rate_version_plan",
        ),
        ForeignKeyConstraint(
            ["organization_id", "published_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_rate_ver_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_rate_ver_org_id"),
        UniqueConstraint(
            "organization_id", "rate_plan_id", "id", name="uq_bill_rate_ver_plan_id"
        ),
        UniqueConstraint(
            "organization_id",
            "rate_plan_id",
            "version_number",
            name="uq_bill_rate_ver_number",
        ),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_rate_ver_operation"
        ),
        CheckConstraint("version_number>0", name="ck_bill_rate_ver_number"),
        CheckConstraint("currency='CAD'", name="ck_bill_rate_ver_currency"),
        CheckConstraint(
            "billing_unit IN ('weekly_period','biweekly_period','monthly_period','service_event')",
            name="ck_bill_rate_ver_unit",
        ),
        CheckConstraint(
            "unit_amount_minor BETWEEN 0 AND 9000000000000", name="ck_bill_rate_ver_amount"
        ),
        CheckConstraint("tax_rate_basis_points=0", name="ck_bill_rate_ver_tax_disabled"),
        CheckConstraint(
            "effective_until IS NULL OR effective_until>=effective_from",
            name="ck_bill_rate_ver_dates",
        ),
        CheckConstraint("status='published'", name="ck_bill_rate_ver_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    rate_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_rate_basis_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), default="published", server_default=text("'published'"), nullable=False
    )
    published_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingAgreement(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_agreements"
    __table_args__ = (
        *_billing_effect_constraints("agreement"),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "billing_account_id"],
            [
                "billing_accounts.organization_id",
                "billing_accounts.family_id",
                "billing_accounts.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_agreement_account",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_bill_agreement_child",
        ),
        ForeignKeyConstraint(
            ["organization_id", "facility_id", "child_id", "enrollment_id"],
            [
                "enrollments.organization_id",
                "enrollments.facility_id",
                "enrollments.child_id",
                "enrollments.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_agreement_enrollment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_agreement_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_agreement_org_id"),
        UniqueConstraint(
            "organization_id", "billing_account_id", "id", name="uq_bill_agreement_acct_id"
        ),
        UniqueConstraint(
            "organization_id",
            "billing_account_id",
            "enrollment_id",
            name="uq_bill_agreement_account_enrollment",
        ),
        Index(
            "uq_bill_agreement_legacy_account_child",
            "organization_id",
            "billing_account_id",
            "child_id",
            unique=True,
            postgresql_where=text("enrollment_id IS NULL"),
            sqlite_where=text("enrollment_id IS NULL"),
        ),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_agreement_operation"
        ),
        CheckConstraint(
            "(enrollment_id IS NULL AND facility_id IS NULL) OR "
            "(enrollment_id IS NOT NULL AND facility_id IS NOT NULL)",
            name="ck_bill_agreement_enrollment_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    enrollment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    facility_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingAgreementVersion(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_agreement_versions"
    __table_args__ = (
        *_billing_effect_constraints("agreement_ver"),
        ForeignKeyConstraint(
            ["organization_id", "agreement_id"],
            ["billing_agreements.organization_id", "billing_agreements.id"],
            ondelete="RESTRICT",
            name="fk_bill_agreement_ver_root",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rate_plan_version_id"],
            ["billing_rate_plan_versions.organization_id", "billing_rate_plan_versions.id"],
            ondelete="RESTRICT",
            name="fk_bill_agreement_ver_rate",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_agreement_ver_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_agreement_ver_org_id"),
        UniqueConstraint(
            "organization_id", "agreement_id", "id", name="uq_bill_agreement_ver_root_id"
        ),
        UniqueConstraint(
            "organization_id",
            "agreement_id",
            "version_number",
            name="uq_bill_agreement_ver_number",
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_bill_agreement_ver_operation",
        ),
        CheckConstraint("version_number>0", name="ck_bill_agreement_ver_number"),
        CheckConstraint(
            "billing_frequency IN ('weekly','biweekly','monthly','per_service')",
            name="ck_bill_agreement_ver_frequency",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until>=effective_from",
            name="ck_bill_agreement_ver_dates",
        ),
        CheckConstraint(
            "family_amount_minor_per_unit BETWEEN 0 AND 9000000000000 "
            "AND funding_amount_minor_per_unit=0",
            name="ck_bill_agreement_ver_portions",
        ),
        CheckConstraint("review_status='reviewed'", name="ck_bill_agreement_ver_review"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    agreement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    rate_plan_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    family_amount_minor_per_unit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funding_amount_minor_per_unit: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(
        String(20), default="reviewed", server_default=text("'reviewed'"), nullable=False
    )
    reviewed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingInvoice(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        *_billing_effect_constraints("invoice"),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "billing_account_id"],
            [
                "billing_accounts.organization_id",
                "billing_accounts.family_id",
                "billing_accounts.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_invoice_account",
        ),
        ForeignKeyConstraint(
            ["organization_id", "billing_account_id", "billing_account_payer_version_id"],
            [
                "billing_account_payer_versions.organization_id",
                "billing_account_payer_versions.billing_account_id",
                "billing_account_payer_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_invoice_payer_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "payer_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            ondelete="RESTRICT",
            name="fk_bill_invoice_payer_guardian",
        ),
        ForeignKeyConstraint(
            ["organization_id", "issued_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_invoice_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_invoice_org_id"),
        UniqueConstraint(
            "organization_id", "billing_account_id", "id", name="uq_bill_invoice_acct_id"
        ),
        UniqueConstraint("organization_id", "invoice_number", name="uq_bill_invoice_number"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_invoice_operation"
        ),
        CheckConstraint("status='issued'", name="ck_bill_invoice_status"),
        CheckConstraint("currency='CAD'", name="ck_bill_invoice_currency"),
        CheckConstraint("due_date>=issue_date", name="ck_bill_invoice_due_date"),
        CheckConstraint(
            "service_period_end>=service_period_start", name="ck_bill_invoice_service_dates"
        ),
        CheckConstraint(
            "gross_subtotal_minor>=0 AND funding_minor>=0 AND subtotal_minor>=0 AND "
            "gross_subtotal_minor=subtotal_minor+funding_minor AND tax_minor>=0 AND "
            "total_minor=subtotal_minor+tax_minor AND "
            "gross_subtotal_minor<=9000000000000 AND funding_minor<=9000000000000 AND "
            "subtotal_minor<=9000000000000 AND tax_minor<=9000000000000 AND "
            "total_minor<=9000000000000",
            name="ck_bill_invoice_totals",
        ),
        CheckConstraint("total_minor>0", name="ck_bill_invoice_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    billing_account_payer_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    payer_guardian_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="issued", server_default=text("'issued'"), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    service_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    family_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    payer_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    payer_email_snapshot: Mapped[str | None] = mapped_column(String(320))
    payer_address_snapshot: Mapped[str | None] = mapped_column(String(500))
    gross_subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funding_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issued_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingInvoiceLine(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_invoice_lines"
    __table_args__ = (
        *_billing_effect_constraints("invoice_line"),
        ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["billing_invoices.organization_id", "billing_invoices.id"],
            ondelete="RESTRICT",
            name="fk_bill_invoice_line_invoice",
        ),
        ForeignKeyConstraint(
            ["organization_id", "agreement_version_id"],
            ["billing_agreement_versions.organization_id", "billing_agreement_versions.id"],
            ondelete="RESTRICT",
            name="fk_bill_invoice_line_agreement",
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_bill_invoice_line_child",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_invoice_line_org_id"),
        UniqueConstraint(
            "organization_id", "invoice_id", "line_number", name="uq_bill_invoice_line_number"
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            "agreement_version_id",
            name="uq_bill_invoice_line_operation_agreement",
        ),
        CheckConstraint("line_number>0", name="ck_bill_invoice_line_number"),
        CheckConstraint("quantity>0", name="ck_bill_invoice_line_quantity"),
        CheckConstraint(
            "gross_unit_amount_minor>=0 AND funding_unit_amount_minor>=0 AND "
            "unit_amount_minor>=0 AND "
            "gross_unit_amount_minor=unit_amount_minor+funding_unit_amount_minor AND "
            "gross_subtotal_minor=quantity*gross_unit_amount_minor AND "
            "funding_minor=quantity*funding_unit_amount_minor AND "
            "subtotal_minor=quantity*unit_amount_minor AND "
            "gross_unit_amount_minor<=9000000000000 AND "
            "funding_unit_amount_minor<=9000000000000 AND "
            "unit_amount_minor<=9000000000000 AND gross_subtotal_minor<=9000000000000 AND "
            "funding_minor<=9000000000000 AND subtotal_minor<=9000000000000",
            name="ck_bill_invoice_line_subtotal",
        ),
        CheckConstraint(
            "tax_rate_basis_points BETWEEN 0 AND 10000", name="ck_bill_invoice_line_tax_rate"
        ),
        CheckConstraint(
            "tax_minor BETWEEN 0 AND 9000000000000 AND "
            "total_minor=subtotal_minor+tax_minor AND total_minor<=9000000000000",
            name="ck_bill_invoice_line_total",
        ),
        CheckConstraint(
            "service_period_end>=service_period_start", name="ck_bill_invoice_line_dates"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    agreement_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    child_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    child_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    rate_plan_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    billing_unit_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    service_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    service_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funding_unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funding_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BillingPayment(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_payments"
    __table_args__ = (
        *_billing_effect_constraints("payment"),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "billing_account_id"],
            [
                "billing_accounts.organization_id",
                "billing_accounts.family_id",
                "billing_accounts.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_payment_account",
        ),
        ForeignKeyConstraint(
            ["organization_id", "family_id", "payer_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            ondelete="RESTRICT",
            name="fk_bill_payment_payer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "recorded_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_payment_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_payment_org_id"),
        UniqueConstraint(
            "organization_id", "billing_account_id", "id", name="uq_bill_payment_acct_id"
        ),
        UniqueConstraint(
            "organization_id",
            "external_reference",
            name="uq_bill_payment_reference",
        ),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_payment_operation"
        ),
        CheckConstraint("currency='CAD'", name="ck_bill_payment_currency"),
        CheckConstraint("status='settled'", name="ck_bill_payment_status"),
        CheckConstraint(
            "method IN ('cash','cheque','e_transfer','other')", name="ck_bill_payment_method"
        ),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9000000000000", name="ck_bill_payment_amount"
        ),
        CheckConstraint(
            "length(trim(external_reference))>0 AND "
            "(method NOT IN ('cash','other') OR "
            "(operator_confirmation_note IS NOT NULL "
            "AND length(trim(operator_confirmation_note))>0))",
            name="ck_bill_payment_evidence",
        ),
        CheckConstraint(
            "external_reference=upper(trim(external_reference))",
            name="ck_bill_payment_reference_canonical",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payer_guardian_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="settled", server_default=text("'settled'"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    payer_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    payer_email_snapshot: Mapped[str | None] = mapped_column(String(320))
    operator_confirmation_note: Mapped[str | None] = mapped_column(String(500))
    memo: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingAllocation(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_allocations"
    __table_args__ = (
        *_billing_effect_constraints("allocation"),
        ForeignKeyConstraint(
            ["organization_id", "billing_account_id", "payment_id"],
            [
                "billing_payments.organization_id",
                "billing_payments.billing_account_id",
                "billing_payments.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_allocation_payment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "billing_account_id", "invoice_id"],
            [
                "billing_invoices.organization_id",
                "billing_invoices.billing_account_id",
                "billing_invoices.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_allocation_invoice",
        ),
        ForeignKeyConstraint(
            ["organization_id", "allocated_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_allocation_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_allocation_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_allocation_operation"
        ),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9000000000000", name="ck_bill_allocation_amount"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    payment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingCredit(BillingCommandEffectMixin, BasicBase):
    __tablename__ = "billing_credits"
    __table_args__ = (
        *_billing_effect_constraints("credit"),
        ForeignKeyConstraint(
            ["organization_id", "billing_account_id", "invoice_id"],
            [
                "billing_invoices.organization_id",
                "billing_invoices.billing_account_id",
                "billing_invoices.id",
            ],
            ondelete="RESTRICT",
            name="fk_bill_credit_invoice",
        ),
        ForeignKeyConstraint(
            ["organization_id", "issued_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_credit_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_credit_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_credit_operation"
        ),
        CheckConstraint("currency='CAD'", name="ck_bill_credit_currency"),
        CheckConstraint("status='issued'", name="ck_bill_credit_status"),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9000000000000", name="ck_bill_credit_amount"
        ),
        CheckConstraint("length(trim(reason_code))>0", name="ck_bill_credit_reason"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="issued", server_default=text("'issued'"), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    issued_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingJournalEntry(BasicBase):
    __tablename__ = "billing_journal_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_journal_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "posted_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_journal_actor",
        ),
        ForeignKeyConstraint(
            ["organization_id", "client_operation_id", "request_hash"],
            [
                "billing_command_preparations.organization_id",
                "billing_command_preparations.client_operation_id",
                "billing_command_preparations.request_hash",
            ],
            ondelete="RESTRICT",
            name="fk_bill_journal_preparation",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_journal_org_id"),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_bill_journal_operation",
        ),
        UniqueConstraint(
            "organization_id", "book_sequence", name="uq_bill_journal_book_sequence"
        ),
        UniqueConstraint(
            "organization_id", "source_type", "source_id", name="uq_bill_journal_source"
        ),
        CheckConstraint("currency='CAD'", name="ck_bill_journal_currency"),
        CheckConstraint("book_sequence>0", name="ck_bill_journal_book_sequence"),
        CheckConstraint(_lowercase_sha256_check("request_hash"), name="ck_bill_journal_hash"),
        CheckConstraint(
            "entry_kind IN ('invoice_issued','payment_settled','payment_allocated',"
            "'credit_issued','reversal')",
            name="ck_bill_journal_kind",
        ),
        CheckConstraint(
            "source_type IN ('billing_invoice','billing_payment','billing_allocation',"
            "'billing_credit','billing_reversal')",
            name="ck_bill_journal_source_type",
        ),
        CheckConstraint(
            "(entry_kind='invoice_issued' AND source_type='billing_invoice') OR "
            "(entry_kind='payment_settled' AND source_type='billing_payment') OR "
            "(entry_kind='payment_allocated' AND source_type='billing_allocation') OR "
            "(entry_kind='credit_issued' AND source_type='billing_credit') OR "
            "(entry_kind='reversal' AND source_type='billing_reversal')",
            name="ck_bill_journal_source_match",
        ),
        CheckConstraint(
            "line_count>=2 AND total_debit_minor>0 AND "
            "total_debit_minor=total_credit_minor AND "
            "total_debit_minor<=9000000000000",
            name="ck_bill_journal_balanced_header",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    book_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(
        CHAR(3), default="CAD", server_default=text("'CAD'"), nullable=False
    )
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_debit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_credit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posted_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingJournalLine(BasicBase):
    __tablename__ = "billing_journal_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "journal_entry_id"],
            ["billing_journal_entries.organization_id", "billing_journal_entries.id"],
            ondelete="RESTRICT",
            name="fk_bill_journal_line_entry",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_journal_line_org_id"),
        UniqueConstraint(
            "organization_id",
            "journal_entry_id",
            "line_number",
            name="uq_bill_journal_line_number",
        ),
        CheckConstraint("line_number>0", name="ck_bill_journal_line_number"),
        CheckConstraint("direction IN ('debit','credit')", name="ck_bill_journal_line_direction"),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9000000000000", name="ck_bill_journal_line_amount"
        ),
        CheckConstraint("length(trim(account_code))>0", name="ck_bill_journal_line_account"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    journal_entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(String(60), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BillingReversal(BasicBase):
    __tablename__ = "billing_reversals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "original_journal_entry_id"],
            ["billing_journal_entries.organization_id", "billing_journal_entries.id"],
            ondelete="RESTRICT",
            name="fk_bill_reversal_original",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversing_journal_entry_id"],
            ["billing_journal_entries.organization_id", "billing_journal_entries.id"],
            ondelete="RESTRICT",
            name="fk_bill_reversal_reversing",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversed_by_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_reversal_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_reversal_org_id"),
        UniqueConstraint(
            "organization_id", "original_journal_entry_id", name="uq_bill_reversal_original"
        ),
        CheckConstraint(
            "original_journal_entry_id<>reversing_journal_entry_id",
            name="ck_bill_reversal_distinct",
        ),
        CheckConstraint("length(trim(reason_code))>0", name="ck_bill_reversal_reason"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    original_journal_entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reversing_journal_entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reversed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reversed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingCommandPreparation(BasicBase):
    """Server-canonical, PII-free proof prepared before a billing command."""

    __tablename__ = "billing_command_preparations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_preparation_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_preparation_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_preparation_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_preparation_operation"
        ),
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            "request_hash",
            name="uq_bill_preparation_operation_hash",
        ),
        CheckConstraint(
            "command_type IN ('account_open','account_payer_assign','rate_version_publish',"
            "'agreement_establish','invoice_issue','payment_record','payment_allocate',"
            "'credit_issue')",
            name="ck_bill_preparation_command",
        ),
        CheckConstraint(
            _lowercase_sha256_check("request_hash"), name="ck_bill_preparation_hash"
        ),
        CheckConstraint(
            "length(trim(target_scope))>0", name="ck_bill_preparation_target_scope"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingCommandTerminal(BasicBase):
    """Unified receipt/absence slot preventing split-terminal races."""

    __tablename__ = "billing_command_terminals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_terminal_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_terminal_actor",
        ),
        ForeignKeyConstraint(
            ["organization_id", "client_operation_id", "request_hash"],
            [
                "billing_command_preparations.organization_id",
                "billing_command_preparations.client_operation_id",
                "billing_command_preparations.request_hash",
            ],
            ondelete="RESTRICT",
            name="fk_bill_terminal_preparation",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_terminal_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_terminal_operation"
        ),
        UniqueConstraint(
            "organization_id",
            "terminal_kind",
            "terminal_id",
            name="uq_bill_terminal_fact",
        ),
        CheckConstraint(
            "command_type IN ('account_open','account_payer_assign','rate_version_publish',"
            "'agreement_establish','invoice_issue','payment_record','payment_allocate',"
            "'credit_issue')",
            name="ck_bill_terminal_command",
        ),
        CheckConstraint(
            "terminal_kind IN ('receipt','absence_claim')", name="ck_bill_terminal_kind"
        ),
        CheckConstraint(_lowercase_sha256_check("request_hash"), name="ck_bill_terminal_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    terminal_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    terminal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingCommandReceipt(BasicBase):
    __tablename__ = "billing_command_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_receipt_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_receipt_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_receipt_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_receipt_operation"
        ),
        CheckConstraint(
            "command_type IN ('account_open','account_payer_assign','rate_version_publish',"
            "'agreement_establish',"
            "'invoice_issue','payment_record','payment_allocate','credit_issue')",
            name="ck_bill_receipt_command",
        ),
        CheckConstraint(
            "result_kind IN ('billing_account','billing_rate_plan','billing_agreement',"
            "'billing_invoice','billing_payment','billing_allocation','billing_credit')",
            name="ck_bill_receipt_result_kind",
        ),
        CheckConstraint(
            "(command_type IN ('account_open','account_payer_assign') "
            "AND result_kind='billing_account') OR "
            "(command_type='rate_version_publish' AND result_kind='billing_rate_plan') OR "
            "(command_type='agreement_establish' AND result_kind='billing_agreement') OR "
            "(command_type='invoice_issue' AND result_kind='billing_invoice') OR "
            "(command_type='payment_record' AND result_kind='billing_payment') OR "
            "(command_type='payment_allocate' AND result_kind='billing_allocation') OR "
            "(command_type='credit_issue' AND result_kind='billing_credit')",
            name="ck_bill_receipt_result_match",
        ),
        CheckConstraint(_lowercase_sha256_check("request_hash"), name="ck_bill_receipt_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_path: Mapped[str] = mapped_column(String(255), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BillingCommandClaim(BasicBase):
    """Durable proof that an actor reconciled an operation as not committed."""

    __tablename__ = "billing_command_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_bill_claim_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_bill_claim_actor",
        ),
        UniqueConstraint("organization_id", "id", name="uq_bill_claim_org_id"),
        UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_bill_claim_operation"
        ),
        CheckConstraint(
            "command_type IN ('account_open','account_payer_assign','rate_version_publish',"
            "'agreement_establish','invoice_issue','payment_record','payment_allocate',"
            "'credit_issue')",
            name="ck_bill_claim_command",
        ),
        CheckConstraint(_lowercase_sha256_check("request_hash"), name="ck_bill_claim_hash"),
        CheckConstraint(
            "length(trim(target_scope))>0", name="ck_bill_claim_target_scope"
        ),
        CheckConstraint(
            "reason_code='operator_confirmed_not_committed'",
            name="ck_bill_claim_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    reason_code: Mapped[str] = mapped_column(
        String(80),
        default="operator_confirmed_not_committed",
        server_default=text("'operator_confirmed_not_committed'"),
        nullable=False,
    )
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

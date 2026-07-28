"""Add fixed staff roles, room-scoped access, and one-time auth challenges.

Revision ID: 0004_staff_access
Revises: 0003_program_license_types
Create Date: 2026-07-15
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "0004_staff_access"
down_revision = "0003_program_license_types"
branch_labels = None
depends_on = None

OWNER_PERMISSIONS = [
    "organization:manage",
    "facility:read",
    "facility:manage",
    "childcare:read",
    "childcare:manage",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
    "attendance:correct",
    "staff:manage",
    "staff:manage_educators",
    "audit:read",
    "settings:manage",
]
LEGACY_OWNER_PERMISSIONS = [
    "organization:manage",
    "facility:manage",
    "childcare:manage",
    "attendance:manage",
    "settings:manage",
]
ADMINISTRATOR_PERMISSIONS = [
    "facility:read",
    "facility:manage",
    "childcare:read",
    "childcare:manage",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
    "attendance:correct",
    "staff:manage_educators",
]
EDUCATOR_PERMISSIONS = [
    "facility:read",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
]


def _set_rls(table_names: tuple[str, ...], *, enabled: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in table_names:
        action = "ENABLE" if enabled else "DISABLE"
        op.execute(f'ALTER TABLE "{table_name}" {action} ROW LEVEL SECURITY')
        if enabled:
            op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')


def _create_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    org_setting = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for table_name in (
        "membership_room_assignments",
        "staff_invitation_rooms",
        "staff_invitations",
        "password_reset_challenges",
    ):
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_tenant" ON "{table_name}" '
            f"USING (organization_id = {org_setting}) "
            f"WITH CHECK (organization_id = {org_setting})"
        )


def _seed_roles() -> None:
    bind = op.get_bind()
    _set_rls(("organizations", "roles"), enabled=False)
    try:
        roles = sa.table(
            "roles",
            sa.column("id", sa.Uuid()),
            sa.column("organization_id", sa.Uuid()),
            sa.column("key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("permissions", sa.JSON()),
            sa.column("is_system", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        organizations = sa.table("organizations", sa.column("id", sa.Uuid()))
        now = datetime.now(UTC)
        organization_ids = list(bind.execute(sa.select(organizations.c.id)).scalars())
        existing_rows = list(
            bind.execute(sa.select(roles.c.organization_id, roles.c.key, roles.c.id)).mappings()
        )
        existing = {(row["organization_id"], row["key"]) for row in existing_rows}
        bind.execute(
            roles.update().where(roles.c.key == "owner").values(permissions=OWNER_PERMISSIONS)
        )
        rows: list[dict[str, object]] = []
        templates = (
            (
                "administrator",
                "Administrator",
                "Organization-wide operational access and educator administration",
                ADMINISTRATOR_PERMISSIONS,
            ),
            (
                "educator",
                "Educator",
                "Assigned-room care roster and attendance recording",
                EDUCATOR_PERMISSIONS,
            ),
        )
        for organization_id in organization_ids:
            for key, name, description, permissions in templates:
                if (organization_id, key) not in existing:
                    rows.append(
                        {
                            "id": uuid4(),
                            "organization_id": organization_id,
                            "key": key,
                            "name": name,
                            "description": description,
                            "permissions": permissions,
                            "is_system": True,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
        if rows:
            bind.execute(roles.insert(), rows)
    finally:
        _set_rls(("organizations", "roles"), enabled=True)


def _unseed_roles() -> None:
    """Restore the pre-0004 role data without deleting staff memberships."""

    bind = op.get_bind()
    _set_rls(("roles", "organization_memberships"), enabled=False)
    try:
        roles = sa.table(
            "roles",
            sa.column("id", sa.Uuid()),
            sa.column("organization_id", sa.Uuid()),
            sa.column("key", sa.String()),
            sa.column("permissions", sa.JSON()),
        )
        memberships = sa.table(
            "organization_memberships",
            sa.column("organization_id", sa.Uuid()),
            sa.column("role_id", sa.Uuid()),
        )
        bind.execute(
            roles.update()
            .where(roles.c.key == "owner")
            .values(permissions=LEGACY_OWNER_PERMISSIONS)
        )
        referenced_role = sa.exists(
            sa.select(1).where(
                memberships.c.organization_id == roles.c.organization_id,
                memberships.c.role_id == roles.c.id,
            )
        )
        bind.execute(
            roles.delete().where(
                roles.c.key.in_(("administrator", "educator")),
                ~referenced_role,
            )
        )
    finally:
        _set_rls(("roles", "organization_memberships"), enabled=True)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), server_default="1", nullable=False),
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint("ck_users_auth_version", "auth_version > 0")

    with op.batch_alter_table("rooms") as batch_op:
        batch_op.create_unique_constraint(
            "uq_rooms_org_facility_id", ["organization_id", "facility_id", "id"]
        )

    op.add_column("attendance_days", sa.Column("room_id", sa.Uuid(), nullable=True))
    _set_rls(("attendance_days", "enrollments"), enabled=False)
    try:
        attendance_days = sa.table(
            "attendance_days",
            sa.column("organization_id", sa.Uuid()),
            sa.column("enrollment_id", sa.Uuid()),
            sa.column("room_id", sa.Uuid()),
        )
        enrollments = sa.table(
            "enrollments",
            sa.column("organization_id", sa.Uuid()),
            sa.column("id", sa.Uuid()),
            sa.column("room_id", sa.Uuid()),
        )
        room_lookup = (
            sa.select(enrollments.c.room_id)
            .where(
                enrollments.c.organization_id == attendance_days.c.organization_id,
                enrollments.c.id == attendance_days.c.enrollment_id,
            )
            .scalar_subquery()
        )
        op.execute(attendance_days.update().values(room_id=room_lookup))
    finally:
        _set_rls(("attendance_days", "enrollments"), enabled=True)
    with op.batch_alter_table("attendance_days") as batch_op:
        batch_op.create_foreign_key(
            "fk_attendance_days_room_snapshot",
            "rooms",
            ["organization_id", "facility_id", "room_id"],
            ["organization_id", "facility_id", "id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_attendance_days_room_id", ["room_id"], unique=False)

    op.create_table(
        "membership_room_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_member_room_assignments_membership",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            name="fk_member_room_assignments_room",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_member_room_assignments_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "membership_id",
            "room_id",
            name="uq_member_room_assignments_membership_room",
        ),
    )
    for column in ("organization_id", "membership_id", "facility_id", "room_id"):
        op.create_index(
            op.f(f"ix_membership_room_assignments_{column}"),
            "membership_room_assignments",
            [column],
            unique=False,
        )

    op.create_table(
        "staff_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "accepted_at IS NULL OR revoked_at IS NULL",
            name="ck_staff_invitations_single_terminal_state",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["roles.organization_id", "roles.id"],
            name="fk_staff_invitations_role",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_invitations_org_id"),
        sa.UniqueConstraint("token_hash", name="uq_staff_invitations_token_hash"),
    )
    for column in ("organization_id", "email"):
        op.create_index(
            op.f(f"ix_staff_invitations_{column}"),
            "staff_invitations",
            [column],
            unique=False,
        )

    op.create_table(
        "staff_invitation_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "invitation_id"],
            ["staff_invitations.organization_id", "staff_invitations.id"],
            name="fk_staff_invitation_rooms_invitation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            name="fk_staff_invitation_rooms_room",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "invitation_id",
            "room_id",
            name="uq_staff_invitation_rooms_invitation_room",
        ),
    )
    for column in ("organization_id", "invitation_id"):
        op.create_index(
            op.f(f"ix_staff_invitation_rooms_{column}"),
            "staff_invitation_rooms",
            [column],
            unique=False,
        )

    op.create_table(
        "password_reset_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR revoked_at IS NULL",
            name="ck_password_reset_challenges_single_terminal_state",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_password_reset_challenges_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_password_reset_challenges_org_id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_challenges_token_hash"),
    )
    for column in ("organization_id", "membership_id"):
        op.create_index(
            op.f(f"ix_password_reset_challenges_{column}"),
            "password_reset_challenges",
            [column],
            unique=False,
        )

    _create_rls()
    _seed_roles()


def downgrade() -> None:
    for table_name in (
        "password_reset_challenges",
        "staff_invitation_rooms",
        "staff_invitations",
        "membership_room_assignments",
    ):
        op.drop_table(table_name)
    _unseed_roles()
    with op.batch_alter_table("attendance_days") as batch_op:
        batch_op.drop_index("ix_attendance_days_room_id")
        batch_op.drop_constraint("fk_attendance_days_room_snapshot", type_="foreignkey")
        batch_op.drop_column("room_id")
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_constraint("uq_rooms_org_facility_id", type_="unique")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_auth_version", type_="check")
        batch_op.drop_column("auth_version")

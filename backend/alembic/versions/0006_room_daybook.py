"""Add assigned-room daily care records and immutable mutation history.

Revision ID: 0006_room_daybook
Revises: 0005_child_profile_photos
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_room_daybook"
down_revision = "0005_child_profile_photos"
branch_labels = None
depends_on = None

ROLE_PERMISSION_ADDITIONS = {
    "owner": (
        "care:read",
        "care:record",
        "care:correct",
        "care:void",
        "child_safety:read",
    ),
    "administrator": (
        "care:read",
        "care:record",
        "care:correct",
        "care:void",
        "child_safety:read",
    ),
    "educator": (
        "care:read",
        "care:record",
        "care:correct_own",
        "child_safety:read",
    ),
}


def _set_rls(table_names: tuple[str, ...], *, enabled: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in table_names:
        action = "ENABLE" if enabled else "DISABLE"
        op.execute(f'ALTER TABLE "{table_name}" {action} ROW LEVEL SECURITY')
        if enabled:
            op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')


def _update_system_role_permissions(*, add: bool) -> None:
    bind = op.get_bind()
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("permissions", sa.JSON()),
        sa.column("is_system", sa.Boolean()),
    )
    _set_rls(("roles",), enabled=False)
    try:
        rows = list(
            bind.execute(
                sa.select(roles.c.id, roles.c.key, roles.c.permissions).where(
                    roles.c.is_system.is_(True),
                    roles.c.key.in_(tuple(ROLE_PERMISSION_ADDITIONS)),
                )
            ).mappings()
        )
        all_added = {
            permission
            for additions in ROLE_PERMISSION_ADDITIONS.values()
            for permission in additions
        }
        for row in rows:
            current = list(row["permissions"] or [])
            if add:
                additions = ROLE_PERMISSION_ADDITIONS[str(row["key"])]
                updated = list(dict.fromkeys((*current, *additions)))
            else:
                updated = [permission for permission in current if permission not in all_added]
            bind.execute(
                roles.update().where(roles.c.id == row["id"]).values(permissions=updated)
            )
    finally:
        _set_rls(("roles",), enabled=True)


def _create_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    org_setting = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    op.execute('ALTER TABLE "daily_care_records" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "daily_care_records" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "daily_care_records_tenant" ON "daily_care_records" '
        f"USING (organization_id = {org_setting}) "
        f"WITH CHECK (organization_id = {org_setting})"
    )
    op.execute('ALTER TABLE "daily_care_record_events" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "daily_care_record_events" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "daily_care_record_events_select" '
        'ON "daily_care_record_events" FOR SELECT '
        f"USING (organization_id = {org_setting})"
    )
    op.execute(
        'CREATE POLICY "daily_care_record_events_insert" '
        'ON "daily_care_record_events" FOR INSERT '
        f"WITH CHECK (organization_id = {org_setting})"
    )


def upgrade() -> None:
    with op.batch_alter_table("attendance_days") as batch_op:
        batch_op.create_unique_constraint(
            "uq_attendance_days_care_identity",
            [
                "organization_id",
                "facility_id",
                "room_id",
                "child_id",
                "enrollment_id",
                "service_date",
                "id",
            ],
        )

    op.create_table(
        "daily_care_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_day_id", sa.Uuid(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("care_type", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "care_type IN ('feeding','diaper','toilet','sleep','mood','activity')",
            name="ck_daily_care_records_type",
        ),
        sa.CheckConstraint("version > 0", name="ck_daily_care_records_version"),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= occurred_at",
            name="ck_daily_care_records_time_order",
        ),
        sa.CheckConstraint(
            "care_type = 'sleep' OR ended_at IS NULL",
            name="ck_daily_care_records_end_only_for_sleep",
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL AND voided_by_user_id IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by_user_id IS NOT NULL AND "
            "void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_daily_care_records_void_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_daily_care_records_attendance_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_daily_care_records_org_id"),
    )
    for column in (
        "organization_id",
        "facility_id",
        "room_id",
        "child_id",
        "attendance_day_id",
        "service_date",
        "care_type",
    ):
        op.create_index(
            op.f(f"ix_daily_care_records_{column}"),
            "daily_care_records",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_daily_care_records_room_day_time",
        "daily_care_records",
        ["organization_id", "room_id", "service_date", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_daily_care_records_child_day",
        "daily_care_records",
        ["organization_id", "child_id", "service_date"],
        unique=False,
    )
    op.create_index(
        "uq_daily_care_records_open_sleep",
        "daily_care_records",
        ["organization_id", "attendance_day_id"],
        unique=True,
        postgresql_where=sa.text(
            "care_type = 'sleep' AND ended_at IS NULL AND voided_at IS NULL"
        ),
        sqlite_where=sa.text(
            "care_type = 'sleep' AND ended_at IS NULL AND voided_at IS NULL"
        ),
    )

    op.create_table(
        "daily_care_record_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("care_record_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "event_type IN "
            "('recorded','sleep_finished','corrected','voided','auto_finished_at_checkout')",
            name="ck_daily_care_record_events_type",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('corrected','voided') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_daily_care_record_events_reason",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "care_record_id"],
            ["daily_care_records.organization_id", "daily_care_records.id"],
            name="fk_daily_care_record_events_org_record",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_daily_care_record_events_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_daily_care_record_events_operation",
        ),
    )
    op.create_index(
        op.f("ix_daily_care_record_events_organization_id"),
        "daily_care_record_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_care_record_events_care_record_id"),
        "daily_care_record_events",
        ["care_record_id"],
        unique=False,
    )
    _create_rls()
    _update_system_role_permissions(add=True)


def downgrade() -> None:
    _update_system_role_permissions(add=False)
    op.drop_table("daily_care_record_events")
    op.drop_table("daily_care_records")
    with op.batch_alter_table("attendance_days") as batch_op:
        batch_op.drop_constraint("uq_attendance_days_care_identity", type_="unique")

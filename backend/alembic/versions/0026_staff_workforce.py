"""Add staff availability, leave, templates, and coverage planning.

Revision ID: 0026_staff_workforce
Revises: 0025_staff_rota
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_staff_workforce"
down_revision = "0025_staff_rota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("staff_scheduled_shifts") as batch:
        batch.add_column(sa.Column("availability_override_reason", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "ck_scheduled_shifts_availability_override",
            "availability_override_reason IS NULL OR "
            "length(trim(availability_override_reason)) > 0",
        )

    op.create_table(
        "staff_availability_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("windows", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_specified", sa.Boolean(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_availability_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_availability_facility",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_availability_org_id"),
        sa.UniqueConstraint(
            "organization_id", "membership_id", "facility_id", name="uq_staff_availability_scope"
        ),
        sa.CheckConstraint(
            "is_specified OR (json_array_length(windows) = 0 AND note IS NULL)",
            name="ck_staff_availability_tombstone",
        ),
    )
    for column in ("organization_id", "membership_id", "facility_id"):
        op.create_index(
            f"ix_staff_availability_profiles_{column}", "staff_availability_profiles", [column]
        )

    op.create_table(
        "staff_time_off_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_time_off_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_time_off_facility",
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_time_off_org_id"),
        sa.UniqueConstraint(
            "organization_id", "create_operation_id", name="uq_staff_time_off_create_operation"
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','declined','cancelled')",
            name="ck_staff_time_off_status",
        ),
        sa.CheckConstraint(
            "category IN ('vacation','sick','personal','medical','bereavement','unpaid','other')",
            name="ck_staff_time_off_category",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_staff_time_off_interval"),
        sa.CheckConstraint(
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
    )
    for column in ("organization_id", "membership_id", "facility_id", "status"):
        op.create_index(f"ix_staff_time_off_requests_{column}", "staff_time_off_requests", [column])
    op.create_index(
        "ix_staff_time_off_membership_window",
        "staff_time_off_requests",
        ["organization_id", "membership_id", "starts_at", "ends_at"],
    )
    op.create_index(
        "ix_staff_time_off_facility_window",
        "staff_time_off_requests",
        ["organization_id", "facility_id", "starts_at", "ends_at"],
    )

    op.create_table(
        "staff_shift_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_local", sa.Time(), nullable=False),
        sa.Column("end_local", sa.Time(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_templates_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_templates_room",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deactivated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_shift_templates_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_shift_templates_create_operation",
        ),
        sa.CheckConstraint(
            "weekday >= 0 AND weekday <= 6", name="ck_staff_shift_templates_weekday"
        ),
        sa.CheckConstraint("end_local > start_local", name="ck_staff_shift_templates_interval"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_staff_shift_templates_name"),
        sa.CheckConstraint(
            "(is_active AND deactivated_at IS NULL AND deactivated_by_user_id IS NULL) OR "
            "(NOT is_active AND deactivated_at IS NOT NULL "
            "AND deactivated_by_user_id IS NOT NULL)",
            name="ck_staff_shift_templates_lifecycle",
        ),
    )
    for column in ("organization_id", "facility_id", "room_id", "is_active"):
        op.create_index(f"ix_staff_shift_templates_{column}", "staff_shift_templates", [column])

    op.create_table(
        "staff_coverage_target_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("windows", sa.JSON(), nullable=False),
        sa.Column("is_specified", sa.Boolean(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_coverage_targets_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_coverage_targets_room",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_coverage_targets_org_id"),
        sa.CheckConstraint(
            "is_specified OR json_array_length(windows) = 0",
            name="ck_staff_coverage_targets_tombstone",
        ),
    )
    for column in ("organization_id", "facility_id", "room_id"):
        op.create_index(
            f"ix_staff_coverage_target_profiles_{column}",
            "staff_coverage_target_profiles",
            [column],
        )
    op.create_index(
        "uq_staff_coverage_targets_facility",
        "staff_coverage_target_profiles",
        ["organization_id", "facility_id"],
        unique=True,
        postgresql_where=sa.text("room_id IS NULL"),
        sqlite_where=sa.text("room_id IS NULL"),
    )
    op.create_index(
        "uq_staff_coverage_targets_room",
        "staff_coverage_target_profiles",
        ["organization_id", "facility_id", "room_id"],
        unique=True,
        postgresql_where=sa.text("room_id IS NOT NULL"),
        sqlite_where=sa.text("room_id IS NOT NULL"),
    )

    op.create_table(
        "staff_workforce_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_workforce_events_org_id"),
        sa.UniqueConstraint(
            "organization_id", "operation_id", name="uq_staff_workforce_events_operation"
        ),
        sa.CheckConstraint(
            "entity_type IN ('staff_availability','staff_time_off','staff_shift_template',"
            "'staff_coverage_target')",
            name="ck_staff_workforce_events_entity",
        ),
        sa.CheckConstraint(
            "event_type IN ('replaced','removed','requested','approved','declined','cancelled',"
            "'created','updated','deactivated')",
            name="ck_staff_workforce_events_type",
        ),
    )
    for column in ("organization_id", "entity_id"):
        op.create_index(f"ix_staff_workforce_events_{column}", "staff_workforce_events", [column])

    if bind.dialect.name != "postgresql":
        return
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    tables = (
        "staff_availability_profiles",
        "staff_time_off_requests",
        "staff_shift_templates",
        "staff_coverage_target_profiles",
        "staff_workforce_events",
    )
    for table_name in tables:
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_tenant" ON "{table_name}" '
            f"USING (organization_id = {organization}) "
            f"WITH CHECK (organization_id = {organization})"
        )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE
              staff_availability_profiles, staff_time_off_requests, staff_shift_templates,
              staff_coverage_target_profiles TO caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE staff_workforce_events TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.drop_table("staff_workforce_events")
    op.drop_table("staff_coverage_target_profiles")
    op.drop_table("staff_shift_templates")
    op.drop_table("staff_time_off_requests")
    op.drop_table("staff_availability_profiles")
    with op.batch_alter_table("staff_scheduled_shifts") as batch:
        batch.drop_constraint("ck_scheduled_shifts_availability_override", type_="check")
        batch.drop_column("availability_override_reason")

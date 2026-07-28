"""Add planned staff rota and planned-to-actual clock reconciliation.

Revision ID: 0025_staff_rota
Revises: 0024_push_realtime
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_staff_rota"
down_revision = "0024_push_realtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "staff_scheduled_shifts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_status", sa.String(30), nullable=False),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("proposed_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
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
            name="fk_scheduled_shifts_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shifts_room",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_scheduled_shifts_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_scheduled_shifts_create_operation",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','cancelled')",
            name="ck_scheduled_shifts_status",
        ),
        sa.CheckConstraint(
            "response_status IN "
            "('pending','acknowledged','declined','alternate_proposed')",
            name="ck_scheduled_shifts_response",
        ),
        sa.CheckConstraint(
            "scheduled_end_at > scheduled_start_at",
            name="ck_scheduled_shifts_interval",
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND published_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_scheduled_shifts_lifecycle",
        ),
        sa.CheckConstraint(
            "(response_status = 'alternate_proposed' AND proposed_start_at IS NOT NULL "
            "AND proposed_end_at IS NOT NULL AND proposed_end_at > proposed_start_at) OR "
            "(response_status <> 'alternate_proposed' AND proposed_start_at IS NULL "
            "AND proposed_end_at IS NULL)",
            name="ck_scheduled_shifts_proposal",
        ),
        sa.CheckConstraint(
            "(response_status = 'pending' AND responded_at IS NULL "
            "AND response_note IS NULL) OR "
            "(response_status <> 'pending' AND responded_at IS NOT NULL)",
            name="ck_scheduled_shifts_response_time",
        ),
    )
    for column in (
        "organization_id",
        "membership_id",
        "facility_id",
        "room_id",
        "status",
        "response_status",
    ):
        op.create_index(f"ix_staff_scheduled_shifts_{column}", "staff_scheduled_shifts", [column])
    op.create_index(
        "ix_scheduled_shifts_membership_window",
        "staff_scheduled_shifts",
        ["organization_id", "membership_id", "scheduled_start_at", "scheduled_end_at"],
    )
    op.create_index(
        "ix_scheduled_shifts_facility_window",
        "staff_scheduled_shifts",
        ["organization_id", "facility_id", "scheduled_start_at", "scheduled_end_at"],
    )
    op.create_table(
        "staff_scheduled_shift_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_shift_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "scheduled_shift_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_scheduled_shift_events_shift",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_scheduled_shift_events_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_scheduled_shift_events_operation",
        ),
        sa.CheckConstraint(
            "event_type IN "
            "('created','updated','published','cancelled','acknowledged','declined',"
            "'alternate_proposed','alternate_accepted','alternate_rejected')",
            name="ck_scheduled_shift_events_type",
        ),
    )
    op.create_index(
        "ix_staff_scheduled_shift_events_organization_id",
        "staff_scheduled_shift_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_staff_scheduled_shift_events_scheduled_shift_id",
        "staff_scheduled_shift_events",
        ["scheduled_shift_id"],
    )
    with op.batch_alter_table("staff_shifts") as batch:
        batch.add_column(sa.Column("scheduled_shift_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_staff_shifts_scheduled_shift",
            "staff_scheduled_shifts",
            ["organization_id", "scheduled_shift_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_staff_shifts_scheduled_shift_id", ["scheduled_shift_id"])
    op.create_index(
        "uq_staff_shifts_scheduled_link",
        "staff_shifts",
        ["organization_id", "scheduled_shift_id"],
        unique=True,
        postgresql_where=sa.text("scheduled_shift_id IS NOT NULL"),
        sqlite_where=sa.text("scheduled_shift_id IS NOT NULL"),
    )
    if bind.dialect.name != "postgresql":
        return
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for table_name in ("staff_scheduled_shifts", "staff_scheduled_shift_events"):
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
            GRANT SELECT, INSERT, UPDATE ON TABLE staff_scheduled_shifts
              TO caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE staff_scheduled_shift_events
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.drop_index("uq_staff_shifts_scheduled_link", table_name="staff_shifts")
    with op.batch_alter_table("staff_shifts") as batch:
        batch.drop_index("ix_staff_shifts_scheduled_shift_id")
        batch.drop_constraint("fk_staff_shifts_scheduled_shift", type_="foreignkey")
        batch.drop_column("scheduled_shift_id")
    op.drop_table("staff_scheduled_shift_events")
    op.drop_table("staff_scheduled_shifts")

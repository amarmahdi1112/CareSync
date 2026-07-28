"""Add recurring rota, open-shift exchange, substitute, and swap foundations.

Revision ID: 0027_staff_exchange
Revises: 0026_staff_workforce
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_staff_exchange"
down_revision = "0026_staff_workforce"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("staff_scheduled_shifts") as batch:
        batch.add_column(sa.Column("origin_type", sa.String(20), nullable=True))
        batch.add_column(sa.Column("origin_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("origin_occurrence_key", sa.String(200), nullable=True))
        batch.add_column(sa.Column("supersedes_schedule_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_scheduled_shifts_supersedes",
            "staff_scheduled_shifts",
            ["organization_id", "supersedes_schedule_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_origin_triplet",
            "(origin_type IS NULL AND origin_id IS NULL AND origin_occurrence_key IS NULL) OR "
            "(origin_type IS NOT NULL AND origin_id IS NOT NULL "
            "AND origin_occurrence_key IS NOT NULL "
            "AND length(trim(origin_occurrence_key)) > 0)",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_origin_type",
            "origin_type IS NULL OR origin_type IN ('rotation','open_shift','swap')",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_not_self_superseding",
            "supersedes_schedule_id IS NULL OR supersedes_schedule_id <> id",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_supersedes_origin",
            "supersedes_schedule_id IS NULL OR "
            "(origin_type IS NOT NULL AND origin_type IN ('open_shift','swap'))",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_rotation_not_replacement",
            "origin_type <> 'rotation' OR supersedes_schedule_id IS NULL",
        )
        batch.create_check_constraint(
            "ck_scheduled_shifts_swap_replacement",
            "origin_type <> 'swap' OR supersedes_schedule_id IS NOT NULL",
        )
    for column in ("origin_type", "origin_id", "supersedes_schedule_id"):
        op.create_index(f"ix_staff_scheduled_shifts_{column}", "staff_scheduled_shifts", [column])
    op.create_index(
        "uq_scheduled_shifts_origin_occurrence",
        "staff_scheduled_shifts",
        ["organization_id", "origin_type", "origin_id", "origin_occurrence_key"],
        unique=True,
        postgresql_where=sa.text("origin_type IS NOT NULL"),
        sqlite_where=sa.text("origin_type IS NOT NULL"),
    )
    op.create_index(
        "uq_scheduled_shifts_supersedes",
        "staff_scheduled_shifts",
        ["organization_id", "supersedes_schedule_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_schedule_id IS NOT NULL"),
        sqlite_where=sa.text("supersedes_schedule_id IS NOT NULL"),
    )

    op.create_table(
        "staff_rotation_patterns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cycle_length_weeks", sa.Integer(), nullable=False),
        sa.Column("anchor_week_start", sa.Date(), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("activation_operation_id", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("retirement_operation_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("retirement_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_rotation_patterns_facility",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retired_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_rotation_patterns_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_rotation_patterns_create_operation",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "name",
            "version",
            name="uq_staff_rotation_patterns_version",
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_staff_rotation_patterns_name"),
        sa.CheckConstraint("version > 0", name="ck_staff_rotation_patterns_version"),
        sa.CheckConstraint(
            "cycle_length_weeks >= 1 AND cycle_length_weeks <= 8",
            name="ck_staff_rotation_patterns_cycle",
        ),
        sa.CheckConstraint(
            "json_array_length(slots) >= 1 AND json_array_length(slots) <= 500",
            name="ck_staff_rotation_patterns_slots",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')",
            name="ck_staff_rotation_patterns_status",
        ),
        sa.CheckConstraint(
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
    for column in ("organization_id", "facility_id", "status"):
        op.create_index(f"ix_staff_rotation_patterns_{column}", "staff_rotation_patterns", [column])
    op.create_index(
        "uq_staff_rotation_patterns_active_name",
        "staff_rotation_patterns",
        ["organization_id", "facility_id", "name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "staff_substitute_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("is_specified", sa.Boolean(), nullable=False),
        sa.Column("is_opted_in", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_substitute_profiles_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_substitute_profiles_membership",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_substitute_profiles_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "membership_id",
            name="uq_staff_substitute_profiles_scope",
        ),
        sa.CheckConstraint(
            "is_specified OR (NOT is_opted_in AND note IS NULL)",
            name="ck_staff_substitute_profiles_tombstone",
        ),
    )
    for column in ("organization_id", "facility_id", "membership_id", "is_opted_in"):
        op.create_index(
            f"ix_staff_substitute_profiles_{column}", "staff_substitute_profiles", [column]
        )

    op.create_table(
        "staff_open_shifts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("result_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("post_operation_id", sa.Uuid(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_room",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_source_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "result_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shifts_result_schedule",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["filled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_open_shifts_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_open_shifts_create_operation",
        ),
        sa.CheckConstraint(
            "status IN ('draft','open','filled','cancelled')",
            name="ck_staff_open_shifts_status",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_staff_open_shifts_interval"),
        sa.CheckConstraint(
            "source_schedule_id IS NULL OR result_schedule_id IS NULL "
            "OR source_schedule_id <> result_schedule_id",
            name="ck_staff_open_shifts_distinct_schedules",
        ),
        sa.CheckConstraint(
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
    )
    for column in (
        "organization_id",
        "facility_id",
        "room_id",
        "status",
        "source_schedule_id",
        "result_schedule_id",
    ):
        op.create_index(f"ix_staff_open_shifts_{column}", "staff_open_shifts", [column])
    op.create_index(
        "ix_staff_open_shifts_facility_window",
        "staff_open_shifts",
        ["organization_id", "facility_id", "starts_at", "ends_at"],
    )
    op.create_index(
        "uq_staff_open_shifts_result_schedule",
        "staff_open_shifts",
        ["organization_id", "result_schedule_id"],
        unique=True,
        postgresql_where=sa.text("result_schedule_id IS NOT NULL"),
        sqlite_where=sa.text("result_schedule_id IS NOT NULL"),
    )
    op.create_index(
        "uq_staff_open_shifts_active_source",
        "staff_open_shifts",
        ["organization_id", "source_schedule_id"],
        unique=True,
        postgresql_where=sa.text("source_schedule_id IS NOT NULL AND status IN ('draft','open')"),
        sqlite_where=sa.text("source_schedule_id IS NOT NULL AND status IN ('draft','open')"),
    )

    op.create_table(
        "staff_open_shift_engagements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("open_shift_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_interest_id", sa.Uuid(), nullable=True),
        sa.Column("converted_offer_id", sa.Uuid(), nullable=True),
        sa.Column("result_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "open_shift_id"],
            ["staff_open_shifts.organization_id", "staff_open_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_open_shift",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_interest_id"],
            ["staff_open_shift_engagements.organization_id", "staff_open_shift_engagements.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_source_interest",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "converted_offer_id"],
            ["staff_open_shift_engagements.organization_id", "staff_open_shift_engagements.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_converted_offer",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "result_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_open_shift_engagements_result_schedule",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["terminal_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_open_shift_engagements_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_open_shift_engagements_create_operation",
        ),
        sa.CheckConstraint("kind IN ('interest','offer')", name="ck_staff_open_engagements_kind"),
        sa.CheckConstraint(
            "status IN ('pending','withdrawn','rejected','converted','superseded',"
            "'accepted','declined')",
            name="ck_staff_open_engagements_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND terminal_at IS NULL AND terminal_by_user_id IS NULL) OR "
            "(status <> 'pending' AND terminal_at IS NOT NULL "
            "AND terminal_by_user_id IS NOT NULL)",
            name="ck_staff_open_engagements_terminal",
        ),
        sa.CheckConstraint(
            "status <> 'pending' OR terminal_reason IS NULL",
            name="ck_staff_open_engagements_pending_reason",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_staff_open_engagements_expiry",
        ),
        sa.CheckConstraint(
            "source_interest_id IS NULL OR source_interest_id <> id",
            name="ck_staff_open_engagements_source_not_self",
        ),
        sa.CheckConstraint(
            "converted_offer_id IS NULL OR converted_offer_id <> id",
            name="ck_staff_open_engagements_result_not_self",
        ),
    )
    for column in (
        "organization_id",
        "open_shift_id",
        "membership_id",
        "kind",
        "status",
        "expires_at",
        "source_interest_id",
        "result_schedule_id",
    ):
        op.create_index(
            f"ix_staff_open_shift_engagements_{column}",
            "staff_open_shift_engagements",
            [column],
        )
    op.create_index(
        "uq_staff_open_engagements_pending",
        "staff_open_shift_engagements",
        ["organization_id", "open_shift_id", "membership_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_staff_open_engagements_source_interest",
        "staff_open_shift_engagements",
        ["organization_id", "source_interest_id"],
        unique=True,
        postgresql_where=sa.text("source_interest_id IS NOT NULL"),
        sqlite_where=sa.text("source_interest_id IS NOT NULL"),
    )
    op.create_index(
        "uq_staff_open_engagements_converted_offer",
        "staff_open_shift_engagements",
        ["organization_id", "converted_offer_id"],
        unique=True,
        postgresql_where=sa.text("converted_offer_id IS NOT NULL"),
        sqlite_where=sa.text("converted_offer_id IS NOT NULL"),
    )

    op.create_table(
        "staff_shift_swap_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requester_membership_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_membership_id", sa.Uuid(), nullable=False),
        sa.Column("requester_schedule_id", sa.Uuid(), nullable=False),
        sa.Column("requester_schedule_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counterparty_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("counterparty_schedule_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_replacement_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("counterparty_replacement_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("counterparty_response_note", sa.Text(), nullable=True),
        sa.Column("manager_decision_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("create_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counterparty_responded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("manager_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requester_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "counterparty_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requester_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "counterparty_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requester_replacement_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_requester_replacement",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "counterparty_replacement_schedule_id"],
            ["staff_scheduled_shifts.organization_id", "staff_scheduled_shifts.id"],
            ondelete="RESTRICT",
            name="fk_staff_shift_swaps_counterparty_replacement",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["counterparty_responded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["manager_decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_staff_shift_swaps_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "create_operation_id",
            name="uq_staff_shift_swaps_create_operation",
        ),
        sa.CheckConstraint("kind IN ('cover','trade')", name="ck_staff_shift_swaps_kind"),
        sa.CheckConstraint(
            "status IN ('pending_counterparty','pending_manager','approved','declined',"
            "'cancelled','rejected')",
            name="ck_staff_shift_swaps_status",
        ),
        sa.CheckConstraint(
            "requester_membership_id <> counterparty_membership_id",
            name="ck_staff_shift_swaps_distinct_memberships",
        ),
        sa.CheckConstraint(
            "(counterparty_responded_at IS NULL AND "
            "counterparty_responded_by_user_id IS NULL) OR "
            "(counterparty_responded_at IS NOT NULL AND "
            "counterparty_responded_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_counterparty_pair",
        ),
        sa.CheckConstraint(
            "(manager_decided_at IS NULL AND manager_decided_by_user_id IS NULL) OR "
            "(manager_decided_at IS NOT NULL AND manager_decided_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_manager_pair",
        ),
        sa.CheckConstraint(
            "(cancelled_at IS NULL AND cancelled_by_user_id IS NULL) OR "
            "(cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL)",
            name="ck_staff_shift_swaps_cancel_pair",
        ),
        sa.CheckConstraint(
            "counterparty_response_note IS NULL OR counterparty_responded_at IS NOT NULL",
            name="ck_staff_shift_swaps_counterparty_note_evidence",
        ),
        sa.CheckConstraint(
            "status <> 'declined' OR (counterparty_response_note IS NOT NULL "
            "AND length(trim(counterparty_response_note)) > 0)",
            name="ck_staff_shift_swaps_decline_reason",
        ),
        sa.CheckConstraint(
            "manager_decision_reason IS NULL OR manager_decided_at IS NOT NULL",
            name="ck_staff_shift_swaps_manager_reason_evidence",
        ),
        sa.CheckConstraint(
            "(kind = 'cover' AND counterparty_schedule_id IS NULL "
            "AND counterparty_schedule_updated_at IS NULL) OR "
            "(kind = 'trade' AND counterparty_schedule_id IS NOT NULL "
            "AND counterparty_schedule_updated_at IS NOT NULL "
            "AND counterparty_schedule_id <> requester_schedule_id)",
            name="ck_staff_shift_swaps_originals",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "status <> 'rejected' OR (manager_decision_reason IS NOT NULL "
            "AND length(trim(manager_decision_reason)) > 0)",
            name="ck_staff_shift_swaps_rejection_reason",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancellation_reason IS NOT NULL "
            "AND length(trim(cancellation_reason)) > 0) OR "
            "(status <> 'cancelled' AND cancellation_reason IS NULL)",
            name="ck_staff_shift_swaps_cancellation_reason",
        ),
    )
    for index_name, column in (
        ("ix_staff_shift_swaps_org", "organization_id"),
        ("ix_staff_shift_swaps_facility", "facility_id"),
        ("ix_staff_shift_swaps_kind", "kind"),
        ("ix_staff_shift_swaps_status", "status"),
        ("ix_staff_shift_swaps_requester_member", "requester_membership_id"),
        ("ix_staff_shift_swaps_counterparty_member", "counterparty_membership_id"),
        ("ix_staff_shift_swaps_requester_sched", "requester_schedule_id"),
        ("ix_staff_shift_swaps_counterparty_sched", "counterparty_schedule_id"),
        ("ix_staff_shift_swaps_requester_repl", "requester_replacement_schedule_id"),
        ("ix_staff_shift_swaps_counterparty_repl", "counterparty_replacement_schedule_id"),
    ):
        op.create_index(index_name, "staff_shift_swap_requests", [column])
    op.create_index(
        "ix_staff_shift_swaps_facility_status",
        "staff_shift_swap_requests",
        ["organization_id", "facility_id", "status"],
    )

    with op.batch_alter_table("staff_workforce_events") as batch:
        batch.drop_constraint("ck_staff_workforce_events_entity", type_="check")
        batch.drop_constraint("ck_staff_workforce_events_type", type_="check")
        batch.create_check_constraint(
            "ck_staff_workforce_events_entity",
            "entity_type IN ('staff_availability','staff_time_off','staff_shift_template',"
            "'staff_coverage_target','staff_rotation_pattern','staff_open_shift',"
            "'staff_open_shift_engagement','staff_substitute_profile','staff_shift_swap')",
        )
        batch.create_check_constraint(
            "ck_staff_workforce_events_type",
            "event_type IN ('replaced','removed','requested','approved','declined','cancelled',"
            "'created','updated','deactivated','activated','retired','generated','posted',"
            "'filled','interested','offered','withdrawn','rejected','converted','superseded',"
            "'accepted','counterparty_accepted')",
        )

    if bind.dialect.name != "postgresql":
        return
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    tables = (
        "staff_rotation_patterns",
        "staff_open_shifts",
        "staff_open_shift_engagements",
        "staff_substitute_profiles",
        "staff_shift_swap_requests",
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
              staff_rotation_patterns, staff_open_shifts, staff_open_shift_engagements,
              staff_substitute_profiles, staff_shift_swap_requests TO caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE staff_workforce_events TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    # Destructive downgrade policy: 0026 cannot represent exchange entity or
    # lifecycle event types. These immutable receipts describe projection
    # tables that are dropped below, so remove them before restoring the
    # narrower 0026 checks. Scheduled shifts themselves are preserved; only
    # their 0027 provenance columns are removed later in this downgrade.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 0026 already FORCEs tenant RLS on this ledger. The migration owner is
        # therefore subject to a missing ``app.current_organization_id`` and a
        # cross-tenant cleanup would otherwise see zero rows. Temporarily return
        # the table owner to PostgreSQL's normal owner bypass for this migration-
        # owned cleanup only; runtime RLS remains enabled and FORCE is restored
        # immediately after the 0026-compatible constraints are installed.
        op.execute("ALTER TABLE staff_workforce_events NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM staff_workforce_events WHERE entity_type IN ("
        "'staff_rotation_pattern','staff_open_shift','staff_open_shift_engagement',"
        "'staff_substitute_profile','staff_shift_swap')"
    )
    with op.batch_alter_table("staff_workforce_events") as batch:
        batch.drop_constraint("ck_staff_workforce_events_entity", type_="check")
        batch.drop_constraint("ck_staff_workforce_events_type", type_="check")
        batch.create_check_constraint(
            "ck_staff_workforce_events_entity",
            "entity_type IN ('staff_availability','staff_time_off','staff_shift_template',"
            "'staff_coverage_target')",
        )
        batch.create_check_constraint(
            "ck_staff_workforce_events_type",
            "event_type IN ('replaced','removed','requested','approved','declined','cancelled',"
            "'created','updated','deactivated')",
        )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE staff_workforce_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE staff_workforce_events FORCE ROW LEVEL SECURITY")

    op.drop_table("staff_shift_swap_requests")
    op.drop_table("staff_open_shift_engagements")
    op.drop_table("staff_open_shifts")
    op.drop_table("staff_substitute_profiles")
    op.drop_table("staff_rotation_patterns")

    op.drop_index("uq_scheduled_shifts_supersedes", table_name="staff_scheduled_shifts")
    op.drop_index("uq_scheduled_shifts_origin_occurrence", table_name="staff_scheduled_shifts")
    for column in ("supersedes_schedule_id", "origin_id", "origin_type"):
        op.drop_index(f"ix_staff_scheduled_shifts_{column}", table_name="staff_scheduled_shifts")
    with op.batch_alter_table("staff_scheduled_shifts") as batch:
        batch.drop_constraint("ck_scheduled_shifts_swap_replacement", type_="check")
        batch.drop_constraint("ck_scheduled_shifts_rotation_not_replacement", type_="check")
        batch.drop_constraint("ck_scheduled_shifts_supersedes_origin", type_="check")
        batch.drop_constraint("ck_scheduled_shifts_not_self_superseding", type_="check")
        batch.drop_constraint("ck_scheduled_shifts_origin_type", type_="check")
        batch.drop_constraint("ck_scheduled_shifts_origin_triplet", type_="check")
        batch.drop_constraint("fk_scheduled_shifts_supersedes", type_="foreignkey")
        batch.drop_column("supersedes_schedule_id")
        batch.drop_column("origin_occurrence_key")
        batch.drop_column("origin_id")
        batch.drop_column("origin_type")

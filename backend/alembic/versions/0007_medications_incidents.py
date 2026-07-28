"""Add written medication and internal incident workflows.

Revision ID: 0007_medications_incidents
Revises: 0006_room_daybook
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_medications_incidents"
down_revision = "0006_room_daybook"
branch_labels = None
depends_on = None

ROLE_PERMISSION_ADDITIONS = {
    "owner": (
        "medication:read",
        "medication:manage",
        "medication:record",
        "medication:correct",
        "medication:void",
        "incident:read",
        "incident:create",
        "incident:update",
        "incident:review",
        "incident:external_report",
    ),
    "administrator": (
        "medication:read",
        "medication:manage",
        "medication:record",
        "medication:correct",
        "medication:void",
        "incident:read",
        "incident:create",
        "incident:update",
        "incident:review",
        "incident:external_report",
    ),
    "educator": (
        "medication:read",
        "medication:record",
        "medication:correct_own",
        "incident:read",
        "incident:create",
        "incident:update_own",
    ),
}

PROJECTION_TABLES = (
    "medication_plans",
    "medication_administrations",
    "incident_records",
)
EVENT_TABLES = (
    "medication_plan_events",
    "medication_administration_events",
    "incident_record_events",
)


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
                updated = list(
                    dict.fromkeys((*current, *ROLE_PERMISSION_ADDITIONS[str(row["key"])]))
                )
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
    for table_name in PROJECTION_TABLES:
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_tenant" ON "{table_name}" '
            f"USING (organization_id = {org_setting}) "
            f"WITH CHECK (organization_id = {org_setting})"
        )
    for table_name in EVENT_TABLES:
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_select" ON "{table_name}" FOR SELECT '
            f"USING (organization_id = {org_setting})"
        )
        op.execute(
            f'CREATE POLICY "{table_name}_insert" ON "{table_name}" FOR INSERT '
            f"WITH CHECK (organization_id = {org_setting})"
        )


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "medication_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("medication_name", sa.String(length=255), nullable=False),
        sa.Column("dosage", sa.String(length=255), nullable=False),
        sa.Column("route", sa.String(length=30), nullable=False),
        sa.Column("label_directions", sa.Text(), nullable=False),
        sa.Column("scheduled_times", sa.JSON(), nullable=False),
        sa.Column("as_needed", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("medication_kind", sa.String(length=30), nullable=False),
        sa.Column("storage_method", sa.String(length=50), nullable=False),
        sa.Column("storage_instructions", sa.Text(), nullable=False),
        sa.Column("emergency_plan_reference", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("authorization_status", sa.String(length=30), nullable=False),
        sa.Column("authorization_guardian_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_guardian_name", sa.String(length=255), nullable=True),
        sa.Column("signed_authorization_reference", sa.String(length=255), nullable=True),
        sa.Column("authorization_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorization_valid_until", sa.Date(), nullable=True),
        sa.Column("authorization_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorization_verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorization_revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_revocation_reason", sa.Text(), nullable=True),
        sa.Column(
            "original_labelled_container_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("original_labelled_container_verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("label_directions_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label_directions_verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "route IN ('oral','topical','inhaled','injected','other')",
            name="ck_medication_plans_route",
        ),
        sa.CheckConstraint(
            "medication_kind IN ('non_emergency','emergency')",
            name="ck_medication_plans_kind",
        ),
        sa.CheckConstraint(
            "storage_method IN ('locked_inaccessible','emergency_accessible_per_plan')",
            name="ck_medication_plans_storage_method",
        ),
        sa.CheckConstraint(
            "(medication_kind = 'non_emergency' AND storage_method = 'locked_inaccessible' "
            "AND emergency_plan_reference IS NULL) OR "
            "(medication_kind = 'emergency' AND "
            "storage_method = 'emergency_accessible_per_plan' AND "
            "emergency_plan_reference IS NOT NULL AND "
            "length(trim(emergency_plan_reference)) > 0)",
            name="ck_medication_plans_storage_safety",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')", name="ck_medication_plans_status"
        ),
        sa.CheckConstraint(
            "authorization_status IN ('not_recorded','verified','revoked')",
            name="ck_medication_plans_authorization_status",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_medication_plan_dates"
        ),
        sa.CheckConstraint("version > 0", name="ck_medication_plans_version"),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "status <> 'active' OR (authorization_status = 'verified' "
            "AND original_labelled_container_verified_at IS NOT NULL "
            "AND original_labelled_container_verified_by_user_id IS NOT NULL "
            "AND label_directions_verified_at IS NOT NULL "
            "AND label_directions_verified_by_user_id IS NOT NULL)",
            name="ck_medication_plans_active_evidence",
        ),
        sa.CheckConstraint(
            "(archived_at IS NULL AND archived_by_user_id IS NULL AND archive_reason IS NULL) OR "
            "(status = 'archived' AND archived_at IS NOT NULL "
            "AND archived_by_user_id IS NOT NULL AND archive_reason IS NOT NULL "
            "AND length(trim(archive_reason)) > 0)",
            name="ck_medication_plans_archive_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_medication_plans_org_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            ondelete="RESTRICT",
            name="fk_medication_plans_org_child",
        ),
        *[
            sa.ForeignKeyConstraint([column], ["users.id"], ondelete="RESTRICT")
            for column in (
                "authorization_verified_by_user_id",
                "authorization_revoked_by_user_id",
                "original_labelled_container_verified_by_user_id",
                "label_directions_verified_by_user_id",
                "created_by_user_id",
                "archived_by_user_id",
            )
        ],
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_medication_plans_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "child_id",
            "id",
            name="uq_medication_plans_administration_identity",
        ),
    )
    for column in ("organization_id", "facility_id", "child_id", "status"):
        op.create_index(
            op.f(f"ix_medication_plans_{column}"), "medication_plans", [column]
        )
    op.create_index(
        "ix_medication_plans_child_facility_status",
        "medication_plans",
        ["organization_id", "child_id", "facility_id", "status"],
    )

    op.create_table(
        "medication_plan_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("medication_plan_id", sa.Uuid(), nullable=False),
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
            "event_type IN ('created','updated','authorization_verified',"
            "'authorization_revoked','activated','archived')",
            name="ck_medication_plan_events_type",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('updated','authorization_revoked','archived') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_plan_events_reason",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "medication_plan_id"],
            ["medication_plans.organization_id", "medication_plans.id"],
            ondelete="RESTRICT",
            name="fk_medication_plan_events_org_plan",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_medication_plan_events_org_id"),
        sa.UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_medication_plan_events_operation"
        ),
    )
    for column in ("organization_id", "medication_plan_id"):
        op.create_index(
            op.f(f"ix_medication_plan_events_{column}"),
            "medication_plan_events",
            [column],
        )

    op.create_table(
        "medication_administrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_day_id", sa.Uuid(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("medication_plan_id", sa.Uuid(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("scheduled_for", sa.Time(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("staff_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("staff_initials_snapshot", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "outcome IN ('administered','refused','omitted')",
            name="ck_medication_administrations_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'administered' AND amount IS NOT NULL "
            "AND length(trim(amount)) > 0 AND reason IS NULL) OR "
            "(outcome IN ('refused','omitted') AND amount IS NULL "
            "AND reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_administrations_outcome_evidence",
        ),
        sa.CheckConstraint("version > 0", name="ck_medication_administrations_version"),
        sa.CheckConstraint(
            "length(trim(staff_name_snapshot)) > 0 "
            "AND length(trim(staff_initials_snapshot)) > 0",
            name="ck_medication_administrations_staff_snapshot",
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL AND voided_by_user_id IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by_user_id IS NOT NULL "
            "AND void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_medication_administrations_void_evidence",
        ),
        sa.ForeignKeyConstraint(
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
            ondelete="RESTRICT",
            name="fk_medication_administrations_attendance_identity",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["voided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_medication_administrations_org_id"
        ),
    )
    for column in (
        "organization_id",
        "facility_id",
        "room_id",
        "child_id",
        "attendance_day_id",
        "service_date",
        "medication_plan_id",
        "outcome",
    ):
        op.create_index(
            op.f(f"ix_medication_administrations_{column}"),
            "medication_administrations",
            [column],
        )
    op.create_index(
        "ix_medication_administrations_room_day_time",
        "medication_administrations",
        ["organization_id", "room_id", "service_date", "occurred_at"],
    )
    op.create_index(
        "uq_medication_administrations_schedule_slot",
        "medication_administrations",
        ["organization_id", "medication_plan_id", "service_date", "scheduled_for"],
        unique=True,
        postgresql_where=sa.text("scheduled_for IS NOT NULL AND voided_at IS NULL"),
        sqlite_where=sa.text("scheduled_for IS NOT NULL AND voided_at IS NULL"),
    )

    op.create_table(
        "medication_administration_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("medication_administration_id", sa.Uuid(), nullable=False),
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
            "event_type IN ('recorded','corrected','voided')",
            name="ck_medication_administration_events_type",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('corrected','voided') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_medication_administration_events_reason",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "medication_administration_id"],
            ["medication_administrations.organization_id", "medication_administrations.id"],
            ondelete="RESTRICT",
            name="fk_medication_administration_events_org_record",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_medication_administration_events_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_medication_administration_events_operation",
        ),
    )
    for column in ("organization_id", "medication_administration_id"):
        op.create_index(
            op.f(f"ix_medication_administration_events_{column}"),
            "medication_administration_events",
            [column],
        )

    op.create_table(
        "incident_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=True),
        sa.Column("enrollment_id", sa.Uuid(), nullable=True),
        sa.Column("attendance_day_id", sa.Uuid(), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("immediate_actions", sa.Text(), nullable=False),
        sa.Column("medical_attention", sa.String(length=40), nullable=False),
        sa.Column("parent_notification_status", sa.String(length=40), nullable=False),
        sa.Column("parent_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_notification_notes", sa.Text(), nullable=True),
        sa.Column("authorities_contacted", sa.JSON(), nullable=False),
        sa.Column("staff_present", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reportability_assessment", sa.String(length=30), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("external_report_status", sa.String(length=30), nullable=False),
        sa.Column("external_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_confirmation_reference", sa.String(length=255), nullable=True),
        sa.Column("external_submission_channel", sa.String(length=60), nullable=True),
        sa.Column("external_submitted_by_name", sa.String(length=255), nullable=True),
        sa.Column("external_report_recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "category IN ('injury','illness','missing_child','unauthorized_release',"
            "'allegation','emergency','other')",
            name="ck_incident_records_category",
        ),
        sa.CheckConstraint(
            "severity IN ('minor','moderate','serious','critical')",
            name="ck_incident_records_severity",
        ),
        sa.CheckConstraint(
            "medical_attention IN ('none','first_aid','medical_practitioner','emergency_services')",
            name="ck_incident_records_medical_attention",
        ),
        sa.CheckConstraint(
            "parent_notification_status IN "
            "('pending','notified','unable_to_reach','not_applicable')",
            name="ck_incident_records_parent_notification_status",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "status IN ('draft','under_review','finalized')",
            name="ck_incident_records_status",
        ),
        sa.CheckConstraint(
            "reportability_assessment IN "
            "('unassessed','not_reportable','other_reportable','critical')",
            name="ck_incident_records_reportability",
        ),
        sa.CheckConstraint(
            "external_report_status IN ('not_assessed','not_required','pending','recorded')",
            name="ck_incident_records_external_status",
        ),
        sa.CheckConstraint(
            "(child_id IS NULL AND enrollment_id IS NULL AND attendance_day_id IS NULL) OR "
            "(child_id IS NOT NULL AND enrollment_id IS NOT NULL "
            "AND attendance_day_id IS NOT NULL)",
            name="ck_incident_records_child_attendance_pair",
        ),
        sa.CheckConstraint("version > 0", name="ck_incident_records_version"),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_incident_records_org_facility",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "room_id"],
            ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
            ondelete="RESTRICT",
            name="fk_incident_records_room_snapshot",
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
            ondelete="RESTRICT",
            name="fk_incident_records_attendance_identity",
        ),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["external_report_recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_incident_records_org_id"),
    )
    for column in (
        "organization_id",
        "facility_id",
        "room_id",
        "child_id",
        "attendance_day_id",
        "service_date",
        "category",
        "severity",
        "status",
        "external_report_status",
    ):
        op.create_index(op.f(f"ix_incident_records_{column}"), "incident_records", [column])
    op.create_index(
        "ix_incident_records_room_day_time",
        "incident_records",
        ["organization_id", "room_id", "service_date", "occurred_at"],
    )

    op.create_table(
        "incident_record_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("incident_record_id", sa.Uuid(), nullable=False),
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
            "event_type IN ('drafted','updated','submitted_for_review','returned_to_draft',"
            "'finalized','external_report_recorded')",
            name="ck_incident_record_events_type",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('updated','returned_to_draft','finalized') OR "
            "(reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_incident_record_events_reason",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "incident_record_id"],
            ["incident_records.organization_id", "incident_records.id"],
            ondelete="RESTRICT",
            name="fk_incident_record_events_org_record",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_incident_record_events_org_id"),
        sa.UniqueConstraint(
            "organization_id", "client_operation_id", name="uq_incident_record_events_operation"
        ),
    )
    for column in ("organization_id", "incident_record_id"):
        op.create_index(
            op.f(f"ix_incident_record_events_{column}"),
            "incident_record_events",
            [column],
        )

    _create_rls()
    _update_system_role_permissions(add=True)


def downgrade() -> None:
    _update_system_role_permissions(add=False)
    op.drop_table("incident_record_events")
    op.drop_table("incident_records")
    op.drop_table("medication_administration_events")
    op.drop_table("medication_administrations")
    op.drop_table("medication_plan_events")
    op.drop_table("medication_plans")

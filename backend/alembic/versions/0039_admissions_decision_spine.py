"""Add the administrator admissions decision spine.

Revision ID: 0039_admissions_decision_spine
Revises: 0038_public_job_catalog_outbox
Create Date: 2026-07-23

The revision is deliberately additive. It creates no application or decision
for retained Family, Child, or Enrollment rows.
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision = "0039_admissions_decision_spine"
down_revision = "0038_public_job_catalog_outbox"
branch_labels = None
depends_on = None

TABLES = (
    "admission_applications",
    "admission_application_preferences",
    "admission_waitlist_entries",
    "admission_offers",
    "admission_conversion_links",
    "admission_application_events",
)
ADMISSION_TARGETS = (
    "admission_application",
    "admission_waitlist",
    "admission_offer",
)
ADMISSION_PERMISSIONS = (
    "admissions:read",
    "admissions:manage",
    "admissions:decide",
)
_DOWNGRADE_DEPENDENCY_TABLES = (
    "childcare_command_receipts",
    "realtime_events",
    "user_notifications",
)
_RECEIPT_TARGETS_0038 = (
    "'family','child','enrollment','authority_person','authority_evidence',"
    "'authority_evidence_object','release_authorization','release_rule',"
    "'consent','release_activation','attendance_release'"
)
_RECEIPT_TARGETS_0039 = (
    _RECEIPT_TARGETS_0038
    + ",'admission_application','admission_waitlist','admission_offer'"
)

# Freeze every table locally. No current ORM model is imported by historical DDL.
_metadata = sa.MetaData()
sa.Table(
    "organizations",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
)
sa.Table(
    "users",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
)
sa.Table(
    "facilities",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint("organization_id", "id", name="uq_facilities_org_id_id"),
)
sa.Table(
    "facility_programs",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "facility_id",
        "id",
        name="uq_programs_org_facility_id",
    ),
)
sa.Table(
    "families",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint("organization_id", "id", name="uq_families_org_id_id"),
)
sa.Table(
    "children",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint("organization_id", "id", name="uq_children_org_id_id"),
)
sa.Table(
    "enrollments",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint("organization_id", "id", name="uq_enrollments_org_id_id"),
)

APPLICATIONS = sa.Table(
    "admission_applications",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column(
        "organization_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("reference", sa.String(16), nullable=False),
    sa.Column(
        "source",
        sa.String(40),
        nullable=False,
        server_default=sa.text("'administrator_entry'"),
    ),
    sa.Column(
        "status", sa.String(30), nullable=False, server_default=sa.text("'draft'")
    ),
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column("child_first_name", sa.String(100), nullable=False),
    sa.Column("child_last_name", sa.String(100), nullable=False),
    sa.Column("child_normalized_name", sa.String(220), nullable=False),
    sa.Column("child_date_of_birth", sa.Date, nullable=False),
    sa.Column("contact_first_name", sa.String(100), nullable=False),
    sa.Column("contact_last_name", sa.String(100), nullable=False),
    sa.Column("contact_relationship", sa.String(100), nullable=False),
    sa.Column("contact_email", sa.String(320)),
    sa.Column("contact_normalized_email", sa.String(320)),
    sa.Column("contact_telephone", sa.String(30)),
    sa.Column("contact_normalized_telephone", sa.String(30)),
    sa.Column("internal_note", sa.Text),
    sa.Column(
        "created_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("created_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("last_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("review_started_at", sa.DateTime(timezone=True)),
    sa.Column("terminal_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_admission_applications_org_id"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "reference",
        name="uq_admission_applications_org_reference",
    ),
    sa.CheckConstraint(
        "source = 'administrator_entry'", name="ck_admission_applications_source"
    ),
    sa.CheckConstraint(
        "status IN ('draft','submitted','under_review','waitlisted','offered',"
        "'accepted','declined','withdrawn')",
        name="ck_admission_applications_status",
    ),
    sa.CheckConstraint("version > 0", name="ck_admission_applications_version"),
    sa.CheckConstraint(
        "(status = 'draft' AND submitted_at IS NULL) OR "
        "(status <> 'draft' AND submitted_at IS NOT NULL)",
        name="ck_admission_applications_submission",
    ),
    sa.CheckConstraint(
        "(status IN ('accepted','declined','withdrawn') AND terminal_at IS NOT NULL) "
        "OR (status NOT IN ('accepted','declined','withdrawn') AND terminal_at IS NULL)",
        name="ck_admission_applications_terminal",
    ),
)

PREFERENCES = sa.Table(
    "admission_application_preferences",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("rank", sa.Integer, nullable=False),
    sa.Column("current_rank", sa.Integer),
    sa.Column("current_lane_key", sa.String(80)),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("program_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("requested_start_date", sa.Date, nullable=False),
    sa.Column("application_version", sa.Integer, nullable=False),
    sa.Column(
        "created_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("created_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "retired_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
    ),
    sa.Column("retired_operation_id", sa.Uuid(as_uuid=True)),
    sa.Column("retired_at", sa.DateTime(timezone=True)),
    sa.ForeignKeyConstraint(
        ["organization_id", "application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_preferences_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id"],
        ["facilities.organization_id", "facilities.id"],
        ondelete="RESTRICT",
        name="fk_admission_preferences_facility",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id", "program_id"],
        [
            "facility_programs.organization_id",
            "facility_programs.facility_id",
            "facility_programs.id",
        ],
        ondelete="RESTRICT",
        name="fk_admission_preferences_program",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_admission_preferences_org_id"
    ),
    sa.CheckConstraint("rank > 0", name="ck_admission_preferences_rank"),
    sa.CheckConstraint(
        "application_version > 0",
        name="ck_admission_preferences_application_version",
    ),
    sa.CheckConstraint(
        "(retired_at IS NULL AND retired_by_user_id IS NULL "
        "AND retired_operation_id IS NULL AND current_rank = rank "
        "AND current_lane_key IS NOT NULL) OR "
        "(retired_at IS NOT NULL AND retired_by_user_id IS NOT NULL "
        "AND retired_operation_id IS NOT NULL AND current_rank IS NULL "
        "AND current_lane_key IS NULL)",
        name="ck_admission_preferences_current",
    ),
)

WAITLIST = sa.Table(
    "admission_waitlist_entries",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("current_application_id", sa.Uuid(as_uuid=True)),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("program_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("requested_start_date", sa.Date, nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column(
        "priority_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("closure_reason", sa.String(40)),
    sa.Column(
        "created_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("last_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_waitlist_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "current_application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_waitlist_current_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id", "program_id"],
        [
            "facility_programs.organization_id",
            "facility_programs.facility_id",
            "facility_programs.id",
        ],
        ondelete="RESTRICT",
        name="fk_admission_waitlist_program",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_admission_waitlist_org_id"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "current_application_id",
        name="uq_admission_waitlist_current_application",
    ),
    sa.CheckConstraint(
        "status IN ('active','offered','closed')",
        name="ck_admission_waitlist_status",
    ),
    sa.CheckConstraint("version > 0", name="ck_admission_waitlist_version"),
    sa.CheckConstraint(
        "closure_reason IS NULL OR closure_reason IN "
        "('facts_changed','review_reopened','application_declined',"
        "'application_withdrawn','offer_declined','application_accepted')",
        name="ck_admission_waitlist_closure_reason",
    ),
    sa.CheckConstraint(
        "(status IN ('active','offered') AND current_application_id = application_id "
        "AND closure_reason IS NULL AND closed_at IS NULL) OR "
        "(status = 'closed' AND current_application_id IS NULL "
        "AND closure_reason IS NOT NULL AND closed_at IS NOT NULL)",
        name="ck_admission_waitlist_current",
    ),
)

OFFERS = sa.Table(
    "admission_offers",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("open_application_id", sa.Uuid(as_uuid=True)),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("program_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("proposed_start_date", sa.Date, nullable=False),
    sa.Column("respond_by_date", sa.Date),
    sa.Column("prior_application_status", sa.String(30), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column(
        "issued_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("last_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column(
        "issued_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
    sa.Column("declined_at", sa.DateTime(timezone=True)),
    sa.Column("accepted_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_offers_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "open_application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_offers_open_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id", "program_id"],
        [
            "facility_programs.organization_id",
            "facility_programs.facility_id",
            "facility_programs.id",
        ],
        ondelete="RESTRICT",
        name="fk_admission_offers_program",
    ),
    sa.UniqueConstraint("organization_id", "id", name="uq_admission_offers_org_id"),
    sa.UniqueConstraint(
        "organization_id",
        "open_application_id",
        name="uq_admission_offers_open_application",
    ),
    sa.CheckConstraint(
        "status IN ('open','accepted','declined','withdrawn')",
        name="ck_admission_offers_status",
    ),
    sa.CheckConstraint(
        "prior_application_status IN ('under_review','waitlisted')",
        name="ck_admission_offers_prior_status",
    ),
    sa.CheckConstraint("version > 0", name="ck_admission_offers_version"),
    sa.CheckConstraint(
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

CONVERSIONS = sa.Table(
    "admission_conversion_links",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("offer_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("family_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("child_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("enrollment_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("resolution_mode", sa.String(40), nullable=False),
    sa.Column("acceptance_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("review_proof_digest", sa.String(64), nullable=False),
    sa.Column(
        "converted_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "converted_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_conversion_application",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "offer_id"],
        ["admission_offers.organization_id", "admission_offers.id"],
        ondelete="RESTRICT",
        name="fk_admission_conversion_offer",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "family_id"],
        ["families.organization_id", "families.id"],
        ondelete="RESTRICT",
        name="fk_admission_conversion_family",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "child_id"],
        ["children.organization_id", "children.id"],
        ondelete="RESTRICT",
        name="fk_admission_conversion_child",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "enrollment_id"],
        ["enrollments.organization_id", "enrollments.id"],
        ondelete="RESTRICT",
        name="fk_admission_conversion_enrollment",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_admission_conversion_org_id"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "application_id",
        name="uq_admission_conversion_application",
    ),
    sa.UniqueConstraint(
        "organization_id", "offer_id", name="uq_admission_conversion_offer"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "enrollment_id",
        name="uq_admission_conversion_enrollment",
    ),
    sa.CheckConstraint(
        "resolution_mode IN "
        "('create_family_and_child','reuse_family_create_child','reuse_child')",
        name="ck_admission_conversion_resolution",
    ),
    sa.CheckConstraint(
        "length(review_proof_digest) = 64",
        name="ck_admission_conversion_review_digest",
    ),
)

EVENTS = sa.Table(
    "admission_application_events",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("application_version", sa.Integer, nullable=False),
    sa.Column("command", sa.String(80), nullable=False),
    sa.Column("from_status", sa.String(30)),
    sa.Column("to_status", sa.String(30), nullable=False),
    sa.Column("reason_code", sa.String(40)),
    sa.Column(
        "actor_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("client_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column(
        "occurred_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "application_id"],
        ["admission_applications.organization_id", "admission_applications.id"],
        ondelete="RESTRICT",
        name="fk_admission_events_application",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_admission_events_org_id"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "application_id",
        "application_version",
        name="uq_admission_events_application_version",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "client_operation_id",
        name="uq_admission_events_operation",
    ),
    sa.CheckConstraint(
        "application_version > 0",
        name="ck_admission_events_application_version",
    ),
    sa.CheckConstraint(
        "to_status IN ('draft','submitted','under_review','waitlisted','offered',"
        "'accepted','declined','withdrawn')",
        name="ck_admission_events_to_status",
    ),
    sa.CheckConstraint(
        "from_status IS NULL OR from_status IN "
        "('draft','submitted','under_review','waitlisted','offered',"
        "'accepted','declined','withdrawn')",
        name="ck_admission_events_from_status",
    ),
)


def _set_receipt_target_vocabulary(*, include_admissions: bool) -> None:
    targets = _RECEIPT_TARGETS_0039 if include_admissions else _RECEIPT_TARGETS_0038
    bind = op.get_bind()
    sqlite_triggers: list[tuple[str, str]] = []
    if bind.dialect.name == "sqlite":
        sqlite_triggers = [
            (str(row.name), str(row.sql))
            for row in bind.execute(
                sa.text(
                    "SELECT name,sql FROM sqlite_master "
                    "WHERE type='trigger' AND sql IS NOT NULL "
                    "AND (tbl_name='childcare_command_receipts' "
                    "OR instr(lower(sql),'childcare_command_receipts') > 0) "
                    "ORDER BY name"
                )
            )
        ]
        # SQLite reparses every trigger when Alembic renames the replacement
        # table. Temporarily removing references avoids a false "no such table"
        # failure; the frozen trigger SQL is restored immediately afterward.
        for name, _sql in sqlite_triggers:
            quoted = name.replace('"', '""')
            op.execute(f'DROP TRIGGER "{quoted}"')
    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            f"target_type IN ({targets})",
        )
    for _name, sql in sqlite_triggers:
        op.execute(sql)


def _update_system_permissions(*, add: bool) -> None:
    bind = op.get_bind()
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("key", sa.String()),
        sa.column("permissions", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(roles.c.id, roles.c.permissions).where(
            roles.c.key.in_(("owner", "administrator"))
        )
    ).mappings()
    admission_permissions = set(ADMISSION_PERMISSIONS)
    for row in rows:
        raw = row["permissions"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        current = [str(value) for value in (raw or [])]
        if add:
            repaired = sorted(set(current).union(admission_permissions))
        else:
            repaired = [value for value in current if value not in admission_permissions]
        bind.execute(
            sa.update(roles).where(roles.c.id == row["id"]).values(permissions=repaired)
        )


def _set_postgres_role_rls(*, enabled: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    action = "ENABLE" if enabled else "DISABLE"
    op.execute(f"ALTER TABLE public.roles {action} ROW LEVEL SECURITY")
    if enabled:
        op.execute("ALTER TABLE public.roles FORCE ROW LEVEL SECURITY")


def _set_postgres_downgrade_force_rls(*, enabled: bool) -> None:
    """Make the all-tenant downgrade preflight visible to the migration owner.

    The migration role is intentionally NOBYPASSRLS.  Temporarily removing
    FORCE while holding ACCESS EXCLUSIVE locks lets the table owner inspect all
    tenants. PostgreSQL transactional DDL restores FORCE automatically when a
    populated downgrade raises and rolls back.
    """

    action = "FORCE" if enabled else "NO FORCE"
    for table in (*TABLES, *_DOWNGRADE_DEPENDENCY_TABLES):
        op.execute(f"ALTER TABLE public.{table} {action} ROW LEVEL SECURITY")


def _create_indexes() -> None:
    specs = {
        "admission_applications": (
            ("ix_admission_applications_organization_id", ("organization_id",), False),
            (
                "ix_admission_applications_org_status_updated",
                ("organization_id", "status", "updated_at"),
                False,
            ),
        ),
        "admission_application_preferences": (
            (
                "ix_admission_preferences_application",
                ("organization_id", "application_id"),
                False,
            ),
            (
                "uq_admission_preferences_current_rank",
                ("organization_id", "application_id", "current_rank"),
                True,
            ),
            (
                "uq_admission_preferences_current_lane",
                ("organization_id", "application_id", "current_lane_key"),
                True,
            ),
        ),
        "admission_waitlist_entries": (
            (
                "ix_admission_waitlist_lane_priority",
                ("organization_id", "facility_id", "program_id", "priority_at", "id"),
                False,
            ),
            (
                "ix_admission_waitlist_application",
                ("organization_id", "application_id"),
                False,
            ),
        ),
        "admission_offers": (
            (
                "ix_admission_offers_application",
                ("organization_id", "application_id"),
                False,
            ),
        ),
        "admission_conversion_links": (
            (
                "ix_admission_conversion_application",
                ("organization_id", "application_id"),
                False,
            ),
        ),
        "admission_application_events": (
            (
                "ix_admission_events_timeline",
                ("organization_id", "application_id", "application_version"),
                False,
            ),
        ),
    }
    for table_name, table_specs in specs.items():
        for name, columns, unique in table_specs:
            op.create_index(name, table_name, list(columns), unique=unique)


def _install_sqlite_guards() -> None:
    for table in ("admission_conversion_links", "admission_application_events"):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END"
            )
    op.execute(
        """
        CREATE TRIGGER admission_waitlist_priority_immutable
        BEFORE UPDATE OF priority_at ON admission_waitlist_entries
        WHEN NEW.priority_at <> OLD.priority_at
        BEGIN
          SELECT RAISE(ABORT, 'waitlist priority is immutable');
        END
        """
    )
    for table in (
        "admission_application_preferences",
        "admission_waitlist_entries",
        "admission_offers",
    ):
        for action in ("INSERT", "UPDATE"):
            trigger_name = f"{table}_active_program_{action.lower()}"
            update_columns = (
                " OF organization_id,facility_id,program_id" if action == "UPDATE" else ""
            )
            op.execute(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE {action}{update_columns} ON {table}
                WHEN NOT EXISTS (
                  SELECT 1 FROM facility_programs AS program
                  JOIN facilities AS facility
                    ON facility.organization_id=program.organization_id
                   AND facility.id=program.facility_id
                  WHERE program.organization_id=NEW.organization_id
                    AND program.facility_id=NEW.facility_id
                    AND program.id=NEW.program_id
                    AND program.is_active=1
                    AND facility.status='active'
                )
                BEGIN
                  SELECT RAISE(ABORT, 'admission lane must use an active program');
                END
                """
            )
    op.execute(
        """
        CREATE TRIGGER admission_conversion_insert_coherence
        BEFORE INSERT ON admission_conversion_links
        WHEN NOT EXISTS (
          SELECT 1
          FROM admission_applications AS application
          JOIN admission_offers AS offer
            ON offer.organization_id=application.organization_id
           AND offer.id=NEW.offer_id
           AND offer.application_id=application.id
          JOIN families AS family
            ON family.organization_id=application.organization_id
           AND family.id=NEW.family_id
          JOIN children AS child
            ON child.organization_id=application.organization_id
           AND child.id=NEW.child_id
           AND child.family_id=family.id
          JOIN enrollments AS enrollment
            ON enrollment.organization_id=application.organization_id
           AND enrollment.id=NEW.enrollment_id
           AND enrollment.child_id=child.id
           AND enrollment.facility_id=offer.facility_id
           AND enrollment.start_date=offer.proposed_start_date
          WHERE application.organization_id=NEW.organization_id
            AND application.id=NEW.application_id
            AND application.status='offered'
            AND offer.status='open'
            AND family.status='active'
            AND child.is_active=1
            AND enrollment.status='pending'
            AND enrollment.program_id IS NULL
            AND enrollment.room_id IS NULL
            AND enrollment.placement_effective_date IS NULL
        )
        BEGIN
          SELECT RAISE(ABORT, 'admission conversion is incoherent');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER admission_offer_acceptance_coherence
        BEFORE UPDATE OF status ON admission_offers
        WHEN NEW.status='accepted' AND OLD.status<>'accepted' AND NOT EXISTS (
          SELECT 1
          FROM admission_conversion_links AS conversion
          JOIN admission_applications AS application
            ON application.organization_id=conversion.organization_id
           AND application.id=conversion.application_id
          JOIN enrollments AS enrollment
            ON enrollment.organization_id=conversion.organization_id
           AND enrollment.id=conversion.enrollment_id
          WHERE conversion.organization_id=NEW.organization_id
            AND conversion.offer_id=NEW.id
            AND conversion.application_id=NEW.application_id
            AND application.status IN ('offered','accepted')
            AND enrollment.status='pending'
            AND enrollment.program_id IS NULL
            AND enrollment.room_id IS NULL
            AND enrollment.placement_effective_date IS NULL
        )
        BEGIN
          SELECT RAISE(ABORT, 'accepted admission offer requires conversion');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER admission_application_acceptance_coherence
        BEFORE UPDATE OF status ON admission_applications
        WHEN NEW.status='accepted' AND OLD.status<>'accepted' AND NOT EXISTS (
          SELECT 1
          FROM admission_conversion_links AS conversion
          JOIN admission_offers AS offer
            ON offer.organization_id=conversion.organization_id
           AND offer.id=conversion.offer_id
           AND offer.application_id=conversion.application_id
          JOIN families AS family
            ON family.organization_id=conversion.organization_id
           AND family.id=conversion.family_id
          JOIN children AS child
            ON child.organization_id=conversion.organization_id
           AND child.id=conversion.child_id
           AND child.family_id=family.id
          JOIN enrollments AS enrollment
            ON enrollment.organization_id=conversion.organization_id
           AND enrollment.id=conversion.enrollment_id
           AND enrollment.child_id=child.id
           AND enrollment.facility_id=offer.facility_id
           AND enrollment.start_date=offer.proposed_start_date
          WHERE conversion.organization_id=NEW.organization_id
            AND conversion.application_id=NEW.id
            AND offer.status='accepted'
            AND family.status='active'
            AND child.is_active=1
            AND enrollment.status='pending'
            AND enrollment.program_id IS NULL
            AND enrollment.room_id IS NULL
            AND enrollment.placement_effective_date IS NULL
        )
        BEGIN
          SELECT RAISE(ABORT, 'accepted admission application requires conversion');
        END
        """
    )


def _install_postgres_guards_rls_and_grants() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_immutable_fact() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        BEGIN
          RAISE EXCEPTION 'admission fact is immutable'
            USING ERRCODE='23514', CONSTRAINT='ck_admission_immutable_fact';
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_waitlist_priority_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        BEGIN
          IF NEW.priority_at IS DISTINCT FROM OLD.priority_at THEN
            RAISE EXCEPTION 'waitlist priority is immutable'
              USING ERRCODE='23514', CONSTRAINT='ck_admission_waitlist_priority_immutable';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_active_program_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
        AS $guard$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM public.facility_programs AS program
            JOIN public.facilities AS facility
              ON facility.organization_id=program.organization_id
             AND facility.id=program.facility_id
            WHERE program.organization_id=NEW.organization_id
              AND program.facility_id=NEW.facility_id
              AND program.id=NEW.program_id
              AND program.is_active
              AND facility.status='active'
          ) THEN
            RAISE EXCEPTION 'admission lane must use an active program'
              USING ERRCODE='23514', CONSTRAINT='ck_admission_active_program';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_conversion_coherence_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
        AS $guard$
        DECLARE application_key uuid;
        BEGIN
          IF TG_TABLE_NAME='admission_applications' THEN
            application_key := CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
          ELSE
            application_key := CASE
              WHEN TG_OP='DELETE' THEN OLD.application_id
              ELSE NEW.application_id
            END;
          END IF;
          IF EXISTS (
            SELECT 1
            FROM public.admission_applications AS application
            LEFT JOIN public.admission_conversion_links AS conversion
              ON conversion.organization_id=application.organization_id
             AND conversion.application_id=application.id
            LEFT JOIN public.admission_offers AS offer
              ON offer.organization_id=conversion.organization_id
             AND offer.id=conversion.offer_id
            LEFT JOIN public.families AS family
              ON family.organization_id=conversion.organization_id
             AND family.id=conversion.family_id
            LEFT JOIN public.children AS child
              ON child.organization_id=conversion.organization_id
             AND child.id=conversion.child_id
            LEFT JOIN public.enrollments AS enrollment
              ON enrollment.organization_id=conversion.organization_id
             AND enrollment.id=conversion.enrollment_id
            WHERE application.id=application_key
              AND (
                application.status='accepted'
                OR offer.status='accepted'
                OR conversion.id IS NOT NULL
              )
              AND NOT (
                application.status='accepted'
                AND conversion.id IS NOT NULL
                AND offer.id=conversion.offer_id
                AND offer.application_id=application.id
                AND offer.status='accepted'
                AND family.id=conversion.family_id
                AND family.status='active'
                AND child.id=conversion.child_id
                AND child.family_id=family.id
                AND child.is_active
                AND enrollment.id=conversion.enrollment_id
                AND enrollment.child_id=child.id
                AND enrollment.facility_id=offer.facility_id
                AND enrollment.start_date=offer.proposed_start_date
                AND enrollment.status='pending'
                AND enrollment.program_id IS NULL
                AND enrollment.room_id IS NULL
                AND enrollment.placement_effective_date IS NULL
              )
          ) THEN
            RAISE EXCEPTION 'admission conversion is incoherent'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_admission_conversion_coherence';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_command_row_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        DECLARE
          context_organization uuid := NULLIF(
            pg_catalog.current_setting(
              'app.current_organization_id', true
            ), ''
          )::uuid;
          context_user uuid := NULLIF(
            pg_catalog.current_setting('app.current_user_id', true), ''
          )::uuid;
          context_operation uuid := NULLIF(
            pg_catalog.current_setting(
              'app.current_childcare_operation_id', true
            ), ''
          )::uuid;
        BEGIN
          IF context_organization IS NULL
             OR context_user IS NULL
             OR context_operation IS NULL
             OR NEW.organization_id IS DISTINCT FROM context_organization THEN
            RAISE EXCEPTION 'admission command context is missing'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_admission_command_context';
          END IF;

          IF TG_TABLE_NAME='admission_applications' THEN
            IF TG_OP='INSERT' THEN
              IF NEW.version<>1
                 OR NEW.status<>'draft'
                 OR NEW.created_by_user_id IS DISTINCT FROM context_user
                 OR NEW.updated_by_user_id IS DISTINCT FROM context_user
                 OR NEW.created_operation_id IS DISTINCT FROM context_operation
                 OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
                RAISE EXCEPTION 'invalid admission application provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_application_provenance';
              END IF;
            ELSE
              IF NEW.id IS DISTINCT FROM OLD.id
                 OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                 OR NEW.reference IS DISTINCT FROM OLD.reference
                 OR NEW.source IS DISTINCT FROM OLD.source
                 OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                 OR NEW.created_operation_id IS DISTINCT FROM OLD.created_operation_id
                 OR NEW.created_at IS DISTINCT FROM OLD.created_at
                 OR NEW.version<>OLD.version+1
                 OR NEW.updated_by_user_id IS DISTINCT FROM context_user
                 OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
                RAISE EXCEPTION 'invalid admission application provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_application_provenance';
              END IF;
            END IF;
          ELSIF TG_TABLE_NAME='admission_application_preferences' THEN
            IF TG_OP='INSERT' THEN
              IF NEW.created_by_user_id IS DISTINCT FROM context_user
                 OR NEW.created_operation_id IS DISTINCT FROM context_operation
                 OR NEW.retired_at IS NOT NULL
                 OR NEW.retired_by_user_id IS NOT NULL
                 OR NEW.retired_operation_id IS NOT NULL
                 OR NEW.current_rank IS DISTINCT FROM NEW.rank
                 OR NEW.current_lane_key IS NULL THEN
                RAISE EXCEPTION 'invalid admission preference provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_preference_provenance';
              END IF;
            ELSE
              IF OLD.retired_at IS NOT NULL
                 OR NEW.retired_at IS NULL
                 OR NEW.retired_by_user_id IS DISTINCT FROM context_user
                 OR NEW.retired_operation_id IS DISTINCT FROM context_operation
                 OR NEW.current_rank IS NOT NULL
                 OR NEW.current_lane_key IS NOT NULL THEN
                RAISE EXCEPTION 'invalid admission preference provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_preference_provenance';
              END IF;
            END IF;
          ELSIF TG_TABLE_NAME='admission_waitlist_entries' THEN
            IF TG_OP='INSERT' THEN
              IF NEW.version<>1
                 OR NEW.status<>'active'
                 OR NEW.created_by_user_id IS DISTINCT FROM context_user
                 OR NEW.updated_by_user_id IS DISTINCT FROM context_user
                 OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
                RAISE EXCEPTION 'invalid admission waitlist provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_waitlist_provenance';
              END IF;
            ELSIF NEW.version<>OLD.version+1
               OR NEW.updated_by_user_id IS DISTINCT FROM context_user
               OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
              RAISE EXCEPTION 'invalid admission waitlist provenance'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_admission_waitlist_provenance';
            END IF;
          ELSIF TG_TABLE_NAME='admission_offers' THEN
            IF TG_OP='INSERT' THEN
              IF NEW.version<>1
                 OR NEW.status<>'open'
                 OR NEW.issued_by_user_id IS DISTINCT FROM context_user
                 OR NEW.updated_by_user_id IS DISTINCT FROM context_user
                 OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
                RAISE EXCEPTION 'invalid admission offer provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_admission_offer_provenance';
              END IF;
            ELSIF NEW.version<>OLD.version+1
               OR NEW.updated_by_user_id IS DISTINCT FROM context_user
               OR NEW.last_operation_id IS DISTINCT FROM context_operation THEN
              RAISE EXCEPTION 'invalid admission offer provenance'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_admission_offer_provenance';
            END IF;
          ELSIF TG_TABLE_NAME='admission_conversion_links' THEN
            IF NEW.converted_by_user_id IS DISTINCT FROM context_user
               OR NEW.acceptance_operation_id IS DISTINCT FROM context_operation THEN
              RAISE EXCEPTION 'invalid admission conversion provenance'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_admission_conversion_provenance';
            END IF;
          ELSIF TG_TABLE_NAME='admission_application_events' THEN
            IF NEW.actor_user_id IS DISTINCT FROM context_user
               OR NEW.client_operation_id IS DISTINCT FROM context_operation THEN
              RAISE EXCEPTION 'invalid admission event provenance'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_admission_event_provenance';
            END IF;
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0039_command_bundle_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
        AS $guard$
        DECLARE
          application_key uuid;
          organization_key uuid;
          operation_key uuid;
          current_application_version integer;
          application_operation uuid;
          inserted_preference_version integer;
        BEGIN
          organization_key := NEW.organization_id;
          IF TG_TABLE_NAME='admission_applications' THEN
            application_key := NEW.id;
            operation_key := NEW.last_operation_id;
          ELSIF TG_TABLE_NAME='admission_application_preferences' THEN
            application_key := NEW.application_id;
            operation_key := COALESCE(
              NEW.retired_operation_id, NEW.created_operation_id
            );
            IF TG_OP='INSERT' THEN
              inserted_preference_version := NEW.application_version;
            END IF;
          ELSIF TG_TABLE_NAME IN (
            'admission_waitlist_entries', 'admission_offers'
          ) THEN
            application_key := NEW.application_id;
            operation_key := NEW.last_operation_id;
          ELSIF TG_TABLE_NAME='admission_conversion_links' THEN
            application_key := NEW.application_id;
            operation_key := NEW.acceptance_operation_id;
          ELSE
            application_key := NEW.application_id;
            operation_key := NEW.client_operation_id;
          END IF;

          SELECT application.version, application.last_operation_id
          INTO current_application_version, application_operation
          FROM public.admission_applications AS application
          WHERE application.organization_id=organization_key
            AND application.id=application_key;
          IF NOT FOUND
             OR application_operation IS DISTINCT FROM operation_key
             OR inserted_preference_version IS NOT NULL
                AND inserted_preference_version<>current_application_version
             OR NULLIF(
                  pg_catalog.current_setting(
                    'app.current_childcare_operation_id', true
                  ), ''
                )::uuid IS DISTINCT FROM operation_key
             OR NOT EXISTS (
               SELECT 1
               FROM public.admission_application_events AS event
               JOIN public.childcare_command_receipts AS receipt
                 ON receipt.organization_id=event.organization_id
                AND receipt.client_operation_id=event.client_operation_id
                AND receipt.actor_user_id=event.actor_user_id
                AND receipt.command_type=event.command
               JOIN public.audit_events AS audit_event
                 ON audit_event.organization_id=receipt.organization_id
                AND audit_event.actor_user_id=receipt.actor_user_id
                AND audit_event.action=receipt.command_type
                AND audit_event.entity_type=receipt.target_type
                AND audit_event.entity_id=receipt.target_id
                AND audit_event.details->>'operation_id'=
                    receipt.client_operation_id::text
                AND audit_event.details->>'application_id'=
                    application_key::text
                AND audit_event.details->>'application_version'=
                    current_application_version::text
               JOIN public.realtime_events AS realtime_event
                 ON realtime_event.organization_id=receipt.organization_id
                AND realtime_event.entity_type=receipt.target_type
                AND realtime_event.entity_id=receipt.target_id
                AND realtime_event.payload->>'operation_id'=
                    receipt.client_operation_id::text
                AND realtime_event.payload->>'application_id'=
                    application_key::text
                AND realtime_event.payload->>'application_version'=
                    current_application_version::text
               WHERE event.organization_id=organization_key
                 AND event.application_id=application_key
                 AND event.application_version=current_application_version
                 AND event.client_operation_id=operation_key
                 AND receipt.target_type IN (
                   'admission_application',
                   'admission_waitlist',
                   'admission_offer'
                 )
                 AND receipt.outcome->>'application_id'=
                     application_key::text
                 AND (
                   (
                     receipt.target_type='admission_application'
                     AND receipt.target_id=application_key
                     AND receipt.committed_version=current_application_version
                   )
                   OR (
                     receipt.target_type='admission_waitlist'
                     AND EXISTS (
                       SELECT 1
                       FROM public.admission_waitlist_entries AS waitlist
                       WHERE waitlist.organization_id=organization_key
                         AND waitlist.application_id=application_key
                         AND waitlist.id=receipt.target_id
                         AND waitlist.version=receipt.committed_version
                     )
                   )
                   OR (
                     receipt.target_type='admission_offer'
                     AND EXISTS (
                       SELECT 1
                       FROM public.admission_offers AS offer
                       WHERE offer.organization_id=organization_key
                         AND offer.application_id=application_key
                         AND offer.id=receipt.target_id
                         AND offer.version=receipt.committed_version
                     )
                   )
                 )
             ) THEN
            RAISE EXCEPTION 'admission command bundle is incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_admission_command_bundle';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    for function in (
        "caresync_0039_immutable_fact()",
        "caresync_0039_waitlist_priority_guard()",
        "caresync_0039_active_program_guard()",
        "caresync_0039_conversion_coherence_guard()",
        "caresync_0039_command_row_guard()",
        "caresync_0039_command_bundle_guard()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function} FROM PUBLIC")
    for table in ("admission_conversion_links", "admission_application_events"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE "
            f"ON public.{table} FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_immutable_fact()"
        )
    op.execute(
        "CREATE TRIGGER admission_waitlist_priority_immutable "
        "BEFORE UPDATE OF priority_at ON public.admission_waitlist_entries "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0039_waitlist_priority_guard()"
    )
    for table in (
        "admission_application_preferences",
        "admission_waitlist_entries",
        "admission_offers",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_active_program "
            f"BEFORE INSERT OR UPDATE OF organization_id,facility_id,program_id "
            f"ON public.{table} FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_active_program_guard()"
        )
    for table in (
        "admission_applications",
        "admission_offers",
        "admission_conversion_links",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_conversion_coherence "
            f"AFTER INSERT OR UPDATE OR DELETE ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_conversion_coherence_guard()"
        )
    for table in (
        "admission_applications",
        "admission_application_preferences",
        "admission_waitlist_entries",
        "admission_offers",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_command_row "
            f"BEFORE INSERT OR UPDATE ON public.{table} FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_command_row_guard()"
        )
    for table in ("admission_conversion_links", "admission_application_events"):
        op.execute(
            f"CREATE TRIGGER {table}_command_row "
            f"BEFORE INSERT ON public.{table} FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_command_row_guard()"
        )
    for table in TABLES:
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_command_bundle "
            f"AFTER INSERT OR UPDATE ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0039_command_bundle_guard()"
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f'CREATE POLICY "{table}_tenant" ON public.{table} '
            "USING (organization_id = NULLIF("
            "pg_catalog.current_setting('app.current_organization_id', true),'')::uuid) "
            "WITH CHECK (organization_id = NULLIF("
            "pg_catalog.current_setting('app.current_organization_id', true),'')::uuid)"
        )
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE UPDATE ON TABLE
              public.admission_applications,
              public.admission_application_preferences,
              public.admission_waitlist_entries,
              public.admission_offers
            FROM caresync_basic_app;
            GRANT SELECT,INSERT ON TABLE
              public.admission_applications,
              public.admission_application_preferences,
              public.admission_waitlist_entries,
              public.admission_offers,
              public.admission_conversion_links,
              public.admission_application_events
            TO caresync_basic_app;
            GRANT UPDATE (
              status,
              version,
              child_first_name,
              child_last_name,
              child_normalized_name,
              child_date_of_birth,
              contact_first_name,
              contact_last_name,
              contact_relationship,
              contact_email,
              contact_normalized_email,
              contact_telephone,
              contact_normalized_telephone,
              internal_note,
              updated_by_user_id,
              last_operation_id,
              submitted_at,
              review_started_at,
              terminal_at,
              updated_at
            ) ON TABLE public.admission_applications
            TO caresync_basic_app;
            GRANT UPDATE (
              current_rank,
              current_lane_key,
              retired_by_user_id,
              retired_operation_id,
              retired_at
            ) ON TABLE public.admission_application_preferences
            TO caresync_basic_app;
            GRANT UPDATE (
              current_application_id,
              status,
              version,
              closure_reason,
              updated_by_user_id,
              last_operation_id,
              closed_at,
              updated_at
            ) ON TABLE public.admission_waitlist_entries
            TO caresync_basic_app;
            GRANT UPDATE (
              open_application_id,
              status,
              version,
              updated_by_user_id,
              last_operation_id,
              withdrawn_at,
              declined_at,
              accepted_at,
              updated_at
            ) ON TABLE public.admission_offers
            TO caresync_basic_app;
          END IF;
        END
        $grant$
        """
    )


def _dependent_rows_exist(bind: sa.engine.Connection) -> bool:
    if any(
        bind.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)"))
        for table in TABLES
    ):
        return True
    receipt_targets = ",".join(f"'{value}'" for value in ADMISSION_TARGETS)
    checks = (
        f"SELECT EXISTS (SELECT 1 FROM childcare_command_receipts "
        f"WHERE target_type IN ({receipt_targets}) LIMIT 1)",
        "SELECT EXISTS (SELECT 1 FROM realtime_events "
        "WHERE entity_type IN "
        "('admission_application','admission_waitlist','admission_offer') LIMIT 1)",
        "SELECT EXISTS (SELECT 1 FROM user_notifications "
        "WHERE action_entity_type='admission_application' LIMIT 1)",
    )
    return any(bool(bind.scalar(sa.text(statement))) for statement in checks)


def upgrade() -> None:
    for table in (
        APPLICATIONS,
        PREFERENCES,
        WAITLIST,
        OFFERS,
        CONVERSIONS,
        EVENTS,
    ):
        table.create(op.get_bind(), checkfirst=False)
    _create_indexes()
    _set_receipt_target_vocabulary(include_admissions=True)
    _set_postgres_role_rls(enabled=False)
    try:
        _update_system_permissions(add=True)
    finally:
        _set_postgres_role_rls(enabled=True)
    if op.get_bind().dialect.name == "postgresql":
        _install_postgres_guards_rls_and_grants()
    else:
        _install_sqlite_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "LOCK TABLE "
            + ",".join(f"public.{table}" for table in TABLES)
            + ",public.childcare_command_receipts,public.realtime_events,"
            "public.user_notifications IN ACCESS EXCLUSIVE MODE"
        )
        _set_postgres_downgrade_force_rls(enabled=False)
        op.execute("SET LOCAL row_security = off")
    if _dependent_rows_exist(bind):
        raise RuntimeError(
            "0039 downgrade refused: admissions history or dependent events exist"
        )
    if bind.dialect.name == "postgresql":
        _set_postgres_downgrade_force_rls(enabled=True)

    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(
                f"DROP TRIGGER {table}_command_bundle ON public.{table}"
            )
        for table in TABLES:
            op.execute(
                f"DROP TRIGGER {table}_command_row ON public.{table}"
            )
        for table in (
            "admission_applications",
            "admission_offers",
            "admission_conversion_links",
        ):
            op.execute(
                f"DROP TRIGGER {table}_conversion_coherence ON public.{table}"
            )
        for table in (
            "admission_application_preferences",
            "admission_waitlist_entries",
            "admission_offers",
        ):
            op.execute(f"DROP TRIGGER {table}_active_program ON public.{table}")
        op.execute(
            "DROP TRIGGER admission_waitlist_priority_immutable "
            "ON public.admission_waitlist_entries"
        )
        for table in ("admission_conversion_links", "admission_application_events"):
            op.execute(f"DROP TRIGGER {table}_immutable ON public.{table}")
        op.execute("DROP FUNCTION public.caresync_0039_active_program_guard()")
        op.execute("DROP FUNCTION public.caresync_0039_waitlist_priority_guard()")
        op.execute("DROP FUNCTION public.caresync_0039_immutable_fact()")
        op.execute(
            "DROP FUNCTION public.caresync_0039_conversion_coherence_guard()"
        )
        op.execute(
            "DROP FUNCTION public.caresync_0039_command_bundle_guard()"
        )
        op.execute(
            "DROP FUNCTION public.caresync_0039_command_row_guard()"
        )
    else:
        op.execute("DROP TRIGGER admission_application_acceptance_coherence")
        op.execute("DROP TRIGGER admission_offer_acceptance_coherence")
        op.execute("DROP TRIGGER admission_conversion_insert_coherence")
        for table in (
            "admission_application_preferences",
            "admission_waitlist_entries",
            "admission_offers",
        ):
            for action in ("insert", "update"):
                op.execute(f"DROP TRIGGER {table}_active_program_{action}")
        op.execute("DROP TRIGGER admission_waitlist_priority_immutable")
        for table in ("admission_conversion_links", "admission_application_events"):
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER {table}_no_{action}")

    _set_postgres_role_rls(enabled=False)
    try:
        _update_system_permissions(add=False)
    finally:
        _set_postgres_role_rls(enabled=True)
    _set_receipt_target_vocabulary(include_admissions=False)
    for table in reversed(
        (
            APPLICATIONS,
            PREFERENCES,
            WAITLIST,
            OFFERS,
            CONVERSIONS,
            EVENTS,
        )
    ):
        table.drop(bind, checkfirst=False)

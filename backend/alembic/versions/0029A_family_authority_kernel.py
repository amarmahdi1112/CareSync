"""Add the staged family-authority persistence kernel.

Revision ID: 0029A_family_authority_kernel
Revises: 0028_childcare_command_spine
Create Date: 2026-07-17

All new authority tables begin empty. This revision does not promote legacy
pickup/consent markers and does not activate release checkout.
"""

# Alembic keeps SQL check expressions as single string literals so generated
# schema comparisons remain stable and reviewable against the ORM contract.
# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

revision = "0029A_family_authority_kernel"
down_revision = "0028_childcare_command_spine"
branch_labels = None
depends_on = None


AUTHORITY_TABLES = (
    "family_authority_people",
    "family_authority_person_versions",
    "family_authority_evidence",
    "family_authority_evidence_assessments",
    "child_authority_heads",
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
    "attendance_release_snapshots",
)

AUTHORITY_TARGETS = (
    "authority_person",
    "authority_evidence",
    "release_authorization",
    "release_rule",
    "consent",
    "attendance_release",
)


def _lowercase_sha256_check(column_name: str) -> str:
    """Return the shallow portable portion of a server-owned digest check."""

    expression = (
        f"length({column_name}) = 64 AND {column_name} = lower({column_name}) "
        f"AND {column_name} NOT LIKE '% %'"
    )
    if op.get_bind().dialect.name == "sqlite":
        expression += f" AND {column_name} NOT GLOB '*[^0-9a-f]*'"
    return expression


def _opaque_storage_reference_check(column_name: str) -> str:
    """Return a portable allowlist and traversal check for private object keys."""

    expression = (
        f"{column_name} IS NULL OR (length({column_name}) BETWEEN 1 AND 500 "
        f"AND substr({column_name},1,1) NOT IN ('/','.') "
        f"AND {column_name} NOT LIKE '%//%' "
        f"AND {column_name} NOT IN ('.','..') "
        f"AND {column_name} NOT LIKE './%' AND {column_name} NOT LIKE '../%' "
        f"AND {column_name} NOT LIKE '%/./%' AND {column_name} NOT LIKE '%/../%' "
        f"AND {column_name} NOT LIKE '%/.' AND {column_name} NOT LIKE '%/..' "
        f"AND {column_name} NOT LIKE '%/')"
    )
    if op.get_bind().dialect.name == "sqlite":
        expression = expression[:-1] + (
            f" AND {column_name} NOT GLOB '*[^A-Za-z0-9._/-]*' "
            f"AND substr({column_name},1,1) GLOB '[A-Za-z0-9]')"
        )
    return expression


def _media_type_check(column_name: str) -> str:
    """Constrain evidence media to the formats supported by the private vault."""

    return (
        f"{column_name} IS NULL OR "
        f"{column_name} IN ('application/pdf','image/jpeg','image/png')"
    )


def _refuse_unsafe_sqlite_multirevision_downgrade(bind: sa.engine.Connection) -> None:
    """Keep SQLite's non-transactional DDL rollback staged at revision 0028."""

    if bind.dialect.name != "sqlite":
        return
    destination_revision = context.get_revision_argument()
    if destination_revision not in {down_revision, "-1"}:
        raise RuntimeError(
            "0029A SQLite downgrade refused before DDL: first downgrade exactly "
            "to 0028_childcare_command_spine, then start a separate downgrade command"
        )


def upgrade() -> None:
    # Add the composite parent identities before any same-family or exact
    # attendance foreign key can reference them. Batch mode keeps this path
    # portable to the disposable SQLite migration gates.
    for table_name, constraint_name, columns in (
        ("children", "uq_children_org_family_id", ["organization_id", "family_id", "id"]),
        (
            "guardians",
            "uq_guardians_org_family_id",
            ["organization_id", "family_id", "id"],
        ),
        (
            "emergency_contacts",
            "uq_contacts_org_family_id",
            ["organization_id", "family_id", "id"],
        ),
        (
            "attendance_days",
            "uq_attendance_days_release_identity",
            ["organization_id", "facility_id", "child_id", "id"],
        ),
        (
            "attendance_intervals",
            "uq_attendance_intervals_release_identity",
            ["organization_id", "attendance_day_id", "id"],
        ),
        (
            "attendance_events",
            "uq_attendance_events_release_identity",
            ["organization_id", "attendance_day_id", "id"],
        ),
    ):
        with op.batch_alter_table(table_name) as batch:
            batch.create_unique_constraint(constraint_name, columns)

    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            "target_type IN ('family','child','enrollment','authority_person',"
            "'authority_evidence','release_authorization','release_rule','consent',"
            "'attendance_release')",
        )

    # ### commands auto generated by Alembic - adjusted to the locked contract ###
    op.create_table(
        "family_authority_people",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("current_person_version_id", sa.Uuid(), nullable=True),
        sa.Column("source_guardian_id", sa.Uuid(), nullable=True),
        sa.Column("source_emergency_contact_id", sa.Uuid(), nullable=True),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_operation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'active' AND current_person_version_id IS NOT NULL AND retired_at IS NULL AND retired_operation_id IS NULL) OR (status = 'retired' AND current_person_version_id IS NULL AND retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
            name="ck_authority_people_lifecycle",
        ),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_authority_people_status"),
        sa.CheckConstraint(
            "source_guardian_id IS NULL OR source_emergency_contact_id IS NULL",
            name="ck_authority_people_one_source",
        ),
        sa.CheckConstraint("version > 0", name="ck_authority_people_version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_people_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "source_emergency_contact_id"],
            [
                "emergency_contacts.organization_id",
                "emergency_contacts.family_id",
                "emergency_contacts.id",
            ],
            name="fk_authority_people_contact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "source_guardian_id"],
            ["guardians.organization_id", "guardians.family_id", "guardians.id"],
            name="fk_authority_people_guardian",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            name="fk_authority_people_family",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "last_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_people_last_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "retired_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_people_retired_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "id",
            name="uq_authority_people_org_family_id",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_authority_people_org_id"),
    )
    op.create_index(
        "ix_authority_people_family_status",
        "family_authority_people",
        ["organization_id", "family_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_people_family_id"),
        "family_authority_people",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_people_organization_id"),
        "family_authority_people",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_authority_people_source_contact",
        "family_authority_people",
        ["organization_id", "family_id", "source_emergency_contact_id"],
        unique=True,
        postgresql_where=sa.text("source_emergency_contact_id IS NOT NULL"),
        sqlite_where=sa.text("source_emergency_contact_id IS NOT NULL"),
    )
    op.create_index(
        "uq_authority_people_source_guardian",
        "family_authority_people",
        ["organization_id", "family_id", "source_guardian_id"],
        unique=True,
        postgresql_where=sa.text("source_guardian_id IS NOT NULL"),
        sqlite_where=sa.text("source_guardian_id IS NOT NULL"),
    )
    op.create_table(
        "family_authority_person_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("preferred_name", sa.String(length=100), nullable=True),
        sa.Column("relationship_kind", sa.String(length=32), nullable=False),
        sa.Column("relationship_detail", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("primary_phone", sa.String(length=30), nullable=True),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_operation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(relationship_kind = 'other' AND relationship_detail IS NOT NULL AND length(trim(relationship_detail)) > 0) OR (relationship_kind <> 'other' AND relationship_detail IS NULL)",
            name="ck_authority_person_versions_relationship_detail",
        ),
        sa.CheckConstraint(
            "relationship_kind IN ('parent','legal_guardian','foster_parent','grandparent','adult_sibling','aunt_uncle','family_friend','caseworker','transport_provider','other')",
            name="ck_authority_person_versions_relationship",
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL AND closed_operation_id IS NULL) OR (closed_at IS NOT NULL AND closed_operation_id IS NOT NULL)",
            name="ck_authority_person_versions_closure",
        ),
        sa.CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="ck_authority_person_versions_names",
        ),
        sa.CheckConstraint(
            "(middle_name IS NULL OR length(trim(middle_name)) > 0) AND "
            "(preferred_name IS NULL OR length(trim(preferred_name)) > 0) AND "
            "(email IS NULL OR length(trim(email)) > 0) AND "
            "(primary_phone IS NULL OR length(trim(primary_phone)) > 0)",
            name="ck_authority_person_versions_optional_facts",
        ),
        sa.CheckConstraint("version_number > 0", name="ck_authority_person_versions_number"),
        sa.ForeignKeyConstraint(
            ["organization_id", "closed_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_person_versions_closed_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_person_versions_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_authority_person_versions_person",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "person_id",
            "id",
            name="uq_authority_person_versions_identity",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "person_id",
            "version_number",
            name="uq_authority_person_versions_number",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_person_versions_created_operation",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_authority_person_versions_org_id"),
    )
    op.create_index(
        op.f("ix_family_authority_person_versions_family_id"),
        "family_authority_person_versions",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_person_versions_organization_id"),
        "family_authority_person_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_person_versions_person_id"),
        "family_authority_person_versions",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "uq_authority_person_versions_open",
        "family_authority_person_versions",
        ["organization_id", "family_id", "person_id"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
        sqlite_where=sa.text("closed_at IS NULL"),
    )
    with op.batch_alter_table("family_authority_people") as batch:
        batch.create_foreign_key(
            "fk_authority_people_current_version",
            "family_authority_person_versions",
            ["organization_id", "family_id", "id", "current_person_version_id"],
            ["organization_id", "family_id", "person_id", "id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )
    op.create_table(
        "child_authority_heads",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("last_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("revision > 0", name="ck_child_authority_heads_revision"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_child_authority_heads_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            name="fk_child_authority_heads_child",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "last_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_child_authority_heads_last_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("child_id"),
        sa.UniqueConstraint(
            "organization_id", "child_id", name="uq_child_authority_heads_org_child"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "child_id",
            name="uq_child_authority_heads_org_family_child",
        ),
    )
    op.create_index(
        op.f("ix_child_authority_heads_family_id"),
        "child_authority_heads",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_authority_heads_organization_id"),
        "child_authority_heads",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "consent_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("purpose_code", sa.String(length=40), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("content_reference", sa.String(length=500), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("signer_authority_requirement", sa.String(length=40), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose_code IN ('off_site_activity','emergency_health_care','medication_administration','internal_media','external_media','marketing','research','optional_service','information_sharing')",
            name="ck_consent_policy_versions_purpose",
        ),
        sa.CheckConstraint(
            "signer_authority_requirement IN ('guardian_record','legal_decision_maker','specific_reviewed_authority')",
            name="ck_consent_policy_versions_signer",
        ),
        sa.CheckConstraint(
            "effective_until > effective_from", name="ck_consent_policy_versions_window"
        ),
        sa.CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_consent_policy_versions_sha256",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(content_reference)) > 0",
            name="ck_consent_policy_versions_content",
        ),
        sa.CheckConstraint(
            "version_number BETWEEN 1 AND 2147483647",
            name="ck_consent_policy_versions_number",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_consent_policy_versions_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_consent_policy_versions_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "purpose_code",
            "id",
            name="uq_consent_policy_versions_purpose_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "purpose_code",
            "version_number",
            name="uq_consent_policy_versions_number",
        ),
    )
    op.create_index(
        "ix_consent_policy_versions_lane",
        "consent_policy_versions",
        ["organization_id", "purpose_code", "effective_from", "effective_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_consent_policy_versions_organization_id"),
        "consent_policy_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_consent_policy_versions_purpose_code"),
        "consent_policy_versions",
        ["purpose_code"],
        unique=False,
    )
    op.create_table(
        "family_authority_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("source_label", sa.String(length=160), nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('identity_document','custody_document','court_order','guardian_attestation','signed_consent','staff_witness','other_document')",
            name="ck_authority_evidence_kind",
        ),
        sa.CheckConstraint(
            "(storage_reference IS NULL AND media_type IS NULL AND byte_size IS NULL AND content_sha256 IS NULL) OR (storage_reference IS NOT NULL AND media_type IS NOT NULL AND byte_size IS NOT NULL AND byte_size > 0 AND content_sha256 IS NOT NULL)",
            name="ck_authority_evidence_storage_tuple",
        ),
        sa.CheckConstraint(
            _opaque_storage_reference_check("storage_reference"),
            name="ck_authority_evidence_storage_reference",
        ),
        sa.CheckConstraint(
            _media_type_check("media_type"),
            name="ck_authority_evidence_media_type",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size BETWEEN 1 AND 52428800",
            name="ck_authority_evidence_byte_size",
        ),
        sa.CheckConstraint(
            "content_sha256 IS NULL OR (" + _lowercase_sha256_check("content_sha256") + ")",
            name="ck_authority_evidence_sha256",
        ),
        sa.CheckConstraint(
            "issued_at IS NULL OR expires_at IS NULL OR expires_at > issued_at",
            name="ck_authority_evidence_expiry",
        ),
        sa.CheckConstraint(
            "length(trim(source_label)) > 0", name="ck_authority_evidence_source_label"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_evidence_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            name="fk_authority_evidence_family",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recorded_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_authority_evidence_recorder_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "id",
            name="uq_authority_evidence_org_family_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_evidence_created_operation",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_authority_evidence_org_id"),
    )
    op.create_index(
        op.f("ix_family_authority_evidence_expires_at"),
        "family_authority_evidence",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_family_id"),
        "family_authority_evidence",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_organization_id"),
        "family_authority_evidence",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "family_authority_evidence_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("assessed_epistemic_status", sa.String(length=24), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=True),
        sa.Column("confidential_note", sa.Text(), nullable=True),
        sa.Column("superseded_by_evidence_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(version_number = 2 AND decision IN ('reviewed','rejected')) OR "
            "(version_number = 3 AND decision IN ('invalidated','superseded'))",
            name="ck_authority_evidence_assessments_transition",
        ),
        sa.CheckConstraint(
            "decision IN ('reviewed','rejected','invalidated','superseded')",
            name="ck_authority_evidence_assessments_decision",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "(reason_code = 'other' AND confidential_note IS NOT NULL AND "
            "length(trim(confidential_note)) BETWEEN 1 AND 1000) OR "
            "((reason_code IS NULL OR reason_code <> 'other') AND confidential_note IS NULL)",
            name="ck_authority_evidence_assessments_note",
        ),
        sa.CheckConstraint(
            "(decision = 'superseded' AND superseded_by_evidence_id IS NOT NULL AND "
            "superseded_by_evidence_id <> evidence_id) OR "
            "(decision <> 'superseded' AND superseded_by_evidence_id IS NULL)",
            name="ck_authority_evidence_assessments_supersession",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_authority_evidence_assessments_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_evidence_assessments_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            name="fk_authority_evidence_assessments_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "superseded_by_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            name="fk_authority_evidence_assessments_superseding_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_authority_evidence_assessments_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "evidence_id",
            "id",
            name="uq_authority_evidence_assessments_identity",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "evidence_id",
            "version_number",
            name="uq_authority_evidence_assessments_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "created_operation_id",
            name="uq_authority_evidence_assessments_created_operation",
        ),
    )
    op.create_index(
        "ix_authority_evidence_assessments_current",
        "family_authority_evidence_assessments",
        ["organization_id", "evidence_id", "version_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_assessments_family_id"),
        "family_authority_evidence_assessments",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_assessments_organization_id"),
        "family_authority_evidence_assessments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_assessments_evidence_id"),
        "family_authority_evidence_assessments",
        ["evidence_id"],
        unique=False,
    )
    op.create_table(
        "child_consent_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("purpose_code", sa.String(length=40), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("signer_person_id", sa.Uuid(), nullable=False),
        sa.Column("signer_person_version_id", sa.Uuid(), nullable=False),
        sa.Column("signer_authority_basis", sa.String(length=40), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("scope_kind", sa.String(length=20), nullable=False),
        sa.Column("scope_facility_id", sa.Uuid(), nullable=True),
        sa.Column("scope_reference", sa.String(length=160), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_operation_id", sa.Uuid(), nullable=True),
        sa.Column("withdrawal_reason_code", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(scope_kind = 'policy' AND scope_facility_id IS NULL AND scope_reference IS NULL) OR (scope_kind = 'facility' AND scope_facility_id IS NOT NULL AND scope_reference IS NULL) OR (scope_kind = 'named_activity' AND scope_facility_id IS NULL AND scope_reference IS NOT NULL AND length(trim(scope_reference)) > 0)",
            name="ck_child_consent_decisions_scope_shape",
        ),
        sa.CheckConstraint(
            "(withdrawn_at IS NULL AND withdrawn_operation_id IS NULL AND withdrawal_reason_code IS NULL) OR (withdrawn_at IS NOT NULL AND withdrawn_operation_id IS NOT NULL AND withdrawal_reason_code IS NOT NULL AND withdrawal_reason_code IN ('signer_withdrew','authority_changed','superseded','entered_in_error'))",
            name="ck_child_consent_decisions_withdrawal",
        ),
        sa.CheckConstraint(
            "decision IN ('granted','declined')",
            name="ck_child_consent_decisions_decision",
        ),
        sa.CheckConstraint(
            "purpose_code IN ('off_site_activity','emergency_health_care','medication_administration','internal_media','external_media','marketing','research','optional_service','information_sharing')",
            name="ck_child_consent_decisions_purpose",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('policy','facility','named_activity')",
            name="ck_child_consent_decisions_scope_kind",
        ),
        sa.CheckConstraint(
            "signer_authority_basis IN ('guardian_record','reviewed_custody_evidence','reviewed_delegation_evidence','other_reviewed_authority')",
            name="ck_child_consent_decisions_signer_basis",
        ),
        sa.CheckConstraint(
            "effective_until > effective_from", name="ck_child_consent_decisions_window"
        ),
        sa.CheckConstraint("version > 0", name="ck_child_consent_decisions_version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_child_consent_decisions_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            name="fk_child_consent_decisions_child",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            name="fk_child_consent_decisions_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id", "evidence_assessment_id"],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            name="fk_child_consent_decisions_evidence_assessment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "signer_person_id",
                "signer_person_version_id",
            ],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            name="fk_child_consent_decisions_signer_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "signer_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_child_consent_decisions_signer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purpose_code", "policy_version_id"],
            [
                "consent_policy_versions.organization_id",
                "consent_policy_versions.purpose_code",
                "consent_policy_versions.id",
            ],
            name="fk_child_consent_decisions_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "scope_facility_id"],
            ["facilities.organization_id", "facilities.id"],
            name="fk_child_consent_decisions_facility",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "withdrawn_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_child_consent_decisions_withdrawn_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_child_consent_decisions_org_id"),
    )
    op.create_index(
        op.f("ix_child_consent_decisions_child_id"),
        "child_consent_decisions",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_consent_decisions_family_id"),
        "child_consent_decisions",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        "ix_child_consent_decisions_lane",
        "child_consent_decisions",
        [
            "organization_id",
            "child_id",
            "purpose_code",
            "effective_from",
            "effective_until",
        ],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_consent_decisions_organization_id"),
        "child_consent_decisions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_consent_decisions_withdrawn_at"),
        "child_consent_decisions",
        ["withdrawn_at"],
        unique=False,
    )
    op.create_table(
        "child_release_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_id", sa.Uuid(), nullable=False),
        sa.Column("verification_policy_code", sa.String(length=40), nullable=False),
        sa.Column("grantor_person_id", sa.Uuid(), nullable=False),
        sa.Column("grantor_person_version_id", sa.Uuid(), nullable=False),
        sa.Column("grantor_authority_basis", sa.String(length=40), nullable=False),
        sa.Column("basis_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("basis_evidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_operation_id", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason_code", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_operation_id IS NULL AND revocation_reason_code IS NULL) OR (revoked_at IS NOT NULL AND revoked_operation_id IS NOT NULL AND revocation_reason_code IS NOT NULL AND revocation_reason_code IN ('authority_withdrawn','safety_change','superseded','entered_in_error'))",
            name="ck_release_authorizations_revocation",
        ),
        sa.CheckConstraint(
            "grantor_authority_basis IN ('guardian_record','reviewed_custody_evidence','reviewed_delegation_evidence','other_reviewed_authority')",
            name="ck_release_authorizations_grantor_basis",
        ),
        sa.CheckConstraint(
            "verification_policy_code IN ('government_photo_id','documented_familiarity','government_photo_id_or_documented_familiarity','government_photo_id_and_secondary_check')",
            name="ck_release_authorizations_verification_policy",
        ),
        sa.CheckConstraint(
            "effective_until > effective_from", name="ck_release_authorizations_window"
        ),
        sa.CheckConstraint("version > 0", name="ck_release_authorizations_version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_authorizations_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "basis_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            name="fk_release_authorizations_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_release_authorizations_evidence_assessment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            name="fk_release_authorizations_child",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "organization_id",
                "family_id",
                "grantor_person_id",
                "grantor_person_version_id",
            ],
            [
                "family_authority_person_versions.organization_id",
                "family_authority_person_versions.family_id",
                "family_authority_person_versions.person_id",
                "family_authority_person_versions.id",
            ],
            name="fk_release_authorizations_grantor_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "grantor_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_release_authorizations_grantor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "recipient_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_release_authorizations_recipient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "revoked_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_authorizations_revoked_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "child_id",
            "recipient_person_id",
            "id",
            name="uq_release_authorizations_snapshot_identity",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_release_authorizations_org_id"),
    )
    op.create_index(
        op.f("ix_child_release_authorizations_child_id"),
        "child_release_authorizations",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_authorizations_family_id"),
        "child_release_authorizations",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_authorizations_organization_id"),
        "child_release_authorizations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_authorizations_recipient_person_id"),
        "child_release_authorizations",
        ["recipient_person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_authorizations_revoked_at"),
        "child_release_authorizations",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_release_authorizations_lane",
        "child_release_authorizations",
        [
            "organization_id",
            "child_id",
            "recipient_person_id",
            "effective_from",
            "effective_until",
        ],
        unique=False,
    )
    op.create_table(
        "child_release_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("rule_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_person_id", sa.Uuid(), nullable=True),
        sa.Column("directing_person_id", sa.Uuid(), nullable=True),
        sa.Column("directing_person_version_id", sa.Uuid(), nullable=True),
        sa.Column("authority_basis_code", sa.String(length=40), nullable=False),
        sa.Column("basis_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("basis_evidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("safe_explanation_code", sa.String(length=40), nullable=False),
        sa.Column("confidential_reason", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_operation_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_operation_id", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason_code", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_operation_id IS NULL AND revocation_reason_code IS NULL) OR (revoked_at IS NOT NULL AND revoked_operation_id IS NOT NULL AND revocation_reason_code IS NOT NULL AND revocation_reason_code IN ('authority_withdrawn','safety_change','superseded','entered_in_error'))",
            name="ck_release_rules_revocation",
        ),
        sa.CheckConstraint(
            "(rule_kind = 'deny' AND safe_explanation_code = 'release_restricted') OR (rule_kind = 'supervised_only' AND safe_explanation_code = 'supervision_required') OR (rule_kind = 'named_recipient_only' AND safe_explanation_code = 'named_recipient_only') OR (rule_kind = 'manager_review' AND safe_explanation_code = 'manager_review_required')",
            name="ck_release_rules_safe_code",
        ),
        sa.CheckConstraint(
            "(scope_kind = 'all_recipients' AND scope_person_id IS NULL) OR (scope_kind = 'specific_person' AND scope_person_id IS NOT NULL)",
            name="ck_release_rules_scope_shape",
        ),
        sa.CheckConstraint(
            "authority_basis_code IN ('guardian_record','reviewed_custody_evidence','reviewed_delegation_evidence','other_reviewed_authority')",
            name="ck_release_rules_authority_basis",
        ),
        sa.CheckConstraint(
            "rule_kind <> 'named_recipient_only' OR scope_kind = 'specific_person'",
            name="ck_release_rules_named_scope",
        ),
        sa.CheckConstraint(
            "rule_kind IN ('deny','supervised_only','named_recipient_only','manager_review')",
            name="ck_release_rules_kind",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('all_recipients','specific_person')",
            name="ck_release_rules_scope_kind",
        ),
        sa.CheckConstraint(
            "(directing_person_id IS NULL AND directing_person_version_id IS NULL) OR (directing_person_id IS NOT NULL AND directing_person_version_id IS NOT NULL)",
            name="ck_release_rules_directing_pair",
        ),
        sa.CheckConstraint("effective_until > effective_from", name="ck_release_rules_window"),
        sa.CheckConstraint("length(trim(confidential_reason)) > 0", name="ck_release_rules_reason"),
        sa.CheckConstraint("version > 0", name="ck_release_rules_version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_rules_created_op",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "basis_evidence_id"],
            [
                "family_authority_evidence.organization_id",
                "family_authority_evidence.family_id",
                "family_authority_evidence.id",
            ],
            name="fk_release_rules_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_release_rules_evidence_assessment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            name="fk_release_rules_child",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_release_rules_directing_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "directing_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_release_rules_directing_person",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "scope_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_release_rules_scope_person",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "revoked_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_rules_revoked_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_release_rules_org_id"),
    )
    op.create_index(
        op.f("ix_child_release_rules_child_id"),
        "child_release_rules",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_rules_family_id"),
        "child_release_rules",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_rules_organization_id"),
        "child_release_rules",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_rules_revoked_at"),
        "child_release_rules",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_release_rules_scope_person_id"),
        "child_release_rules",
        ["scope_person_id"],
        unique=False,
    )
    op.create_index(
        "ix_release_rules_lane",
        "child_release_rules",
        [
            "organization_id",
            "child_id",
            "rule_kind",
            "scope_kind",
            "scope_person_id",
            "effective_from",
            "effective_until",
        ],
        unique=False,
    )
    op.create_table(
        "attendance_release_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_day_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_interval_id", sa.Uuid(), nullable=False),
        sa.Column("checkout_event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_version_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_display_name", sa.String(length=240), nullable=False),
        sa.Column("recipient_relationship", sa.String(length=120), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_assessment_version", sa.Integer(), nullable=False),
        sa.Column("authority_revision", sa.Integer(), nullable=False),
        sa.Column("restriction_digest_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("verification_method", sa.String(length=40), nullable=False),
        sa.Column("verification_result", sa.String(length=16), nullable=False),
        sa.Column("evidence_digest_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("decision_policy_version", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("release_mode", sa.String(length=16), nullable=False),
        sa.Column("override_reason_code", sa.String(length=32), nullable=True),
        sa.Column("override_justification", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "release_mode = 'normal' AND override_reason_code IS NULL AND override_justification IS NULL",
            name="ck_release_snapshots_normal_only",
        ),
        sa.CheckConstraint(
            "verification_method IN ('government_photo_id','documented_familiarity','government_photo_id_and_secondary_check')",
            name="ck_release_snapshots_verification_method",
        ),
        sa.CheckConstraint(
            "verification_result IN ('verified','documented_familiarity')",
            name="ck_release_snapshots_verification_result",
        ),
        sa.CheckConstraint(
            "authorization_version > 0 AND authority_revision > 0 AND evidence_assessment_version = 2",
            name="ck_release_snapshots_versions",
        ),
        sa.CheckConstraint("committed_at >= requested_at", name="ck_release_snapshots_time_order"),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "attendance_day_id", "attendance_interval_id"],
            [
                "attendance_intervals.organization_id",
                "attendance_intervals.attendance_day_id",
                "attendance_intervals.id",
            ],
            name="fk_release_snapshots_interval_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "attendance_day_id", "checkout_event_id"],
            [
                "attendance_events.organization_id",
                "attendance_events.attendance_day_id",
                "attendance_events.id",
            ],
            name="fk_release_snapshots_event_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_release_snapshots_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "client_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_snapshots_operation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id", "child_id", "attendance_day_id"],
            [
                "attendance_days.organization_id",
                "attendance_days.facility_id",
                "attendance_days.child_id",
                "attendance_days.id",
            ],
            name="fk_release_snapshots_day_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            name="fk_release_snapshots_facility",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_release_snapshots_authorization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "child_id"],
            ["children.organization_id", "children.family_id", "children.id"],
            name="fk_release_snapshots_child",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_id", "evidence_assessment_id"],
            [
                "family_authority_evidence_assessments.organization_id",
                "family_authority_evidence_assessments.family_id",
                "family_authority_evidence_assessments.evidence_id",
                "family_authority_evidence_assessments.id",
            ],
            name="fk_release_snapshots_evidence_assessment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_release_snapshots_recipient_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "recipient_person_id"],
            [
                "family_authority_people.organization_id",
                "family_authority_people.family_id",
                "family_authority_people.id",
            ],
            name="fk_release_snapshots_recipient",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "attendance_interval_id",
            name="uq_release_snapshots_interval",
        ),
        sa.UniqueConstraint(
            "organization_id", "checkout_event_id", name="uq_release_snapshots_event"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_release_snapshots_operation",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_release_snapshots_org_id"),
    )
    op.create_index(
        op.f("ix_attendance_release_snapshots_child_id"),
        "attendance_release_snapshots",
        ["child_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_release_snapshots_facility_id"),
        "attendance_release_snapshots",
        ["facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_release_snapshots_family_id"),
        "attendance_release_snapshots",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_release_snapshots_organization_id"),
        "attendance_release_snapshots",
        ["organization_id"],
        unique=False,
    )
    # ### end Alembic commands ###

    if op.get_bind().dialect.name == "postgresql":
        _install_postgres_authority_guards()


def _install_postgres_authority_guards() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_insert_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          row_data jsonb;
          context_organization uuid;
          context_actor uuid;
          context_operation uuid;
          row_operation uuid;
          expected_target_type text;
          expected_target_id uuid;
          expected_committed_version integer;
          expected_action_route text;
          command_matches boolean;
          head_target_matches boolean;
          timestamp_key text;
          command_receipt public.childcare_command_receipts%ROWTYPE;
        BEGIN
          row_data := to_jsonb(NEW);

          -- PostgreSQL owns the finite-time invariant even for migration/restore
          -- sessions; infinity cannot be serialized safely across the API boundary.
          FOREACH timestamp_key IN ARRAY ARRAY[
            'created_at','updated_at','retired_at','closed_at','issued_at',
            'captured_at','expires_at','effective_from','effective_until',
            'revoked_at','published_at','withdrawn_at','requested_at','committed_at'
          ] LOOP
            IF row_data ? timestamp_key
               AND row_data ->> timestamp_key IS NOT NULL
               AND NOT isfinite((row_data ->> timestamp_key)::timestamptz) THEN
              RAISE EXCEPTION 'family authority timestamps must be finite'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_authority_timestamp_finite';
            END IF;
          END LOOP;

          -- PostgreSQL is the authoritative lowercase-hex guard. The portable
          -- checks also protect length/case, but do not pretend punctuation is hex.
          IF TG_TABLE_NAME = 'family_authority_evidence'
             AND row_data ->> 'content_sha256' IS NOT NULL
             AND row_data ->> 'content_sha256' !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'authority evidence digest is not lowercase hexadecimal'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_authority_evidence_sha256_hex';
          ELSIF TG_TABLE_NAME = 'consent_policy_versions'
             AND row_data ->> 'content_sha256' !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'consent policy digest is not lowercase hexadecimal'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_consent_policy_sha256_hex';
          ELSIF TG_TABLE_NAME = 'attendance_release_snapshots'
             AND (row_data ->> 'restriction_digest_sha256' !~ '^[0-9a-f]{64}$'
               OR row_data ->> 'evidence_digest_sha256' !~ '^[0-9a-f]{64}$'
               OR row_data ->> 'request_hash' !~ '^[0-9a-f]{64}$') THEN
            RAISE EXCEPTION 'release snapshot digest is not lowercase hexadecimal'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_release_snapshot_sha256_hex';
          END IF;

          -- Migration/backup owners may preserve immutable authority records.
          -- Every writable application process is fail-closed to the locked
          -- tenant/actor/operation and a receipt inserted in this transaction.
          IF session_user <> 'caresync_basic_app' THEN
            RETURN NEW;
          END IF;

          context_organization := NULLIF(
            current_setting('app.current_organization_id', true), ''
          )::uuid;
          context_actor := NULLIF(current_setting('app.current_user_id', true), '')::uuid;
          context_operation := NULLIF(
            current_setting('app.current_childcare_operation_id', true), ''
          )::uuid;
          row_operation := COALESCE(
            NULLIF(row_data ->> 'created_operation_id', '')::uuid,
            NULLIF(row_data ->> 'client_operation_id', '')::uuid
          );
          IF context_organization IS NULL OR context_actor IS NULL
             OR context_operation IS NULL OR row_operation IS NULL
             OR NEW.organization_id <> context_organization
             OR row_operation <> context_operation THEN
            RAISE EXCEPTION 'family authority insert does not match locked context'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_insert_locked_context';
          END IF;

          SELECT receipt_row.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt_row
          WHERE receipt_row.organization_id = context_organization
            AND receipt_row.client_operation_id = context_operation
            AND receipt_row.actor_user_id = context_actor
            AND receipt_row.xmin = pg_current_xact_id()::text::xid;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'family authority insert requires a same-transaction receipt'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_insert_current_receipt';
          END IF;
          IF command_receipt.request_hash !~ '^[0-9a-f]{64}$'
             OR jsonb_typeof(command_receipt.outcome::jsonb) IS DISTINCT FROM 'object'
             OR command_receipt.outcome::jsonb IS DISTINCT FROM jsonb_build_object(
               'action_route', command_receipt.outcome::jsonb -> 'action_route'
             )
             OR jsonb_typeof(command_receipt.outcome::jsonb -> 'action_route')
                IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'family authority receipt metadata is not canonical'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_receipt_metadata';
          END IF;

          command_matches := false;
          IF TG_TABLE_NAME = 'family_authority_people' THEN
            expected_target_type := 'authority_person';
            expected_target_id := NEW.id;
            expected_committed_version := NEW.version;
            expected_action_route := '/families/' || NEW.family_id::text
              || '?authority_person_id=' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'family.authority.person.create';
            IF NEW.version <> 1 OR NEW.status <> 'active'
               OR NEW.created_operation_id <> context_operation
               OR NEW.last_operation_id <> context_operation
               OR NEW.retired_at IS NOT NULL OR NEW.retired_operation_id IS NOT NULL THEN
              RAISE EXCEPTION 'new authority person lifecycle or provenance is invalid'
                USING ERRCODE='23514';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
          ELSIF TG_TABLE_NAME = 'family_authority_person_versions' THEN
            expected_target_type := 'authority_person';
            expected_target_id := NEW.person_id;
            expected_committed_version := NEW.version_number;
            expected_action_route := '/families/' || NEW.family_id::text
              || '?authority_person_id=' || NEW.person_id::text;
            command_matches := command_receipt.command_type IN (
              'family.authority.person.create', 'family.authority.person.replace'
            );
            IF NEW.closed_at IS NOT NULL OR NEW.closed_operation_id IS NOT NULL
               OR EXISTS (
                 SELECT 1
                 FROM public.family_authority_person_versions AS same_operation
                 WHERE same_operation.organization_id = NEW.organization_id
                   AND same_operation.family_id = NEW.family_id
                   AND same_operation.person_id = NEW.person_id
                   AND same_operation.created_operation_id = context_operation
               )
               OR NEW.version_number <> COALESCE((
                 SELECT max(existing.version_number)+1
                 FROM public.family_authority_person_versions existing
                 WHERE existing.organization_id=NEW.organization_id
                   AND existing.family_id=NEW.family_id AND existing.person_id=NEW.person_id
               ),1) THEN
              RAISE EXCEPTION 'new person fact version is closed or out of sequence'
                USING ERRCODE='23514';
            END IF;
            NEW.created_at := statement_timestamp();
          ELSIF TG_TABLE_NAME = 'family_authority_evidence' THEN
            expected_target_type := 'authority_evidence';
            expected_target_id := NEW.id;
            expected_committed_version := 1;
            expected_action_route := '/families/' || NEW.family_id::text
              || '?authority_evidence_id=' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'family.authority.evidence.record';
            IF NEW.recorded_by_user_id<>context_actor
               OR NEW.recorded_by_user_id<>command_receipt.actor_user_id THEN
              RAISE EXCEPTION 'evidence recorder is not the locked receipt actor'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_recorder_actor';
            END IF;
            PERFORM 1 FROM public.families AS family
            WHERE family.organization_id=NEW.organization_id
              AND family.id=NEW.family_id
            FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'evidence family lane is missing'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_family_lane';
            END IF;
            PERFORM 1
            FROM public.organization_memberships AS membership
            JOIN public.roles AS actor_role
              ON actor_role.organization_id=membership.organization_id
             AND actor_role.id=membership.role_id
            WHERE membership.organization_id=NEW.organization_id
              AND membership.user_id=context_actor
              AND membership.status='active'
              AND actor_role.key IN ('owner','administrator')
            FOR UPDATE OF membership, actor_role;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'evidence recording requires an active owner or admin actor'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_privileged_actor';
            END IF;
            IF NEW.storage_reference IS NOT NULL OR NEW.media_type IS NOT NULL
               OR NEW.byte_size IS NOT NULL OR NEW.content_sha256 IS NOT NULL THEN
              RAISE EXCEPTION 'runtime evidence intake cannot assert storage metadata'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_runtime_storage_reserved';
            END IF;
            NEW.created_at := transaction_timestamp();
          ELSIF TG_TABLE_NAME = 'family_authority_evidence_assessments' THEN
            expected_target_type := 'authority_evidence';
            expected_target_id := NEW.evidence_id;
            expected_committed_version := NEW.version_number;
            expected_action_route := '/families/' || NEW.family_id::text
              || '?authority_evidence_id=' || NEW.evidence_id::text;
            command_matches := (
              NEW.version_number=2
              AND NEW.decision='reviewed'
              AND command_receipt.command_type='family.authority.evidence.review'
            ) OR (
              NEW.version_number=2
              AND NEW.decision='rejected'
              AND command_receipt.command_type='family.authority.evidence.reject'
            ) OR (
              NEW.version_number=3
              AND NEW.decision='invalidated'
              AND command_receipt.command_type='family.authority.evidence.invalidate'
            ) OR (
              NEW.version_number=3
              AND NEW.decision='superseded'
              AND command_receipt.command_type='family.authority.evidence.supersede'
            );
            IF NEW.actor_user_id<>context_actor THEN
              RAISE EXCEPTION 'evidence assessment actor is not the locked actor'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_assessment_actor';
            END IF;
            PERFORM 1 FROM public.families AS family
            WHERE family.organization_id=NEW.organization_id
              AND family.id=NEW.family_id
            FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'evidence assessment family lane is missing'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_assessment_family_lane';
            END IF;
            PERFORM 1
            FROM public.organization_memberships AS membership
            JOIN public.roles AS actor_role
              ON actor_role.organization_id=membership.organization_id
             AND actor_role.id=membership.role_id
            WHERE membership.organization_id=NEW.organization_id
              AND membership.user_id=context_actor
              AND membership.status='active'
              AND actor_role.key IN ('owner','administrator')
            FOR UPDATE OF membership, actor_role;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'evidence assessment requires an active owner or admin actor'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_assessment_privileged_actor';
            END IF;
            PERFORM 1
            FROM public.family_authority_evidence AS evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id
              AND evidence.id=NEW.evidence_id
            FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'evidence assessment asset is missing'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_assessment_asset';
            END IF;
            IF NEW.version_number=2 THEN
              IF EXISTS (
                SELECT 1 FROM public.family_authority_evidence_assessments existing
                WHERE existing.organization_id=NEW.organization_id
                  AND existing.evidence_id=NEW.evidence_id
              ) THEN
                RAISE EXCEPTION 'evidence has already been assessed'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_authority_evidence_assessment_sequence';
              END IF;
              IF NEW.decision='reviewed' AND EXISTS (
                SELECT 1 FROM public.family_authority_evidence evidence
                WHERE evidence.organization_id=NEW.organization_id
                  AND evidence.family_id=NEW.family_id
                  AND evidence.id=NEW.evidence_id
                  AND evidence.expires_at IS NOT NULL
                  AND evidence.expires_at<=clock_timestamp()
              ) THEN
                RAISE EXCEPTION 'expired evidence cannot be approved'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_authority_evidence_review_unexpired';
              END IF;
            ELSE
              IF NOT EXISTS (
                SELECT 1 FROM public.family_authority_evidence_assessments prior
                WHERE prior.organization_id=NEW.organization_id
                  AND prior.evidence_id=NEW.evidence_id
                  AND prior.version_number=2
                  AND prior.decision='reviewed'
              ) OR EXISTS (
                SELECT 1 FROM public.family_authority_evidence_assessments terminal
                WHERE terminal.organization_id=NEW.organization_id
                  AND terminal.evidence_id=NEW.evidence_id
                  AND terminal.version_number=3
              ) THEN
                RAISE EXCEPTION 'evidence terminal assessment is out of sequence'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_authority_evidence_assessment_sequence';
              END IF;
              IF NEW.decision='superseded' THEN
                PERFORM 1
                FROM public.family_authority_evidence AS replacement
                WHERE replacement.organization_id=NEW.organization_id
                  AND replacement.family_id=NEW.family_id
                  AND replacement.id=NEW.superseded_by_evidence_id
                  AND (replacement.expires_at IS NULL
                    OR replacement.expires_at>clock_timestamp())
                  AND EXISTS (
                    SELECT 1
                    FROM public.family_authority_evidence_assessments replacement_review
                    WHERE replacement_review.organization_id=replacement.organization_id
                      AND replacement_review.evidence_id=replacement.id
                      AND replacement_review.version_number=2
                      AND replacement_review.decision='reviewed'
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public.family_authority_evidence_assessments replacement_terminal
                    WHERE replacement_terminal.organization_id=replacement.organization_id
                      AND replacement_terminal.evidence_id=replacement.id
                      AND replacement_terminal.version_number=3
                  )
                FOR UPDATE;
                IF NOT FOUND THEN
                  RAISE EXCEPTION 'replacement evidence is not current and reviewed'
                    USING ERRCODE='23514',
                          CONSTRAINT='ck_authority_evidence_superseding_current';
                END IF;
              END IF;
            END IF;
            NEW.created_at := transaction_timestamp();
          ELSIF TG_TABLE_NAME = 'child_release_authorizations' THEN
            expected_target_type := 'release_authorization';
            expected_target_id := NEW.id;
            expected_committed_version := NEW.version;
            expected_action_route := '/children/' || NEW.child_id::text
              || '?release_authorization_id=' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'child.release.authorization.grant';
            IF NEW.version<>1 OR NEW.revoked_at IS NOT NULL
               OR NEW.revoked_operation_id IS NOT NULL
               OR NEW.revocation_reason_code IS NOT NULL THEN
              RAISE EXCEPTION 'new release authorization must begin active at version one'
                USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence_assessments AS assessment
              WHERE assessment.organization_id=NEW.organization_id
                AND assessment.family_id=NEW.family_id
                AND assessment.evidence_id=NEW.basis_evidence_id
                AND assessment.id=NEW.basis_evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'release authorization requires reviewed evidence'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_release_authorization_reviewed_evidence';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
          ELSIF TG_TABLE_NAME = 'child_release_rules' THEN
            expected_target_type := 'release_rule';
            expected_target_id := NEW.id;
            expected_committed_version := NEW.version;
            expected_action_route := '/children/' || NEW.child_id::text
              || '?release_rule_id=' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'child.release.rule.create';
            IF NEW.version<>1 OR NEW.revoked_at IS NOT NULL
               OR NEW.revoked_operation_id IS NOT NULL
               OR NEW.revocation_reason_code IS NOT NULL THEN
              RAISE EXCEPTION 'new release rule must begin active at version one'
                USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence_assessments AS assessment
              WHERE assessment.organization_id=NEW.organization_id
                AND assessment.family_id=NEW.family_id
                AND assessment.evidence_id=NEW.basis_evidence_id
                AND assessment.id=NEW.basis_evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'release rule requires reviewed evidence'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_release_rule_reviewed_evidence';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
          ELSIF TG_TABLE_NAME = 'consent_policy_versions' THEN
            expected_target_type := 'consent';
            expected_target_id := NEW.id;
            expected_committed_version := NEW.version_number;
            expected_action_route := '/consent-policies/' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'organization.consent.policy.publish';
            NEW.published_at := statement_timestamp();
          ELSIF TG_TABLE_NAME = 'child_consent_decisions' THEN
            expected_target_type := 'consent';
            expected_target_id := NEW.id;
            expected_committed_version := NEW.version;
            expected_action_route := '/children/' || NEW.child_id::text
              || '?consent_id=' || NEW.id::text;
            command_matches := command_receipt.command_type = 'child.consent.record';
            IF NEW.version<>1 OR NEW.withdrawn_at IS NOT NULL
               OR NEW.withdrawn_operation_id IS NOT NULL
               OR NEW.withdrawal_reason_code IS NOT NULL THEN
              RAISE EXCEPTION 'new consent decision must begin current at version one'
                USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence_assessments AS assessment
              WHERE assessment.organization_id=NEW.organization_id
                AND assessment.family_id=NEW.family_id
                AND assessment.evidence_id=NEW.evidence_id
                AND assessment.id=NEW.evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'consent decision requires reviewed evidence'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_child_consent_reviewed_evidence';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
          ELSIF TG_TABLE_NAME = 'attendance_release_snapshots' THEN
            expected_target_type := 'attendance_release';
            expected_target_id := NEW.id;
            expected_committed_version := 1;
            expected_action_route := '/attendance/releases/' || NEW.id::text;
            command_matches :=
              command_receipt.command_type = 'attendance.release.checkout';
            IF NOT isfinite(NEW.requested_at) THEN
              RAISE EXCEPTION 'release snapshot request time must be finite'
                USING ERRCODE='23514';
            END IF;
            IF command_receipt.request_hash <> NEW.request_hash
               OR command_receipt.actor_user_id <> NEW.actor_user_id THEN
              RAISE EXCEPTION 'release snapshot does not echo command receipt'
                USING ERRCODE = '23514', CONSTRAINT = 'ck_release_snapshot_receipt_echo';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.child_release_authorizations AS release_authorization
              WHERE release_authorization.organization_id = NEW.organization_id
                AND release_authorization.family_id = NEW.family_id
                AND release_authorization.child_id = NEW.child_id
                AND release_authorization.recipient_person_id = NEW.recipient_person_id
                AND release_authorization.id = NEW.authorization_id
                AND release_authorization.version = NEW.authorization_version
                AND release_authorization.basis_evidence_id=NEW.evidence_id
                AND release_authorization.basis_evidence_assessment_id=
                    NEW.evidence_assessment_id
                AND release_authorization.revoked_at IS NULL
                AND NEW.requested_at >= release_authorization.effective_from
                AND NEW.requested_at < release_authorization.effective_until
            ) THEN
              RAISE EXCEPTION 'release snapshot authorization version is stale'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_release_snapshot_authorization_version';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence_assessments AS assessment
              JOIN public.family_authority_evidence AS evidence
                ON evidence.organization_id=assessment.organization_id
               AND evidence.family_id=assessment.family_id
               AND evidence.id=assessment.evidence_id
              WHERE assessment.organization_id=NEW.organization_id
                AND assessment.family_id=NEW.family_id
                AND assessment.evidence_id=NEW.evidence_id
                AND assessment.id=NEW.evidence_assessment_id
                AND assessment.version_number=NEW.evidence_assessment_version
                AND assessment.version_number=2
                AND assessment.decision='reviewed'
                AND (evidence.expires_at IS NULL
                  OR NEW.requested_at<evidence.expires_at)
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'release snapshot evidence assessment is stale'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_snapshot_evidence_assessment';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.child_authority_heads AS head
              WHERE head.organization_id=NEW.organization_id
                AND head.family_id=NEW.family_id AND head.child_id=NEW.child_id
                AND head.revision=NEW.authority_revision
            ) THEN
              RAISE EXCEPTION 'release snapshot authority revision is stale'
                USING ERRCODE='23514', CONSTRAINT='ck_release_snapshot_authority_revision';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.family_authority_people AS person
              WHERE person.organization_id=NEW.organization_id
                AND person.family_id=NEW.family_id AND person.id=NEW.recipient_person_id
                AND person.status='active'
                AND person.current_person_version_id=NEW.recipient_person_version_id
            ) THEN
              RAISE EXCEPTION 'release snapshot recipient fact version is stale'
                USING ERRCODE='23514', CONSTRAINT='ck_release_snapshot_recipient_version';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.organization_memberships membership
              WHERE membership.organization_id=NEW.organization_id
                AND membership.user_id=NEW.actor_user_id AND membership.status='active'
            ) THEN
              RAISE EXCEPTION 'release snapshot actor lacks active tenant membership'
                USING ERRCODE='23514', CONSTRAINT='ck_release_snapshot_actor_membership';
            END IF;
            NEW.committed_at := transaction_timestamp();
          ELSIF TG_TABLE_NAME = 'child_authority_heads' THEN
            expected_action_route := CASE command_receipt.target_type
              WHEN 'release_authorization' THEN '/children/' || NEW.child_id::text
                || '?release_authorization_id=' || command_receipt.target_id::text
              WHEN 'release_rule' THEN '/children/' || NEW.child_id::text
                || '?release_rule_id=' || command_receipt.target_id::text
              WHEN 'consent' THEN '/children/' || NEW.child_id::text
                || '?consent_id=' || command_receipt.target_id::text
              ELSE NULL
            END;
            IF NEW.revision <> 1 OR NEW.created_operation_id <> context_operation
               OR NEW.last_operation_id <> context_operation THEN
              RAISE EXCEPTION 'new authority head must begin at revision one'
                USING ERRCODE = '23514', CONSTRAINT = 'ck_child_authority_head_initial';
            END IF;
            head_target_matches :=
              (command_receipt.target_type = 'release_authorization' AND EXISTS (
                SELECT 1
                FROM public.child_release_authorizations AS release_authorization
                WHERE release_authorization.organization_id = NEW.organization_id
                  AND release_authorization.id = command_receipt.target_id
                  AND release_authorization.version =
                      command_receipt.committed_version
                  AND release_authorization.child_id = NEW.child_id
                  AND release_authorization.created_operation_id = context_operation
                  AND release_authorization.xmin = pg_current_xact_id()::text::xid
              )) OR
              (command_receipt.target_type = 'release_rule' AND EXISTS (
                SELECT 1 FROM public.child_release_rules AS rule
                WHERE rule.organization_id = NEW.organization_id
                  AND rule.id = command_receipt.target_id
                  AND rule.version = command_receipt.committed_version
                  AND rule.child_id = NEW.child_id
                  AND rule.created_operation_id = context_operation
                  AND rule.xmin = pg_current_xact_id()::text::xid
              )) OR
              (command_receipt.target_type = 'consent' AND EXISTS (
                SELECT 1 FROM public.child_consent_decisions AS decision
                WHERE decision.organization_id = NEW.organization_id
                  AND decision.id = command_receipt.target_id
                  AND decision.version = command_receipt.committed_version
                  AND decision.child_id = NEW.child_id
                  AND decision.created_operation_id = context_operation
                  AND decision.xmin = pg_current_xact_id()::text::xid
              ));
            IF NOT head_target_matches THEN
              RAISE EXCEPTION 'authority head receipt target is not an affected child record'
                USING ERRCODE = '23514', CONSTRAINT = 'ck_child_authority_head_target';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
            IF command_receipt.committed_version <> 1 THEN
              RAISE EXCEPTION 'initial authority head target version is not exact'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_child_authority_head_receipt_version';
            END IF;
            IF command_receipt.outcome ->> 'action_route'
               IS DISTINCT FROM expected_action_route THEN
              RAISE EXCEPTION 'family authority receipt action route is not canonical'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_family_authority_receipt_metadata';
            END IF;
            RETURN NEW;
          ELSE
            RAISE EXCEPTION 'unsupported family authority insert table'
              USING ERRCODE = '23514';
          END IF;

          IF command_receipt.outcome ->> 'action_route'
             IS DISTINCT FROM expected_action_route THEN
            RAISE EXCEPTION 'family authority receipt action route is not canonical'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_receipt_metadata';
          END IF;
          IF command_receipt.target_type <> expected_target_type
             OR command_receipt.target_id <> expected_target_id
             OR command_receipt.committed_version <> expected_committed_version
             OR NOT command_matches THEN
            RAISE EXCEPTION 'family authority receipt command or target does not match row'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_insert_receipt_target';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.caresync_family_authority_insert_guard() FROM PUBLIC")

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_transition_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          context_organization uuid;
          context_actor uuid;
          context_operation uuid;
          command_receipt public.childcare_command_receipts%ROWTYPE;
          expected_committed_version integer;
          expected_action_route text;
          allowed_change boolean;
          target_matches boolean;
          row_data jsonb;
          timestamp_key text;
        BEGIN
          IF TG_OP='UPDATE' THEN
            row_data:=to_jsonb(NEW);
            FOREACH timestamp_key IN ARRAY ARRAY[
              'created_at','updated_at','retired_at','closed_at','issued_at',
              'captured_at','expires_at','effective_from','effective_until',
              'revoked_at','published_at','withdrawn_at','requested_at','committed_at'
            ] LOOP
              IF row_data ? timestamp_key
                 AND row_data ->> timestamp_key IS NOT NULL
                 AND NOT isfinite((row_data ->> timestamp_key)::timestamptz) THEN
                RAISE EXCEPTION 'family authority timestamps must be finite'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_family_authority_timestamp_finite';
              END IF;
            END LOOP;
          END IF;
          IF session_user <> 'caresync_basic_app' THEN
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'family authority history cannot be deleted'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_family_authority_history_immutable';
          END IF;

          context_organization := NULLIF(
            current_setting('app.current_organization_id', true), ''
          )::uuid;
          context_actor := NULLIF(current_setting('app.current_user_id', true), '')::uuid;
          context_operation := NULLIF(
            current_setting('app.current_childcare_operation_id', true), ''
          )::uuid;
          IF context_organization IS NULL OR context_actor IS NULL
             OR context_operation IS NULL OR NEW.organization_id <> context_organization THEN
            RAISE EXCEPTION 'family authority transition does not match locked context'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_transition_locked_context';
          END IF;
          SELECT receipt_row.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt_row
          WHERE receipt_row.organization_id = context_organization
            AND receipt_row.client_operation_id = context_operation
            AND receipt_row.actor_user_id = context_actor
            AND receipt_row.xmin = pg_current_xact_id()::text::xid;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'family authority transition requires a same-transaction receipt'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_transition_current_receipt';
          END IF;
          IF command_receipt.request_hash !~ '^[0-9a-f]{64}$'
             OR jsonb_typeof(command_receipt.outcome::jsonb) IS DISTINCT FROM 'object'
             OR command_receipt.outcome::jsonb IS DISTINCT FROM jsonb_build_object(
               'action_route', command_receipt.outcome::jsonb -> 'action_route'
             )
             OR jsonb_typeof(command_receipt.outcome::jsonb -> 'action_route')
                IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'family authority receipt metadata is not canonical'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_receipt_metadata';
          END IF;

          IF TG_TABLE_NAME = 'family_authority_person_versions' THEN
            expected_committed_version := OLD.version_number + 1;
            expected_action_route := '/families/' || OLD.family_id::text
              || '?authority_person_id=' || OLD.person_id::text;
            IF OLD.closed_at IS NOT NULL OR OLD.closed_operation_id IS NOT NULL
               OR NEW.closed_operation_id <> context_operation
               OR command_receipt.target_type <> 'authority_person'
               OR command_receipt.target_id <> OLD.person_id
               OR command_receipt.command_type NOT IN (
                 'family.authority.person.replace', 'family.authority.person.retire'
               ) THEN
              RAISE EXCEPTION 'person fact version may only close once under its person command'
                USING ERRCODE = '23514';
            END IF;
            NEW.closed_at := statement_timestamp();
            IF NEW.closed_at < OLD.created_at THEN
              RAISE EXCEPTION 'person fact version cannot close before creation'
                USING ERRCODE='23514';
            END IF;
            allowed_change :=
              (to_jsonb(NEW) - ARRAY['closed_at','closed_operation_id']) =
              (to_jsonb(OLD) - ARRAY['closed_at','closed_operation_id']);
          ELSIF TG_TABLE_NAME = 'family_authority_people' THEN
            expected_committed_version := NEW.version;
            expected_action_route := '/families/' || OLD.family_id::text
              || '?authority_person_id=' || OLD.id::text;
            target_matches := command_receipt.target_type = 'authority_person'
              AND command_receipt.target_id = OLD.id;
            IF OLD.status <> 'active'
               OR OLD.last_operation_id = context_operation
               OR NOT target_matches OR NEW.version <> OLD.version + 1
               OR NEW.last_operation_id <> context_operation THEN
              RAISE EXCEPTION 'authority person transition is stale or mismatched'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_authority_person_one_transition_per_operation';
            END IF;
            IF command_receipt.command_type = 'family.authority.person.replace' THEN
              IF NEW.status <> 'active' OR NEW.current_person_version_id IS NULL
                 OR NEW.current_person_version_id = OLD.current_person_version_id
                 OR NEW.retired_at IS NOT NULL OR NEW.retired_operation_id IS NOT NULL THEN
                RAISE EXCEPTION 'authority person replacement shape is invalid'
                  USING ERRCODE = '23514';
              END IF;
              allowed_change :=
                (to_jsonb(NEW) - ARRAY[
                  'version','current_person_version_id','last_operation_id','updated_at'
                ]) =
                (to_jsonb(OLD) - ARRAY[
                  'version','current_person_version_id','last_operation_id','updated_at'
                ]);
            ELSIF command_receipt.command_type = 'family.authority.person.retire' THEN
              IF NEW.status <> 'retired' OR NEW.current_person_version_id IS NOT NULL
                 OR NEW.retired_operation_id <> context_operation THEN
                RAISE EXCEPTION 'authority person retirement shape is invalid'
                  USING ERRCODE = '23514';
              END IF;
              NEW.retired_at := statement_timestamp();
              IF NEW.retired_at < OLD.created_at THEN
                RAISE EXCEPTION 'authority person cannot retire before creation'
                  USING ERRCODE='23514';
              END IF;
              allowed_change :=
                (to_jsonb(NEW) - ARRAY[
                  'version','status','current_person_version_id','last_operation_id',
                  'retired_at','retired_operation_id','updated_at'
                ]) =
                (to_jsonb(OLD) - ARRAY[
                  'version','status','current_person_version_id','last_operation_id',
                  'retired_at','retired_operation_id','updated_at'
                ]);
            ELSE
              allowed_change := false;
            END IF;
            NEW.updated_at := statement_timestamp();
          ELSIF TG_TABLE_NAME = 'child_authority_heads' THEN
            expected_committed_version := command_receipt.committed_version;
            expected_action_route := CASE command_receipt.target_type
              WHEN 'authority_person' THEN '/families/' || NEW.family_id::text
                || '?authority_person_id=' || command_receipt.target_id::text
              WHEN 'authority_evidence' THEN '/families/' || NEW.family_id::text
                || '?authority_evidence_id=' || command_receipt.target_id::text
              WHEN 'release_authorization' THEN '/children/' || NEW.child_id::text
                || '?release_authorization_id=' || command_receipt.target_id::text
              WHEN 'release_rule' THEN '/children/' || NEW.child_id::text
                || '?release_rule_id=' || command_receipt.target_id::text
              WHEN 'consent' THEN '/children/' || NEW.child_id::text
                || '?consent_id=' || command_receipt.target_id::text
              ELSE NULL
            END;
            IF NEW.revision <> OLD.revision + 1
               OR OLD.last_operation_id = context_operation
               OR NEW.last_operation_id <> context_operation THEN
              RAISE EXCEPTION 'authority head must increment exactly once'
                USING ERRCODE = '23514', CONSTRAINT = 'ck_child_authority_head_increment';
            END IF;
            target_matches :=
              (command_receipt.target_type = 'release_authorization' AND EXISTS (
                SELECT 1
                FROM public.child_release_authorizations AS release_authorization
                WHERE release_authorization.organization_id = NEW.organization_id
                  AND release_authorization.id = command_receipt.target_id
                  AND release_authorization.version =
                      command_receipt.committed_version
                  AND release_authorization.child_id = NEW.child_id
                  AND (
                    release_authorization.created_operation_id = context_operation
                    OR release_authorization.revoked_operation_id = context_operation
                  )
                  AND release_authorization.xmin = pg_current_xact_id()::text::xid
              )) OR
              (command_receipt.target_type = 'authority_evidence' AND EXISTS (
                SELECT 1
                FROM public.family_authority_evidence_assessments AS assessment
                WHERE assessment.organization_id=NEW.organization_id
                  AND assessment.family_id=NEW.family_id
                  AND assessment.evidence_id=command_receipt.target_id
                  AND assessment.version_number=command_receipt.committed_version
                  AND assessment.version_number=3
                  AND assessment.created_operation_id=context_operation
                  AND assessment.xmin=pg_current_xact_id()::text::xid
                  AND (
                    EXISTS (
                      SELECT 1 FROM public.child_release_authorizations dependency
                      WHERE dependency.organization_id=NEW.organization_id
                        AND dependency.family_id=NEW.family_id
                        AND dependency.child_id=NEW.child_id
                        AND dependency.basis_evidence_id=assessment.evidence_id
                        AND dependency.revoked_at IS NULL
                        AND dependency.effective_until>transaction_timestamp()
                    ) OR EXISTS (
                      SELECT 1 FROM public.child_release_rules dependency
                      WHERE dependency.organization_id=NEW.organization_id
                        AND dependency.family_id=NEW.family_id
                        AND dependency.child_id=NEW.child_id
                        AND dependency.basis_evidence_id=assessment.evidence_id
                        AND dependency.revoked_at IS NULL
                        AND dependency.effective_until>transaction_timestamp()
                    ) OR EXISTS (
                      SELECT 1 FROM public.child_consent_decisions dependency
                      WHERE dependency.organization_id=NEW.organization_id
                        AND dependency.family_id=NEW.family_id
                        AND dependency.child_id=NEW.child_id
                        AND dependency.evidence_id=assessment.evidence_id
                        AND dependency.withdrawn_at IS NULL
                        AND dependency.effective_until>transaction_timestamp()
                    )
                  )
              )) OR
              (command_receipt.target_type = 'release_rule' AND EXISTS (
                SELECT 1 FROM public.child_release_rules AS rule
                WHERE rule.organization_id = NEW.organization_id
                  AND rule.id = command_receipt.target_id
                  AND rule.version = command_receipt.committed_version
                  AND rule.child_id = NEW.child_id
                  AND (rule.created_operation_id = context_operation
                    OR rule.revoked_operation_id = context_operation)
                  AND rule.xmin = pg_current_xact_id()::text::xid
              )) OR
              (command_receipt.target_type = 'consent' AND EXISTS (
                SELECT 1 FROM public.child_consent_decisions AS decision
                WHERE decision.organization_id = NEW.organization_id
                  AND decision.id = command_receipt.target_id
                  AND decision.version = command_receipt.committed_version
                  AND decision.child_id = NEW.child_id
                  AND (decision.created_operation_id = context_operation
                    OR decision.withdrawn_operation_id = context_operation)
                  AND decision.xmin = pg_current_xact_id()::text::xid
              )) OR
              (command_receipt.target_type = 'authority_person' AND EXISTS (
                SELECT 1
                FROM public.family_authority_people AS person
                WHERE person.organization_id = NEW.organization_id
                  AND person.id = command_receipt.target_id
                  AND person.version = command_receipt.committed_version
                  AND person.last_operation_id = context_operation
                  AND person.xmin = pg_current_xact_id()::text::xid
                  AND (
                    EXISTS (SELECT 1 FROM public.child_release_authorizations a
                      WHERE a.organization_id=NEW.organization_id
                        AND a.child_id=NEW.child_id AND a.revoked_at IS NULL
                        AND a.effective_until > transaction_timestamp()
                        AND (a.recipient_person_id=person.id OR a.grantor_person_id=person.id))
                    OR EXISTS (SELECT 1 FROM public.child_release_rules r
                      WHERE r.organization_id=NEW.organization_id
                        AND r.child_id=NEW.child_id AND r.revoked_at IS NULL
                        AND r.effective_until > transaction_timestamp()
                        AND (r.scope_person_id=person.id OR r.directing_person_id=person.id))
                    OR EXISTS (SELECT 1 FROM public.child_consent_decisions d
                      WHERE d.organization_id=NEW.organization_id
                        AND d.child_id=NEW.child_id AND d.withdrawn_at IS NULL
                        AND d.effective_until > transaction_timestamp()
                        AND d.signer_person_id=person.id)
                  )
              ));
            IF NOT target_matches THEN
              RAISE EXCEPTION 'authority head operation does not affect this child'
                USING ERRCODE = '23514', CONSTRAINT = 'ck_child_authority_head_target';
            END IF;
            allowed_change :=
              (to_jsonb(NEW) - ARRAY['revision','last_operation_id','updated_at']) =
              (to_jsonb(OLD) - ARRAY['revision','last_operation_id','updated_at']);
            NEW.updated_at := statement_timestamp();
          ELSIF TG_TABLE_NAME IN ('child_release_authorizations','child_release_rules') THEN
            expected_committed_version := NEW.version;
            expected_action_route := CASE TG_TABLE_NAME
              WHEN 'child_release_authorizations' THEN '/children/' || NEW.child_id::text
                || '?release_authorization_id=' || OLD.id::text
              ELSE '/children/' || NEW.child_id::text
                || '?release_rule_id=' || OLD.id::text
            END;
            IF OLD.revoked_at IS NOT NULL OR OLD.revoked_operation_id IS NOT NULL
               OR NEW.revoked_operation_id <> context_operation OR NEW.version <> OLD.version + 1
               OR command_receipt.target_id <> OLD.id
               OR (TG_TABLE_NAME = 'child_release_authorizations' AND (
                 command_receipt.target_type <> 'release_authorization'
                 OR command_receipt.command_type <>
                    'child.release.authorization.revoke'
               ))
               OR (TG_TABLE_NAME = 'child_release_rules' AND (
                 command_receipt.target_type <> 'release_rule'
                 OR command_receipt.command_type <> 'child.release.rule.revoke'
               )) THEN
              RAISE EXCEPTION 'release authority may only revoke once under its exact command'
                USING ERRCODE = '23514';
            END IF;
            NEW.revoked_at := statement_timestamp();
            IF NEW.revoked_at < OLD.created_at THEN
              RAISE EXCEPTION 'release authority cannot revoke before creation'
                USING ERRCODE='23514';
            END IF;
            allowed_change :=
              (to_jsonb(NEW) - ARRAY[
                'version','revoked_at','revoked_operation_id','revocation_reason_code','updated_at'
              ]) =
              (to_jsonb(OLD) - ARRAY[
                'version','revoked_at','revoked_operation_id','revocation_reason_code','updated_at'
              ]);
            NEW.updated_at := statement_timestamp();
          ELSIF TG_TABLE_NAME = 'child_consent_decisions' THEN
            expected_committed_version := NEW.version;
            expected_action_route := '/children/' || NEW.child_id::text
              || '?consent_id=' || OLD.id::text;
            IF OLD.withdrawn_at IS NOT NULL OR OLD.withdrawn_operation_id IS NOT NULL
               OR NEW.withdrawn_operation_id <> context_operation
               OR NEW.version <> OLD.version + 1
               OR command_receipt.target_type <> 'consent'
               OR command_receipt.target_id <> OLD.id
               OR command_receipt.command_type <> 'child.consent.withdraw' THEN
              RAISE EXCEPTION 'consent decision may only withdraw once under its exact command'
                USING ERRCODE = '23514';
            END IF;
            NEW.withdrawn_at := statement_timestamp();
            IF NEW.withdrawn_at < OLD.created_at THEN
              RAISE EXCEPTION 'consent decision cannot withdraw before creation'
                USING ERRCODE='23514';
            END IF;
            allowed_change :=
              (to_jsonb(NEW) - ARRAY[
                'version','withdrawn_at','withdrawn_operation_id',
                'withdrawal_reason_code','updated_at'
              ]) =
              (to_jsonb(OLD) - ARRAY[
                'version','withdrawn_at','withdrawn_operation_id',
                'withdrawal_reason_code','updated_at'
              ]);
            NEW.updated_at := statement_timestamp();
          ELSE
            RAISE EXCEPTION 'family authority facts are append-only'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_family_authority_facts_immutable';
          END IF;

          IF command_receipt.committed_version <> expected_committed_version THEN
            RAISE EXCEPTION 'family authority receipt committed version is not exact'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_receipt_committed_version';
          END IF;
          IF command_receipt.outcome ->> 'action_route'
             IS DISTINCT FROM expected_action_route THEN
            RAISE EXCEPTION 'family authority receipt action route is not canonical'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_family_authority_receipt_metadata';
          END IF;
          IF NOT allowed_change THEN
            RAISE EXCEPTION 'family authority facts or provenance are immutable'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_family_authority_facts_immutable';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_family_authority_transition_guard() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_temporal_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          policy_requirement text;
        BEGIN
          IF TG_TABLE_NAME = 'child_release_authorizations' THEN
            IF NOT isfinite(NEW.effective_from) OR NOT isfinite(NEW.effective_until) THEN
              RAISE EXCEPTION 'release authorization interval must be finite'
                USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(
              NEW.organization_id::text || ':authorization:' || NEW.child_id::text
                || ':' || NEW.recipient_person_id::text, 0
            ));
            PERFORM 1
            FROM public.family_authority_people AS locked_person
            WHERE locked_person.organization_id = NEW.organization_id
              AND locked_person.family_id = NEW.family_id
              AND locked_person.id IN (
                NEW.recipient_person_id, NEW.grantor_person_id
              )
            ORDER BY locked_person.id
            FOR SHARE;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence AS evidence
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id=evidence.organization_id
               AND assessment.family_id=evidence.family_id
               AND assessment.evidence_id=evidence.id
              WHERE evidence.organization_id=NEW.organization_id
                AND evidence.family_id=NEW.family_id
                AND evidence.id=NEW.basis_evidence_id
                AND assessment.id=NEW.basis_evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND (evidence.expires_at IS NULL OR (
                  evidence.expires_at > clock_timestamp()
                  AND NEW.effective_until<=evidence.expires_at
                ))
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'release authorization evidence is not reviewed'
                USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.family_authority_people recipient
              JOIN public.family_authority_people grantor
                ON grantor.organization_id=recipient.organization_id
               AND grantor.family_id=recipient.family_id
              WHERE recipient.organization_id=NEW.organization_id
                AND recipient.family_id=NEW.family_id
                AND recipient.id=NEW.recipient_person_id AND recipient.status='active'
                AND grantor.id=NEW.grantor_person_id AND grantor.status='active'
                AND grantor.current_person_version_id=NEW.grantor_person_version_id
            ) THEN
              RAISE EXCEPTION 'release authorization references inactive or stale people'
                USING ERRCODE='23514', CONSTRAINT='ck_release_authorization_current_people';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.child_release_authorizations existing
              WHERE existing.organization_id=NEW.organization_id
                AND existing.child_id=NEW.child_id
                AND existing.recipient_person_id=NEW.recipient_person_id
                AND existing.revoked_at IS NULL
                AND tstzrange(existing.effective_from,existing.effective_until,'[)')
                  && tstzrange(NEW.effective_from,NEW.effective_until,'[)')
            ) THEN
              RAISE EXCEPTION 'release authorization interval overlaps an active grant'
                USING ERRCODE='23P01',
                      CONSTRAINT='ex_release_authorizations_active_window';
            END IF;
          ELSIF TG_TABLE_NAME = 'child_release_rules' THEN
            IF NOT isfinite(NEW.effective_from) OR NOT isfinite(NEW.effective_until) THEN
              RAISE EXCEPTION 'release rule interval must be finite'
                USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(
              NEW.organization_id::text || ':rule:' || NEW.child_id::text || ':'
                || NEW.rule_kind || ':' || NEW.scope_kind || ':'
                || COALESCE(NEW.scope_person_id::text,'all'), 0
            ));
            PERFORM 1
            FROM public.family_authority_people AS locked_person
            WHERE locked_person.organization_id = NEW.organization_id
              AND locked_person.family_id = NEW.family_id
              AND locked_person.id IN (
                NEW.scope_person_id, NEW.directing_person_id
              )
            ORDER BY locked_person.id
            FOR SHARE;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence AS evidence
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id=evidence.organization_id
               AND assessment.family_id=evidence.family_id
               AND assessment.evidence_id=evidence.id
              WHERE evidence.organization_id=NEW.organization_id
                AND evidence.family_id=NEW.family_id
                AND evidence.id=NEW.basis_evidence_id
                AND assessment.id=NEW.basis_evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND (evidence.expires_at IS NULL OR (
                  evidence.expires_at > clock_timestamp()
                  AND NEW.effective_until<=evidence.expires_at
                ))
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'release rule evidence is not reviewed'
                USING ERRCODE='23514';
            END IF;
            IF NEW.scope_person_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.family_authority_people person
              WHERE person.organization_id=NEW.organization_id
                AND person.family_id=NEW.family_id AND person.id=NEW.scope_person_id
                AND person.status='active'
            ) THEN
              RAISE EXCEPTION 'release rule scope person is not active'
                USING ERRCODE='23514', CONSTRAINT='ck_release_rule_scope_person_active';
            END IF;
            IF NEW.directing_person_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.family_authority_people person
              WHERE person.organization_id=NEW.organization_id
                AND person.family_id=NEW.family_id AND person.id=NEW.directing_person_id
                AND person.status='active'
                AND person.current_person_version_id=NEW.directing_person_version_id
            ) THEN
              RAISE EXCEPTION 'release rule directing person version is stale'
                USING ERRCODE='23514', CONSTRAINT='ck_release_rule_directing_person_current';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.child_release_rules existing
              WHERE existing.organization_id=NEW.organization_id
                AND existing.child_id=NEW.child_id AND existing.rule_kind=NEW.rule_kind
                AND existing.scope_kind=NEW.scope_kind
                AND existing.scope_person_id IS NOT DISTINCT FROM NEW.scope_person_id
                AND existing.revoked_at IS NULL
                AND tstzrange(existing.effective_from,existing.effective_until,'[)')
                  && tstzrange(NEW.effective_from,NEW.effective_until,'[)')
            ) THEN
              RAISE EXCEPTION 'release rule interval overlaps its active lane'
                USING ERRCODE='23P01', CONSTRAINT='ex_release_rules_active_window';
            END IF;
          ELSIF TG_TABLE_NAME = 'consent_policy_versions' THEN
            IF NOT isfinite(NEW.effective_from) OR NOT isfinite(NEW.effective_until) THEN
              RAISE EXCEPTION 'consent policy interval must be finite'
                USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(
              NEW.organization_id::text || ':' || 'consent-policy:'
                || NEW.purpose_code, 0
            ));
            IF EXISTS (
              SELECT 1 FROM public.consent_policy_versions existing
              WHERE existing.organization_id=NEW.organization_id
                AND existing.purpose_code=NEW.purpose_code
                AND tstzrange(existing.effective_from,existing.effective_until,'[)')
                  && tstzrange(NEW.effective_from,NEW.effective_until,'[)')
            ) THEN
              RAISE EXCEPTION 'consent policy interval overlaps its purpose lane'
                USING ERRCODE='23P01', CONSTRAINT='ex_consent_policy_active_window';
            END IF;
          ELSIF TG_TABLE_NAME = 'child_consent_decisions' THEN
            IF NOT isfinite(NEW.effective_from) OR NOT isfinite(NEW.effective_until) THEN
              RAISE EXCEPTION 'consent decision interval must be finite'
                USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(
              NEW.organization_id::text || ':consent:' || NEW.child_id::text
                || ':' || NEW.purpose_code, 0
            ));
            PERFORM 1
            FROM public.family_authority_people AS locked_person
            WHERE locked_person.organization_id = NEW.organization_id
              AND locked_person.family_id = NEW.family_id
              AND locked_person.id = NEW.signer_person_id
            FOR SHARE;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence AS evidence
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id=evidence.organization_id
               AND assessment.family_id=evidence.family_id
               AND assessment.evidence_id=evidence.id
              WHERE evidence.organization_id=NEW.organization_id
                AND evidence.family_id=NEW.family_id AND evidence.id=NEW.evidence_id
                AND assessment.id=NEW.evidence_assessment_id
                AND assessment.version_number=2 AND assessment.decision='reviewed'
                AND (evidence.expires_at IS NULL OR (
                  evidence.expires_at > clock_timestamp()
                  AND NEW.effective_until<=evidence.expires_at
                ))
                AND NOT EXISTS (
                  SELECT 1 FROM public.family_authority_evidence_assessments terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'consent decision evidence is not reviewed'
                USING ERRCODE='23514';
            END IF;
            SELECT policy.signer_authority_requirement INTO policy_requirement
            FROM public.consent_policy_versions policy
            WHERE policy.organization_id=NEW.organization_id
              AND policy.purpose_code=NEW.purpose_code AND policy.id=NEW.policy_version_id
              AND NEW.effective_from >= policy.effective_from
              AND NEW.effective_until <= policy.effective_until;
            IF NOT EXISTS (
              SELECT 1 FROM public.family_authority_people signer
              WHERE signer.organization_id=NEW.organization_id
                AND signer.family_id=NEW.family_id AND signer.id=NEW.signer_person_id
                AND signer.status='active'
                AND signer.current_person_version_id=NEW.signer_person_version_id
            ) THEN
              RAISE EXCEPTION 'consent signer fact version is stale'
                USING ERRCODE='23514', CONSTRAINT='ck_child_consent_signer_current';
            END IF;
            IF policy_requirement IS NULL OR NOT (
              (policy_requirement='guardian_record'
                AND NEW.signer_authority_basis='guardian_record')
              OR (policy_requirement='legal_decision_maker'
                AND NEW.signer_authority_basis IN (
                  'guardian_record','reviewed_custody_evidence'
                ))
              OR (policy_requirement='specific_reviewed_authority'
                AND NEW.signer_authority_basis IN (
                  'reviewed_custody_evidence','reviewed_delegation_evidence',
                  'other_reviewed_authority'
                ))
            ) THEN
              RAISE EXCEPTION 'consent signer basis does not satisfy the exact policy'
                USING ERRCODE='23514', CONSTRAINT='ck_child_consent_signer_authority';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.child_consent_decisions existing
              WHERE existing.organization_id=NEW.organization_id
                AND existing.child_id=NEW.child_id
                AND existing.purpose_code=NEW.purpose_code
                AND existing.withdrawn_at IS NULL
                AND tstzrange(existing.effective_from,existing.effective_until,'[)')
                  && tstzrange(NEW.effective_from,NEW.effective_until,'[)')
            ) THEN
              RAISE EXCEPTION 'consent decision interval overlaps its active lane'
                USING ERRCODE='23P01', CONSTRAINT='ex_child_consent_active_window';
            END IF;
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_family_authority_temporal_guard() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_person_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          person_organization uuid;
          person_family uuid;
          authority_person_id uuid;
          person_status text;
          person_version_number integer;
          current_version_id uuid;
          open_count integer;
          operation_id uuid;
          uncovered_children integer;
        BEGIN
          IF TG_TABLE_NAME='family_authority_people' THEN
            person_organization:=NEW.organization_id;
            person_family:=NEW.family_id;
            authority_person_id:=NEW.id;
            operation_id:=NEW.last_operation_id;
          ELSE
            person_organization:=NEW.organization_id;
            person_family:=NEW.family_id;
            authority_person_id:=NEW.person_id;
            operation_id:=COALESCE(NEW.closed_operation_id,NEW.created_operation_id);
          END IF;
          SELECT person.status,person.version,person.current_person_version_id
            INTO person_status,person_version_number,current_version_id
          FROM public.family_authority_people person
          WHERE person.organization_id=person_organization
            AND person.family_id=person_family AND person.id=authority_person_id;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT count(*) INTO open_count
          FROM public.family_authority_person_versions version
          WHERE version.organization_id=person_organization
            AND version.family_id=person_family
            AND version.person_id=authority_person_id
            AND version.closed_at IS NULL;
          IF person_status='active' AND (
            open_count<>1 OR current_version_id IS NULL OR NOT EXISTS (
              SELECT 1 FROM public.family_authority_person_versions version
              WHERE version.organization_id=person_organization
                AND version.family_id=person_family
                AND version.person_id=authority_person_id
                AND version.id=current_version_id
                AND version.version_number=person_version_number
                AND version.closed_at IS NULL
            )
          ) THEN
            RAISE EXCEPTION 'active authority person lacks its exact open fact version'
              USING ERRCODE='23514', CONSTRAINT='ck_authority_person_current_version';
          ELSIF person_status='retired' AND (open_count<>0 OR current_version_id IS NOT NULL) THEN
            RAISE EXCEPTION 'retired authority person retains an open fact version'
              USING ERRCODE='23514', CONSTRAINT='ck_authority_person_retired_versions';
          END IF;

          IF TG_TABLE_NAME='family_authority_people' AND TG_OP='UPDATE'
             AND to_jsonb(NEW) ->> 'last_operation_id'
                 IS DISTINCT FROM to_jsonb(OLD) ->> 'last_operation_id' THEN
            WITH affected AS (
              SELECT release_authorization.child_id
              FROM public.child_release_authorizations release_authorization
              WHERE release_authorization.organization_id=person_organization
                AND release_authorization.family_id=person_family
                AND release_authorization.revoked_at IS NULL
                AND release_authorization.effective_until > clock_timestamp()
                AND (
                  release_authorization.recipient_person_id=authority_person_id
                  OR release_authorization.grantor_person_id=authority_person_id
                )
              UNION
              SELECT rule.child_id FROM public.child_release_rules rule
              WHERE rule.organization_id=person_organization AND rule.family_id=person_family
                AND rule.revoked_at IS NULL
                AND rule.effective_until > clock_timestamp()
                AND (rule.scope_person_id=authority_person_id
                  OR rule.directing_person_id=authority_person_id)
              UNION
              SELECT decision.child_id FROM public.child_consent_decisions decision
              WHERE decision.organization_id=person_organization
                AND decision.family_id=person_family AND decision.withdrawn_at IS NULL
                AND decision.effective_until > clock_timestamp()
                AND decision.signer_person_id=authority_person_id
            )
            SELECT count(*) INTO uncovered_children FROM affected
            WHERE NOT EXISTS (
              SELECT 1 FROM public.child_authority_heads head
              WHERE head.organization_id=person_organization
                AND head.child_id=affected.child_id
                AND head.last_operation_id=operation_id
                AND head.xmin=pg_current_xact_id()::text::xid
            );
            IF uncovered_children<>0 THEN
              RAISE EXCEPTION 'shared person change did not bump every affected child revision'
                USING ERRCODE='23514', CONSTRAINT='ck_authority_person_child_revisions';
            END IF;
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_family_authority_person_invariant() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_child_revision_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          authority_operation_id uuid;
          authority_evidence_id uuid;
          authority_evidence_assessment_id uuid;
        BEGIN
          IF TG_OP='INSERT' THEN
            authority_operation_id:=NEW.created_operation_id;
          ELSIF TG_TABLE_NAME='child_consent_decisions' THEN
            authority_operation_id:=NEW.withdrawn_operation_id;
          ELSE
            authority_operation_id:=NEW.revoked_operation_id;
          END IF;
          IF authority_operation_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.child_authority_heads head
            WHERE head.organization_id=NEW.organization_id AND head.child_id=NEW.child_id
              AND head.last_operation_id=authority_operation_id
              AND head.xmin=pg_current_xact_id()::text::xid
          ) THEN
            RAISE EXCEPTION 'child authority command did not create or increment its head'
              USING ERRCODE='23514', CONSTRAINT='ck_child_authority_command_revision';
          END IF;
          IF TG_OP='INSERT' THEN
            IF TG_TABLE_NAME='child_consent_decisions' THEN
              authority_evidence_id:=NEW.evidence_id;
              authority_evidence_assessment_id:=NEW.evidence_assessment_id;
            ELSE
              authority_evidence_id:=NEW.basis_evidence_id;
              authority_evidence_assessment_id:=NEW.basis_evidence_assessment_id;
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence AS evidence
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id=evidence.organization_id
               AND assessment.family_id=evidence.family_id
               AND assessment.evidence_id=evidence.id
              WHERE evidence.organization_id=NEW.organization_id
                AND evidence.family_id=NEW.family_id
                AND evidence.id=authority_evidence_id
                AND assessment.id=authority_evidence_assessment_id
                AND assessment.version_number=2
                AND assessment.decision='reviewed'
                AND (evidence.expires_at IS NULL OR (
                  evidence.expires_at > clock_timestamp()
                  AND NEW.effective_until<=evidence.expires_at
                ))
                AND NOT EXISTS (
                  SELECT 1
                  FROM public.family_authority_evidence_assessments AS terminal
                  WHERE terminal.organization_id=assessment.organization_id
                    AND terminal.evidence_id=assessment.evidence_id
                    AND terminal.version_number=3
                )
            ) THEN
              RAISE EXCEPTION 'authority evidence expired or changed before commit'
                USING ERRCODE='23514',
                  CONSTRAINT='ck_family_authority_evidence_commit_current';
            END IF;
          END IF;
          IF TG_OP='INSERT' AND TG_TABLE_NAME='child_release_authorizations' THEN
            IF NOT EXISTS (
              SELECT 1
              FROM public.family_authority_people AS recipient
              JOIN public.family_authority_people AS grantor
                ON grantor.organization_id=recipient.organization_id
               AND grantor.family_id=recipient.family_id
              WHERE recipient.organization_id=NEW.organization_id
                AND recipient.family_id=NEW.family_id
                AND recipient.id=NEW.recipient_person_id
                AND recipient.status='active'
                AND grantor.id=NEW.grantor_person_id
                AND grantor.status='active'
                AND grantor.current_person_version_id=NEW.grantor_person_version_id
            ) THEN
              RAISE EXCEPTION 'release authorization people changed before commit'
                USING ERRCODE='40001',
                      CONSTRAINT='ck_release_authorization_people_commit_current';
            END IF;
          ELSIF TG_OP='INSERT' AND TG_TABLE_NAME='child_release_rules' THEN
            IF NEW.scope_person_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.family_authority_people AS scope_person
              WHERE scope_person.organization_id=NEW.organization_id
                AND scope_person.family_id=NEW.family_id
                AND scope_person.id=NEW.scope_person_id
                AND scope_person.status='active'
            ) THEN
              RAISE EXCEPTION 'release rule scope person changed before commit'
                USING ERRCODE='40001',
                      CONSTRAINT='ck_release_rule_scope_person_commit_current';
            END IF;
            IF NEW.directing_person_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.family_authority_people AS directing_person
              WHERE directing_person.organization_id=NEW.organization_id
                AND directing_person.family_id=NEW.family_id
                AND directing_person.id=NEW.directing_person_id
                AND directing_person.status='active'
                AND directing_person.current_person_version_id=
                    NEW.directing_person_version_id
            ) THEN
              RAISE EXCEPTION 'release rule directing person changed before commit'
                USING ERRCODE='40001',
                      CONSTRAINT='ck_release_rule_directing_person_commit_current';
            END IF;
          ELSIF TG_OP='INSERT' AND TG_TABLE_NAME='child_consent_decisions' THEN
            IF NOT EXISTS (
              SELECT 1 FROM public.family_authority_people AS signer
              WHERE signer.organization_id=NEW.organization_id
                AND signer.family_id=NEW.family_id
                AND signer.id=NEW.signer_person_id
                AND signer.status='active'
                AND signer.current_person_version_id=NEW.signer_person_version_id
            ) THEN
              RAISE EXCEPTION 'consent signer changed before commit'
                USING ERRCODE='40001',
                      CONSTRAINT='ck_child_consent_signer_commit_current';
            END IF;
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_child_revision_invariant() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_evidence_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          command_receipt public.childcare_command_receipts%ROWTYPE;
          reviewed_assessment_id uuid;
          uncovered_children integer;
        BEGIN
          SELECT receipt.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt
          WHERE receipt.organization_id=NEW.organization_id
            AND receipt.client_operation_id=NEW.created_operation_id;
          IF NOT FOUND OR command_receipt.target_type<>'authority_evidence'
             OR command_receipt.target_id<>NEW.evidence_id
             OR command_receipt.actor_user_id<>NEW.actor_user_id
             OR command_receipt.committed_version<>NEW.version_number
             OR command_receipt.command_type IS DISTINCT FROM (CASE NEW.decision
               WHEN 'reviewed' THEN 'family.authority.evidence.review'
               WHEN 'rejected' THEN 'family.authority.evidence.reject'
               WHEN 'invalidated' THEN 'family.authority.evidence.invalidate'
               WHEN 'superseded' THEN 'family.authority.evidence.supersede'
             END) THEN
            RAISE EXCEPTION 'evidence assessment lacks its exact command receipt'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_assessment_receipt';
          END IF;

          IF NEW.decision='reviewed' AND EXISTS (
            SELECT 1 FROM public.family_authority_evidence evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id AND evidence.id=NEW.evidence_id
              AND evidence.expires_at IS NOT NULL
              AND evidence.expires_at<=clock_timestamp()
          ) THEN
            RAISE EXCEPTION 'evidence expired before review committed'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_unexpired';
          END IF;
          IF NEW.version_number<>3 THEN
            RETURN NULL;
          END IF;

          SELECT assessment.id INTO reviewed_assessment_id
          FROM public.family_authority_evidence_assessments assessment
          WHERE assessment.organization_id=NEW.organization_id
            AND assessment.evidence_id=NEW.evidence_id
            AND assessment.version_number=2 AND assessment.decision='reviewed';
          IF reviewed_assessment_id IS NULL THEN
            RAISE EXCEPTION 'terminal evidence decision lacks reviewed predecessor'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_assessment_sequence';
          END IF;

          IF NEW.decision='superseded' AND NOT EXISTS (
            SELECT 1
            FROM public.family_authority_evidence AS replacement
            JOIN public.family_authority_evidence_assessments AS review
              ON review.organization_id=replacement.organization_id
             AND review.family_id=replacement.family_id
             AND review.evidence_id=replacement.id
             AND review.version_number=2 AND review.decision='reviewed'
            WHERE replacement.organization_id=NEW.organization_id
              AND replacement.family_id=NEW.family_id
              AND replacement.id=NEW.superseded_by_evidence_id
              AND (replacement.expires_at IS NULL
                OR replacement.expires_at>clock_timestamp())
              AND NOT EXISTS (
                SELECT 1 FROM public.family_authority_evidence_assessments terminal
                WHERE terminal.organization_id=replacement.organization_id
                  AND terminal.evidence_id=replacement.id
                  AND terminal.version_number=3
              )
          ) THEN
            RAISE EXCEPTION 'replacement evidence changed before commit'
              USING ERRCODE='40001',
                    CONSTRAINT='ck_authority_evidence_superseding_current';
          END IF;

          WITH affected(child_id) AS (
            SELECT dependency_authorization.child_id
            FROM public.child_release_authorizations AS dependency_authorization
            WHERE dependency_authorization.organization_id=NEW.organization_id
              AND dependency_authorization.family_id=NEW.family_id
              AND dependency_authorization.basis_evidence_id=NEW.evidence_id
              AND dependency_authorization.basis_evidence_assessment_id=
                  reviewed_assessment_id
              AND dependency_authorization.revoked_at IS NULL
              AND dependency_authorization.effective_until>transaction_timestamp()
            UNION
            SELECT rule.child_id
            FROM public.child_release_rules rule
            WHERE rule.organization_id=NEW.organization_id
              AND rule.family_id=NEW.family_id
              AND rule.basis_evidence_id=NEW.evidence_id
              AND rule.basis_evidence_assessment_id=reviewed_assessment_id
              AND rule.revoked_at IS NULL
              AND rule.effective_until>transaction_timestamp()
            UNION
            SELECT decision.child_id
            FROM public.child_consent_decisions decision
            WHERE decision.organization_id=NEW.organization_id
              AND decision.family_id=NEW.family_id
              AND decision.evidence_id=NEW.evidence_id
              AND decision.evidence_assessment_id=reviewed_assessment_id
              AND decision.withdrawn_at IS NULL
              AND decision.effective_until>transaction_timestamp()
          )
          SELECT count(*) INTO uncovered_children
          FROM affected
          WHERE NOT EXISTS (
            SELECT 1 FROM public.child_authority_heads head
            WHERE head.organization_id=NEW.organization_id
              AND head.family_id=NEW.family_id
              AND head.child_id=affected.child_id
              AND head.last_operation_id=NEW.created_operation_id
              AND head.xmin=pg_current_xact_id()::text::xid
          );
          IF uncovered_children<>0 THEN
            RAISE EXCEPTION 'evidence terminal decision did not bump every dependent child'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_child_revisions';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_evidence_invariant() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_receipt_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          action_route text;
          expected_target_type text;
          expected_version integer;
        BEGIN
          IF NEW.command_type NOT IN (
            'family.authority.person.create','family.authority.person.replace',
            'family.authority.person.retire','family.authority.evidence.record',
            'family.authority.evidence.review','family.authority.evidence.reject',
            'family.authority.evidence.invalidate','family.authority.evidence.supersede',
            'child.release.authorization.grant','child.release.authorization.revoke',
            'child.release.rule.create','child.release.rule.revoke',
            'organization.consent.policy.publish','child.consent.record',
            'child.consent.withdraw','attendance.release.checkout'
          ) THEN
            IF NEW.target_type IN (
              'authority_person','authority_evidence','release_authorization',
              'release_rule','consent','attendance_release'
            ) OR NEW.command_type LIKE 'family.authority.%'
              OR NEW.command_type LIKE 'child.release.%'
              OR NEW.command_type LIKE 'child.consent.%'
              OR NEW.command_type LIKE 'organization.consent.%'
              OR NEW.command_type LIKE 'attendance.release.%' THEN
              RAISE EXCEPTION 'unknown authority command or target'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_authority_receipt_command';
            END IF;
            RETURN NEW;
          END IF;

          IF NOT isfinite(NEW.committed_at)
             OR NEW.request_hash !~ '^[0-9a-f]{64}$'
             OR jsonb_typeof(NEW.outcome::jsonb) IS DISTINCT FROM 'object'
             OR NEW.outcome::jsonb IS DISTINCT FROM jsonb_build_object(
               'action_route', NEW.outcome::jsonb -> 'action_route'
             )
             OR jsonb_typeof(NEW.outcome::jsonb -> 'action_route')
                IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'authority receipt metadata is not canonical'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_receipt_metadata';
          END IF;
          action_route:=NEW.outcome::jsonb ->> 'action_route';
          expected_target_type:=CASE
            WHEN NEW.command_type LIKE 'family.authority.person.%' THEN 'authority_person'
            WHEN NEW.command_type LIKE 'family.authority.evidence.%' THEN 'authority_evidence'
            WHEN NEW.command_type LIKE 'child.release.authorization.%'
              THEN 'release_authorization'
            WHEN NEW.command_type LIKE 'child.release.rule.%' THEN 'release_rule'
            WHEN NEW.command_type IN (
              'organization.consent.policy.publish','child.consent.record',
              'child.consent.withdraw'
            ) THEN 'consent'
            ELSE 'attendance_release'
          END;
          expected_version:=CASE
            WHEN NEW.command_type IN (
              'family.authority.person.create','family.authority.evidence.record',
              'child.release.authorization.grant','child.release.rule.create',
              'child.consent.record','attendance.release.checkout'
            ) THEN 1
            WHEN NEW.command_type IN (
              'family.authority.evidence.review','family.authority.evidence.reject'
            ) THEN 2
            WHEN NEW.command_type IN (
              'family.authority.evidence.invalidate','family.authority.evidence.supersede'
            ) THEN 3
            ELSE NULL
          END;
          IF NEW.target_type<>expected_target_type
             OR (expected_version IS NOT NULL AND NEW.committed_version<>expected_version)
             OR (NEW.command_type LIKE 'family.authority.person.%' AND
               action_route !~ ('^/families/[0-9a-f-]{36}\?authority_person_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type LIKE 'family.authority.evidence.%' AND
               action_route !~ ('^/families/[0-9a-f-]{36}\?authority_evidence_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type LIKE 'child.release.authorization.%' AND
               action_route !~ ('^/children/[0-9a-f-]{36}\?release_authorization_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type LIKE 'child.release.rule.%' AND
               action_route !~ ('^/children/[0-9a-f-]{36}\?release_rule_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type IN ('child.consent.record','child.consent.withdraw') AND
               action_route !~ ('^/children/[0-9a-f-]{36}\?consent_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type='organization.consent.policy.publish' AND
               action_route<>('/consent-policies/' || NEW.target_id::text))
             OR (NEW.command_type='attendance.release.checkout' AND
               action_route<>('/attendance/releases/' || NEW.target_id::text)) THEN
            RAISE EXCEPTION 'authority receipt command, target, version, or route is invalid'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_receipt_command';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_family_authority_receipt_guard() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_receipt_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          expected_action_route text;
          domain_present boolean := false;
        BEGIN
          IF NEW.command_type NOT IN (
            'family.authority.person.create','family.authority.person.replace',
            'family.authority.person.retire','family.authority.evidence.record',
            'family.authority.evidence.review','family.authority.evidence.reject',
            'family.authority.evidence.invalidate','family.authority.evidence.supersede',
            'child.release.authorization.grant','child.release.authorization.revoke',
            'child.release.rule.create','child.release.rule.revoke',
            'organization.consent.policy.publish','child.consent.record',
            'child.consent.withdraw','attendance.release.checkout'
          ) THEN
            RETURN NULL;
          END IF;

          IF NEW.command_type LIKE 'family.authority.person.%' THEN
            SELECT '/families/' || person.family_id::text || '?authority_person_id='
                     || person.id::text,
                   person.version=NEW.committed_version AND CASE NEW.command_type
                     WHEN 'family.authority.person.create'
                       THEN person.created_operation_id=NEW.client_operation_id
                     WHEN 'family.authority.person.retire'
                       THEN person.retired_operation_id=NEW.client_operation_id
                     ELSE person.last_operation_id=NEW.client_operation_id
                   END
              INTO expected_action_route,domain_present
            FROM public.family_authority_people person
            WHERE person.organization_id=NEW.organization_id AND person.id=NEW.target_id;
          ELSIF NEW.command_type='family.authority.evidence.record' THEN
            SELECT '/families/' || evidence.family_id::text || '?authority_evidence_id='
                     || evidence.id::text,
                   evidence.created_operation_id=NEW.client_operation_id
                     AND evidence.recorded_by_user_id=NEW.actor_user_id
                     AND NEW.committed_version=1
              INTO expected_action_route,domain_present
            FROM public.family_authority_evidence evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.id=NEW.target_id;
          ELSIF NEW.command_type LIKE 'family.authority.evidence.%' THEN
            SELECT '/families/' || assessment.family_id::text || '?authority_evidence_id='
                     || assessment.evidence_id::text,
                   assessment.created_operation_id=NEW.client_operation_id
                     AND assessment.version_number=NEW.committed_version
              INTO expected_action_route,domain_present
            FROM public.family_authority_evidence_assessments assessment
            WHERE assessment.organization_id=NEW.organization_id
              AND assessment.evidence_id=NEW.target_id
              AND assessment.version_number=NEW.committed_version;
          ELSIF NEW.command_type LIKE 'child.release.authorization.%' THEN
            SELECT '/children/' || release_record.child_id::text
                     || '?release_authorization_id=' || release_record.id::text,
                   release_record.version=NEW.committed_version AND CASE
                     WHEN NEW.command_type='child.release.authorization.grant'
                       THEN release_record.created_operation_id=NEW.client_operation_id
                     ELSE release_record.revoked_operation_id=NEW.client_operation_id
                   END
              INTO expected_action_route,domain_present
            FROM public.child_release_authorizations AS release_record
            WHERE release_record.organization_id=NEW.organization_id
              AND release_record.id=NEW.target_id;
          ELSIF NEW.command_type LIKE 'child.release.rule.%' THEN
            SELECT '/children/' || rule.child_id::text || '?release_rule_id='
                     || rule.id::text,
                   rule.version=NEW.committed_version AND CASE
                     WHEN NEW.command_type='child.release.rule.create'
                       THEN rule.created_operation_id=NEW.client_operation_id
                     ELSE rule.revoked_operation_id=NEW.client_operation_id
                   END
              INTO expected_action_route,domain_present
            FROM public.child_release_rules rule
            WHERE rule.organization_id=NEW.organization_id AND rule.id=NEW.target_id;
          ELSIF NEW.command_type='organization.consent.policy.publish' THEN
            SELECT '/consent-policies/' || policy.id::text,
                   policy.version_number=NEW.committed_version
                     AND policy.created_operation_id=NEW.client_operation_id
              INTO expected_action_route,domain_present
            FROM public.consent_policy_versions policy
            WHERE policy.organization_id=NEW.organization_id AND policy.id=NEW.target_id;
          ELSIF NEW.command_type IN ('child.consent.record','child.consent.withdraw') THEN
            SELECT '/children/' || decision.child_id::text || '?consent_id='
                     || decision.id::text,
                   decision.version=NEW.committed_version AND CASE
                     WHEN NEW.command_type='child.consent.record'
                       THEN decision.created_operation_id=NEW.client_operation_id
                     ELSE decision.withdrawn_operation_id=NEW.client_operation_id
                   END
              INTO expected_action_route,domain_present
            FROM public.child_consent_decisions decision
            WHERE decision.organization_id=NEW.organization_id AND decision.id=NEW.target_id;
          ELSE
            SELECT '/attendance/releases/' || snapshot.id::text,
                   snapshot.client_operation_id=NEW.client_operation_id
                     AND NEW.committed_version=1
              INTO expected_action_route,domain_present
            FROM public.attendance_release_snapshots snapshot
            WHERE snapshot.organization_id=NEW.organization_id AND snapshot.id=NEW.target_id;
          END IF;
          IF NOT COALESCE(domain_present,false)
             OR NEW.outcome::jsonb ->> 'action_route'
                IS DISTINCT FROM expected_action_route THEN
            RAISE EXCEPTION 'authority receipt has no exact committed domain row'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_receipt_domain_row';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_receipt_invariant() FROM PUBLIC"
    )

    # The authority kernel contains custody, release, and consent evidence that
    # must not become visible merely because a query carries the right tenant
    # setting.  This predicate binds every 0029A RLS policy to the authenticated
    # actor setting and an active privileged membership.  This is defense in
    # depth for the API's authenticated transaction-local GUC context; it does
    # not turn the shared runtime credential into a per-user database identity.
    # A narrow session-user owner bypass keeps schema-owner restore/repair
    # workflows possible while FORCE ROW LEVEL SECURITY remains enabled.
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_actor_is_privileged(
          authority_organization_id uuid
        )
        RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $policy$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
          authority_owner name;
        BEGIN
          SELECT pg_catalog.pg_get_userbyid(relation.relowner)
            INTO authority_owner
          FROM pg_catalog.pg_class AS relation
          JOIN pg_catalog.pg_namespace AS namespace
            ON namespace.oid=relation.relnamespace
          WHERE namespace.nspname='public'
            AND relation.relname='family_authority_people'
            AND relation.relkind IN ('r','p');

          IF authority_owner IS NOT NULL AND session_user::name=authority_owner THEN
            RETURN true;
          END IF;

          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
          EXCEPTION
            WHEN invalid_text_representation THEN
              RETURN false;
          END;

          IF authority_organization_id IS NULL
             OR context_organization_id IS NULL
             OR context_user_id IS NULL
             OR authority_organization_id<>context_organization_id THEN
            RETURN false;
          END IF;

          RETURN EXISTS (
            SELECT 1
            FROM public.organization_memberships AS membership
            JOIN public.roles AS role
              ON role.organization_id=membership.organization_id
             AND role.id=membership.role_id
            WHERE membership.organization_id=context_organization_id
              AND membership.user_id=context_user_id
              AND membership.status='active'
              AND role.key IN ('owner','administrator')
          );
        END
        $policy$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_actor_is_privileged(uuid) FROM PUBLIC"
    )
    op.execute(
        """
        DO $policy_grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app') THEN
            GRANT EXECUTE ON FUNCTION
              public.caresync_family_authority_actor_is_privileged(uuid)
            TO caresync_basic_app;
          END IF;
        END
        $policy_grant$
        """
    )

    op.execute(
        "CREATE TRIGGER trg_childcare_command_receipts_authority_guard "
        "BEFORE INSERT ON public.childcare_command_receipts FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_family_authority_receipt_guard()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_childcare_command_receipts_authority_invariant "
        "AFTER INSERT ON public.childcare_command_receipts DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_family_authority_receipt_invariant()"
    )

    for table_name in AUTHORITY_TABLES:
        op.execute(
            f'CREATE TRIGGER "trg_{table_name}_insert_guard" '
            f'BEFORE INSERT ON public."{table_name}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_family_authority_insert_guard()"
        )
        op.execute(
            f'CREATE TRIGGER "trg_{table_name}_transition_guard" '
            f'BEFORE UPDATE OR DELETE ON public."{table_name}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_family_authority_transition_guard()"
        )
    for table_name in (
        "child_release_authorizations",
        "child_release_rules",
        "consent_policy_versions",
        "child_consent_decisions",
    ):
        op.execute(
            f'CREATE TRIGGER "trg_{table_name}_temporal_guard" '
            f'BEFORE INSERT ON public."{table_name}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_family_authority_temporal_guard()"
        )
    for table_name in (
        "family_authority_people",
        "family_authority_person_versions",
    ):
        op.execute(
            f'CREATE CONSTRAINT TRIGGER "trg_{table_name}_person_invariant" '
            f'AFTER INSERT OR UPDATE ON public."{table_name}" DEFERRABLE INITIALLY DEFERRED '
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_family_authority_person_invariant()"
        )
    for table_name in (
        "child_release_authorizations",
        "child_release_rules",
        "child_consent_decisions",
    ):
        op.execute(
            f'CREATE CONSTRAINT TRIGGER "trg_{table_name}_revision_invariant" '
            f'AFTER INSERT OR UPDATE ON public."{table_name}" DEFERRABLE INITIALLY DEFERRED '
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_family_authority_child_revision_invariant()"
        )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_family_authority_evidence_assessments_invariant "
        "AFTER INSERT ON public.family_authority_evidence_assessments "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_family_authority_evidence_invariant()"
    )

    for table_name in AUTHORITY_TABLES:
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_privileged_actor" ON public."{table_name}" '
            "USING (public.caresync_family_authority_actor_is_privileged(organization_id)) "
            "WITH CHECK (public.caresync_family_authority_actor_is_privileged(organization_id))"
        )

    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE ALL ON TABLE
              public.family_authority_people,
              public.family_authority_person_versions,
              public.family_authority_evidence,
              public.family_authority_evidence_assessments,
              public.child_authority_heads,
              public.child_release_authorizations,
              public.child_release_rules,
              public.consent_policy_versions,
              public.child_consent_decisions,
              public.attendance_release_snapshots
            FROM caresync_basic_app;
            GRANT SELECT ON TABLE
              public.family_authority_people,
              public.family_authority_person_versions,
              public.family_authority_evidence,
              public.family_authority_evidence_assessments,
              public.child_authority_heads,
              public.child_release_authorizations,
              public.child_release_rules,
              public.consent_policy_versions,
              public.child_consent_decisions,
              public.attendance_release_snapshots
            TO caresync_basic_app;
            GRANT INSERT ON TABLE
              public.family_authority_people,
              public.family_authority_person_versions,
              public.family_authority_evidence,
              public.family_authority_evidence_assessments,
              public.child_authority_heads
            TO caresync_basic_app;
            GRANT UPDATE (
              version,status,current_person_version_id,last_operation_id,
              retired_at,retired_operation_id,updated_at
            ) ON TABLE public.family_authority_people TO caresync_basic_app;
            GRANT UPDATE (closed_at,closed_operation_id)
              ON TABLE public.family_authority_person_versions TO caresync_basic_app;
            GRANT UPDATE (revision,last_operation_id,updated_at)
              ON TABLE public.child_authority_heads TO caresync_basic_app;
          END IF;
        END $grants$
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    _refuse_unsafe_sqlite_multirevision_downgrade(bind)
    preflight_tables = (*AUTHORITY_TABLES, "childcare_command_receipts")
    if bind.dialect.name == "postgresql":
        for table_name in preflight_tables:
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    table_counts = {
        table_name: bind.execute(sa.text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
        for table_name in AUTHORITY_TABLES
    }
    target_receipt_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM childcare_command_receipts WHERE target_type IN "
            "('authority_person','authority_evidence','release_authorization',"
            "'release_rule','consent','attendance_release')"
        )
    ).scalar_one()
    command_receipt_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM childcare_command_receipts WHERE "
            "command_type LIKE 'family.authority.%' OR "
            "command_type LIKE 'child.release.%' OR "
            "command_type LIKE 'child.consent.%' OR "
            "command_type LIKE 'organization.consent.%' OR "
            "command_type LIKE 'attendance.release.%'"
        )
    ).scalar_one()
    populated = {name: count for name, count in table_counts.items() if count}
    if populated or target_receipt_count or command_receipt_count:
        if bind.dialect.name == "postgresql":
            for table_name in preflight_tables:
                op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
                op.execute(f'ALTER TABLE public."{table_name}" FORCE ROW LEVEL SECURITY')
        raise RuntimeError(
            "0029A family authority downgrade refused because reviewed authority, "
            "release history, or command provenance cannot be represented by 0028: "
            f"tables={populated}, target_receipts={target_receipt_count}, "
            f"command_receipts={command_receipt_count}"
        )

    # Break the deliberately deferred person/current-version cycle first.
    with op.batch_alter_table("family_authority_people") as batch:
        batch.drop_constraint("fk_authority_people_current_version", type_="foreignkey")

    for table_name in (
        "attendance_release_snapshots",
        "child_consent_decisions",
        "child_release_rules",
        "child_release_authorizations",
        "child_authority_heads",
        "family_authority_evidence_assessments",
        "family_authority_evidence",
        "consent_policy_versions",
        "family_authority_person_versions",
        "family_authority_people",
    ):
        op.drop_table(table_name)

    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER trg_childcare_command_receipts_authority_invariant "
            "ON public.childcare_command_receipts"
        )
        op.execute(
            "DROP TRIGGER trg_childcare_command_receipts_authority_guard "
            "ON public.childcare_command_receipts"
        )
        for function_name in (
            "caresync_family_authority_actor_is_privileged",
            "caresync_family_authority_receipt_invariant",
            "caresync_family_authority_receipt_guard",
            "caresync_family_authority_evidence_invariant",
            "caresync_family_authority_child_revision_invariant",
            "caresync_family_authority_person_invariant",
            "caresync_family_authority_temporal_guard",
            "caresync_family_authority_transition_guard",
            "caresync_family_authority_insert_guard",
        ):
            signature = "(uuid)" if function_name == "caresync_family_authority_actor_is_privileged" else "()"
            op.execute(f"DROP FUNCTION public.{function_name}{signature}")

    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            "target_type IN ('family','child','enrollment')",
        )

    for table_name, constraint_name in (
        ("attendance_events", "uq_attendance_events_release_identity"),
        ("attendance_intervals", "uq_attendance_intervals_release_identity"),
        ("attendance_days", "uq_attendance_days_release_identity"),
        ("emergency_contacts", "uq_contacts_org_family_id"),
        ("guardians", "uq_guardians_org_family_id"),
        ("children", "uq_children_org_family_id"),
    ):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(constraint_name, type_="unique")

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.childcare_command_receipts ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.childcare_command_receipts FORCE ROW LEVEL SECURITY")

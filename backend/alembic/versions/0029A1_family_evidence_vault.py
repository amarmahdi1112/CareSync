"""Add the private family-authority evidence object vault.

Revision ID: 0029A1_family_evidence_vault
Revises: 0029A_family_authority_kernel
Create Date: 2026-07-17

The object row records the exact server-observed upload.  Scan decisions are
append-only and the only mutable object field is its one-way quarantine status.
"""

# The checks intentionally remain literal and portable so Alembic can compare
# this revision with ``BasicBase.metadata`` on both SQLite and PostgreSQL.
# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

revision = "0029A1_family_evidence_vault"
down_revision = "0029A_family_authority_kernel"
branch_labels = None
depends_on = None


EVIDENCE_OBJECT_TABLES = (
    "family_authority_evidence_objects",
    "family_authority_evidence_object_assessments",
)


def _lowercase_sha256_check(column_name: str) -> str:
    """Return the portable part of the server-owned SHA-256 check.

    PostgreSQL's write guard below applies the hexadecimal regular expression.
    Keeping this table check shallow matters on SQLite: deeply nested ``replace``
    expressions can create a database that upgrades successfully but later fails
    schema parsing with ``parser stack overflow``.
    """

    expression = (
        f"length({column_name}) = 64 AND {column_name} = lower({column_name}) "
        f"AND {column_name} NOT LIKE '% %'"
    )
    if op.get_bind().dialect.name == "sqlite":
        expression += f" AND {column_name} NOT GLOB '*[^0-9a-f]*'"
    return expression


def _opaque_storage_reference_check(column_name: str) -> str:
    """Return a shallow, portable traversal check for an opaque server key."""

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
    """Constrain media type to the three formats accepted by the vault."""

    return f"{column_name} IN ('application/pdf','image/jpeg','image/png')"


def _preflight_legacy_evidence_media() -> None:
    """Refuse unsupported predecessor metadata before the first schema write."""

    unsupported = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM family_authority_evidence "
            "WHERE media_type IS NOT NULL AND media_type NOT IN "
            "('application/pdf','image/jpeg','image/png')"
        )
    ).scalar_one()
    if unsupported:
        raise RuntimeError(
            "0029A1 upgrade refused before DDL: predecessor authority evidence "
            f"contains {unsupported} unsupported media row(s)"
        )


def upgrade() -> None:
    _preflight_legacy_evidence_media()
    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            "target_type IN ('family','child','enrollment','authority_person',"
            "'authority_evidence','authority_evidence_object','release_authorization',"
            "'release_rule','consent','attendance_release')",
        )

    op.create_table(
        "family_authority_evidence_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("object_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="quarantined", nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('identity_document','custody_document','court_order','signed_consent','other_document')",
            name="ck_authority_evidence_objects_kind",
        ),
        sa.CheckConstraint(
            "object_version = 1",
            name="ck_authority_evidence_objects_version",
        ),
        sa.CheckConstraint(
            "status IN ('quarantined','clean','rejected')",
            name="ck_authority_evidence_objects_status",
        ),
        sa.CheckConstraint(
            _opaque_storage_reference_check("storage_reference"),
            name="ck_authority_evidence_objects_reference",
        ),
        sa.CheckConstraint(
            _media_type_check("media_type"),
            name="ck_authority_evidence_objects_media_type",
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 1 AND 52428800",
            name="ck_authority_evidence_objects_byte_size",
        ),
        sa.CheckConstraint(
            _lowercase_sha256_check("content_sha256"),
            name="ck_authority_evidence_objects_sha256",
        ),
        sa.CheckConstraint(
            "original_filename IS NULL OR length(trim(original_filename)) BETWEEN 1 AND 255",
            name="ck_authority_evidence_objects_filename",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id"],
            ["families.organization_id", "families.id"],
            name="fk_authority_evidence_objects_family",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_authority_evidence_objects_uploader",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_authority_evidence_objects_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_evidence_objects_upload_op",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_authority_evidence_objects_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "id",
            name="uq_authority_evidence_objects_org_family_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "uploaded_operation_id",
            name="uq_authority_evidence_objects_upload_op",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "storage_reference",
            name="uq_authority_evidence_objects_reference",
        ),
    )
    op.create_index(
        "ix_authority_evidence_objects_family_status",
        "family_authority_evidence_objects",
        ["organization_id", "family_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_objects_family_id"),
        "family_authority_evidence_objects",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_objects_organization_id"),
        "family_authority_evidence_objects",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "family_authority_evidence_object_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_object_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("scanner_engine", sa.String(length=80), nullable=True),
        sa.Column("scanner_version", sa.String(length=160), nullable=True),
        sa.Column("scanner_signature", sa.String(length=160), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(version_number = 1 AND decision = 'quarantined' AND scanner_engine IS NULL AND scanner_version IS NULL AND scanner_signature IS NULL AND reason_code IS NULL) OR (version_number = 2 AND decision = 'clean' AND scanner_engine IS NOT NULL AND length(trim(scanner_engine)) > 0 AND scanner_version IS NOT NULL AND length(trim(scanner_version)) > 0 AND scanner_signature IS NULL AND reason_code IS NULL) OR (version_number = 2 AND decision = 'rejected' AND scanner_engine IS NOT NULL AND length(trim(scanner_engine)) > 0 AND scanner_version IS NOT NULL AND length(trim(scanner_version)) > 0 AND (scanner_signature IS NULL OR length(trim(scanner_signature)) > 0) AND reason_code IN ('malware_detected','invalid_document'))",
            name="ck_authority_object_assessments_transition",
        ),
        sa.CheckConstraint(
            "decision IN ('quarantined','clean','rejected')",
            name="ck_authority_object_assessments_decision",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "family_id", "evidence_object_id"],
            [
                "family_authority_evidence_objects.organization_id",
                "family_authority_evidence_objects.family_id",
                "family_authority_evidence_objects.id",
            ],
            name="fk_authority_object_assessments_object",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_authority_object_assessments_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_authority_object_assessments_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_authority_object_assessments_operation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_authority_object_assessments_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "family_id",
            "evidence_object_id",
            "id",
            name="uq_authority_object_assessments_identity",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "evidence_object_id",
            "version_number",
            name="uq_authority_object_assessments_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_authority_object_assessments_operation",
        ),
    )
    op.create_index(
        "ix_authority_object_assessments_current",
        "family_authority_evidence_object_assessments",
        ["organization_id", "evidence_object_id", "version_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_object_assessments_family_id"),
        "family_authority_evidence_object_assessments",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_object_assessments_organization_id"),
        "family_authority_evidence_object_assessments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_family_authority_evidence_object_assessments_evidence_object_id"),
        "family_authority_evidence_object_assessments",
        ["evidence_object_id"],
        unique=False,
    )

    with op.batch_alter_table("family_authority_evidence") as batch:
        # 0029A's portable allowlist checks were expressed as very deeply
        # nested replace() calls. SQLite accepts that CREATE TABLE statement
        # but subsequently reports a parser-stack overflow while reading the
        # schema. Rebuild those three checks here with shallow equivalents;
        # the new object FK plus server-owned copy is the stronger authority.
        batch.drop_constraint(
            "ck_authority_evidence_storage_reference", type_="check"
        )
        batch.drop_constraint("ck_authority_evidence_media_type", type_="check")
        batch.drop_constraint("ck_authority_evidence_sha256", type_="check")
        batch.add_column(sa.Column("evidence_object_id", sa.Uuid(), nullable=True))
        batch.create_check_constraint(
            "ck_authority_evidence_storage_reference",
            _opaque_storage_reference_check("storage_reference"),
        )
        batch.create_check_constraint(
            "ck_authority_evidence_media_type",
            "media_type IS NULL OR " + _media_type_check("media_type"),
        )
        batch.create_check_constraint(
            "ck_authority_evidence_sha256",
            "content_sha256 IS NULL OR ("
            + _lowercase_sha256_check("content_sha256")
            + ")",
        )
        batch.create_foreign_key(
            "fk_authority_evidence_object",
            "family_authority_evidence_objects",
            ["organization_id", "family_id", "evidence_object_id"],
            ["organization_id", "family_id", "id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "uq_authority_evidence_object",
        "family_authority_evidence",
        ["organization_id", "evidence_object_id"],
        unique=True,
        postgresql_where=sa.text("evidence_object_id IS NOT NULL"),
        sqlite_where=sa.text("evidence_object_id IS NOT NULL"),
    )

    if op.get_bind().dialect.name == "postgresql":
        _install_postgres_vault_guards()


def _install_postgres_vault_guards() -> None:
    _install_postgres_receipt_functions(include_evidence_objects=True)

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_evidence_object_write_guard()
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
          allowed_change boolean;
        BEGIN
          IF TG_OP <> 'DELETE' AND NOT isfinite(NEW.created_at) THEN
            RAISE EXCEPTION 'family evidence object timestamp must be finite'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_timestamp_finite';
          END IF;
          IF TG_TABLE_NAME='family_authority_evidence_objects'
             AND TG_OP<>'DELETE'
             AND to_jsonb(NEW) ->> 'content_sha256' !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'family evidence object digest is not lowercase hexadecimal'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_objects_sha256_hex';
          END IF;

          IF session_user <> 'caresync_basic_app' THEN
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
          END IF;
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'family evidence object history cannot be deleted'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_history_immutable';
          END IF;

          context_organization:=NULLIF(
            current_setting('app.current_organization_id', true), ''
          )::uuid;
          context_actor:=NULLIF(
            current_setting('app.current_user_id', true), ''
          )::uuid;
          context_operation:=NULLIF(
            current_setting('app.current_childcare_operation_id', true), ''
          )::uuid;
          IF context_organization IS NULL OR context_actor IS NULL
             OR context_operation IS NULL
             OR NEW.organization_id<>context_organization THEN
            RAISE EXCEPTION 'family evidence object write does not match locked context'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_locked_context';
          END IF;

          SELECT receipt.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt
          WHERE receipt.organization_id=context_organization
            AND receipt.client_operation_id=context_operation
            AND receipt.actor_user_id=context_actor
            AND receipt.xmin=pg_current_xact_id()::text::xid;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'family evidence object write requires a current receipt'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_current_receipt';
          END IF;

          IF TG_TABLE_NAME='family_authority_evidence_objects' AND TG_OP='INSERT' THEN
            IF NEW.object_version<>1 OR NEW.status<>'quarantined'
               OR NEW.uploaded_by_user_id<>context_actor
               OR NEW.uploaded_operation_id<>context_operation
               OR command_receipt.command_type<>
                  'family.authority.evidence_object.upload'
               OR command_receipt.target_type<>'authority_evidence_object'
               OR command_receipt.target_id<>NEW.id
               OR command_receipt.committed_version<>1 THEN
              RAISE EXCEPTION 'family evidence upload provenance is not exact'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_evidence_object_upload_provenance';
            END IF;
          ELSIF TG_TABLE_NAME='family_authority_evidence_objects' AND TG_OP='UPDATE' THEN
            allowed_change:=(to_jsonb(NEW)-'status')=(to_jsonb(OLD)-'status');
            IF NOT allowed_change OR OLD.status<>'quarantined'
               OR NEW.status NOT IN ('clean','rejected')
               OR command_receipt.command_type<>
                  'family.authority.evidence_object.scan'
               OR command_receipt.target_type<>'authority_evidence_object'
               OR command_receipt.target_id<>OLD.id
               OR command_receipt.committed_version<>2 THEN
              RAISE EXCEPTION 'family evidence object transition is not exact'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_evidence_object_transition';
            END IF;
          ELSIF TG_TABLE_NAME='family_authority_evidence_object_assessments'
                AND TG_OP='INSERT' THEN
            IF NEW.actor_user_id<>context_actor
               OR NEW.operation_id<>context_operation
               OR command_receipt.target_type<>'authority_evidence_object'
               OR command_receipt.target_id<>NEW.evidence_object_id
               OR command_receipt.committed_version<>NEW.version_number
               OR command_receipt.command_type<>(CASE NEW.version_number
                    WHEN 1 THEN 'family.authority.evidence_object.upload'
                    WHEN 2 THEN 'family.authority.evidence_object.scan'
                    ELSE NULL
                  END) THEN
              RAISE EXCEPTION 'family evidence assessment provenance is not exact'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_evidence_object_assessment_provenance';
            END IF;
          ELSE
            RAISE EXCEPTION 'family evidence assessments are append-only'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_assessment_immutable';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_evidence_object_write_guard() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_evidence_object_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          object_id uuid;
          object_row public.family_authority_evidence_objects%ROWTYPE;
          upload_assessment public.family_authority_evidence_object_assessments%ROWTYPE;
          scan_assessment public.family_authority_evidence_object_assessments%ROWTYPE;
        BEGIN
          object_id:=(to_jsonb(NEW) ->> CASE TG_TABLE_NAME
            WHEN 'family_authority_evidence_objects' THEN 'id'
            ELSE 'evidence_object_id'
          END)::uuid;
          SELECT object_value.* INTO object_row
          FROM public.family_authority_evidence_objects AS object_value
          WHERE object_value.organization_id=NEW.organization_id
            AND object_value.id=object_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'family evidence object invariant has no object'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_assessment_chain';
          END IF;

          SELECT assessment.* INTO upload_assessment
          FROM public.family_authority_evidence_object_assessments AS assessment
          WHERE assessment.organization_id=object_row.organization_id
            AND assessment.evidence_object_id=object_row.id
            AND assessment.version_number=1;
          IF NOT FOUND OR upload_assessment.decision<>'quarantined'
             OR upload_assessment.actor_user_id<>object_row.uploaded_by_user_id
             OR upload_assessment.operation_id<>object_row.uploaded_operation_id THEN
            RAISE EXCEPTION 'family evidence object has no exact upload assessment'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_assessment_chain';
          END IF;

          SELECT assessment.* INTO scan_assessment
          FROM public.family_authority_evidence_object_assessments AS assessment
          WHERE assessment.organization_id=object_row.organization_id
            AND assessment.evidence_object_id=object_row.id
            AND assessment.version_number=2;
          IF object_row.status='quarantined' AND FOUND THEN
            RAISE EXCEPTION 'quarantined evidence object cannot have a terminal scan'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_assessment_chain';
          ELSIF object_row.status IN ('clean','rejected')
                AND (NOT FOUND OR scan_assessment.decision<>object_row.status
                  OR scan_assessment.operation_id=object_row.uploaded_operation_id
                  OR scan_assessment.created_at<upload_assessment.created_at) THEN
            RAISE EXCEPTION 'terminal evidence object has no exact scan assessment'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_evidence_object_assessment_chain';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_evidence_object_invariant() FROM PUBLIC"
    )

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_evidence_object_link_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          link_is_current boolean := false;
          measured_reference text;
          measured_media_type text;
          measured_byte_size bigint;
          measured_sha256 character(64);
        BEGIN
          IF NEW.evidence_kind IN (
            'identity_document','custody_document','court_order',
            'signed_consent','other_document'
          ) THEN
            IF NEW.evidence_object_id IS NULL THEN
              RAISE EXCEPTION 'document evidence requires one clean object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_object_link';
            END IF;

            SELECT true,object_value.storage_reference,object_value.media_type,
                   object_value.byte_size,object_value.content_sha256
              INTO link_is_current,measured_reference,measured_media_type,
                   measured_byte_size,measured_sha256
            FROM public.family_authority_evidence_objects AS object_value
            JOIN public.family_authority_evidence_object_assessments AS assessment
              ON assessment.organization_id=object_value.organization_id
             AND assessment.family_id=object_value.family_id
             AND assessment.evidence_object_id=object_value.id
             AND assessment.version_number=2
             AND assessment.decision='clean'
            WHERE object_value.organization_id=NEW.organization_id
              AND object_value.family_id=NEW.family_id
              AND object_value.id=NEW.evidence_object_id
              AND object_value.evidence_kind=NEW.evidence_kind
              AND object_value.status='clean';
            IF NOT COALESCE(link_is_current,false) THEN
              RAISE EXCEPTION 'document evidence object is not clean and current'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_object_link';
            END IF;

            IF TG_ARGV[0]='prepare' THEN
              IF NEW.storage_reference IS NULL OR NEW.media_type IS NULL
                 OR NEW.byte_size IS NULL OR NEW.content_sha256 IS NULL
                 OR NEW.storage_reference<>measured_reference
                 OR NEW.media_type<>measured_media_type
                 OR NEW.byte_size<>measured_byte_size
                 OR NEW.content_sha256<>measured_sha256 THEN
                RAISE EXCEPTION 'document evidence tuple is not the measured object tuple'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_authority_evidence_object_link';
              END IF;
              -- The locked 0029A guard deliberately rejects runtime-authored
              -- storage claims.  Clear them before that trigger, then restore
              -- the exact server-owned tuple in the final trigger below.
              NEW.storage_reference:=NULL;
              NEW.media_type:=NULL;
              NEW.byte_size:=NULL;
              NEW.content_sha256:=NULL;
            ELSE
              NEW.storage_reference:=measured_reference;
              NEW.media_type:=measured_media_type;
              NEW.byte_size:=measured_byte_size;
              NEW.content_sha256:=measured_sha256;
            END IF;
          ELSIF NEW.evidence_object_id IS NOT NULL
                OR NEW.storage_reference IS NOT NULL
                OR NEW.media_type IS NOT NULL
                OR NEW.byte_size IS NOT NULL
                OR NEW.content_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'attestation and witness evidence cannot carry an object'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_object_link';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_evidence_object_link_guard() FROM PUBLIC"
    )
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_evidence_review_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          evidence_row public.family_authority_evidence%ROWTYPE;
          uploader_user_id uuid;
        BEGIN
          IF NEW.version_number<>2 OR NEW.decision<>'reviewed' THEN
            RETURN NEW;
          END IF;

          SELECT evidence.* INTO evidence_row
          FROM public.family_authority_evidence AS evidence
          WHERE evidence.organization_id=NEW.organization_id
            AND evidence.family_id=NEW.family_id
            AND evidence.id=NEW.evidence_id
          FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'reviewed evidence is missing'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_asset';
          END IF;

          IF evidence_row.recorded_by_user_id=NEW.actor_user_id THEN
            RAISE EXCEPTION 'evidence review requires a distinct maker and checker'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_maker_checker';
          END IF;

          IF evidence_row.evidence_kind IN (
            'identity_document','custody_document','court_order',
            'signed_consent','other_document'
          ) THEN
            IF NEW.assessed_epistemic_status IS DISTINCT FROM 'document_observed'
               OR evidence_row.evidence_object_id IS NULL THEN
              RAISE EXCEPTION 'document evidence requires an observed clean object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_review_epistemic_kind';
            END IF;
            SELECT object_value.uploaded_by_user_id INTO uploader_user_id
            FROM public.family_authority_evidence_objects AS object_value
            JOIN public.family_authority_evidence_object_assessments AS assessment
              ON assessment.organization_id=object_value.organization_id
             AND assessment.family_id=object_value.family_id
             AND assessment.evidence_object_id=object_value.id
             AND assessment.version_number=2
             AND assessment.decision='clean'
            WHERE object_value.organization_id=evidence_row.organization_id
              AND object_value.family_id=evidence_row.family_id
              AND object_value.id=evidence_row.evidence_object_id
              AND object_value.evidence_kind=evidence_row.evidence_kind
              AND object_value.status='clean'
            FOR UPDATE OF object_value;
            IF uploader_user_id IS NULL THEN
              RAISE EXCEPTION 'document evidence object is not clean and current'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_review_object';
            ELSIF uploader_user_id=NEW.actor_user_id THEN
              RAISE EXCEPTION 'evidence uploader cannot approve their own object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_maker_checker';
            END IF;
          ELSIF NEW.assessed_epistemic_status IS DISTINCT FROM 'reported'
                OR evidence_row.evidence_object_id IS NOT NULL THEN
            RAISE EXCEPTION 'reported evidence cannot claim document observation'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_epistemic_kind';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_evidence_review_guard() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER trg_family_authority_evidence_aaa_object_link_guard "
        "BEFORE INSERT ON public.family_authority_evidence FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_family_evidence_object_link_guard('prepare')"
    )
    op.execute(
        "CREATE TRIGGER trg_family_authority_evidence_zzz_object_link_guard "
        "BEFORE INSERT ON public.family_authority_evidence FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_family_evidence_object_link_guard('finalize')"
    )
    op.execute(
        "CREATE TRIGGER trg_family_authority_evidence_assessments_review_guard "
        "BEFORE INSERT ON public.family_authority_evidence_assessments FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_family_evidence_review_guard()"
    )

    for table_name in EVIDENCE_OBJECT_TABLES:
        op.execute(
            f'CREATE TRIGGER "trg_{table_name}_write_guard" '
            f'BEFORE INSERT OR UPDATE OR DELETE ON public."{table_name}" '
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_family_evidence_object_write_guard()"
        )
        op.execute(
            f'CREATE CONSTRAINT TRIGGER "trg_{table_name}_invariant" '
            f'AFTER INSERT OR UPDATE ON public."{table_name}" '
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_family_evidence_object_invariant()"
        )
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_privileged_actor" '
            f'ON public."{table_name}" '
            "USING (public.caresync_family_authority_actor_is_privileged(organization_id)) "
            "WITH CHECK (public.caresync_family_authority_actor_is_privileged(organization_id))"
        )

    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE ALL ON TABLE
              public.family_authority_evidence_objects,
              public.family_authority_evidence_object_assessments
            FROM caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE
              public.family_authority_evidence_objects,
              public.family_authority_evidence_object_assessments
            TO caresync_basic_app;
            GRANT UPDATE (status) ON TABLE
              public.family_authority_evidence_objects
            TO caresync_basic_app;
          END IF;
        END $grants$
        """
    )


def _install_postgres_receipt_functions(*, include_evidence_objects: bool) -> None:
    object_command_list = (
        "'family.authority.evidence_object.upload',"
        "'family.authority.evidence_object.scan',"
        if include_evidence_objects
        else ""
    )
    object_target_list = "'authority_evidence_object'," if include_evidence_objects else ""
    object_target_case = (
        "WHEN NEW.command_type LIKE 'family.authority.evidence_object.%' "
        "THEN 'authority_evidence_object'"
        if include_evidence_objects
        else ""
    )
    object_version_one = (
        "'family.authority.evidence_object.upload'," if include_evidence_objects else ""
    )
    object_version_two = (
        ",'family.authority.evidence_object.scan'" if include_evidence_objects else ""
    )
    object_route_check = (
        "OR (NEW.command_type LIKE 'family.authority.evidence_object.%' AND "
        "action_route !~ ('^/families/[0-9a-f-]{36}\\?authority_evidence_object_id=' "
        "|| NEW.target_id::text || '$'))"
        if include_evidence_objects
        else ""
    )
    evidence_route_predicate = (
        "NEW.command_type IN ("
        "'family.authority.evidence.record','family.authority.evidence.review',"
        "'family.authority.evidence.reject','family.authority.evidence.invalidate',"
        "'family.authority.evidence.supersede')"
        if include_evidence_objects
        else "NEW.command_type LIKE 'family.authority.evidence.%'"
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.caresync_family_authority_receipt_guard()
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
            {object_command_list}
            'child.release.authorization.grant','child.release.authorization.revoke',
            'child.release.rule.create','child.release.rule.revoke',
            'organization.consent.policy.publish','child.consent.record',
            'child.consent.withdraw','attendance.release.checkout'
          ) THEN
            IF NEW.target_type IN (
              'authority_person','authority_evidence',{object_target_list}
              'release_authorization','release_rule','consent','attendance_release'
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
             OR NEW.request_hash !~ '^[0-9a-f]{{64}}$'
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
            {object_target_case}
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
              {object_version_one}
              'child.release.authorization.grant','child.release.rule.create',
              'child.consent.record','attendance.release.checkout'
            ) THEN 1
            WHEN NEW.command_type IN (
              'family.authority.evidence.review','family.authority.evidence.reject'
              {object_version_two}
            ) THEN 2
            WHEN NEW.command_type IN (
              'family.authority.evidence.invalidate','family.authority.evidence.supersede'
            ) THEN 3
            ELSE NULL
          END;
          IF NEW.target_type<>expected_target_type
             OR (expected_version IS NOT NULL AND NEW.committed_version<>expected_version)
             OR (NEW.command_type LIKE 'family.authority.person.%' AND
               action_route !~ ('^/families/[0-9a-f-]{{36}}\\?authority_person_id='
                 || NEW.target_id::text || '$'))
             {object_route_check}
             OR ({evidence_route_predicate} AND
               action_route !~ ('^/families/[0-9a-f-]{{36}}\\?authority_evidence_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type LIKE 'child.release.authorization.%' AND
               action_route !~ ('^/children/[0-9a-f-]{{36}}\\?release_authorization_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type LIKE 'child.release.rule.%' AND
               action_route !~ ('^/children/[0-9a-f-]{{36}}\\?release_rule_id='
                 || NEW.target_id::text || '$'))
             OR (NEW.command_type IN ('child.consent.record','child.consent.withdraw') AND
               action_route !~ ('^/children/[0-9a-f-]{{36}}\\?consent_id='
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

    object_invariant_branch = (
        """
          ELSIF NEW.command_type='family.authority.evidence_object.upload' THEN
            SELECT '/families/' || object_value.family_id::text
                     || '?authority_evidence_object_id=' || object_value.id::text,
                   object_value.uploaded_operation_id=NEW.client_operation_id
                     AND object_value.uploaded_by_user_id=NEW.actor_user_id
                     AND object_value.object_version=1
                     AND NEW.committed_version=1
              INTO expected_action_route,domain_present
            FROM public.family_authority_evidence_objects AS object_value
            WHERE object_value.organization_id=NEW.organization_id
              AND object_value.id=NEW.target_id;
          ELSIF NEW.command_type='family.authority.evidence_object.scan' THEN
            SELECT '/families/' || assessment.family_id::text
                     || '?authority_evidence_object_id='
                     || assessment.evidence_object_id::text,
                   assessment.operation_id=NEW.client_operation_id
                     AND assessment.actor_user_id=NEW.actor_user_id
                     AND assessment.version_number=2
                     AND assessment.decision IN ('clean','rejected')
                     AND object_value.status=assessment.decision
                     AND NEW.committed_version=2
              INTO expected_action_route,domain_present
            FROM public.family_authority_evidence_object_assessments AS assessment
            JOIN public.family_authority_evidence_objects AS object_value
              ON object_value.organization_id=assessment.organization_id
             AND object_value.family_id=assessment.family_id
             AND object_value.id=assessment.evidence_object_id
            WHERE assessment.organization_id=NEW.organization_id
              AND assessment.evidence_object_id=NEW.target_id
              AND assessment.version_number=2;
        """
        if include_evidence_objects
        else ""
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.caresync_family_authority_receipt_invariant()
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
            {object_command_list}
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
          {object_invariant_branch}
          ELSIF NEW.command_type='family.authority.evidence.record' THEN
            SELECT '/families/' || evidence.family_id::text || '?authority_evidence_id='
                     || evidence.id::text,
                   evidence.created_operation_id=NEW.client_operation_id
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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        destination_revision = context.get_revision_argument()
        if destination_revision not in {down_revision, "-1"}:
            raise RuntimeError(
                "0029A1 SQLite downgrade refused before DDL: first downgrade "
                "exactly to 0029A_family_authority_kernel, then start a separate "
                "downgrade command"
            )
    if bind.dialect.name == "postgresql":
        for table_name in EVIDENCE_OBJECT_TABLES:
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    populated = {
        table_name: bind.execute(sa.text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
        for table_name in EVIDENCE_OBJECT_TABLES
    }
    populated = {table_name: count for table_name, count in populated.items() if count}
    linked_evidence_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM family_authority_evidence "
            "WHERE evidence_object_id IS NOT NULL"
        )
    ).scalar_one()
    receipt_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM childcare_command_receipts "
            "WHERE target_type='authority_evidence_object' OR command_type IN "
            "('family.authority.evidence_object.upload',"
            "'family.authority.evidence_object.scan')"
        )
    ).scalar_one()
    if populated or linked_evidence_count or receipt_count:
        if bind.dialect.name == "postgresql":
            for table_name in EVIDENCE_OBJECT_TABLES:
                op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
                op.execute(f'ALTER TABLE public."{table_name}" FORCE ROW LEVEL SECURITY')
        raise RuntimeError(
            "0029A1 family evidence vault downgrade refused because immutable "
            "object history cannot be represented by 0029A: "
            f"tables={populated}, linked_evidence={linked_evidence_count}, "
            f"receipts={receipt_count}"
        )

    if bind.dialect.name == "postgresql":
        _install_postgres_receipt_functions(include_evidence_objects=False)
        op.execute(
            "DROP TRIGGER trg_family_authority_evidence_assessments_review_guard "
            "ON public.family_authority_evidence_assessments"
        )
        op.execute(
            "DROP FUNCTION public.caresync_family_evidence_review_guard()"
        )
        for trigger_name in (
            "trg_family_authority_evidence_aaa_object_link_guard",
            "trg_family_authority_evidence_zzz_object_link_guard",
        ):
            op.execute(
                f"DROP TRIGGER {trigger_name} ON public.family_authority_evidence"
            )
        op.execute(
            "DROP FUNCTION public.caresync_family_evidence_object_link_guard()"
        )
        for table_name in EVIDENCE_OBJECT_TABLES:
            op.execute(
                f'DROP TRIGGER "trg_{table_name}_invariant" '
                f'ON public."{table_name}"'
            )
            op.execute(
                f'DROP TRIGGER "trg_{table_name}_write_guard" '
                f'ON public."{table_name}"'
            )
        # Both functions carry dependencies on the object table row types.
        op.execute("DROP FUNCTION public.caresync_family_evidence_object_invariant()")
        op.execute("DROP FUNCTION public.caresync_family_evidence_object_write_guard()")

    op.drop_index(
        "uq_authority_evidence_object",
        table_name="family_authority_evidence",
    )
    with op.batch_alter_table("family_authority_evidence") as batch:
        batch.drop_constraint("fk_authority_evidence_object", type_="foreignkey")
        batch.drop_constraint(
            "ck_authority_evidence_storage_reference", type_="check"
        )
        batch.drop_constraint("ck_authority_evidence_media_type", type_="check")
        batch.drop_constraint("ck_authority_evidence_sha256", type_="check")
        batch.drop_column("evidence_object_id")
        batch.create_check_constraint(
            "ck_authority_evidence_storage_reference",
            _opaque_storage_reference_check("storage_reference"),
        )
        batch.create_check_constraint(
            "ck_authority_evidence_media_type",
            "media_type IS NULL OR " + _media_type_check("media_type"),
        )
        batch.create_check_constraint(
            "ck_authority_evidence_sha256",
            "content_sha256 IS NULL OR ("
            + _lowercase_sha256_check("content_sha256")
            + ")",
        )

    op.drop_table("family_authority_evidence_object_assessments")
    op.drop_table("family_authority_evidence_objects")

    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            "target_type IN ('family','child','enrollment','authority_person',"
            "'authority_evidence','release_authorization','release_rule','consent',"
            "'attendance_release')",
        )

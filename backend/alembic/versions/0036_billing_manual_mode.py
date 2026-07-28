"""Add the immutable private/local manual-billing activation boundary.

Revision ID: 0036_billing_manual_mode
Revises: 0035_release_checkout_activation
Create Date: 2026-07-22

The 0033 synthetic sandbox remains unchanged.  This revision adds a separate,
owner-reviewed organization boundary whose records represent only charges and
payments completed outside CareSync.  It deliberately adds no processor,
delivery, automatic issue, tax, or money-movement capability.
"""

from __future__ import annotations

import hashlib
import re

import sqlalchemy as sa

from alembic import op
from app.basic.models import BillingManualActivation

revision = "0036_billing_manual_mode"
down_revision = "0035_release_checkout_activation"
branch_labels = None
depends_on = None

BUNDLE_TABLES = (
    "billing_accounts",
    "billing_account_payer_versions",
    "billing_rate_plans",
    "billing_rate_plan_versions",
    "billing_agreements",
    "billing_agreement_versions",
    "billing_invoices",
    "billing_invoice_lines",
    "billing_payments",
    "billing_allocations",
    "billing_credits",
    "billing_journal_entries",
    "billing_journal_lines",
)
BASE_BUNDLE_SOURCE_SHA256 = "53a9a0e54c0b35aed704649c94addf323ee471778d727ce4138d9dd34fe2c355"


def _compact_sql(definition: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", " ", definition, flags=re.DOTALL)
    without_lines = re.sub(r"--[^\n]*", " ", without_blocks).lower()
    return "".join(without_lines.split()).replace('"', "")


def _source_hash(definition: str) -> str:
    return hashlib.sha256(_compact_sql(definition).encode("utf-8")).hexdigest()


def _install_source_authorization_view() -> None:
    op.execute(
        """
        CREATE VIEW public.billing_source_authorizations_0036
        WITH (security_invoker=true) AS
          SELECT attestation.id,attestation.organization_id,
                 attestation.source_type,attestation.source_id,
                 attestation.marker,attestation.reason_code,
                 attestation.attested_by_user_id,attestation.attested_at
            FROM public.billing_sandbox_source_attestations AS attestation
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'organization'::varchar(30),organization_record.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.organizations AS organization_record
              ON organization_record.id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'family'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.families AS source
              ON source.organization_id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'guardian'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.guardians AS source
              ON source.organization_id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'child'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.children AS source
              ON source.organization_id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'enrollment'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.enrollments AS source
              ON source.organization_id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'facility'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.facilities AS source
              ON source.organization_id=activation.organization_id
          UNION ALL
          SELECT activation.id,activation.organization_id,
                 'program'::varchar(30),source.id,
                 'TEST_SYNTHETIC_ONLY'::varchar(40),
                 'disposable_test_fixture'::varchar(50),
                 activation.activated_by_user_id,activation.activated_at
            FROM public.billing_manual_activations AS activation
            JOIN public.facility_programs AS source
              ON source.organization_id=activation.organization_id
        """
    )
    op.execute("REVOKE ALL ON public.billing_source_authorizations_0036 FROM PUBLIC")


def _clone_bundle_validator(bind: sa.engine.Connection) -> None:
    base_source = str(
        bind.scalar(
            sa.text(
                "SELECT prosrc FROM pg_catalog.pg_proc "
                "WHERE oid='public.caresync_0033_bundle_validate()'::regprocedure"
            )
        )
        or ""
    )
    if _source_hash(base_source) != BASE_BUNDLE_SOURCE_SHA256:
        raise RuntimeError("0036 refused drifted 0033 billing bundle validator")
    definition = str(
        bind.scalar(
            sa.text(
                "SELECT pg_catalog.pg_get_functiondef("
                "'public.caresync_0033_bundle_validate()'::regprocedure)"
            )
        )
        or ""
    )
    if definition.count("public.billing_sandbox_source_attestations") != 15:
        raise RuntimeError("0036 refused an unknown 0033 source-validation shape")
    manual_definition = definition.replace(
        "caresync_0033_bundle_validate",
        "caresync_0036_bundle_validate",
        1,
    ).replace(
        "public.billing_sandbox_source_attestations",
        "public.billing_source_authorizations_0036",
    )
    op.execute(manual_definition)
    op.execute("REVOKE ALL ON FUNCTION public.caresync_0036_bundle_validate() FROM PUBLIC")
    op.execute(
        """
        DO $revoke$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE ALL ON FUNCTION public.caresync_0036_bundle_validate()
              FROM caresync_basic_app;
          END IF;
        END
        $revoke$
        """
    )
    for table in BUNDLE_TABLES:
        op.execute(f"DROP TRIGGER {table}_0033_bundle ON public.{table}")
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_0033_bundle AFTER INSERT "
            f"ON public.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0036_bundle_validate()"
        )


def _install_postgres_activation_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0036_manual_activation_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
          IF NULLIF(current_setting('app.current_organization_id',true),'')::uuid
               IS DISTINCT FROM NEW.organization_id
             OR NULLIF(current_setting('app.current_user_id',true),'')::uuid
               IS DISTINCT FROM NEW.activated_by_user_id
             OR NOT EXISTS (
               SELECT 1 FROM public.organization_memberships membership
               JOIN public.roles role
                 ON role.organization_id=membership.organization_id
                AND role.id=membership.role_id
              WHERE membership.organization_id=NEW.organization_id
                AND membership.id=NEW.activated_by_membership_id
                AND membership.user_id=NEW.activated_by_user_id
                AND membership.status='active'
                AND role.key='owner'
                AND role.permissions::jsonb @> '["billing:manage"]'::jsonb
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_sandbox_source_attestations source
                WHERE source.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_command_preparations preparation
                WHERE preparation.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_accounts account
                WHERE account.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_rate_plans plan
                WHERE plan.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_agreements agreement
                WHERE agreement.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_invoices invoice
                WHERE invoice.organization_id=NEW.organization_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_payments payment
                WHERE payment.organization_id=NEW.organization_id
             ) THEN
            RAISE EXCEPTION '0036 manual billing activation boundary is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0036_manual_activation_immutable() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
          RAISE EXCEPTION '0036 manual billing activation is immutable'
            USING ERRCODE='23514';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_manual_activations_0036_insert_guard BEFORE INSERT "
        "ON public.billing_manual_activations FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0036_manual_activation_guard()"
    )
    op.execute(
        "CREATE TRIGGER billing_manual_activations_0036_immutable BEFORE UPDATE OR DELETE "
        "ON public.billing_manual_activations FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0036_manual_activation_immutable()"
    )
    for signature in (
        "caresync_0036_manual_activation_guard()",
        "caresync_0036_manual_activation_immutable()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(
            f"""
            DO $revoke$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
                REVOKE ALL ON FUNCTION public.{signature} FROM caresync_basic_app;
              END IF;
            END
            $revoke$
            """
        )


def _install_postgres_rls_and_grants() -> None:
    org = "NULLIF(current_setting('app.current_organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.current_user_id',true),'')::uuid"
    reader = (
        f"organization_id={org} AND EXISTS (SELECT 1 FROM organization_memberships m "
        "JOIN roles r ON r.organization_id=m.organization_id AND r.id=m.role_id "
        f"WHERE m.organization_id={org} AND m.user_id={user} AND m.status='active' "
        "AND r.key IN ('owner','administrator') "
        "AND r.permissions::jsonb @> '[\"billing:read\"]'::jsonb)"
    )
    owner = (
        f"organization_id={org} AND EXISTS (SELECT 1 FROM organization_memberships m "
        "JOIN roles r ON r.organization_id=m.organization_id AND r.id=m.role_id "
        f"WHERE m.organization_id={org} AND m.user_id={user} AND m.status='active' "
        "AND r.key='owner' AND r.permissions::jsonb @> '[\"billing:manage\"]'::jsonb)"
    )
    op.execute("ALTER TABLE public.billing_manual_activations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.billing_manual_activations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY billing_manual_activations_0036_select "
        f"ON public.billing_manual_activations FOR SELECT USING ({reader})"
    )
    op.execute(
        "CREATE POLICY billing_manual_activations_0036_insert "
        f"ON public.billing_manual_activations FOR INSERT WITH CHECK ({owner})"
    )
    op.execute("REVOKE ALL ON public.billing_manual_activations FROM PUBLIC")
    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            GRANT SELECT,INSERT ON public.billing_manual_activations
              TO caresync_basic_app;
            GRANT SELECT ON public.billing_source_authorizations_0036
              TO caresync_basic_app;
            REVOKE UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER
              ON public.billing_manual_activations FROM caresync_basic_app;
          END IF;
        END
        $grants$
        """
    )


def _install_sqlite_invoice_payer_guard(*, allow_manual: bool) -> None:
    sandbox_authorization = (
        "EXISTS (SELECT 1 FROM billing_sandbox_source_attestations attestation WHERE "
        "attestation.organization_id=NEW.organization_id AND "
        "attestation.source_type='guardian' AND "
        "attestation.source_id=NEW.payer_guardian_id AND "
        "attestation.marker='TEST_SYNTHETIC_ONLY' AND "
        "attestation.reason_code='disposable_test_fixture')"
    )
    source_authorization = sandbox_authorization
    if allow_manual:
        source_authorization = (
            "(EXISTS (SELECT 1 FROM billing_manual_activations activation WHERE "
            "activation.organization_id=NEW.organization_id) OR "
            f"{sandbox_authorization})"
        )
    op.execute(
        "CREATE TRIGGER billing_invoices_0033_payer_guard BEFORE INSERT ON billing_invoices "
        "WHEN NOT EXISTS (SELECT 1 FROM billing_account_payer_versions payer_version JOIN "
        "guardians guardian ON guardian.organization_id=payer_version.organization_id AND "
        "guardian.family_id=payer_version.family_id AND guardian.id="
        "payer_version.payer_guardian_id JOIN families family ON family.organization_id="
        "payer_version.organization_id AND family.id=payer_version.family_id WHERE "
        "payer_version.organization_id=NEW.organization_id AND "
        "payer_version.billing_account_id=NEW.billing_account_id AND "
        "payer_version.id=NEW.billing_account_payer_version_id AND "
        "payer_version.family_id=NEW.family_id AND "
        "payer_version.payer_guardian_id=NEW.payer_guardian_id AND "
        "NEW.family_name_snapshot=family.name AND "
        "NEW.payer_name_snapshot=trim(guardian.first_name||' '||guardian.last_name) AND "
        "NEW.payer_email_snapshot IS NULLIF(guardian.email,'') AND "
        "NEW.payer_address_snapshot IS NULLIF(trim(COALESCE(guardian.address||', ','')||"
        "COALESCE(guardian.city||', ','')||COALESCE(guardian.postal_code,''),', '),'') AND "
        f"{source_authorization}) BEGIN "
        "SELECT RAISE(ABORT,'0033 invalid invoice payer snapshot'); END"
    )


def _install_sqlite_guards() -> None:
    op.execute(
        "CREATE TRIGGER billing_manual_activations_0036_insert_guard BEFORE INSERT "
        "ON billing_manual_activations WHEN NOT EXISTS (SELECT 1 FROM "
        "organization_memberships membership JOIN roles role ON role.organization_id="
        "membership.organization_id AND role.id=membership.role_id WHERE "
        "membership.organization_id=NEW.organization_id AND membership.id="
        "NEW.activated_by_membership_id AND membership.user_id=NEW.activated_by_user_id "
        "AND membership.status='active' AND role.key='owner' AND EXISTS (SELECT 1 FROM "
        "json_each(role.permissions) WHERE value='billing:manage')) OR EXISTS (SELECT 1 "
        "FROM billing_sandbox_source_attestations source WHERE source.organization_id="
        "NEW.organization_id) OR EXISTS (SELECT 1 FROM billing_command_preparations "
        "preparation WHERE preparation.organization_id=NEW.organization_id) OR EXISTS "
        "(SELECT 1 FROM billing_accounts account WHERE account.organization_id="
        "NEW.organization_id) BEGIN SELECT RAISE(ABORT,"
        "'0036 invalid manual billing activation'); END"
    )
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER billing_manual_activations_0036_immutable_{operation.lower()} "
            f"BEFORE {operation} ON billing_manual_activations BEGIN SELECT RAISE(ABORT,"
            "'0036 immutable manual billing activation'); END"
        )
    op.execute("DROP TRIGGER billing_invoices_0033_payer_guard")
    _install_sqlite_invoice_payer_guard(allow_manual=True)


def upgrade() -> None:
    bind = op.get_bind()
    BillingManualActivation.__table__.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        _install_postgres_activation_guards()
        _install_source_authorization_view()
        _install_postgres_rls_and_grants()
        _clone_bundle_validator(bind)
    else:
        _install_sqlite_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bool(
        bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM billing_manual_activations LIMIT 1)"))
    ):
        raise RuntimeError("0036 downgrade refused: manual billing is activated")
    if bind.dialect.name == "postgresql":
        for table in BUNDLE_TABLES:
            op.execute(f"DROP TRIGGER {table}_0033_bundle ON public.{table}")
            op.execute(
                f"CREATE CONSTRAINT TRIGGER {table}_0033_bundle AFTER INSERT "
                f"ON public.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION public.caresync_0033_bundle_validate()"
            )
        op.execute("DROP VIEW public.billing_source_authorizations_0036")
        for signature in (
            "caresync_0036_bundle_validate()",
            "caresync_0036_manual_activation_guard()",
            "caresync_0036_manual_activation_immutable()",
        ):
            op.execute(f"DROP FUNCTION public.{signature}")
    else:
        op.execute("DROP TRIGGER billing_invoices_0033_payer_guard")
        _install_sqlite_invoice_payer_guard(allow_manual=False)
    BillingManualActivation.__table__.drop(bind, checkfirst=False)

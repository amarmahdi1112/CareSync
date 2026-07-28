"""Add the synthetic-only append-only CAD billing ledger.

Revision ID: 0033_billing_ledger
Revises: 0032_transport_commands
Create Date: 2026-07-22

This is a source-only sandbox boundary.  It cannot move money, calculate tax,
or issue a real invoice.  Runtime writes are additionally gated by application
configuration and immutable synthetic-source attestations.
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    BillingAccount,
    BillingAccountPayerVersion,
    BillingAgreement,
    BillingAgreementVersion,
    BillingAllocation,
    BillingCommandClaim,
    BillingCommandPreparation,
    BillingCommandReceipt,
    BillingCommandTerminal,
    BillingCredit,
    BillingInvoice,
    BillingInvoiceLine,
    BillingJournalEntry,
    BillingJournalLine,
    BillingPayment,
    BillingRatePlan,
    BillingRatePlanVersion,
    BillingReversal,
    BillingSandboxSourceAttestation,
)

revision = "0033_billing_ledger"
down_revision = "0032_transport_commands"
branch_labels = None
depends_on = None

TABLES = (
    BillingSandboxSourceAttestation,
    BillingCommandPreparation,
    BillingCommandTerminal,
    BillingAccount,
    BillingAccountPayerVersion,
    BillingRatePlan,
    BillingRatePlanVersion,
    BillingAgreement,
    BillingAgreementVersion,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPayment,
    BillingAllocation,
    BillingCredit,
    BillingJournalEntry,
    BillingJournalLine,
    BillingReversal,
    BillingCommandReceipt,
    BillingCommandClaim,
)
TABLE_NAMES = tuple(model.__tablename__ for model in TABLES)
ROLE_PERMISSION_BACKUP_TABLE = "billing_0033_role_permission_backups"
ORIGINAL_AGREEMENT_CONSTRAINT = "uq_bill_agreement_account_child"
CURRENT_AGREEMENT_CONSTRAINT = "uq_bill_agreement_account_enrollment"
CURRENT_LEGACY_AGREEMENT_INDEX = "uq_bill_agreement_legacy_account_child"
POSTGRES_FUNCTIONS = (
    "caresync_0033_immutable_fact()",
    "caresync_0033_role_permission_guard()",
    "caresync_0033_source_attestation_guard()",
    "caresync_0033_attested_source_immutable()",
    "caresync_0033_actor_guard()",
    "caresync_0033_version_guard()",
    "caresync_0033_invoice_line_guard()",
    "caresync_0033_allocation_guard()",
    "caresync_0033_credit_guard()",
    "caresync_0033_journal_sequence_guard()",
    "caresync_0033_journal_validate()",
    "caresync_0033_effect_open_guard()",
    "caresync_0033_bundle_validate()",
    "caresync_0033_receipt_guard()",
    "caresync_0033_claim_guard()",
    "caresync_0033_terminal_claim()",
)
SOURCE_TABLE_TYPES = {
    "organizations": "organization",
    "families": "family",
    "guardians": "guardian",
    "children": "child",
    "enrollments": "enrollment",
    "facilities": "facility",
    "facility_programs": "program",
}

OWNER_BILLING_PERMISSIONS = (
    "billing:read",
    "billing:manage",
    "billing:issue",
    "billing:payments",
    "billing:adjust",
    "billing:close",
    "billing:recover",
)
ADMIN_BILLING_PERMISSIONS = (
    "billing:read",
    "billing:manage",
    "billing:issue",
    "billing:payments",
    "billing:recover",
)


def _freeze_original_billing_agreement_scope(
    bind: sa.engine.Connection,
) -> None:
    """Keep revision 0033 reproducible after the ORM moves to later scopes."""

    inspector = sa.inspect(bind)
    constraints = {
        str(item["name"])
        for item in inspector.get_unique_constraints("billing_agreements")
        if item.get("name")
    }
    indexes = {
        str(item["name"])
        for item in inspector.get_indexes("billing_agreements")
        if item.get("name")
    }
    schema = "public" if bind.dialect.name == "postgresql" else None
    if CURRENT_LEGACY_AGREEMENT_INDEX in indexes:
        op.drop_index(
            CURRENT_LEGACY_AGREEMENT_INDEX,
            table_name="billing_agreements",
            schema=schema,
        )
    if bind.dialect.name == "postgresql":
        if CURRENT_AGREEMENT_CONSTRAINT in constraints:
            op.drop_constraint(
                CURRENT_AGREEMENT_CONSTRAINT,
                "billing_agreements",
                type_="unique",
                schema="public",
            )
        if ORIGINAL_AGREEMENT_CONSTRAINT not in constraints:
            op.create_unique_constraint(
                ORIGINAL_AGREEMENT_CONSTRAINT,
                "billing_agreements",
                ["organization_id", "billing_account_id", "child_id"],
                schema="public",
            )
        return
    if (
        CURRENT_AGREEMENT_CONSTRAINT not in constraints
        and ORIGINAL_AGREEMENT_CONSTRAINT in constraints
    ):
        return
    with op.batch_alter_table("billing_agreements", recreate="always") as batch:
        if CURRENT_AGREEMENT_CONSTRAINT in constraints:
            batch.drop_constraint(
                CURRENT_AGREEMENT_CONSTRAINT,
                type_="unique",
            )
        if ORIGINAL_AGREEMENT_CONSTRAINT not in constraints:
            batch.create_unique_constraint(
                ORIGINAL_AGREEMENT_CONSTRAINT,
                ["organization_id", "billing_account_id", "child_id"],
            )


def _backfill_role_permissions(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "postgresql":
        for key, permissions in (
            ("owner", OWNER_BILLING_PERMISSIONS),
            ("administrator", ADMIN_BILLING_PERMISSIONS),
        ):
            encoded = json.dumps(list(permissions))
            bind.execute(
                sa.text(
                    "UPDATE roles SET permissions=(SELECT json_agg(value ORDER BY value) "
                    "FROM (SELECT DISTINCT value FROM jsonb_array_elements_text("
                    "COALESCE(roles.permissions::jsonb,'[]'::jsonb) || "
                    "CAST(:permissions AS jsonb)) AS value) AS valueset) "
                    "WHERE key=:key"
                ),
                {"permissions": encoded, "key": key},
            )
        bind.execute(
            sa.text(
                "UPDATE roles SET permissions=(SELECT COALESCE(json_agg(value ORDER BY value),"
                "'[]'::json) FROM jsonb_array_elements_text(COALESCE(roles.permissions::jsonb,"
                "'[]'::jsonb)) AS value WHERE value NOT LIKE 'billing:%') "
                "WHERE key NOT IN ('owner','administrator')"
            )
        )
        return
    rows = bind.execute(sa.text("SELECT id,key,permissions FROM roles")).mappings()
    for row in rows:
        existing = json.loads(row["permissions"] or "[]")
        additions = (
            OWNER_BILLING_PERMISSIONS
            if row["key"] == "owner"
            else ADMIN_BILLING_PERMISSIONS
            if row["key"] == "administrator"
            else ()
        )
        if additions:
            updated = sorted(set(existing).union(additions))
        else:
            updated = [value for value in existing if not value.startswith("billing:")]
        bind.execute(
            sa.text("UPDATE roles SET permissions=:permissions WHERE id=:id"),
            {"permissions": json.dumps(updated), "id": row["id"]},
        )


def _postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_immutable_fact() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
          RAISE EXCEPTION '0033 immutable billing fact cannot be changed'
            USING ERRCODE='23514';
        END $$
        """
    )
    for table in TABLE_NAMES:
        op.execute(
            f"CREATE TRIGGER {table}_0033_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_immutable_fact()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_role_permission_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE billing_permissions text[];
        BEGIN
          SELECT COALESCE(array_agg(DISTINCT value ORDER BY value),ARRAY[]::text[])
            INTO billing_permissions
            FROM jsonb_array_elements_text(COALESCE(NEW.permissions::jsonb,'[]'::jsonb)) value
           WHERE value LIKE 'billing:%';
          IF (NEW.key='owner' AND billing_permissions<>ARRAY[
                'billing:adjust','billing:close','billing:issue','billing:manage',
                'billing:payments','billing:read','billing:recover']::text[])
             OR (NEW.key='administrator' AND billing_permissions<>ARRAY[
                'billing:issue','billing:manage','billing:payments','billing:read',
                'billing:recover']::text[])
             OR (NEW.key NOT IN ('owner','administrator')
                 AND cardinality(billing_permissions)<>0) THEN
            RAISE EXCEPTION '0033 role billing permissions are invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER roles_0033_billing_permissions BEFORE INSERT OR UPDATE OF "
        "key,permissions ON roles FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0033_role_permission_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_source_attestation_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE source_exists boolean;
        BEGIN
          IF current_setting('app.billing_seed_mode',true)<>'synthetic_fixture'
             OR NULLIF(current_setting('app.current_organization_id',true),'')::uuid
                  IS DISTINCT FROM NEW.organization_id
             OR NULLIF(current_setting('app.current_user_id',true),'')::uuid
                  IS DISTINCT FROM NEW.attested_by_user_id
             OR NOT EXISTS (
               SELECT 1 FROM public.organization_memberships AS member
               WHERE member.organization_id=NEW.organization_id
                 AND member.user_id=NEW.attested_by_user_id AND member.status='active'
             ) THEN
            RAISE EXCEPTION '0033 synthetic source seed context is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.source_type<>'organization' AND NOT EXISTS (
            SELECT 1 FROM public.billing_sandbox_source_attestations AS root
            WHERE root.organization_id=NEW.organization_id
              AND root.source_type='organization' AND root.source_id=NEW.organization_id
          ) THEN
            RAISE EXCEPTION '0033 organization synthetic attestation is missing'
              USING ERRCODE='23514';
          END IF;
          source_exists := CASE NEW.source_type
            WHEN 'organization' THEN EXISTS (
              SELECT 1 FROM public.organizations s
              WHERE s.id=NEW.organization_id AND NEW.source_id=NEW.organization_id)
            WHEN 'family' THEN EXISTS (
              SELECT 1 FROM public.families s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            WHEN 'guardian' THEN EXISTS (
              SELECT 1 FROM public.guardians s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            WHEN 'child' THEN EXISTS (
              SELECT 1 FROM public.children s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            WHEN 'enrollment' THEN EXISTS (
              SELECT 1 FROM public.enrollments s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            WHEN 'facility' THEN EXISTS (
              SELECT 1 FROM public.facilities s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            WHEN 'program' THEN EXISTS (
              SELECT 1 FROM public.facility_programs s
              WHERE s.organization_id=NEW.organization_id AND s.id=NEW.source_id)
            ELSE false END;
          IF NOT source_exists THEN
            RAISE EXCEPTION '0033 synthetic source does not exist in tenant'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_sandbox_source_attestations_0033_insert_guard "
        "BEFORE INSERT ON billing_sandbox_source_attestations FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0033_source_attestation_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_attested_source_immutable() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE source_kind text; source_organization_id uuid;
        BEGIN
          source_kind := CASE TG_TABLE_NAME
            WHEN 'organizations' THEN 'organization'
            WHEN 'families' THEN 'family'
            WHEN 'guardians' THEN 'guardian'
            WHEN 'children' THEN 'child'
            WHEN 'enrollments' THEN 'enrollment'
            WHEN 'facilities' THEN 'facility'
            WHEN 'facility_programs' THEN 'program'
            ELSE NULL END;
          source_organization_id := CASE
            WHEN TG_TABLE_NAME='organizations' THEN OLD.id
            ELSE (to_jsonb(OLD)->>'organization_id')::uuid END;
          IF source_kind IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.billing_sandbox_source_attestations AS attestation
            WHERE attestation.organization_id=source_organization_id
              AND attestation.source_type=source_kind
              AND attestation.source_id=OLD.id
              AND attestation.marker='TEST_SYNTHETIC_ONLY'
              AND attestation.reason_code='disposable_test_fixture'
          ) THEN
            RAISE EXCEPTION '0033 attested synthetic source is immutable'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_billing_0033_attested_source_immutable';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in SOURCE_TABLE_TYPES:
        op.execute(
            f"CREATE TRIGGER {table}_0033_attested_source_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_0033_attested_source_immutable()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_actor_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE actor_column text := TG_ARGV[0]; actor_id uuid; operation_id uuid;
          required_command text; required_permission text;
        BEGIN
          actor_id := (to_jsonb(NEW)->>actor_column)::uuid;
          operation_id := NULLIF(
            current_setting('app.current_billing_operation_id',true),''
          )::uuid;
          IF NULLIF(current_setting('app.current_billing_operation_id',true),'') IS NULL
             OR NULLIF(current_setting('app.current_organization_id',true),'')::uuid
                  IS DISTINCT FROM NEW.organization_id
             OR NULLIF(current_setting('app.current_user_id',true),'')::uuid
                  IS DISTINCT FROM actor_id
             OR NOT EXISTS (
               SELECT 1 FROM public.organization_memberships AS member
               JOIN public.roles AS role ON role.organization_id=member.organization_id
                 AND role.id=member.role_id
               WHERE member.organization_id=NEW.organization_id
                 AND member.user_id=actor_id AND member.status='active'
                 AND role.key IN ('owner','administrator')
             ) THEN
            RAISE EXCEPTION '0033 billing actor or operation context is invalid'
              USING ERRCODE='23514';
          END IF;
          IF TG_TABLE_NAME IN ('billing_command_preparations','billing_command_receipts',
                               'billing_command_claims')
             AND operation_id
               IS DISTINCT FROM (to_jsonb(NEW)->>'client_operation_id')::uuid THEN
            RAISE EXCEPTION '0033 billing operation id is not bound to terminal fact'
              USING ERRCODE='23514';
          END IF;
          IF TG_TABLE_NAME NOT IN ('billing_command_preparations','billing_command_receipts',
                                   'billing_command_claims') THEN
            IF operation_id IS DISTINCT FROM
                 (to_jsonb(NEW)->>'client_operation_id')::uuid THEN
              RAISE EXCEPTION '0033 billing effect operation id is invalid'
                USING ERRCODE='23514';
            END IF;
            required_command := CASE TG_TABLE_NAME
              WHEN 'billing_accounts' THEN 'account_open'
              WHEN 'billing_rate_plans' THEN 'rate_version_publish'
              WHEN 'billing_rate_plan_versions' THEN 'rate_version_publish'
              WHEN 'billing_agreements' THEN 'agreement_establish'
              WHEN 'billing_agreement_versions' THEN 'agreement_establish'
              WHEN 'billing_invoices' THEN 'invoice_issue'
              WHEN 'billing_payments' THEN 'payment_record'
              WHEN 'billing_allocations' THEN 'payment_allocate'
              WHEN 'billing_credits' THEN 'credit_issue'
              WHEN 'billing_journal_entries' THEN CASE (to_jsonb(NEW)->>'entry_kind')
                WHEN 'invoice_issued' THEN 'invoice_issue'
                WHEN 'payment_settled' THEN 'payment_record'
                WHEN 'payment_allocated' THEN 'payment_allocate'
                WHEN 'credit_issued' THEN 'credit_issue' END
              ELSE NULL END;
            required_permission := CASE
              WHEN TG_TABLE_NAME IN ('billing_accounts','billing_account_payer_versions',
                'billing_rate_plans','billing_rate_plan_versions','billing_agreements',
                'billing_agreement_versions') THEN 'billing:manage'
              WHEN TG_TABLE_NAME='billing_invoices' THEN 'billing:issue'
              WHEN TG_TABLE_NAME IN ('billing_payments','billing_allocations')
                THEN 'billing:payments'
              WHEN TG_TABLE_NAME='billing_credits' THEN 'billing:adjust'
              WHEN TG_TABLE_NAME='billing_journal_entries' THEN
                CASE (to_jsonb(NEW)->>'entry_kind')
                WHEN 'invoice_issued' THEN 'billing:issue'
                WHEN 'payment_settled' THEN 'billing:payments'
                WHEN 'payment_allocated' THEN 'billing:payments'
                WHEN 'credit_issued' THEN 'billing:adjust' END
              ELSE NULL END;
            IF required_permission IS NULL OR NOT EXISTS (
              SELECT 1 FROM public.organization_memberships member
              JOIN public.roles role ON role.organization_id=member.organization_id
                AND role.id=member.role_id
              WHERE member.organization_id=NEW.organization_id
                AND member.user_id=actor_id AND member.status='active'
                AND role.key IN ('owner','administrator')
                AND role.permissions::jsonb @> jsonb_build_array(required_permission)
            ) THEN
              RAISE EXCEPTION '0033 billing permission is not current'
                USING ERRCODE='42501';
            END IF;
            IF TG_TABLE_NAME='billing_account_payer_versions' THEN
              IF NOT EXISTS (SELECT 1 FROM public.billing_command_preparations preparation
                WHERE preparation.organization_id=NEW.organization_id
                  AND preparation.client_operation_id=operation_id
                  AND preparation.actor_user_id=actor_id
                  AND preparation.command_type IN ('account_open','account_payer_assign')
                  AND preparation.request_hash=(to_jsonb(NEW)->>'request_hash')) THEN
                RAISE EXCEPTION '0033 billing fact has no matching preparation'
                  USING ERRCODE='23514';
              END IF;
            ELSIF required_command IS NULL OR NOT EXISTS (
              SELECT 1 FROM public.billing_command_preparations preparation
               WHERE preparation.organization_id=NEW.organization_id
                 AND preparation.client_operation_id=operation_id
                 AND preparation.actor_user_id=actor_id
                 AND preparation.command_type=required_command
                 AND preparation.request_hash=(to_jsonb(NEW)->>'request_hash')
            ) THEN
              RAISE EXCEPTION '0033 billing fact has no matching preparation'
                USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    actor_tables = {
        "billing_accounts": "opened_by_user_id",
        "billing_account_payer_versions": "assigned_by_user_id",
        "billing_rate_plans": "created_by_user_id",
        "billing_rate_plan_versions": "published_by_user_id",
        "billing_agreements": "created_by_user_id",
        "billing_agreement_versions": "reviewed_by_user_id",
        "billing_invoices": "issued_by_user_id",
        "billing_payments": "recorded_by_user_id",
        "billing_allocations": "allocated_by_user_id",
        "billing_credits": "issued_by_user_id",
        "billing_journal_entries": "posted_by_user_id",
        "billing_reversals": "reversed_by_user_id",
        "billing_command_preparations": "actor_user_id",
        "billing_command_receipts": "actor_user_id",
        "billing_command_claims": "actor_user_id",
    }
    for table, column in actor_tables.items():
        op.execute(
            f"CREATE TRIGGER {table}_0033_actor BEFORE INSERT ON {table} FOR EACH ROW "
            f"EXECUTE FUNCTION public.caresync_0033_actor_guard('{column}')"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_version_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE expected integer; previous_from date; current_from date;
        BEGIN
          IF TG_TABLE_NAME='billing_account_payer_versions' THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(
              'billing:0033:'||NEW.organization_id||':account:'||NEW.billing_account_id,0));
            SELECT COALESCE(max(version_number),0)+1 INTO expected
              FROM public.billing_account_payer_versions
             WHERE organization_id=NEW.organization_id
               AND billing_account_id=NEW.billing_account_id;
          ELSIF TG_TABLE_NAME='billing_rate_plan_versions' THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(
              'billing:0033:'||NEW.organization_id||':rate_plan:'||NEW.rate_plan_id,0));
            SELECT COALESCE(max(version_number),0)+1,max(effective_from)
              INTO expected,previous_from FROM public.billing_rate_plan_versions
             WHERE organization_id=NEW.organization_id AND rate_plan_id=NEW.rate_plan_id;
            current_from := (to_jsonb(NEW)->>'effective_from')::date;
          ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(
              'billing:0033:'||NEW.organization_id||':agreement:'||NEW.agreement_id,0));
            SELECT COALESCE(max(version_number),0)+1,max(effective_from)
              INTO expected,previous_from FROM public.billing_agreement_versions
             WHERE organization_id=NEW.organization_id AND agreement_id=NEW.agreement_id;
            current_from := (to_jsonb(NEW)->>'effective_from')::date;
          END IF;
          IF NEW.version_number<>expected OR
             (previous_from IS NOT NULL AND current_from<=previous_from) THEN
            RAISE EXCEPTION '0033 billing version sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in (
        "billing_account_payer_versions",
        "billing_rate_plan_versions",
        "billing_agreement_versions",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_0033_version BEFORE INSERT ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0033_version_guard()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_invoice_line_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE invoice_row record; agreement_row record; version_row record;
          rate_row record;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':invoice:'||NEW.invoice_id,0));
          SELECT * INTO invoice_row FROM public.billing_invoices
           WHERE organization_id=NEW.organization_id AND id=NEW.invoice_id;
          SELECT root.*,version.id AS version_id,version.rate_plan_version_id,
                 version.family_amount_minor_per_unit,version.funding_amount_minor_per_unit,
                 version.effective_from,version.effective_until,version.review_status
            INTO agreement_row
            FROM public.billing_agreements root
            JOIN public.billing_agreement_versions version
              ON version.organization_id=root.organization_id
             AND version.agreement_id=root.id
           WHERE root.organization_id=NEW.organization_id
             AND version.id=NEW.agreement_version_id;
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':agreement:'||agreement_row.id,0));
          SELECT rv.*,plan.name AS plan_name INTO rate_row
            FROM public.billing_rate_plan_versions rv
            JOIN public.billing_rate_plans plan
              ON plan.organization_id=rv.organization_id AND plan.id=rv.rate_plan_id
           WHERE rv.organization_id=NEW.organization_id
             AND rv.id=agreement_row.rate_plan_version_id;
          IF NOT EXISTS (SELECT 1 FROM public.billing_command_preparations preparation
               WHERE preparation.organization_id=NEW.organization_id
                 AND preparation.client_operation_id=NULLIF(current_setting(
                   'app.current_billing_operation_id',true),'')::uuid
                 AND preparation.actor_user_id=NULLIF(current_setting(
                   'app.current_user_id',true),'')::uuid
                 AND preparation.command_type='invoice_issue')
             OR invoice_row.id IS NULL OR agreement_row.version_id IS NULL OR rate_row.id IS NULL
             OR agreement_row.billing_account_id<>invoice_row.billing_account_id
             OR NEW.child_id<>agreement_row.child_id OR NEW.quantity<>1
             OR NEW.service_period_start<>invoice_row.service_period_start
             OR NEW.service_period_end<>invoice_row.service_period_end
             OR agreement_row.review_status<>'reviewed'
             OR agreement_row.effective_from>NEW.service_period_start
             OR (agreement_row.effective_until IS NOT NULL
                 AND agreement_row.effective_until<NEW.service_period_end)
             OR rate_row.effective_from>NEW.service_period_start
             OR (rate_row.effective_until IS NOT NULL
                 AND rate_row.effective_until<NEW.service_period_end)
             OR NEW.gross_unit_amount_minor<>rate_row.unit_amount_minor
             OR NEW.funding_unit_amount_minor<>agreement_row.funding_amount_minor_per_unit
             OR NEW.unit_amount_minor<>agreement_row.family_amount_minor_per_unit
             OR NEW.tax_rate_basis_points<>0
             OR NEW.gross_subtotal_minor<>NEW.gross_unit_amount_minor
             OR NEW.funding_minor<>NEW.funding_unit_amount_minor
             OR NEW.subtotal_minor<>NEW.unit_amount_minor OR NEW.tax_minor<>0
             OR NEW.total_minor<>NEW.subtotal_minor
             OR EXISTS (
               SELECT 1 FROM public.billing_invoice_lines prior
               JOIN public.billing_agreement_versions pv
                 ON pv.organization_id=prior.organization_id
                AND pv.id=prior.agreement_version_id
               WHERE prior.organization_id=NEW.organization_id
                 AND pv.agreement_id=agreement_row.id
                 AND prior.service_period_start<=NEW.service_period_end
                 AND prior.service_period_end>=NEW.service_period_start
             ) THEN
            RAISE EXCEPTION '0033 invoice line source or arithmetic is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_invoice_lines_0033_guard BEFORE INSERT ON billing_invoice_lines "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_invoice_line_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_allocation_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE payment_amount bigint; invoice_amount bigint;
          payment_used bigint; invoice_used bigint; invoice_credits bigint;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':account:'||NEW.billing_account_id,0));
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':payment:'||NEW.payment_id,0));
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':invoice:'||NEW.invoice_id,0));
          SELECT amount_minor INTO payment_amount FROM public.billing_payments
           WHERE organization_id=NEW.organization_id AND id=NEW.payment_id
             AND billing_account_id=NEW.billing_account_id;
          SELECT total_minor INTO invoice_amount FROM public.billing_invoices
           WHERE organization_id=NEW.organization_id AND id=NEW.invoice_id
             AND billing_account_id=NEW.billing_account_id;
          SELECT COALESCE(sum(amount_minor),0) INTO payment_used FROM public.billing_allocations
           WHERE organization_id=NEW.organization_id AND payment_id=NEW.payment_id;
          SELECT COALESCE(sum(amount_minor),0) INTO invoice_used FROM public.billing_allocations
           WHERE organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id;
          SELECT COALESCE(sum(amount_minor),0) INTO invoice_credits FROM public.billing_credits
           WHERE organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id;
          IF payment_amount IS NULL OR invoice_amount IS NULL
             OR payment_used+NEW.amount_minor>payment_amount
             OR invoice_used+invoice_credits+NEW.amount_minor>invoice_amount THEN
            RAISE EXCEPTION '0033 allocation exceeds immutable source balance'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_allocations_0033_guard BEFORE INSERT ON billing_allocations "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_allocation_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_credit_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE invoice_amount bigint; allocated bigint; credited bigint;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':account:'||NEW.billing_account_id,0));
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':invoice:'||NEW.invoice_id,0));
          SELECT total_minor INTO invoice_amount FROM public.billing_invoices
           WHERE organization_id=NEW.organization_id AND id=NEW.invoice_id
             AND billing_account_id=NEW.billing_account_id;
          SELECT COALESCE(sum(amount_minor),0) INTO allocated FROM public.billing_allocations
           WHERE organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id;
          SELECT COALESCE(sum(amount_minor),0) INTO credited FROM public.billing_credits
           WHERE organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id;
          IF invoice_amount IS NULL OR allocated+credited+NEW.amount_minor>invoice_amount THEN
            RAISE EXCEPTION '0033 credit exceeds immutable invoice balance'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_credits_0033_guard BEFORE INSERT ON billing_credits "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_credit_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_journal_sequence_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE expected_sequence bigint; expected_command text;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':journal_book:'||NEW.organization_id,0));
          SELECT COALESCE(max(book_sequence),0)+1 INTO expected_sequence
            FROM public.billing_journal_entries
           WHERE organization_id=NEW.organization_id;
          expected_command := CASE NEW.entry_kind
            WHEN 'invoice_issued' THEN 'invoice_issue'
            WHEN 'payment_settled' THEN 'payment_record'
            WHEN 'payment_allocated' THEN 'payment_allocate'
            WHEN 'credit_issued' THEN 'credit_issue' END;
          IF NEW.book_sequence<>expected_sequence OR expected_command IS NULL
             OR NULLIF(current_setting('app.current_billing_operation_id',true),'')::uuid
                  IS DISTINCT FROM NEW.client_operation_id
             OR NOT EXISTS (
               SELECT 1 FROM public.billing_command_preparations preparation
                WHERE preparation.organization_id=NEW.organization_id
                  AND preparation.client_operation_id=NEW.client_operation_id
                  AND preparation.actor_user_id=NEW.posted_by_user_id
                  AND preparation.command_type=expected_command
                  AND preparation.request_hash=NEW.request_hash
             ) THEN
            RAISE EXCEPTION '0033 journal operation or book sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_journal_entries_0033_sequence BEFORE INSERT ON "
        "billing_journal_entries FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0033_journal_sequence_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_journal_validate() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE entry_id uuid; entry_row record; actual_count integer;
          actual_debit bigint; actual_credit bigint; source_amount bigint;
        BEGIN
          IF TG_TABLE_NAME='billing_journal_entries' THEN
            entry_id := (to_jsonb(NEW)->>'id')::uuid;
          ELSE
            entry_id := (to_jsonb(NEW)->>'journal_entry_id')::uuid;
          END IF;
          SELECT * INTO entry_row FROM public.billing_journal_entries
           WHERE id=entry_id AND organization_id=NEW.organization_id;
          IF entry_row.id IS NULL THEN RETURN NEW; END IF;
          SELECT count(*),COALESCE(sum(amount_minor) FILTER (WHERE direction='debit'),0),
                 COALESCE(sum(amount_minor) FILTER (WHERE direction='credit'),0)
            INTO actual_count,actual_debit,actual_credit
            FROM public.billing_journal_lines
           WHERE organization_id=entry_row.organization_id
             AND journal_entry_id=entry_row.id;
          IF actual_count<>entry_row.line_count OR actual_debit<>entry_row.total_debit_minor
             OR actual_credit<>entry_row.total_credit_minor OR actual_debit<>actual_credit THEN
            RAISE EXCEPTION '0033 journal actual lines are not balanced to header'
              USING ERRCODE='23514';
          END IF;
          source_amount := CASE entry_row.source_type
            WHEN 'billing_invoice' THEN (SELECT total_minor+funding_minor
              FROM public.billing_invoices WHERE organization_id=entry_row.organization_id
                AND id=entry_row.source_id)
            WHEN 'billing_payment' THEN (SELECT amount_minor FROM public.billing_payments
              WHERE organization_id=entry_row.organization_id AND id=entry_row.source_id)
            WHEN 'billing_allocation' THEN (SELECT amount_minor FROM public.billing_allocations
              WHERE organization_id=entry_row.organization_id AND id=entry_row.source_id)
            WHEN 'billing_credit' THEN (SELECT amount_minor FROM public.billing_credits
              WHERE organization_id=entry_row.organization_id AND id=entry_row.source_id)
            WHEN 'billing_reversal' THEN (SELECT original.total_debit_minor
              FROM public.billing_reversals reversal
              JOIN public.billing_journal_entries original
                ON original.organization_id=reversal.organization_id
               AND original.id=reversal.original_journal_entry_id
              WHERE reversal.organization_id=entry_row.organization_id
                AND reversal.id=entry_row.source_id)
            ELSE NULL END;
          IF source_amount IS NULL OR source_amount<>entry_row.total_debit_minor THEN
            RAISE EXCEPTION '0033 journal source amount is invalid' USING ERRCODE='23514';
          END IF;
          IF entry_row.entry_kind='invoice_issued' AND NOT EXISTS (
            SELECT 1 FROM public.billing_invoices invoice
             WHERE invoice.organization_id=entry_row.organization_id
               AND invoice.id=entry_row.source_id
               AND (SELECT count(*) FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id)=
                   2 + CASE WHEN invoice.funding_minor>0 THEN 1 ELSE 0 END
                     + CASE WHEN invoice.tax_minor>0 THEN 1 ELSE 0 END
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='accounts_receivable' AND line.direction='debit'
                   AND line.amount_minor=invoice.total_minor)
               AND (invoice.funding_minor=0 OR EXISTS (SELECT 1
                 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='funding_receivable' AND line.direction='debit'
                   AND line.amount_minor=invoice.funding_minor))
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='childcare_revenue' AND line.direction='credit'
                   AND line.amount_minor=invoice.gross_subtotal_minor)
               AND (invoice.tax_minor=0 OR EXISTS (SELECT 1
                 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='sales_tax_payable' AND line.direction='credit'
                   AND line.amount_minor=invoice.tax_minor))
          ) THEN
            RAISE EXCEPTION '0033 invoice journal posting shape is invalid'
              USING ERRCODE='23514';
          ELSIF entry_row.entry_kind='payment_settled' AND NOT EXISTS (
            SELECT 1 FROM public.billing_payments payment
             WHERE payment.organization_id=entry_row.organization_id
               AND payment.id=entry_row.source_id
               AND (SELECT count(*) FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id)=2
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id AND line.direction='debit'
                   AND line.account_code=CASE payment.method
                     WHEN 'cash' THEN 'cash_on_hand'
                     WHEN 'cheque' THEN 'cheque_clearing'
                     WHEN 'e_transfer' THEN 'e_transfer_clearing'
                     ELSE 'other_payment_clearing' END
                   AND line.amount_minor=payment.amount_minor)
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='unapplied_cash' AND line.direction='credit'
                   AND line.amount_minor=payment.amount_minor)
          ) THEN
            RAISE EXCEPTION '0033 payment journal posting shape is invalid'
              USING ERRCODE='23514';
          ELSIF entry_row.entry_kind='payment_allocated' AND NOT EXISTS (
            SELECT 1 FROM public.billing_allocations allocation
             WHERE allocation.organization_id=entry_row.organization_id
               AND allocation.id=entry_row.source_id
               AND (SELECT count(*) FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id)=2
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='unapplied_cash' AND line.direction='debit'
                   AND line.amount_minor=allocation.amount_minor)
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='accounts_receivable' AND line.direction='credit'
                   AND line.amount_minor=allocation.amount_minor)
          ) THEN
            RAISE EXCEPTION '0033 allocation journal posting shape is invalid'
              USING ERRCODE='23514';
          ELSIF entry_row.entry_kind='credit_issued' AND NOT EXISTS (
            SELECT 1 FROM public.billing_credits credit
             WHERE credit.organization_id=entry_row.organization_id
               AND credit.id=entry_row.source_id
               AND (SELECT count(*) FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id)=2
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='billing_adjustments' AND line.direction='debit'
                   AND line.amount_minor=credit.amount_minor)
               AND EXISTS (SELECT 1 FROM public.billing_journal_lines line
                 WHERE line.organization_id=entry_row.organization_id
                   AND line.journal_entry_id=entry_row.id
                   AND line.account_code='accounts_receivable' AND line.direction='credit'
                   AND line.amount_minor=credit.amount_minor)
          ) THEN
            RAISE EXCEPTION '0033 credit journal posting shape is invalid'
              USING ERRCODE='23514';
          END IF;
          IF entry_row.source_type='billing_invoice' THEN
            IF NOT EXISTS (
              SELECT 1 FROM public.billing_invoices invoice
               WHERE invoice.organization_id=entry_row.organization_id
                 AND invoice.id=entry_row.source_id
                 AND EXISTS (SELECT 1 FROM public.billing_invoice_lines line
                   WHERE line.organization_id=invoice.organization_id
                     AND line.invoice_id=invoice.id)
                 AND invoice.gross_subtotal_minor=(SELECT sum(gross_subtotal_minor)
                   FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                     AND invoice_id=invoice.id)
                 AND invoice.funding_minor=(SELECT sum(funding_minor)
                   FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                     AND invoice_id=invoice.id)
                 AND invoice.subtotal_minor=(SELECT sum(subtotal_minor)
                   FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                     AND invoice_id=invoice.id)
                 AND invoice.tax_minor=(SELECT sum(tax_minor)
                   FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                     AND invoice_id=invoice.id)
                 AND invoice.total_minor=(SELECT sum(total_minor)
                   FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                     AND invoice_id=invoice.id)
            ) THEN
              RAISE EXCEPTION '0033 invoice header does not equal immutable lines'
                USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in ("billing_journal_entries", "billing_journal_lines"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_0033_balance AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0033_journal_validate()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_effect_open_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE operation_id uuid; effect_operation_id uuid; effect_hash text;
          actor_id uuid;
        BEGIN
          operation_id := NULLIF(
            current_setting('app.current_billing_operation_id',true),''
          )::uuid;
          actor_id := NULLIF(current_setting('app.current_user_id',true),'')::uuid;
          IF TG_TABLE_NAME='billing_journal_lines' THEN
            SELECT client_operation_id,request_hash
              INTO effect_operation_id,effect_hash
              FROM public.billing_journal_entries
             WHERE organization_id=NEW.organization_id
               AND id=NEW.journal_entry_id;
          ELSE
            effect_operation_id := (to_jsonb(NEW)->>'client_operation_id')::uuid;
            effect_hash := to_jsonb(NEW)->>'request_hash';
          END IF;
          IF operation_id IS NULL OR operation_id IS DISTINCT FROM effect_operation_id
             OR actor_id IS NULL
             OR NULLIF(current_setting('app.current_organization_id',true),'')::uuid
                  IS DISTINCT FROM NEW.organization_id
             OR NOT EXISTS (
               SELECT 1 FROM public.billing_command_preparations preparation
                WHERE preparation.organization_id=NEW.organization_id
                  AND preparation.client_operation_id=effect_operation_id
                  AND preparation.actor_user_id=actor_id
                  AND preparation.request_hash=effect_hash
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_command_receipts receipt
                WHERE receipt.organization_id=NEW.organization_id
                  AND receipt.client_operation_id=effect_operation_id
             )
             OR EXISTS (
               SELECT 1 FROM public.billing_command_claims claim
                WHERE claim.organization_id=NEW.organization_id
                  AND claim.client_operation_id=effect_operation_id
             ) THEN
            RAISE EXCEPTION '0033 billing operation is not open for effects'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in (
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
    ):
        op.execute(
            f"CREATE TRIGGER {table}_0033_effect_open BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_effect_open_guard()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_bundle_validate() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE operation_id uuid; effect_operation_id uuid; actor_id uuid;
          effect_hash text; actual_command text; actual_target_scope text;
          prepared_command text;
          expected_result_kind text; expected_result_id uuid; journal_row record;
        BEGIN
          operation_id := NULLIF(
            current_setting('app.current_billing_operation_id',true),''
          )::uuid;
          actor_id := NULLIF(current_setting('app.current_user_id',true),'')::uuid;
          IF TG_TABLE_NAME='billing_journal_lines' THEN
            SELECT * INTO journal_row
              FROM public.billing_journal_entries
             WHERE organization_id=NEW.organization_id
               AND id=NEW.journal_entry_id;
            effect_operation_id := journal_row.client_operation_id;
            effect_hash := journal_row.request_hash;
          ELSE
            effect_operation_id := (to_jsonb(NEW)->>'client_operation_id')::uuid;
            effect_hash := to_jsonb(NEW)->>'request_hash';
          END IF;
          SELECT command_type,target_scope INTO actual_command,actual_target_scope
            FROM public.billing_command_preparations preparation
           WHERE preparation.organization_id=NEW.organization_id
             AND preparation.client_operation_id=effect_operation_id
             AND preparation.actor_user_id=actor_id
             AND preparation.request_hash=effect_hash;
          IF operation_id IS NULL OR operation_id IS DISTINCT FROM effect_operation_id
             OR actor_id IS NULL OR actual_command IS NULL
             OR NULLIF(current_setting('app.current_organization_id',true),'')::uuid
                  IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION '0033 billing bundle context is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.billing_sandbox_source_attestations attestation
             WHERE attestation.organization_id=NEW.organization_id
               AND attestation.source_type='organization'
               AND attestation.source_id=NEW.organization_id
               AND attestation.marker='TEST_SYNTHETIC_ONLY'
               AND attestation.reason_code='disposable_test_fixture'
          ) THEN
            RAISE EXCEPTION '0033 organization is not synthetic-attested'
              USING ERRCODE='23514';
          END IF;

          IF TG_TABLE_NAME='billing_accounts' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='family'
                AND a.source_id=NEW.family_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='guardian'
                AND a.source_id=NEW.payer_guardian_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture') THEN
              RAISE EXCEPTION '0033 account sources are not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_account'; expected_result_id := NEW.id;
            prepared_command := 'account_open';
          ELSIF TG_TABLE_NAME='billing_account_payer_versions' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='guardian'
                AND a.source_id=NEW.payer_guardian_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture') THEN
              RAISE EXCEPTION '0033 payer source is not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_account';
            expected_result_id := NEW.billing_account_id;
          ELSIF TG_TABLE_NAME='billing_rate_plans' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='facility'
                AND a.source_id=NEW.facility_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='program'
                AND a.source_id=NEW.program_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture') THEN
              RAISE EXCEPTION '0033 rate sources are not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_rate_plan'; expected_result_id := NEW.id;
            prepared_command := 'rate_version_publish';
          ELSIF TG_TABLE_NAME='billing_rate_plan_versions' THEN
            expected_result_kind := 'billing_rate_plan';
            expected_result_id := NEW.rate_plan_id;
            prepared_command := 'rate_version_publish';
          ELSIF TG_TABLE_NAME='billing_agreements' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='family'
                AND a.source_id=NEW.family_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='child'
                AND a.source_id=NEW.child_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR (NEW.enrollment_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='enrollment'
                AND a.source_id=NEW.enrollment_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture'))
               OR (NEW.facility_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='facility'
                AND a.source_id=NEW.facility_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')) THEN
              RAISE EXCEPTION '0033 agreement sources are not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_agreement'; expected_result_id := NEW.id;
            prepared_command := 'agreement_establish';
          ELSIF TG_TABLE_NAME='billing_agreement_versions' THEN
            expected_result_kind := 'billing_agreement';
            expected_result_id := NEW.agreement_id;
            prepared_command := 'agreement_establish';
          ELSIF TG_TABLE_NAME='billing_invoices' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='family'
                AND a.source_id=NEW.family_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='guardian'
                AND a.source_id=NEW.payer_guardian_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (
              SELECT 1 FROM public.billing_account_payer_versions payer_version
              JOIN public.guardians guardian
                ON guardian.organization_id=payer_version.organization_id
               AND guardian.family_id=payer_version.family_id
               AND guardian.id=payer_version.payer_guardian_id
              JOIN public.families family
                ON family.organization_id=payer_version.organization_id
               AND family.id=payer_version.family_id
              WHERE payer_version.organization_id=NEW.organization_id
                AND payer_version.billing_account_id=NEW.billing_account_id
                AND payer_version.id=NEW.billing_account_payer_version_id
                AND payer_version.family_id=NEW.family_id
                AND payer_version.payer_guardian_id=NEW.payer_guardian_id
                AND NEW.family_name_snapshot=family.name
                AND NEW.payer_name_snapshot=btrim(
                  guardian.first_name||' '||guardian.last_name)
                AND NEW.payer_email_snapshot IS NOT DISTINCT FROM NULLIF(guardian.email,'')
                AND NEW.payer_address_snapshot IS NOT DISTINCT FROM NULLIF(concat_ws(', ',
                  NULLIF(guardian.address,''),NULLIF(guardian.city,''),
                  NULLIF(guardian.postal_code,'')),'')
            ) THEN
              RAISE EXCEPTION '0033 invoice payer source or snapshot is invalid'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_invoice'; expected_result_id := NEW.id;
            prepared_command := 'invoice_issue';
          ELSIF TG_TABLE_NAME='billing_invoice_lines' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='child'
                AND a.source_id=NEW.child_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture') THEN
              RAISE EXCEPTION '0033 invoice line source is not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_invoice';
            expected_result_id := NEW.invoice_id;
            prepared_command := 'invoice_issue';
          ELSIF TG_TABLE_NAME='billing_payments' THEN
            IF NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='family'
                AND a.source_id=NEW.family_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture')
               OR NOT EXISTS (SELECT 1 FROM public.billing_sandbox_source_attestations a
              WHERE a.organization_id=NEW.organization_id AND a.source_type='guardian'
                AND a.source_id=NEW.payer_guardian_id AND a.marker='TEST_SYNTHETIC_ONLY'
                AND a.reason_code='disposable_test_fixture') THEN
              RAISE EXCEPTION '0033 payment sources are not synthetic-attested'
                USING ERRCODE='23514';
            END IF;
            expected_result_kind := 'billing_payment'; expected_result_id := NEW.id;
            prepared_command := 'payment_record';
          ELSIF TG_TABLE_NAME='billing_allocations' THEN
            expected_result_kind := 'billing_allocation'; expected_result_id := NEW.id;
            prepared_command := 'payment_allocate';
          ELSIF TG_TABLE_NAME='billing_credits' THEN
            expected_result_kind := 'billing_credit'; expected_result_id := NEW.id;
            prepared_command := 'credit_issue';
          ELSIF TG_TABLE_NAME='billing_journal_entries' THEN
            expected_result_kind := NEW.source_type; expected_result_id := NEW.source_id;
            prepared_command := CASE NEW.entry_kind
              WHEN 'invoice_issued' THEN 'invoice_issue'
              WHEN 'payment_settled' THEN 'payment_record'
              WHEN 'payment_allocated' THEN 'payment_allocate'
              WHEN 'credit_issued' THEN 'credit_issue' END;
          ELSIF TG_TABLE_NAME='billing_journal_lines' THEN
            expected_result_kind := journal_row.source_type;
            expected_result_id := journal_row.source_id;
            prepared_command := CASE journal_row.entry_kind
              WHEN 'invoice_issued' THEN 'invoice_issue'
              WHEN 'payment_settled' THEN 'payment_record'
              WHEN 'payment_allocated' THEN 'payment_allocate'
              WHEN 'credit_issued' THEN 'credit_issue' END;
          ELSE
            RAISE EXCEPTION '0033 unsupported billing bundle table'
              USING ERRCODE='23514';
          END IF;

          IF TG_TABLE_NAME='billing_account_payer_versions' THEN
            IF NOT EXISTS (
              SELECT 1 FROM public.billing_command_preparations preparation
              JOIN public.billing_command_receipts receipt
                ON receipt.organization_id=preparation.organization_id
               AND receipt.client_operation_id=preparation.client_operation_id
               AND receipt.actor_user_id=preparation.actor_user_id
               AND receipt.command_type=preparation.command_type
               AND receipt.request_hash=preparation.request_hash
             WHERE preparation.organization_id=NEW.organization_id
               AND preparation.client_operation_id=effect_operation_id
               AND preparation.actor_user_id=actor_id
               AND preparation.command_type IN ('account_open','account_payer_assign')
               AND preparation.request_hash=effect_hash
               AND receipt.result_kind=expected_result_kind
               AND receipt.result_id=expected_result_id
            ) THEN
              RAISE EXCEPTION '0033 payer version has no exact terminal bundle'
                USING ERRCODE='23514';
            END IF;
          ELSIF prepared_command IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.billing_command_preparations preparation
            JOIN public.billing_command_receipts receipt
              ON receipt.organization_id=preparation.organization_id
             AND receipt.client_operation_id=preparation.client_operation_id
             AND receipt.actor_user_id=preparation.actor_user_id
             AND receipt.command_type=preparation.command_type
             AND receipt.request_hash=preparation.request_hash
           WHERE preparation.organization_id=NEW.organization_id
             AND preparation.client_operation_id=effect_operation_id
             AND preparation.actor_user_id=actor_id
             AND preparation.command_type=prepared_command
             AND preparation.request_hash=effect_hash
             AND receipt.result_kind=expected_result_kind
             AND receipt.result_id=expected_result_id
          ) THEN
            RAISE EXCEPTION '0033 billing fact has no exact terminal bundle'
              USING ERRCODE='23514';
          END IF;
          IF actual_command IN ('account_open','account_payer_assign') AND
             (SELECT count(*) FROM public.billing_account_payer_versions effect
               WHERE effect.organization_id=NEW.organization_id
                 AND effect.client_operation_id=effect_operation_id
                 AND effect.request_hash=effect_hash)<>1 THEN
            RAISE EXCEPTION '0033 payer operation must produce exactly one version'
              USING ERRCODE='23514';
          ELSIF actual_command='rate_version_publish' AND
             (SELECT count(*) FROM public.billing_rate_plan_versions effect
               WHERE effect.organization_id=NEW.organization_id
                 AND effect.client_operation_id=effect_operation_id
                 AND effect.request_hash=effect_hash)<>1 THEN
            RAISE EXCEPTION '0033 rate operation must produce exactly one version'
              USING ERRCODE='23514';
          ELSIF actual_command='agreement_establish' AND
             (SELECT count(*) FROM public.billing_agreement_versions effect
               WHERE effect.organization_id=NEW.organization_id
                 AND effect.client_operation_id=effect_operation_id
                 AND effect.request_hash=effect_hash)<>1 THEN
            RAISE EXCEPTION '0033 agreement operation must produce exactly one version'
              USING ERRCODE='23514';
          END IF;
          IF (actual_command='account_open' AND
              (SELECT count(*) FROM public.billing_accounts effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>1)
             OR (actual_command='account_payer_assign' AND
              (SELECT count(*) FROM public.billing_accounts effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id)<>0)
             OR (actual_command='rate_version_publish' AND
              (SELECT count(*) FROM public.billing_rate_plans effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>
                    CASE WHEN actual_target_scope='new' THEN 1 ELSE 0 END)
             OR (actual_command='agreement_establish' AND
              (SELECT count(*) FROM public.billing_agreements effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>
                    CASE WHEN actual_target_scope=expected_result_id::text THEN 0 ELSE 1 END)
             OR (actual_command='invoice_issue' AND
              (SELECT count(*) FROM public.billing_invoices effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>1)
             OR (actual_command='payment_record' AND
              (SELECT count(*) FROM public.billing_payments effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>1)
             OR (actual_command='payment_allocate' AND
              (SELECT count(*) FROM public.billing_allocations effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>1)
             OR (actual_command='credit_issue' AND
              (SELECT count(*) FROM public.billing_credits effect
                WHERE effect.organization_id=NEW.organization_id
                  AND effect.client_operation_id=effect_operation_id
                  AND effect.request_hash=effect_hash)<>1) THEN
            RAISE EXCEPTION '0033 billing operation root cardinality is invalid'
              USING ERRCODE='23514';
          END IF;
          IF (actual_command='account_open' AND actual_target_scope IS DISTINCT FROM
                (SELECT family_id::text FROM public.billing_accounts
                  WHERE organization_id=NEW.organization_id AND id=expected_result_id))
             OR (actual_command='account_payer_assign'
                 AND actual_target_scope IS DISTINCT FROM expected_result_id::text)
             OR (actual_command='rate_version_publish'
                 AND actual_target_scope<>'new'
                 AND actual_target_scope IS DISTINCT FROM expected_result_id::text)
             OR (actual_command='agreement_establish'
                 AND actual_target_scope IS DISTINCT FROM expected_result_id::text
                 AND actual_target_scope IS DISTINCT FROM
                   (SELECT billing_account_id::text FROM public.billing_agreements
                     WHERE organization_id=NEW.organization_id
                       AND id=expected_result_id))
             OR (actual_command='invoice_issue' AND actual_target_scope IS DISTINCT FROM
                   (SELECT billing_account_id::text FROM public.billing_invoices
                     WHERE organization_id=NEW.organization_id
                       AND id=expected_result_id))
             OR (actual_command='payment_record' AND actual_target_scope IS DISTINCT FROM
                   (SELECT billing_account_id::text FROM public.billing_payments
                     WHERE organization_id=NEW.organization_id
                       AND id=expected_result_id))
             OR (actual_command='payment_allocate' AND actual_target_scope IS DISTINCT FROM
                   (SELECT payment_id::text FROM public.billing_allocations
                     WHERE organization_id=NEW.organization_id
                       AND id=expected_result_id))
             OR (actual_command='credit_issue' AND actual_target_scope IS DISTINCT FROM
                   (SELECT invoice_id::text FROM public.billing_credits
                     WHERE organization_id=NEW.organization_id
                       AND id=expected_result_id)) THEN
            RAISE EXCEPTION '0033 billing operation target is not bound to its effect'
              USING ERRCODE='23514';
          END IF;
          IF actual_command='invoice_issue' AND NOT EXISTS (
            SELECT 1 FROM public.billing_invoices invoice
             WHERE invoice.organization_id=NEW.organization_id
               AND invoice.id=expected_result_id
               AND invoice.client_operation_id=effect_operation_id
               AND invoice.request_hash=effect_hash
               AND EXISTS (SELECT 1 FROM public.billing_invoice_lines line
                 WHERE line.organization_id=invoice.organization_id
                   AND line.invoice_id=invoice.id
                   AND line.client_operation_id=effect_operation_id
                   AND line.request_hash=effect_hash)
               AND NOT EXISTS (SELECT 1 FROM public.billing_invoice_lines line
                 WHERE line.organization_id=invoice.organization_id
                   AND line.invoice_id=invoice.id
                   AND (line.client_operation_id<>effect_operation_id
                        OR line.request_hash<>effect_hash))
               AND invoice.gross_subtotal_minor=(SELECT sum(gross_subtotal_minor)
                 FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                   AND invoice_id=invoice.id)
               AND invoice.funding_minor=(SELECT sum(funding_minor)
                 FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                   AND invoice_id=invoice.id)
               AND invoice.subtotal_minor=(SELECT sum(subtotal_minor)
                 FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                   AND invoice_id=invoice.id)
               AND invoice.tax_minor=(SELECT sum(tax_minor)
                 FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                   AND invoice_id=invoice.id)
               AND invoice.total_minor=(SELECT sum(total_minor)
                 FROM public.billing_invoice_lines WHERE organization_id=invoice.organization_id
                   AND invoice_id=invoice.id)
               AND EXISTS (SELECT 1 FROM public.billing_journal_entries journal
                 WHERE journal.organization_id=invoice.organization_id
                   AND journal.source_type='billing_invoice'
                   AND journal.source_id=invoice.id
                   AND journal.client_operation_id=effect_operation_id
                   AND journal.request_hash=effect_hash)
          ) THEN
            RAISE EXCEPTION '0033 invoice terminal aggregate is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in (
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
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_0033_bundle AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.caresync_0033_bundle_validate()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_receipt_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE fact_exists boolean; journal_required boolean;
          expected_audit_action text; expected_event_type text; prepared_target text;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':operation:'||NEW.client_operation_id,0));
          IF NULLIF(current_setting('app.current_billing_operation_id',true),'')::uuid
               IS DISTINCT FROM NEW.client_operation_id
             OR NOT EXISTS (SELECT 1 FROM public.billing_command_preparations preparation
               WHERE preparation.organization_id=NEW.organization_id
                 AND preparation.client_operation_id=NEW.client_operation_id
                 AND preparation.actor_user_id=NEW.actor_user_id
                 AND preparation.command_type=NEW.command_type
                 AND preparation.request_hash=NEW.request_hash)
             OR EXISTS (SELECT 1 FROM public.billing_command_claims claim
               WHERE claim.organization_id=NEW.organization_id
                 AND claim.client_operation_id=NEW.client_operation_id) THEN
            RAISE EXCEPTION '0033 receipt operation context conflicts'
              USING ERRCODE='23514';
          END IF;
          SELECT target_scope INTO prepared_target
            FROM public.billing_command_preparations preparation
           WHERE preparation.organization_id=NEW.organization_id
             AND preparation.client_operation_id=NEW.client_operation_id;
          fact_exists := CASE NEW.command_type
            WHEN 'account_open' THEN EXISTS (
              SELECT 1 FROM public.billing_accounts root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.client_operation_id=NEW.client_operation_id
                 AND root.request_hash=NEW.request_hash
                 AND root.family_id::text=prepared_target
                 AND 1=(SELECT count(*) FROM public.billing_account_payer_versions version
                   WHERE version.organization_id=root.organization_id
                     AND version.billing_account_id=root.id
                     AND version.client_operation_id=NEW.client_operation_id
                     AND version.request_hash=NEW.request_hash))
            WHEN 'account_payer_assign' THEN EXISTS (
              SELECT 1 FROM public.billing_accounts root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.id::text=prepared_target
                 AND 1=(SELECT count(*) FROM public.billing_account_payer_versions version
                   WHERE version.organization_id=root.organization_id
                     AND version.billing_account_id=root.id
                     AND version.client_operation_id=NEW.client_operation_id
                     AND version.request_hash=NEW.request_hash))
            WHEN 'rate_version_publish' THEN EXISTS (
              SELECT 1 FROM public.billing_rate_plans root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND (prepared_target='new' OR root.id::text=prepared_target)
                 AND 1=(SELECT count(*) FROM public.billing_rate_plan_versions version
                   WHERE version.organization_id=root.organization_id
                     AND version.rate_plan_id=root.id
                     AND version.client_operation_id=NEW.client_operation_id
                     AND version.request_hash=NEW.request_hash)
                 AND (SELECT count(*) FROM public.billing_rate_plans effect
                   WHERE effect.organization_id=root.organization_id
                     AND effect.client_operation_id=NEW.client_operation_id
                     AND effect.request_hash=NEW.request_hash)=
                       CASE WHEN prepared_target='new' THEN 1 ELSE 0 END)
            WHEN 'agreement_establish' THEN EXISTS (
              SELECT 1 FROM public.billing_agreements root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND (root.id::text=prepared_target
                      OR root.billing_account_id::text=prepared_target)
                 AND 1=(SELECT count(*) FROM public.billing_agreement_versions version
                   WHERE version.organization_id=root.organization_id
                     AND version.agreement_id=root.id
                     AND version.client_operation_id=NEW.client_operation_id
                     AND version.request_hash=NEW.request_hash)
                 AND (SELECT count(*) FROM public.billing_agreements effect
                   WHERE effect.organization_id=root.organization_id
                     AND effect.client_operation_id=NEW.client_operation_id
                     AND effect.request_hash=NEW.request_hash)=
                       CASE WHEN root.id::text=prepared_target THEN 0 ELSE 1 END)
            WHEN 'invoice_issue' THEN EXISTS (
              SELECT 1 FROM public.billing_invoices root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.client_operation_id=NEW.client_operation_id
                 AND root.request_hash=NEW.request_hash
                 AND root.billing_account_id::text=prepared_target
                 AND EXISTS (SELECT 1 FROM public.billing_invoice_lines line
                   WHERE line.organization_id=root.organization_id AND line.invoice_id=root.id
                     AND line.client_operation_id=NEW.client_operation_id
                     AND line.request_hash=NEW.request_hash))
            WHEN 'payment_record' THEN EXISTS (
              SELECT 1 FROM public.billing_payments root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.client_operation_id=NEW.client_operation_id
                 AND root.request_hash=NEW.request_hash
                 AND root.billing_account_id::text=prepared_target)
            WHEN 'payment_allocate' THEN EXISTS (
              SELECT 1 FROM public.billing_allocations root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.client_operation_id=NEW.client_operation_id
                 AND root.request_hash=NEW.request_hash
                 AND root.payment_id::text=prepared_target)
            WHEN 'credit_issue' THEN EXISTS (
              SELECT 1 FROM public.billing_credits root
               WHERE root.organization_id=NEW.organization_id AND root.id=NEW.result_id
                 AND root.client_operation_id=NEW.client_operation_id
                 AND root.request_hash=NEW.request_hash
                 AND root.invoice_id::text=prepared_target)
            ELSE false END;
          journal_required := NEW.result_kind IN
            ('billing_invoice','billing_payment','billing_allocation','billing_credit');
          expected_audit_action := CASE NEW.command_type
            WHEN 'account_open' THEN 'billing.account.opened'
            WHEN 'account_payer_assign' THEN 'billing.account.payer_assigned'
            WHEN 'rate_version_publish' THEN 'billing.rate_plan.published'
            WHEN 'agreement_establish' THEN 'billing.agreement.reviewed'
            WHEN 'invoice_issue' THEN 'billing.invoice.issued'
            WHEN 'payment_record' THEN 'billing.payment.recorded'
            WHEN 'payment_allocate' THEN 'billing.payment.allocated'
            WHEN 'credit_issue' THEN 'billing.credit.issued' END;
          expected_event_type := CASE NEW.command_type
            WHEN 'account_open' THEN 'billing.account.changed'
            WHEN 'account_payer_assign' THEN 'billing.account.changed'
            WHEN 'rate_version_publish' THEN 'billing.rate_plan.changed'
            WHEN 'agreement_establish' THEN 'billing.agreement.changed'
            WHEN 'invoice_issue' THEN 'billing.invoice.changed'
            WHEN 'payment_record' THEN 'billing.payment.changed'
            WHEN 'payment_allocate' THEN 'billing.allocation.changed'
            WHEN 'credit_issue' THEN 'billing.credit.changed' END;
          IF NOT fact_exists OR (journal_required AND NOT EXISTS (
               SELECT 1 FROM public.billing_journal_entries journal
               WHERE journal.organization_id=NEW.organization_id
                 AND journal.source_type=NEW.result_kind AND journal.source_id=NEW.result_id
                 AND journal.client_operation_id=NEW.client_operation_id
                 AND journal.request_hash=NEW.request_hash
                 AND journal.posted_by_user_id=NEW.actor_user_id))
             OR NOT EXISTS (SELECT 1 FROM public.audit_events audit
               WHERE audit.organization_id=NEW.organization_id
                 AND audit.actor_user_id=NEW.actor_user_id
                 AND audit.action=expected_audit_action
                 AND audit.entity_type=NEW.result_kind AND audit.entity_id=NEW.result_id
                 AND audit.details::jsonb->>'client_operation_id'=NEW.client_operation_id::text
                 AND audit.details::jsonb->>'request_hash'=NEW.request_hash)
             OR NOT EXISTS (SELECT 1 FROM public.realtime_events event
               WHERE event.organization_id=NEW.organization_id
                 AND event.event_type=expected_event_type
                 AND event.entity_type=NEW.result_kind AND event.entity_id=NEW.result_id
                 AND event.payload::jsonb->>'client_operation_id'=
                     NEW.client_operation_id::text
                 AND event.payload::jsonb->>'request_hash'=NEW.request_hash) THEN
            RAISE EXCEPTION '0033 terminal receipt proof is incomplete'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_command_receipts_0033_guard BEFORE INSERT "
        "ON billing_command_receipts FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0033_receipt_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_claim_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE expected_kind text;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'billing:0033:'||NEW.organization_id||':operation:'||NEW.client_operation_id,0));
          expected_kind := CASE NEW.command_type
            WHEN 'account_open' THEN 'billing_account'
            WHEN 'account_payer_assign' THEN 'billing_account'
            WHEN 'rate_version_publish' THEN 'billing_rate_plan'
            WHEN 'agreement_establish' THEN 'billing_agreement'
            WHEN 'invoice_issue' THEN 'billing_invoice'
            WHEN 'payment_record' THEN 'billing_payment'
            WHEN 'payment_allocate' THEN 'billing_allocation'
            WHEN 'credit_issue' THEN 'billing_credit' END;
          IF NULLIF(current_setting('app.current_billing_operation_id',true),'')::uuid
               IS DISTINCT FROM NEW.client_operation_id
             OR NOT EXISTS (SELECT 1 FROM public.billing_command_preparations preparation
               WHERE preparation.organization_id=NEW.organization_id
                 AND preparation.client_operation_id=NEW.client_operation_id
                 AND preparation.actor_user_id=NEW.actor_user_id
                 AND preparation.command_type=NEW.command_type
                 AND preparation.request_hash=NEW.request_hash
                 AND preparation.target_scope=NEW.target_scope)
             OR EXISTS (SELECT 1 FROM public.billing_command_receipts receipt
               WHERE receipt.organization_id=NEW.organization_id
                 AND receipt.client_operation_id=NEW.client_operation_id)
             OR NOT EXISTS (SELECT 1 FROM public.audit_events audit
               WHERE audit.organization_id=NEW.organization_id
                 AND audit.actor_user_id=NEW.actor_user_id
                 AND audit.action='billing.command.finalized_absent'
                 AND audit.entity_type=expected_kind
                 AND audit.entity_id IS NULL
                 AND audit.details::jsonb->>'claim_id'=NEW.id::text
                 AND audit.details::jsonb->>'client_operation_id'=NEW.client_operation_id::text
                 AND audit.details::jsonb->>'request_hash'=NEW.request_hash)
             OR NOT EXISTS (SELECT 1 FROM public.realtime_events event
               WHERE event.organization_id=NEW.organization_id
                 AND event.event_type='billing.command.finalized_absent'
                 AND event.entity_type=expected_kind AND event.entity_id IS NULL
                 AND event.occurred_at=NEW.finalized_at) THEN
            RAISE EXCEPTION '0033 command absence proof is incomplete or conflicting'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_command_claims_0033_guard BEFORE INSERT "
        "ON billing_command_claims FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0033_claim_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0033_terminal_claim() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        BEGIN
          INSERT INTO public.billing_command_terminals(
            id,organization_id,actor_user_id,client_operation_id,command_type,
            request_hash,terminal_kind,terminal_id,created_at
          ) VALUES (
            NEW.id,NEW.organization_id,NEW.actor_user_id,NEW.client_operation_id,
            NEW.command_type,NEW.request_hash,
            CASE TG_TABLE_NAME WHEN 'billing_command_receipts' THEN 'receipt'
              ELSE 'absence_claim' END,
            NEW.id,COALESCE(
              (to_jsonb(NEW)->>'committed_at')::timestamptz,
              (to_jsonb(NEW)->>'finalized_at')::timestamptz
            )
          );
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER billing_command_receipts_0033_terminal AFTER INSERT ON "
        "billing_command_receipts FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0033_terminal_claim()"
    )
    op.execute(
        "CREATE TRIGGER billing_command_claims_0033_terminal AFTER INSERT ON "
        "billing_command_claims FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0033_terminal_claim()"
    )


def _postgres_rls_and_grants() -> None:
    org = "NULLIF(current_setting('app.current_organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.current_user_id',true),'')::uuid"

    def allowed(permission: str) -> str:
        return (
            f"organization_id={org} AND EXISTS (SELECT 1 FROM organization_memberships m "
            "JOIN roles r ON r.organization_id=m.organization_id AND r.id=m.role_id "
            f"WHERE m.organization_id={org} AND m.user_id={user} AND m.status='active' "
            "AND r.key IN ('owner','administrator') AND "
            f"r.permissions::jsonb @> '[\"{permission}\"]'::jsonb)"
        )

    insert_permissions = {
        "billing_accounts": "billing:manage",
        "billing_account_payer_versions": "billing:manage",
        "billing_rate_plans": "billing:manage",
        "billing_rate_plan_versions": "billing:manage",
        "billing_agreements": "billing:manage",
        "billing_agreement_versions": "billing:manage",
        "billing_invoices": "billing:issue",
        "billing_invoice_lines": "billing:issue",
        "billing_payments": "billing:payments",
        "billing_allocations": "billing:payments",
        "billing_credits": "billing:adjust",
        "billing_command_claims": "billing:recover",
    }
    op.execute("REVOKE ALL ON TABLE public.billing_0033_role_permission_backups FROM PUBLIC")
    for table in TABLE_NAMES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_0033_select ON {table} FOR SELECT "
            f"USING ({allowed('billing:read')})"
        )
        if table in insert_permissions:
            permission = insert_permissions[table]
            op.execute(
                f"CREATE POLICY {table}_0033_insert ON {table} FOR INSERT "
                f"WITH CHECK ({allowed(permission)})"
            )
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
    preparation_permission = (
        "((command_type IN ('account_open','account_payer_assign','rate_version_publish',"
        "'agreement_establish') AND "
        f"{allowed('billing:manage')}) OR (command_type='invoice_issue' AND "
        f"{allowed('billing:issue')}) OR (command_type IN ('payment_record',"
        f"'payment_allocate') AND {allowed('billing:payments')}) OR "
        f"(command_type='credit_issue' AND {allowed('billing:adjust')}))"
    )
    op.execute(
        "CREATE POLICY billing_command_preparations_0033_insert ON "
        "billing_command_preparations FOR INSERT WITH CHECK "
        f"({preparation_permission})"
    )
    receipt_permission = preparation_permission
    op.execute(
        "CREATE POLICY billing_command_receipts_0033_insert ON billing_command_receipts "
        f"FOR INSERT WITH CHECK ({receipt_permission})"
    )
    op.execute(
        "CREATE POLICY billing_command_terminals_0033_insert ON billing_command_terminals "
        f"FOR INSERT WITH CHECK ({receipt_permission})"
    )
    journal_permission = (
        f"((entry_kind='invoice_issued' AND {allowed('billing:issue')}) OR "
        f"(entry_kind IN ('payment_settled','payment_allocated') AND "
        f"{allowed('billing:payments')}) OR (entry_kind='credit_issued' AND "
        f"{allowed('billing:adjust')}))"
    )
    op.execute(
        "CREATE POLICY billing_journal_entries_0033_insert ON billing_journal_entries "
        f"FOR INSERT WITH CHECK ({journal_permission})"
    )
    journal_line_permission = (
        "((EXISTS (SELECT 1 FROM billing_journal_entries parent WHERE parent.organization_id="
        "billing_journal_lines.organization_id AND parent.id=journal_entry_id AND "
        f"parent.entry_kind='invoice_issued') AND {allowed('billing:issue')}) OR "
        "(EXISTS (SELECT 1 FROM billing_journal_entries parent WHERE parent.organization_id="
        "billing_journal_lines.organization_id AND parent.id=journal_entry_id AND "
        f"parent.entry_kind IN ('payment_settled','payment_allocated')) AND "
        f"{allowed('billing:payments')}) OR (EXISTS (SELECT 1 FROM billing_journal_entries "
        "parent WHERE parent.organization_id=billing_journal_lines.organization_id AND "
        f"parent.id=journal_entry_id AND parent.entry_kind='credit_issued') AND "
        f"{allowed('billing:adjust')}))"
    )
    op.execute(
        "CREATE POLICY billing_journal_lines_0033_insert ON billing_journal_lines "
        f"FOR INSERT WITH CHECK ({journal_line_permission})"
    )
    for signature in POSTGRES_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE ALL ON TABLE public.billing_0033_role_permission_backups
              FROM caresync_basic_app;
            GRANT SELECT ON TABLE
              public.billing_sandbox_source_attestations,
              public.billing_accounts,public.billing_account_payer_versions,
              public.billing_rate_plans,public.billing_rate_plan_versions,
              public.billing_agreements,public.billing_agreement_versions,
              public.billing_invoices,public.billing_invoice_lines,
              public.billing_payments,public.billing_allocations,public.billing_credits,
              public.billing_journal_entries,public.billing_journal_lines,
              public.billing_reversals,public.billing_command_preparations,
              public.billing_command_terminals,public.billing_command_receipts,
              public.billing_command_claims
              TO caresync_basic_app;
            GRANT INSERT ON TABLE
              public.billing_accounts,public.billing_account_payer_versions,
              public.billing_rate_plans,public.billing_rate_plan_versions,
              public.billing_agreements,public.billing_agreement_versions,
              public.billing_invoices,public.billing_invoice_lines,
              public.billing_payments,public.billing_allocations,public.billing_credits,
              public.billing_journal_entries,public.billing_journal_lines,
              public.billing_command_preparations,
              public.billing_command_receipts,
              public.billing_command_claims TO caresync_basic_app;
            REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER
              ON public.billing_sandbox_source_attestations FROM caresync_basic_app;
            REVOKE UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER
              ON TABLE public.billing_accounts,public.billing_account_payer_versions,
              public.billing_rate_plans,public.billing_rate_plan_versions,
              public.billing_agreements,public.billing_agreement_versions,
              public.billing_invoices,public.billing_invoice_lines,
              public.billing_payments,public.billing_allocations,public.billing_credits,
              public.billing_journal_entries,public.billing_journal_lines,
              public.billing_reversals,public.billing_command_preparations,
              public.billing_command_receipts,
              public.billing_command_claims FROM caresync_basic_app;
          END IF;
        END $grants$
        """
    )


def _sqlite_guards() -> None:
    for table in TABLE_NAMES:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_0033_immutable_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT,'0033 immutable billing fact'); END"
            )
    owner_values = (
        "'billing:adjust','billing:close','billing:issue','billing:manage',"
        "'billing:payments','billing:read','billing:recover'"
    )
    administrator_values = (
        "'billing:issue','billing:manage','billing:payments','billing:read','billing:recover'"
    )
    role_guard = (
        "(NEW.key='owner' AND ((SELECT count(DISTINCT value) FROM json_each(NEW.permissions) "
        "WHERE value LIKE 'billing:%')<>7 OR EXISTS (SELECT 1 FROM json_each(NEW.permissions) "
        f"WHERE value LIKE 'billing:%' AND value NOT IN ({owner_values})))) OR "
        "(NEW.key='administrator' AND ((SELECT count(DISTINCT value) FROM "
        "json_each(NEW.permissions) WHERE value LIKE 'billing:%')<>5 OR EXISTS (SELECT 1 "
        "FROM json_each(NEW.permissions) WHERE value LIKE 'billing:%' AND value NOT IN "
        f"({administrator_values})))) OR (NEW.key NOT IN ('owner','administrator') AND "
        "EXISTS (SELECT 1 FROM json_each(NEW.permissions) WHERE value LIKE 'billing:%'))"
    )
    op.execute(
        "CREATE TRIGGER roles_0033_billing_permissions_insert BEFORE INSERT ON roles WHEN "
        f"{role_guard} BEGIN SELECT RAISE(ABORT,'0033 invalid role billing permissions'); END"
    )
    op.execute(
        "CREATE TRIGGER roles_0033_billing_permissions_update BEFORE UPDATE OF key,permissions "
        f"ON roles WHEN {role_guard} BEGIN SELECT RAISE(ABORT,"
        "'0033 invalid role billing permissions'); END"
    )
    source_relations = {
        "organization": ("organizations", "id", "id"),
        "family": ("families", "organization_id", "id"),
        "guardian": ("guardians", "organization_id", "id"),
        "child": ("children", "organization_id", "id"),
        "enrollment": ("enrollments", "organization_id", "id"),
        "facility": ("facilities", "organization_id", "id"),
        "program": ("facility_programs", "organization_id", "id"),
    }
    branches = " AND ".join(
        f"(NEW.source_type<>'{kind}' OR EXISTS (SELECT 1 FROM {table} source "
        f"WHERE source.{org_column}=NEW.organization_id AND source.{id_column}=NEW.source_id))"
        for kind, (table, org_column, id_column) in source_relations.items()
    )
    op.execute(
        "CREATE TRIGGER billing_sandbox_source_attestations_0033_insert_guard BEFORE INSERT "
        "ON billing_sandbox_source_attestations WHEN NOT EXISTS (SELECT 1 FROM "
        "organization_memberships actor WHERE actor.organization_id=NEW.organization_id "
        "AND actor.user_id=NEW.attested_by_user_id AND actor.status='active') OR NOT ("
        f"{branches}) OR (NEW.source_type<>'organization' AND NOT EXISTS (SELECT 1 FROM "
        "billing_sandbox_source_attestations root WHERE root.organization_id="
        "NEW.organization_id AND root.source_type='organization' AND root.source_id="
        "NEW.organization_id)) BEGIN SELECT RAISE(ABORT,'0033 invalid synthetic source'); END"
    )
    for table, source_kind in SOURCE_TABLE_TYPES.items():
        organization_expression = "OLD.id" if table == "organizations" else "OLD.organization_id"
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_0033_attested_source_immutable_"
                f"{operation.lower()} BEFORE {operation} ON {table} WHEN EXISTS (SELECT 1 "
                "FROM billing_sandbox_source_attestations attestation WHERE "
                f"attestation.organization_id={organization_expression} AND "
                f"attestation.source_type='{source_kind}' AND attestation.source_id=OLD.id "
                "AND attestation.marker='TEST_SYNTHETIC_ONLY' AND "
                "attestation.reason_code='disposable_test_fixture') BEGIN SELECT "
                "RAISE(ABORT,'0033 attested synthetic source is immutable'); END"
            )
    actor_tables = {
        "billing_accounts": "opened_by_user_id",
        "billing_account_payer_versions": "assigned_by_user_id",
        "billing_rate_plans": "created_by_user_id",
        "billing_rate_plan_versions": "published_by_user_id",
        "billing_agreements": "created_by_user_id",
        "billing_agreement_versions": "reviewed_by_user_id",
        "billing_invoices": "issued_by_user_id",
        "billing_payments": "recorded_by_user_id",
        "billing_allocations": "allocated_by_user_id",
        "billing_credits": "issued_by_user_id",
        "billing_journal_entries": "posted_by_user_id",
        "billing_reversals": "reversed_by_user_id",
        "billing_command_preparations": "actor_user_id",
        "billing_command_receipts": "actor_user_id",
        "billing_command_claims": "actor_user_id",
    }
    for table, column in actor_tables.items():
        op.execute(
            f"CREATE TRIGGER {table}_0033_actor BEFORE INSERT ON {table} WHEN NOT EXISTS "
            "(SELECT 1 FROM organization_memberships member JOIN roles role ON "
            "role.organization_id=member.organization_id AND role.id=member.role_id WHERE "
            f"member.organization_id=NEW.organization_id AND member.user_id=NEW.{column} "
            "AND member.status='active' AND role.key IN ('owner','administrator')) BEGIN "
            "SELECT RAISE(ABORT,'0033 invalid billing actor'); END"
        )
    for table, root_table, root_column in (
        ("billing_account_payer_versions", "billing_accounts", "billing_account_id"),
        ("billing_rate_plan_versions", "billing_rate_plans", "rate_plan_id"),
        ("billing_agreement_versions", "billing_agreements", "agreement_id"),
    ):
        op.execute(
            f"CREATE TRIGGER {table}_0033_version BEFORE INSERT ON {table} WHEN "
            f"NEW.version_number<>COALESCE((SELECT max(version_number)+1 FROM {table} "
            f"WHERE organization_id=NEW.organization_id AND {root_column}=NEW.{root_column}),1) "
            f"OR NOT EXISTS (SELECT 1 FROM {root_table} root WHERE root.organization_id="
            f"NEW.organization_id AND root.id=NEW.{root_column}) BEGIN SELECT "
            "RAISE(ABORT,'0033 invalid billing version sequence'); END"
        )
    op.execute(
        "CREATE TRIGGER billing_allocations_0033_guard BEFORE INSERT ON billing_allocations "
        "WHEN NOT EXISTS (SELECT 1 FROM billing_payments payment JOIN billing_invoices invoice "
        "ON invoice.organization_id=payment.organization_id AND invoice.billing_account_id="
        "payment.billing_account_id WHERE payment.organization_id=NEW.organization_id AND "
        "payment.id=NEW.payment_id AND invoice.id=NEW.invoice_id AND payment.billing_account_id="
        "NEW.billing_account_id AND COALESCE((SELECT sum(amount_minor) FROM billing_allocations "
        "WHERE organization_id=NEW.organization_id AND payment_id=NEW.payment_id),0)+"
        "NEW.amount_minor<=payment.amount_minor AND COALESCE((SELECT sum(amount_minor) FROM "
        "billing_allocations WHERE organization_id=NEW.organization_id AND invoice_id="
        "NEW.invoice_id),0)+COALESCE((SELECT sum(amount_minor) FROM billing_credits WHERE "
        "organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id),0)+NEW.amount_minor"
        "<=invoice.total_minor) BEGIN SELECT RAISE(ABORT,'0033 allocation exceeds balance'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_invoices_0033_payer_guard BEFORE INSERT ON billing_invoices "
        "WHEN NOT EXISTS (SELECT 1 FROM billing_account_payer_versions payer_version JOIN "
        "guardians guardian ON guardian.organization_id=payer_version.organization_id AND "
        "guardian.family_id=payer_version.family_id AND guardian.id="
        "payer_version.payer_guardian_id JOIN families family ON family.organization_id="
        "payer_version.organization_id AND family.id=payer_version.family_id WHERE "
        "payer_version.organization_id=NEW.organization_id AND payer_version.billing_account_id="
        "NEW.billing_account_id AND payer_version.id=NEW.billing_account_payer_version_id AND "
        "payer_version.family_id=NEW.family_id AND payer_version.payer_guardian_id="
        "NEW.payer_guardian_id AND NEW.family_name_snapshot=family.name AND "
        "NEW.payer_name_snapshot=trim(guardian.first_name||' '||guardian.last_name) AND "
        "NEW.payer_email_snapshot IS NULLIF(guardian.email,'') AND "
        "NEW.payer_address_snapshot IS NULLIF(trim(COALESCE(guardian.address||', ','')||"
        "COALESCE(guardian.city||', ','')||COALESCE(guardian.postal_code,''),', '),'') AND "
        "EXISTS (SELECT 1 FROM billing_sandbox_source_attestations attestation WHERE "
        "attestation.organization_id=NEW.organization_id AND attestation.source_type='guardian' "
        "AND attestation.source_id=NEW.payer_guardian_id AND attestation.marker="
        "'TEST_SYNTHETIC_ONLY' AND attestation.reason_code='disposable_test_fixture')) BEGIN "
        "SELECT RAISE(ABORT,'0033 invalid invoice payer snapshot'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_credits_0033_guard BEFORE INSERT ON billing_credits WHEN NOT "
        "EXISTS (SELECT 1 FROM billing_invoices invoice WHERE invoice.organization_id="
        "NEW.organization_id AND invoice.id=NEW.invoice_id AND invoice.billing_account_id="
        "NEW.billing_account_id AND COALESCE((SELECT sum(amount_minor) FROM billing_allocations "
        "WHERE organization_id=NEW.organization_id AND invoice_id=NEW.invoice_id),0)+"
        "COALESCE((SELECT sum(amount_minor) FROM billing_credits WHERE organization_id="
        "NEW.organization_id AND invoice_id=NEW.invoice_id),0)+NEW.amount_minor<="
        "invoice.total_minor) "
        "BEGIN SELECT RAISE(ABORT,'0033 credit exceeds balance'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_journal_entries_0033_sequence BEFORE INSERT ON "
        "billing_journal_entries WHEN NEW.book_sequence<>COALESCE((SELECT "
        "max(book_sequence)+1 FROM billing_journal_entries WHERE organization_id="
        "NEW.organization_id),1) OR NOT EXISTS (SELECT 1 FROM "
        "billing_command_preparations preparation WHERE preparation.organization_id="
        "NEW.organization_id AND preparation.client_operation_id=NEW.client_operation_id "
        "AND preparation.actor_user_id=NEW.posted_by_user_id AND preparation.request_hash="
        "NEW.request_hash AND preparation.command_type=CASE NEW.entry_kind WHEN "
        "'invoice_issued' THEN 'invoice_issue' WHEN 'payment_settled' THEN "
        "'payment_record' WHEN 'payment_allocated' THEN 'payment_allocate' WHEN "
        "'credit_issued' THEN 'credit_issue' END) BEGIN SELECT RAISE(ABORT,"
        "'0033 invalid journal operation or book sequence'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_journal_lines_0033_guard BEFORE INSERT ON billing_journal_lines "
        "WHEN NOT EXISTS (SELECT 1 FROM billing_journal_entries entry WHERE entry.organization_id="
        "NEW.organization_id AND entry.id=NEW.journal_entry_id AND NEW.line_number="
        "COALESCE((SELECT max(line_number)+1 FROM billing_journal_lines WHERE organization_id="
        "NEW.organization_id AND journal_entry_id=NEW.journal_entry_id),1) AND "
        "(SELECT count(*) FROM billing_journal_lines WHERE organization_id=NEW.organization_id "
        "AND journal_entry_id=NEW.journal_entry_id)<entry.line_count AND COALESCE((SELECT "
        "sum(amount_minor) FROM billing_journal_lines WHERE organization_id=NEW.organization_id "
        "AND journal_entry_id=NEW.journal_entry_id AND direction=NEW.direction),0)+NEW.amount_minor"
        "<=CASE NEW.direction WHEN 'debit' THEN entry.total_debit_minor ELSE "
        "entry.total_credit_minor END) BEGIN SELECT RAISE(ABORT,'0033 invalid journal line'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_command_receipts_0033_guard BEFORE INSERT ON "
        "billing_command_receipts WHEN NOT EXISTS (SELECT 1 FROM billing_command_preparations "
        "preparation WHERE preparation.organization_id=NEW.organization_id AND preparation."
        "client_operation_id=NEW.client_operation_id AND preparation.actor_user_id="
        "NEW.actor_user_id AND preparation.command_type=NEW.command_type AND preparation."
        "request_hash=NEW.request_hash) OR EXISTS (SELECT 1 FROM billing_command_claims "
        "claim WHERE "
        "claim.organization_id=NEW.organization_id AND claim.client_operation_id="
        "NEW.client_operation_id) OR NOT EXISTS (SELECT 1 FROM audit_events audit WHERE "
        "audit.organization_id=NEW.organization_id AND audit.actor_user_id=NEW.actor_user_id "
        "AND audit.action=CASE NEW.command_type WHEN 'account_open' THEN "
        "'billing.account.opened' WHEN 'account_payer_assign' THEN "
        "'billing.account.payer_assigned' WHEN 'rate_version_publish' THEN "
        "'billing.rate_plan.published' WHEN 'agreement_establish' THEN "
        "'billing.agreement.reviewed' WHEN 'invoice_issue' THEN 'billing.invoice.issued' "
        "WHEN 'payment_record' THEN 'billing.payment.recorded' WHEN 'payment_allocate' "
        "THEN 'billing.payment.allocated' WHEN 'credit_issue' THEN "
        "'billing.credit.issued' END AND audit.entity_type=NEW.result_kind AND "
        "audit.entity_id=NEW.result_id AND "
        "replace(json_extract(audit.details,'$.client_operation_id'),'-','')="
        "CAST(NEW.client_operation_id AS TEXT) AND json_extract(audit.details,"
        "'$.request_hash')=NEW.request_hash) "
        "OR NOT EXISTS (SELECT 1 FROM realtime_events event WHERE event.organization_id="
        "NEW.organization_id AND event.event_type=CASE NEW.command_type WHEN "
        "'account_open' THEN 'billing.account.changed' WHEN 'account_payer_assign' THEN "
        "'billing.account.changed' WHEN 'rate_version_publish' THEN "
        "'billing.rate_plan.changed' WHEN 'agreement_establish' THEN "
        "'billing.agreement.changed' WHEN 'invoice_issue' THEN 'billing.invoice.changed' "
        "WHEN 'payment_record' THEN 'billing.payment.changed' WHEN 'payment_allocate' THEN "
        "'billing.allocation.changed' WHEN 'credit_issue' THEN 'billing.credit.changed' END "
        "AND event.entity_type=NEW.result_kind AND event.entity_id=NEW.result_id AND "
        "replace(json_extract(event.payload,'$.client_operation_id'),'-','')="
        "CAST(NEW.client_operation_id "
        "AS TEXT) AND json_extract(event.payload,'$.request_hash')=NEW.request_hash) OR "
        "(NEW.result_kind IN ('billing_invoice','billing_payment',"
        "'billing_allocation','billing_credit') AND NOT EXISTS (SELECT 1 FROM "
        "billing_journal_entries journal WHERE journal.organization_id=NEW.organization_id AND "
        "journal.source_type=NEW.result_kind AND journal.source_id=NEW.result_id AND "
        "journal.client_operation_id=NEW.client_operation_id AND journal.request_hash="
        "NEW.request_hash AND journal.posted_by_user_id=NEW.actor_user_id AND "
        "journal.line_count=(SELECT count(*) FROM billing_journal_lines line WHERE "
        "line.organization_id=journal.organization_id AND line.journal_entry_id=journal.id) AND "
        "journal.total_debit_minor=(SELECT sum(amount_minor) FROM billing_journal_lines line WHERE "
        "line.organization_id=journal.organization_id AND line.journal_entry_id=journal.id AND "
        "line.direction='debit') AND journal.total_credit_minor=(SELECT sum(amount_minor) FROM "
        "billing_journal_lines line WHERE line.organization_id=journal.organization_id AND "
        "line.journal_entry_id=journal.id AND line.direction='credit'))) BEGIN SELECT "
        "RAISE(ABORT,'0033 incomplete terminal receipt proof'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_command_claims_0033_guard BEFORE INSERT ON "
        "billing_command_claims WHEN NOT EXISTS (SELECT 1 FROM billing_command_preparations "
        "preparation WHERE preparation.organization_id=NEW.organization_id AND preparation."
        "client_operation_id=NEW.client_operation_id AND preparation.actor_user_id="
        "NEW.actor_user_id AND preparation.command_type=NEW.command_type AND preparation."
        "request_hash=NEW.request_hash AND preparation.target_scope=NEW.target_scope) OR EXISTS "
        "(SELECT 1 FROM billing_command_receipts receipt WHERE "
        "receipt.organization_id=NEW.organization_id AND receipt.client_operation_id="
        "NEW.client_operation_id) OR NOT EXISTS (SELECT 1 FROM audit_events audit WHERE "
        "audit.organization_id=NEW.organization_id AND audit.actor_user_id=NEW.actor_user_id AND "
        "audit.action='billing.command.finalized_absent' AND audit.entity_type=CASE "
        "NEW.command_type WHEN 'account_open' THEN 'billing_account' WHEN "
        "'account_payer_assign' THEN 'billing_account' WHEN 'rate_version_publish' THEN "
        "'billing_rate_plan' WHEN 'agreement_establish' THEN 'billing_agreement' WHEN "
        "'invoice_issue' THEN 'billing_invoice' WHEN 'payment_record' THEN "
        "'billing_payment' WHEN 'payment_allocate' THEN 'billing_allocation' WHEN "
        "'credit_issue' THEN 'billing_credit' END AND audit.entity_id IS NULL AND "
        "replace(json_extract(audit.details,'$.claim_id'),'-','')=CAST(NEW.id AS TEXT) AND "
        "replace(json_extract("
        "audit.details,'$.client_operation_id'),'-','')="
        "CAST(NEW.client_operation_id AS TEXT) AND json_extract("
        "audit.details,'$.request_hash')=NEW.request_hash) OR NOT EXISTS (SELECT 1 FROM "
        "realtime_events event WHERE event.organization_id=NEW.organization_id AND "
        "event.event_type='billing.command.finalized_absent' AND event.entity_type=CASE "
        "NEW.command_type WHEN 'account_open' THEN 'billing_account' WHEN "
        "'account_payer_assign' THEN 'billing_account' WHEN 'rate_version_publish' THEN "
        "'billing_rate_plan' WHEN 'agreement_establish' THEN 'billing_agreement' WHEN "
        "'invoice_issue' THEN 'billing_invoice' WHEN 'payment_record' THEN "
        "'billing_payment' WHEN 'payment_allocate' THEN 'billing_allocation' WHEN "
        "'credit_issue' THEN 'billing_credit' END AND event.entity_id IS NULL AND "
        "event.occurred_at=NEW.finalized_at) BEGIN "
        "SELECT RAISE(ABORT,"
        "'0033 incomplete absence proof'); END"
    )
    op.execute(
        "CREATE TRIGGER billing_command_receipts_0033_terminal AFTER INSERT ON "
        "billing_command_receipts BEGIN INSERT INTO billing_command_terminals("
        "id,organization_id,actor_user_id,client_operation_id,command_type,request_hash,"
        "terminal_kind,terminal_id,created_at) VALUES (NEW.id,NEW.organization_id,"
        "NEW.actor_user_id,NEW.client_operation_id,NEW.command_type,NEW.request_hash,"
        "'receipt',NEW.id,NEW.committed_at); END"
    )
    op.execute(
        "CREATE TRIGGER billing_command_claims_0033_terminal AFTER INSERT ON "
        "billing_command_claims BEGIN INSERT INTO billing_command_terminals("
        "id,organization_id,actor_user_id,client_operation_id,command_type,request_hash,"
        "terminal_kind,terminal_id,created_at) VALUES (NEW.id,NEW.organization_id,"
        "NEW.actor_user_id,NEW.client_operation_id,NEW.command_type,NEW.request_hash,"
        "'absence_claim',NEW.id,NEW.finalized_at); END"
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        ROLE_PERMISSION_BACKUP_TABLE,
        sa.Column("role_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
    )
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    _freeze_original_billing_agreement_scope(bind)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.roles DISABLE ROW LEVEL SECURITY")
    try:
        bind.execute(
            sa.text(
                f"INSERT INTO {ROLE_PERMISSION_BACKUP_TABLE}(role_id,permissions) "
                "SELECT id,permissions FROM roles"
            )
        )
        _backfill_role_permissions(bind)
    finally:
        if bind.dialect.name == "postgresql":
            op.execute("ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY")
            op.execute("ALTER TABLE public.roles FORCE ROW LEVEL SECURITY")
    if bind.dialect.name == "postgresql":
        _postgres_guards()
        _postgres_rls_and_grants()
    else:
        _sqlite_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TABLE_NAMES:
            op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.roles DISABLE ROW LEVEL SECURITY")
    if any(
        bool(bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} LIMIT 1)")))
        for table in TABLE_NAMES
    ):
        raise RuntimeError("0033 downgrade refused: billing ledger or attestations exist")
    if bind.dialect.name == "postgresql":
        for table in TABLE_NAMES:
            op.execute(f"DROP POLICY IF EXISTS {table}_0033_select ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_0033_insert ON {table}")
        for signature in POSTGRES_FUNCTIONS:
            op.execute(f"DROP FUNCTION IF EXISTS public.{signature} CASCADE")
    else:
        trigger_rows = bind.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%_0033_%'")
        )
        for row in trigger_rows:
            op.execute(f"DROP TRIGGER IF EXISTS {row.name}")
    bind.execute(
        sa.text(
            f"UPDATE roles SET permissions=(SELECT backup.permissions FROM "
            f"{ROLE_PERMISSION_BACKUP_TABLE} backup WHERE backup.role_id=roles.id) "
            f"WHERE EXISTS (SELECT 1 FROM {ROLE_PERMISSION_BACKUP_TABLE} backup "
            "WHERE backup.role_id=roles.id)"
        )
    )
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE roles SET permissions=(SELECT COALESCE(json_agg(value ORDER BY value),"
                "'[]'::json) FROM jsonb_array_elements_text(COALESCE(roles.permissions::jsonb,"
                "'[]'::jsonb)) AS value WHERE value NOT LIKE 'billing:%') WHERE NOT EXISTS "
                f"(SELECT 1 FROM {ROLE_PERMISSION_BACKUP_TABLE} backup "
                "WHERE backup.role_id=roles.id)"
            )
        )
    else:
        for row in bind.execute(
            sa.text(
                f"SELECT id,permissions FROM roles WHERE id NOT IN "
                f"(SELECT role_id FROM {ROLE_PERMISSION_BACKUP_TABLE})"
            )
        ).mappings():
            values = [
                value
                for value in json.loads(row["permissions"] or "[]")
                if not value.startswith("billing:")
            ]
            bind.execute(
                sa.text("UPDATE roles SET permissions=:permissions WHERE id=:id"),
                {"permissions": json.dumps(values), "id": row["id"]},
            )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.roles FORCE ROW LEVEL SECURITY")
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)
    op.drop_table(ROLE_PERMISSION_BACKUP_TABLE)

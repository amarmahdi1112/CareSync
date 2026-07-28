"""Recertify the frozen 0033 PostgreSQL billing-policy catalog.

Revision ID: 0042_billing_policy_recert
Revises: 0041_live_room_presence
Create Date: 2026-07-23

Some retained PostgreSQL 17 databases contain one complete, semantically
equivalent catalog rendering of the 0033 policies whose expression identity no
longer matches the frozen runtime certificate.  This revision accepts only the
two audited *whole-catalog* input profiles and atomically recreates all 36
policies from the concise 0033 definitions.  It never accepts a mixture of the
profiles and never weakens row-level security.

SQLite has no PostgreSQL policy catalog, so both directions are deliberate
no-ops there.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0042_billing_policy_recert"
down_revision = "0041_live_room_presence"
branch_labels = None
depends_on = None

POSTGRESQL_MAJOR_VERSION = 17
RUNTIME_ROLE = "caresync_basic_app"

POLICY_TABLES = (
    "billing_sandbox_source_attestations",
    "billing_command_preparations",
    "billing_command_terminals",
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
    "billing_reversals",
    "billing_command_receipts",
    "billing_command_claims",
)
REFERENCE_TABLES = (
    "organization_memberships",
    "roles",
)

INSERT_POLICY_KINDS = {
    "billing_accounts": "manage",
    "billing_account_payer_versions": "manage",
    "billing_rate_plans": "manage",
    "billing_rate_plan_versions": "manage",
    "billing_agreements": "manage",
    "billing_agreement_versions": "manage",
    "billing_invoices": "issue",
    "billing_invoice_lines": "issue",
    "billing_payments": "payments",
    "billing_allocations": "payments",
    "billing_credits": "adjust",
    "billing_command_claims": "recover",
    "billing_command_preparations": "command",
    "billing_command_receipts": "command",
    "billing_command_terminals": "command",
    "billing_journal_entries": "journal_entry",
    "billing_journal_lines": "journal_line",
}

# Profile A is the exact policy identity frozen by the 0033 runtime detector.
PROFILE_A_HASHES = {
    "select": "18d93cb0b39184162b43f4ef5f9c06c919eac6b4ae696dcf3322285021503d28",
    "manage": "375bffb43c9174d5ac955031278f82237fe9ae1c0247e7ae80a7b473efa7f3eb",
    "issue": "34b1d859068b459173db0591c023310aed0de8554cee85d4e0d8164ec6e30b02",
    "payments": "e210fd5cc0fca2fb6021a68c96ed8adf438dc1320e91da21d94c8ba83252be8e",
    "adjust": "99da565eb97a063083a27abd0a6ff9a336563c0278157baf54c8f771dc8480fe",
    "recover": "fcab26ab0ba0b53667633a05c54537570741bf231fce7c1ce1b45d3c0ba07edd",
    "command": "a9e8631e078624fa64950ab0544cd646f93ca77438ed4c01e8a256473cac4f7a",
    "journal_entry": (
        "9fc77aef7678a37fef676eec4debe6314e419413995883a4d6d9635bdc3847f4"
    ),
    "journal_line": (
        "b180690f53b4441b8e4034a9ab6f68eec81a6fd28771c01ae519ba8a68305ed8"
    ),
}

# Profile B is the one complete alternate PostgreSQL 17 catalog identity
# observed in the retained pre-0042 backup.  It is accepted only as a whole.
PROFILE_B_HASHES = {
    "select": "4b64b7fb76b4cf60e1032497c5bbfbb67ceb49515ee3a1143c1e1f1346a784c2",
    "manage": "47a5b154550491be58ca93c93704d4e6fef24e2125f0c6d52ad9328627db7f9d",
    "issue": "2799b1973ad446874a2fd409fa0a7e351d5b14038582995a1855d0a4247c5aa0",
    "payments": "6f14b8f4290a26ba09048ba9f32cb186ab1a56bcdda451c5ed4be9c87b2f2a1d",
    "adjust": "f4782adcc0d042916aa875a511b23ecbbb497908278b97a3a0d56debeb4c6fc5",
    "recover": "7058ab9771fbf7b72f645c2789954e2934f74a331de1ae8ad6882820e98744b7",
    "command": "c1ef04ccc3ab509588946949e03181506a61e68f075e0dda6fd709ba84e23c89",
    "journal_entry": (
        "70e1f7b4b49fe12829ff79a4ff86d338fb7a55ca855d0728dde1e261e9d5d52a"
    ),
    "journal_line": (
        "cccd1cd9250d5f2002fad0dcc95031e6df515c43857aa7109edd68f0446a02e4"
    ),
}

_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*(?:\n|$)")


class BillingPolicyRecertificationError(RuntimeError):
    """Raised before any repair when the policy boundary is not recognized."""


def _compact_sql(definition: str) -> str:
    without_blocks = _SQL_BLOCK_COMMENT.sub(" ", definition)
    without_comments = _SQL_LINE_COMMENT.sub(" ", without_blocks)
    return "".join(without_comments.lower().split()).replace('"', "")


def _canonical_sql_sha256(definition: str) -> str:
    return hashlib.sha256(_compact_sql(definition).encode("utf-8")).hexdigest()


def _policy_specs() -> dict[tuple[str, str], tuple[str, str]]:
    specs = {
        (table, f"{table}_0033_select"): ("r", "select")
        for table in POLICY_TABLES
    }
    specs.update(
        {
            (table, f"{table}_0033_insert"): ("a", kind)
            for table, kind in INSERT_POLICY_KINDS.items()
        }
    )
    return specs


def _profile_policy_hashes(
    profile_hashes: Mapping[str, str],
) -> dict[tuple[str, str], str]:
    return {
        key: profile_hashes[kind]
        for key, (_command, kind) in _policy_specs().items()
    }


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping[key]
    return getattr(row, key)


def _public_roles(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.replace(" ", "") in {"{0}", "[0]", "(0,)"}
    return tuple(int(role) for role in value) == (0,)


def _classify_policy_rows(rows: Sequence[Any]) -> str:
    """Return ``A`` or ``B`` only for one exact whole-catalog profile."""

    specs = _policy_specs()
    keyed: dict[tuple[str, str], Any] = {}
    for row in rows:
        key = (
            str(_row_value(row, "table_name")),
            str(_row_value(row, "policy_name")),
        )
        if key in keyed:
            raise BillingPolicyRecertificationError(
                "0042 billing-policy preflight found duplicate policy identities"
            )
        keyed[key] = row
    if set(keyed) != set(specs):
        raise BillingPolicyRecertificationError(
            "0042 billing-policy preflight requires the exact 36-policy catalog"
        )

    observed_hashes: dict[tuple[str, str], str] = {}
    for key, (expected_command, _kind) in specs.items():
        row = keyed[key]
        using_expression = _row_value(row, "using_expression")
        check_expression = _row_value(row, "check_expression")
        expression = (
            using_expression if expected_command == "r" else check_expression
        )
        unused_expression = (
            check_expression if expected_command == "r" else using_expression
        )
        if (
            str(_row_value(row, "command")) != expected_command
            or not bool(_row_value(row, "permissive"))
            or not _public_roles(_row_value(row, "roles"))
            or expression is None
            or unused_expression is not None
        ):
            raise BillingPolicyRecertificationError(
                "0042 billing-policy preflight found a noncanonical policy shape"
            )
        observed_hashes[key] = _canonical_sql_sha256(str(expression))

    if observed_hashes == _profile_policy_hashes(PROFILE_A_HASHES):
        return "A"
    if observed_hashes == _profile_policy_hashes(PROFILE_B_HASHES):
        return "B"
    raise BillingPolicyRecertificationError(
        "0042 billing-policy preflight rejected an unknown or mixed catalog profile"
    )


def _require_postgresql_17(bind: sa.engine.Connection) -> None:
    version_number = int(
        bind.scalar(sa.text("SELECT current_setting('server_version_num')"))
        or 0
    )
    if version_number // 10000 != POSTGRESQL_MAJOR_VERSION:
        raise BillingPolicyRecertificationError(
            "0042 billing-policy recertification requires PostgreSQL 17"
        )


def _lock_catalog_boundary(bind: sa.engine.Connection) -> None:
    # Alembic runs this revision transactionally.  These locks close the
    # preflight-to-replacement race for policies and their referenced ACL data.
    references = ",".join(f"public.{table}" for table in sorted(REFERENCE_TABLES))
    policy_tables = ",".join(
        f"public.{table}" for table in sorted(POLICY_TABLES)
    )
    bind.exec_driver_sql(
        f"LOCK TABLE {references} IN ACCESS SHARE MODE"
    )
    bind.exec_driver_sql(
        f"LOCK TABLE {policy_tables} IN ACCESS EXCLUSIVE MODE"
    )


def _require_owned_hardened_relations(bind: sa.engine.Connection) -> None:
    expected_relations = set(POLICY_TABLES) | set(REFERENCE_TABLES)
    rows = list(
        bind.execute(
            sa.text(
                "SELECT class.relname AS table_name,class.relkind,"
                "class.relpersistence,class.relrowsecurity,class.relforcerowsecurity,"
                "pg_catalog.pg_get_userbyid(class.relowner) AS owner_name,"
                "current_user AS migration_owner "
                "FROM pg_catalog.pg_class class "
                "JOIN pg_catalog.pg_namespace namespace "
                "ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND class.relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": sorted(expected_relations)},
        )
    )
    if {
        str(_row_value(row, "table_name"))
        for row in rows
    } != expected_relations:
        raise BillingPolicyRecertificationError(
            "0042 billing-policy preflight found a missing relation"
        )
    for row in rows:
        table = str(_row_value(row, "table_name"))
        owner = str(_row_value(row, "owner_name"))
        migration_owner = str(_row_value(row, "migration_owner"))
        if (
            str(_row_value(row, "relkind")) != "r"
            or str(_row_value(row, "relpersistence")) != "p"
            or owner != migration_owner
            or owner == RUNTIME_ROLE
        ):
            raise BillingPolicyRecertificationError(
                "0042 billing-policy preflight requires migration-owned "
                "persistent relations"
            )
        if table in POLICY_TABLES and (
            not bool(_row_value(row, "relrowsecurity"))
            or not bool(_row_value(row, "relforcerowsecurity"))
        ):
            raise BillingPolicyRecertificationError(
                "0042 billing-policy preflight requires enabled and forced RLS"
            )


def _catalog_policy_rows(bind: sa.engine.Connection) -> list[Any]:
    return list(
        bind.execute(
            sa.text(
                "SELECT class.relname AS table_name,policy.polname AS policy_name,"
                "policy.polcmd AS command,policy.polpermissive AS permissive,"
                "policy.polroles AS roles,"
                "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                "AS using_expression,"
                "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                "AS check_expression "
                "FROM pg_catalog.pg_policy policy "
                "JOIN pg_catalog.pg_class class ON class.oid=policy.polrelid "
                "JOIN pg_catalog.pg_namespace namespace "
                "ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND class.relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": sorted(POLICY_TABLES)},
        )
    )


def _allowed(permission: str) -> str:
    organization = (
        "NULLIF(current_setting('app.current_organization_id',true),'')::uuid"
    )
    user = "NULLIF(current_setting('app.current_user_id',true),'')::uuid"
    return (
        f"organization_id={organization} AND EXISTS (SELECT 1 FROM "
        "organization_memberships m JOIN roles r ON "
        "r.organization_id=m.organization_id AND r.id=m.role_id "
        f"WHERE m.organization_id={organization} AND m.user_id={user} "
        "AND m.status='active' AND r.key IN ('owner','administrator') AND "
        f"r.permissions::jsonb @> '[\"{permission}\"]'::jsonb)"
    )


def _create_policy_statements() -> tuple[str, ...]:
    statements: list[str] = []
    for table in POLICY_TABLES:
        statements.append(
            f"CREATE POLICY {table}_0033_select ON public.{table} FOR SELECT "
            f"USING ({_allowed('billing:read')})"
        )

    direct_insert_permissions = {
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
    for table, permission in direct_insert_permissions.items():
        statements.append(
            f"CREATE POLICY {table}_0033_insert ON public.{table} FOR INSERT "
            f"WITH CHECK ({_allowed(permission)})"
        )

    command_permission = (
        "((command_type IN ('account_open','account_payer_assign',"
        "'rate_version_publish','agreement_establish') AND "
        f"{_allowed('billing:manage')}) OR (command_type='invoice_issue' AND "
        f"{_allowed('billing:issue')}) OR (command_type IN ('payment_record',"
        f"'payment_allocate') AND {_allowed('billing:payments')}) OR "
        f"(command_type='credit_issue' AND {_allowed('billing:adjust')}))"
    )
    for table in (
        "billing_command_preparations",
        "billing_command_receipts",
        "billing_command_terminals",
    ):
        statements.append(
            f"CREATE POLICY {table}_0033_insert ON public.{table} FOR INSERT "
            f"WITH CHECK ({command_permission})"
        )

    journal_permission = (
        f"((entry_kind='invoice_issued' AND {_allowed('billing:issue')}) OR "
        f"(entry_kind IN ('payment_settled','payment_allocated') AND "
        f"{_allowed('billing:payments')}) OR (entry_kind='credit_issued' AND "
        f"{_allowed('billing:adjust')}))"
    )
    statements.append(
        "CREATE POLICY billing_journal_entries_0033_insert ON "
        "public.billing_journal_entries FOR INSERT WITH CHECK "
        f"({journal_permission})"
    )

    journal_line_permission = (
        "((EXISTS (SELECT 1 FROM billing_journal_entries parent WHERE "
        "parent.organization_id=billing_journal_lines.organization_id AND "
        "parent.id=journal_entry_id AND parent.entry_kind='invoice_issued') AND "
        f"{_allowed('billing:issue')}) OR (EXISTS (SELECT 1 FROM "
        "billing_journal_entries parent WHERE parent.organization_id="
        "billing_journal_lines.organization_id AND parent.id=journal_entry_id AND "
        "parent.entry_kind IN ('payment_settled','payment_allocated')) AND "
        f"{_allowed('billing:payments')}) OR (EXISTS (SELECT 1 FROM "
        "billing_journal_entries parent WHERE parent.organization_id="
        "billing_journal_lines.organization_id AND parent.id=journal_entry_id AND "
        f"parent.entry_kind='credit_issued') AND {_allowed('billing:adjust')}))"
    )
    statements.append(
        "CREATE POLICY billing_journal_lines_0033_insert ON "
        "public.billing_journal_lines FOR INSERT WITH CHECK "
        f"({journal_line_permission})"
    )
    return tuple(statements)


def _replace_policies(bind: sa.engine.Connection) -> None:
    for table, policy_name in sorted(_policy_specs()):
        bind.exec_driver_sql(
            f"DROP POLICY {policy_name} ON public.{table}"
        )
    for statement in _create_policy_statements():
        bind.exec_driver_sql(statement)


def _prepare_postgresql_boundary(bind: sa.engine.Connection) -> None:
    _require_postgresql_17(bind)
    _lock_catalog_boundary(bind)
    _require_owned_hardened_relations(bind)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if bind.dialect.name != "postgresql":
        raise BillingPolicyRecertificationError(
            "0042 billing-policy recertification supports only SQLite "
            "and PostgreSQL"
        )

    _prepare_postgresql_boundary(bind)
    _classify_policy_rows(_catalog_policy_rows(bind))
    _replace_policies(bind)
    _require_owned_hardened_relations(bind)
    if _classify_policy_rows(_catalog_policy_rows(bind)) != "A":
        raise BillingPolicyRecertificationError(
            "0042 billing-policy postflight did not produce frozen profile A"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if bind.dialect.name != "postgresql":
        raise BillingPolicyRecertificationError(
            "0042 billing-policy recertification supports only SQLite "
            "and PostgreSQL"
        )

    # The revision marker may move back to 0041, but the secure recertified
    # catalog remains in place.  Refuse the downgrade if that catalog drifted.
    _prepare_postgresql_boundary(bind)
    if _classify_policy_rows(_catalog_policy_rows(bind)) != "A":
        raise BillingPolicyRecertificationError(
            "0042 billing-policy downgrade requires frozen profile A"
        )

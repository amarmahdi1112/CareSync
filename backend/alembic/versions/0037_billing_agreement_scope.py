"""Scope immutable billing agreements to one enrollment.

Revision ID: 0037_billing_agreement_scope
Revises: 0036_billing_manual_mode
Create Date: 2026-07-22

The original ledger allowed only one agreement per account and child.  That
prevented a later enrollment for the same child from receiving its own
immutable agreement.  This revision moves uniqueness to the enrollment while
retaining a partial one-per-child fallback for historical null-enrollment
agreements.  No billing fact is rewritten or removed.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037_billing_agreement_scope"
down_revision = "0036_billing_manual_mode"
branch_labels = None
depends_on = None

TABLE = "billing_agreements"
LEGACY_CONSTRAINT = "uq_bill_agreement_account_child"
ENROLLMENT_CONSTRAINT = "uq_bill_agreement_account_enrollment"
LEGACY_NULL_INDEX = "uq_bill_agreement_legacy_account_child"


def _unique_constraints(bind: sa.engine.Connection) -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(bind).get_unique_constraints(TABLE)
        if item.get("name")
    }


def _indexes(bind: sa.engine.Connection) -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(bind).get_indexes(TABLE)
        if item.get("name")
    }


def _sqlite_trigger_definitions(
    bind: sa.engine.Connection,
) -> list[tuple[str, str]]:
    return [
        (str(row.name), str(row.sql))
        for row in bind.execute(
            sa.text(
                "SELECT name,sql FROM sqlite_master "
                "WHERE type='trigger' "
                "AND (tbl_name=:table_name OR instr(lower(sql),:table_name)>0) "
                "AND sql IS NOT NULL ORDER BY name"
            ),
            {"table_name": TABLE},
        )
    ]


def _drop_sqlite_triggers(definitions: list[tuple[str, str]]) -> None:
    for name, _definition in definitions:
        op.execute(f'DROP TRIGGER "{name}"')


def _restore_sqlite_triggers(definitions: list[tuple[str, str]]) -> None:
    for _name, definition in definitions:
        op.execute(definition)


def _assert_upgrade_safe(bind: sa.engine.Connection) -> None:
    duplicate_enrollment = bind.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM billing_agreements "
            "WHERE enrollment_id IS NOT NULL "
            "GROUP BY organization_id,billing_account_id,enrollment_id "
            "HAVING count(*)>1)"
        )
    )
    duplicate_legacy = bind.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM billing_agreements "
            "WHERE enrollment_id IS NULL "
            "GROUP BY organization_id,billing_account_id,child_id "
            "HAVING count(*)>1)"
        )
    )
    if bool(duplicate_enrollment) or bool(duplicate_legacy):
        raise RuntimeError("0037 upgrade refused: billing agreement scope is ambiguous")


def _assert_downgrade_safe(bind: sa.engine.Connection) -> None:
    duplicate_child = bind.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM billing_agreements "
            "GROUP BY organization_id,billing_account_id,child_id "
            "HAVING count(*)>1)"
        )
    )
    if bool(duplicate_child):
        raise RuntimeError(
            "0037 downgrade refused: re-enrollment agreements cannot fit the 0036 scope"
        )


def _upgrade_postgresql(bind: sa.engine.Connection) -> None:
    constraints = _unique_constraints(bind)
    indexes = _indexes(bind)
    if LEGACY_CONSTRAINT in constraints:
        op.drop_constraint(
            LEGACY_CONSTRAINT,
            TABLE,
            type_="unique",
            schema="public",
        )
    if ENROLLMENT_CONSTRAINT not in constraints:
        op.create_unique_constraint(
            ENROLLMENT_CONSTRAINT,
            TABLE,
            ["organization_id", "billing_account_id", "enrollment_id"],
            schema="public",
        )
    if LEGACY_NULL_INDEX not in indexes:
        op.create_index(
            LEGACY_NULL_INDEX,
            TABLE,
            ["organization_id", "billing_account_id", "child_id"],
            unique=True,
            schema="public",
            postgresql_where=sa.text("enrollment_id IS NULL"),
        )


def _downgrade_postgresql(bind: sa.engine.Connection) -> None:
    constraints = _unique_constraints(bind)
    indexes = _indexes(bind)
    if LEGACY_NULL_INDEX in indexes:
        op.drop_index(LEGACY_NULL_INDEX, table_name=TABLE, schema="public")
    if ENROLLMENT_CONSTRAINT in constraints:
        op.drop_constraint(
            ENROLLMENT_CONSTRAINT,
            TABLE,
            type_="unique",
            schema="public",
        )
    if LEGACY_CONSTRAINT not in constraints:
        op.create_unique_constraint(
            LEGACY_CONSTRAINT,
            TABLE,
            ["organization_id", "billing_account_id", "child_id"],
            schema="public",
        )


def _upgrade_sqlite(bind: sa.engine.Connection) -> None:
    constraints = _unique_constraints(bind)
    indexes = _indexes(bind)
    if LEGACY_CONSTRAINT in constraints or ENROLLMENT_CONSTRAINT not in constraints:
        triggers = _sqlite_trigger_definitions(bind)
        _drop_sqlite_triggers(triggers)
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            if LEGACY_CONSTRAINT in constraints:
                batch.drop_constraint(LEGACY_CONSTRAINT, type_="unique")
            if ENROLLMENT_CONSTRAINT not in constraints:
                batch.create_unique_constraint(
                    ENROLLMENT_CONSTRAINT,
                    ["organization_id", "billing_account_id", "enrollment_id"],
                )
        _restore_sqlite_triggers(triggers)
    if LEGACY_NULL_INDEX not in indexes:
        op.create_index(
            LEGACY_NULL_INDEX,
            TABLE,
            ["organization_id", "billing_account_id", "child_id"],
            unique=True,
            sqlite_where=sa.text("enrollment_id IS NULL"),
        )


def _downgrade_sqlite(bind: sa.engine.Connection) -> None:
    constraints = _unique_constraints(bind)
    indexes = _indexes(bind)
    if LEGACY_NULL_INDEX in indexes:
        op.drop_index(LEGACY_NULL_INDEX, table_name=TABLE)
    if ENROLLMENT_CONSTRAINT in constraints or LEGACY_CONSTRAINT not in constraints:
        triggers = _sqlite_trigger_definitions(bind)
        _drop_sqlite_triggers(triggers)
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            if ENROLLMENT_CONSTRAINT in constraints:
                batch.drop_constraint(ENROLLMENT_CONSTRAINT, type_="unique")
            if LEGACY_CONSTRAINT not in constraints:
                batch.create_unique_constraint(
                    LEGACY_CONSTRAINT,
                    ["organization_id", "billing_account_id", "child_id"],
                )
        _restore_sqlite_triggers(triggers)


def upgrade() -> None:
    bind = op.get_bind()
    _assert_upgrade_safe(bind)
    if bind.dialect.name == "postgresql":
        _upgrade_postgresql(bind)
    else:
        _upgrade_sqlite(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _assert_downgrade_safe(bind)
    if bind.dialect.name == "postgresql":
        _downgrade_postgresql(bind)
    else:
        _downgrade_sqlite(bind)

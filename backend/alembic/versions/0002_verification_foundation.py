"""Add future-ready email, organization, and facility verification metadata.

Revision ID: 0002_verification_foundation
Revises: 0001_basic_foundation
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_verification_foundation"
down_revision = "0001_basic_foundation"
branch_labels = None
depends_on = None

MIGRATION_BACKFILL = "migration_backfill"
TENANT_VERIFICATION_TABLES = ("organizations", "facilities")


def _set_postgres_rls(*, enabled: bool) -> None:
    """Temporarily permit the owner-run backfill, then restore forced RLS."""

    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in TENANT_VERIFICATION_TABLES:
        if enabled:
            op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        else:
            op.execute(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY')


def _add_verification_columns() -> None:
    op.add_column(
        "users",
        sa.Column("email_verification_method", sa.String(length=50), nullable=True),
    )
    for table_name in TENANT_VERIFICATION_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "verification_status",
                sa.String(length=30),
                server_default="pending",
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("verification_method", sa.String(length=50), nullable=True),
        )


def _backfill_temporary_policy() -> None:
    users = sa.table(
        "users",
        sa.column("email_verified_at", sa.DateTime(timezone=True)),
        sa.column("email_verification_method", sa.String(length=50)),
    )
    op.execute(
        users.update().values(
            email_verified_at=sa.func.coalesce(users.c.email_verified_at, sa.func.now()),
            email_verification_method=MIGRATION_BACKFILL,
        )
    )

    for table_name in TENANT_VERIFICATION_TABLES:
        subject = sa.table(
            table_name,
            sa.column("verification_status", sa.String(length=30)),
            sa.column("verified_at", sa.DateTime(timezone=True)),
            sa.column("verification_method", sa.String(length=50)),
        )
        op.execute(
            subject.update().values(
                verification_status="verified",
                verified_at=sa.func.now(),
                verification_method=MIGRATION_BACKFILL,
            )
        )


def _add_verification_constraints() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_email_verification_pair",
            "(email_verified_at IS NULL AND email_verification_method IS NULL) OR "
            "(email_verified_at IS NOT NULL AND email_verification_method IS NOT NULL)",
        )

    for table_name in TENANT_VERIFICATION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_check_constraint(
                f"ck_{table_name}_verification_status",
                "verification_status IN ('pending','under_review','verified','rejected')",
            )
            batch_op.create_check_constraint(
                f"ck_{table_name}_verification_evidence",
                "(verification_status = 'verified' AND verified_at IS NOT NULL AND "
                "verification_method IS NOT NULL) OR "
                "(verification_status IN ('pending','under_review','rejected') AND "
                "verified_at IS NULL AND "
                "verification_method IS NULL)",
            )
        op.create_index(
            op.f(f"ix_{table_name}_verification_status"),
            table_name,
            ["verification_status"],
            unique=False,
        )


def upgrade() -> None:
    _add_verification_columns()
    _set_postgres_rls(enabled=False)
    _backfill_temporary_policy()
    _set_postgres_rls(enabled=True)
    _add_verification_constraints()


def downgrade() -> None:
    for table_name in reversed(TENANT_VERIFICATION_TABLES):
        op.drop_index(op.f(f"ix_{table_name}_verification_status"), table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(
                f"ck_{table_name}_verification_evidence",
                type_="check",
            )
            batch_op.drop_constraint(
                f"ck_{table_name}_verification_status",
                type_="check",
            )
            batch_op.drop_column("verification_method")
            batch_op.drop_column("verified_at")
            batch_op.drop_column("verification_status")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_email_verification_pair", type_="check")
        batch_op.drop_column("email_verification_method")

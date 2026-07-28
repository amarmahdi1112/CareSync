"""Add durable idempotency keys for atomic offer publication.

Revision ID: 0023_atomic_offer_send
Revises: 0022_attendance_idempotency
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_atomic_offer_send"
down_revision = "0022_attendance_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("ats_offers")}
    if "client_operation_id" not in columns:
        op.add_column(
            "ats_offers",
            sa.Column("client_operation_id", sa.Uuid(), nullable=True),
        )

    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("ats_offers")}
    unique_constraints = {item["name"] for item in inspector.get_unique_constraints("ats_offers")}
    if "ix_ats_offers_client_operation_id" not in indexes:
        op.create_index(
            "ix_ats_offers_client_operation_id",
            "ats_offers",
            ["client_operation_id"],
        )
    if (
        "uq_ats_offers_client_operation" not in indexes
        and "uq_ats_offers_client_operation" not in unique_constraints
    ):
        op.create_index(
            "uq_ats_offers_client_operation",
            "ats_offers",
            ["organization_id", "client_operation_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("ats_offers")}
    unique_constraints = {item["name"] for item in inspector.get_unique_constraints("ats_offers")}
    with op.batch_alter_table("ats_offers") as batch:
        if "uq_ats_offers_client_operation" in indexes:
            batch.drop_index("uq_ats_offers_client_operation")
        elif "uq_ats_offers_client_operation" in unique_constraints:
            batch.drop_constraint("uq_ats_offers_client_operation", type_="unique")
        if "ix_ats_offers_client_operation_id" in indexes:
            batch.drop_index("ix_ats_offers_client_operation_id")
        batch.drop_column("client_operation_id")

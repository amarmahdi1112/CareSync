"""Add durable client idempotency keys to attendance mutations.

Revision ID: 0022_attendance_idempotency
Revises: 0021_user_notifications
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_attendance_idempotency"
down_revision = "0021_user_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_events",
        sa.Column("client_operation_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_attendance_events_client_operation_id",
        "attendance_events",
        ["client_operation_id"],
    )
    op.create_index(
        "uq_attendance_events_client_operation",
        "attendance_events",
        ["organization_id", "client_operation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_attendance_events_client_operation",
        table_name="attendance_events",
    )
    op.drop_index("ix_attendance_events_client_operation_id", table_name="attendance_events")
    op.drop_column("attendance_events", "client_operation_id")

"""Allow shift events without device location.

Revision ID: 0018_location_free_shift_clock
Revises: 0017_credential_vault
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_location_free_shift_clock"
down_revision = "0017_credential_vault"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("latitude", sa.Numeric(9, 6)),
    ("longitude", sa.Numeric(9, 6)),
    ("accuracy_meters", sa.Numeric(8, 2)),
    ("distance_meters", sa.Numeric(10, 2)),
    ("radius_meters", sa.Integer()),
)


def upgrade() -> None:
    with op.batch_alter_table("staff_shift_events") as batch:
        for name, column_type in _COLUMNS:
            batch.alter_column(name, existing_type=column_type, nullable=True)


def downgrade() -> None:
    op.execute(
        "UPDATE staff_shift_events SET latitude = COALESCE(latitude, 0), "
        "longitude = COALESCE(longitude, 0), accuracy_meters = COALESCE(accuracy_meters, 0), "
        "distance_meters = COALESCE(distance_meters, 0), radius_meters = COALESCE(radius_meters, 0)"
    )
    with op.batch_alter_table("staff_shift_events") as batch:
        for name, column_type in _COLUMNS:
            batch.alter_column(name, existing_type=column_type, nullable=False)

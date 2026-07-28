"""Add configured room age ranges for approval-first placement.

Revision ID: 0008_dob_room_placement
Revises: 0007_medications_incidents
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_dob_room_placement"
down_revision = "0007_medications_incidents"
branch_labels = None
depends_on = None


def _set_room_rls(*, enabled: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    action = "ENABLE" if enabled else "DISABLE"
    op.execute(f'ALTER TABLE "rooms" {action} ROW LEVEL SECURITY')
    if enabled:
        op.execute('ALTER TABLE "rooms" FORCE ROW LEVEL SECURITY')


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("minimum_age_months", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("maximum_age_months", sa.Integer(), nullable=True))

    _set_room_rls(enabled=False)
    try:
        # These values seed the current known room categories. They are editable
        # configuration, not a hidden classifier, and intentionally overlap for
        # mixed/all-room spaces so a manager must choose when several fit.
        op.execute(
            sa.text(
                """
                UPDATE rooms
                SET minimum_age_months = CASE
                      WHEN lower(trim(coalesce(age_group, ''))) = 'infant' THEN 0
                      WHEN lower(trim(coalesce(age_group, ''))) = 'toddler' THEN 19
                      WHEN lower(trim(coalesce(age_group, ''))) IN ('kinder', 'preschool') THEN 36
                      WHEN lower(trim(coalesce(age_group, '')))
                           IN ('school-age', 'school age') THEN 60
                      WHEN lower(trim(coalesce(age_group, '')))
                           IN ('all-rooms', 'all rooms', 'mixed') THEN 0
                    END,
                    maximum_age_months = CASE
                      WHEN lower(trim(coalesce(age_group, ''))) = 'infant' THEN 18
                      WHEN lower(trim(coalesce(age_group, ''))) = 'toddler' THEN 35
                      WHEN lower(trim(coalesce(age_group, ''))) IN ('kinder', 'preschool') THEN 71
                      WHEN lower(trim(coalesce(age_group, '')))
                           IN ('school-age', 'school age') THEN 143
                      WHEN lower(trim(coalesce(age_group, '')))
                           IN ('all-rooms', 'all rooms', 'mixed') THEN 143
                    END
                """
            )
        )
    finally:
        _set_room_rls(enabled=True)

    with op.batch_alter_table("rooms") as batch:
        batch.create_check_constraint(
            "ck_rooms_age_range_pair",
            "(minimum_age_months IS NULL AND maximum_age_months IS NULL) OR "
            "(minimum_age_months IS NOT NULL AND maximum_age_months IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_rooms_minimum_age",
            "minimum_age_months IS NULL OR minimum_age_months >= 0",
        )
        batch.create_check_constraint(
            "ck_rooms_age_range_order",
            "maximum_age_months IS NULL OR maximum_age_months >= minimum_age_months",
        )


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.drop_constraint("ck_rooms_age_range_order", type_="check")
        batch.drop_constraint("ck_rooms_minimum_age", type_="check")
        batch.drop_constraint("ck_rooms_age_range_pair", type_="check")
        batch.drop_column("maximum_age_months")
        batch.drop_column("minimum_age_months")

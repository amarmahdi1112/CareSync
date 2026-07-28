"""Add explicit interview timezone and offer expiry.

Revision ID: 0020_hiring_contracts
Revises: 0019_application_snapshot
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_hiring_contracts"
down_revision = "0019_application_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offer_columns = {item["name"] for item in sa.inspect(bind).get_columns("ats_offers")}
    if "expires_at" not in offer_columns:
        op.add_column("ats_offers", sa.Column("expires_at", sa.DateTime(timezone=True)))
    interview_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("ats_interviews")
    }
    if "timezone" not in interview_columns:
        op.add_column(
            "ats_interviews",
            sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        )
    op.execute(
        """
        UPDATE ats_interviews
        SET timezone = COALESCE(
          (SELECT organizations.timezone FROM organizations
           WHERE organizations.id = ats_interviews.organization_id),
          'UTC'
        )
        WHERE timezone IS NULL OR trim(timezone) = ''
        """
    )


def downgrade() -> None:
    op.drop_column("ats_interviews", "timezone")
    op.drop_column("ats_offers", "expires_at")

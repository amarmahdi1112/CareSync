"""Add candidate-private personal details and normalized photo.

Revision ID: 0015_candidate_personal
Revises: 0014_marketplace_candidate_types
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import MarketplaceProfilePhoto

revision = "0015_candidate_personal"
down_revision = "0014_marketplace_candidate_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns("marketplace_profiles")}
    missing = []
    if "date_of_birth" not in existing:
        missing.append(sa.Column("date_of_birth", sa.Date(), nullable=True))
    if "phone" not in existing:
        missing.append(sa.Column("phone", sa.String(30), nullable=True))
    if missing:
        with op.batch_alter_table("marketplace_profiles") as batch:
            for column in missing:
                batch.add_column(column)
    MarketplaceProfilePhoto.__table__.create(bind, checkfirst=True)
    if bind.dialect.name != "postgresql":
        return
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    op.execute('ALTER TABLE "marketplace_profile_photos" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "marketplace_profile_photos" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "marketplace_profile_photos_owner" ON "marketplace_profile_photos" '
        f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE marketplace_profile_photos
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    MarketplaceProfilePhoto.__table__.drop(bind, checkfirst=True)
    existing = {item["name"] for item in sa.inspect(bind).get_columns("marketplace_profiles")}
    with op.batch_alter_table("marketplace_profiles") as batch:
        if "phone" in existing:
            batch.drop_column("phone")
        if "date_of_birth" in existing:
            batch.drop_column("date_of_birth")

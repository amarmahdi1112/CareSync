"""Persist immutable listing identity on candidate application links.

Revision ID: 0019_application_snapshot
Revises: 0018_location_free_shift_clock
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_application_snapshot"
down_revision = "0018_location_free_shift_clock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("marketplace_application_links")
    }
    with op.batch_alter_table("marketplace_application_links") as batch:
        if "listing_title" not in existing:
            batch.add_column(sa.Column("listing_title", sa.String(180), nullable=True))
        if "organization_name" not in existing:
            batch.add_column(sa.Column("organization_name", sa.String(255), nullable=True))
        if "listing_location" not in existing:
            batch.add_column(sa.Column("listing_location", sa.String(255), nullable=True))
        if "employment_type" not in existing:
            batch.add_column(sa.Column("employment_type", sa.String(50), nullable=True))
        if "published_at" not in existing:
            batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE marketplace_application_links
        SET listing_title = (
              SELECT ats_jobs.title FROM ats_jobs
              WHERE ats_jobs.id = marketplace_application_links.listing_id
                AND ats_jobs.organization_id = marketplace_application_links.organization_id
            ),
            organization_name = (
              SELECT organizations.name FROM organizations
              WHERE organizations.id = marketplace_application_links.organization_id
            ),
            listing_location = (
              SELECT ats_jobs.location FROM ats_jobs
              WHERE ats_jobs.id = marketplace_application_links.listing_id
                AND ats_jobs.organization_id = marketplace_application_links.organization_id
            ),
            employment_type = (
              SELECT ats_jobs.employment_type FROM ats_jobs
              WHERE ats_jobs.id = marketplace_application_links.listing_id
                AND ats_jobs.organization_id = marketplace_application_links.organization_id
            ),
            published_at = (
              SELECT ats_jobs.published_at FROM ats_jobs
              WHERE ats_jobs.id = marketplace_application_links.listing_id
                AND ats_jobs.organization_id = marketplace_application_links.organization_id
            )
        """
    )
    with op.batch_alter_table("marketplace_application_links") as batch:
        batch.alter_column("listing_title", existing_type=sa.String(180), nullable=False)
        batch.alter_column("organization_name", existing_type=sa.String(255), nullable=False)
        batch.alter_column("employment_type", existing_type=sa.String(50), nullable=False)
        batch.alter_column(
            "published_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("marketplace_application_links") as batch:
        batch.drop_column("published_at")
        batch.drop_column("employment_type")
        batch.drop_column("listing_location")
        batch.drop_column("organization_name")
        batch.drop_column("listing_title")

"""Add global candidate marketplace and consent-gated application links.

Revision ID: 0012_candidate_marketplace
Revises: 0011_realtime_outbox
Create Date: 2026-07-15
"""

from __future__ import annotations

from contextlib import nullcontext

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    AtsInterview,
    MarketplaceApplicationLink,
    MarketplaceInterest,
    MarketplaceJob,
    MarketplaceProfile,
)

revision = "0012_candidate_marketplace"
down_revision = "0011_realtime_outbox"
branch_labels = None
depends_on = None

TABLES = (
    MarketplaceProfile,
    MarketplaceJob,
    MarketplaceApplicationLink,
    MarketplaceInterest,
    AtsInterview,
)


class _NoopBatch:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _postgres_job_projection() -> None:
    op.execute(
        """
        CREATE FUNCTION sync_marketplace_job() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.status = 'open' THEN
            INSERT INTO marketplace_jobs
              (listing_id, organization_id, title, description, employment_type,
               location, openings, organization_name, published_at)
            SELECT NEW.id, NEW.organization_id, NEW.title, NEW.description,
                   NEW.employment_type, NEW.location, NEW.openings, organizations.name,
                   NEW.published_at
            FROM organizations WHERE organizations.id = NEW.organization_id
            ON CONFLICT (listing_id) DO UPDATE SET
              title=EXCLUDED.title, description=EXCLUDED.description,
              employment_type=EXCLUDED.employment_type, location=EXCLUDED.location,
              openings=EXCLUDED.openings, organization_name=EXCLUDED.organization_name,
              published_at=EXCLUDED.published_at;
          ELSE
            DELETE FROM marketplace_jobs WHERE listing_id = NEW.id;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_jobs_marketplace AFTER INSERT OR UPDATE ON ats_jobs "
        "FOR EACH ROW EXECUTE FUNCTION sync_marketplace_job()"
    )


def _sqlite_job_projection() -> None:
    op.execute(
        """
        CREATE TRIGGER ats_jobs_marketplace_open AFTER INSERT ON ats_jobs
        WHEN NEW.status = 'open'
        BEGIN
          INSERT OR REPLACE INTO marketplace_jobs
            (listing_id, organization_id, title, description, employment_type,
             location, openings, organization_name, published_at)
          SELECT NEW.id, NEW.organization_id, NEW.title, NEW.description,
                 NEW.employment_type, NEW.location, NEW.openings, organizations.name,
                 NEW.published_at FROM organizations WHERE id = NEW.organization_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_jobs_marketplace_update AFTER UPDATE ON ats_jobs
        BEGIN
          DELETE FROM marketplace_jobs WHERE listing_id = NEW.id;
          INSERT OR REPLACE INTO marketplace_jobs
            (listing_id, organization_id, title, description, employment_type,
             location, openings, organization_name, published_at)
          SELECT NEW.id, NEW.organization_id, NEW.title, NEW.description,
                 NEW.employment_type, NEW.location, NEW.openings, organizations.name,
                 NEW.published_at FROM organizations
          WHERE id = NEW.organization_id AND NEW.status = 'open';
        END
        """
    )


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("ats_applications")}
    batch_context = (
        nullcontext(_NoopBatch())
        if "source" in columns
        else op.batch_alter_table("ats_applications")
    )
    with batch_context as batch:
        batch.add_column(
            sa.Column("source", sa.String(30), server_default="private_invitation", nullable=False)
        )
        batch.add_column(
            sa.Column(
                "candidate_consent_status",
                sa.String(20),
                server_default="accepted",
                nullable=False,
            )
        )
        batch.create_check_constraint(
            "ck_ats_applications_source",
            "source IN ('private_invitation','marketplace_application','employer_interest')",
        )
        batch.create_check_constraint(
            "ck_ats_applications_consent",
            "candidate_consent_status IN ('requested','accepted','declined')",
        )
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        org = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
        user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        for name in ("ats_interviews",):
            op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY "{name}_tenant" ON "{name}" '
                f"USING (organization_id = {org}) WITH CHECK (organization_id = {org})"
            )
        op.execute('ALTER TABLE "marketplace_profiles" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "marketplace_profiles" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY "marketplace_profiles_select" ON "marketplace_profiles" '
            f"FOR SELECT USING (user_id = {user} OR discoverable)"
        )
        op.execute(
            'CREATE POLICY "marketplace_profiles_owner" ON "marketplace_profiles" '
            f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
        )
        op.execute('ALTER TABLE "marketplace_application_links" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "marketplace_application_links" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY "marketplace_links_owner" ON "marketplace_application_links" '
            f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
        )
        op.execute('ALTER TABLE "marketplace_interests" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "marketplace_interests" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY "marketplace_interests_access" ON "marketplace_interests" '
            f"FOR ALL USING (organization_id = {org} OR profile_user_id = {user}) "
            f"WITH CHECK (organization_id = {org} OR profile_user_id = {user})"
        )
        op.execute(
            """
            DO $grant$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
                GRANT SELECT, INSERT, UPDATE ON TABLE marketplace_profiles,
                  marketplace_application_links, marketplace_interests, ats_interviews
                  TO caresync_basic_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE marketplace_jobs
                  TO caresync_basic_app;
              END IF;
            END $grant$
            """
        )
        _postgres_job_projection()
    else:
        _sqlite_job_projection()
    op.execute(
        """
        INSERT INTO marketplace_jobs
          (listing_id, organization_id, title, description, employment_type,
           location, openings, organization_name, published_at)
        SELECT ats_jobs.id, ats_jobs.organization_id, ats_jobs.title,
               ats_jobs.description, ats_jobs.employment_type, ats_jobs.location,
               ats_jobs.openings, organizations.name, ats_jobs.published_at
        FROM ats_jobs JOIN organizations ON organizations.id = ats_jobs.organization_id
        WHERE ats_jobs.status = 'open'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS ats_jobs_marketplace ON ats_jobs")
        op.execute("DROP FUNCTION IF EXISTS sync_marketplace_job()")
    else:
        op.execute("DROP TRIGGER IF EXISTS ats_jobs_marketplace_update")
        op.execute("DROP TRIGGER IF EXISTS ats_jobs_marketplace_open")
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)
    with op.batch_alter_table("ats_applications") as batch:
        batch.drop_constraint("ck_ats_applications_consent", type_="check")
        batch.drop_constraint("ck_ats_applications_source", type_="check")
        batch.drop_column("candidate_consent_status")
        batch.drop_column("source")

"""Add permanent versioned candidate credential vault.

Revision ID: 0017_credential_vault
Revises: 0016_candidate_hiring_realtime
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
from app.basic.models import MarketplaceCredentialDocument, MarketplaceCredentialNotification

revision = "0017_credential_vault"
down_revision = "0016_candidate_hiring_realtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    MarketplaceCredentialDocument.__table__.create(bind, checkfirst=True)
    MarketplaceCredentialNotification.__table__.create(bind, checkfirst=True)
    if bind.dialect.name != "postgresql":
        return
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for table in ("marketplace_credential_documents", "marketplace_credential_notifications"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "marketplace_credentials_owner" ON "marketplace_credential_documents" '
        f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "marketplace_credential_notifications_org" '
        'ON "marketplace_credential_notifications" FOR ALL '
        f"USING (organization_id = {organization}) WITH CHECK (organization_id = {organization})"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE marketplace_credential_documents,
              marketplace_credential_notifications TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_marketplace_credentials_current",
        table_name="marketplace_credential_documents",
    )
    MarketplaceCredentialNotification.__table__.drop(op.get_bind(), checkfirst=True)
    MarketplaceCredentialDocument.__table__.drop(op.get_bind(), checkfirst=True)

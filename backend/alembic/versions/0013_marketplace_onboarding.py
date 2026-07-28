"""Add resumable, candidate-owned marketplace onboarding.

Revision ID: 0013_marketplace_onboarding
Revises: 0012_candidate_marketplace
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import MarketplaceDocumentAnalysis, MarketplaceOnboardingState

revision = "0013_marketplace_onboarding"
down_revision = "0012_candidate_marketplace"
branch_labels = None
depends_on = None

EVIDENCE_COLUMNS = (
    ("certification_provenance", sa.String(30)),
    ("certification_candidate_confirmed_at", sa.DateTime(timezone=True)),
    ("work_history_provenance", sa.String(30)),
    ("work_history_candidate_confirmed_at", sa.DateTime(timezone=True)),
)


def _add_missing_evidence(table_name: str) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
    missing = [(name, type_) for name, type_ in EVIDENCE_COLUMNS if name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name) as batch:
        for name, type_ in missing:
            batch.add_column(sa.Column(name, type_, nullable=True))


def upgrade() -> None:
    _add_missing_evidence("marketplace_profiles")
    _add_missing_evidence("ats_candidates")
    bind = op.get_bind()
    MarketplaceOnboardingState.__table__.create(bind, checkfirst=True)
    MarketplaceDocumentAnalysis.__table__.create(bind, checkfirst=True)
    if bind.dialect.name != "postgresql":
        return
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    for table_name in ("marketplace_onboarding_states", "marketplace_document_analyses"):
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table_name}_owner" ON "{table_name}" '
            f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
        )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE marketplace_onboarding_states,
              marketplace_document_analyses TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    MarketplaceDocumentAnalysis.__table__.drop(bind, checkfirst=True)
    MarketplaceOnboardingState.__table__.drop(bind, checkfirst=True)
    for table_name in ("ats_candidates", "marketplace_profiles"):
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        removable = [name for name, _ in EVIDENCE_COLUMNS if name in existing]
        if not removable:
            continue
        with op.batch_alter_table(table_name) as batch:
            for name in removable:
                batch.drop_column(name)

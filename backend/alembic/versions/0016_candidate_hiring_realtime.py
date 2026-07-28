"""Add candidate hiring realtime tickets and interview negotiation.

Revision ID: 0016_candidate_hiring_realtime
Revises: 0015_candidate_personal
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import MarketplaceRealtimeTicket

revision = "0016_candidate_hiring_realtime"
down_revision = "0015_candidate_personal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    MarketplaceRealtimeTicket.__table__.create(bind, checkfirst=True)
    existing = {item["name"] for item in sa.inspect(bind).get_columns("ats_interviews")}
    if "candidate_proposed_at" not in existing:
        op.add_column(
            "ats_interviews",
            sa.Column("candidate_proposed_at", sa.DateTime(timezone=True)),
        )
    if "candidate_proposal_note" not in existing:
        op.add_column("ats_interviews", sa.Column("candidate_proposal_note", sa.Text()))
    if "candidate_proposed_at" not in existing or "candidate_proposal_note" not in existing:
        with op.batch_alter_table("ats_interviews") as batch:
            batch.drop_constraint("ck_ats_interviews_status", type_="check")
            batch.create_check_constraint(
                "ck_ats_interviews_status",
                "status IN ('requested','confirmed','declined','cancelled',"
                "'candidate_proposed','proposal_declined')",
            )
    if bind.dialect.name != "postgresql":
        return
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    op.execute('ALTER TABLE "marketplace_realtime_tickets" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "marketplace_realtime_tickets" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "marketplace_realtime_tickets_owner" ON "marketplace_realtime_tickets" '
        f"FOR ALL USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE marketplace_realtime_tickets
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("ats_interviews") as batch:
        batch.drop_constraint("ck_ats_interviews_status", type_="check")
        batch.create_check_constraint(
            "ck_ats_interviews_status",
            "status IN ('requested','confirmed','declined','cancelled')",
        )
    op.drop_column("ats_interviews", "candidate_proposal_note")
    op.drop_column("ats_interviews", "candidate_proposed_at")
    MarketplaceRealtimeTicket.__table__.drop(op.get_bind(), checkfirst=True)

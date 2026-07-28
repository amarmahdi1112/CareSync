"""Add tenant-scoped invite-only applicant tracking.

Revision ID: 0009_invite_only_ats
Revises: 0008_dob_room_placement
Create Date: 2026-07-15
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    AtsApplication,
    AtsCandidate,
    AtsCandidateInvitation,
    AtsEvent,
    AtsJob,
    AtsOffer,
)

revision = "0009_invite_only_ats"
down_revision = "0008_dob_room_placement"
branch_labels = None
depends_on = None

TABLES = (AtsJob, AtsCandidate, AtsApplication, AtsCandidateInvitation, AtsOffer, AtsEvent)
PERMISSIONS = {
    "owner": ("ats:read", "ats:manage", "ats:hire"),
    "administrator": ("ats:read", "ats:manage", "ats:hire"),
}


def _roles_rls(enabled: bool) -> None:
    if op.get_bind().dialect.name == "postgresql":
        action = "ENABLE" if enabled else "DISABLE"
        op.execute(f'ALTER TABLE "roles" {action} ROW LEVEL SECURITY')
        if enabled:
            op.execute('ALTER TABLE "roles" FORCE ROW LEVEL SECURITY')


def _update_permissions(add: bool) -> None:
    bind = op.get_bind()
    _roles_rls(False)
    try:
        roles = sa.table(
            "roles",
            sa.column("id", sa.Uuid()),
            sa.column("key", sa.String()),
            sa.column("permissions", sa.JSON()),
        )
        for row in bind.execute(
            sa.select(roles.c.id, roles.c.key, roles.c.permissions).where(
                roles.c.key.in_(tuple(PERMISSIONS))
            )
        ).mappings():
            value = row["permissions"]
            current = list(json.loads(value) if isinstance(value, str) else (value or []))
            additions = PERMISSIONS[row["key"]]
            updated = (
                list(dict.fromkeys([*current, *additions]))
                if add
                else [item for item in current if item not in additions]
            )
            bind.execute(roles.update().where(roles.c.id == row["id"]).values(permissions=updated))
    finally:
        _roles_rls(True)


def _create_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    org = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for model in TABLES:
        name = model.__tablename__
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{name}_tenant" ON "{name}" '
            f"USING (organization_id = {org}) WITH CHECK (organization_id = {org})"
        )
    # Candidate access remains application-filtered and claim-checked in the API;
    # the tenant setting always comes from the signed invitation token, never a header.
    op.execute("""
    DO $grant$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE ats_jobs, ats_candidates, ats_applications,
          ats_candidate_invitations, ats_offers TO caresync_basic_app;
        GRANT SELECT, INSERT ON TABLE ats_events TO caresync_basic_app;
        GRANT USAGE, SELECT ON SEQUENCE ats_events_sequence_id_seq TO caresync_basic_app;
      END IF;
    END $grant$
    """)


def upgrade() -> None:
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    _update_permissions(True)
    _create_rls()


def downgrade() -> None:
    _update_permissions(False)
    bind = op.get_bind()
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)

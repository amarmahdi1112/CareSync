"""Add safe staff provisioning, candidate credentials, and shift evidence.

Revision ID: 0010_staff_ops
Revises: 0009_invite_only_ats
Create Date: 2026-07-15
"""

from __future__ import annotations

import json
from contextlib import nullcontext

import sqlalchemy as sa

from alembic import op
from app.basic.models import AtsStaffProvisioning, StaffShiftEvent

revision = "0010_staff_ops"
down_revision = "0009_invite_only_ats"
branch_labels = None
depends_on = None

_legacy_metadata = sa.MetaData()
sa.Table(
    "organization_memberships",
    _legacy_metadata,
    sa.Column("organization_id", sa.Uuid()),
    sa.Column("id", sa.Uuid()),
)
sa.Table(
    "facilities",
    _legacy_metadata,
    sa.Column("organization_id", sa.Uuid()),
    sa.Column("id", sa.Uuid()),
)
_legacy_staff_shifts = sa.Table(
    "staff_shifts",
    _legacy_metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
    sa.Column("membership_id", sa.Uuid(), nullable=False, index=True),
    sa.Column("facility_id", sa.Uuid(), nullable=False, index=True),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("clocked_in_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("clocked_out_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "membership_id"],
        ["organization_memberships.organization_id", "organization_memberships.id"],
        ondelete="RESTRICT",
        name="fk_staff_shifts_membership",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id"],
        ["facilities.organization_id", "facilities.id"],
        ondelete="RESTRICT",
        name="fk_staff_shifts_facility",
    ),
    sa.UniqueConstraint("organization_id", "id", name="uq_staff_shifts_org_id"),
    sa.CheckConstraint("status IN ('open','closed')", name="ck_staff_shifts_status"),
    sa.CheckConstraint(
        "(status = 'open' AND clocked_out_at IS NULL) OR "
        "(status = 'closed' AND clocked_out_at IS NOT NULL)",
        name="ck_staff_shifts_terminal",
    ),
)
sa.Index(
    "uq_staff_shifts_open_membership",
    _legacy_staff_shifts.c.organization_id,
    _legacy_staff_shifts.c.membership_id,
    unique=True,
    postgresql_where=_legacy_staff_shifts.c.status == "open",
    sqlite_where=_legacy_staff_shifts.c.status == "open",
)


class _LegacyStaffShift:
    __tablename__ = "staff_shifts"
    __table__ = _legacy_staff_shifts


TABLES = (AtsStaffProvisioning, _LegacyStaffShift, StaffShiftEvent)


class _NoopBatch:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _role_permissions(add: bool) -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        op.execute('ALTER TABLE "roles" DISABLE ROW LEVEL SECURITY')
    try:
        roles = sa.table(
            "roles",
            sa.column("id", sa.Uuid()),
            sa.column("key", sa.String()),
            sa.column("permissions", sa.JSON()),
        )
        rows = bind.execute(
            sa.select(roles.c.id, roles.c.permissions).where(
                roles.c.key.in_(("owner", "administrator", "educator"))
            )
        ).mappings()
        for row in rows:
            value = row["permissions"]
            permissions = list(json.loads(value) if isinstance(value, str) else (value or []))
            if add and "shift:clock" not in permissions:
                permissions.append("shift:clock")
            if not add:
                permissions = [item for item in permissions if item != "shift:clock"]
            bind.execute(
                roles.update().where(roles.c.id == row["id"]).values(permissions=permissions)
            )
    finally:
        if postgres:
            op.execute('ALTER TABLE "roles" ENABLE ROW LEVEL SECURITY')
            op.execute('ALTER TABLE "roles" FORCE ROW LEVEL SECURITY')


def _rls_and_grants() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    setting = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for model in TABLES:
        name = model.__tablename__
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{name}_tenant" ON "{name}" '
            f"USING (organization_id = {setting}) WITH CHECK (organization_id = {setting})"
        )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE ats_staff_provisionings, staff_shifts
              TO caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE staff_shift_events TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def upgrade() -> None:
    with op.batch_alter_table("facilities") as batch:
        batch.add_column(sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
        batch.add_column(
            sa.Column(
                "shift_clock_radius_meters", sa.Integer(), server_default="150", nullable=False
            )
        )
        batch.create_check_constraint(
            "ck_facilities_shift_coordinates_pair",
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
        )
        batch.create_check_constraint(
            "ck_facilities_shift_radius", "shift_clock_radius_meters BETWEEN 25 AND 5000"
        )
    candidate_columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("ats_candidates")
    }
    candidate_batch = (
        nullcontext(_NoopBatch())
        if "onboarding_status" in candidate_columns
        else op.batch_alter_table("ats_candidates")
    )
    with candidate_batch as batch:
        batch.add_column(
            sa.Column(
                "onboarding_status", sa.String(30), server_default="not_started", nullable=False
            )
        )
        batch.add_column(sa.Column("certification_type", sa.String(120), nullable=True))
        batch.add_column(sa.Column("certification_number", sa.String(120), nullable=True))
        batch.add_column(sa.Column("certification_expiry_date", sa.Date(), nullable=True))
        batch.add_column(
            sa.Column(
                "certification_verification_status",
                sa.String(30),
                server_default="unverified",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("certification_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("certification_verified_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("certification_review_note", sa.Text(), nullable=True))
        batch.add_column(sa.Column("work_history", sa.JSON(), server_default="[]", nullable=False))
        batch.create_foreign_key(
            "fk_ats_candidates_certification_reviewer",
            "users",
            ["certification_verified_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_ats_candidates_onboarding_status",
            "onboarding_status IN ('not_started','in_progress','submitted','complete')",
        )
        batch.create_check_constraint(
            "ck_ats_candidates_certification_status",
            "certification_verification_status IN ('unverified','pending','verified','rejected')",
        )
        batch.create_check_constraint(
            "ck_ats_candidates_certification_evidence",
            "(certification_verification_status = 'verified' AND "
            "certification_verified_at IS NOT NULL AND "
            "certification_verified_by_user_id IS NOT NULL) OR "
            "certification_verification_status <> 'verified'",
        )
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    _role_permissions(True)
    _rls_and_grants()


def downgrade() -> None:
    _role_permissions(False)
    bind = op.get_bind()
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)
    with op.batch_alter_table("ats_candidates") as batch:
        batch.drop_constraint("ck_ats_candidates_certification_evidence", type_="check")
        batch.drop_constraint("ck_ats_candidates_certification_status", type_="check")
        batch.drop_constraint("ck_ats_candidates_onboarding_status", type_="check")
        for column in (
            "work_history",
            "certification_review_note",
            "certification_verified_by_user_id",
            "certification_verified_at",
            "certification_verification_status",
            "certification_expiry_date",
            "certification_number",
            "certification_type",
            "onboarding_status",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("facilities") as batch:
        batch.drop_constraint("ck_facilities_shift_radius", type_="check")
        batch.drop_constraint("ck_facilities_shift_coordinates_pair", type_="check")
        batch.drop_column("shift_clock_radius_meters")
        batch.drop_column("longitude")
        batch.drop_column("latitude")

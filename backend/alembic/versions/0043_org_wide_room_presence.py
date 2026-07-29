"""Allow organization-wide staff to select a physical room while clocked in.

Revision ID: 0043_org_wide_room_presence
Revises: 0042_billing_policy_recert
Create Date: 2026-07-28

The 0041 room-presence boundary correctly requires an active physical room
presence before child-state mutations, but its database insert guard originally
required every actor to have a ``membership_room_assignments`` row.  Owner and
administrator roles are organization-wide and intentionally cannot receive
those access-scope rows.  This additive recertification preserves every 0041
provenance, permission, shift, facility, room, tenant, and immutability check
while allowing those two fixed system roles to select any active room in the
active shift facility.
"""

from __future__ import annotations

import hashlib
import re

import sqlalchemy as sa

from alembic import op

revision = "0043_org_wide_room_presence"
down_revision = "0042_billing_policy_recert"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "caresync_basic_app"

_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*(?:\n|$)")

_POSTGRES_GUARD_SOURCE_0041 = r"""
DECLARE
  context_operation uuid := NULLIF(
    pg_catalog.current_setting(
      'app.current_room_presence_operation_id', true
    ), ''
  )::uuid;
  context_user uuid := NULLIF(
    pg_catalog.current_setting('app.current_user_id', true), ''
  )::uuid;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'room presence is immutable'
      USING ERRCODE='23514',
            CONSTRAINT='ck_room_presence_sessions_immutable';
  END IF;
  IF context_operation IS NULL OR context_user IS NULL THEN
    RAISE EXCEPTION 'room presence command context is required'
      USING ERRCODE='23514',
            CONSTRAINT='ck_room_presence_sessions_command_context';
  END IF;
  IF (
    TG_OP='INSERT'
    AND NOT EXISTS (
      SELECT 1
      FROM public.organization_memberships AS actor_membership
      JOIN public.roles AS actor_role
        ON actor_role.organization_id=actor_membership.organization_id
       AND actor_role.id=actor_membership.role_id
      WHERE actor_membership.organization_id=NEW.organization_id
        AND actor_membership.id=NEW.membership_id
        AND actor_membership.user_id=context_user
        AND actor_membership.status='active'
        AND actor_role.permissions::jsonb
            @> '["shift:clock","care_roster:read"]'::jsonb
    )
  ) OR (
    TG_OP='UPDATE'
    AND NEW.end_reason<>'access_revoked'
    AND NOT EXISTS (
      SELECT 1
      FROM public.organization_memberships AS actor_membership
      JOIN public.roles AS actor_role
        ON actor_role.organization_id=actor_membership.organization_id
       AND actor_role.id=actor_membership.role_id
      WHERE actor_membership.organization_id=NEW.organization_id
        AND actor_membership.id=NEW.membership_id
        AND actor_membership.user_id=context_user
        AND actor_membership.status='active'
        AND actor_role.permissions::jsonb
            @> '["shift:clock","care_roster:read"]'::jsonb
    )
  ) OR (
    TG_OP='UPDATE'
    AND NEW.end_reason='access_revoked'
    AND NOT EXISTS (
      SELECT 1
      FROM public.organization_memberships AS actor_membership
      JOIN public.roles AS actor_role
        ON actor_role.organization_id=actor_membership.organization_id
       AND actor_role.id=actor_membership.role_id
      WHERE actor_membership.organization_id=NEW.organization_id
        AND actor_membership.user_id=context_user
        AND actor_membership.status='active'
        AND actor_role.permissions::jsonb
            @> '["staff:manage_educators"]'::jsonb
    )
  ) THEN
    RAISE EXCEPTION 'room presence actor is not authorized'
      USING ERRCODE='23514',
            CONSTRAINT='ck_room_presence_sessions_actor';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      NEW.organization_id::text || ':' || NEW.membership_id::text, 41
    )
  );
  IF TG_OP='INSERT' THEN
    IF NEW.start_operation_id IS DISTINCT FROM context_operation
       OR NEW.started_by_user_id IS DISTINCT FROM context_user
       OR NEW.version<>1 OR NEW.ended_at IS NOT NULL THEN
      RAISE EXCEPTION 'invalid room presence start provenance'
        USING ERRCODE='23514',
              CONSTRAINT='ck_room_presence_sessions_start_provenance';
    END IF;
    IF NOT EXISTS (
      SELECT 1
      FROM public.staff_shifts AS shift
      JOIN public.organization_memberships AS membership
        ON membership.organization_id=shift.organization_id
       AND membership.id=shift.membership_id
      JOIN public.facilities AS facility
        ON facility.organization_id=shift.organization_id
       AND facility.id=shift.facility_id
      JOIN public.rooms AS room
        ON room.organization_id=shift.organization_id
       AND room.facility_id=shift.facility_id
       AND room.id=NEW.room_id
      JOIN public.membership_room_assignments AS assignment
        ON assignment.organization_id=shift.organization_id
       AND assignment.membership_id=shift.membership_id
       AND assignment.facility_id=shift.facility_id
       AND assignment.room_id=NEW.room_id
       AND assignment.is_active
      WHERE shift.organization_id=NEW.organization_id
        AND shift.id=NEW.staff_shift_id
        AND shift.membership_id=NEW.membership_id
        AND shift.facility_id=NEW.facility_id
        AND shift.status='open'
        AND shift.clocked_out_at IS NULL
        AND membership.status='active'
        AND facility.status='active'
        AND room.is_active
    ) THEN
      RAISE EXCEPTION 'room presence start is not eligible'
        USING ERRCODE='23514',
              CONSTRAINT='ck_room_presence_sessions_start_eligibility';
    END IF;
  ELSE
    IF OLD.ended_at IS NOT NULL
       OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.membership_id IS DISTINCT FROM OLD.membership_id
       OR NEW.staff_shift_id IS DISTINCT FROM OLD.staff_shift_id
       OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
       OR NEW.room_id IS DISTINCT FROM OLD.room_id
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.started_at IS DISTINCT FROM OLD.started_at
       OR NEW.start_operation_id IS DISTINCT FROM OLD.start_operation_id
       OR NEW.started_by_user_id IS DISTINCT FROM OLD.started_by_user_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.ended_at IS NULL
       OR NEW.end_operation_id IS DISTINCT FROM context_operation
       OR NEW.ended_by_user_id IS DISTINCT FROM context_user
       OR NEW.version<>2 THEN
      RAISE EXCEPTION 'invalid room presence terminal transition'
        USING ERRCODE='23514',
              CONSTRAINT='ck_room_presence_sessions_terminal_transition';
    END IF;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.staff_shifts AS shift
    JOIN public.organization_memberships AS membership
      ON membership.organization_id=shift.organization_id
     AND membership.id=shift.membership_id
    JOIN public.rooms AS room
      ON room.organization_id=shift.organization_id
     AND room.facility_id=shift.facility_id
     AND room.id=NEW.room_id
    WHERE shift.organization_id=NEW.organization_id
      AND shift.id=NEW.staff_shift_id
      AND shift.membership_id=NEW.membership_id
      AND shift.facility_id=NEW.facility_id
      AND (
        TG_OP='UPDATE'
        OR membership.status='active'
      )
  ) THEN
    RAISE EXCEPTION 'room presence scope does not match actual shift'
      USING ERRCODE='23514',
            CONSTRAINT='ck_room_presence_sessions_shift_scope';
  END IF;
  IF TG_OP='INSERT' AND EXISTS (
    SELECT 1
    FROM public.staff_room_presence_sessions AS other
    WHERE other.organization_id=NEW.organization_id
      AND other.membership_id=NEW.membership_id
      AND other.id<>NEW.id
      AND other.started_at<COALESCE(
            NEW.ended_at, 'infinity'::timestamptz
          )
      AND COALESCE(
            other.ended_at, 'infinity'::timestamptz
          )>NEW.started_at
  ) THEN
    RAISE EXCEPTION 'overlapping room presence is forbidden'
      USING ERRCODE='23P01',
            CONSTRAINT='ck_room_presence_sessions_no_overlap';
  END IF;
  RETURN NEW;
END
"""

_POSTGRES_ASSIGNMENT_ELIGIBILITY_0041 = r"""
      JOIN public.membership_room_assignments AS assignment
        ON assignment.organization_id=shift.organization_id
       AND assignment.membership_id=shift.membership_id
       AND assignment.facility_id=shift.facility_id
       AND assignment.room_id=NEW.room_id
       AND assignment.is_active
      WHERE shift.organization_id=NEW.organization_id
"""

_POSTGRES_ORGANIZATION_WIDE_ELIGIBILITY_0043 = r"""
      JOIN public.roles AS membership_role
        ON membership_role.organization_id=membership.organization_id
       AND membership_role.id=membership.role_id
      WHERE shift.organization_id=NEW.organization_id
        AND (
          membership_role.key IN ('owner','administrator')
          OR EXISTS (
            SELECT 1
            FROM public.membership_room_assignments AS assignment
            WHERE assignment.organization_id=shift.organization_id
              AND assignment.membership_id=shift.membership_id
              AND assignment.facility_id=shift.facility_id
              AND assignment.room_id=NEW.room_id
              AND assignment.is_active
          )
        )
"""

if _POSTGRES_GUARD_SOURCE_0041.count(_POSTGRES_ASSIGNMENT_ELIGIBILITY_0041) != 1:
    raise RuntimeError("0043 PostgreSQL guard derivation is not exact")

_POSTGRES_GUARD_SOURCE_0043 = _POSTGRES_GUARD_SOURCE_0041.replace(
    _POSTGRES_ASSIGNMENT_ELIGIBILITY_0041,
    _POSTGRES_ORGANIZATION_WIDE_ELIGIBILITY_0043,
)

_SQLITE_INSERT_GUARD_0041 = r"""
CREATE TRIGGER staff_room_presence_sessions_insert_guard
BEFORE INSERT ON staff_room_presence_sessions
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
    FROM staff_shifts AS shift
    JOIN organization_memberships AS membership
      ON membership.organization_id=shift.organization_id
     AND membership.id=shift.membership_id
    JOIN rooms AS room
      ON room.organization_id=shift.organization_id
     AND room.facility_id=shift.facility_id
     AND room.id=NEW.room_id
    JOIN facilities AS facility
      ON facility.organization_id=shift.organization_id
     AND facility.id=shift.facility_id
    JOIN membership_room_assignments AS assignment
      ON assignment.organization_id=shift.organization_id
     AND assignment.membership_id=shift.membership_id
     AND assignment.facility_id=shift.facility_id
     AND assignment.room_id=NEW.room_id
     AND assignment.is_active
    WHERE shift.organization_id=NEW.organization_id
      AND shift.id=NEW.staff_shift_id
      AND shift.membership_id=NEW.membership_id
      AND shift.facility_id=NEW.facility_id
      AND shift.status='open'
      AND membership.status='active'
      AND room.is_active
      AND facility.status='active'
  ) THEN RAISE(ABORT,'invalid 0041 room presence scope') END;
END
"""

_SQLITE_INSERT_GUARD_0043 = r"""
CREATE TRIGGER staff_room_presence_sessions_insert_guard
BEFORE INSERT ON staff_room_presence_sessions
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
    FROM staff_shifts AS shift
    JOIN organization_memberships AS membership
      ON membership.organization_id=shift.organization_id
     AND membership.id=shift.membership_id
    JOIN roles AS membership_role
      ON membership_role.organization_id=membership.organization_id
     AND membership_role.id=membership.role_id
    JOIN rooms AS room
      ON room.organization_id=shift.organization_id
     AND room.facility_id=shift.facility_id
     AND room.id=NEW.room_id
    JOIN facilities AS facility
      ON facility.organization_id=shift.organization_id
     AND facility.id=shift.facility_id
    WHERE shift.organization_id=NEW.organization_id
      AND shift.id=NEW.staff_shift_id
      AND shift.membership_id=NEW.membership_id
      AND shift.facility_id=NEW.facility_id
      AND shift.status='open'
      AND membership.status='active'
      AND room.is_active
      AND facility.status='active'
      AND (
        membership_role.key IN ('owner','administrator')
        OR EXISTS (
          SELECT 1
          FROM membership_room_assignments AS assignment
          WHERE assignment.organization_id=shift.organization_id
            AND assignment.membership_id=shift.membership_id
            AND assignment.facility_id=shift.facility_id
            AND assignment.room_id=NEW.room_id
            AND assignment.is_active
        )
      )
  ) THEN RAISE(ABORT,'invalid 0041 room presence scope') END;
END
"""


def _compact_sql(definition: str) -> str:
    without_blocks = _SQL_BLOCK_COMMENT.sub(" ", definition)
    without_comments = _SQL_LINE_COMMENT.sub(" ", without_blocks)
    return "".join(without_comments.lower().split()).replace('"', "")


def _source_sha256(definition: str) -> str:
    return hashlib.sha256(_compact_sql(definition).encode("utf-8")).hexdigest()


def _postgres_guard_source(bind: sa.engine.Connection) -> str | None:
    return bind.scalar(
        sa.text(
            "SELECT procedure.prosrc "
            "FROM pg_catalog.pg_proc AS procedure "
            "JOIN pg_catalog.pg_namespace AS namespace "
            "ON namespace.oid=procedure.pronamespace "
            "WHERE namespace.nspname='public' "
            "AND procedure.proname='caresync_0041_presence_row_guard' "
            "AND pg_catalog.pg_get_function_identity_arguments(procedure.oid)=''"
        )
    )


def _replace_postgres_guard(
    bind: sa.engine.Connection,
    *,
    expected_source: str,
    replacement_source: str,
) -> None:
    observed = _postgres_guard_source(bind)
    if observed is None or _source_sha256(observed) != _source_sha256(expected_source):
        raise RuntimeError(
            "0043 room-presence recertification requires the exact expected predecessor guard"
        )
    trigger_matches = bind.scalar(
        sa.text(
            "SELECT count(*) FROM pg_catalog.pg_trigger AS trigger "
            "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
            "WHERE trigger.tgrelid="
            "'public.staff_room_presence_sessions'::pg_catalog.regclass "
            "AND trigger.tgname='staff_room_presence_sessions_row_guard' "
            "AND NOT trigger.tgisinternal "
            "AND procedure.oid="
            "'public.caresync_0041_presence_row_guard()'::pg_catalog.regprocedure"
        )
    )
    if trigger_matches != 1:
        raise RuntimeError(
            "0043 room-presence recertification requires the exact 0041 trigger binding"
        )
    op.execute(
        "CREATE OR REPLACE FUNCTION public.caresync_0041_presence_row_guard() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER "
        "SET search_path=pg_catalog,public AS $guard$"
        f"{replacement_source}"
        "$guard$"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.caresync_0041_presence_row_guard() FROM PUBLIC"
    )
    op.execute(
        "DO $revoke_runtime$ BEGIN "
        f"IF pg_catalog.to_regrole('{RUNTIME_ROLE}') IS NOT NULL THEN "
        "EXECUTE 'REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.caresync_0041_presence_row_guard() "
        f"FROM {RUNTIME_ROLE}'; "
        "END IF; END $revoke_runtime$"
    )
    replaced = _postgres_guard_source(bind)
    if replaced is None or _source_sha256(replaced) != _source_sha256(replacement_source):
        raise RuntimeError(
            "0043 room-presence guard replacement did not produce the certified source"
        )


def _replace_sqlite_guard(
    bind: sa.engine.Connection,
    *,
    expected_definition: str,
    replacement_definition: str,
) -> None:
    observed = bind.scalar(
        sa.text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='staff_room_presence_sessions_insert_guard'"
        )
    )
    if observed is None or _compact_sql(observed) != _compact_sql(expected_definition):
        raise RuntimeError(
            "0043 portable room-presence recertification requires the exact "
            "expected predecessor trigger"
        )
    op.execute("DROP TRIGGER staff_room_presence_sessions_insert_guard")
    op.execute(replacement_definition)
    replaced = bind.scalar(
        sa.text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='staff_room_presence_sessions_insert_guard'"
        )
    )
    if replaced is None or _compact_sql(replaced) != _compact_sql(replacement_definition):
        raise RuntimeError("0043 portable room-presence trigger replacement was not exact")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _replace_postgres_guard(
            bind,
            expected_source=_POSTGRES_GUARD_SOURCE_0041,
            replacement_source=_POSTGRES_GUARD_SOURCE_0043,
        )
    else:
        _replace_sqlite_guard(
            bind,
            expected_definition=_SQLITE_INSERT_GUARD_0041,
            replacement_definition=_SQLITE_INSERT_GUARD_0043,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _replace_postgres_guard(
            bind,
            expected_source=_POSTGRES_GUARD_SOURCE_0043,
            replacement_source=_POSTGRES_GUARD_SOURCE_0041,
        )
    else:
        _replace_sqlite_guard(
            bind,
            expected_definition=_SQLITE_INSERT_GUARD_0043,
            replacement_definition=_SQLITE_INSERT_GUARD_0041,
        )

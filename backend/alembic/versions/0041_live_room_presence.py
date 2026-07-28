"""Add live room presence and operational configured-target evidence.

Revision ID: 0041_live_room_presence
Revises: 0039_admissions_decision_spine
Create Date: 2026-07-23

This revision is additive and intentionally performs no historical backfill.
Existing attendance, shift, schedule, assignment, room and coverage rows are
left byte-for-byte under their retained schemas.
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "0041_live_room_presence"
down_revision = "0039_admissions_decision_spine"
branch_labels = None
depends_on = None

TABLES = (
    "staff_room_presence_sessions",
    "staff_room_presence_events",
    "room_operational_exception_heads",
    "room_operational_exception_events",
)
_DOWNGRADE_DEPENDENCY_TABLES = (
    "audit_events",
    "realtime_events",
    "user_notifications",
)

_metadata = sa.MetaData()


def _lowercase_sha256_check(column_name: str) -> str:
    """Return the exact portable lowercase-hex SHA-256 predicate."""

    remainder = column_name
    for character in "0123456789abcdef":
        remainder = f"replace({remainder},'{character}','')"
    return (
        f"length({column_name})=64 AND {column_name}=lower({column_name}) "
        f"AND length({remainder})=0"
    )


sa.Table(
    "organizations",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
)
sa.Table(
    "users",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
)
sa.Table(
    "organization_memberships",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_memberships_org_id_id"
    ),
)
sa.Table(
    "facilities",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint("organization_id", "id", name="uq_facilities_org_id_id"),
)
sa.Table(
    "rooms",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "facility_id",
        "id",
        name="uq_rooms_org_facility_id",
    ),
)
sa.Table(
    "staff_shifts",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_staff_shifts_org_id"
    ),
)

SESSIONS = sa.Table(
    "staff_room_presence_sessions",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("membership_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("staff_shift_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("room_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("source", sa.String(30), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("end_reason", sa.String(30)),
    sa.Column("start_operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("end_operation_id", sa.Uuid(as_uuid=True)),
    sa.Column(
        "started_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_started_by",
        ),
        nullable=False,
    ),
    sa.Column(
        "ended_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_sessions_ended_by",
        ),
    ),
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "membership_id"],
        ["organization_memberships.organization_id", "organization_memberships.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_sessions_membership",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "staff_shift_id"],
        ["staff_shifts.organization_id", "staff_shifts.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_sessions_shift",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id"],
        ["facilities.organization_id", "facilities.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_sessions_facility",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id", "room_id"],
        ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_sessions_room",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_room_presence_sessions_org_id"
    ),
    sa.CheckConstraint(
        "source IN ('scheduled_room','single_assignment','staff_selected')",
        name="ck_room_presence_sessions_source",
    ),
    sa.CheckConstraint(
        "end_reason IS NULL OR end_reason IN "
        "('moved','staff_ended','clocked_out','access_revoked')",
        name="ck_room_presence_sessions_end_reason",
    ),
    sa.CheckConstraint(
        "(ended_at IS NULL AND end_reason IS NULL AND end_operation_id IS NULL "
        "AND ended_by_user_id IS NULL) OR "
        "(ended_at IS NOT NULL AND end_reason IS NOT NULL "
        "AND end_operation_id IS NOT NULL AND ended_by_user_id IS NOT NULL)",
        name="ck_room_presence_sessions_terminal_bundle",
    ),
    sa.CheckConstraint(
        "ended_at IS NULL OR ended_at >= started_at",
        name="ck_room_presence_sessions_time_order",
    ),
    sa.CheckConstraint(
        "(ended_at IS NULL AND version = 1) OR "
        "(ended_at IS NOT NULL AND version = 2)",
        name="ck_room_presence_sessions_version",
    ),
)

PRESENCE_EVENTS = sa.Table(
    "staff_room_presence_events",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column(
        "actor_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_presence_events_actor",
        ),
        nullable=False,
    ),
    sa.Column("membership_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("staff_shift_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.String(40), nullable=False),
    sa.Column("from_session_id", sa.Uuid(as_uuid=True)),
    sa.Column("to_session_id", sa.Uuid(as_uuid=True)),
    sa.Column("request_sha256", sa.CHAR(64), nullable=False),
    sa.Column("intent", sa.JSON, nullable=False),
    sa.Column("result", sa.JSON, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "membership_id"],
        ["organization_memberships.organization_id", "organization_memberships.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_events_membership",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "staff_shift_id"],
        ["staff_shifts.organization_id", "staff_shifts.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_events_shift",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id"],
        ["facilities.organization_id", "facilities.id"],
        ondelete="RESTRICT",
        name="fk_room_presence_events_facility",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "from_session_id"],
        [
            "staff_room_presence_sessions.organization_id",
            "staff_room_presence_sessions.id",
        ],
        ondelete="RESTRICT",
        name="fk_room_presence_events_from_session",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "to_session_id"],
        [
            "staff_room_presence_sessions.organization_id",
            "staff_room_presence_sessions.id",
        ],
        ondelete="RESTRICT",
        name="fk_room_presence_events_to_session",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_room_presence_events_org_id"
    ),
    sa.UniqueConstraint(
        "organization_id",
        "operation_id",
        name="uq_room_presence_events_operation",
    ),
    sa.CheckConstraint(
        "event_type IN ('started','moved','ended','clock_started_presence',"
        "'clock_ended_presence','access_revoked_presence')",
        name="ck_room_presence_events_type",
    ),
    sa.CheckConstraint(
        "(event_type IN ('started','clock_started_presence') "
        "AND from_session_id IS NULL AND to_session_id IS NOT NULL) OR "
        "(event_type = 'moved' AND from_session_id IS NOT NULL "
        "AND to_session_id IS NOT NULL AND from_session_id <> to_session_id) OR "
        "(event_type IN ('ended','clock_ended_presence','access_revoked_presence') "
        "AND from_session_id IS NOT NULL AND to_session_id IS NULL)",
        name="ck_room_presence_events_transition",
    ),
    sa.CheckConstraint(
        _lowercase_sha256_check("request_sha256"),
        name="ck_room_presence_events_request_sha256",
    ),
)

EXCEPTION_HEADS = sa.Table(
    "room_operational_exception_heads",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("facility_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("scope_kind", sa.String(20), nullable=False),
    sa.Column("scope_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("room_id", sa.Uuid(as_uuid=True)),
    sa.Column("condition_code", sa.String(100), nullable=False),
    sa.Column("state", sa.String(20), nullable=False),
    sa.Column("current_fingerprint_sha256", sa.CHAR(64), nullable=False),
    sa.Column("current_evidence", sa.JSON, nullable=False),
    sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    sa.Column(
        "acknowledged_by_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_operational_exceptions_acknowledged_by",
        ),
    ),
    sa.Column("acknowledgement_reason", sa.Text),
    sa.Column("resolved_at", sa.DateTime(timezone=True)),
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id"],
        ["facilities.organization_id", "facilities.id"],
        ondelete="RESTRICT",
        name="fk_room_operational_exceptions_facility",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "facility_id", "room_id"],
        ["rooms.organization_id", "rooms.facility_id", "rooms.id"],
        ondelete="RESTRICT",
        name="fk_room_operational_exceptions_room",
    ),
    sa.UniqueConstraint(
        "organization_id", "id", name="uq_room_operational_exceptions_org_id"
    ),
    sa.CheckConstraint(
        "scope_kind IN ('facility','room')",
        name="ck_room_operational_exceptions_scope",
    ),
    sa.CheckConstraint(
        "(scope_kind='facility' AND room_id IS NULL AND scope_id=facility_id) OR "
        "(scope_kind='room' AND room_id IS NOT NULL AND scope_id=room_id)",
        name="ck_room_operational_exceptions_scope_identity",
    ),
    sa.CheckConstraint(
        "condition_code IN "
        "('confirmed_children_above_configured_room_capacity',"
        "'confirmed_staff_below_configured_room_target',"
        "'open_shift_staff_without_current_room',"
        "'present_child_without_active_room','source_integrity_unknown')",
        name="ck_room_operational_exceptions_condition",
    ),
    sa.CheckConstraint(
        "state IN ('open','acknowledged','resolved')",
        name="ck_room_operational_exceptions_state",
    ),
    sa.CheckConstraint(
        _lowercase_sha256_check("current_fingerprint_sha256"),
        name="ck_room_operational_exceptions_fingerprint",
    ),
    sa.CheckConstraint(
        "(state='open' AND acknowledged_at IS NULL "
        "AND acknowledged_by_user_id IS NULL AND acknowledgement_reason IS NULL "
        "AND resolved_at IS NULL) OR "
        "(state='acknowledged' AND acknowledged_at IS NOT NULL "
        "AND acknowledged_by_user_id IS NOT NULL "
        "AND length(trim(acknowledgement_reason))>=5 AND resolved_at IS NULL) OR "
        "(state='resolved' AND resolved_at IS NOT NULL AND ("
        "(acknowledged_at IS NULL AND acknowledged_by_user_id IS NULL "
        "AND acknowledgement_reason IS NULL) OR "
        "(acknowledged_at IS NOT NULL AND acknowledged_by_user_id IS NOT NULL "
        "AND length(trim(acknowledgement_reason))>=5)))",
        name="ck_room_operational_exceptions_state_bundle",
    ),
    sa.CheckConstraint(
        "version > 0", name="ck_room_operational_exceptions_version"
    ),
)

EXCEPTION_EVENTS = sa.Table(
    "room_operational_exception_events",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("exception_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("operation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.String(30), nullable=False),
    sa.Column(
        "actor_user_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_room_operational_exception_events_actor",
        ),
    ),
    sa.Column("cause_entity_type", sa.String(60), nullable=False),
    sa.Column("cause_entity_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("previous_fingerprint_sha256", sa.CHAR(64)),
    sa.Column("current_fingerprint_sha256", sa.CHAR(64), nullable=False),
    sa.Column("evidence", sa.JSON, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "exception_id"],
        [
            "room_operational_exception_heads.organization_id",
            "room_operational_exception_heads.id",
        ],
        ondelete="RESTRICT",
        name="fk_room_operational_exception_events_head",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "id",
        name="uq_room_operational_exception_events_org_id",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "operation_id",
        name="uq_room_operational_exception_events_operation",
    ),
    sa.CheckConstraint(
        "event_type IN ('opened','materially_changed','acknowledged','resolved')",
        name="ck_room_operational_exception_events_type",
    ),
    sa.CheckConstraint(
        "(event_type='acknowledged' AND actor_user_id IS NOT NULL "
        "AND reason IS NOT NULL AND length(trim(reason))>=5) OR "
        "(event_type<>'acknowledged' AND reason IS NULL)",
        name="ck_room_operational_exception_events_acknowledgement",
    ),
    sa.CheckConstraint(
        _lowercase_sha256_check("current_fingerprint_sha256"),
        name="ck_room_operational_exception_events_current_fingerprint",
    ),
    sa.CheckConstraint(
        "previous_fingerprint_sha256 IS NULL OR "
        f"({_lowercase_sha256_check('previous_fingerprint_sha256')})",
        name="ck_room_operational_exception_events_previous_fingerprint",
    ),
)


def _create_indexes() -> None:
    for table_name, column_names in (
        (
            SESSIONS.name,
            (
                "organization_id",
                "membership_id",
                "staff_shift_id",
                "facility_id",
                "room_id",
            ),
        ),
        (
            PRESENCE_EVENTS.name,
            ("organization_id", "membership_id", "facility_id"),
        ),
        (
            EXCEPTION_HEADS.name,
            ("organization_id", "facility_id", "room_id"),
        ),
        (
            EXCEPTION_EVENTS.name,
            ("organization_id", "exception_id"),
        ),
    ):
        for column_name in column_names:
            op.create_index(
                f"ix_{table_name}_{column_name}",
                table_name,
                [column_name],
            )
    op.create_index(
        "uq_room_presence_sessions_open_membership",
        SESSIONS.name,
        ["organization_id", "membership_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "uq_room_presence_sessions_open_shift",
        SESSIONS.name,
        ["organization_id", "staff_shift_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_room_presence_sessions_room_live",
        SESSIONS.name,
        ["organization_id", "facility_id", "room_id", "ended_at"],
    )
    op.create_index(
        "ix_room_presence_events_membership_time",
        PRESENCE_EVENTS.name,
        ["organization_id", "membership_id", "occurred_at"],
    )
    op.create_index(
        "uq_room_operational_exceptions_unresolved",
        EXCEPTION_HEADS.name,
        ["organization_id", "scope_kind", "scope_id", "condition_code"],
        unique=True,
        postgresql_where=sa.text("state <> 'resolved'"),
        sqlite_where=sa.text("state <> 'resolved'"),
    )
    op.create_index(
        "ix_room_operational_exceptions_facility_state",
        EXCEPTION_HEADS.name,
        ["organization_id", "facility_id", "state", "last_changed_at"],
    )
    op.create_index(
        "ix_room_operational_exception_events_timeline",
        EXCEPTION_EVENTS.name,
        ["organization_id", "exception_id", "occurred_at"],
    )


def _install_sqlite_guards() -> None:
    for table in ("staff_room_presence_events", "room_operational_exception_events"):
        for action in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'immutable 0041 event'); END"
            )
    op.execute(
        """
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
    )
    op.execute(
        """
        CREATE TRIGGER staff_room_presence_sessions_update_guard
        BEFORE UPDATE ON staff_room_presence_sessions
        BEGIN
          SELECT CASE WHEN
            OLD.ended_at IS NOT NULL
            OR NEW.id<>OLD.id
            OR NEW.organization_id<>OLD.organization_id
            OR NEW.membership_id<>OLD.membership_id
            OR NEW.staff_shift_id<>OLD.staff_shift_id
            OR NEW.facility_id<>OLD.facility_id
            OR NEW.room_id<>OLD.room_id
            OR NEW.source<>OLD.source
            OR NEW.started_at<>OLD.started_at
            OR NEW.start_operation_id<>OLD.start_operation_id
            OR NEW.started_by_user_id<>OLD.started_by_user_id
            OR NEW.version<>2
            OR NEW.ended_at IS NULL
          THEN RAISE(ABORT,'invalid 0041 room presence transition') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_room_presence_sessions_no_delete
        BEFORE DELETE ON staff_room_presence_sessions
        BEGIN SELECT RAISE(ABORT,'immutable 0041 room presence'); END
        """
    )
    op.execute(
        """
        CREATE TRIGGER room_operational_exception_heads_insert_guard
        BEFORE INSERT ON room_operational_exception_heads
        BEGIN
          SELECT CASE WHEN NEW.state<>'open' OR NEW.version<>1
          THEN RAISE(ABORT,'invalid 0041 exception opening') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER room_operational_exception_heads_update_guard
        BEFORE UPDATE ON room_operational_exception_heads
        BEGIN
          SELECT CASE WHEN
            OLD.state='resolved'
            OR NEW.id<>OLD.id
            OR NEW.organization_id<>OLD.organization_id
            OR NEW.facility_id<>OLD.facility_id
            OR NEW.scope_kind<>OLD.scope_kind
            OR NEW.scope_id<>OLD.scope_id
            OR COALESCE(NEW.room_id,'')<>COALESCE(OLD.room_id,'')
            OR NEW.condition_code<>OLD.condition_code
            OR NEW.opened_at<>OLD.opened_at
            OR NEW.created_at<>OLD.created_at
            OR NEW.version NOT IN (OLD.version,OLD.version+1)
            OR (
              NEW.version=OLD.version
              AND (
                NEW.state<>OLD.state
                OR NEW.last_changed_at<>OLD.last_changed_at
                OR COALESCE(NEW.acknowledged_at,'')<>
                   COALESCE(OLD.acknowledged_at,'')
                OR COALESCE(NEW.acknowledged_by_user_id,'')<>
                   COALESCE(OLD.acknowledged_by_user_id,'')
                OR COALESCE(NEW.acknowledgement_reason,'')<>
                   COALESCE(OLD.acknowledgement_reason,'')
                OR COALESCE(NEW.resolved_at,'')<>COALESCE(OLD.resolved_at,'')
              )
            )
          THEN RAISE(ABORT,'invalid 0041 exception transition') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER room_operational_exception_heads_no_delete
        BEFORE DELETE ON room_operational_exception_heads
        BEGIN SELECT RAISE(ABORT,'immutable 0041 exception episode'); END
        """
    )


def _install_postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_presence_row_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
        AS $guard$
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
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_event_immutable_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        BEGIN
          RAISE EXCEPTION '0041 events are immutable'
            USING ERRCODE='23514', CONSTRAINT='ck_0041_events_immutable';
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_presence_event_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
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
          IF NEW.operation_id IS DISTINCT FROM context_operation
             OR NEW.actor_user_id IS DISTINCT FROM context_user THEN
            RAISE EXCEPTION 'invalid room presence event provenance'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_presence_events_provenance';
          END IF;
          IF (
            NEW.event_type<>'access_revoked_presence'
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
            NEW.event_type='access_revoked_presence'
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
            RAISE EXCEPTION 'invalid room presence event actor'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_presence_events_actor';
          END IF;
          IF (
            NEW.event_type IN ('started','clock_started_presence')
            AND NOT EXISTS (
              SELECT 1
              FROM public.staff_room_presence_sessions AS presence
              WHERE presence.organization_id=NEW.organization_id
                AND presence.id=NEW.to_session_id
                AND presence.membership_id=NEW.membership_id
                AND presence.staff_shift_id=NEW.staff_shift_id
                AND presence.facility_id=NEW.facility_id
                AND presence.start_operation_id=NEW.operation_id
                AND presence.started_by_user_id=NEW.actor_user_id
                AND presence.started_at=NEW.occurred_at
                AND presence.ended_at IS NULL
            )
          ) OR (
            NEW.event_type IN (
              'ended','clock_ended_presence','access_revoked_presence'
            )
            AND NOT EXISTS (
              SELECT 1
              FROM public.staff_room_presence_sessions AS presence
              WHERE presence.organization_id=NEW.organization_id
                AND presence.id=NEW.from_session_id
                AND presence.membership_id=NEW.membership_id
                AND presence.staff_shift_id=NEW.staff_shift_id
                AND presence.facility_id=NEW.facility_id
                AND presence.end_operation_id=NEW.operation_id
                AND presence.ended_by_user_id=NEW.actor_user_id
                AND presence.ended_at=NEW.occurred_at
            )
          ) OR (
            NEW.event_type='moved'
            AND (
              NOT EXISTS (
                SELECT 1
                FROM public.staff_room_presence_sessions AS source
                WHERE source.organization_id=NEW.organization_id
                  AND source.id=NEW.from_session_id
                  AND source.membership_id=NEW.membership_id
                  AND source.staff_shift_id=NEW.staff_shift_id
                  AND source.facility_id=NEW.facility_id
                  AND source.end_operation_id=NEW.operation_id
                  AND source.ended_by_user_id=NEW.actor_user_id
                  AND source.ended_at=NEW.occurred_at
                  AND source.end_reason='moved'
              )
              OR NOT EXISTS (
                SELECT 1
                FROM public.staff_room_presence_sessions AS destination
                WHERE destination.organization_id=NEW.organization_id
                  AND destination.id=NEW.to_session_id
                  AND destination.membership_id=NEW.membership_id
                  AND destination.staff_shift_id=NEW.staff_shift_id
                  AND destination.facility_id=NEW.facility_id
                  AND destination.start_operation_id=NEW.operation_id
                  AND destination.started_by_user_id=NEW.actor_user_id
                  AND destination.started_at=NEW.occurred_at
                  AND destination.ended_at IS NULL
              )
            )
          ) THEN
            RAISE EXCEPTION 'room presence event transition is incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_presence_events_session_bundle';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_presence_bundle_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
        AS $guard$
        DECLARE operation_key uuid;
        BEGIN
          operation_key := CASE
            WHEN NEW.ended_at IS NULL THEN NEW.start_operation_id
            ELSE NEW.end_operation_id
          END;
          IF NOT EXISTS (
            SELECT 1 FROM public.staff_room_presence_events AS event
            WHERE event.organization_id=NEW.organization_id
              AND event.operation_id=operation_key
              AND event.membership_id=NEW.membership_id
              AND event.staff_shift_id=NEW.staff_shift_id
              AND event.facility_id=NEW.facility_id
              AND (
                  (
                    NEW.ended_at IS NULL
                    AND event.to_session_id=NEW.id
                    AND event.event_type IN (
                      'started','moved','clock_started_presence'
                    )
                    AND event.occurred_at=NEW.started_at
                )
                OR (
                  NEW.ended_at IS NOT NULL
                  AND event.from_session_id=NEW.id
                  AND event.event_type IN (
                    'moved','ended','clock_ended_presence',
                    'access_revoked_presence'
                  )
                  AND event.occurred_at=NEW.ended_at
                )
              )
          ) THEN
            RAISE EXCEPTION 'room presence command bundle is incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_presence_sessions_command_bundle';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_exception_head_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        DECLARE
          context_operation uuid := NULLIF(
            pg_catalog.current_setting(
              'app.current_room_presence_operation_id', true
            ), ''
          )::uuid;
          context_user uuid := NULLIF(
            pg_catalog.current_setting('app.current_user_id', true), ''
          )::uuid;
          server_derived boolean := COALESCE(
            NULLIF(
              pg_catalog.current_setting(
                'app.current_room_presence_server_derived', true
              ), ''
            )::boolean,
            false
          );
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'room operational episodes are immutable'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_operational_exceptions_immutable';
          END IF;
          IF context_operation IS NULL THEN
            RAISE EXCEPTION 'room exception command context is required'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_operational_exceptions_command_context';
          END IF;
            IF TG_OP='INSERT' THEN
              IF NOT server_derived OR NEW.state<>'open' OR NEW.version<>1 THEN
                RAISE EXCEPTION 'invalid room exception opening provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_room_operational_exceptions_open_provenance';
              END IF;
            ELSE
              IF server_derived
                 AND NEW.version=OLD.version
                 AND OLD.state<>'resolved' THEN
                IF NEW.id IS DISTINCT FROM OLD.id
                   OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                   OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
                   OR NEW.scope_kind IS DISTINCT FROM OLD.scope_kind
                   OR NEW.scope_id IS DISTINCT FROM OLD.scope_id
                   OR NEW.room_id IS DISTINCT FROM OLD.room_id
                   OR NEW.condition_code IS DISTINCT FROM OLD.condition_code
                   OR NEW.state IS DISTINCT FROM OLD.state
                   OR NEW.opened_at IS DISTINCT FROM OLD.opened_at
                   OR NEW.last_changed_at IS DISTINCT FROM OLD.last_changed_at
                   OR NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at
                   OR NEW.acknowledged_by_user_id IS DISTINCT FROM
                      OLD.acknowledged_by_user_id
                   OR NEW.acknowledgement_reason IS DISTINCT FROM
                      OLD.acknowledgement_reason
                   OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                  RAISE EXCEPTION 'invalid room exception projection refresh'
                    USING ERRCODE='23514',
                          CONSTRAINT='ck_room_operational_exceptions_refresh';
                END IF;
                RETURN NEW;
              END IF;
              IF OLD.state='resolved'
               OR NEW.id IS DISTINCT FROM OLD.id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.facility_id IS DISTINCT FROM OLD.facility_id
               OR NEW.scope_kind IS DISTINCT FROM OLD.scope_kind
               OR NEW.scope_id IS DISTINCT FROM OLD.scope_id
               OR NEW.room_id IS DISTINCT FROM OLD.room_id
               OR NEW.condition_code IS DISTINCT FROM OLD.condition_code
               OR NEW.opened_at IS DISTINCT FROM OLD.opened_at
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.version<>OLD.version+1 THEN
              RAISE EXCEPTION 'invalid room exception transition'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_room_operational_exceptions_transition';
            END IF;
              IF NOT server_derived THEN
                IF OLD.state<>'open' OR NEW.state<>'acknowledged'
                   OR context_user IS NULL
                   OR NOT EXISTS (
                     SELECT 1
                     FROM public.organization_memberships AS actor_membership
                     JOIN public.roles AS actor_role
                       ON actor_role.organization_id=
                          actor_membership.organization_id
                      AND actor_role.id=actor_membership.role_id
                     WHERE actor_membership.organization_id=
                           NEW.organization_id
                       AND actor_membership.user_id=context_user
                       AND actor_membership.status='active'
                       AND actor_role.permissions::jsonb
                           @> '["staff:manage_educators"]'::jsonb
                   )
                   OR NEW.acknowledged_by_user_id IS DISTINCT FROM context_user
                   OR NEW.current_fingerprint_sha256 IS DISTINCT FROM
                      OLD.current_fingerprint_sha256
                   OR NEW.current_evidence IS DISTINCT FROM OLD.current_evidence
                   OR NEW.last_changed_at IS DISTINCT FROM OLD.last_changed_at
                   OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                   OR NEW.acknowledged_at IS NULL
                   OR NEW.acknowledgement_reason IS NULL THEN
                  RAISE EXCEPTION 'invalid room exception acknowledgement'
                    USING ERRCODE='23514',
                          CONSTRAINT='ck_room_operational_exceptions_acknowledgement';
                END IF;
              ELSIF NEW.state='acknowledged' THEN
                RAISE EXCEPTION 'server-derived acknowledgement is forbidden'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_room_operational_exceptions_actor';
              END IF;
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_exception_event_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $guard$
        DECLARE
          context_operation uuid := NULLIF(
            pg_catalog.current_setting(
              'app.current_room_presence_operation_id', true
            ), ''
          )::uuid;
          context_user uuid := NULLIF(
            pg_catalog.current_setting('app.current_user_id', true), ''
          )::uuid;
          server_derived boolean := COALESCE(
            NULLIF(
              pg_catalog.current_setting(
                'app.current_room_presence_server_derived', true
              ), ''
            )::boolean,
            false
          );
        BEGIN
          IF NEW.operation_id IS DISTINCT FROM context_operation
             OR (
               NEW.event_type='acknowledged'
               AND (
                 server_derived OR context_user IS NULL
                 OR NEW.actor_user_id IS DISTINCT FROM context_user
                 OR NOT EXISTS (
                   SELECT 1
                   FROM public.organization_memberships AS actor_membership
                   JOIN public.roles AS actor_role
                     ON actor_role.organization_id=
                        actor_membership.organization_id
                    AND actor_role.id=actor_membership.role_id
                   WHERE actor_membership.organization_id=
                         NEW.organization_id
                     AND actor_membership.user_id=context_user
                     AND actor_membership.status='active'
                     AND actor_role.permissions::jsonb
                         @> '["staff:manage_educators"]'::jsonb
                 )
               )
             )
             OR (
               NEW.event_type<>'acknowledged'
               AND (NOT server_derived OR NEW.actor_user_id IS NOT NULL)
          ) THEN
            RAISE EXCEPTION 'invalid room exception event provenance'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_operational_exception_events_provenance';
          END IF;
          IF NOT EXISTS (
            SELECT 1
            FROM public.room_operational_exception_heads AS head
            WHERE head.organization_id=NEW.organization_id
              AND head.id=NEW.exception_id
              AND head.current_fingerprint_sha256=
                  NEW.current_fingerprint_sha256
              AND head.current_evidence::jsonb=NEW.evidence::jsonb
              AND (
                (
                  NEW.event_type='opened'
                  AND head.state='open'
                  AND head.version=1
                  AND NEW.previous_fingerprint_sha256 IS NULL
                  AND head.opened_at=NEW.occurred_at
                  AND head.last_changed_at=NEW.occurred_at
                )
                OR (
                  NEW.event_type='materially_changed'
                  AND head.state='open'
                  AND head.version>1
                  AND NEW.previous_fingerprint_sha256 IS NOT NULL
                  AND head.last_changed_at=NEW.occurred_at
                )
                OR (
                  NEW.event_type='acknowledged'
                  AND head.state='acknowledged'
                  AND head.acknowledged_by_user_id=NEW.actor_user_id
                  AND head.acknowledged_at=NEW.occurred_at
                  AND head.acknowledgement_reason=NEW.reason
                )
                OR (
                  NEW.event_type='resolved'
                  AND head.state='resolved'
                  AND head.resolved_at=NEW.occurred_at
                  AND head.last_changed_at=NEW.occurred_at
                )
              )
          ) THEN
            RAISE EXCEPTION 'room exception event transition is incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_operational_exception_events_head_bundle';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0041_exception_bundle_guard()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public
          AS $guard$
          BEGIN
            IF TG_OP='UPDATE' AND NEW.version=OLD.version THEN
              RETURN NULL;
            END IF;
            IF NOT EXISTS (
            SELECT 1
            FROM public.room_operational_exception_events AS event
            WHERE event.organization_id=NEW.organization_id
              AND event.exception_id=NEW.id
              AND event.current_fingerprint_sha256=
                  NEW.current_fingerprint_sha256
              AND event.evidence::jsonb=NEW.current_evidence::jsonb
                AND (
                  (NEW.version=1 AND event.event_type='opened'
                      AND event.previous_fingerprint_sha256 IS NULL
                      AND event.occurred_at=NEW.last_changed_at)
                  OR (NEW.state='acknowledged'
                      AND event.event_type='acknowledged'
                      AND event.actor_user_id=NEW.acknowledged_by_user_id
                      AND event.previous_fingerprint_sha256=
                          OLD.current_fingerprint_sha256
                      AND event.occurred_at=NEW.acknowledged_at
                      AND event.reason=NEW.acknowledgement_reason)
                  OR (NEW.state='resolved' AND event.event_type='resolved'
                      AND event.previous_fingerprint_sha256=
                          OLD.current_fingerprint_sha256
                      AND event.occurred_at=NEW.last_changed_at)
                  OR (NEW.version>1 AND NEW.state='open'
                      AND event.event_type='materially_changed'
                      AND event.previous_fingerprint_sha256=
                          OLD.current_fingerprint_sha256
                      AND event.occurred_at=NEW.last_changed_at)
              )
          ) THEN
            RAISE EXCEPTION 'room exception command bundle is incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_room_operational_exceptions_command_bundle';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    for function in (
        "caresync_0041_presence_row_guard()",
        "caresync_0041_event_immutable_guard()",
        "caresync_0041_presence_event_guard()",
        "caresync_0041_presence_bundle_guard()",
        "caresync_0041_exception_head_guard()",
        "caresync_0041_exception_event_guard()",
        "caresync_0041_exception_bundle_guard()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function} FROM PUBLIC")

    op.execute(
        "CREATE TRIGGER staff_room_presence_sessions_row_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON public.staff_room_presence_sessions "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0041_presence_row_guard()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER staff_room_presence_sessions_bundle_guard "
        "AFTER INSERT OR UPDATE ON public.staff_room_presence_sessions "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_presence_bundle_guard()"
    )
    op.execute(
        "CREATE TRIGGER staff_room_presence_events_insert_guard "
        "BEFORE INSERT ON public.staff_room_presence_events FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_presence_event_guard()"
    )
    op.execute(
        "CREATE TRIGGER staff_room_presence_events_immutable "
        "BEFORE UPDATE OR DELETE ON public.staff_room_presence_events FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_event_immutable_guard()"
    )
    op.execute(
        "CREATE TRIGGER room_operational_exception_heads_row_guard "
        "BEFORE INSERT OR UPDATE OR DELETE "
        "ON public.room_operational_exception_heads FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_exception_head_guard()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER room_operational_exception_heads_bundle_guard "
        "AFTER INSERT OR UPDATE ON public.room_operational_exception_heads "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_exception_bundle_guard()"
    )
    op.execute(
        "CREATE TRIGGER room_operational_exception_events_insert_guard "
        "BEFORE INSERT ON public.room_operational_exception_events FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0041_exception_event_guard()"
    )
    op.execute(
        "CREATE TRIGGER room_operational_exception_events_immutable "
        "BEFORE UPDATE OR DELETE ON public.room_operational_exception_events "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0041_event_immutable_guard()"
    )


def _install_postgres_rls_and_grants() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        active_member = (
            "EXISTS (SELECT 1 FROM public.organization_memberships AS membership "
            "WHERE membership.organization_id=NULLIF("
            "pg_catalog.current_setting('app.current_organization_id',true),'')::uuid "
            "AND membership.user_id=NULLIF("
            "pg_catalog.current_setting('app.current_user_id',true),'')::uuid "
            "AND membership.status='active')"
        )
        scope = (
            "organization_id=NULLIF("
            "pg_catalog.current_setting('app.current_organization_id',true),'')::uuid "
            f"AND {active_member}"
        )
        op.execute(
            f'CREATE POLICY "{table}_tenant" ON public.{table} '
            f"USING ({scope}) WITH CHECK ({scope})"
        )
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles
            WHERE rolname='caresync_basic_app'
          ) THEN
            GRANT SELECT,INSERT ON TABLE
              public.staff_room_presence_sessions,
              public.staff_room_presence_events,
              public.room_operational_exception_heads,
              public.room_operational_exception_events
            TO caresync_basic_app;
            GRANT UPDATE (
              ended_at,end_reason,end_operation_id,ended_by_user_id,version,updated_at
            ) ON TABLE public.staff_room_presence_sessions
            TO caresync_basic_app;
            GRANT UPDATE (
              state,current_fingerprint_sha256,current_evidence,last_changed_at,
              acknowledged_at,acknowledged_by_user_id,acknowledgement_reason,
              resolved_at,version,updated_at
            ) ON TABLE public.room_operational_exception_heads
            TO caresync_basic_app;
          END IF;
        END
        $grant$
        """
    )


def _set_postgres_downgrade_force_rls(*, enabled: bool) -> None:
    """Give the NOBYPASSRLS migration owner complete downgrade visibility.

    The caller holds ACCESS EXCLUSIVE locks across both 0041 and residue
    relations. PostgreSQL transactional DDL restores FORCE automatically if a
    populated downgrade raises and the migration transaction rolls back.
    """

    action = "FORCE" if enabled else "NO FORCE"
    for table in (*TABLES, *_DOWNGRADE_DEPENDENCY_TABLES):
        op.execute(
            f"ALTER TABLE public.{table} {action} ROW LEVEL SECURITY"
        )


def _has_rows(bind: sa.engine.Connection) -> bool:
    if any(
        bool(
            bind.scalar(
                sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")
            )
        )
        for table in TABLES
    ):
        return True
    return bool(
        bind.scalar(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM audit_events WHERE action IN "
                "('room_safety.release_reconciliation_facility_completed',"
                "'room_safety.release_reconciliation_completed',"
                "'staff_room_presence.started','staff_room_presence.moved',"
                "'staff_room_presence.ended',"
                "'staff_room_presence.access_revoked',"
                "'room_operational_exception.acknowledged') "
                "UNION ALL SELECT 1 FROM realtime_events WHERE "
                "event_type LIKE 'staff_room_presence.%' OR "
                "event_type LIKE 'room_operational_exception.%' "
                "UNION ALL SELECT 1 FROM user_notifications WHERE "
                "event_key LIKE 'room-operational-exception:%' OR "
                "action_entity_type='room_operational_exception' LIMIT 1)"
            )
        )
    )


def _delete_disposable_external_residue(
    bind: sa.engine.Connection,
) -> None:
    """Remove only 0041-owned rows during an explicitly destructive proof."""

    bind.execute(
        sa.text(
            "DELETE FROM realtime_events WHERE "
            "event_type LIKE 'staff_room_presence.%' OR "
            "event_type LIKE 'room_operational_exception.%'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM user_notifications WHERE "
            "event_key LIKE 'room-operational-exception:%' OR "
            "action_entity_type='room_operational_exception'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM audit_events WHERE action IN "
            "('room_safety.release_reconciliation_facility_completed',"
            "'room_safety.release_reconciliation_completed',"
            "'staff_room_presence.started','staff_room_presence.moved',"
            "'staff_room_presence.ended',"
            "'staff_room_presence.access_revoked',"
            "'room_operational_exception.acknowledged')"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    for table in (SESSIONS, PRESENCE_EVENTS, EXCEPTION_HEADS, EXCEPTION_EVENTS):
        table.create(bind, checkfirst=False)
    _create_indexes()
    if bind.dialect.name == "postgresql":
        _install_postgres_guards()
        _install_postgres_rls_and_grants()
    else:
        _install_sqlite_guards()


def downgrade() -> None:
    bind = op.get_bind()
    disposable_opt_in = os.getenv(
        "CARESYNC_ALLOW_0041_DESTRUCTIVE_DOWNGRADE", ""
    ).strip().lower() in {"1", "true", "yes"}
    if bind.dialect.name == "postgresql":
        op.execute(
            "LOCK TABLE "
            + ",".join(
                f"public.{table}"
                for table in (*TABLES, *_DOWNGRADE_DEPENDENCY_TABLES)
            )
            + " IN ACCESS EXCLUSIVE MODE"
        )
        _set_postgres_downgrade_force_rls(enabled=False)
        op.execute("SET LOCAL row_security=off")
    has_history = _has_rows(bind)
    if has_history and not disposable_opt_in:
        raise RuntimeError(
            "0041 downgrade refused: live room presence or exception history exists; "
            "set CARESYNC_ALLOW_0041_DESTRUCTIVE_DOWNGRADE=1 only for a disposable database"
        )
    if disposable_opt_in:
        _delete_disposable_external_residue(bind)
    if bind.dialect.name == "postgresql":
        _set_postgres_downgrade_force_rls(enabled=True)
        for table, trigger in (
            (
                "staff_room_presence_sessions",
                "staff_room_presence_sessions_bundle_guard",
            ),
            (
                "staff_room_presence_sessions",
                "staff_room_presence_sessions_row_guard",
            ),
            (
                "staff_room_presence_events",
                "staff_room_presence_events_insert_guard",
            ),
            (
                "staff_room_presence_events",
                "staff_room_presence_events_immutable",
            ),
            (
                "room_operational_exception_heads",
                "room_operational_exception_heads_bundle_guard",
            ),
            (
                "room_operational_exception_heads",
                "room_operational_exception_heads_row_guard",
            ),
            (
                "room_operational_exception_events",
                "room_operational_exception_events_insert_guard",
            ),
            (
                "room_operational_exception_events",
                "room_operational_exception_events_immutable",
            ),
        ):
            op.execute(f"DROP TRIGGER {trigger} ON public.{table}")
        for function in (
            "caresync_0041_exception_bundle_guard()",
            "caresync_0041_exception_event_guard()",
            "caresync_0041_exception_head_guard()",
            "caresync_0041_presence_bundle_guard()",
            "caresync_0041_presence_event_guard()",
            "caresync_0041_event_immutable_guard()",
            "caresync_0041_presence_row_guard()",
        ):
            op.execute(f"DROP FUNCTION public.{function}")
    else:
        for table in ("staff_room_presence_events", "room_operational_exception_events"):
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER {table}_no_{action}")
        op.execute("DROP TRIGGER staff_room_presence_sessions_insert_guard")
        op.execute("DROP TRIGGER staff_room_presence_sessions_update_guard")
        op.execute("DROP TRIGGER staff_room_presence_sessions_no_delete")
    for table in reversed(
        (SESSIONS, PRESENCE_EVENTS, EXCEPTION_HEADS, EXCEPTION_EVENTS)
    ):
        table.drop(bind, checkfirst=False)

"""Add durable realtime outbox, scoped tickets, and ledger bridges.

Revision ID: 0011_realtime_outbox
Revises: 0010_staff_ops
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
from app.basic.models import RealtimeEvent, RealtimeTicket

revision = "0011_realtime_outbox"
down_revision = "0010_staff_ops"
branch_labels = None
depends_on = None


def _postgres_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION realtime_from_audit_event() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id, occurred_at, payload)
          VALUES
            (NEW.id, NEW.organization_id, NEW.action, NEW.entity_type, NEW.entity_id,
             NEW.occurred_at,
             jsonb_build_object('source', 'audit_event', 'facility_id', NEW.facility_id));
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION realtime_from_ats_event() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id, occurred_at, payload)
          VALUES
            (NEW.id, NEW.organization_id, NEW.event_type, NEW.entity_type, NEW.entity_id,
             NEW.occurred_at, jsonb_build_object('source', 'ats_event'));
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION realtime_from_audit_event()"
    )
    op.execute(
        "CREATE TRIGGER ats_events_realtime AFTER INSERT ON ats_events "
        "FOR EACH ROW EXECUTE FUNCTION realtime_from_ats_event()"
    )


def _sqlite_triggers() -> None:
    op.execute(
        """
        CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id, occurred_at, payload)
          VALUES
            (lower(hex(randomblob(16))), NEW.organization_id, NEW.action, NEW.entity_type,
             NEW.entity_id, NEW.occurred_at,
             json_object('source', 'audit_event', 'facility_id', NEW.facility_id));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_events_realtime AFTER INSERT ON ats_events
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id, occurred_at, payload)
          VALUES
            (lower(hex(randomblob(16))), NEW.organization_id, NEW.event_type, NEW.entity_type,
             NEW.entity_id, NEW.occurred_at, json_object('source', 'ats_event'));
        END
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    RealtimeEvent.__table__.create(bind, checkfirst=False)
    RealtimeTicket.__table__.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        setting = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
        for name in ("realtime_events", "realtime_tickets"):
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
                GRANT SELECT, INSERT ON TABLE realtime_events TO caresync_basic_app;
                GRANT SELECT, INSERT, UPDATE ON TABLE realtime_tickets TO caresync_basic_app;
                GRANT USAGE, SELECT ON SEQUENCE realtime_events_sequence_id_seq
                  TO caresync_basic_app;
              END IF;
            END $grant$
            """
        )
        _postgres_triggers()
    else:
        _sqlite_triggers()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS ats_events_realtime ON ats_events")
        op.execute("DROP TRIGGER IF EXISTS audit_events_realtime ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS realtime_from_ats_event()")
        op.execute("DROP FUNCTION IF EXISTS realtime_from_audit_event()")
    else:
        op.execute("DROP TRIGGER IF EXISTS ats_events_realtime")
        op.execute("DROP TRIGGER IF EXISTS audit_events_realtime")
    RealtimeTicket.__table__.drop(bind, checkfirst=False)
    RealtimeEvent.__table__.drop(bind, checkfirst=False)

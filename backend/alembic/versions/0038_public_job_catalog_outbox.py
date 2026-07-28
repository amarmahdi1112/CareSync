"""Add a durable public-safe job catalog invalidation outbox.

Revision ID: 0038_public_job_catalog_outbox
Revises: 0037_billing_agreement_scope
Create Date: 2026-07-23

The candidate marketplace projection intentionally deletes paused and closed
listings.  A reconnecting candidate therefore cannot use that projection to
prove which tenant realtime event should be replayed.  Open-listing edits also
need a global invalidation without copying their new content into an event.
This revision records a minimal, globally readable invalidation beside the
canonical realtime event. It contains no employer-authored listing text and no
candidate data.

Downgrade removes only the 0038 public projection and trigger. Synthetic
backfill rows already appended to ``realtime_events`` are harmless canonical
refresh invalidations, so they are intentionally retained rather than silently
rewriting shared realtime history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op

revision = "0038_public_job_catalog_outbox"
down_revision = "0037_billing_agreement_scope"
branch_labels = None
depends_on = None

TABLE = "public_job_catalog_events"
TRIGGER = "realtime_events_public_job_catalog"
FUNCTION = "caresync_public_job_catalog_from_realtime"

# Freeze the historical 0038 DDL locally. Later ORM evolution must not mutate
# a fresh install or replay of this revision.
_metadata = sa.MetaData()
sa.Table(
    "realtime_events",
    _metadata,
    sa.Column("sequence_id", sa.Integer(), primary_key=True),
    sa.Column("id", sa.Uuid(as_uuid=True), unique=True, nullable=False),
)
PUBLIC_JOB_CATALOG_TABLE = sa.Table(
    TABLE,
    _metadata,
    sa.Column(
        "sequence_id",
        sa.Integer(),
        sa.ForeignKey("realtime_events.sequence_id", ondelete="RESTRICT"),
        primary_key=True,
        autoincrement=False,
    ),
    sa.Column(
        "event_id",
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("realtime_events.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("listing_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
    sa.Column("event_type", sa.String(100), nullable=False),
    sa.Column("public_status", sa.String(20), nullable=False),
    sa.Column("listing_version", sa.Integer(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("event_id", name="uq_public_job_catalog_event_id"),
    sa.UniqueConstraint(
        "listing_id",
        "listing_version",
        name="uq_public_job_catalog_listing_version",
    ),
    sa.CheckConstraint(
        "public_status IN ('open','paused','closed')",
        name="ck_public_job_catalog_status",
    ),
    sa.CheckConstraint(
        "event_type IN ('job.updated','job.status_changed')",
        name="ck_public_job_catalog_event_type",
    ),
    sa.CheckConstraint(
        "listing_version > 0",
        name="ck_public_job_catalog_version",
    ),
)
REALTIME_INSERT = sa.table(
    "realtime_events",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("organization_id", sa.Uuid(as_uuid=True)),
    sa.column("event_type", sa.String(100)),
    sa.column("entity_type", sa.String(60)),
    sa.column("entity_id", sa.Uuid(as_uuid=True)),
    sa.column("occurred_at", sa.DateTime(timezone=True)),
    sa.column("payload", sa.JSON()),
)


def _postgres_trigger() -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
          IF NEW.event_type IN ('job.updated', 'job.status_changed')
             AND NEW.entity_type = 'job'
             AND NEW.entity_id IS NOT NULL THEN
            INSERT INTO public.{TABLE}
              (sequence_id, event_id, listing_id,
               event_type, public_status, listing_version, occurred_at)
            SELECT NEW.sequence_id, NEW.id, job.id,
                   NEW.event_type, job.status, job.version, NEW.occurred_at
            FROM public.ats_jobs AS job
            WHERE job.organization_id = NEW.organization_id
              AND job.id = NEW.entity_id
              AND job.published_at IS NOT NULL
              AND job.status IN ('open', 'paused', 'closed')
              AND (NEW.event_type = 'job.status_changed' OR job.status = 'open');
          END IF;
          RETURN NEW;
        END
        $function$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.{FUNCTION}() FROM PUBLIC")
    op.execute(
        f"CREATE TRIGGER {TRIGGER} AFTER INSERT ON public.realtime_events "
        f"FOR EACH ROW EXECUTE FUNCTION public.{FUNCTION}()"
    )


def _sqlite_trigger() -> None:
    op.execute(
        f"""
        CREATE TRIGGER {TRIGGER} AFTER INSERT ON realtime_events
        WHEN NEW.event_type IN ('job.updated', 'job.status_changed')
          AND NEW.entity_type = 'job'
          AND NEW.entity_id IS NOT NULL
        BEGIN
          INSERT INTO {TABLE}
            (sequence_id, event_id, listing_id,
             event_type, public_status, listing_version, occurred_at)
          SELECT NEW.sequence_id, NEW.id, job.id,
                 NEW.event_type, job.status, job.version, NEW.occurred_at
          FROM ats_jobs AS job
          WHERE job.organization_id = NEW.organization_id
            AND job.id = NEW.entity_id
            AND job.published_at IS NOT NULL
            AND job.status IN ('open', 'paused', 'closed')
            AND (NEW.event_type = 'job.status_changed' OR job.status = 'open');
        END
        """
    )


def _install_postgres_read_boundary() -> None:
    # Do not FORCE RLS here: the table/function owner is the only writer and
    # the SECURITY DEFINER trigger needs the normal owner bypass. The runtime
    # role receives SELECT only and no INSERT policy exists.
    op.execute(f'ALTER TABLE public."{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{TABLE}_public_read" ON public."{TABLE}" '
        "FOR SELECT USING (true)"
    )
    op.execute(f'REVOKE ALL ON TABLE public."{TABLE}" FROM PUBLIC')
    op.execute("REVOKE ALL ON TABLE public.alembic_version FROM PUBLIC")
    op.execute(
        f"""
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            REVOKE ALL ON TABLE public.{TABLE} FROM caresync_basic_app;
            REVOKE ALL ON TABLE public.alembic_version FROM caresync_basic_app;
            GRANT SELECT ON TABLE public.{TABLE} TO caresync_basic_app;
            GRANT SELECT ON TABLE public.alembic_version TO caresync_basic_app;
          END IF;
        END
        $grant$
        """
    )


def _backfill_final_catalog_state(bind: sa.engine.Connection) -> None:
    """Append one final refresh invalidation for every historically public job."""

    public_jobs = bind.execute(
        sa.text(
            "SELECT id,organization_id FROM ats_jobs "
            "WHERE published_at IS NOT NULL "
            "AND status IN ('open','paused','closed') "
            "ORDER BY organization_id,id"
        )
    ).mappings()
    occurred_at = datetime.now(UTC)
    for job in public_jobs:
        bind.execute(
            sa.insert(REALTIME_INSERT).values(
                id=uuid4(),
                organization_id=UUID(str(job["organization_id"])),
                event_type="job.status_changed",
                entity_type="job",
                entity_id=UUID(str(job["id"])),
                occurred_at=occurred_at,
                payload={
                    "source": "0038_public_job_catalog_backfill",
                    "refresh_required": True,
                },
            )
        )


def _postgres_backfill_with_force_restored(bind: sa.engine.Connection) -> None:
    """Let a NOBYPASSRLS schema owner backfill, then restore exact FORCE state."""

    force_state = {
        str(row.relname): bool(row.relforcerowsecurity)
        for row in bind.execute(
            sa.text(
                "SELECT relation.relname,relation.relforcerowsecurity "
                "FROM pg_catalog.pg_class AS relation "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid=relation.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND relation.relname IN ('ats_jobs','realtime_events')"
            )
        )
    }
    if set(force_state) != {"ats_jobs", "realtime_events"}:
        raise RuntimeError("0038 backfill refused: canonical source tables are missing")
    if force_state != {"ats_jobs": True, "realtime_events": True}:
        raise RuntimeError(
            "0038 backfill refused: canonical 0037 source tables must both FORCE RLS"
        )
    try:
        for table_name in force_state:
            op.execute(f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY")
        _backfill_final_catalog_state(bind)
    finally:
        for table_name in force_state:
            op.execute(f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY")
    restored = {
        str(row.relname): bool(row.relforcerowsecurity)
        for row in bind.execute(
            sa.text(
                "SELECT relation.relname,relation.relforcerowsecurity "
                "FROM pg_catalog.pg_class AS relation "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid=relation.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND relation.relname IN ('ats_jobs','realtime_events')"
            )
        )
    }
    if restored != {"ats_jobs": True, "realtime_events": True}:
        raise RuntimeError("0038 backfill refused: FORCE RLS state was not restored")


def upgrade() -> None:
    bind = op.get_bind()
    PUBLIC_JOB_CATALOG_TABLE.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        _install_postgres_read_boundary()
        _postgres_trigger()
        _postgres_backfill_with_force_restored(bind)
    else:
        _sqlite_trigger()
        _backfill_final_catalog_state(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON public.realtime_events")
        op.execute(f"DROP FUNCTION IF EXISTS public.{FUNCTION}()")
    else:
        op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER}")
    PUBLIC_JOB_CATALOG_TABLE.drop(bind, checkfirst=False)

"""Add the versioned childcare command spine and temporal care network.

Revision ID: 0028_childcare_command_spine
Revises: 0027_staff_exchange
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_childcare_command_spine"
down_revision = "0027_staff_exchange"
branch_labels = None
depends_on = None


def _disable_rls_for_owner_visible_preflight(bind, tables: tuple[str, ...]) -> None:
    if bind.dialect.name != "postgresql":
        return
    for table in tables:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


def _restore_forced_rls(bind, tables: tuple[str, ...]) -> None:
    if bind.dialect.name != "postgresql":
        return
    for table in tables:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')


def upgrade() -> None:
    bind = op.get_bind()
    preflight_tables = (
        "guardians",
        "enrollments",
        "children",
        "facility_programs",
        "rooms",
    )
    # FORCE RLS also filters a NOBYPASSRLS table owner. Migrations must audit
    # every tenant, so suspend it transactionally while the owner-only
    # reconciliation queries run, then restore the exact protection before
    # any schema mutation. A refusal rolls the DDL back as well.
    _disable_rls_for_owner_visible_preflight(bind, preflight_tables)

    duplicate_guardian_slots = bind.execute(
        sa.text(
            "SELECT count(*) FROM ("
            "SELECT organization_id, family_id, is_primary FROM guardians "
            "GROUP BY organization_id, family_id, is_primary HAVING count(*) > 1"
            ") AS duplicate_slots"
        )
    ).scalar_one()
    duplicate_open_enrollments = bind.execute(
        sa.text(
            "SELECT count(*) FROM ("
            "SELECT organization_id, child_id FROM enrollments "
            "WHERE status IN ('pending','active','paused') "
            "GROUP BY organization_id, child_id HAVING count(*) > 1"
            ") AS duplicate_open"
        )
    ).scalar_one()
    incoherent_placements = bind.execute(
        sa.text(
            "SELECT count(*) FROM enrollments e "
            "JOIN children c ON c.organization_id=e.organization_id AND c.id=e.child_id "
            "LEFT JOIN facility_programs p ON p.organization_id=e.organization_id "
            "AND p.id=e.program_id "
            "LEFT JOIN rooms r ON r.organization_id=e.organization_id AND r.id=e.room_id "
            "WHERE (e.program_id IS NULL) <> (e.room_id IS NULL) "
            "OR e.start_date < c.date_of_birth "
            "OR (e.program_id IS NOT NULL AND (p.id IS NULL OR r.id IS NULL "
            "OR p.facility_id <> e.facility_id OR r.facility_id <> e.facility_id "
            "OR r.program_id IS NULL OR r.program_id <> e.program_id))"
        )
    ).scalar_one()
    assigned_pending_enrollments = bind.execute(
        sa.text(
            "SELECT count(*) FROM enrollments "
            "WHERE status = 'pending' AND (program_id IS NOT NULL OR room_id IS NOT NULL)"
        )
    ).scalar_one()
    if (
        duplicate_guardian_slots
        or duplicate_open_enrollments
        or incoherent_placements
        or assigned_pending_enrollments
    ):
        _restore_forced_rls(bind, preflight_tables)
        raise RuntimeError(
            "0028 reconciliation required before migration: "
            f"duplicate_guardian_slots={duplicate_guardian_slots}, "
            f"duplicate_open_enrollments={duplicate_open_enrollments}, "
            f"incoherent_placements={incoherent_placements}, "
            f"assigned_pending_enrollments={assigned_pending_enrollments}"
        )

    with op.batch_alter_table("facility_programs") as batch:
        batch.create_unique_constraint(
            "uq_programs_org_facility_id",
            ["organization_id", "facility_id", "id"],
        )
    with op.batch_alter_table("rooms") as batch:
        batch.create_unique_constraint(
            "uq_rooms_org_facility_program_id",
            ["organization_id", "facility_id", "program_id", "id"],
        )

    with op.batch_alter_table("families") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch.create_check_constraint("ck_families_version", "version > 0")

    with op.batch_alter_table("children") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch.create_check_constraint("ck_children_version", "version > 0")

    with op.batch_alter_table("guardians") as batch:
        batch.add_column(sa.Column("created_operation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("retired_operation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "ck_guardians_retirement_pair",
            "(retired_at IS NULL AND retired_operation_id IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
        )
    op.create_index("ix_guardians_retired_at", "guardians", ["retired_at"])
    op.create_index(
        "uq_guardians_current_primary_slot",
        "guardians",
        ["organization_id", "family_id", "is_primary"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
        sqlite_where=sa.text("retired_at IS NULL"),
    )

    with op.batch_alter_table("emergency_contacts") as batch:
        batch.add_column(sa.Column("created_operation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("retired_operation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "ck_contacts_retirement_pair",
            "(retired_at IS NULL AND retired_operation_id IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_operation_id IS NOT NULL)",
        )
    op.create_index("ix_emergency_contacts_retired_at", "emergency_contacts", ["retired_at"])
    op.create_index(
        "ix_contacts_current_family",
        "emergency_contacts",
        ["organization_id", "family_id"],
        postgresql_where=sa.text("retired_at IS NULL"),
        sqlite_where=sa.text("retired_at IS NULL"),
    )

    with op.batch_alter_table("enrollments") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("placement_effective_date", sa.Date(), nullable=True))
        batch.alter_column(
            "status",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default="pending",
        )
    op.execute(
        "UPDATE enrollments SET placement_effective_date = start_date "
        "WHERE program_id IS NOT NULL AND room_id IS NOT NULL"
    )
    # Keep the legacy assigned-row backfill in the same owner-visible window;
    # otherwise FORCE RLS would make a NOBYPASSRLS migration owner update zero
    # tenant rows. Protection is restored before constraints and policies are
    # finalized.
    _restore_forced_rls(bind, preflight_tables)
    with op.batch_alter_table("enrollments") as batch:
        batch.create_check_constraint("ck_enrollments_version", "version > 0")
        batch.create_check_constraint(
            "ck_enrollment_placement_pair",
            "(program_id IS NULL AND room_id IS NULL AND placement_effective_date IS NULL) OR "
            "(program_id IS NOT NULL AND room_id IS NOT NULL "
            "AND placement_effective_date IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_enrollment_pending_unassigned",
            "status <> 'pending' OR program_id IS NULL",
        )
        batch.create_foreign_key(
            "fk_enrollments_facility_program",
            "facility_programs",
            ["organization_id", "facility_id", "program_id"],
            ["organization_id", "facility_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_enrollments_facility_program_room",
            "rooms",
            ["organization_id", "facility_id", "program_id", "room_id"],
            ["organization_id", "facility_id", "program_id", "id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "uq_enrollments_one_open_org_child",
        "enrollments",
        ["organization_id", "child_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','active','paused')"),
        sqlite_where=sa.text("status IN ('pending','active','paused')"),
    )
    op.create_index(
        "ix_enrollments_open_room_interval",
        "enrollments",
        [
            "organization_id",
            "room_id",
            "status",
            "placement_effective_date",
            "end_date",
        ],
        postgresql_where=sa.text("room_id IS NOT NULL AND status IN ('pending','active','paused')"),
        sqlite_where=sa.text("room_id IS NOT NULL AND status IN ('pending','active','paused')"),
    )

    op.create_table(
        "childcare_command_slots",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("client_operation_id", sa.Uuid(), primary_key=True),
        sa.Column("entry_kind", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "entry_kind IN ('receipt','absence_claim')",
            name="ck_childcare_command_slots_kind",
        ),
    )
    op.create_table(
        "childcare_command_reconciliation_proofs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "client_operation_id",
            name="uq_childcare_command_reconciliation_proofs_identity_operation",
        ),
    )
    op.create_index(
        "ix_childcare_command_reconciliation_proofs_organization_id",
        "childcare_command_reconciliation_proofs",
        ["organization_id"],
    )
    op.create_index(
        "ix_childcare_command_reconciliation_proofs_actor_user_id",
        "childcare_command_reconciliation_proofs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_childcare_command_reconciliation_proofs_actor_window",
        "childcare_command_reconciliation_proofs",
        ["organization_id", "actor_user_id", "finalized_at"],
    )
    op.create_table(
        "childcare_command_reconciliation_budget_entries",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), primary_key=True),
        sa.Column("client_operation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "charged_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "childcare_command_reconciliation_budgets",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), primary_key=True),
        sa.Column("window_kind", sa.String(20), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("operation_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "window_kind IN ('hour','day')",
            name="ck_childcare_command_reconciliation_budgets_kind",
        ),
        sa.CheckConstraint(
            "operation_count >= 1 AND "
            "((window_kind = 'hour' AND operation_count <= 120) OR "
            "(window_kind = 'day' AND operation_count <= 500))",
            name="ck_childcare_command_reconciliation_budgets_count",
        ),
    )

    op.create_table(
        "childcare_command_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("command_type", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=True),
        sa.Column("committed_version", sa.Integer(), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("outcome", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            ondelete="RESTRICT",
            name="fk_childcare_command_receipts_facility",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_childcare_command_receipts_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_childcare_command_receipts_operation",
        ),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_childcare_command_receipts_hash"),
        sa.CheckConstraint("committed_version > 0", name="ck_childcare_command_receipts_version"),
        sa.CheckConstraint(
            "target_type IN ('family','child','enrollment')",
            name="ck_childcare_command_receipts_target",
        ),
    )
    for column in ("organization_id", "command_type", "target_id", "facility_id"):
        op.create_index(
            f"ix_childcare_command_receipts_{column}",
            "childcare_command_receipts",
            [column],
        )

    op.create_table(
        "childcare_command_claims",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_childcare_command_claims_operation",
        ),
    )
    op.create_index(
        "ix_childcare_command_claims_organization_id",
        "childcare_command_claims",
        ["organization_id"],
    )
    op.create_index(
        "ix_childcare_command_claims_actor_user_id",
        "childcare_command_claims",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_childcare_command_claims_actor_window",
        "childcare_command_claims",
        ["organization_id", "actor_user_id", "claimed_at"],
    )

    # The care-network rows retain the exact command that created or retired
    # them.  Add these constraints only after the receipt table exists.
    with op.batch_alter_table("guardians") as batch:
        batch.create_foreign_key(
            "fk_guardians_created_operation",
            "childcare_command_receipts",
            ["organization_id", "created_operation_id"],
            ["organization_id", "client_operation_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_guardians_retired_operation",
            "childcare_command_receipts",
            ["organization_id", "retired_operation_id"],
            ["organization_id", "client_operation_id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("emergency_contacts") as batch:
        batch.create_foreign_key(
            "fk_contacts_created_operation",
            "childcare_command_receipts",
            ["organization_id", "created_operation_id"],
            ["organization_id", "client_operation_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_contacts_retired_operation",
            "childcare_command_receipts",
            ["organization_id", "retired_operation_id"],
            ["organization_id", "client_operation_id"],
            ondelete="RESTRICT",
        )

    if bind.dialect.name != "postgresql":
        return
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    actor = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    operation = "NULLIF(current_setting('app.current_childcare_operation_id', true), '')::uuid"
    op.execute(
        """
        CREATE FUNCTION public.caresync_charge_childcare_reconciliation(
          charged_organization_id uuid,
          charged_actor_user_id uuid,
          charged_operation_id uuid
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $charge$
        DECLARE
          inserted_operation_id uuid;
          updated_budget integer;
          current_hour timestamptz;
          current_day timestamptz;
        BEGIN
          inserted_operation_id := NULL;
          INSERT INTO public.childcare_command_reconciliation_budget_entries
            (organization_id, actor_user_id, client_operation_id)
          VALUES
            (charged_organization_id, charged_actor_user_id, charged_operation_id)
          ON CONFLICT (organization_id, actor_user_id, client_operation_id) DO NOTHING
          RETURNING client_operation_id INTO inserted_operation_id;
          IF inserted_operation_id IS NULL THEN
            RETURN;
          END IF;

          current_hour := date_trunc(
            'hour', statement_timestamp() AT TIME ZONE 'UTC'
          ) AT TIME ZONE 'UTC';
          current_day := date_trunc(
            'day', statement_timestamp() AT TIME ZONE 'UTC'
          ) AT TIME ZONE 'UTC';

          updated_budget := NULL;
          INSERT INTO public.childcare_command_reconciliation_budgets AS budget
            (organization_id, actor_user_id, window_kind, window_started_at, operation_count)
          VALUES
            (charged_organization_id, charged_actor_user_id, 'hour', current_hour, 1)
          ON CONFLICT (organization_id, actor_user_id, window_kind, window_started_at)
          DO UPDATE SET operation_count = budget.operation_count + 1
            WHERE budget.operation_count < 120
          RETURNING budget.operation_count INTO updated_budget;
          IF updated_budget IS NULL THEN
            RAISE EXCEPTION 'hourly childcare reconciliation budget exceeded'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_childcare_reconciliation_hour_limit';
          END IF;

          updated_budget := NULL;
          INSERT INTO public.childcare_command_reconciliation_budgets AS budget
            (organization_id, actor_user_id, window_kind, window_started_at, operation_count)
          VALUES
            (charged_organization_id, charged_actor_user_id, 'day', current_day, 1)
          ON CONFLICT (organization_id, actor_user_id, window_kind, window_started_at)
          DO UPDATE SET operation_count = budget.operation_count + 1
            WHERE budget.operation_count < 500
          RETURNING budget.operation_count INTO updated_budget;
          IF updated_budget IS NULL THEN
            RAISE EXCEPTION 'daily childcare reconciliation budget exceeded'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_childcare_reconciliation_day_limit';
          END IF;
        END
        $charge$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_charge_childcare_reconciliation(uuid, uuid, uuid) FROM PUBLIC"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_childcare_operation_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          desired_kind text;
          existing_kind text;
          existing_actor uuid;
          context_organization uuid;
          context_actor uuid;
          context_operation uuid;
        BEGIN
          IF TG_TABLE_NAME = 'childcare_command_receipts' THEN
            desired_kind := 'receipt';
          ELSIF TG_TABLE_NAME = 'childcare_command_claims' THEN
            desired_kind := 'absence_claim';
          ELSE
            RAISE EXCEPTION 'unsupported childcare operation ledger table'
              USING ERRCODE = '23514';
          END IF;

          IF session_user = 'caresync_basic_app' THEN
            context_organization := NULLIF(
              current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_actor := NULLIF(
              current_setting('app.current_user_id', true), ''
            )::uuid;
            context_operation := NULLIF(
              current_setting('app.current_childcare_operation_id', true), ''
            )::uuid;
            IF context_organization IS NULL OR context_actor IS NULL
               OR context_operation IS NULL
               OR NEW.organization_id <> context_organization
               OR NEW.actor_user_id <> context_actor
               OR NEW.client_operation_id <> context_operation THEN
              RAISE EXCEPTION 'childcare operation insert does not match locked context'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_childcare_operation_locked_context';
            END IF;
          END IF;

          IF desired_kind = 'absence_claim' THEN
            NEW.claimed_at := transaction_timestamp();
            PERFORM public.caresync_charge_childcare_reconciliation(
              NEW.organization_id, NEW.actor_user_id, NEW.client_operation_id
            );
          ELSE
            NEW.committed_at := transaction_timestamp();
          END IF;

          -- This shared unique row is the database serialization point across
          -- both ledgers. ON CONFLICT observes the winner even when the two
          -- outer INSERT statements began on older READ COMMITTED snapshots.
          INSERT INTO public.childcare_command_slots AS slot
            (organization_id, client_operation_id, entry_kind, actor_user_id)
          VALUES
            (NEW.organization_id, NEW.client_operation_id, desired_kind, NEW.actor_user_id)
          ON CONFLICT (organization_id, client_operation_id) DO UPDATE
            SET organization_id = EXCLUDED.organization_id
          RETURNING slot.entry_kind, slot.actor_user_id
            INTO existing_kind, existing_actor;

          IF existing_kind <> desired_kind OR existing_actor <> NEW.actor_user_id THEN
            RAISE EXCEPTION 'childcare operation already belongs to another terminal ledger'
              USING ERRCODE = '23505',
                    CONSTRAINT = 'uq_childcare_operation_terminal_slot';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.caresync_childcare_operation_guard() FROM PUBLIC")
    for table in ("childcare_command_receipts", "childcare_command_claims"):
        op.execute(
            f'CREATE TRIGGER "trg_{table}_operation_guard" '
            f'BEFORE INSERT ON public."{table}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_childcare_operation_guard()"
        )
    op.execute(
        """
        CREATE FUNCTION public.caresync_childcare_reconciliation_proof_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          context_organization uuid;
          context_actor uuid;
          context_operation uuid;
          terminal_kind text;
          terminal_actor uuid;
        BEGIN
          IF session_user = 'caresync_basic_app' THEN
            context_organization := NULLIF(
              current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_actor := NULLIF(
              current_setting('app.current_user_id', true), ''
            )::uuid;
            context_operation := NULLIF(
              current_setting('app.current_childcare_operation_id', true), ''
            )::uuid;
            IF context_organization IS NULL OR context_actor IS NULL
               OR context_operation IS NULL
               OR NEW.organization_id <> context_organization
               OR NEW.actor_user_id <> context_actor
               OR NEW.client_operation_id <> context_operation THEN
              RAISE EXCEPTION 'reconciliation proof does not match locked context'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'ck_childcare_reconciliation_proof_locked_context';
            END IF;
          END IF;
          SELECT slot.entry_kind, slot.actor_user_id
            INTO terminal_kind, terminal_actor
          FROM public.childcare_command_slots AS slot
          WHERE slot.organization_id = NEW.organization_id
            AND slot.client_operation_id = NEW.client_operation_id;
          IF terminal_kind IS NULL
             OR (terminal_kind = 'receipt' AND terminal_actor = NEW.actor_user_id) THEN
            RAISE EXCEPTION 'reconciliation proof has no actor-relative terminal authority'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_childcare_reconciliation_proof_terminal_authority';
          END IF;
          PERFORM public.caresync_charge_childcare_reconciliation(
            NEW.organization_id, NEW.actor_user_id, NEW.client_operation_id
          );
          NEW.finalized_at := transaction_timestamp();
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_childcare_reconciliation_proof_guard() FROM PUBLIC"
    )
    op.execute(
        'CREATE TRIGGER "trg_childcare_command_reconciliation_proofs_guard" '
        "BEFORE INSERT ON public.childcare_command_reconciliation_proofs FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_childcare_reconciliation_proof_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_childcare_immutable_ledger_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $guard$
        BEGIN
          IF session_user = 'caresync_basic_app' THEN
            RAISE EXCEPTION 'childcare command history is append-only'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_childcare_command_history_immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_childcare_immutable_ledger_guard() FROM PUBLIC"
    )
    for table in (
        "childcare_command_receipts",
        "childcare_command_claims",
        "childcare_command_reconciliation_proofs",
    ):
        op.execute(
            f'CREATE TRIGGER "trg_{table}_immutable" '
            f'BEFORE UPDATE OR DELETE ON public."{table}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_childcare_immutable_ledger_guard()"
        )
    op.execute(
        """
        CREATE FUNCTION public.caresync_childcare_contact_retirement_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          operation_setting text;
          operation_id uuid;
          actor_id uuid;
          receipt_matches boolean;
        BEGIN
          -- Migration/backup owners need to preserve or restore legacy rows.
          -- The writable Basic process is fail-closed to this one runtime role.
          IF session_user <> 'caresync_basic_app' THEN
            IF TG_OP = 'DELETE' THEN
              RETURN OLD;
            END IF;
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'childcare contact history cannot be deleted'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_childcare_contact_history_immutable';
          END IF;
          operation_setting := NULLIF(
            current_setting('app.current_childcare_operation_id', true), ''
          );
          IF operation_setting IS NULL THEN
            RAISE EXCEPTION 'childcare contact write requires a locked operation'
              USING ERRCODE = '23514';
          END IF;
          operation_id := operation_setting::uuid;
          actor_id := NULLIF(current_setting('app.current_user_id', true), '')::uuid;

          IF TG_OP = 'INSERT' THEN
            IF NEW.retired_at IS NOT NULL OR NEW.retired_operation_id IS NOT NULL THEN
              RAISE EXCEPTION 'new childcare contacts must begin current'
                USING ERRCODE = '23514';
            END IF;
            IF NEW.created_operation_id IS NULL
               OR NEW.created_operation_id <> operation_id THEN
              RAISE EXCEPTION 'childcare contact creation provenance does not match operation'
                USING ERRCODE = '23514';
            END IF;
            IF TG_TABLE_NAME = 'guardians' THEN
              SELECT EXISTS (
                SELECT 1 FROM public.childcare_command_receipts receipt
                WHERE receipt.organization_id = NEW.organization_id
                  AND receipt.client_operation_id = operation_id
                  AND receipt.actor_user_id = actor_id
                  AND receipt.xmin = pg_current_xact_id()::text::xid
                  AND receipt.target_type = 'family'
                  AND receipt.target_id = NEW.family_id
                  AND (
                    receipt.command_type = 'family.create'
                    OR (receipt.command_type = 'family.guardian.primary.replace'
                      AND NEW.is_primary)
                    OR (receipt.command_type = 'family.guardian.secondary.replace'
                      AND NOT NEW.is_primary)
                  )
              ) INTO receipt_matches;
            ELSE
              SELECT EXISTS (
                SELECT 1 FROM public.childcare_command_receipts receipt
                WHERE receipt.organization_id = NEW.organization_id
                  AND receipt.client_operation_id = operation_id
                  AND receipt.actor_user_id = actor_id
                  AND receipt.xmin = pg_current_xact_id()::text::xid
                  AND receipt.target_type = 'family'
                  AND receipt.target_id = NEW.family_id
                  AND receipt.command_type IN (
                    'family.create',
                    'family.emergency_contacts.replace'
                  )
              ) INTO receipt_matches;
            END IF;
            IF NOT receipt_matches THEN
              RAISE EXCEPTION 'childcare contact creation receipt does not match row'
                USING ERRCODE = '23514';
            END IF;
            NEW.created_at := statement_timestamp();
            NEW.updated_at := NEW.created_at;
            RETURN NEW;
          END IF;

          IF OLD.retired_at IS NOT NULL OR OLD.retired_operation_id IS NOT NULL THEN
            RAISE EXCEPTION 'retired childcare contact history is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.retired_at IS NULL OR NEW.retired_operation_id IS NULL THEN
            RAISE EXCEPTION 'childcare contacts may only transition from current to retired'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.retired_operation_id <> operation_id THEN
            RAISE EXCEPTION 'childcare contact retirement provenance does not match operation'
              USING ERRCODE = '23514';
          END IF;
          IF TG_TABLE_NAME = 'guardians' THEN
            SELECT EXISTS (
              SELECT 1 FROM public.childcare_command_receipts receipt
              WHERE receipt.organization_id = NEW.organization_id
                AND receipt.client_operation_id = operation_id
                AND receipt.actor_user_id = actor_id
                AND receipt.xmin = pg_current_xact_id()::text::xid
                AND receipt.target_type = 'family'
                AND receipt.target_id = NEW.family_id
                AND (
                  (receipt.command_type = 'family.guardian.primary.replace'
                    AND OLD.is_primary)
                  OR (receipt.command_type = 'family.guardian.secondary.replace'
                    AND NOT OLD.is_primary)
                )
            ) INTO receipt_matches;
          ELSE
            SELECT EXISTS (
              SELECT 1 FROM public.childcare_command_receipts receipt
              WHERE receipt.organization_id = NEW.organization_id
                AND receipt.client_operation_id = operation_id
                AND receipt.actor_user_id = actor_id
                AND receipt.xmin = pg_current_xact_id()::text::xid
                AND receipt.target_type = 'family'
                AND receipt.target_id = NEW.family_id
                AND receipt.command_type = 'family.emergency_contacts.replace'
            ) INTO receipt_matches;
          END IF;
          IF NOT receipt_matches THEN
            RAISE EXCEPTION 'childcare contact retirement receipt does not match row'
              USING ERRCODE = '23514';
          END IF;
          NEW.retired_at := statement_timestamp();
          NEW.updated_at := NEW.retired_at;
          IF NEW.retired_at < OLD.created_at THEN
            RAISE EXCEPTION 'childcare contact cannot retire before creation'
              USING ERRCODE = '23514';
          END IF;
          IF (to_jsonb(NEW) - ARRAY['retired_at', 'retired_operation_id', 'updated_at'])
             IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['retired_at', 'retired_operation_id', 'updated_at']) THEN
            RAISE EXCEPTION 'childcare contact facts and provenance are immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_childcare_contact_retirement_guard() FROM PUBLIC"
    )
    for table in ("guardians", "emergency_contacts"):
        op.execute(
            f'CREATE TRIGGER "trg_{table}_retirement_guard" '
            f'BEFORE INSERT OR UPDATE OR DELETE ON public."{table}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_childcare_contact_retirement_guard()"
        )
    op.execute("ALTER TABLE public.childcare_command_receipts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.childcare_command_receipts FORCE ROW LEVEL SECURITY")
    op.execute(
        'CREATE POLICY "childcare_command_receipts_tenant" '
        "ON public.childcare_command_receipts "
        f"USING (organization_id = {organization} "
        f"AND (actor_user_id = {actor} OR client_operation_id = {operation})) "
        f"WITH CHECK (organization_id = {organization} AND actor_user_id = {actor})"
    )
    op.execute("ALTER TABLE public.childcare_command_claims ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.childcare_command_claims FORCE ROW LEVEL SECURITY")
    op.execute(
        'CREATE POLICY "childcare_command_claims_tenant" '
        "ON public.childcare_command_claims "
        f"USING (organization_id = {organization} "
        f"AND (actor_user_id = {actor} OR client_operation_id = {operation})) "
        f"WITH CHECK (organization_id = {organization} AND actor_user_id = {actor})"
    )
    op.execute(
        "ALTER TABLE public.childcare_command_reconciliation_proofs ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE public.childcare_command_reconciliation_proofs FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        'CREATE POLICY "childcare_command_reconciliation_proofs_tenant" '
        "ON public.childcare_command_reconciliation_proofs "
        f"USING (organization_id = {organization} AND actor_user_id = {actor}) "
        f"WITH CHECK (organization_id = {organization} AND actor_user_id = {actor})"
    )
    for table in (
        "childcare_command_slots",
        "childcare_command_reconciliation_budget_entries",
        "childcare_command_reconciliation_budgets",
    ):
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table}_tenant" ON public."{table}" '
            f"USING (organization_id = {organization}) "
            f"WITH CHECK (organization_id = {organization})"
        )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT ON TABLE public.childcare_command_receipts
              TO caresync_basic_app;
            REVOKE UPDATE, DELETE ON TABLE public.childcare_command_receipts
              FROM caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE public.childcare_command_claims
              TO caresync_basic_app;
            REVOKE UPDATE, DELETE ON TABLE public.childcare_command_claims
              FROM caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE public.childcare_command_reconciliation_proofs
              TO caresync_basic_app;
            REVOKE UPDATE, DELETE ON TABLE public.childcare_command_reconciliation_proofs
              FROM caresync_basic_app;
            REVOKE ALL ON TABLE public.childcare_command_slots,
              public.childcare_command_reconciliation_budget_entries,
              public.childcare_command_reconciliation_budgets FROM caresync_basic_app;
            REVOKE UPDATE, DELETE ON TABLE public.guardians, public.emergency_contacts
              FROM caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE public.guardians, public.emergency_contacts
              TO caresync_basic_app;
            GRANT UPDATE (retired_at, retired_operation_id, updated_at)
              ON TABLE public.guardians, public.emergency_contacts TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    history_tables = (
        "childcare_command_receipts",
        "childcare_command_claims",
        "childcare_command_reconciliation_proofs",
        "childcare_command_slots",
        "childcare_command_reconciliation_budget_entries",
        "childcare_command_reconciliation_budgets",
        "guardians",
        "emergency_contacts",
    )
    _disable_rls_for_owner_visible_preflight(bind, history_tables)
    try:
        receipt_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_receipts")
        ).scalar_one()
        claim_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_claims")
        ).scalar_one()
        proof_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_reconciliation_proofs")
        ).scalar_one()
        slot_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_slots")
        ).scalar_one()
        budget_entry_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_reconciliation_budget_entries")
        ).scalar_one()
        budget_count = bind.execute(
            sa.text("SELECT count(*) FROM childcare_command_reconciliation_budgets")
        ).scalar_one()
        retired_guardian_count = bind.execute(
            sa.text("SELECT count(*) FROM guardians WHERE retired_at IS NOT NULL")
        ).scalar_one()
        retired_contact_count = bind.execute(
            sa.text("SELECT count(*) FROM emergency_contacts WHERE retired_at IS NOT NULL")
        ).scalar_one()
    finally:
        _restore_forced_rls(bind, history_tables)
    if (
        receipt_count
        or claim_count
        or proof_count
        or slot_count
        or budget_entry_count
        or budget_count
        or retired_guardian_count
        or retired_contact_count
    ):
        raise RuntimeError(
            "0028 downgrade refused because committed childcare command history "
            "cannot be represented by revision 0027: "
            f"receipts={receipt_count}, "
            f"absence_claims={claim_count}, "
            f"reconciliation_proofs={proof_count}, "
            f"operation_slots={slot_count}, "
            f"reconciliation_budget_entries={budget_entry_count}, "
            f"reconciliation_budgets={budget_count}, "
            f"retired_guardians={retired_guardian_count}, "
            f"retired_emergency_contacts={retired_contact_count}"
        )

    if bind.dialect.name == "postgresql":
        for table in (
            "childcare_command_receipts",
            "childcare_command_claims",
            "childcare_command_reconciliation_proofs",
        ):
            op.execute(f'DROP TRIGGER "trg_{table}_immutable" ON public."{table}"')
        op.execute("DROP FUNCTION public.caresync_childcare_immutable_ledger_guard()")
        op.execute(
            'DROP TRIGGER "trg_childcare_command_reconciliation_proofs_guard" '
            "ON public.childcare_command_reconciliation_proofs"
        )
        op.execute("DROP FUNCTION public.caresync_childcare_reconciliation_proof_guard()")
        op.execute(
            'DROP TRIGGER "trg_childcare_command_receipts_operation_guard" '
            "ON public.childcare_command_receipts"
        )
        op.execute(
            'DROP TRIGGER "trg_childcare_command_claims_operation_guard" '
            "ON public.childcare_command_claims"
        )
        op.execute("DROP FUNCTION public.caresync_childcare_operation_guard()")
        op.execute(
            "DROP FUNCTION public.caresync_charge_childcare_reconciliation(uuid, uuid, uuid)"
        )
        op.execute('DROP TRIGGER "trg_guardians_retirement_guard" ON public.guardians')
        op.execute(
            'DROP TRIGGER "trg_emergency_contacts_retirement_guard" ON public.emergency_contacts'
        )
        op.execute("DROP FUNCTION public.caresync_childcare_contact_retirement_guard()")

    # Remove provenance references before removing their receipt target.
    with op.batch_alter_table("guardians") as batch:
        batch.drop_constraint("fk_guardians_retired_operation", type_="foreignkey")
        batch.drop_constraint("fk_guardians_created_operation", type_="foreignkey")
    with op.batch_alter_table("emergency_contacts") as batch:
        batch.drop_constraint("fk_contacts_retired_operation", type_="foreignkey")
        batch.drop_constraint("fk_contacts_created_operation", type_="foreignkey")
    op.drop_table("childcare_command_claims")
    op.drop_table("childcare_command_receipts")
    op.drop_table("childcare_command_reconciliation_proofs")
    op.drop_table("childcare_command_reconciliation_budgets")
    op.drop_table("childcare_command_reconciliation_budget_entries")
    op.drop_table("childcare_command_slots")

    op.drop_index("ix_enrollments_open_room_interval", table_name="enrollments")
    op.drop_index("uq_enrollments_one_open_org_child", table_name="enrollments")
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_constraint("fk_enrollments_facility_program_room", type_="foreignkey")
        batch.drop_constraint("fk_enrollments_facility_program", type_="foreignkey")
        batch.drop_constraint("ck_enrollment_pending_unassigned", type_="check")
        batch.drop_constraint("ck_enrollment_placement_pair", type_="check")
        batch.drop_constraint("ck_enrollments_version", type_="check")
        batch.alter_column(
            "status",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=None,
        )
        batch.drop_column("placement_effective_date")
        batch.drop_column("version")

    op.drop_index("ix_contacts_current_family", table_name="emergency_contacts")
    op.drop_index("ix_emergency_contacts_retired_at", table_name="emergency_contacts")
    with op.batch_alter_table("emergency_contacts") as batch:
        batch.drop_constraint("ck_contacts_retirement_pair", type_="check")
        batch.drop_column("retired_at")
        batch.drop_column("retired_operation_id")
        batch.drop_column("created_operation_id")

    op.drop_index("uq_guardians_current_primary_slot", table_name="guardians")
    op.drop_index("ix_guardians_retired_at", table_name="guardians")
    with op.batch_alter_table("guardians") as batch:
        batch.drop_constraint("ck_guardians_retirement_pair", type_="check")
        batch.drop_column("retired_at")
        batch.drop_column("retired_operation_id")
        batch.drop_column("created_operation_id")

    with op.batch_alter_table("children") as batch:
        batch.drop_constraint("ck_children_version", type_="check")
        batch.drop_column("version")
    with op.batch_alter_table("families") as batch:
        batch.drop_constraint("ck_families_version", type_="check")
        batch.drop_column("version")

    with op.batch_alter_table("rooms") as batch:
        batch.drop_constraint("uq_rooms_org_facility_program_id", type_="unique")
    with op.batch_alter_table("facility_programs") as batch:
        batch.drop_constraint("uq_programs_org_facility_id", type_="unique")

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $grant$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
                GRANT SELECT, INSERT, UPDATE ON TABLE public.guardians,
                  public.emergency_contacts
                  TO caresync_basic_app;
              END IF;
            END $grant$
            """
        )

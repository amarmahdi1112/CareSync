"""Reserve immutable facts for normal verified release checkout.

Revision ID: 0029C_verified_release_checkout
Revises: 0029B_release_context
Create Date: 2026-07-18

This is a dormant data foundation.  It adds no checkout command, activation
route, runtime table write, or retained-database cutover.  The unsupported
secondary-check policy remains impossible to commit as a release snapshot.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "0029C_verified_release_checkout"
down_revision = "0029B_release_context"
branch_labels = None
depends_on = None


SYSTEM_RELEASE_ROLE_KEYS = ("owner", "administrator", "educator")
CHECKOUT_PERMISSION = "release:checkout"
ACTIVATION_POLICY_VERSION = "normal_verified_release_v1"


def _permission_list(raw: Any) -> list[str]:
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise RuntimeError("0029C refused malformed system-role permissions")
    return decoded


def _set_system_checkout_permission(*, enabled: bool) -> None:
    """Append/remove only release:checkout on the three system templates."""

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, permissions FROM roles "
            "WHERE is_system = :is_system AND key IN "
            "('owner','administrator','educator') ORDER BY id"
        ),
        {"is_system": True},
    ).mappings()
    for row in rows:
        permissions = _permission_list(row["permissions"])
        if enabled:
            updated = (
                permissions
                if CHECKOUT_PERMISSION in permissions
                else [
                    *permissions,
                    CHECKOUT_PERMISSION,
                ]
            )
        else:
            updated = [item for item in permissions if item != CHECKOUT_PERMISSION]
        if updated == permissions:
            continue
        bind.execute(
            sa.text("UPDATE roles SET permissions = :permissions WHERE id = :role_id"),
            {
                "permissions": json.dumps(updated, separators=(",", ":")),
                "role_id": row["id"],
            },
        )


def _release_history_counts() -> tuple[int, int, int]:
    bind = op.get_bind()
    snapshot_count = int(
        bind.execute(sa.text("SELECT count(*) FROM attendance_release_snapshots")).scalar_one()
    )
    activation_count = 0
    inspector = sa.inspect(bind)
    if "facility_release_checkout_activations" in inspector.get_table_names():
        activation_count = int(
            bind.execute(
                sa.text("SELECT count(*) FROM facility_release_checkout_activations")
            ).scalar_one()
        )
    receipt_count = int(
        bind.execute(
            sa.text(
                "SELECT count(*) FROM childcare_command_receipts "
                "WHERE target_type IN ('release_activation','attendance_release') "
                "OR command_type IN "
                "('facility.release_checkout.activate','attendance.release.checkout')"
            )
        ).scalar_one()
    )
    return activation_count, snapshot_count, receipt_count


def _preflight_empty_snapshot_upgrade() -> None:
    """B has no writer; refuse rather than fabricate new immutable facts."""

    _, snapshot_count, _ = _release_history_counts()
    if snapshot_count:
        raise RuntimeError(
            "0029C upgrade refused before DDL because dormant B contains release "
            f"snapshot history that cannot be given exact C facts: snapshots={snapshot_count}"
        )


def _preflight_empty_release_history_downgrade() -> None:
    activation_count, snapshot_count, receipt_count = _release_history_counts()
    if activation_count or snapshot_count or receipt_count:
        raise RuntimeError(
            "0029C downgrade refused before DDL because immutable activation or "
            "release history exists: "
            f"activations={activation_count}, snapshots={snapshot_count}, "
            f"receipts={receipt_count}"
        )


def _refuse_unsafe_sqlite_multirevision_downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    destination_revision = context.get_revision_argument()
    if destination_revision not in {down_revision, "-1"}:
        raise RuntimeError(
            "0029C SQLite downgrade refused before DDL: first downgrade exactly "
            "to 0029B_release_context, then start a separate downgrade command"
        )


def _create_activation_table() -> None:
    op.create_table(
        "facility_release_checkout_activations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by_role_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by_role_key", sa.String(length=50), nullable=False),
        sa.Column("activation_operation_id", sa.Uuid(), nullable=False),
        sa.Column("activation_policy_version", sa.String(length=40), nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "activated_by_role_key IN ('owner','administrator')",
            name="ck_release_checkout_activations_privileged_role",
        ),
        sa.CheckConstraint(
            f"activation_policy_version = '{ACTIVATION_POLICY_VERSION}'",
            name="ck_release_checkout_activations_policy_version",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "activation_operation_id"],
            [
                "childcare_command_receipts.organization_id",
                "childcare_command_receipts.client_operation_id",
            ],
            name="fk_release_checkout_activations_operation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "facility_id"],
            ["facilities.organization_id", "facilities.id"],
            name="fk_release_checkout_activations_facility",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "activated_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_release_checkout_activations_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "activated_by_role_id"],
            ["roles.organization_id", "roles.id"],
            name="fk_release_checkout_activations_role",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_release_checkout_activations_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            name="uq_release_checkout_activations_facility",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "activation_operation_id",
            name="uq_release_checkout_activations_operation",
        ),
    )
    op.create_index(
        op.f("ix_facility_release_checkout_activations_organization_id"),
        "facility_release_checkout_activations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_facility_release_checkout_activations_facility_id"),
        "facility_release_checkout_activations",
        ["facility_id"],
        unique=False,
    )


def _set_receipt_target_vocabulary(*, checkout_foundation: bool) -> None:
    with op.batch_alter_table("childcare_command_receipts") as batch:
        batch.drop_constraint("ck_childcare_command_receipts_target", type_="check")
        target_values = (
            "'family','child','enrollment','authority_person','authority_evidence',"
            "'authority_evidence_object','release_authorization','release_rule',"
            "'consent','attendance_release'"
        )
        if checkout_foundation:
            target_values = (
                "'family','child','enrollment','authority_person','authority_evidence',"
                "'authority_evidence_object','release_authorization','release_rule',"
                "'consent','release_activation','attendance_release'"
            )
        batch.create_check_constraint(
            "ck_childcare_command_receipts_target",
            f"target_type IN ({target_values})",
        )


def _install_activation_immutability() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION public.caresync_release_checkout_activation_immutable()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $guard$
            BEGIN
              RAISE EXCEPTION 'release checkout activation is immutable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_checkout_activation_immutable';
            END
            $guard$
            """
        )
        op.execute(
            "REVOKE ALL ON FUNCTION "
            "public.caresync_release_checkout_activation_immutable() FROM PUBLIC"
        )
        op.execute(
            "CREATE TRIGGER facility_release_checkout_activations_immutable "
            "BEFORE UPDATE OR DELETE ON public.facility_release_checkout_activations "
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_release_checkout_activation_immutable()"
        )
        op.execute(
            "ALTER TABLE public.facility_release_checkout_activations ENABLE ROW LEVEL SECURITY"
        )
        op.execute(
            "ALTER TABLE public.facility_release_checkout_activations FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            "CREATE POLICY facility_release_checkout_activations_privileged_actor "
            "ON public.facility_release_checkout_activations "
            "USING (public.caresync_family_authority_actor_is_privileged(organization_id)) "
            "WITH CHECK "
            "(public.caresync_family_authority_actor_is_privileged(organization_id))"
        )
        op.execute(
            """
            DO $revoke$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app'
              ) THEN
                REVOKE ALL ON TABLE
                  public.facility_release_checkout_activations
                FROM caresync_basic_app;
              END IF;
            END
            $revoke$
            """
        )
        return

    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"""
            CREATE TRIGGER facility_release_checkout_activations_no_{operation.lower()}
            BEFORE {operation} ON facility_release_checkout_activations
            BEGIN
              SELECT RAISE(ABORT, 'release checkout activation is immutable');
            END
            """
        )


def _drop_activation_immutability() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER facility_release_checkout_activations_immutable "
            "ON public.facility_release_checkout_activations"
        )
        op.execute("DROP FUNCTION public.caresync_release_checkout_activation_immutable()")
        return
    op.execute("DROP TRIGGER facility_release_checkout_activations_no_update")
    op.execute("DROP TRIGGER facility_release_checkout_activations_no_delete")


def _install_snapshot_immutability() -> None:
    """Make the committed release record append-only on every supported dialect."""

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION public.caresync_release_snapshot_immutable()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $guard$
            BEGIN
              RAISE EXCEPTION 'attendance release snapshot is immutable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_snapshot_immutable';
            END
            $guard$
            """
        )
        op.execute(
            "REVOKE ALL ON FUNCTION public.caresync_release_snapshot_immutable() FROM PUBLIC"
        )
        op.execute(
            "CREATE TRIGGER attendance_release_snapshots_immutable "
            "BEFORE UPDATE OR DELETE ON public.attendance_release_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_release_snapshot_immutable()"
        )
        return

    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"""
            CREATE TRIGGER attendance_release_snapshots_no_{operation.lower()}
            BEFORE {operation} ON attendance_release_snapshots
            BEGIN
              SELECT RAISE(ABORT, 'attendance release snapshot is immutable');
            END
            """
        )


def _drop_snapshot_immutability() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER attendance_release_snapshots_immutable "
            "ON public.attendance_release_snapshots"
        )
        op.execute("DROP FUNCTION public.caresync_release_snapshot_immutable()")
        return
    op.execute("DROP TRIGGER attendance_release_snapshots_no_update")
    op.execute("DROP TRIGGER attendance_release_snapshots_no_delete")


def _install_relational_consistency_guards() -> None:
    """Reject release facts whose duplicated identities disagree at insertion."""

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION public.caresync_release_checkout_activation_insert_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $guard$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM public.organization_memberships AS membership
                JOIN public.roles AS actor_role
                  ON actor_role.organization_id = membership.organization_id
                 AND actor_role.id = membership.role_id
                JOIN public.childcare_command_receipts AS receipt
                  ON receipt.organization_id = NEW.organization_id
                 AND receipt.client_operation_id = NEW.activation_operation_id
                WHERE membership.organization_id = NEW.organization_id
                  AND membership.id = NEW.activated_by_membership_id
                  AND membership.user_id = NEW.activated_by_user_id
                  AND membership.role_id = NEW.activated_by_role_id
                  AND membership.status = 'active'
                  AND actor_role.organization_id = NEW.organization_id
                  AND actor_role.id = NEW.activated_by_role_id
                  AND actor_role.key = NEW.activated_by_role_key
                  AND receipt.command_type = 'facility.release_checkout.activate'
                  AND receipt.target_type = 'release_activation'
                  AND receipt.target_id = NEW.id
                  AND receipt.actor_user_id = NEW.activated_by_user_id
                  AND receipt.facility_id = NEW.facility_id
                  AND receipt.committed_version = 1
              ) THEN
                RAISE EXCEPTION 'release checkout activation relational consistency failed'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_checkout_activation_relational_consistency';
              END IF;
              RETURN NEW;
            END
            $guard$
            """
        )
        op.execute(
            "REVOKE ALL ON FUNCTION "
            "public.caresync_release_checkout_activation_insert_guard() FROM PUBLIC"
        )
        op.execute(
            "CREATE TRIGGER facility_release_checkout_activations_insert_guard "
            "BEFORE INSERT ON public.facility_release_checkout_activations "
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_release_checkout_activation_insert_guard()"
        )
        op.execute(
            """
            CREATE FUNCTION public.caresync_release_snapshot_insert_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $guard$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM public.organization_memberships AS membership
                JOIN public.roles AS actor_role
                  ON actor_role.organization_id = membership.organization_id
                 AND actor_role.id = membership.role_id
                JOIN public.staff_shifts AS staff_shift
                  ON staff_shift.organization_id = NEW.organization_id
                 AND staff_shift.id = NEW.staff_shift_id
                JOIN public.childcare_command_receipts AS receipt
                  ON receipt.organization_id = NEW.organization_id
                 AND receipt.client_operation_id = NEW.client_operation_id
                JOIN public.attendance_events AS checkout_event
                  ON checkout_event.organization_id = NEW.organization_id
                 AND checkout_event.id = NEW.checkout_event_id
                WHERE membership.organization_id = NEW.organization_id
                  AND membership.id = NEW.actor_membership_id
                  AND membership.user_id = NEW.actor_user_id
                  AND membership.role_id = NEW.actor_role_id
                  AND membership.status = 'active'
                  AND actor_role.organization_id = NEW.organization_id
                  AND actor_role.id = NEW.actor_role_id
                  AND actor_role.key = NEW.actor_role_key
                  AND staff_shift.membership_id = NEW.actor_membership_id
                  AND staff_shift.facility_id = NEW.facility_id
                  AND receipt.command_type = 'attendance.release.checkout'
                  AND receipt.target_type = 'attendance_release'
                  AND receipt.target_id = NEW.id
                  AND receipt.actor_user_id = NEW.actor_user_id
                  AND receipt.facility_id = NEW.facility_id
                  AND receipt.request_hash = NEW.request_hash
                  AND receipt.committed_at = NEW.committed_at
                  AND receipt.committed_version = 1
                  AND checkout_event.attendance_day_id = NEW.attendance_day_id
                  AND checkout_event.client_operation_id = NEW.client_operation_id
                  AND checkout_event.actor_user_id = NEW.actor_user_id
                  AND checkout_event.occurred_at = NEW.checked_out_at
                  AND checkout_event.event_type = 'check_out'
                  AND (
                    NEW.room_assignment_id IS NULL
                    OR EXISTS (
                      SELECT 1
                      FROM public.membership_room_assignments AS room_assignment
                      WHERE room_assignment.organization_id = NEW.organization_id
                        AND room_assignment.id = NEW.room_assignment_id
                        AND room_assignment.membership_id = NEW.actor_membership_id
                        AND room_assignment.facility_id = NEW.facility_id
                        AND room_assignment.room_id = NEW.room_id
                    )
                  )
              ) THEN
                RAISE EXCEPTION 'attendance release snapshot relational consistency failed'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_snapshot_relational_consistency';
              END IF;
              RETURN NEW;
            END
            $guard$
            """
        )
        op.execute(
            "REVOKE ALL ON FUNCTION public.caresync_release_snapshot_insert_guard() FROM PUBLIC"
        )
        # PostgreSQL orders same-event triggers by name.  The zz name deliberately
        # follows 0029A's trigger, which canonicalizes committed_at.
        op.execute(
            "CREATE TRIGGER zz_attendance_release_snapshots_insert_guard "
            "BEFORE INSERT ON public.attendance_release_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_release_snapshot_insert_guard()"
        )
        return

    op.execute(
        """
        CREATE TRIGGER facility_release_checkout_activations_insert_guard
        BEFORE INSERT ON facility_release_checkout_activations
        WHEN NOT EXISTS (
          SELECT 1
          FROM organization_memberships AS membership
          JOIN roles AS actor_role
            ON actor_role.organization_id = membership.organization_id
           AND actor_role.id = membership.role_id
          JOIN childcare_command_receipts AS receipt
            ON receipt.organization_id = NEW.organization_id
           AND receipt.client_operation_id = NEW.activation_operation_id
          WHERE membership.organization_id = NEW.organization_id
            AND membership.id = NEW.activated_by_membership_id
            AND membership.user_id = NEW.activated_by_user_id
            AND membership.role_id = NEW.activated_by_role_id
            AND membership.status = 'active'
            AND actor_role.organization_id = NEW.organization_id
            AND actor_role.id = NEW.activated_by_role_id
            AND actor_role.key = NEW.activated_by_role_key
            AND receipt.command_type = 'facility.release_checkout.activate'
            AND receipt.target_type = 'release_activation'
            AND receipt.target_id = NEW.id
            AND receipt.actor_user_id = NEW.activated_by_user_id
            AND receipt.facility_id = NEW.facility_id
            AND receipt.committed_version = 1
        )
        BEGIN
          SELECT RAISE(
            ABORT,
            'release checkout activation relational consistency failed'
          );
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER attendance_release_snapshots_insert_guard
        BEFORE INSERT ON attendance_release_snapshots
        WHEN NOT EXISTS (
          SELECT 1
          FROM organization_memberships AS membership
          JOIN roles AS actor_role
            ON actor_role.organization_id = membership.organization_id
           AND actor_role.id = membership.role_id
          JOIN staff_shifts AS staff_shift
            ON staff_shift.organization_id = NEW.organization_id
           AND staff_shift.id = NEW.staff_shift_id
          JOIN childcare_command_receipts AS receipt
            ON receipt.organization_id = NEW.organization_id
           AND receipt.client_operation_id = NEW.client_operation_id
          JOIN attendance_events AS checkout_event
            ON checkout_event.organization_id = NEW.organization_id
           AND checkout_event.id = NEW.checkout_event_id
          WHERE membership.organization_id = NEW.organization_id
            AND membership.id = NEW.actor_membership_id
            AND membership.user_id = NEW.actor_user_id
            AND membership.role_id = NEW.actor_role_id
            AND membership.status = 'active'
            AND actor_role.organization_id = NEW.organization_id
            AND actor_role.id = NEW.actor_role_id
            AND actor_role.key = NEW.actor_role_key
            AND staff_shift.membership_id = NEW.actor_membership_id
            AND staff_shift.facility_id = NEW.facility_id
            AND receipt.command_type = 'attendance.release.checkout'
            AND receipt.target_type = 'attendance_release'
            AND receipt.target_id = NEW.id
            AND receipt.actor_user_id = NEW.actor_user_id
            AND receipt.facility_id = NEW.facility_id
            AND receipt.request_hash = NEW.request_hash
            AND receipt.committed_at = NEW.committed_at
            AND receipt.committed_version = 1
            AND checkout_event.attendance_day_id = NEW.attendance_day_id
            AND checkout_event.client_operation_id = NEW.client_operation_id
            AND checkout_event.actor_user_id = NEW.actor_user_id
            AND checkout_event.occurred_at = NEW.checked_out_at
            AND checkout_event.event_type = 'check_out'
            AND (
              NEW.room_assignment_id IS NULL
              OR EXISTS (
                SELECT 1
                FROM membership_room_assignments AS room_assignment
                WHERE room_assignment.organization_id = NEW.organization_id
                  AND room_assignment.id = NEW.room_assignment_id
                  AND room_assignment.membership_id = NEW.actor_membership_id
                  AND room_assignment.facility_id = NEW.facility_id
                  AND room_assignment.room_id = NEW.room_id
              )
            )
        )
        BEGIN
          SELECT RAISE(
            ABORT,
            'attendance release snapshot relational consistency failed'
          );
        END
        """
    )


def _drop_relational_consistency_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER zz_attendance_release_snapshots_insert_guard "
            "ON public.attendance_release_snapshots"
        )
        op.execute("DROP FUNCTION public.caresync_release_snapshot_insert_guard()")
        op.execute(
            "DROP TRIGGER facility_release_checkout_activations_insert_guard "
            "ON public.facility_release_checkout_activations"
        )
        op.execute("DROP FUNCTION public.caresync_release_checkout_activation_insert_guard()")
        return
    op.execute("DROP TRIGGER attendance_release_snapshots_insert_guard")
    op.execute("DROP TRIGGER facility_release_checkout_activations_insert_guard")


def _upgrade_snapshot_shape() -> None:
    with op.batch_alter_table("attendance_release_snapshots") as batch:
        batch.alter_column(
            "recipient_display_name",
            existing_type=sa.String(length=240),
            type_=sa.String(length=302),
            existing_nullable=False,
        )
        batch.add_column(sa.Column("attendance_day_version", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("verification_policy_code", sa.String(64), nullable=False))
        batch.add_column(sa.Column("actor_membership_id", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("actor_role_id", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("actor_role_key", sa.String(50), nullable=False))
        batch.add_column(sa.Column("staff_shift_id", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("room_id", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("scope_basis", sa.String(32), nullable=False))
        batch.add_column(sa.Column("room_assignment_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=False))
        batch.create_foreign_key(
            "fk_release_snapshots_actor_membership_id",
            "organization_memberships",
            ["organization_id", "actor_membership_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_release_snapshots_actor_role",
            "roles",
            ["organization_id", "actor_role_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_release_snapshots_staff_shift",
            "staff_shifts",
            ["organization_id", "staff_shift_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_release_snapshots_room",
            "rooms",
            ["organization_id", "facility_id", "room_id"],
            ["organization_id", "facility_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_release_snapshots_room_assignment",
            "membership_room_assignments",
            ["organization_id", "room_assignment_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_release_snapshots_attendance_day_version",
            "attendance_day_version >= 1",
        )
        batch.create_check_constraint(
            "ck_release_snapshots_scope_basis",
            "scope_basis IN ('organization_role','room_assignment') AND "
            "((scope_basis = 'organization_role' AND room_assignment_id IS NULL) OR "
            "(scope_basis = 'room_assignment' AND room_assignment_id IS NOT NULL))",
        )
        batch.create_check_constraint(
            "ck_release_snapshots_executable_verification_policy",
            "(verification_policy_code = 'government_photo_id' "
            "AND verification_method = 'government_photo_id' "
            "AND verification_result = 'verified') OR "
            "(verification_policy_code = 'documented_familiarity' "
            "AND verification_method = 'documented_familiarity' "
            "AND verification_result = 'documented_familiarity') OR "
            "(verification_policy_code = "
            "'government_photo_id_or_documented_familiarity' AND "
            "((verification_method = 'government_photo_id' "
            "AND verification_result = 'verified') OR "
            "(verification_method = 'documented_familiarity' "
            "AND verification_result = 'documented_familiarity')))",
        )
        batch.create_check_constraint(
            "ck_release_snapshots_checkout_time_order",
            "checked_out_at >= requested_at AND committed_at = checked_out_at",
        )
        batch.create_check_constraint(
            "ck_release_snapshots_decision_policy_version",
            "decision_policy_version = 'release-context-v1'",
        )


def _downgrade_snapshot_shape() -> None:
    with op.batch_alter_table("attendance_release_snapshots") as batch:
        batch.drop_constraint("ck_release_snapshots_checkout_time_order", type_="check")
        batch.drop_constraint("ck_release_snapshots_decision_policy_version", type_="check")
        batch.drop_constraint("ck_release_snapshots_executable_verification_policy", type_="check")
        batch.drop_constraint("ck_release_snapshots_scope_basis", type_="check")
        batch.drop_constraint("ck_release_snapshots_attendance_day_version", type_="check")
        batch.drop_constraint("fk_release_snapshots_room_assignment", type_="foreignkey")
        batch.drop_constraint("fk_release_snapshots_room", type_="foreignkey")
        batch.drop_constraint("fk_release_snapshots_staff_shift", type_="foreignkey")
        batch.drop_constraint("fk_release_snapshots_actor_role", type_="foreignkey")
        batch.drop_constraint("fk_release_snapshots_actor_membership_id", type_="foreignkey")
        batch.drop_column("checked_out_at")
        batch.drop_column("room_assignment_id")
        batch.drop_column("scope_basis")
        batch.drop_column("room_id")
        batch.drop_column("staff_shift_id")
        batch.drop_column("actor_role_key")
        batch.drop_column("actor_role_id")
        batch.drop_column("actor_membership_id")
        batch.drop_column("verification_policy_code")
        batch.drop_column("attendance_day_version")
        batch.alter_column(
            "recipient_display_name",
            existing_type=sa.String(length=302),
            type_=sa.String(length=240),
            existing_nullable=False,
        )


def upgrade() -> None:
    _preflight_empty_snapshot_upgrade()
    _set_receipt_target_vocabulary(checkout_foundation=True)
    _create_activation_table()
    _install_activation_immutability()
    _upgrade_snapshot_shape()
    _install_snapshot_immutability()
    _install_relational_consistency_guards()
    _set_system_checkout_permission(enabled=True)


def downgrade() -> None:
    _refuse_unsafe_sqlite_multirevision_downgrade()
    _preflight_empty_release_history_downgrade()
    _set_system_checkout_permission(enabled=False)
    _drop_relational_consistency_guards()
    _drop_snapshot_immutability()
    _downgrade_snapshot_shape()
    _drop_activation_immutability()
    op.drop_index(
        op.f("ix_facility_release_checkout_activations_facility_id"),
        table_name="facility_release_checkout_activations",
    )
    op.drop_index(
        op.f("ix_facility_release_checkout_activations_organization_id"),
        table_name="facility_release_checkout_activations",
    )
    op.drop_table("facility_release_checkout_activations")
    _set_receipt_target_vocabulary(checkout_foundation=False)

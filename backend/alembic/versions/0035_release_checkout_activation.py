"""Add the explicit owner/administrator facility release activation command.

Revision ID: 0035_release_checkout_activation
Revises: 0034_transport_role_permissions
Create Date: 2026-07-22

The 0029C activation record remains immutable and the runtime role retains no
direct table authority. This revision adds one narrow SECURITY DEFINER writer
that derives the current actor, organization, membership and role from the
transaction-local authenticated context, verifies the exact command receipt,
rechecks facility and authority-record readiness, and inserts one activation.
It never updates, deletes, deactivates or automatically activates a facility.
"""

from __future__ import annotations

from alembic import op

revision = "0035_release_checkout_activation"
down_revision = "0034_transport_role_permissions"
branch_labels = None
depends_on = None

ACTIVATION_FUNCTION = (
    "public.caresync_release_checkout_activate_facility("
    "uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)"
)


def _install_postgres_writer() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_release_checkout_activate_facility(
          requested_facility_id uuid,
          requested_activation_id uuid,
          requested_operation_id uuid,
          requested_request_hash text,
          requested_policy_version text,
          requested_confirmation_text text,
          authority_records_reviewed boolean,
          verification_workflow_reviewed boolean,
          legacy_checkout_closure_understood boolean,
          irreversible_activation_understood boolean
        )
        RETURNS timestamp with time zone
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $activation$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
          actor_membership_id uuid;
          actor_role_id uuid;
          actor_role_key text;
          receipt_committed_at timestamp with time zone;
        BEGIN
          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'release_activation_forbidden'
              USING ERRCODE='42501';
          END;

          IF context_organization_id IS NULL
             OR context_user_id IS NULL
             OR requested_facility_id IS NULL
             OR requested_activation_id IS NULL
             OR requested_operation_id IS NULL
             OR requested_request_hash IS NULL
             OR requested_request_hash !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'release_activation_forbidden'
              USING ERRCODE='42501';
          END IF;

          IF requested_policy_version <> 'normal_verified_release_v1'
             OR requested_confirmation_text <> 'ACTIVATE VERIFIED RELEASE CHECKOUT'
             OR authority_records_reviewed IS DISTINCT FROM true
             OR verification_workflow_reviewed IS DISTINCT FROM true
             OR legacy_checkout_closure_understood IS DISTINCT FROM true
             OR irreversible_activation_understood IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'release_activation_confirmation_required'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_activation_explicit_confirmation';
          END IF;

          SELECT membership.id, actor_role.id, actor_role.key,
                 receipt.committed_at
          INTO actor_membership_id, actor_role_id, actor_role_key,
               receipt_committed_at
          FROM public.users AS actor
          JOIN public.organization_memberships AS membership
            ON membership.user_id=actor.id
           AND membership.organization_id=context_organization_id
           AND membership.status='active'
          JOIN public.roles AS actor_role
            ON actor_role.organization_id=membership.organization_id
           AND actor_role.id=membership.role_id
           AND actor_role.key IN ('owner','administrator')
          JOIN public.organizations AS organization_record
            ON organization_record.id=membership.organization_id
           AND organization_record.status='active'
          JOIN public.facilities AS facility
            ON facility.organization_id=membership.organization_id
           AND facility.id=requested_facility_id
           AND facility.status='active'
          JOIN public.childcare_command_receipts AS receipt
            ON receipt.organization_id=membership.organization_id
           AND receipt.client_operation_id=requested_operation_id
           AND receipt.command_type='facility.release_checkout.activate'
           AND receipt.target_type='release_activation'
           AND receipt.target_id=requested_activation_id
           AND receipt.request_hash=requested_request_hash
           AND receipt.actor_user_id=actor.id
           AND receipt.facility_id=facility.id
           AND receipt.committed_version=1
          WHERE actor.id=context_user_id
            AND actor.is_active=true
            AND actor.email_verified_at IS NOT NULL
          FOR SHARE OF actor, membership, actor_role, organization_record,
                       facility, receipt;

          IF NOT FOUND THEN
            RAISE EXCEPTION 'release_activation_forbidden'
              USING ERRCODE='42501';
          END IF;

          PERFORM 1
          FROM public.facility_release_checkout_activations AS activation
          WHERE activation.organization_id=context_organization_id
            AND activation.facility_id=requested_facility_id;
          IF FOUND THEN
            RAISE EXCEPTION 'release_activation_already_active'
              USING ERRCODE='23505',
                    CONSTRAINT='uq_release_checkout_activations_facility';
          END IF;

          IF EXISTS (
            SELECT 1
            FROM public.enrollments AS enrollment
            WHERE enrollment.organization_id=context_organization_id
              AND enrollment.facility_id=requested_facility_id
              AND enrollment.status IN ('active','paused')
              AND NOT EXISTS (
                SELECT 1
                FROM public.child_release_authorizations AS release_auth
                WHERE release_auth.organization_id=enrollment.organization_id
                  AND release_auth.child_id=enrollment.child_id
                  AND release_auth.revoked_at IS NULL
                  AND release_auth.effective_from <=
                      pg_catalog.transaction_timestamp()
                  AND release_auth.effective_until >
                      pg_catalog.transaction_timestamp()
                  AND release_auth.verification_policy_code IN (
                    'government_photo_id',
                    'documented_familiarity',
                    'government_photo_id_or_documented_familiarity'
                  )
              )
          ) THEN
            RAISE EXCEPTION 'release_activation_authority_records_incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_activation_authority_readiness';
          END IF;

          INSERT INTO public.facility_release_checkout_activations (
            id,
            organization_id,
            facility_id,
            activated_by_user_id,
            activated_by_membership_id,
            activated_by_role_id,
            activated_by_role_key,
            activation_operation_id,
            activation_policy_version,
            activated_at
          ) VALUES (
            requested_activation_id,
            context_organization_id,
            requested_facility_id,
            context_user_id,
            actor_membership_id,
            actor_role_id,
            actor_role_key,
            requested_operation_id,
            requested_policy_version,
            receipt_committed_at
          );

          RETURN receipt_committed_at;
        END
        $activation$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {ACTIVATION_FUNCTION} FROM PUBLIC")
    op.execute(
        f"""
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION {ACTIVATION_FUNCTION}
            TO caresync_basic_app;
          END IF;
        END
        $grant$
        """
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _install_postgres_writer()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP FUNCTION {ACTIVATION_FUNCTION}")

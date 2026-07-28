"""Install the restricted PostgreSQL normal-release checkout writer.

Revision ID: 0029D_release_checkout_writer
Revises: 0029C_verified_release_checkout
Create Date: 2026-07-18

The writer is deliberately PostgreSQL-only.  SQLite keeps the portable C
foundation for contract tests, but never advertises a production checkout
runtime.  PostgreSQL receives four narrow runtime-callable functions and two
trigger-only guards; the application role still has no direct write
authority over activation or immutable release snapshots.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029D_release_checkout_writer"
down_revision = "0029C_verified_release_checkout"
branch_labels = None
depends_on = None


ACTIVATION_FUNCTION = "public.caresync_release_checkout_activation_enabled(uuid)"
REPLAY_FUNCTION = "public.caresync_release_checkout_replay(uuid)"
WRITER_CONTEXT_FUNCTION = (
    "public.caresync_family_release_context_inputs_at("
    "uuid,uuid,timestamp with time zone)"
)
INSERT_FUNCTION = (
    "public.caresync_release_checkout_insert_snapshot("
    "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
    "integer,integer,text,text,text,text,timestamp with time zone,"
    "timestamp with time zone,text)"
)
INTERVAL_GUARD_FUNCTION = "public.caresync_attendance_interval_verified_release_guard()"
SNAPSHOT_TIME_GUARD_FUNCTION = "public.caresync_release_snapshot_commit_time_guard()"


def _install_writer_context_projection() -> None:
    """Clone B's hardened projection with one explicit post-lock instant."""

    bind = op.get_bind()
    source = bind.execute(
        sa.text(
            "SELECT procedure.prosrc FROM pg_catalog.pg_proc AS procedure "
            "WHERE procedure.oid=pg_catalog.to_regprocedure("
            "'public.caresync_family_release_context_inputs(uuid,uuid)')"
        )
    ).scalar_one_or_none()
    clock = "evaluated_at_value timestamptz := pg_catalog.statement_timestamp();"
    if source is None or str(source).count(clock) != 1:
        raise RuntimeError("0029D requires the exact 0029B release-context projection")
    writer_source = str(source).replace(
        clock,
        "evaluated_at_value timestamptz := requested_evaluated_at;",
    )
    op.execute(
        "CREATE FUNCTION public.caresync_family_release_context_inputs_at("
        "requested_child_id uuid,requested_facility_id uuid,"
        "requested_evaluated_at timestamptz) RETURNS jsonb LANGUAGE plpgsql "
        "SECURITY DEFINER SET search_path = pg_catalog, public AS $writer_projection$"
        + writer_source
        + "$writer_projection$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {WRITER_CONTEXT_FUNCTION} FROM PUBLIC")


def _set_release_receipt_clock_contract(*, enabled: bool) -> None:
    """Preserve only the writer-supplied post-lock release receipt instant."""

    bind = op.get_bind()
    definition = bind.execute(
        sa.text(
            "SELECT pg_catalog.pg_get_functiondef(procedure.oid) "
            "FROM pg_catalog.pg_proc AS procedure "
            "WHERE procedure.oid=pg_catalog.to_regprocedure("
            "'public.caresync_childcare_operation_guard()')"
        )
    ).scalar_one_or_none()
    if definition is None:
        raise RuntimeError("0029D requires the exact 0028 childcare operation guard")
    original = "NEW.committed_at := transaction_timestamp();"
    release_aware = (
        "IF NEW.command_type = 'attendance.release.checkout' THEN\n"
        "              IF NEW.committed_at IS NULL "
        "OR NOT pg_catalog.isfinite(NEW.committed_at) THEN\n"
        "                RAISE EXCEPTION 'release checkout receipt time is invalid'\n"
        "                  USING ERRCODE='23514',\n"
        "                        CONSTRAINT='ck_release_checkout_receipt_time';\n"
        "              END IF;\n"
        "            ELSE\n"
        "              NEW.committed_at := transaction_timestamp();\n"
        "            END IF;"
    )
    source, target = (original, release_aware) if enabled else (release_aware, original)
    if str(definition).count(source) != 1 or (enabled and target in str(definition)):
        raise RuntimeError("0029D refused an unexpected childcare receipt clock definition")
    bind.exec_driver_sql(str(definition).replace(source, target))


def _install_activation_projection() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_release_checkout_activation_enabled(
          requested_facility_id uuid
        )
        RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $projection$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
        BEGIN
          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RETURN false;
          END;

          IF context_organization_id IS NULL OR context_user_id IS NULL
             OR requested_facility_id IS NULL THEN
            RETURN false;
          END IF;

          RETURN EXISTS (
            SELECT 1
            FROM public.users AS actor
            JOIN public.organization_memberships AS membership
              ON membership.user_id=actor.id
             AND membership.organization_id=context_organization_id
             AND membership.status='active'
            JOIN public.organizations AS organization_record
              ON organization_record.id=membership.organization_id
             AND organization_record.status='active'
            JOIN public.facilities AS facility
              ON facility.organization_id=membership.organization_id
             AND facility.id=requested_facility_id
             AND facility.status='active'
            JOIN public.facility_release_checkout_activations AS activation
              ON activation.organization_id=facility.organization_id
             AND activation.facility_id=facility.id
             AND activation.activation_policy_version='normal_verified_release_v1'
            WHERE actor.id=context_user_id
              AND actor.is_active=true
              AND actor.email_verified_at IS NOT NULL
          );
        END
        $projection$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {ACTIVATION_FUNCTION} FROM PUBLIC")


def _install_replay_projection() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_release_checkout_replay(
          requested_client_operation_id uuid
        )
        RETURNS TABLE(
          release_id uuid,
          organization_id uuid,
          facility_id uuid,
          room_id uuid,
          child_id uuid,
          attendance_day_id uuid,
          attendance_interval_id uuid,
          attendance_day_version integer,
          checkout_event_id uuid,
          staff_shift_id uuid,
          actor_user_id uuid,
          actor_membership_id uuid,
          recipient_person_id uuid,
          recipient_person_version_id uuid,
          recipient_display_name text,
          recipient_relationship text,
          authorization_id uuid,
          authorization_version integer,
          authority_revision integer,
          restriction_digest_sha256 text,
          verification_policy_code text,
          verification_method text,
          verification_result text,
          decision_policy_version text,
          requested_at timestamptz,
          checked_out_at timestamptz,
          committed_at timestamptz,
          client_operation_id uuid,
          request_hash text,
          release_mode text
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $projection$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
          context_operation_id uuid;
          actor_ready boolean;
        BEGIN
          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
            context_operation_id := NULLIF(
              pg_catalog.current_setting('app.current_childcare_operation_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'release_checkout_identity_unavailable'
              USING ERRCODE='42501';
          END;
          IF context_organization_id IS NULL OR context_user_id IS NULL
             OR context_operation_id IS NULL
             OR requested_client_operation_id IS NULL
             OR context_operation_id<>requested_client_operation_id THEN
            RAISE EXCEPTION 'release_checkout_identity_unavailable'
              USING ERRCODE='42501';
          END IF;

          SELECT EXISTS (
            SELECT 1
            FROM public.users AS actor
            JOIN public.organization_memberships AS membership
              ON membership.user_id=actor.id
             AND membership.organization_id=context_organization_id
             AND membership.status='active'
            JOIN public.organizations AS organization_record
              ON organization_record.id=membership.organization_id
             AND organization_record.status='active'
            WHERE actor.id=context_user_id
              AND actor.is_active=true
              AND actor.email_verified_at IS NOT NULL
          ) INTO actor_ready;
          IF NOT actor_ready THEN
            RAISE EXCEPTION 'release_checkout_forbidden' USING ERRCODE='42501';
          END IF;

          RETURN QUERY
          SELECT snapshot.id,
                 snapshot.organization_id,
                 snapshot.facility_id,
                 snapshot.room_id,
                 snapshot.child_id,
                 snapshot.attendance_day_id,
                 snapshot.attendance_interval_id,
                 snapshot.attendance_day_version,
                 snapshot.checkout_event_id,
                 snapshot.staff_shift_id,
                 snapshot.actor_user_id,
                 snapshot.actor_membership_id,
                 snapshot.recipient_person_id,
                 snapshot.recipient_person_version_id,
                 snapshot.recipient_display_name::text,
                 snapshot.recipient_relationship::text,
                 snapshot.authorization_id,
                 snapshot.authorization_version,
                 snapshot.authority_revision,
                 snapshot.restriction_digest_sha256::text,
                 snapshot.verification_policy_code::text,
                 snapshot.verification_method::text,
                 snapshot.verification_result::text,
                 snapshot.decision_policy_version::text,
                 snapshot.requested_at,
                 snapshot.checked_out_at,
                 snapshot.committed_at,
                 snapshot.client_operation_id,
                 snapshot.request_hash::text,
                 snapshot.release_mode::text
          FROM public.attendance_release_snapshots AS snapshot
          JOIN public.childcare_command_receipts AS receipt
            ON receipt.organization_id=snapshot.organization_id
           AND receipt.client_operation_id=snapshot.client_operation_id
           AND receipt.target_id=snapshot.id
          WHERE snapshot.organization_id=context_organization_id
            AND snapshot.client_operation_id=requested_client_operation_id
            AND snapshot.actor_user_id=context_user_id
            AND receipt.actor_user_id=context_user_id
            AND receipt.command_type='attendance.release.checkout'
            AND receipt.target_type='attendance_release'
            AND receipt.committed_version=1
            AND receipt.facility_id=snapshot.facility_id
            AND receipt.request_hash=snapshot.request_hash
            AND receipt.committed_at=snapshot.committed_at;

          IF NOT FOUND THEN
            RAISE EXCEPTION 'release_checkout_receipt_incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_checkout_replay_bundle';
          END IF;
        END
        $projection$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {REPLAY_FUNCTION} FROM PUBLIC")


def _install_snapshot_time_guard() -> None:
    """Derive both snapshot instants from the same-transaction receipt."""

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_release_snapshot_commit_time_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          receipt_committed_at timestamptz;
        BEGIN
          SELECT receipt.committed_at
            INTO receipt_committed_at
          FROM public.childcare_command_receipts AS receipt
          WHERE receipt.organization_id=NEW.organization_id
            AND receipt.client_operation_id=NEW.client_operation_id
            AND receipt.actor_user_id=NEW.actor_user_id
            AND receipt.command_type='attendance.release.checkout'
            AND receipt.target_type='attendance_release'
            AND receipt.target_id=NEW.id
            AND receipt.request_hash=NEW.request_hash
            AND receipt.committed_version=1
            AND receipt.facility_id=NEW.facility_id
            AND receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid;
          IF receipt_committed_at IS NULL THEN
            RAISE EXCEPTION 'release checkout snapshot has no exact receipt time'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_checkout_snapshot_receipt_time';
          END IF;
          NEW.checked_out_at := receipt_committed_at;
          NEW.committed_at := receipt_committed_at;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {SNAPSHOT_TIME_GUARD_FUNCTION} FROM PUBLIC")
    # PostgreSQL orders same-event triggers by name.  A's generic insert guard
    # runs first, this clock canonicalizer follows, and C's zz relational guard
    # observes the final receipt-derived values.
    op.execute(
        "CREATE TRIGGER zy_attendance_release_snapshots_commit_time "
        "BEFORE INSERT ON public.attendance_release_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_release_snapshot_commit_time_guard()"
    )


def _install_snapshot_repository() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_release_checkout_insert_snapshot(
          requested_release_id uuid,
          requested_child_id uuid,
          requested_facility_id uuid,
          requested_room_id uuid,
          requested_attendance_day_id uuid,
          requested_attendance_day_version integer,
          requested_attendance_interval_id uuid,
          requested_checkout_event_id uuid,
          requested_staff_shift_id uuid,
          requested_recipient_person_id uuid,
          requested_recipient_person_version_id uuid,
          requested_authorization_id uuid,
          requested_authorization_version integer,
          requested_authority_revision integer,
          requested_restriction_digest_sha256 text,
          requested_verification_method text,
          requested_verification_result text,
          requested_decision_policy_version text,
          requested_decision_at timestamp with time zone,
          requested_requested_at timestamp with time zone,
          requested_request_hash text
        )
        RETURNS TABLE(
          release_id uuid,
          organization_id uuid,
          facility_id uuid,
          room_id uuid,
          child_id uuid,
          attendance_day_id uuid,
          attendance_interval_id uuid,
          attendance_day_version integer,
          checkout_event_id uuid,
          staff_shift_id uuid,
          actor_user_id uuid,
          actor_membership_id uuid,
          recipient_person_id uuid,
          recipient_person_version_id uuid,
          recipient_display_name text,
          recipient_relationship text,
          authorization_id uuid,
          authorization_version integer,
          authority_revision integer,
          restriction_digest_sha256 text,
          verification_policy_code text,
          verification_method text,
          verification_result text,
          decision_policy_version text,
          requested_at timestamptz,
          checked_out_at timestamptz,
          committed_at timestamptz,
          client_operation_id uuid,
          request_hash text,
          release_mode text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $repository$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
          context_operation_id uuid;
          decision_at timestamptz := requested_decision_at;
          observed_after_locks timestamptz;
          selected_membership_id uuid;
          selected_role_id uuid;
          selected_role_key text;
          selected_scope_basis text;
          selected_room_assignment_id uuid;
          selected_family_id uuid;
          selected_evidence_id uuid;
          selected_evidence_assessment_id uuid;
          selected_evidence_assessment_version integer;
          selected_evidence_kind text;
          selected_evidence_object_id uuid;
          selected_evidence_content_sha256 text;
          selected_evidence_expires_at timestamptz;
          selected_epistemic_status text;
          selected_verification_policy text;
          selected_authorization_effective_from timestamptz;
          selected_authorization_effective_until timestamptz;
          selected_display_name text;
          selected_relationship text;
          evidence_document text;
          selected_evidence_digest text;
          assignment_count integer;
        BEGIN
          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
            context_operation_id := NULLIF(
              pg_catalog.current_setting('app.current_childcare_operation_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'release_checkout_identity_unavailable'
              USING ERRCODE='42501';
          END;
          IF context_organization_id IS NULL OR context_user_id IS NULL
             OR context_operation_id IS NULL THEN
            RAISE EXCEPTION 'release_checkout_identity_unavailable'
              USING ERRCODE='42501';
          END IF;
          IF requested_release_id IS NULL OR requested_child_id IS NULL
             OR requested_facility_id IS NULL OR requested_room_id IS NULL
             OR requested_attendance_day_id IS NULL
             OR requested_attendance_day_version IS NULL
             OR requested_attendance_interval_id IS NULL
             OR requested_checkout_event_id IS NULL
             OR requested_staff_shift_id IS NULL
             OR requested_recipient_person_id IS NULL
             OR requested_recipient_person_version_id IS NULL
             OR requested_authorization_id IS NULL
             OR requested_authorization_version IS NULL
             OR requested_authority_revision IS NULL
             OR requested_restriction_digest_sha256 IS NULL
             OR requested_verification_method IS NULL
             OR requested_verification_result IS NULL
             OR requested_decision_policy_version IS NULL
             OR requested_decision_at IS NULL
             OR requested_requested_at IS NULL
             OR requested_request_hash IS NULL
             OR NOT pg_catalog.isfinite(requested_decision_at)
             OR NOT pg_catalog.isfinite(requested_requested_at)
             OR requested_decision_at<pg_catalog.transaction_timestamp()
             OR requested_requested_at>requested_decision_at
             OR requested_attendance_day_version<1
             OR requested_authorization_version<1
             OR requested_authority_revision<1
             OR requested_restriction_digest_sha256 !~ '^[0-9a-f]{64}$'
             OR requested_request_hash !~ '^[0-9a-f]{64}$'
             OR requested_decision_policy_version<>'release-context-v1' THEN
            RAISE EXCEPTION 'release_checkout_request_invalid'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_checkout_repository_request';
          END IF;

          SELECT membership.id,role_record.id,role_record.key
            INTO selected_membership_id,selected_role_id,selected_role_key
          FROM public.users AS actor
          JOIN public.organization_memberships AS membership
            ON membership.user_id=actor.id
           AND membership.organization_id=context_organization_id
           AND membership.status='active'
          JOIN public.organizations AS organization_record
            ON organization_record.id=membership.organization_id
           AND organization_record.status='active'
          JOIN public.roles AS role_record
            ON role_record.organization_id=membership.organization_id
           AND role_record.id=membership.role_id
          WHERE actor.id=context_user_id
            AND actor.is_active=true
            AND actor.email_verified_at IS NOT NULL
            AND EXISTS (
              SELECT 1 FROM pg_catalog.json_array_elements_text(
                role_record.permissions
              ) AS permission(value)
              WHERE permission.value='attendance:record'
            )
            AND EXISTS (
              SELECT 1 FROM pg_catalog.json_array_elements_text(
                role_record.permissions
              ) AS permission(value)
              WHERE permission.value='release:checkout'
            )
          FOR SHARE OF actor, membership, organization_record, role_record;
          IF selected_membership_id IS NULL THEN
            RAISE EXCEPTION 'release_checkout_forbidden' USING ERRCODE='42501';
          END IF;

          PERFORM 1
          FROM public.facilities AS facility
          JOIN public.facility_release_checkout_activations AS activation
            ON activation.organization_id=facility.organization_id
           AND activation.facility_id=facility.id
           AND activation.activation_policy_version='normal_verified_release_v1'
          WHERE facility.organization_id=context_organization_id
            AND facility.id=requested_facility_id
            AND facility.status='active'
          FOR SHARE OF facility,activation;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'release_checkout_not_activated' USING ERRCODE='23514';
          END IF;

          PERFORM 1
          FROM public.staff_shifts AS shift_record
          WHERE shift_record.organization_id=context_organization_id
            AND shift_record.id=requested_staff_shift_id
            AND shift_record.membership_id=selected_membership_id
            AND shift_record.facility_id=requested_facility_id
            AND shift_record.status='open'
            AND shift_record.clocked_out_at IS NULL
          FOR SHARE OF shift_record;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'open_shift_required' USING ERRCODE='23514';
          END IF;

          SELECT child_record.family_id
            INTO selected_family_id
          FROM public.children AS child_record
          JOIN public.families AS family_record
            ON family_record.organization_id=child_record.organization_id
           AND family_record.id=child_record.family_id
           AND family_record.status='active'
          JOIN public.child_authority_heads AS authority_head
            ON authority_head.organization_id=child_record.organization_id
           AND authority_head.family_id=child_record.family_id
           AND authority_head.child_id=child_record.id
          JOIN public.attendance_days AS attendance_day
            ON attendance_day.organization_id=child_record.organization_id
           AND attendance_day.id=requested_attendance_day_id
           AND attendance_day.facility_id=requested_facility_id
           AND attendance_day.child_id=child_record.id
           AND attendance_day.room_id=requested_room_id
           AND attendance_day.status='present'
          JOIN public.attendance_intervals AS attendance_interval
            ON attendance_interval.organization_id=attendance_day.organization_id
           AND attendance_interval.attendance_day_id=attendance_day.id
           AND attendance_interval.id=requested_attendance_interval_id
           AND attendance_interval.checked_out_at IS NULL
          JOIN public.enrollments AS enrollment
            ON enrollment.organization_id=attendance_day.organization_id
           AND enrollment.id=attendance_day.enrollment_id
           AND enrollment.facility_id=attendance_day.facility_id
           AND enrollment.child_id=attendance_day.child_id
           AND enrollment.room_id=attendance_day.room_id
           AND enrollment.status='active'
           AND enrollment.start_date<=attendance_day.service_date
           AND enrollment.placement_effective_date<=attendance_day.service_date
           AND (enrollment.end_date IS NULL
             OR enrollment.end_date>=attendance_day.service_date)
          JOIN public.rooms AS room_record
            ON room_record.organization_id=attendance_day.organization_id
           AND room_record.facility_id=attendance_day.facility_id
           AND room_record.id=attendance_day.room_id
           AND room_record.is_active=true
           AND room_record.program_id=enrollment.program_id
          JOIN public.facility_programs AS program_record
            ON program_record.organization_id=enrollment.organization_id
           AND program_record.facility_id=enrollment.facility_id
           AND program_record.id=enrollment.program_id
           AND program_record.is_active=true
          WHERE child_record.organization_id=context_organization_id
            AND child_record.id=requested_child_id
            AND child_record.is_active=true
            AND authority_head.revision=requested_authority_revision
            AND attendance_day.version=requested_attendance_day_version
            AND attendance_interval.checked_in_at<=decision_at
          FOR SHARE OF child_record,family_record,authority_head,attendance_day,
            attendance_interval,enrollment,room_record,program_record;
          IF selected_family_id IS NULL THEN
            RAISE EXCEPTION 'release_checkout_context_stale' USING ERRCODE='40001';
          END IF;

          IF selected_role_key IN ('owner','administrator') THEN
            selected_scope_basis := 'organization_role';
            selected_room_assignment_id := NULL;
          ELSE
            SELECT count(*),min(assignment.id::text)::uuid
              INTO assignment_count,selected_room_assignment_id
            FROM public.membership_room_assignments AS assignment
            WHERE assignment.organization_id=context_organization_id
              AND assignment.membership_id=selected_membership_id
              AND assignment.facility_id=requested_facility_id
              AND assignment.room_id=requested_room_id
              AND assignment.is_active=true;
            IF assignment_count<>1 THEN
              RAISE EXCEPTION 'release_checkout_scope_not_found' USING ERRCODE='42501';
            END IF;
            PERFORM 1 FROM public.membership_room_assignments AS assignment
            WHERE assignment.organization_id=context_organization_id
              AND assignment.id=selected_room_assignment_id
            FOR SHARE OF assignment;
            selected_scope_basis := 'room_assignment';
          END IF;

          SELECT authorization_record.basis_evidence_id,
                 authorization_record.basis_evidence_assessment_id,
                 assessment.version_number,
                 evidence.evidence_kind,
                 evidence.evidence_object_id,
                 evidence.content_sha256::text,
                 evidence.expires_at,
                 assessment.assessed_epistemic_status,
                 authorization_record.verification_policy_code,
                 authorization_record.effective_from,
                 authorization_record.effective_until,
                 pg_catalog.concat_ws(
                   ' ',person_version.first_name,person_version.middle_name,
                   person_version.last_name
                 ),
                 CASE person_version.relationship_kind
                   WHEN 'parent' THEN 'Parent'
                   WHEN 'legal_guardian' THEN 'Legal guardian'
                   WHEN 'foster_parent' THEN 'Foster parent'
                   WHEN 'grandparent' THEN 'Grandparent'
                   WHEN 'adult_sibling' THEN 'Adult sibling'
                   WHEN 'aunt_uncle' THEN 'Aunt or uncle'
                   WHEN 'family_friend' THEN 'Family friend'
                   WHEN 'caseworker' THEN 'Caseworker'
                   WHEN 'transport_provider' THEN 'Transport provider'
                   WHEN 'other' THEN person_version.relationship_detail
                 END
            INTO selected_evidence_id,selected_evidence_assessment_id,
                 selected_evidence_assessment_version,selected_evidence_kind,
                 selected_evidence_object_id,selected_evidence_content_sha256,
                 selected_evidence_expires_at,selected_epistemic_status,
                 selected_verification_policy,
                 selected_authorization_effective_from,
                 selected_authorization_effective_until,selected_display_name,
                 selected_relationship
          FROM public.child_release_authorizations AS authorization_record
          JOIN public.family_authority_people AS person_record
            ON person_record.organization_id=authorization_record.organization_id
           AND person_record.family_id=authorization_record.family_id
           AND person_record.id=authorization_record.recipient_person_id
           AND person_record.status='active'
          JOIN public.family_authority_person_versions AS person_version
            ON person_version.organization_id=person_record.organization_id
           AND person_version.family_id=person_record.family_id
           AND person_version.person_id=person_record.id
           AND person_version.id=person_record.current_person_version_id
           AND person_version.closed_at IS NULL
          JOIN public.family_authority_evidence AS evidence
            ON evidence.organization_id=authorization_record.organization_id
           AND evidence.family_id=authorization_record.family_id
           AND evidence.id=authorization_record.basis_evidence_id
          JOIN public.family_authority_evidence_assessments AS assessment
            ON assessment.organization_id=evidence.organization_id
           AND assessment.family_id=evidence.family_id
           AND assessment.evidence_id=evidence.id
           AND assessment.id=authorization_record.basis_evidence_assessment_id
           AND assessment.version_number=2
           AND assessment.decision='reviewed'
           AND assessment.assessed_epistemic_status IN ('reported','document_observed')
          WHERE authorization_record.organization_id=context_organization_id
            AND authorization_record.family_id=selected_family_id
            AND authorization_record.child_id=requested_child_id
            AND authorization_record.id=requested_authorization_id
            AND authorization_record.recipient_person_id=
                requested_recipient_person_id
            AND authorization_record.version=requested_authorization_version
            AND authorization_record.revoked_at IS NULL
            AND authorization_record.effective_from<=decision_at
            AND authorization_record.effective_until>decision_at
            AND person_version.id=requested_recipient_person_version_id
            AND (evidence.expires_at IS NULL OR evidence.expires_at>decision_at)
            AND NOT EXISTS (
              SELECT 1
              FROM public.family_authority_evidence_assessments AS terminal
              WHERE terminal.organization_id=evidence.organization_id
                AND terminal.evidence_id=evidence.id
                AND terminal.version_number=3
            )
          FOR SHARE OF authorization_record,person_record,person_version,evidence,assessment;
          IF selected_evidence_id IS NULL OR selected_display_name IS NULL
             OR selected_relationship IS NULL THEN
            RAISE EXCEPTION 'release_checkout_context_stale' USING ERRCODE='40001';
          END IF;

          -- Every potentially blocking authorization row is now locked.  The
          -- observed clock closes the expiry-after-lock race: the asserted
          -- decision instant must be a current-transaction server instant, and
          -- the authority must remain valid when lock acquisition completes.
          observed_after_locks := pg_catalog.clock_timestamp();
          IF decision_at>observed_after_locks
             OR selected_authorization_effective_from>observed_after_locks
             OR selected_authorization_effective_until<=observed_after_locks
             OR (selected_evidence_expires_at IS NOT NULL
               AND selected_evidence_expires_at<=observed_after_locks) THEN
            RAISE EXCEPTION 'release_checkout_context_stale' USING ERRCODE='40001';
          END IF;

          IF NOT (
            (selected_verification_policy='government_photo_id'
              AND requested_verification_method='government_photo_id'
              AND requested_verification_result='verified')
            OR (selected_verification_policy='documented_familiarity'
              AND requested_verification_method='documented_familiarity'
              AND requested_verification_result='documented_familiarity')
            OR (selected_verification_policy=
                  'government_photo_id_or_documented_familiarity'
              AND ((requested_verification_method='government_photo_id'
                    AND requested_verification_result='verified')
                OR (requested_verification_method='documented_familiarity'
                    AND requested_verification_result='documented_familiarity')))
          ) THEN
            RAISE EXCEPTION 'release_checkout_verification_policy_mismatch'
              USING ERRCODE='23514';
          END IF;

          evidence_document :=
            '{"assessed_epistemic_status":'
            || pg_catalog.to_json(selected_epistemic_status)::text
            || ',"content_sha256":'
            || COALESCE(
                 pg_catalog.to_json(selected_evidence_content_sha256)::text,'null'
               )
            || ',"decision":"reviewed"'
            || ',"evidence_assessment_id":'
            || pg_catalog.to_json(selected_evidence_assessment_id)::text
            || ',"evidence_assessment_version":'
            || selected_evidence_assessment_version::text
            || ',"evidence_id":'
            || pg_catalog.to_json(selected_evidence_id)::text
            || ',"evidence_kind":'
            || pg_catalog.to_json(selected_evidence_kind)::text
            || ',"evidence_object_id":'
            || COALESCE(pg_catalog.to_json(selected_evidence_object_id)::text,'null')
            || ',"expires_at":'
            || COALESCE(
                 pg_catalog.to_json(
                   pg_catalog.to_char(
                     selected_evidence_expires_at AT TIME ZONE 'UTC',
                     'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                   )
                 )::text,
                 'null'
               )
            || ',"schema_version":"release-evidence-v1"}';
          selected_evidence_digest := pg_catalog.encode(
            pg_catalog.sha256(pg_catalog.convert_to(evidence_document,'UTF8')),
            'hex'
          );

          INSERT INTO public.attendance_events (
            id,organization_id,attendance_day_id,client_operation_id,
            actor_user_id,event_type,occurred_at,before,after
          ) VALUES (
            requested_checkout_event_id,context_organization_id,
            requested_attendance_day_id,context_operation_id,context_user_id,
            'check_out',decision_at,
            pg_catalog.jsonb_build_object(
              'checked_out_at',NULL,
              'attendance_day_version',requested_attendance_day_version-1
            ),
            pg_catalog.jsonb_build_object(
              'checked_out_at',pg_catalog.to_char(
                decision_at AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'
              ),
              'attendance_day_version',requested_attendance_day_version,
              'release_id',requested_release_id::text
            )
          );

          INSERT INTO public.childcare_command_receipts (
            id,organization_id,client_operation_id,command_type,target_type,
            target_id,request_hash,actor_user_id,facility_id,
            committed_version,committed_at,outcome
          ) VALUES (
            pg_catalog.gen_random_uuid(),context_organization_id,
            context_operation_id,'attendance.release.checkout',
            'attendance_release',requested_release_id,requested_request_hash,
            context_user_id,requested_facility_id,1,decision_at,
            pg_catalog.jsonb_build_object(
              'action_route','/attendance/releases/' || requested_release_id::text
            )
          );

          INSERT INTO public.attendance_release_snapshots (
            id,organization_id,family_id,facility_id,child_id,
            attendance_day_id,attendance_day_version,attendance_interval_id,
            checkout_event_id,recipient_person_id,recipient_person_version_id,
            recipient_display_name,recipient_relationship,authorization_id,
            authorization_version,evidence_id,evidence_assessment_id,
            evidence_assessment_version,authority_revision,
            restriction_digest_sha256,verification_method,verification_result,
            verification_policy_code,evidence_digest_sha256,
            decision_policy_version,actor_user_id,actor_membership_id,
            actor_role_id,actor_role_key,staff_shift_id,room_id,scope_basis,
            room_assignment_id,requested_at,checked_out_at,committed_at,
            client_operation_id,request_hash,release_mode,
            override_reason_code,override_justification
          ) VALUES (
            requested_release_id,context_organization_id,selected_family_id,
            requested_facility_id,requested_child_id,requested_attendance_day_id,
            requested_attendance_day_version,requested_attendance_interval_id,
            requested_checkout_event_id,requested_recipient_person_id,
            requested_recipient_person_version_id,selected_display_name,
            selected_relationship,requested_authorization_id,
            requested_authorization_version,selected_evidence_id,
            selected_evidence_assessment_id,selected_evidence_assessment_version,
            requested_authority_revision,requested_restriction_digest_sha256,
            requested_verification_method,requested_verification_result,
            selected_verification_policy,selected_evidence_digest,
            requested_decision_policy_version,context_user_id,
            selected_membership_id,selected_role_id,selected_role_key,
            requested_staff_shift_id,requested_room_id,selected_scope_basis,
            selected_room_assignment_id,requested_requested_at,decision_at,
            decision_at,context_operation_id,requested_request_hash,'normal',NULL,NULL
          );

          RETURN QUERY
          SELECT snapshot.id,
                 snapshot.organization_id,
                 snapshot.facility_id,
                 snapshot.room_id,
                 snapshot.child_id,
                 snapshot.attendance_day_id,
                 snapshot.attendance_interval_id,
                 snapshot.attendance_day_version,
                 snapshot.checkout_event_id,
                 snapshot.staff_shift_id,
                 snapshot.actor_user_id,
                 snapshot.actor_membership_id,
                 snapshot.recipient_person_id,
                 snapshot.recipient_person_version_id,
                 snapshot.recipient_display_name::text,
                 snapshot.recipient_relationship::text,
                 snapshot.authorization_id,
                 snapshot.authorization_version,
                 snapshot.authority_revision,
                 snapshot.restriction_digest_sha256::text,
                 snapshot.verification_policy_code::text,
                 snapshot.verification_method::text,
                 snapshot.verification_result::text,
                 snapshot.decision_policy_version::text,
                 snapshot.requested_at,
                 snapshot.checked_out_at,
                 snapshot.committed_at,
                 snapshot.client_operation_id,
                 snapshot.request_hash::text,
                 snapshot.release_mode::text
          FROM public.attendance_release_snapshots AS snapshot
          WHERE snapshot.organization_id=context_organization_id
            AND snapshot.id=requested_release_id
            AND snapshot.client_operation_id=context_operation_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'release_checkout_snapshot_incomplete'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_release_checkout_repository_snapshot';
          END IF;
        END
        $repository$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {INSERT_FUNCTION} FROM PUBLIC")


def _install_interval_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.caresync_attendance_interval_verified_release_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          activated boolean;
          bundle_matches boolean := false;
        BEGIN
          IF TG_OP='DELETE' THEN
            IF EXISTS (
              SELECT 1
              FROM public.attendance_release_snapshots AS snapshot
              WHERE snapshot.organization_id=OLD.organization_id
                AND snapshot.attendance_day_id=OLD.attendance_day_id
                AND snapshot.attendance_interval_id=OLD.id
            ) THEN
              RAISE EXCEPTION 'verified release attendance interval is immutable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_verified_release_interval_immutable';
            END IF;
            RETURN OLD;
          END IF;

          SELECT EXISTS (
            SELECT 1
            FROM public.attendance_days AS attendance_day
            JOIN public.facility_release_checkout_activations AS activation
              ON activation.organization_id=attendance_day.organization_id
             AND activation.facility_id=attendance_day.facility_id
             AND activation.activation_policy_version='normal_verified_release_v1'
            WHERE attendance_day.organization_id=OLD.organization_id
              AND attendance_day.id=OLD.attendance_day_id
          ) INTO activated;

          IF OLD.checked_out_at IS NULL AND NEW.checked_out_at IS NOT NULL
             AND activated THEN
            SELECT EXISTS (
              SELECT 1
              FROM public.attendance_release_snapshots AS snapshot
              JOIN public.attendance_events AS checkout_event
                ON checkout_event.organization_id=snapshot.organization_id
               AND checkout_event.attendance_day_id=snapshot.attendance_day_id
               AND checkout_event.id=snapshot.checkout_event_id
              JOIN public.childcare_command_receipts AS receipt
                ON receipt.organization_id=snapshot.organization_id
               AND receipt.client_operation_id=snapshot.client_operation_id
               AND receipt.target_id=snapshot.id
              WHERE snapshot.organization_id=OLD.organization_id
                AND snapshot.attendance_day_id=OLD.attendance_day_id
                AND snapshot.attendance_interval_id=OLD.id
                AND snapshot.checked_out_at=NEW.checked_out_at
                AND snapshot.committed_at=NEW.checked_out_at
                AND snapshot.xmin=pg_catalog.pg_current_xact_id()::text::xid
                AND checkout_event.client_operation_id=snapshot.client_operation_id
                AND checkout_event.actor_user_id=snapshot.actor_user_id
                AND checkout_event.event_type='check_out'
                AND checkout_event.occurred_at=NEW.checked_out_at
                AND checkout_event.xmin=pg_catalog.pg_current_xact_id()::text::xid
                AND receipt.actor_user_id=snapshot.actor_user_id
                AND receipt.command_type='attendance.release.checkout'
                AND receipt.target_type='attendance_release'
                AND receipt.facility_id=snapshot.facility_id
                AND receipt.request_hash=snapshot.request_hash
                AND receipt.committed_at=NEW.checked_out_at
                AND receipt.committed_version=1
                AND receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid
            ) INTO bundle_matches;
            IF NOT bundle_matches
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.attendance_day_id IS DISTINCT FROM OLD.attendance_day_id
               OR NEW.id IS DISTINCT FROM OLD.id
               OR NEW.sequence IS DISTINCT FROM OLD.sequence
               OR NEW.checked_in_at IS DISTINCT FROM OLD.checked_in_at
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
              RAISE EXCEPTION 'activated release checkout requires one exact bundle'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_verified_release_interval_bundle';
            END IF;
            RETURN NEW;
          END IF;

          IF EXISTS (
            SELECT 1
            FROM public.attendance_release_snapshots AS snapshot
            WHERE snapshot.organization_id=OLD.organization_id
              AND snapshot.attendance_day_id=OLD.attendance_day_id
              AND snapshot.attendance_interval_id=OLD.id
          ) THEN
            RAISE EXCEPTION 'verified release attendance interval is immutable'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_verified_release_interval_immutable';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {INTERVAL_GUARD_FUNCTION} FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER attendance_intervals_verified_release_guard "
        "BEFORE DELETE OR UPDATE ON public.attendance_intervals "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_attendance_interval_verified_release_guard()"
    )


def _grant_runtime_callables() -> None:
    op.execute(
        f"""
        DO $grants$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app'
          ) THEN
            REVOKE ALL ON FUNCTION {INTERVAL_GUARD_FUNCTION},
              {SNAPSHOT_TIME_GUARD_FUNCTION}
              FROM caresync_basic_app;
            GRANT EXECUTE ON FUNCTION {ACTIVATION_FUNCTION},
              {REPLAY_FUNCTION},
              {WRITER_CONTEXT_FUNCTION},
              {INSERT_FUNCTION}
            TO caresync_basic_app;
          END IF;
        END
        $grants$
        """
    )


def _preflight_empty_release_history_downgrade() -> None:
    bind = op.get_bind()
    snapshot_count = int(
        bind.execute(sa.text("SELECT count(*) FROM attendance_release_snapshots")).scalar_one()
    )
    receipt_count = int(
        bind.execute(
            sa.text(
                "SELECT count(*) FROM childcare_command_receipts "
                "WHERE target_type='attendance_release' "
                "OR command_type='attendance.release.checkout'"
            )
        ).scalar_one()
    )
    if snapshot_count or receipt_count:
        raise RuntimeError(
            "0029D downgrade refused before DDL because verified release history exists: "
            f"snapshots={snapshot_count}, receipts={receipt_count}"
        )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _install_writer_context_projection()
    _set_release_receipt_clock_contract(enabled=True)
    _install_activation_projection()
    _install_replay_projection()
    _install_snapshot_repository()
    _install_snapshot_time_guard()
    _install_interval_guard()
    _grant_runtime_callables()


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _preflight_empty_release_history_downgrade()
    op.execute(
        "DROP TRIGGER attendance_intervals_verified_release_guard "
        "ON public.attendance_intervals"
    )
    op.execute(f"DROP FUNCTION {INTERVAL_GUARD_FUNCTION}")
    op.execute(
        "DROP TRIGGER zy_attendance_release_snapshots_commit_time "
        "ON public.attendance_release_snapshots"
    )
    op.execute(f"DROP FUNCTION {SNAPSHOT_TIME_GUARD_FUNCTION}")
    op.execute(f"DROP FUNCTION {INSERT_FUNCTION}")
    op.execute(f"DROP FUNCTION {REPLAY_FUNCTION}")
    op.execute(f"DROP FUNCTION {ACTIVATION_FUNCTION}")
    op.execute(f"DROP FUNCTION {WRITER_CONTEXT_FUNCTION}")
    _set_release_receipt_clock_contract(enabled=False)

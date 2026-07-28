"""Add the bounded, read-only family release-context database boundary.

Revision ID: 0029B_release_context
Revises: 0029A2_authority_activation
Create Date: 2026-07-18

This revision does not authorize or record checkout.  It adds one dedicated
permission, a generic child-authority invalidation, and one minimum-necessary
PostgreSQL SECURITY DEFINER projection.  Existing A2 table RLS and grants are
deliberately unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "0029B_release_context"
down_revision = "0029A2_authority_activation"
branch_labels = None
depends_on = None


SYSTEM_RELEASE_ROLE_KEYS = ("owner", "administrator", "educator")
RELEASE_PERMISSION = "release:read"
POSTGRES_PROJECTION = "public.caresync_family_release_context_inputs(uuid,uuid)"


def _permission_list(raw: Any) -> list[str]:
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise RuntimeError("0029B refused malformed system-role permissions")
    return decoded


def _set_system_release_permission(*, enabled: bool) -> None:
    """Append/remove only release:read on the three system role templates."""

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
            updated = permissions if RELEASE_PERMISSION in permissions else [
                *permissions,
                RELEASE_PERMISSION,
            ]
        else:
            updated = [item for item in permissions if item != RELEASE_PERMISSION]
        if updated == permissions:
            continue
        bind.execute(
            sa.text("UPDATE roles SET permissions = :permissions WHERE id = :role_id"),
            {
                "permissions": json.dumps(updated, separators=(",", ":")),
                "role_id": row["id"],
            },
        )


def _preflight_a2_policy_width() -> None:
    """Refuse a lossy B-to-A2 type narrowing before the first mutation."""

    oversized = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM child_release_authorizations "
                "WHERE length(verification_policy_code) > 40"
            )
        )
        .scalar_one()
    )
    if oversized:
        raise RuntimeError(
            "0029B downgrade refused before DDL because a verification policy "
            f"exceeds the A2 VARCHAR(40) boundary: rows={oversized}"
        )


def _set_verification_policy_width(*, release_context_width: bool) -> None:
    with op.batch_alter_table("child_release_authorizations") as batch:
        batch.alter_column(
            "verification_policy_code",
            existing_type=sa.String(length=40 if release_context_width else 64),
            type_=sa.String(length=64 if release_context_width else 40),
            existing_nullable=False,
        )


def _install_postgres_invalidation() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_release_context_from_authority_head()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $event$
        BEGIN
          IF TG_OP = 'UPDATE' AND OLD.revision IS NOT DISTINCT FROM NEW.revision THEN
            RETURN NEW;
          END IF;
          INSERT INTO public.realtime_events
            (id, organization_id, event_type, entity_type, entity_id,
             occurred_at, payload)
          VALUES
            (pg_catalog.gen_random_uuid(), NEW.organization_id,
             'family_authority.release_context_invalidated',
             'child_authority_head', NULL, pg_catalog.statement_timestamp(),
             pg_catalog.jsonb_build_object(
               'source', 'authority_head', 'scope', 'release_context'
             ));
          RETURN NEW;
        END
        $event$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_release_context_from_authority_head() FROM PUBLIC"
    )
    op.execute(
        """
        CREATE TRIGGER child_authority_heads_release_context_invalidated
        AFTER INSERT OR UPDATE OF revision ON public.child_authority_heads
        FOR EACH ROW
        EXECUTE FUNCTION public.caresync_release_context_from_authority_head()
        """
    )


def _install_sqlite_invalidation() -> None:
    op.execute(
        """
        CREATE TRIGGER child_authority_heads_release_context_insert
        AFTER INSERT ON child_authority_heads
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id,
             occurred_at, payload)
          VALUES
            (lower(hex(randomblob(16))), NEW.organization_id,
             'family_authority.release_context_invalidated',
             'child_authority_head', NULL, CURRENT_TIMESTAMP,
             json_object('source', 'authority_head', 'scope', 'release_context'));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER child_authority_heads_release_context_update
        AFTER UPDATE OF revision ON child_authority_heads
        WHEN OLD.revision IS NOT NEW.revision
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id,
             occurred_at, payload)
          VALUES
            (lower(hex(randomblob(16))), NEW.organization_id,
             'family_authority.release_context_invalidated',
             'child_authority_head', NULL, CURRENT_TIMESTAMP,
             json_object('source', 'authority_head', 'scope', 'release_context'));
        END
        """
    )


def _install_postgres_projection() -> None:
    """Install the strict ReleaseContextInput JSON projection and its gates."""

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_release_context_inputs(
          requested_child_id uuid,
          requested_facility_id uuid
        )
        RETURNS jsonb
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $projection$
        DECLARE
          actor_organization_id uuid;
          actor_user_id uuid;
          actor_membership_id uuid;
          actor_role_key text;
          evaluated_at_value timestamptz := pg_catalog.statement_timestamp();
          projected_family_id uuid;
          projected_room_id uuid;
          projected_attendance_day_id uuid;
          projected_attendance_interval_id uuid;
          projected_shift_id uuid;
          projected_authority_revision bigint := 0;
          actor_scope_ready boolean := false;
          permission_ready boolean := false;
          facility_ready boolean := false;
          facility_timezone_ready boolean := false;
          room_scope_ready boolean := false;
          exact_shift_count integer := 0;
          other_shift_count integer := 0;
          active_enrollment_count integer := 0;
          open_attendance_count integer := 0;
          result jsonb;
        BEGIN
          BEGIN
            actor_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            actor_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'release_context_identity_unavailable'
              USING ERRCODE = '42501';
          END;
          IF actor_organization_id IS NULL OR actor_user_id IS NULL THEN
            RAISE EXCEPTION 'release_context_identity_unavailable'
              USING ERRCODE = '42501';
          END IF;

          -- Match the authority writers' family synchronization boundary
          -- before the statement-snapshot operational authorization gate.
          SELECT family_record.id
            INTO projected_family_id
          FROM public.children AS child_record
          JOIN public.families AS family_record
            ON family_record.organization_id = child_record.organization_id
           AND family_record.id = child_record.family_id
          WHERE child_record.organization_id = actor_organization_id
            AND child_record.id = requested_child_id
          FOR SHARE OF family_record;
          IF projected_family_id IS NULL THEN
            RAISE EXCEPTION 'release_context_scope_not_found' USING ERRCODE = 'P0002';
          END IF;

          -- Every operational gate below is evaluated by this one SQL command
          -- and therefore by one READ COMMITTED statement snapshot.  In
          -- particular, shift and attendance states from opposite sides of a
          -- concurrent transition can never be composed.
          WITH actor_scope AS (
            SELECT membership.id AS membership_id,
                   role_record.key AS role_key,
                   EXISTS (
                     SELECT 1
                     FROM pg_catalog.json_array_elements_text(
                       role_record.permissions
                     ) AS permission(value)
                     WHERE permission.value = 'release:read'
                   ) AS has_release_permission
            FROM public.users AS actor
            JOIN public.organization_memberships AS membership
              ON membership.user_id = actor.id
             AND membership.organization_id = actor_organization_id
             AND membership.status = 'active'
            JOIN public.organizations AS organization_record
              ON organization_record.id = membership.organization_id
             AND organization_record.status = 'active'
            JOIN public.roles AS role_record
              ON role_record.organization_id = membership.organization_id
             AND role_record.id = membership.role_id
            WHERE actor.id = actor_user_id
              AND actor.is_active = true
          ), active_facility AS (
            SELECT facility.timezone
            FROM public.facilities AS facility
            WHERE facility.organization_id = actor_organization_id
              AND facility.id = requested_facility_id
              AND facility.status = 'active'
          ), facility_scope AS (
            SELECT EXISTS (SELECT 1 FROM active_facility) AS is_active,
                   COALESCE((
                     SELECT EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_timezone_names AS timezone_record
                       WHERE timezone_record.name = active_facility.timezone
                     )
                     FROM active_facility
                   ), false) AS timezone_is_valid,
                   (
                     SELECT (evaluated_at_value AT TIME ZONE active_facility.timezone)::date
                     FROM active_facility
                     WHERE EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_timezone_names AS timezone_record
                       WHERE timezone_record.name = active_facility.timezone
                     )
                   ) AS service_date
          ), active_enrollments AS (
            SELECT enrollment.id, enrollment.room_id
            FROM public.children AS child_record
            JOIN public.families AS family_record
              ON family_record.organization_id = child_record.organization_id
             AND family_record.id = child_record.family_id
             AND family_record.status = 'active'
            JOIN public.enrollments AS enrollment
              ON enrollment.organization_id = child_record.organization_id
             AND enrollment.child_id = child_record.id
             AND enrollment.facility_id = requested_facility_id
             AND enrollment.status = 'active'
             AND enrollment.room_id IS NOT NULL
             AND enrollment.placement_effective_date IS NOT NULL
             AND enrollment.start_date <= (
               SELECT facility_scope.service_date FROM facility_scope
             )
             AND enrollment.placement_effective_date <= (
               SELECT facility_scope.service_date FROM facility_scope
             )
             AND (enrollment.end_date IS NULL
               OR enrollment.end_date >= (
                 SELECT facility_scope.service_date FROM facility_scope
               ))
            WHERE child_record.organization_id = actor_organization_id
              AND child_record.family_id = projected_family_id
              AND child_record.id = requested_child_id
              AND child_record.is_active = true
          ), shift_summary AS (
            SELECT count(*) FILTER (
                     WHERE shift_record.facility_id = requested_facility_id
                   )::integer AS exact_count,
                   count(*) FILTER (
                     WHERE shift_record.facility_id <> requested_facility_id
                   )::integer AS other_count,
                   min(shift_record.id::text) FILTER (
                     WHERE shift_record.facility_id = requested_facility_id
                   )::uuid AS shift_id
            FROM public.staff_shifts AS shift_record
            WHERE shift_record.organization_id = actor_organization_id
              AND shift_record.membership_id = (
                SELECT actor_scope.membership_id FROM actor_scope
              )
              AND shift_record.status = 'open'
              AND shift_record.clocked_out_at IS NULL
          ), open_attendance AS (
            SELECT attendance_day.id AS attendance_day_id,
                   attendance_interval.id AS attendance_interval_id,
                   attendance_day.room_id AS room_id
            FROM active_enrollments AS enrollment
            JOIN public.attendance_days AS attendance_day
              ON attendance_day.organization_id = actor_organization_id
             AND attendance_day.facility_id = requested_facility_id
             AND attendance_day.child_id = requested_child_id
             AND attendance_day.enrollment_id = enrollment.id
             AND attendance_day.room_id = enrollment.room_id
             AND attendance_day.status = 'present'
            JOIN public.attendance_intervals AS attendance_interval
              ON attendance_interval.organization_id = attendance_day.organization_id
             AND attendance_interval.attendance_day_id = attendance_day.id
             AND attendance_interval.checked_out_at IS NULL
            JOIN public.rooms AS room_record
              ON room_record.organization_id = attendance_day.organization_id
             AND room_record.facility_id = attendance_day.facility_id
             AND room_record.id = attendance_day.room_id
             AND room_record.is_active = true
          ), attendance_summary AS (
            SELECT count(*)::integer AS open_count,
                   min(attendance_day_id::text)::uuid AS attendance_day_id,
                   min(attendance_interval_id::text)::uuid AS attendance_interval_id,
                   min(room_id::text)::uuid AS room_id
            FROM open_attendance
          )
          SELECT EXISTS (SELECT 1 FROM actor_scope),
                 (SELECT membership_id FROM actor_scope),
                 (SELECT role_key FROM actor_scope),
                 COALESCE(
                   (SELECT has_release_permission FROM actor_scope), false
                 ),
                 (SELECT is_active FROM facility_scope),
                 (SELECT timezone_is_valid FROM facility_scope),
                 shift_summary.exact_count,
                 shift_summary.other_count,
                 shift_summary.shift_id,
                 (SELECT count(*)::integer FROM active_enrollments),
                 attendance_summary.open_count,
                 attendance_summary.attendance_day_id,
                 attendance_summary.attendance_interval_id,
                 attendance_summary.room_id,
                 COALESCE((
                   SELECT actor_scope.role_key IN ('owner', 'administrator')
                     OR EXISTS (
                       SELECT 1
                       FROM public.membership_room_assignments AS assignment
                       WHERE assignment.organization_id = actor_organization_id
                         AND assignment.membership_id = actor_scope.membership_id
                         AND assignment.facility_id = requested_facility_id
                         AND assignment.room_id = attendance_summary.room_id
                         AND assignment.is_active = true
                     )
                   FROM actor_scope
                 ), false)
            INTO actor_scope_ready, actor_membership_id, actor_role_key,
                 permission_ready, facility_ready, facility_timezone_ready,
                 exact_shift_count, other_shift_count, projected_shift_id,
                 active_enrollment_count, open_attendance_count,
                 projected_attendance_day_id,
                 projected_attendance_interval_id, projected_room_id,
                 room_scope_ready
          FROM shift_summary CROSS JOIN attendance_summary;

          IF NOT actor_scope_ready THEN
            RAISE EXCEPTION 'release_context_forbidden' USING ERRCODE = '42501';
          END IF;
          IF NOT permission_ready THEN
            RAISE EXCEPTION 'release_context_forbidden' USING ERRCODE = '42501';
          END IF;
          IF NOT facility_ready THEN
            RAISE EXCEPTION 'release_context_scope_not_found' USING ERRCODE = 'P0002';
          END IF;
          IF NOT facility_timezone_ready THEN
            RAISE EXCEPTION 'release_context_inconsistent' USING ERRCODE = 'P0001';
          END IF;
          IF exact_shift_count = 0 THEN
            IF other_shift_count > 0 THEN
              RAISE EXCEPTION 'open_shift_facility_mismatch' USING ERRCODE = 'P0001';
            END IF;
            RAISE EXCEPTION 'open_shift_required' USING ERRCODE = 'P0001';
          ELSIF exact_shift_count <> 1 OR other_shift_count > 0 THEN
            RAISE EXCEPTION 'release_context_inconsistent' USING ERRCODE = 'P0001';
          END IF;
          IF active_enrollment_count = 0 THEN
            RAISE EXCEPTION 'release_context_scope_not_found' USING ERRCODE = 'P0002';
          ELSIF active_enrollment_count <> 1 THEN
            RAISE EXCEPTION 'release_context_inconsistent' USING ERRCODE = 'P0001';
          END IF;
          IF open_attendance_count = 0 THEN
            RAISE EXCEPTION 'child_not_on_site' USING ERRCODE = 'P0001';
          ELSIF open_attendance_count <> 1 THEN
            RAISE EXCEPTION 'release_context_inconsistent' USING ERRCODE = 'P0001';
          END IF;
          IF NOT room_scope_ready THEN
            RAISE EXCEPTION 'release_context_scope_not_found' USING ERRCODE = 'P0002';
          END IF;

          SELECT head.revision
            INTO projected_authority_revision
          FROM public.child_authority_heads AS head
          WHERE head.organization_id = actor_organization_id
            AND head.family_id = projected_family_id
            AND head.child_id = requested_child_id;
          projected_authority_revision := COALESCE(projected_authority_revision, 0);

          SELECT pg_catalog.jsonb_build_object(
            'input_schema_version', 'release-context-input-v1',
            'organization_id', actor_organization_id,
            'family_id', projected_family_id,
            'facility_id', requested_facility_id,
            'room_id', projected_room_id,
            'child_id', requested_child_id,
            'attendance_day_id', projected_attendance_day_id,
            'attendance_interval_id', projected_attendance_interval_id,
            'staff_shift_id', projected_shift_id,
            'evaluated_at', pg_catalog.to_char(
              evaluated_at_value AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            ),
            'authority_revision', projected_authority_revision,
            'people', COALESCE((
              SELECT pg_catalog.jsonb_agg(
                pg_catalog.jsonb_build_object(
                  'organization_id', person.organization_id,
                  'family_id', person.family_id,
                  'person_id', person.id,
                  'status', person.status,
                  'current_versions', COALESCE((
                    SELECT pg_catalog.jsonb_agg(
                      pg_catalog.jsonb_build_object(
                        'person_version_id', person_version.id,
                        'first_name', person_version.first_name,
                        'middle_name', person_version.middle_name,
                        'last_name', person_version.last_name,
                        'preferred_name', person_version.preferred_name,
                        'relationship_kind', person_version.relationship_kind,
                        'relationship_detail', person_version.relationship_detail
                      ) ORDER BY person_version.id::text
                    )
                    FROM public.family_authority_person_versions AS person_version
                    WHERE person_version.organization_id = person.organization_id
                      AND person_version.family_id = person.family_id
                      AND person_version.person_id = person.id
                      AND person_version.id = person.current_person_version_id
                  ), '[]'::jsonb)
                ) ORDER BY person.id::text
              )
              FROM public.family_authority_people AS person
              WHERE person.organization_id = actor_organization_id
                AND person.family_id = projected_family_id
                AND EXISTS (
                  SELECT 1
                  FROM public.child_release_authorizations AS person_authorization
                  WHERE person_authorization.organization_id = actor_organization_id
                    AND person_authorization.family_id = projected_family_id
                    AND person_authorization.child_id = requested_child_id
                    AND person_authorization.recipient_person_id = person.id
                    AND person_authorization.revoked_at IS NULL
                    AND person_authorization.effective_until > evaluated_at_value
                )
            ), '[]'::jsonb),
            'authorizations', COALESCE((
              SELECT pg_catalog.jsonb_agg(
                pg_catalog.jsonb_build_object(
                  'organization_id', authorization_record.organization_id,
                  'family_id', authorization_record.family_id,
                  'child_id', authorization_record.child_id,
                  'authorization_id', authorization_record.id,
                  'authorization_version', authorization_record.version,
                  'recipient_person_id', authorization_record.recipient_person_id,
                  'verification_policy_code', authorization_record.verification_policy_code,
                  'effective_from', pg_catalog.to_char(
                    authorization_record.effective_from AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'effective_until', pg_catalog.to_char(
                    authorization_record.effective_until AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'revoked_at', pg_catalog.to_char(
                    authorization_record.revoked_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'supporting_evidence', pg_catalog.jsonb_build_object(
                    'bound_assessment_decision', assessment.decision,
                    'bound_assessment_is_latest', NOT EXISTS (
                      SELECT 1
                      FROM public.family_authority_evidence_assessments AS later_assessment
                      WHERE later_assessment.organization_id = assessment.organization_id
                        AND later_assessment.family_id = assessment.family_id
                        AND later_assessment.evidence_id = assessment.evidence_id
                        AND later_assessment.version_number > assessment.version_number
                    ),
                    'evidence_expires_at', pg_catalog.to_char(
                      evidence.expires_at AT TIME ZONE 'UTC',
                      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ),
                    'scope_matches_authority_record',
                      evidence.organization_id = authorization_record.organization_id
                      AND evidence.family_id = authorization_record.family_id
                  )
                ) ORDER BY authorization_record.id::text
              )
              FROM public.child_release_authorizations AS authorization_record
              JOIN public.family_authority_evidence AS evidence
                ON evidence.organization_id = authorization_record.organization_id
               AND evidence.family_id = authorization_record.family_id
               AND evidence.id = authorization_record.basis_evidence_id
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id = authorization_record.organization_id
               AND assessment.family_id = authorization_record.family_id
               AND assessment.evidence_id = authorization_record.basis_evidence_id
               AND assessment.id = authorization_record.basis_evidence_assessment_id
              WHERE authorization_record.organization_id = actor_organization_id
                AND authorization_record.family_id = projected_family_id
                AND authorization_record.child_id = requested_child_id
                AND authorization_record.revoked_at IS NULL
                AND authorization_record.effective_until > evaluated_at_value
            ), '[]'::jsonb),
            'rules', COALESCE((
              SELECT pg_catalog.jsonb_agg(
                pg_catalog.jsonb_build_object(
                  'organization_id', rule_record.organization_id,
                  'family_id', rule_record.family_id,
                  'child_id', rule_record.child_id,
                  'rule_id', rule_record.id,
                  'rule_version', rule_record.version,
                  'rule_kind', rule_record.rule_kind,
                  'scope_kind', rule_record.scope_kind,
                  'scope_person_id', rule_record.scope_person_id,
                  'safe_explanation_code', rule_record.safe_explanation_code,
                  'effective_from', pg_catalog.to_char(
                    rule_record.effective_from AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'effective_until', pg_catalog.to_char(
                    rule_record.effective_until AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'revoked_at', pg_catalog.to_char(
                    rule_record.revoked_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                  ),
                  'supporting_evidence', pg_catalog.jsonb_build_object(
                    'bound_assessment_decision', assessment.decision,
                    'bound_assessment_is_latest', NOT EXISTS (
                      SELECT 1
                      FROM public.family_authority_evidence_assessments AS later_assessment
                      WHERE later_assessment.organization_id = assessment.organization_id
                        AND later_assessment.family_id = assessment.family_id
                        AND later_assessment.evidence_id = assessment.evidence_id
                        AND later_assessment.version_number > assessment.version_number
                    ),
                    'evidence_expires_at', pg_catalog.to_char(
                      evidence.expires_at AT TIME ZONE 'UTC',
                      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ),
                    'scope_matches_authority_record',
                      evidence.organization_id = rule_record.organization_id
                      AND evidence.family_id = rule_record.family_id
                  )
                ) ORDER BY rule_record.id::text
              )
              FROM public.child_release_rules AS rule_record
              JOIN public.family_authority_evidence AS evidence
                ON evidence.organization_id = rule_record.organization_id
               AND evidence.family_id = rule_record.family_id
               AND evidence.id = rule_record.basis_evidence_id
              JOIN public.family_authority_evidence_assessments AS assessment
                ON assessment.organization_id = rule_record.organization_id
               AND assessment.family_id = rule_record.family_id
               AND assessment.evidence_id = rule_record.basis_evidence_id
               AND assessment.id = rule_record.basis_evidence_assessment_id
              WHERE rule_record.organization_id = actor_organization_id
                AND rule_record.family_id = projected_family_id
                AND rule_record.child_id = requested_child_id
                AND rule_record.revoked_at IS NULL
                AND rule_record.effective_until > evaluated_at_value
            ), '[]'::jsonb)
          ) INTO result;
          RETURN result;
        END
        $projection$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {POSTGRES_PROJECTION} FROM PUBLIC")
    op.execute(
        f"""
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'caresync_basic_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION {POSTGRES_PROJECTION} TO caresync_basic_app;
          END IF;
        END
        $grant$
        """
    )


def upgrade() -> None:
    # A2's 40-character column cannot represent the 45-character executable
    # composite policy that its own check constraint already admits.
    _set_verification_policy_width(release_context_width=True)
    _set_system_release_permission(enabled=True)
    if op.get_bind().dialect.name == "postgresql":
        _install_postgres_invalidation()
        _install_postgres_projection()
    else:
        _install_sqlite_invalidation()


def downgrade() -> None:
    bind = op.get_bind()
    _preflight_a2_policy_width()
    if bind.dialect.name == "sqlite":
        destination_revision = context.get_revision_argument()
        if destination_revision not in {down_revision, "-1"}:
            raise RuntimeError(
                "0029B SQLite downgrade refused before DDL: first downgrade "
                "exactly to 0029A2_authority_activation, then start a separate "
                "downgrade command"
            )
        op.execute("DROP TRIGGER child_authority_heads_release_context_update")
        op.execute("DROP TRIGGER child_authority_heads_release_context_insert")
    else:
        op.execute(
            "DROP TRIGGER child_authority_heads_release_context_invalidated "
            "ON public.child_authority_heads"
        )
        op.execute(f"DROP FUNCTION {POSTGRES_PROJECTION}")
        op.execute("DROP FUNCTION public.caresync_release_context_from_authority_head()")
    _set_system_release_permission(enabled=False)
    _set_verification_policy_width(release_context_width=False)

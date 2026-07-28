"""Add fail-closed exact-retry transport registry commands.

Revision ID: 0032_transport_commands
Revises: 0031_driver_vehicle_registry
Create Date: 2026-07-21

The command layer can collect and independently review encrypted staff/vehicle
evidence.  It deliberately cannot grant operational driving or dispatch.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationReviewDecision,
    TransportRegistryCommandReceipt,
    TransportVehicleEvidenceReviewDecision,
    TransportVehicleEvidenceScanFact,
)

revision = "0032_transport_commands"
down_revision = "0031_driver_vehicle_registry"
branch_labels = None
depends_on = None

TABLES = (
    TransportRegistryCommandReceipt,
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationReviewDecision,
    TransportVehicleEvidenceReviewDecision,
    TransportVehicleEvidenceScanFact,
)

IMMUTABLE_TABLES = tuple(model.__tablename__ for model in TABLES)
POSTGRES_FUNCTIONS = (
    "caresync_0032_immutable_fact()",
    "caresync_0032_receipt_guard()",
    "caresync_0032_qualification_evidence_guard()",
    "caresync_0032_qualification_review_guard()",
    "caresync_0032_vehicle_review_guard()",
    "caresync_0032_vehicle_scan_guard()",
    "caresync_0032_execute_command(text,uuid,text,jsonb)",
)


def _normalize_sqlite_plate_part(value: str) -> str:
    """Mirror the SQLite trigger's ASCII-only plate normalization."""
    return "".join(
        character.lower() for character in value if character.isascii() and character.isalnum()
    )


def _preflight_postgres_0031_vehicle_plates() -> None:
    """Refuse legacy 0031 plate drift instead of mutating historical facts."""
    op.execute(
        """
        DO $preflight$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM public.transport_vehicles AS vehicle
            JOIN public.transport_vehicle_versions AS version
              ON version.organization_id=vehicle.organization_id
             AND version.vehicle_id=vehicle.id
             AND version.version_number=(
               SELECT max(latest.version_number)
               FROM public.transport_vehicle_versions AS latest
               WHERE latest.organization_id=vehicle.organization_id
                 AND latest.vehicle_id=vehicle.id
             )
            WHERE vehicle.retired_at IS NULL
              AND (
                pg_catalog.regexp_replace(
                  pg_catalog.upper(version.plate_jurisdiction),'[^A-Z0-9]','','g'
                )=''
                OR pg_catalog.regexp_replace(
                  pg_catalog.upper(version.plate_token),'[^A-Z0-9]','','g'
                )=''
              )
          ) THEN
            RAISE EXCEPTION
              '0032 upgrade refused: active vehicle has an empty normalized plate'
              USING ERRCODE='23514';
          END IF;
          IF EXISTS (
            SELECT 1
            FROM (
              SELECT vehicle.organization_id,
                pg_catalog.regexp_replace(
                  pg_catalog.upper(version.plate_jurisdiction),'[^A-Z0-9]','','g'
                ) AS normalized_jurisdiction,
                pg_catalog.regexp_replace(
                  pg_catalog.upper(version.plate_token),'[^A-Z0-9]','','g'
                ) AS normalized_plate
              FROM public.transport_vehicles AS vehicle
              JOIN public.transport_vehicle_versions AS version
                ON version.organization_id=vehicle.organization_id
               AND version.vehicle_id=vehicle.id
               AND version.version_number=(
                 SELECT max(latest.version_number)
                 FROM public.transport_vehicle_versions AS latest
                 WHERE latest.organization_id=vehicle.organization_id
                   AND latest.vehicle_id=vehicle.id
               )
              WHERE vehicle.retired_at IS NULL
            ) AS active_plate
            GROUP BY active_plate.organization_id,
              active_plate.normalized_jurisdiction,active_plate.normalized_plate
            HAVING count(*)>1
          ) THEN
            RAISE EXCEPTION
              '0032 upgrade refused: duplicate normalized active vehicle plate'
              USING ERRCODE='23514';
          END IF;
        END $preflight$
        """
    )


def _preflight_sqlite_0031_vehicle_plates(bind: sa.engine.Connection) -> None:
    """Apply the same fail-closed compatibility preflight on SQLite."""
    rows = bind.execute(
        sa.text(
            "SELECT vehicle.organization_id,vehicle.id AS vehicle_id,"
            "version.plate_jurisdiction,version.plate_token "
            "FROM transport_vehicles AS vehicle "
            "JOIN transport_vehicle_versions AS version "
            "ON version.organization_id=vehicle.organization_id "
            "AND version.vehicle_id=vehicle.id "
            "AND version.version_number=(SELECT max(latest.version_number) "
            "FROM transport_vehicle_versions AS latest "
            "WHERE latest.organization_id=vehicle.organization_id "
            "AND latest.vehicle_id=vehicle.id) "
            "WHERE vehicle.retired_at IS NULL"
        )
    ).mappings()
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        jurisdiction = _normalize_sqlite_plate_part(row["plate_jurisdiction"])
        plate = _normalize_sqlite_plate_part(row["plate_token"])
        if not jurisdiction or not plate:
            raise RuntimeError("0032 upgrade refused: active vehicle has an empty normalized plate")
        key = (str(row["organization_id"]), jurisdiction, plate)
        if key in seen:
            raise RuntimeError("0032 upgrade refused: duplicate normalized active vehicle plate")
        seen.add(key)


def _converge_postgres_0031_guards() -> None:
    """Replace guards hardened after the experimental 0031 cut was authored.

    Some source-only development databases can already be stamped at 0031 with
    the earlier guard bodies.  Replacing the functions here makes an in-place
    0031 -> 0032 upgrade converge with a fresh migration without touching any
    retained 0028 database.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.caresync_0031_authorization_guard()
        RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE total integer; distinct_total integer; matched integer;
          type_total integer; valid_total integer; licence_matches integer; member_user uuid;
          organization_timezone text; authorization_end_date date;
        BEGIN
          SELECT membership.user_id,organization.timezone
            INTO member_user,organization_timezone
          FROM public.organization_memberships AS membership
          JOIN public.organizations AS organization
            ON organization.id=membership.organization_id
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id
          FOR UPDATE OF membership,organization;
          IF member_user IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.reviewed_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 authorization actor or membership mismatch'
              USING ERRCODE='23514';
          END IF;
          IF NEW.decision_sequence<>COALESCE((SELECT max(decision_sequence)
            FROM public.staff_driver_authorization_decisions
            WHERE organization_id=NEW.organization_id
              AND membership_id=NEW.membership_id),0)+1 THEN
            RAISE EXCEPTION '0031 authorization sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.reviewed_at<COALESCE((SELECT max(reviewed_at)
            FROM public.staff_driver_authorization_decisions
            WHERE organization_id=NEW.organization_id
              AND membership_id=NEW.membership_id),NEW.reviewed_at) THEN
            RAISE EXCEPTION '0031 authorization review time is out of order'
              USING ERRCODE='23514';
          END IF;
          IF pg_catalog.jsonb_typeof(NEW.qualification_version_ids::jsonb)<>'array' THEN
            RAISE EXCEPTION '0031 authorization qualification list is invalid'
              USING ERRCODE='23514';
          END IF;
          SELECT count(*),count(DISTINCT replace(value,'-','')) INTO total,distinct_total
          FROM pg_catalog.jsonb_array_elements_text(
            NEW.qualification_version_ids::jsonb
          ) AS value;
          SELECT count(*),count(DISTINCT qualification.qualification_type)
            INTO matched,type_total
          FROM public.staff_driver_qualification_versions AS qualification
          JOIN pg_catalog.jsonb_array_elements_text(
            NEW.qualification_version_ids::jsonb
          ) AS item ON replace(item.value,'-','')=replace(qualification.id::text,'-','')
          WHERE qualification.organization_id=NEW.organization_id
            AND qualification.membership_id=NEW.membership_id;
          IF total<>distinct_total OR matched<>total OR type_total<>total THEN
            RAISE EXCEPTION '0031 authorization qualification ownership mismatch'
              USING ERRCODE='23514';
          END IF;
          IF NEW.decision='authorized' THEN
            BEGIN
              authorization_end_date := pg_catalog.timezone(
                organization_timezone,NEW.authorization_valid_until
              )::date;
            EXCEPTION WHEN invalid_parameter_value THEN
              RAISE EXCEPTION '0031 organization timezone is invalid'
                USING ERRCODE='23514';
            END;
            IF NEW.reviewed_by_user_id=member_user THEN
              RAISE EXCEPTION '0031 authorized decision requires an independent reviewer'
                USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.staff_driver_capability_versions AS capability
              WHERE capability.organization_id=NEW.organization_id
                AND capability.membership_id=NEW.membership_id
                AND capability.id=NEW.capability_version_id
                AND capability.status='declared'
                AND capability.effective_at<=NEW.reviewed_at
                AND capability.version_number=(
                  SELECT max(current_capability.version_number)
                  FROM public.staff_driver_capability_versions AS current_capability
                  WHERE current_capability.organization_id=NEW.organization_id
                    AND current_capability.membership_id=NEW.membership_id
                )
            ) THEN
              RAISE EXCEPTION '0031 authorization capability is not current'
                USING ERRCODE='23514';
            END IF;
            SELECT count(*) INTO licence_matches
            FROM public.staff_driver_qualification_versions AS qualification
            JOIN pg_catalog.jsonb_array_elements_text(
              NEW.qualification_version_ids::jsonb
            ) AS item ON replace(item.value,'-','')=replace(qualification.id::text,'-','')
            WHERE qualification.organization_id=NEW.organization_id
              AND qualification.membership_id=NEW.membership_id
              AND qualification.qualification_type='driver_licence'
              AND qualification.status='verified'
              AND qualification.expiry_date IS NOT NULL
              AND qualification.expiry_date>=authorization_end_date
              AND qualification.effective_at<=NEW.reviewed_at
              AND qualification.version_number=(
                SELECT max(current_qualification.version_number)
                FROM public.staff_driver_qualification_versions AS current_qualification
                WHERE current_qualification.organization_id=NEW.organization_id
                  AND current_qualification.membership_id=NEW.membership_id
                  AND current_qualification.qualification_type='driver_licence'
              );
            SELECT count(*) INTO valid_total
            FROM public.staff_driver_qualification_versions AS qualification
            JOIN pg_catalog.jsonb_array_elements_text(
              NEW.qualification_version_ids::jsonb
            ) AS item ON replace(item.value,'-','')=replace(qualification.id::text,'-','')
            WHERE qualification.organization_id=NEW.organization_id
              AND qualification.membership_id=NEW.membership_id
              AND qualification.status='verified'
              AND qualification.effective_at<=NEW.reviewed_at
              AND (qualification.expiry_date IS NULL
                OR qualification.expiry_date>=authorization_end_date)
              AND qualification.version_number=(
                SELECT max(current_qualification.version_number)
                FROM public.staff_driver_qualification_versions AS current_qualification
                WHERE current_qualification.organization_id=NEW.organization_id
                  AND current_qualification.membership_id=NEW.membership_id
                  AND current_qualification.qualification_type=
                    qualification.qualification_type
              );
            IF licence_matches<>1 OR valid_total<>total THEN
              RAISE EXCEPTION '0031 authorization lacks verified driver licence'
                USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.caresync_0031_vehicle_version_guard()
        RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE previous record; normalized_jurisdiction text; normalized_plate text;
        BEGIN
          PERFORM 1 FROM public.transport_vehicles AS vehicle
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
            AND vehicle.retired_at IS NULL FOR UPDATE;
          IF NOT FOUND OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 vehicle version actor or vehicle mismatch'
              USING ERRCODE='23514';
          END IF;
          SELECT version_number,effective_at INTO previous
          FROM public.transport_vehicle_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
          ORDER BY version_number DESC LIMIT 1;
          IF NEW.version_number<>COALESCE(previous.version_number,0)+1
             OR (previous.effective_at IS NOT NULL AND NEW.effective_at<previous.effective_at) THEN
            RAISE EXCEPTION '0031 vehicle version sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          normalized_jurisdiction := pg_catalog.regexp_replace(
            pg_catalog.upper(NEW.plate_jurisdiction),'[^A-Z0-9]','','g'
          );
          normalized_plate := pg_catalog.regexp_replace(
            pg_catalog.upper(NEW.plate_token),'[^A-Z0-9]','','g'
          );
          IF normalized_jurisdiction='' OR normalized_plate='' THEN
            RAISE EXCEPTION 'transport_vehicle_plate_conflict' USING ERRCODE='23514';
          END IF;
          PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            'caresync:transport:plate:' || NEW.organization_id::text || ':' ||
              normalized_jurisdiction || ':' || normalized_plate, 0
          ));
          IF EXISTS (
            SELECT 1
            FROM public.transport_vehicles AS other_vehicle
            JOIN public.transport_vehicle_versions AS other_version
              ON other_version.organization_id=other_vehicle.organization_id
             AND other_version.vehicle_id=other_vehicle.id
             AND other_version.version_number=(
               SELECT max(latest.version_number)
               FROM public.transport_vehicle_versions AS latest
               WHERE latest.organization_id=other_vehicle.organization_id
                 AND latest.vehicle_id=other_vehicle.id
             )
            WHERE other_vehicle.organization_id=NEW.organization_id
              AND other_vehicle.id<>NEW.vehicle_id
              AND other_vehicle.retired_at IS NULL
              AND pg_catalog.regexp_replace(
                pg_catalog.upper(other_version.plate_jurisdiction),'[^A-Z0-9]','','g'
              )=normalized_jurisdiction
              AND pg_catalog.regexp_replace(
                pg_catalog.upper(other_version.plate_token),'[^A-Z0-9]','','g'
              )=normalized_plate
          ) THEN
            RAISE EXCEPTION 'transport_vehicle_plate_conflict' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )


def _converge_sqlite_0031_guards() -> None:
    """Recreate changed 0031 triggers with their canonical hardened bodies."""
    op.execute("DROP TRIGGER IF EXISTS staff_driver_authorization_insert_guard")
    op.execute(
        """
        CREATE TRIGGER staff_driver_authorization_insert_guard
        BEFORE INSERT ON staff_driver_authorization_decisions
        WHEN NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.reviewed_by_user_id AND actor.status='active'
        ) OR NEW.decision_sequence<>COALESCE((
          SELECT max(decision_sequence) FROM staff_driver_authorization_decisions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),0)+1 OR NEW.reviewed_at<COALESCE((
          SELECT max(reviewed_at) FROM staff_driver_authorization_decisions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),NEW.reviewed_at) OR json_valid(NEW.qualification_version_ids)=0
          OR json_type(NEW.qualification_version_ids)<>'array'
          OR (SELECT count(*) FROM json_each(NEW.qualification_version_ids))<>
             (SELECT count(DISTINCT replace(value,'-',''))
              FROM json_each(NEW.qualification_version_ids))
          OR EXISTS (
            SELECT 1 FROM json_each(NEW.qualification_version_ids) AS item
            WHERE NOT EXISTS (
              SELECT 1 FROM staff_driver_qualification_versions AS qualification
              WHERE replace(qualification.id,'-','')=replace(item.value,'-','')
                AND qualification.organization_id=NEW.organization_id
                AND qualification.membership_id=NEW.membership_id
            )
          ) OR EXISTS (
            SELECT 1
            FROM staff_driver_qualification_versions AS qualification
            JOIN json_each(NEW.qualification_version_ids) AS item
              ON replace(qualification.id,'-','')=replace(item.value,'-','')
            WHERE qualification.organization_id=NEW.organization_id
              AND qualification.membership_id=NEW.membership_id
            GROUP BY qualification.qualification_type
            HAVING count(*)>1
          ) OR (NEW.decision='authorized' AND EXISTS (
            SELECT 1 FROM organization_memberships AS membership
            WHERE membership.organization_id=NEW.organization_id
              AND membership.id=NEW.membership_id
              AND membership.user_id=NEW.reviewed_by_user_id
          )) OR (NEW.decision='authorized' AND NOT EXISTS (
            SELECT 1 FROM staff_driver_capability_versions AS capability
            WHERE capability.organization_id=NEW.organization_id
              AND capability.membership_id=NEW.membership_id
              AND capability.id=NEW.capability_version_id
              AND capability.status='declared'
              AND capability.effective_at<=NEW.reviewed_at
              AND capability.version_number=(
                SELECT max(current_capability.version_number)
                FROM staff_driver_capability_versions AS current_capability
                WHERE current_capability.organization_id=NEW.organization_id
                  AND current_capability.membership_id=NEW.membership_id
              )
          )) OR (NEW.decision='authorized' AND NOT EXISTS (
            SELECT 1 FROM staff_driver_qualification_versions AS qualification
            JOIN json_each(NEW.qualification_version_ids) AS item
              ON replace(qualification.id,'-','')=replace(item.value,'-','')
            WHERE qualification.organization_id=NEW.organization_id
              AND qualification.membership_id=NEW.membership_id
              AND qualification.qualification_type='driver_licence'
              AND qualification.status='verified'
              AND qualification.expiry_date IS NOT NULL
              AND qualification.expiry_date>=caresync_local_date(
                NEW.authorization_valid_until,
                (SELECT timezone FROM organizations WHERE id=NEW.organization_id)
              )
              AND qualification.effective_at<=NEW.reviewed_at
              AND qualification.version_number=(
                SELECT max(current_qualification.version_number)
                FROM staff_driver_qualification_versions AS current_qualification
                WHERE current_qualification.organization_id=NEW.organization_id
                  AND current_qualification.membership_id=NEW.membership_id
                  AND current_qualification.qualification_type='driver_licence'
              )
          )) OR (NEW.decision='authorized' AND EXISTS (
            SELECT 1 FROM json_each(NEW.qualification_version_ids) AS item
            WHERE NOT EXISTS (
              SELECT 1 FROM staff_driver_qualification_versions AS qualification
              WHERE replace(qualification.id,'-','')=replace(item.value,'-','')
                AND qualification.organization_id=NEW.organization_id
                AND qualification.membership_id=NEW.membership_id
                AND qualification.status='verified'
                AND qualification.effective_at<=NEW.reviewed_at
                AND (qualification.expiry_date IS NULL
                  OR qualification.expiry_date>=caresync_local_date(
                    NEW.authorization_valid_until,
                    (SELECT timezone FROM organizations WHERE id=NEW.organization_id)
                  ))
                AND qualification.version_number=(
                  SELECT max(current_qualification.version_number)
                  FROM staff_driver_qualification_versions AS current_qualification
                  WHERE current_qualification.organization_id=NEW.organization_id
                    AND current_qualification.membership_id=NEW.membership_id
                    AND current_qualification.qualification_type=
                      qualification.qualification_type
                )
            )
          ))
        BEGIN
          SELECT RAISE(ABORT,'0031 authorization sequence or evidence is invalid');
        END
        """
    )
    op.execute("DROP TRIGGER IF EXISTS transport_vehicle_versions_plate_guard")
    op.execute(
        """
        CREATE TRIGGER transport_vehicle_versions_plate_guard
        BEFORE INSERT ON transport_vehicle_versions
        WHEN NEW.plate_token NOT GLOB '*[0-9A-Za-z]*'
          OR NEW.plate_jurisdiction NOT GLOB '*[0-9A-Za-z]*'
          OR EXISTS (
            SELECT 1
            FROM transport_vehicles AS other_vehicle
            JOIN transport_vehicle_versions AS other_version
              ON other_version.organization_id=other_vehicle.organization_id
             AND other_version.vehicle_id=other_vehicle.id
             AND other_version.version_number=(
               SELECT max(latest.version_number)
               FROM transport_vehicle_versions AS latest
               WHERE latest.organization_id=other_vehicle.organization_id
                 AND latest.vehicle_id=other_vehicle.id
             )
            WHERE other_vehicle.organization_id=NEW.organization_id
              AND other_vehicle.id<>NEW.vehicle_id
              AND other_vehicle.retired_at IS NULL
              AND (
                WITH RECURSIVE normalized(position,new_jurisdiction,new_plate,
                  existing_jurisdiction,existing_plate) AS (
                  SELECT 1,'','','',''
                  UNION ALL
                  SELECT position+1,
                    new_jurisdiction || CASE WHEN
                      substr(NEW.plate_jurisdiction,position,1) GLOB '[0-9A-Za-z]'
                      THEN lower(substr(NEW.plate_jurisdiction,position,1)) ELSE '' END,
                    new_plate || CASE WHEN
                      substr(NEW.plate_token,position,1) GLOB '[0-9A-Za-z]'
                      THEN lower(substr(NEW.plate_token,position,1)) ELSE '' END,
                    existing_jurisdiction || CASE WHEN
                      substr(other_version.plate_jurisdiction,position,1)
                        GLOB '[0-9A-Za-z]'
                      THEN lower(substr(other_version.plate_jurisdiction,position,1))
                      ELSE '' END,
                    existing_plate || CASE WHEN
                      substr(other_version.plate_token,position,1) GLOB '[0-9A-Za-z]'
                      THEN lower(substr(other_version.plate_token,position,1)) ELSE '' END
                  FROM normalized
                  WHERE position<=max(
                    length(NEW.plate_jurisdiction),length(NEW.plate_token),
                    length(other_version.plate_jurisdiction),length(other_version.plate_token)
                  )
                )
                SELECT new_jurisdiction=existing_jurisdiction
                  AND new_plate=existing_plate
                FROM normalized ORDER BY position DESC LIMIT 1
              )
          )
        BEGIN
          SELECT RAISE(ABORT,'transport_vehicle_plate_conflict');
        END
        """
    )


def _postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_immutable_fact() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          RAISE EXCEPTION '0032 immutable transport command fact cannot be changed'
            USING ERRCODE='23514';
        END $$
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0032_immutable_fact()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_receipt_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE result_bound boolean := false;
        BEGIN
          result_bound := CASE NEW.command_kind
            WHEN 'driver_declaration' THEN NEW.result_kind='driver_capability' AND EXISTS (
              SELECT 1 FROM public.staff_driver_capability_versions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id)
            WHEN 'qualification_evidence' THEN NEW.result_kind='driver_qualification' AND EXISTS (
              SELECT 1 FROM public.staff_driver_qualification_versions AS value
              JOIN public.staff_driver_qualification_evidence_objects AS evidence
                ON evidence.organization_id=value.organization_id
               AND evidence.membership_id=value.membership_id
               AND evidence.qualification_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.status='declared' AND value.recorded_by_user_id=NEW.actor_user_id
                AND evidence.recorded_by_user_id=NEW.actor_user_id)
            WHEN 'qualification_review' THEN NEW.result_kind='driver_qualification' AND EXISTS (
              SELECT 1 FROM public.staff_driver_qualification_versions AS value
              JOIN public.staff_driver_qualification_review_decisions AS review
                ON review.organization_id=value.organization_id
               AND review.membership_id=value.membership_id
               AND review.result_qualification_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id
                AND review.reviewed_by_user_id=NEW.actor_user_id)
            WHEN 'driver_authorization' THEN NEW.result_kind='driver_authorization' AND EXISTS (
              SELECT 1 FROM public.staff_driver_authorization_decisions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.reviewed_by_user_id=NEW.actor_user_id
                AND NOT value.operational_driver_ready AND NOT value.dispatch_authorized)
            WHEN 'vehicle_create' THEN NEW.result_kind='vehicle' AND EXISTS (
              SELECT 1 FROM public.transport_vehicles AS value
              JOIN public.transport_vehicle_versions AS version
                ON version.organization_id=value.organization_id AND version.vehicle_id=value.id
               AND version.version_number=1
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.created_by_user_id=NEW.actor_user_id
                AND version.recorded_by_user_id=NEW.actor_user_id)
            WHEN 'vehicle_retire' THEN NEW.result_kind='vehicle' AND EXISTS (
              SELECT 1 FROM public.transport_vehicles AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.retired_by_user_id=NEW.actor_user_id AND value.retired_at IS NOT NULL)
            WHEN 'vehicle_version' THEN NEW.result_kind='vehicle_version' AND EXISTS (
              SELECT 1 FROM public.transport_vehicle_versions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id)
            WHEN 'vehicle_evidence' THEN NEW.result_kind='vehicle_evidence' AND EXISTS (
              SELECT 1 FROM public.transport_vehicle_evidence_versions AS value
              JOIN public.transport_vehicle_evidence_scan_facts AS scan
                ON scan.organization_id=value.organization_id AND scan.vehicle_id=value.vehicle_id
               AND scan.evidence_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.status='provided' AND value.recorded_by_user_id=NEW.actor_user_id
                AND scan.recorded_by_user_id=NEW.actor_user_id AND scan.decision='clean')
            WHEN 'vehicle_evidence_review' THEN NEW.result_kind='vehicle_evidence' AND EXISTS (
              SELECT 1 FROM public.transport_vehicle_evidence_versions AS value
              JOIN public.transport_vehicle_evidence_review_decisions AS review
                ON review.organization_id=value.organization_id
               AND review.vehicle_id=value.vehicle_id
               AND review.result_evidence_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id
                AND review.reviewed_by_user_id=NEW.actor_user_id)
            WHEN 'readiness_evaluation' THEN NEW.result_kind='driver_readiness' AND EXISTS (
              SELECT 1 FROM public.staff_driver_readiness_decisions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.evaluated_by_user_id=NEW.actor_user_id
                AND NOT value.operational_driver_ready AND NOT value.dispatch_authorized)
            ELSE false END;
          IF NEW.operational_driver_ready OR NEW.dispatch_authorized OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.actor_user_id AND actor.status='active'
          ) OR NOT result_bound THEN
            RAISE EXCEPTION '0032 receipt actor, result, or authority boundary is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transport_registry_receipt_insert_guard BEFORE INSERT ON "
        "transport_registry_command_receipts FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0032_receipt_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_qualification_evidence_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.operational_driver_ready OR NEW.dispatch_authorized
             OR length(trim(NEW.scanner_engine))=0
             OR length(trim(NEW.scanner_version))=0
             OR NEW.storage_reference !~ '^[0-9a-f]{32}/[0-9a-f]{32}/[0-9a-f]{32}/v1[.]enc$'
             OR pg_catalog.split_part(NEW.storage_reference,'/',1)<>
                pg_catalog.replace(NEW.recorded_by_user_id::text,'-','')
             OR pg_catalog.split_part(NEW.storage_reference,'/',2)<>
                pg_catalog.replace(NEW.membership_id::text,'-','')
             OR NEW.scanned_at>pg_catalog.clock_timestamp()+interval '1 minute'
             OR NEW.scanned_at<pg_catalog.clock_timestamp()-interval '15 minutes'
             OR NOT EXISTS (
            SELECT 1 FROM public.staff_driver_qualification_versions AS qualification
            JOIN public.organization_memberships AS membership
              ON membership.organization_id=qualification.organization_id
             AND membership.id=qualification.membership_id
            WHERE qualification.organization_id=NEW.organization_id
              AND qualification.membership_id=NEW.membership_id
              AND qualification.id=NEW.qualification_version_id
              AND qualification.status='declared'
              AND qualification.evidence_reference_sha256=NEW.content_sha256
              AND membership.user_id=NEW.recorded_by_user_id
              AND membership.status='active'
          ) THEN
            RAISE EXCEPTION '0032 qualification evidence ownership is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_driver_qualification_evidence_insert_guard BEFORE INSERT ON "
        "staff_driver_qualification_evidence_objects FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0032_qualification_evidence_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_qualification_review_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE member_user uuid;
        BEGIN
          SELECT membership.user_id INTO member_user
          FROM public.organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id;
          IF member_user IS NULL OR member_user=NEW.reviewed_by_user_id
             OR NEW.operational_driver_ready OR NEW.dispatch_authorized OR NOT EXISTS (
               SELECT 1 FROM public.organization_memberships AS reviewer
               JOIN public.roles AS role ON role.organization_id=reviewer.organization_id
                 AND role.id=reviewer.role_id
               WHERE reviewer.organization_id=NEW.organization_id
                 AND reviewer.user_id=NEW.reviewed_by_user_id
                 AND reviewer.status='active'
                 AND role.permissions::jsonb @> '["transport:manage"]'::jsonb
             ) OR NOT EXISTS (
               SELECT 1
               FROM public.staff_driver_qualification_versions AS source
               JOIN public.staff_driver_qualification_evidence_objects AS evidence
                 ON evidence.organization_id=source.organization_id
                AND evidence.membership_id=source.membership_id
                AND evidence.qualification_version_id=source.id
               JOIN public.staff_driver_qualification_versions AS result
                 ON result.organization_id=source.organization_id
                AND result.membership_id=source.membership_id
                AND result.id=NEW.result_qualification_version_id
               WHERE source.organization_id=NEW.organization_id
                 AND source.membership_id=NEW.membership_id
                 AND source.id=NEW.source_qualification_version_id
                 AND source.status='declared'
                 AND result.version_number=source.version_number+1
                 AND result.version_number=(
                   SELECT max(latest.version_number)
                   FROM public.staff_driver_qualification_versions AS latest
                   WHERE latest.organization_id=source.organization_id
                     AND latest.membership_id=source.membership_id
                     AND latest.qualification_type=source.qualification_type
                 )
                 AND result.status=NEW.decision
                 AND evidence.recorded_by_user_id<>NEW.reviewed_by_user_id
                 AND result.qualification_type=source.qualification_type
                 AND result.jurisdiction IS NOT DISTINCT FROM source.jurisdiction
                 AND result.qualification_class IS NOT DISTINCT FROM source.qualification_class
                 AND result.identifier_last4 IS NOT DISTINCT FROM source.identifier_last4
                 AND result.issue_date IS NOT DISTINCT FROM source.issue_date
                 AND result.expiry_date IS NOT DISTINCT FROM source.expiry_date
                 AND result.evidence_reference_sha256=source.evidence_reference_sha256
                 AND result.recorded_by_user_id=NEW.reviewed_by_user_id
             ) THEN
            RAISE EXCEPTION '0032 qualification review is not independently evidence-bound'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_driver_qualification_review_insert_guard BEFORE INSERT ON "
        "staff_driver_qualification_review_decisions FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0032_qualification_review_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_vehicle_review_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE owner_user uuid;
        BEGIN
          SELECT membership.user_id INTO owner_user
          FROM public.transport_vehicles AS vehicle
          LEFT JOIN public.organization_memberships AS membership
            ON membership.organization_id=vehicle.organization_id
           AND membership.id=vehicle.staff_owner_membership_id
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id;
          IF owner_user=NEW.reviewed_by_user_id
             OR NEW.operational_driver_ready OR NEW.dispatch_authorized OR NOT EXISTS (
               SELECT 1 FROM public.organization_memberships AS reviewer
               JOIN public.roles AS role ON role.organization_id=reviewer.organization_id
                 AND role.id=reviewer.role_id
               WHERE reviewer.organization_id=NEW.organization_id
                 AND reviewer.user_id=NEW.reviewed_by_user_id
                 AND reviewer.status='active'
                 AND role.permissions::jsonb @> '["transport:manage"]'::jsonb
             ) OR NOT EXISTS (
               SELECT 1 FROM public.transport_vehicle_evidence_versions AS source
               JOIN public.transport_vehicle_evidence_versions AS result
                 ON result.organization_id=source.organization_id
                AND result.vehicle_id=source.vehicle_id
                AND result.id=NEW.result_evidence_version_id
               WHERE source.organization_id=NEW.organization_id
                 AND source.vehicle_id=NEW.vehicle_id
                 AND source.id=NEW.source_evidence_version_id
                 AND source.status='provided'
                 AND result.version_number=source.version_number+1
                 AND result.version_number=(
                   SELECT max(latest.version_number)
                   FROM public.transport_vehicle_evidence_versions AS latest
                   WHERE latest.organization_id=source.organization_id
                     AND latest.vehicle_id=source.vehicle_id
                     AND latest.evidence_type=source.evidence_type
                 )
                 AND source.recorded_by_user_id<>NEW.reviewed_by_user_id
                 AND result.status=NEW.decision
                 AND result.vehicle_version_id=source.vehicle_version_id
                 AND result.evidence_type=source.evidence_type
                 AND result.issue_date IS NOT DISTINCT FROM source.issue_date
                 AND result.expiry_date IS NOT DISTINCT FROM source.expiry_date
                 AND result.content_sha256=source.content_sha256
                 AND result.ciphertext_sha256=source.ciphertext_sha256
                 AND result.storage_reference=source.storage_reference
                 AND result.encryption_key_id=source.encryption_key_id
                 AND result.recorded_by_user_id=NEW.reviewed_by_user_id
             ) THEN
            RAISE EXCEPTION '0032 vehicle evidence review is not independently evidence-bound'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transport_vehicle_evidence_review_insert_guard BEFORE INSERT ON "
        "transport_vehicle_evidence_review_decisions FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0032_vehicle_review_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0032_vehicle_scan_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.decision<>'clean' OR NEW.scanner_signature IS NOT NULL
             OR length(trim(NEW.scanner_engine))=0
             OR length(trim(NEW.scanner_version))=0
             OR NEW.scanned_at>pg_catalog.clock_timestamp()+interval '1 minute'
             OR NEW.scanned_at<pg_catalog.clock_timestamp()-interval '15 minutes'
             OR NEW.operational_driver_ready OR NEW.dispatch_authorized OR NOT EXISTS (
               SELECT 1 FROM public.transport_vehicle_evidence_versions AS evidence
               WHERE evidence.organization_id=NEW.organization_id
                 AND evidence.vehicle_id=NEW.vehicle_id
                 AND evidence.id=NEW.evidence_version_id
                 AND evidence.status='provided'
                 AND evidence.recorded_by_user_id=NEW.recorded_by_user_id
                 AND evidence.storage_reference ~
                   '^[0-9a-f]{32}/[0-9a-f]{32}/[0-9a-f]{32}/v1[.]enc$'
                 AND pg_catalog.split_part(evidence.storage_reference,'/',1)=
                   pg_catalog.replace(NEW.recorded_by_user_id::text,'-','')
                 AND pg_catalog.split_part(evidence.storage_reference,'/',2)=
                   pg_catalog.replace(NEW.vehicle_id::text,'-','')
             ) THEN
            RAISE EXCEPTION '0032 vehicle scan provenance is invalid'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transport_vehicle_evidence_scan_insert_guard BEFORE INSERT ON "
        "transport_vehicle_evidence_scan_facts FOR EACH ROW EXECUTE FUNCTION "
        "public.caresync_0032_vehicle_scan_guard()"
    )


def _sqlite_guards() -> None:
    for table in IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_immutable_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT,'0032 immutable transport command fact "
                "cannot be changed'); END"
            )
    op.execute(
        """
        CREATE TRIGGER transport_registry_receipt_insert_guard
        BEFORE INSERT ON transport_registry_command_receipts
        WHEN NEW.operational_driver_ready<>0 OR NEW.dispatch_authorized<>0 OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.actor_user_id AND actor.status='active'
        ) OR NOT (
          (NEW.command_kind='driver_declaration' AND NEW.result_kind='driver_capability'
            AND EXISTS (SELECT 1 FROM staff_driver_capability_versions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='qualification_evidence'
            AND NEW.result_kind='driver_qualification' AND EXISTS (
              SELECT 1 FROM staff_driver_qualification_versions AS value
              JOIN staff_driver_qualification_evidence_objects AS evidence
                ON evidence.organization_id=value.organization_id
               AND evidence.membership_id=value.membership_id
               AND evidence.qualification_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.status='declared' AND value.recorded_by_user_id=NEW.actor_user_id
                AND evidence.recorded_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='qualification_review'
            AND NEW.result_kind='driver_qualification' AND EXISTS (
              SELECT 1 FROM staff_driver_qualification_versions AS value
              JOIN staff_driver_qualification_review_decisions AS review
                ON review.organization_id=value.organization_id
               AND review.membership_id=value.membership_id
               AND review.result_qualification_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id
                AND review.reviewed_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='driver_authorization' AND NEW.result_kind='driver_authorization'
            AND EXISTS (SELECT 1 FROM staff_driver_authorization_decisions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.reviewed_by_user_id=NEW.actor_user_id
                AND value.operational_driver_ready=0 AND value.dispatch_authorized=0))
          OR (NEW.command_kind='vehicle_create' AND NEW.result_kind='vehicle' AND EXISTS (
              SELECT 1 FROM transport_vehicles AS value
              JOIN transport_vehicle_versions AS version
                ON version.organization_id=value.organization_id
               AND version.vehicle_id=value.id AND version.version_number=1
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.created_by_user_id=NEW.actor_user_id
                AND version.recorded_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='vehicle_retire' AND NEW.result_kind='vehicle' AND EXISTS (
              SELECT 1 FROM transport_vehicles AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.retired_by_user_id=NEW.actor_user_id
                AND value.retired_at IS NOT NULL))
          OR (NEW.command_kind='vehicle_version' AND NEW.result_kind='vehicle_version'
            AND EXISTS (SELECT 1 FROM transport_vehicle_versions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='vehicle_evidence' AND NEW.result_kind='vehicle_evidence'
            AND EXISTS (SELECT 1 FROM transport_vehicle_evidence_versions AS value
              JOIN transport_vehicle_evidence_scan_facts AS scan
                ON scan.organization_id=value.organization_id
               AND scan.vehicle_id=value.vehicle_id AND scan.evidence_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.status='provided' AND value.recorded_by_user_id=NEW.actor_user_id
                AND scan.recorded_by_user_id=NEW.actor_user_id AND scan.decision='clean'))
          OR (NEW.command_kind='vehicle_evidence_review'
            AND NEW.result_kind='vehicle_evidence' AND EXISTS (
              SELECT 1 FROM transport_vehicle_evidence_versions AS value
              JOIN transport_vehicle_evidence_review_decisions AS review
                ON review.organization_id=value.organization_id
               AND review.vehicle_id=value.vehicle_id
               AND review.result_evidence_version_id=value.id
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.recorded_by_user_id=NEW.actor_user_id
                AND review.reviewed_by_user_id=NEW.actor_user_id))
          OR (NEW.command_kind='readiness_evaluation' AND NEW.result_kind='driver_readiness'
            AND EXISTS (SELECT 1 FROM staff_driver_readiness_decisions AS value
              WHERE value.organization_id=NEW.organization_id AND value.id=NEW.result_id
                AND value.evaluated_by_user_id=NEW.actor_user_id
                AND value.operational_driver_ready=0 AND value.dispatch_authorized=0))
        ) BEGIN
          SELECT RAISE(ABORT,'0032 receipt actor, result, or authority boundary is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_driver_qualification_evidence_insert_guard
        BEFORE INSERT ON staff_driver_qualification_evidence_objects
        WHEN NEW.operational_driver_ready<>0 OR NEW.dispatch_authorized<>0
          OR length(trim(NEW.scanner_engine))=0 OR length(trim(NEW.scanner_version))=0
          OR length(NEW.storage_reference)<>105
          OR substr(NEW.storage_reference,1,32)<>
             lower(replace(NEW.recorded_by_user_id,'-',''))
          OR substr(NEW.storage_reference,33,1)<>'/'
          OR substr(NEW.storage_reference,34,32)<>
             lower(replace(NEW.membership_id,'-',''))
          OR substr(NEW.storage_reference,66,1)<>'/'
          OR substr(NEW.storage_reference,67,32) GLOB '*[^0-9a-f]*'
          OR substr(NEW.storage_reference,99,7)<>'/v1.enc'
          OR datetime(NEW.scanned_at)>datetime('now','+1 minute')
          OR datetime(NEW.scanned_at)<datetime('now','-15 minutes')
          OR NOT EXISTS (
          SELECT 1 FROM staff_driver_qualification_versions AS qualification
          JOIN organization_memberships AS membership
            ON membership.organization_id=qualification.organization_id
           AND membership.id=qualification.membership_id
          WHERE qualification.organization_id=NEW.organization_id
            AND qualification.membership_id=NEW.membership_id
            AND qualification.id=NEW.qualification_version_id
            AND qualification.status='declared'
            AND qualification.evidence_reference_sha256=NEW.content_sha256
            AND membership.user_id=NEW.recorded_by_user_id
            AND membership.status='active'
        ) BEGIN SELECT RAISE(ABORT,'0032 qualification evidence ownership is invalid'); END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_driver_qualification_review_insert_guard
        BEFORE INSERT ON staff_driver_qualification_review_decisions
        WHEN NEW.operational_driver_ready<>0 OR NEW.dispatch_authorized<>0 OR EXISTS (
          SELECT 1 FROM organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id
            AND membership.user_id=NEW.reviewed_by_user_id
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS reviewer
          JOIN roles AS role ON role.organization_id=reviewer.organization_id
            AND role.id=reviewer.role_id
          WHERE reviewer.organization_id=NEW.organization_id
            AND reviewer.user_id=NEW.reviewed_by_user_id AND reviewer.status='active'
            AND instr(role.permissions,'transport:manage')>0
        ) OR NOT EXISTS (
          SELECT 1 FROM staff_driver_qualification_versions AS source
          JOIN staff_driver_qualification_evidence_objects AS evidence
            ON evidence.organization_id=source.organization_id
           AND evidence.membership_id=source.membership_id
           AND evidence.qualification_version_id=source.id
          JOIN staff_driver_qualification_versions AS result
            ON result.organization_id=source.organization_id
           AND result.membership_id=source.membership_id
           AND result.id=NEW.result_qualification_version_id
          WHERE source.organization_id=NEW.organization_id
            AND source.membership_id=NEW.membership_id
            AND source.id=NEW.source_qualification_version_id
            AND source.status='declared'
            AND result.version_number=source.version_number+1
            AND result.version_number=(
              SELECT max(latest.version_number)
              FROM staff_driver_qualification_versions AS latest
              WHERE latest.organization_id=source.organization_id
                AND latest.membership_id=source.membership_id
                AND latest.qualification_type=source.qualification_type
            )
            AND result.status=NEW.decision
            AND evidence.recorded_by_user_id<>NEW.reviewed_by_user_id
            AND result.qualification_type=source.qualification_type
            AND result.jurisdiction IS source.jurisdiction
            AND result.qualification_class IS source.qualification_class
            AND result.identifier_last4 IS source.identifier_last4
            AND result.issue_date IS source.issue_date AND result.expiry_date IS source.expiry_date
            AND result.evidence_reference_sha256=source.evidence_reference_sha256
            AND result.recorded_by_user_id=NEW.reviewed_by_user_id
        ) BEGIN
          SELECT RAISE(ABORT,'0032 qualification review is not independently evidence-bound');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER transport_vehicle_evidence_review_insert_guard
        BEFORE INSERT ON transport_vehicle_evidence_review_decisions
        WHEN NEW.operational_driver_ready<>0 OR NEW.dispatch_authorized<>0 OR EXISTS (
          SELECT 1 FROM transport_vehicles AS vehicle
          JOIN organization_memberships AS membership
            ON membership.organization_id=vehicle.organization_id
           AND membership.id=vehicle.staff_owner_membership_id
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
            AND membership.user_id=NEW.reviewed_by_user_id
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS reviewer
          JOIN roles AS role ON role.organization_id=reviewer.organization_id
            AND role.id=reviewer.role_id
          WHERE reviewer.organization_id=NEW.organization_id
            AND reviewer.user_id=NEW.reviewed_by_user_id AND reviewer.status='active'
            AND instr(role.permissions,'transport:manage')>0
        ) OR NOT EXISTS (
          SELECT 1 FROM transport_vehicle_evidence_versions AS source
          JOIN transport_vehicle_evidence_versions AS result
            ON result.organization_id=source.organization_id
           AND result.vehicle_id=source.vehicle_id
           AND result.id=NEW.result_evidence_version_id
          WHERE source.organization_id=NEW.organization_id AND source.vehicle_id=NEW.vehicle_id
            AND source.id=NEW.source_evidence_version_id
            AND source.status='provided'
            AND result.version_number=source.version_number+1
            AND result.version_number=(
              SELECT max(latest.version_number)
              FROM transport_vehicle_evidence_versions AS latest
              WHERE latest.organization_id=source.organization_id
                AND latest.vehicle_id=source.vehicle_id
                AND latest.evidence_type=source.evidence_type
            )
            AND source.recorded_by_user_id<>NEW.reviewed_by_user_id
            AND result.status=NEW.decision
            AND result.vehicle_version_id=source.vehicle_version_id
            AND result.evidence_type=source.evidence_type
            AND result.issue_date IS source.issue_date AND result.expiry_date IS source.expiry_date
            AND result.content_sha256=source.content_sha256
            AND result.ciphertext_sha256=source.ciphertext_sha256
            AND result.storage_reference=source.storage_reference
            AND result.encryption_key_id=source.encryption_key_id
            AND result.recorded_by_user_id=NEW.reviewed_by_user_id
        ) BEGIN
          SELECT RAISE(ABORT,'0032 vehicle review is not independently evidence-bound');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER transport_vehicle_evidence_scan_insert_guard
        BEFORE INSERT ON transport_vehicle_evidence_scan_facts
        WHEN NEW.decision<>'clean' OR NEW.scanner_signature IS NOT NULL
          OR NEW.operational_driver_ready<>0 OR NEW.dispatch_authorized<>0
          OR length(trim(NEW.scanner_engine))=0 OR length(trim(NEW.scanner_version))=0
          OR datetime(NEW.scanned_at)>datetime('now','+1 minute')
          OR datetime(NEW.scanned_at)<datetime('now','-15 minutes')
          OR NOT EXISTS (
            SELECT 1 FROM transport_vehicle_evidence_versions AS evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.vehicle_id=NEW.vehicle_id
              AND evidence.id=NEW.evidence_version_id AND evidence.status='provided'
              AND evidence.recorded_by_user_id=NEW.recorded_by_user_id
              AND length(evidence.storage_reference)=105
              AND substr(evidence.storage_reference,1,32)=
                  lower(replace(NEW.recorded_by_user_id,'-',''))
              AND substr(evidence.storage_reference,33,1)='/'
              AND substr(evidence.storage_reference,34,32)=
                  lower(replace(NEW.vehicle_id,'-',''))
              AND substr(evidence.storage_reference,66,1)='/'
              AND substr(evidence.storage_reference,67,32) NOT GLOB '*[^0-9a-f]*'
              AND substr(evidence.storage_reference,99,7)='/v1.enc'
          )
        BEGIN SELECT RAISE(ABORT,'0032 vehicle scan provenance is invalid'); END
        """
    )


def _install_postgres_writer() -> None:
    """Install the only runtime-write surface for 0032 PostgreSQL facts."""

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_0032_execute_command(
          requested_command_kind text,
          requested_operation_id uuid,
          requested_request_sha256 text,
          requested_payload jsonb
        )
        RETURNS TABLE(
          client_operation_id uuid,
          command_kind text,
          result_kind text,
          result_id uuid,
          committed_at timestamptz,
          exact_retry boolean,
          operational_driver_ready boolean,
          dispatch_authorized boolean
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $writer$
        DECLARE
          context_organization_id uuid;
          context_user_id uuid;
          organization_timezone text;
          local_today date;
          actor_is_manager boolean := false;
          now_value timestamptz;
          canonical_payload jsonb;
          computed_request_sha256 text;
          existing public.transport_registry_command_receipts%ROWTYPE;
          receipt_id uuid;
          created_result_kind text;
          created_result_id uuid;
          membership_id_value uuid;
          target_user_id uuid;
          version_value integer;
          sequence_value integer;
          source_qualification public.staff_driver_qualification_versions%ROWTYPE;
          current_qualification public.staff_driver_qualification_versions%ROWTYPE;
          source_vehicle_evidence public.transport_vehicle_evidence_versions%ROWTYPE;
          vehicle_value public.transport_vehicles%ROWTYPE;
          vehicle_version_value public.transport_vehicle_versions%ROWTYPE;
          capability_value public.staff_driver_capability_versions%ROWTYPE;
          current_capability_value public.staff_driver_capability_versions%ROWTYPE;
          authorization_value public.staff_driver_authorization_decisions%ROWTYPE;
          evidence_ids jsonb := '[]'::jsonb;
          reasons jsonb := '[]'::jsonb;
          expiry_attention boolean := false;
          expired_attention boolean := false;
          licence_expiry_attention boolean := false;
          licence_expired_attention boolean := false;
          vehicle_expiry_attention boolean := false;
          vehicle_expired_attention boolean := false;
          readiness_hard_block boolean := false;
          qualification_blocked_attention boolean := false;
          qualification_expiry_attention boolean := false;
          qualification_expired_attention boolean := false;
          qualification_id_value text;
          qualification_total integer := 0;
          qualification_matched integer := 0;
          qualification_owned integer := 0;
          qualification_type_total integer := 0;
          notification_user_id uuid;
          constraint_name_value text;
        BEGIN
          BEGIN
            context_organization_id := NULLIF(
              pg_catalog.current_setting('app.current_organization_id', true), ''
            )::uuid;
            context_user_id := NULLIF(
              pg_catalog.current_setting('app.current_user_id', true), ''
            )::uuid;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'transport_command_identity_unavailable' USING ERRCODE='42501';
          END;
          IF context_organization_id IS NULL OR context_user_id IS NULL
             OR requested_operation_id IS NULL OR requested_command_kind IS NULL
             OR requested_request_sha256 !~ '^[0-9a-f]{64}$'
             OR pg_catalog.jsonb_typeof(requested_payload)<>'object' THEN
            RAISE EXCEPTION 'transport_command_invalid' USING ERRCODE='22023';
          END IF;
          IF session_user NOT IN (
               'caresync_basic_app','caresync_transport_evidence_ingest'
             ) OR (session_user='caresync_basic_app' AND requested_command_kind IN (
               'qualification_evidence','vehicle_evidence'
             )) OR (session_user='caresync_transport_evidence_ingest'
               AND requested_command_kind NOT IN ('qualification_evidence','vehicle_evidence'))
          THEN
            RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
          END IF;

          PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            'caresync:transport:organization:' || context_organization_id::text, 0
          ));
          SELECT organization_record.timezone INTO organization_timezone
          FROM public.users AS actor
            JOIN public.organization_memberships AS membership
              ON membership.user_id=actor.id
             AND membership.organization_id=context_organization_id
             AND membership.status='active'
            JOIN public.organizations AS organization_record
              ON organization_record.id=membership.organization_id
             AND organization_record.status='active'
            JOIN public.roles AS actor_role
              ON actor_role.organization_id=membership.organization_id
             AND actor_role.id=membership.role_id
            WHERE actor.id=context_user_id AND actor.is_active=true
              AND actor.email_verified_at IS NOT NULL
          FOR UPDATE OF actor,membership,organization_record,actor_role;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
          END IF;
          SELECT EXISTS (
            SELECT 1 FROM public.organization_memberships AS membership
            JOIN public.roles AS role ON role.organization_id=membership.organization_id
              AND role.id=membership.role_id
            WHERE membership.organization_id=context_organization_id
              AND membership.user_id=context_user_id AND membership.status='active'
              AND role.permissions::jsonb @> '["transport:manage"]'::jsonb
          ) INTO actor_is_manager;

          canonical_payload := requested_payload - ARRAY[
            'result_id','version_id','evidence_object_id','review_id','scan_fact_id',
            'ciphertext_sha256','storage_reference','encryption_key_id','scanner_engine',
            'scanner_version','scanned_at'
          ];
          computed_request_sha256 := pg_catalog.encode(
            pg_catalog.sha256(pg_catalog.convert_to(canonical_payload::text,'UTF8')),'hex'
          );
          IF requested_request_sha256<>computed_request_sha256 THEN
            RAISE EXCEPTION 'transport_request_digest_mismatch' USING ERRCODE='22023';
          END IF;

          PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            context_organization_id::text || ':' || context_user_id::text || ':' ||
            requested_operation_id::text, 0
          ));
          SELECT receipt.* INTO existing
          FROM public.transport_registry_command_receipts AS receipt
          WHERE receipt.organization_id=context_organization_id
            AND receipt.actor_user_id=context_user_id
            AND receipt.client_operation_id=requested_operation_id;
          IF FOUND THEN
            IF existing.command_kind<>requested_command_kind
               OR existing.request_sha256<>requested_request_sha256 THEN
              RAISE EXCEPTION 'transport_operation_reused' USING ERRCODE='23505';
            END IF;
            RETURN QUERY SELECT existing.client_operation_id,existing.command_kind::text,
              existing.result_kind::text,existing.result_id,existing.committed_at,true,
              false,false;
            RETURN;
          END IF;

          now_value := pg_catalog.clock_timestamp();
          BEGIN
            local_today := pg_catalog.timezone(organization_timezone,now_value)::date;
          EXCEPTION WHEN invalid_parameter_value THEN
            RAISE EXCEPTION 'transport_organization_timezone_invalid' USING ERRCODE='23514';
          END;
          IF requested_command_kind='driver_declaration' THEN
            IF NOT requested_payload ?& ARRAY[
                 'result_id','membership_id','status','willing_to_drive',
                 'licence_jurisdiction','licence_jurisdiction_other','licence_class',
                 'vehicle_access','preferred_service_radius_km'
               ] OR requested_payload - ARRAY[
                 'result_id','membership_id','status','willing_to_drive',
                 'licence_jurisdiction','licence_jurisdiction_other','licence_class',
                 'vehicle_access','preferred_service_radius_km'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            membership_id_value := (requested_payload->>'membership_id')::uuid;
            IF NOT EXISTS (
              SELECT 1 FROM public.organization_memberships AS membership
              WHERE membership.organization_id=context_organization_id
                AND membership.id=membership_id_value
                AND membership.user_id=context_user_id AND membership.status='active'
              FOR UPDATE
            ) THEN RAISE EXCEPTION 'transport_command_scope_not_found' USING ERRCODE='42501';
            END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.staff_driver_capability_versions
            WHERE organization_id=context_organization_id AND membership_id=membership_id_value;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.staff_driver_capability_versions(
              id,organization_id,membership_id,version_number,status,willing_to_drive,
              licence_jurisdiction,licence_jurisdiction_other,licence_class,vehicle_access,
              preferred_service_radius_km,source_kind,source_screening_profile_version,
              effective_at,recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,membership_id_value,version_value,
              requested_payload->>'status',(requested_payload->>'willing_to_drive')::boolean,
              NULLIF(requested_payload->>'licence_jurisdiction',''),
              NULLIF(requested_payload->>'licence_jurisdiction_other',''),
              NULLIF(requested_payload->>'licence_class',''),requested_payload->>'vehicle_access',
              NULLIF(requested_payload->>'preferred_service_radius_km','')::integer,
              'staff_self',NULL,now_value,context_user_id,now_value
            );
            created_result_kind := 'driver_capability';

          ELSIF requested_command_kind='qualification_evidence' THEN
            IF NOT requested_payload ?& ARRAY[
                 'result_id','evidence_object_id','membership_id','qualification_type',
                 'jurisdiction','qualification_class','identifier_last4','issue_date',
                 'expiry_date','original_filename','media_type','byte_size','content_sha256',
                 'ciphertext_sha256','storage_reference','encryption_key_id','scanner_engine',
                 'scanner_version','scanned_at'
               ] OR requested_payload - ARRAY[
                 'result_id','evidence_object_id','membership_id','qualification_type',
                 'jurisdiction','qualification_class','identifier_last4','issue_date',
                 'expiry_date','original_filename','media_type','byte_size','content_sha256',
                 'ciphertext_sha256','storage_reference','encryption_key_id','scanner_engine',
                 'scanner_version','scanned_at'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            membership_id_value := (requested_payload->>'membership_id')::uuid;
            IF NOT EXISTS (
              SELECT 1 FROM public.organization_memberships AS membership
              WHERE membership.organization_id=context_organization_id
                AND membership.id=membership_id_value
                AND membership.user_id=context_user_id AND membership.status='active'
              FOR UPDATE
            ) THEN RAISE EXCEPTION 'transport_command_scope_not_found' USING ERRCODE='42501';
            END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.staff_driver_qualification_versions
            WHERE organization_id=context_organization_id AND membership_id=membership_id_value
              AND qualification_type=requested_payload->>'qualification_type';
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.staff_driver_qualification_versions(
              id,organization_id,membership_id,qualification_type,version_number,status,
              jurisdiction,qualification_class,identifier_last4,issue_date,expiry_date,
              source_screening_document_version_id,evidence_reference_sha256,effective_at,
              recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,membership_id_value,
              requested_payload->>'qualification_type',version_value,'declared',
              NULLIF(requested_payload->>'jurisdiction',''),
              NULLIF(requested_payload->>'qualification_class',''),
              NULLIF(requested_payload->>'identifier_last4',''),
              NULLIF(requested_payload->>'issue_date','')::date,
              NULLIF(requested_payload->>'expiry_date','')::date,NULL,
              requested_payload->>'content_sha256',now_value,context_user_id,now_value
            );
            INSERT INTO public.staff_driver_qualification_evidence_objects(
              id,organization_id,membership_id,qualification_version_id,original_filename,
              media_type,byte_size,content_sha256,ciphertext_sha256,storage_reference,
              encryption_key_id,scanner_engine,scanner_version,scanned_at,
              recorded_by_user_id,recorded_at,operational_driver_ready,dispatch_authorized
            ) VALUES (
              (requested_payload->>'evidence_object_id')::uuid,context_organization_id,
              membership_id_value,created_result_id,
              NULLIF(requested_payload->>'original_filename',''),requested_payload->>'media_type',
              (requested_payload->>'byte_size')::integer,requested_payload->>'content_sha256',
              requested_payload->>'ciphertext_sha256',requested_payload->>'storage_reference',
              requested_payload->>'encryption_key_id',requested_payload->>'scanner_engine',
              requested_payload->>'scanner_version',(requested_payload->>'scanned_at')::timestamptz,
              context_user_id,now_value,false,false
            );
            created_result_kind := 'driver_qualification';

          ELSIF requested_command_kind='qualification_review' THEN
            IF NOT actor_is_manager OR NOT requested_payload ?& ARRAY[
                 'result_id','review_id','membership_id','source_qualification_version_id',
                 'decision','reason_code'
               ] OR requested_payload - ARRAY[
                 'result_id','review_id','membership_id','source_qualification_version_id',
                 'decision','reason_code'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
            END IF;
            membership_id_value := (requested_payload->>'membership_id')::uuid;
            SELECT membership.user_id INTO target_user_id
            FROM public.organization_memberships AS membership
            WHERE membership.organization_id=context_organization_id
              AND membership.id=membership_id_value AND membership.status='active' FOR UPDATE;
            IF target_user_id IS NULL THEN
              RAISE EXCEPTION 'transport_command_scope_not_found' USING ERRCODE='42501';
            ELSIF target_user_id=context_user_id THEN
              RAISE EXCEPTION 'transport_independent_review_required' USING ERRCODE='42501';
            END IF;
            SELECT source.* INTO source_qualification
            FROM public.staff_driver_qualification_versions AS source
            JOIN public.staff_driver_qualification_evidence_objects AS evidence
              ON evidence.organization_id=source.organization_id
             AND evidence.membership_id=source.membership_id
             AND evidence.qualification_version_id=source.id
            WHERE source.organization_id=context_organization_id
              AND source.membership_id=membership_id_value
              AND source.id=(requested_payload->>'source_qualification_version_id')::uuid
              AND source.status='declared'
              AND source.version_number=(
                SELECT max(latest.version_number)
                FROM public.staff_driver_qualification_versions AS latest
                WHERE latest.organization_id=source.organization_id
                  AND latest.membership_id=source.membership_id
                  AND latest.qualification_type=source.qualification_type
              ) FOR UPDATE OF source;
            IF NOT FOUND OR source_qualification.recorded_by_user_id=context_user_id
               OR requested_payload->>'decision' NOT IN ('verified','rejected') THEN
              RAISE EXCEPTION 'transport_review_source_invalid' USING ERRCODE='23514';
            END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.staff_driver_qualification_versions
            WHERE organization_id=context_organization_id AND membership_id=membership_id_value
              AND qualification_type=source_qualification.qualification_type;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.staff_driver_qualification_versions(
              id,organization_id,membership_id,qualification_type,version_number,status,
              jurisdiction,qualification_class,identifier_last4,issue_date,expiry_date,
              source_screening_document_version_id,evidence_reference_sha256,effective_at,
              recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,membership_id_value,
              source_qualification.qualification_type,version_value,
              requested_payload->>'decision',source_qualification.jurisdiction,
              source_qualification.qualification_class,source_qualification.identifier_last4,
              source_qualification.issue_date,source_qualification.expiry_date,
              source_qualification.source_screening_document_version_id,
              source_qualification.evidence_reference_sha256,now_value,context_user_id,now_value
            );
            INSERT INTO public.staff_driver_qualification_review_decisions(
              id,organization_id,membership_id,source_qualification_version_id,
              result_qualification_version_id,decision,reason_code,reviewed_by_user_id,
              reviewed_at,operational_driver_ready,dispatch_authorized
            ) VALUES (
              (requested_payload->>'review_id')::uuid,context_organization_id,
              membership_id_value,source_qualification.id,created_result_id,
              requested_payload->>'decision',requested_payload->>'reason_code',
              context_user_id,now_value,false,false
            );
            created_result_kind := 'driver_qualification';

          ELSIF requested_command_kind='driver_authorization' THEN
            IF NOT actor_is_manager OR NOT requested_payload ?& ARRAY[
                 'result_id','membership_id','capability_version_id','qualification_version_ids',
                 'decision','reason_code','authorization_valid_from','authorization_valid_until'
               ] OR requested_payload - ARRAY[
                 'result_id','membership_id','capability_version_id','qualification_version_ids',
                 'decision','reason_code','authorization_valid_from','authorization_valid_until'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
            END IF;
            membership_id_value := (requested_payload->>'membership_id')::uuid;
            SELECT membership.user_id INTO target_user_id
            FROM public.organization_memberships AS membership
            WHERE membership.organization_id=context_organization_id
              AND membership.id=membership_id_value AND membership.status='active' FOR UPDATE;
            IF target_user_id IS NULL THEN
              RAISE EXCEPTION 'transport_command_scope_not_found' USING ERRCODE='42501';
            ELSIF target_user_id=context_user_id THEN
              RAISE EXCEPTION 'transport_independent_review_required' USING ERRCODE='42501';
            END IF;
            SELECT capability.* INTO capability_value
            FROM public.staff_driver_capability_versions AS capability
            WHERE capability.organization_id=context_organization_id
              AND capability.membership_id=membership_id_value
              AND capability.id=(requested_payload->>'capability_version_id')::uuid
            FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'transport_authorization_capability_mismatch'
                USING ERRCODE='23514';
            END IF;
            IF pg_catalog.jsonb_typeof(
                 requested_payload->'qualification_version_ids'
               )<>'array' THEN
              RAISE EXCEPTION 'transport_authorization_qualification_set_invalid'
                USING ERRCODE='23514';
            END IF;
            SELECT count(*),count(DISTINCT item.value),count(qualification.id),
                   count(DISTINCT qualification.qualification_type)
              INTO qualification_total,qualification_matched,
                   qualification_owned,qualification_type_total
            FROM pg_catalog.jsonb_array_elements_text(
              requested_payload->'qualification_version_ids'
            ) AS item(value)
            LEFT JOIN public.staff_driver_qualification_versions AS qualification
              ON qualification.organization_id=context_organization_id
             AND qualification.membership_id=membership_id_value
             AND qualification.id::text=item.value;
            IF qualification_total<>qualification_matched
               OR qualification_total<>qualification_owned
               OR qualification_total<>qualification_type_total THEN
              RAISE EXCEPTION 'transport_authorization_qualification_set_invalid'
                USING ERRCODE='23514';
            END IF;
            PERFORM 1 FROM public.staff_driver_qualification_versions AS qualification
            WHERE qualification.organization_id=context_organization_id
              AND qualification.membership_id=membership_id_value
              AND qualification.id::text IN (
                SELECT item.value FROM pg_catalog.jsonb_array_elements_text(
                  requested_payload->'qualification_version_ids'
                ) AS item(value)
              ) FOR UPDATE;
            IF requested_payload->>'decision'='authorized' THEN
              IF capability_value.status<>'declared'
                 OR capability_value.effective_at>now_value
                 OR capability_value.version_number<>(
                   SELECT max(latest.version_number)
                   FROM public.staff_driver_capability_versions AS latest
                   WHERE latest.organization_id=context_organization_id
                     AND latest.membership_id=membership_id_value
                 ) OR qualification_total=0
                 OR qualification_type_total<>qualification_total
                 OR NULLIF(requested_payload->>'authorization_valid_from','') IS NULL
                 OR NULLIF(requested_payload->>'authorization_valid_until','') IS NULL THEN
                RAISE EXCEPTION 'transport_authorization_qualification_set_invalid'
                  USING ERRCODE='23514';
              END IF;
              SELECT count(*) INTO qualification_matched
              FROM public.staff_driver_qualification_versions AS qualification
              JOIN pg_catalog.jsonb_array_elements_text(
                requested_payload->'qualification_version_ids'
              ) AS item(value) ON item.value=qualification.id::text
              WHERE qualification.organization_id=context_organization_id
                AND qualification.membership_id=membership_id_value
                AND qualification.status='verified'
                AND qualification.effective_at<=now_value
                AND qualification.version_number=(
                  SELECT max(latest.version_number)
                  FROM public.staff_driver_qualification_versions AS latest
                  WHERE latest.organization_id=qualification.organization_id
                    AND latest.membership_id=qualification.membership_id
                    AND latest.qualification_type=qualification.qualification_type
                )
                AND (qualification.expiry_date IS NULL OR
                  qualification.expiry_date>=
                    pg_catalog.timezone(
                      organization_timezone,
                      (requested_payload->>'authorization_valid_until')::timestamptz
                    )::date);
              IF qualification_matched<>qualification_total OR NOT EXISTS (
                SELECT 1
                FROM public.staff_driver_qualification_versions AS qualification
                JOIN pg_catalog.jsonb_array_elements_text(
                  requested_payload->'qualification_version_ids'
                ) AS item(value) ON item.value=qualification.id::text
                WHERE qualification.organization_id=context_organization_id
                  AND qualification.membership_id=membership_id_value
                  AND qualification.qualification_type='driver_licence'
              ) THEN
                RAISE EXCEPTION 'transport_authorization_qualification_set_invalid'
                  USING ERRCODE='23514';
              END IF;
            END IF;
            SELECT COALESCE(max(decision_sequence),0)+1 INTO sequence_value
            FROM public.staff_driver_authorization_decisions
            WHERE organization_id=context_organization_id AND membership_id=membership_id_value;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.staff_driver_authorization_decisions(
              id,organization_id,membership_id,decision_sequence,capability_version_id,
              qualification_version_ids,decision,reason_code,authorization_valid_from,
              authorization_valid_until,reviewed_by_user_id,reviewed_at,
              operational_driver_ready,dispatch_authorized
            ) VALUES (
              created_result_id,context_organization_id,membership_id_value,sequence_value,
              (requested_payload->>'capability_version_id')::uuid,
              requested_payload->'qualification_version_ids',requested_payload->>'decision',
              requested_payload->>'reason_code',
              NULLIF(requested_payload->>'authorization_valid_from','')::timestamptz,
              NULLIF(requested_payload->>'authorization_valid_until','')::timestamptz,
              context_user_id,now_value,false,false
            );
            created_result_kind := 'driver_authorization';

          ELSIF requested_command_kind='vehicle_create' THEN
            IF NOT requested_payload ?& ARRAY[
                 'result_id','version_id','owner_kind','staff_owner_membership_id','make','model',
                 'model_year','color','plate_token','plate_jurisdiction','passenger_capacity',
                 'child_passenger_capacity','wheelchair_accessible'
               ] OR requested_payload - ARRAY[
                 'result_id','version_id','owner_kind','staff_owner_membership_id','make','model',
                 'model_year','color','plate_token','plate_jurisdiction','passenger_capacity',
                 'child_passenger_capacity','wheelchair_accessible'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            membership_id_value := NULLIF(
              requested_payload->>'staff_owner_membership_id',''
            )::uuid;
            IF requested_payload->>'owner_kind'='organization' THEN
              IF NOT actor_is_manager OR membership_id_value IS NOT NULL THEN
                RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
              END IF;
            ELSIF requested_payload->>'owner_kind'='staff_personal' THEN
              SELECT membership.user_id INTO target_user_id
              FROM public.organization_memberships AS membership
              WHERE membership.organization_id=context_organization_id
                AND membership.id=membership_id_value AND membership.status='active';
              IF target_user_id IS NULL OR (
                target_user_id<>context_user_id AND NOT actor_is_manager
              )
              THEN RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501'; END IF;
            ELSE RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.transport_vehicles(
              id,organization_id,owner_kind,staff_owner_membership_id,created_by_user_id,created_at
            ) VALUES (
              created_result_id,context_organization_id,requested_payload->>'owner_kind',
              membership_id_value,context_user_id,now_value
            );
            INSERT INTO public.transport_vehicle_versions(
              id,organization_id,vehicle_id,version_number,make,model,model_year,color,
              plate_token,plate_jurisdiction,passenger_capacity,child_passenger_capacity,
              wheelchair_accessible,effective_at,recorded_by_user_id,recorded_at
            ) VALUES (
              (requested_payload->>'version_id')::uuid,context_organization_id,
              created_result_id,1,requested_payload->>'make',requested_payload->>'model',
              (requested_payload->>'model_year')::integer,NULLIF(requested_payload->>'color',''),
              requested_payload->>'plate_token',requested_payload->>'plate_jurisdiction',
              (requested_payload->>'passenger_capacity')::integer,
              (requested_payload->>'child_passenger_capacity')::integer,
              (requested_payload->>'wheelchair_accessible')::boolean,now_value,
              context_user_id,now_value
            );
            created_result_kind := 'vehicle';

          ELSIF requested_command_kind='vehicle_version' THEN
            IF NOT requested_payload ?& ARRAY[
                 'result_id','vehicle_id','make','model','model_year','color','plate_token',
                 'plate_jurisdiction','passenger_capacity','child_passenger_capacity',
                 'wheelchair_accessible'
               ] OR requested_payload - ARRAY[
                 'result_id','vehicle_id','make','model','model_year','color','plate_token',
                 'plate_jurisdiction','passenger_capacity','child_passenger_capacity',
                 'wheelchair_accessible'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            SELECT vehicle.* INTO vehicle_value FROM public.transport_vehicles AS vehicle
            WHERE vehicle.organization_id=context_organization_id
              AND vehicle.id=(requested_payload->>'vehicle_id')::uuid
              AND vehicle.retired_at IS NULL FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'transport_vehicle_not_found' USING ERRCODE='42501';
            ELSIF NOT actor_is_manager AND NOT EXISTS (
              SELECT 1 FROM public.organization_memberships AS owner
              WHERE owner.organization_id=context_organization_id
                AND owner.id=vehicle_value.staff_owner_membership_id
                AND owner.user_id=context_user_id AND owner.status='active'
            ) THEN RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501'; END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.transport_vehicle_versions
            WHERE organization_id=context_organization_id AND vehicle_id=vehicle_value.id;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.transport_vehicle_versions(
              id,organization_id,vehicle_id,version_number,make,model,model_year,color,
              plate_token,plate_jurisdiction,passenger_capacity,child_passenger_capacity,
              wheelchair_accessible,effective_at,recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,vehicle_value.id,version_value,
              requested_payload->>'make',requested_payload->>'model',
              (requested_payload->>'model_year')::integer,NULLIF(requested_payload->>'color',''),
              requested_payload->>'plate_token',requested_payload->>'plate_jurisdiction',
              (requested_payload->>'passenger_capacity')::integer,
              (requested_payload->>'child_passenger_capacity')::integer,
              (requested_payload->>'wheelchair_accessible')::boolean,now_value,
              context_user_id,now_value
            );
            created_result_kind := 'vehicle_version';

          ELSIF requested_command_kind='vehicle_retire' THEN
            IF NOT requested_payload ?& ARRAY['result_id','vehicle_id','reason_code']
               OR requested_payload - ARRAY['result_id','vehicle_id','reason_code']
                  <> '{}'::jsonb
               OR requested_payload->>'result_id'<>requested_payload->>'vehicle_id' THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            SELECT vehicle.* INTO vehicle_value FROM public.transport_vehicles AS vehicle
            WHERE vehicle.organization_id=context_organization_id
              AND vehicle.id=(requested_payload->>'vehicle_id')::uuid
              AND vehicle.retired_at IS NULL FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'transport_vehicle_not_found' USING ERRCODE='42501';
            ELSIF NOT actor_is_manager AND NOT EXISTS (
              SELECT 1 FROM public.organization_memberships AS owner
              WHERE owner.organization_id=context_organization_id
                AND owner.id=vehicle_value.staff_owner_membership_id
                AND owner.user_id=context_user_id AND owner.status='active'
            ) THEN RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501'; END IF;
            UPDATE public.transport_vehicles SET retired_at=now_value,
              retired_by_user_id=context_user_id,
              retirement_reason_code=requested_payload->>'reason_code'
            WHERE organization_id=context_organization_id AND id=vehicle_value.id;
            created_result_id := vehicle_value.id;
            created_result_kind := 'vehicle';

          ELSIF requested_command_kind='vehicle_evidence' THEN
            IF NOT requested_payload ?& ARRAY[
                 'result_id','scan_fact_id','vehicle_id','evidence_type','issue_date','expiry_date',
                 'original_filename','media_type','byte_size','content_sha256','ciphertext_sha256',
                 'storage_reference','encryption_key_id','scanner_engine','scanner_version','scanned_at'
               ] OR requested_payload - ARRAY[
                 'result_id','scan_fact_id','vehicle_id','evidence_type','issue_date','expiry_date',
                 'original_filename','media_type','byte_size','content_sha256','ciphertext_sha256',
                 'storage_reference','encryption_key_id','scanner_engine','scanner_version','scanned_at'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_payload_invalid' USING ERRCODE='22023';
            END IF;
            SELECT vehicle.* INTO vehicle_value FROM public.transport_vehicles AS vehicle
            WHERE vehicle.organization_id=context_organization_id
              AND vehicle.id=(requested_payload->>'vehicle_id')::uuid
              AND vehicle.retired_at IS NULL FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'transport_vehicle_not_found' USING ERRCODE='42501';
            ELSIF NOT actor_is_manager AND NOT EXISTS (
              SELECT 1 FROM public.organization_memberships AS owner
              WHERE owner.organization_id=context_organization_id
                AND owner.id=vehicle_value.staff_owner_membership_id
                AND owner.user_id=context_user_id AND owner.status='active'
            ) THEN RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501'; END IF;
            SELECT version.* INTO vehicle_version_value
            FROM public.transport_vehicle_versions AS version
            WHERE version.organization_id=context_organization_id
              AND version.vehicle_id=vehicle_value.id ORDER BY version.version_number DESC LIMIT 1;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'transport_vehicle_version_missing' USING ERRCODE='23514';
            END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.transport_vehicle_evidence_versions
            WHERE organization_id=context_organization_id AND vehicle_id=vehicle_value.id
              AND evidence_type=requested_payload->>'evidence_type';
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.transport_vehicle_evidence_versions(
              id,organization_id,vehicle_id,vehicle_version_id,evidence_type,version_number,
              status,issue_date,expiry_date,original_filename,media_type,byte_size,content_sha256,
              ciphertext_sha256,storage_reference,encryption_key_id,recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,vehicle_value.id,vehicle_version_value.id,
              requested_payload->>'evidence_type',version_value,'provided',
              NULLIF(requested_payload->>'issue_date','')::date,
              NULLIF(requested_payload->>'expiry_date','')::date,
              NULLIF(requested_payload->>'original_filename',''),requested_payload->>'media_type',
              (requested_payload->>'byte_size')::integer,requested_payload->>'content_sha256',
              requested_payload->>'ciphertext_sha256',requested_payload->>'storage_reference',
              requested_payload->>'encryption_key_id',context_user_id,now_value
            );
            INSERT INTO public.transport_vehicle_evidence_scan_facts(
              id,organization_id,vehicle_id,evidence_version_id,decision,scanner_engine,
              scanner_version,scanner_signature,scanned_at,recorded_by_user_id,
              operational_driver_ready,dispatch_authorized
            ) VALUES (
              (requested_payload->>'scan_fact_id')::uuid,context_organization_id,
              vehicle_value.id,created_result_id,'clean',requested_payload->>'scanner_engine',
              requested_payload->>'scanner_version',NULL,
              (requested_payload->>'scanned_at')::timestamptz,context_user_id,false,false
            );
            created_result_kind := 'vehicle_evidence';

          ELSIF requested_command_kind='vehicle_evidence_review' THEN
            IF NOT actor_is_manager OR NOT requested_payload ?& ARRAY[
                 'result_id','review_id','vehicle_id','source_evidence_version_id',
                 'decision','reason_code'
               ] OR requested_payload - ARRAY[
                 'result_id','review_id','vehicle_id','source_evidence_version_id',
                 'decision','reason_code'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
            END IF;
            SELECT vehicle.* INTO vehicle_value FROM public.transport_vehicles AS vehicle
            WHERE vehicle.organization_id=context_organization_id
              AND vehicle.id=(requested_payload->>'vehicle_id')::uuid
              AND vehicle.retired_at IS NULL FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'transport_vehicle_not_found' USING ERRCODE='42501';
            ELSIF EXISTS (
              SELECT 1 FROM public.organization_memberships AS owner
              WHERE owner.organization_id=context_organization_id
                AND owner.id=vehicle_value.staff_owner_membership_id
                AND owner.user_id=context_user_id
            ) THEN RAISE EXCEPTION 'transport_independent_review_required' USING ERRCODE='42501';
            END IF;
            SELECT source.* INTO source_vehicle_evidence
            FROM public.transport_vehicle_evidence_versions AS source
            JOIN public.transport_vehicle_evidence_scan_facts AS scan
              ON scan.organization_id=source.organization_id AND scan.vehicle_id=source.vehicle_id
             AND scan.evidence_version_id=source.id AND scan.decision='clean'
            WHERE source.organization_id=context_organization_id
              AND source.vehicle_id=vehicle_value.id
              AND source.id=(requested_payload->>'source_evidence_version_id')::uuid
              AND source.status='provided'
              AND source.version_number=(
                SELECT max(latest.version_number)
                FROM public.transport_vehicle_evidence_versions AS latest
                WHERE latest.organization_id=source.organization_id
                  AND latest.vehicle_id=source.vehicle_id
                  AND latest.evidence_type=source.evidence_type
              ) FOR UPDATE OF source;
            IF NOT FOUND OR source_vehicle_evidence.recorded_by_user_id=context_user_id
               OR requested_payload->>'decision' NOT IN ('verified','rejected') THEN
              RAISE EXCEPTION 'transport_review_source_invalid' USING ERRCODE='23514';
            END IF;
            SELECT COALESCE(max(version_number),0)+1 INTO version_value
            FROM public.transport_vehicle_evidence_versions
            WHERE organization_id=context_organization_id AND vehicle_id=vehicle_value.id
              AND evidence_type=source_vehicle_evidence.evidence_type;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.transport_vehicle_evidence_versions(
              id,organization_id,vehicle_id,vehicle_version_id,evidence_type,version_number,status,
              issue_date,expiry_date,original_filename,media_type,byte_size,content_sha256,
              ciphertext_sha256,storage_reference,encryption_key_id,recorded_by_user_id,recorded_at
            ) VALUES (
              created_result_id,context_organization_id,vehicle_value.id,
              source_vehicle_evidence.vehicle_version_id,source_vehicle_evidence.evidence_type,
              version_value,requested_payload->>'decision',source_vehicle_evidence.issue_date,
              source_vehicle_evidence.expiry_date,source_vehicle_evidence.original_filename,
              source_vehicle_evidence.media_type,source_vehicle_evidence.byte_size,
              source_vehicle_evidence.content_sha256,source_vehicle_evidence.ciphertext_sha256,
              source_vehicle_evidence.storage_reference,source_vehicle_evidence.encryption_key_id,
              context_user_id,now_value
            );
            INSERT INTO public.transport_vehicle_evidence_review_decisions(
              id,organization_id,vehicle_id,source_evidence_version_id,
              result_evidence_version_id,decision,reason_code,reviewed_by_user_id,reviewed_at,
              operational_driver_ready,dispatch_authorized
            ) VALUES (
              (requested_payload->>'review_id')::uuid,context_organization_id,vehicle_value.id,
              source_vehicle_evidence.id,created_result_id,requested_payload->>'decision',
              requested_payload->>'reason_code',context_user_id,now_value,false,false
            );
            created_result_kind := 'vehicle_evidence';

          ELSIF requested_command_kind='readiness_evaluation' THEN
            IF NOT actor_is_manager OR NOT requested_payload ?& ARRAY[
                 'result_id','membership_id','vehicle_id'
               ] OR requested_payload - ARRAY[
                 'result_id','membership_id','vehicle_id'
               ] <> '{}'::jsonb THEN
              RAISE EXCEPTION 'transport_command_forbidden' USING ERRCODE='42501';
            END IF;
            membership_id_value := (requested_payload->>'membership_id')::uuid;
            SELECT membership.user_id INTO target_user_id
            FROM public.organization_memberships AS membership
            WHERE membership.organization_id=context_organization_id
              AND membership.id=membership_id_value AND membership.status='active' FOR UPDATE;
            IF target_user_id IS NULL THEN
              RAISE EXCEPTION 'transport_command_scope_not_found' USING ERRCODE='42501';
            ELSIF target_user_id=context_user_id THEN
              RAISE EXCEPTION 'transport_independent_review_required' USING ERRCODE='42501';
            END IF;
            SELECT authorization_record.* INTO authorization_value
            FROM public.staff_driver_authorization_decisions AS authorization_record
            WHERE authorization_record.organization_id=context_organization_id
              AND authorization_record.membership_id=membership_id_value
            ORDER BY authorization_record.decision_sequence DESC LIMIT 1 FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'transport_readiness_requires_authorization' USING ERRCODE='23514';
            END IF;
            SELECT capability.* INTO capability_value
            FROM public.staff_driver_capability_versions AS capability
            WHERE capability.organization_id=context_organization_id
              AND capability.membership_id=membership_id_value
              AND capability.id=authorization_value.capability_version_id
            FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'transport_readiness_requires_capability' USING ERRCODE='23514';
            END IF;
            SELECT capability.* INTO current_capability_value
            FROM public.staff_driver_capability_versions AS capability
            WHERE capability.organization_id=context_organization_id
              AND capability.membership_id=membership_id_value
            ORDER BY capability.version_number DESC LIMIT 1 FOR UPDATE;
            IF current_capability_value.id<>capability_value.id THEN
              reasons := reasons || '["capability_changed_since_authorization"]'::jsonb;
              readiness_hard_block := true;
            ELSIF current_capability_value.status<>'declared' THEN
              reasons := reasons || '["capability_withdrawn"]'::jsonb;
              readiness_hard_block := true;
            END IF;
            IF authorization_value.decision<>'authorized'
               OR authorization_value.authorization_valid_from IS NULL
               OR authorization_value.authorization_valid_until IS NULL
               OR authorization_value.authorization_valid_from>now_value
               OR authorization_value.authorization_valid_until<=now_value THEN
              reasons := reasons || '["authorization_not_current"]'::jsonb;
              readiness_hard_block := true;
            END IF;
            IF pg_catalog.jsonb_typeof(
                 authorization_value.qualification_version_ids::jsonb
               ) IS DISTINCT FROM 'array' THEN
              reasons := reasons || '["qualification_binding_invalid"]'::jsonb;
              qualification_blocked_attention := true;
            ELSE
              SELECT count(*),count(DISTINCT item.value),count(qualification.id),
                     count(DISTINCT qualification.qualification_type)
                INTO qualification_total,qualification_matched,
                     qualification_owned,qualification_type_total
              FROM pg_catalog.jsonb_array_elements_text(
                authorization_value.qualification_version_ids::jsonb
              ) AS item(value)
              LEFT JOIN public.staff_driver_qualification_versions AS qualification
                ON qualification.organization_id=context_organization_id
               AND qualification.membership_id=membership_id_value
               AND qualification.id::text=item.value;
              IF qualification_total<>qualification_matched
                 OR qualification_total<>qualification_owned
                 OR qualification_total<>qualification_type_total THEN
                reasons := reasons || '["qualification_binding_invalid"]'::jsonb;
                qualification_blocked_attention := true;
              END IF;
              PERFORM 1
              FROM public.staff_driver_qualification_versions AS qualification
              WHERE qualification.organization_id=context_organization_id
                AND qualification.membership_id=membership_id_value
                AND qualification.id::text IN (
                  SELECT item.value
                  FROM pg_catalog.jsonb_array_elements_text(
                    authorization_value.qualification_version_ids::jsonb
                  ) AS item(value)
                )
              FOR UPDATE;
              FOR source_qualification IN
                SELECT qualification.*
                FROM public.staff_driver_qualification_versions AS qualification
                JOIN pg_catalog.jsonb_array_elements_text(
                  authorization_value.qualification_version_ids::jsonb
                ) AS item(value) ON item.value=qualification.id::text
                WHERE qualification.organization_id=context_organization_id
                  AND qualification.membership_id=membership_id_value
                  AND qualification.qualification_type<>'driver_licence'
                ORDER BY qualification.qualification_type
              LOOP
                SELECT qualification.* INTO current_qualification
                FROM public.staff_driver_qualification_versions AS qualification
                WHERE qualification.organization_id=context_organization_id
                  AND qualification.membership_id=membership_id_value
                  AND qualification.qualification_type=
                    source_qualification.qualification_type
                ORDER BY qualification.version_number DESC LIMIT 1 FOR UPDATE;
                IF NOT FOUND THEN
                  reasons := reasons || pg_catalog.jsonb_build_array(
                    'qualification_missing:' || source_qualification.qualification_type
                  );
                  qualification_blocked_attention := true;
                ELSE
                  IF current_qualification.id<>source_qualification.id THEN
                    reasons := reasons || pg_catalog.jsonb_build_array(
                      'qualification_changed_since_authorization:' ||
                        source_qualification.qualification_type
                    );
                    qualification_blocked_attention := true;
                  END IF;
                  IF current_qualification.status<>'verified'
                     OR current_qualification.effective_at>now_value THEN
                    reasons := reasons || pg_catalog.jsonb_build_array(
                      'qualification_unverified:' || source_qualification.qualification_type
                    );
                    qualification_blocked_attention := true;
                  END IF;
                  IF current_qualification.expiry_date<local_today THEN
                    reasons := reasons || pg_catalog.jsonb_build_array(
                      'qualification_expired:' || source_qualification.qualification_type
                    );
                    qualification_expired_attention := true;
                    qualification_blocked_attention := true;
                  ELSIF current_qualification.expiry_date BETWEEN local_today
                        AND local_today+30 THEN
                    reasons := reasons || pg_catalog.jsonb_build_array(
                      'qualification_expiring_soon:' ||
                        source_qualification.qualification_type
                    );
                    qualification_expiry_attention := true;
                  END IF;
                END IF;
              END LOOP;
            END IF;
            SELECT qualification.* INTO source_qualification
            FROM public.staff_driver_qualification_versions AS qualification
            WHERE qualification.organization_id=context_organization_id
              AND qualification.membership_id=membership_id_value
              AND qualification.qualification_type='driver_licence'
            ORDER BY qualification.version_number DESC LIMIT 1 FOR UPDATE;
            IF NOT FOUND THEN
              reasons := reasons || '["driver_licence_missing"]'::jsonb;
              qualification_blocked_attention := true;
            ELSE
              IF source_qualification.status<>'verified'
                 OR source_qualification.effective_at>now_value THEN
                reasons := reasons || '["driver_licence_unverified"]'::jsonb;
                qualification_blocked_attention := true;
              END IF;
              IF NOT authorization_value.qualification_version_ids::jsonb @>
                   pg_catalog.jsonb_build_array(source_qualification.id::text) THEN
                reasons := reasons || '["driver_licence_changed_since_authorization"]'::jsonb;
                qualification_blocked_attention := true;
              END IF;
              IF source_qualification.expiry_date<local_today THEN
                licence_expired_attention := true;
                qualification_blocked_attention := true;
                reasons := reasons || '["driver_licence_expired"]'::jsonb;
              ELSIF source_qualification.expiry_date BETWEEN local_today
                    AND local_today+30 THEN
                licence_expiry_attention := true;
                reasons := reasons || '["driver_licence_expiring_soon"]'::jsonb;
              END IF;
            END IF;
            IF NULLIF(requested_payload->>'vehicle_id','') IS NOT NULL THEN
              SELECT vehicle.* INTO vehicle_value FROM public.transport_vehicles AS vehicle
              WHERE vehicle.organization_id=context_organization_id
                AND vehicle.id=(requested_payload->>'vehicle_id')::uuid
                AND vehicle.retired_at IS NULL AND (vehicle.owner_kind='organization'
                  OR vehicle.staff_owner_membership_id=membership_id_value)
              FOR UPDATE;
              IF NOT FOUND THEN
                RAISE EXCEPTION 'transport_vehicle_not_found' USING ERRCODE='42501';
              END IF;
              SELECT version.* INTO vehicle_version_value
              FROM public.transport_vehicle_versions AS version
              WHERE version.organization_id=context_organization_id
                AND version.vehicle_id=vehicle_value.id
              ORDER BY version.version_number DESC LIMIT 1 FOR UPDATE;
              IF NOT FOUND THEN
                RAISE EXCEPTION 'transport_vehicle_version_missing' USING ERRCODE='23514';
              END IF;
              PERFORM 1 FROM public.transport_vehicle_evidence_versions AS evidence
              WHERE evidence.organization_id=context_organization_id
                AND evidence.vehicle_id=vehicle_value.id FOR UPDATE;
              SELECT COALESCE(jsonb_agg(latest.id::text),'[]'::jsonb),
                     COALESCE(bool_or(latest.expiry_date<local_today),false),
                     COALESCE(bool_or(latest.expiry_date BETWEEN local_today
                       AND local_today+30),false)
                INTO evidence_ids,vehicle_expired_attention,vehicle_expiry_attention
              FROM (
                SELECT DISTINCT ON (evidence.evidence_type) evidence.id,evidence.status,
                       evidence.expiry_date,evidence.evidence_type,
                       evidence.vehicle_version_id
                FROM public.transport_vehicle_evidence_versions AS evidence
                WHERE evidence.organization_id=context_organization_id
                  AND evidence.vehicle_id=vehicle_value.id
                ORDER BY evidence.evidence_type,evidence.version_number DESC
              ) AS latest
              WHERE latest.status='verified'
                AND latest.vehicle_version_id=vehicle_version_value.id;
              IF NOT EXISTS (
                SELECT 1 FROM public.transport_vehicle_evidence_versions AS evidence
                WHERE evidence.organization_id=context_organization_id
                  AND evidence.vehicle_id=vehicle_value.id
                  AND evidence.evidence_type='registration' AND evidence.status='verified'
                  AND evidence.vehicle_version_id=vehicle_version_value.id
                  AND evidence.version_number=(SELECT max(current.version_number)
                    FROM public.transport_vehicle_evidence_versions AS current
                    WHERE current.organization_id=context_organization_id
                      AND current.vehicle_id=vehicle_value.id
                      AND current.evidence_type='registration')
                  AND evidence.expiry_date>=local_today
              ) OR NOT EXISTS (
                SELECT 1 FROM public.transport_vehicle_evidence_versions AS evidence
                WHERE evidence.organization_id=context_organization_id
                  AND evidence.vehicle_id=vehicle_value.id
                  AND evidence.evidence_type='insurance' AND evidence.status='verified'
                  AND evidence.vehicle_version_id=vehicle_version_value.id
                  AND evidence.version_number=(SELECT max(current.version_number)
                    FROM public.transport_vehicle_evidence_versions AS current
                    WHERE current.organization_id=context_organization_id
                      AND current.vehicle_id=vehicle_value.id
                      AND current.evidence_type='insurance')
                  AND evidence.expiry_date>=local_today
              ) THEN
                reasons := reasons || '["vehicle_evidence_incomplete"]'::jsonb;
                readiness_hard_block := true;
              END IF;
              IF vehicle_expired_attention THEN
                reasons := reasons || '["vehicle_evidence_expired"]'::jsonb;
              ELSIF vehicle_expiry_attention THEN
                reasons := reasons || '["vehicle_evidence_expiring_soon"]'::jsonb;
              END IF;
            ELSE
              reasons := reasons || '["vehicle_not_selected_for_evaluation"]'::jsonb;
            END IF;
            IF pg_catalog.jsonb_array_length(reasons)=0 THEN
              reasons := '["operational_transport_release_not_enabled"]'::jsonb;
            END IF;
            SELECT COALESCE(max(decision_sequence),0)+1 INTO sequence_value
            FROM public.staff_driver_readiness_decisions
            WHERE organization_id=context_organization_id AND membership_id=membership_id_value;
            created_result_id := (requested_payload->>'result_id')::uuid;
            INSERT INTO public.staff_driver_readiness_decisions(
              id,organization_id,membership_id,decision_sequence,capability_version_id,
              authorization_decision_id,vehicle_id,vehicle_version_id,
              vehicle_evidence_version_ids,decision,reason_codes,evaluated_by_user_id,
              evaluated_at,operational_driver_ready,dispatch_authorized
            ) VALUES (
              created_result_id,context_organization_id,membership_id_value,sequence_value,
              capability_value.id,authorization_value.id,vehicle_value.id,
              vehicle_version_value.id,evidence_ids,
              CASE WHEN readiness_hard_block OR qualification_blocked_attention
                     OR licence_expired_attention OR qualification_expired_attention
                     OR vehicle_expired_attention
                THEN 'blocked' ELSE 'needs_review' END,
              reasons,context_user_id,now_value,false,false
            );
            IF licence_expired_attention OR licence_expiry_attention
               OR qualification_expired_attention OR qualification_expiry_attention
               OR vehicle_expired_attention OR vehicle_expiry_attention THEN
              FOR notification_user_id IN
                SELECT target_user_id UNION SELECT membership.user_id
                FROM public.organization_memberships AS membership
                JOIN public.roles AS role ON role.organization_id=membership.organization_id
                  AND role.id=membership.role_id
                WHERE membership.organization_id=context_organization_id
                  AND membership.status='active'
                  AND role.permissions::jsonb @> '["transport:manage"]'::jsonb
              LOOP
                IF licence_expired_attention OR licence_expiry_attention THEN
                  BEGIN
                    INSERT INTO public.user_notifications(
                      id,user_id,organization_id,event_key,category,severity,title,body,
                      action_path,action_entity_type,action_entity_id,created_at
                    ) VALUES (
                      pg_catalog.gen_random_uuid(),notification_user_id,context_organization_id,
                      'driver-licence-expiry:' || membership_id_value::text || ':' ||
                        local_today::text || ':' ||
                        CASE WHEN licence_expired_attention THEN 'expired' ELSE 'warning' END,
                      'credential',
                      CASE WHEN licence_expired_attention THEN 'critical' ELSE 'warning' END,
                      CASE WHEN licence_expired_attention
                        THEN 'Driver licence expired' ELSE 'Driver licence expires soon' END,
                      CASE WHEN licence_expired_attention
                        THEN 'The current verified driver licence has expired.'
                        ELSE 'The current verified driver licence expires within 30 days.' END,
                      '/transport-registry','transport_registry',created_result_id,now_value
                    );
                  EXCEPTION WHEN unique_violation THEN
                    GET STACKED DIAGNOSTICS constraint_name_value = CONSTRAINT_NAME;
                    IF constraint_name_value<>'uq_user_notifications_event' THEN RAISE;
                    END IF;
                  END;
                END IF;
                IF qualification_expired_attention OR qualification_expiry_attention THEN
                  BEGIN
                    INSERT INTO public.user_notifications(
                      id,user_id,organization_id,event_key,category,severity,title,body,
                      action_path,action_entity_type,action_entity_id,created_at
                    ) VALUES (
                      pg_catalog.gen_random_uuid(),notification_user_id,context_organization_id,
                      'driver-qualification-expiry:' || membership_id_value::text || ':' ||
                        local_today::text || ':' ||
                        CASE WHEN qualification_expired_attention
                          THEN 'expired' ELSE 'warning' END,
                      'credential',
                      CASE WHEN qualification_expired_attention
                        THEN 'critical' ELSE 'warning' END,
                      CASE WHEN qualification_expired_attention
                        THEN 'Driver qualification expired'
                        ELSE 'Driver qualification expires soon' END,
                      CASE WHEN qualification_expired_attention
                        THEN 'A current authorization-bound driver qualification has expired.'
                        ELSE 'A current authorization-bound driver qualification expires within '
                          || '30 days.' END,
                      '/transport-registry','transport_registry',created_result_id,now_value
                    );
                  EXCEPTION WHEN unique_violation THEN
                    GET STACKED DIAGNOSTICS constraint_name_value = CONSTRAINT_NAME;
                    IF constraint_name_value<>'uq_user_notifications_event' THEN RAISE;
                    END IF;
                  END;
                END IF;
                IF vehicle_expired_attention OR vehicle_expiry_attention THEN
                  BEGIN
                    INSERT INTO public.user_notifications(
                      id,user_id,organization_id,event_key,category,severity,title,body,
                      action_path,action_entity_type,action_entity_id,created_at
                    ) VALUES (
                      pg_catalog.gen_random_uuid(),notification_user_id,context_organization_id,
                      'vehicle-evidence-expiry:' || vehicle_value.id::text || ':' ||
                        local_today::text || ':' ||
                        CASE WHEN vehicle_expired_attention THEN 'expired' ELSE 'warning' END,
                      'credential',
                      CASE WHEN vehicle_expired_attention THEN 'critical' ELSE 'warning' END,
                      CASE WHEN vehicle_expired_attention
                        THEN 'Vehicle evidence expired' ELSE 'Vehicle evidence expires soon' END,
                      CASE WHEN vehicle_expired_attention
                        THEN 'Current verified vehicle evidence has expired.'
                        ELSE 'Current verified vehicle evidence expires within 30 days.' END,
                      '/transport-registry','transport_registry',created_result_id,now_value
                    );
                  EXCEPTION WHEN unique_violation THEN
                    GET STACKED DIAGNOSTICS constraint_name_value = CONSTRAINT_NAME;
                    IF constraint_name_value<>'uq_user_notifications_event' THEN RAISE;
                    END IF;
                  END;
                END IF;
              END LOOP;
            END IF;
            created_result_kind := 'driver_readiness';
          ELSE
            RAISE EXCEPTION 'transport_command_kind_unknown' USING ERRCODE='22023';
          END IF;

          receipt_id := pg_catalog.gen_random_uuid();
          INSERT INTO public.transport_registry_command_receipts(
            id,organization_id,actor_user_id,client_operation_id,command_kind,
            request_sha256,result_kind,result_id,committed_at,
            operational_driver_ready,dispatch_authorized
          ) VALUES (
            receipt_id,context_organization_id,context_user_id,requested_operation_id,
            requested_command_kind,requested_request_sha256,created_result_kind,
            created_result_id,now_value,false,false
          );
          INSERT INTO public.audit_events(
            id,organization_id,actor_user_id,action,entity_type,entity_id,occurred_at,details
          ) VALUES (
            pg_catalog.gen_random_uuid(),context_organization_id,context_user_id,
            'transport_registry.' || requested_command_kind,'transport_registry_command',
            created_result_id,now_value,
            pg_catalog.jsonb_build_object('operation_id',requested_operation_id::text,
              'result_kind',created_result_kind,'operational_driver_ready',false,
              'dispatch_authorized',false)
          );
          RETURN QUERY SELECT requested_operation_id,requested_command_kind,
            created_result_kind,created_result_id,now_value,false,false,false;
        END
        $writer$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.caresync_0032_execute_command("
        "text,uuid,text,jsonb) FROM PUBLIC"
    )


def _install_audit_realtime_bridge(*, transport_generic: bool) -> None:
    """Keep transport command identifiers out of the organization-wide outbox."""

    bind = op.get_bind()
    transport_branch = ""
    if transport_generic:
        transport_branch = """
          IF NEW.entity_type='transport_registry_command' THEN
            INSERT INTO public.realtime_events(
              id,organization_id,event_type,entity_type,entity_id,occurred_at,payload
            ) VALUES (
              NEW.id,NEW.organization_id,'transport_registry.changed',
              'transport_registry',NULL,NEW.occurred_at,
              pg_catalog.jsonb_build_object(
                'source','audit_event','refresh_required',true
              )
            );
            RETURN NEW;
          END IF;
        """
    if bind.dialect.name == "postgresql":
        op.execute(
            rf"""
            CREATE OR REPLACE FUNCTION public.realtime_from_audit_event()
            RETURNS trigger
            LANGUAGE plpgsql
            SET search_path = pg_catalog, public
            AS $bridge$
            BEGIN
              IF NEW.action LIKE 'family.authority.%'
                 OR NEW.action LIKE 'child.release.%'
                 OR NEW.action LIKE 'child.consent.%'
                 OR NEW.action LIKE 'organization.consent.%' THEN
                RETURN NEW;
              END IF;
              {transport_branch}
              INSERT INTO public.realtime_events(
                id,organization_id,event_type,entity_type,entity_id,occurred_at,payload
              ) VALUES (
                NEW.id,NEW.organization_id,NEW.action,NEW.entity_type,NEW.entity_id,
                NEW.occurred_at,pg_catalog.jsonb_build_object(
                  'source','audit_event','facility_id',NEW.facility_id
                )
              );
              RETURN NEW;
            END
            $bridge$
            """
        )
        return

    op.execute("DROP TRIGGER IF EXISTS audit_events_realtime")
    if transport_generic:
        op.execute(
            """
            CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events
            WHEN NEW.action NOT LIKE 'family.authority.%'
             AND NEW.action NOT LIKE 'child.release.%'
             AND NEW.action NOT LIKE 'child.consent.%'
             AND NEW.action NOT LIKE 'organization.consent.%'
            BEGIN
              INSERT INTO realtime_events(
                id,organization_id,event_type,entity_type,entity_id,occurred_at,payload
              ) VALUES (
                lower(hex(randomblob(16))),NEW.organization_id,
                CASE WHEN NEW.entity_type='transport_registry_command'
                  THEN 'transport_registry.changed' ELSE NEW.action END,
                CASE WHEN NEW.entity_type='transport_registry_command'
                  THEN 'transport_registry' ELSE NEW.entity_type END,
                CASE WHEN NEW.entity_type='transport_registry_command'
                  THEN NULL ELSE NEW.entity_id END,
                NEW.occurred_at,
                CASE WHEN NEW.entity_type='transport_registry_command'
                  THEN json_object('source','audit_event','refresh_required',json('true'))
                  ELSE json_object(
                    'source','audit_event','facility_id',NEW.facility_id
                  ) END
              );
            END
            """
        )
        return
    op.execute(
        """
        CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events
        WHEN NEW.action NOT LIKE 'family.authority.%'
         AND NEW.action NOT LIKE 'child.release.%'
         AND NEW.action NOT LIKE 'child.consent.%'
         AND NEW.action NOT LIKE 'organization.consent.%'
        BEGIN
          INSERT INTO realtime_events(
            id,organization_id,event_type,entity_type,entity_id,occurred_at,payload
          ) VALUES (
            lower(hex(randomblob(16))),NEW.organization_id,NEW.action,
            NEW.entity_type,NEW.entity_id,NEW.occurred_at,
            json_object('source','audit_event','facility_id',NEW.facility_id)
          );
        END
        """
    )


def _postgres_rls_and_grants() -> None:
    """Install read policies plus an internal writer-only policy.

    Runtime roles receive no DML here.  The bootstrap later gives the terminal
    application identities only EXECUTE on the repository and makes the
    dedicated, non-login command owner the function owner.
    """

    for signature in POSTGRES_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    org = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    manager = (
        "EXISTS (SELECT 1 FROM organization_memberships AS command_membership JOIN roles AS "
        "command_role ON command_role.organization_id=command_membership.organization_id AND "
        "command_role.id=command_membership.role_id WHERE command_membership.organization_id="
        f"{org} AND command_membership.user_id={user} AND command_membership.status='active' "
        "AND command_role.permissions::jsonb @> '[\"transport:manage\"]'::jsonb)"
    )

    def self_member(table: str) -> str:
        return (
            "EXISTS (SELECT 1 FROM organization_memberships AS command_self WHERE "
            f"command_self.organization_id={table}.organization_id AND "
            f"command_self.organization_id={org} AND "
            f"command_self.id={table}.membership_id AND "
            f"command_self.user_id={user} AND command_self.status='active')"
        )

    def personal_vehicle(table: str) -> str:
        return (
            "EXISTS (SELECT 1 FROM transport_vehicles AS command_vehicle JOIN "
            "organization_memberships AS command_owner ON command_owner.organization_id="
            "command_vehicle.organization_id AND command_owner.id="
            "command_vehicle.staff_owner_membership_id WHERE command_vehicle.organization_id="
            f"{table}.organization_id AND command_vehicle.id={table}.vehicle_id AND "
            f"command_vehicle.owner_kind='staff_personal' AND command_owner.user_id={user} "
            "AND command_owner.status='active')"
        )

    select_policies = {
        "transport_registry_command_receipts": (f"organization_id={org} AND actor_user_id={user}"),
        "staff_driver_qualification_evidence_objects": (
            f"(organization_id={org} AND {manager}) OR "
            f"{self_member('staff_driver_qualification_evidence_objects')}"
        ),
        "staff_driver_qualification_review_decisions": (f"organization_id={org} AND {manager}"),
        "transport_vehicle_evidence_review_decisions": (f"organization_id={org} AND {manager}"),
        "transport_vehicle_evidence_scan_facts": (
            f"(organization_id={org} AND {manager}) OR "
            f"{personal_vehicle('transport_vehicle_evidence_scan_facts')}"
        ),
    }
    for table, expression in select_policies.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({expression})")

    writer_expression = (
        "current_user='caresync_transport_command_owner' AND "
        "session_user IN ('caresync_basic_app','caresync_transport_evidence_ingest')"
    )
    context_lock_scopes = {
        "users": f"id={user}",
        "organizations": f"id={org}",
        "organization_memberships": f"organization_id={org}",
        "roles": f"organization_id={org}",
    }
    for table, scope in context_lock_scopes.items():
        lock_expression = f"{writer_expression} AND {scope}"
        op.execute(
            f"CREATE POLICY {table}_0032_lock ON {table} AS PERMISSIVE FOR UPDATE "
            f"USING ({lock_expression}) WITH CHECK (false)"
        )
        # Other role-specific policies continue unchanged.  This restrictive
        # policy affects only the command owner and makes its id-column ACL a
        # row-lock capability, never a mutation capability.
        op.execute(
            f"CREATE POLICY {table}_0032_lock_no_mutation ON {table} AS RESTRICTIVE "
            "FOR UPDATE USING (current_user<>'caresync_transport_command_owner' OR "
            f"({lock_expression})) WITH CHECK "
            "(current_user<>'caresync_transport_command_owner')"
        )
    writer_tables = (
        "staff_driver_capability_versions",
        "staff_driver_qualification_versions",
        "staff_driver_authorization_decisions",
        "staff_driver_readiness_decisions",
        "transport_vehicles",
        "transport_vehicle_versions",
        "transport_vehicle_evidence_versions",
        "transport_registry_command_receipts",
        "staff_driver_qualification_evidence_objects",
        "staff_driver_qualification_review_decisions",
        "transport_vehicle_evidence_review_decisions",
        "transport_vehicle_evidence_scan_facts",
    )
    for table in writer_tables:
        op.execute(
            f"CREATE POLICY {table}_0032_writer ON {table} FOR ALL "
            f"USING ({writer_expression}) WITH CHECK ({writer_expression})"
        )

    # Notifications and ordinary audit rows are side effects of the same
    # repository transaction.  Their existing user policies remain intact;
    # this policy is reachable only while the dedicated writer owns execution.
    for table in ("user_notifications", "audit_events"):
        op.execute(
            f"CREATE POLICY {table}_0032_writer ON {table} FOR ALL "
            f"USING ({writer_expression}) WITH CHECK ({writer_expression})"
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _preflight_postgres_0031_vehicle_plates()
    else:
        _preflight_sqlite_0031_vehicle_plates(bind)
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        _converge_postgres_0031_guards()
        _postgres_guards()
        _install_audit_realtime_bridge(transport_generic=True)
        _install_postgres_writer()
        _postgres_rls_and_grants()
    else:
        _converge_sqlite_0031_guards()
        _sqlite_guards()
        _install_audit_realtime_bridge(transport_generic=True)


def downgrade() -> None:
    bind = op.get_bind()
    populated = any(
        bool(bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {model.__tablename__} LIMIT 1)")))
        for model in TABLES
    )
    if populated:
        raise RuntimeError("0032 downgrade refused: transport command records exist")
    if bind.dialect.name == "postgresql":
        for table in (
            "users",
            "organizations",
            "organization_memberships",
            "roles",
        ):
            op.execute(f"DROP POLICY IF EXISTS {table}_0032_lock ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_0032_lock_no_mutation ON {table}")
        writer_tables = (
            "staff_driver_capability_versions",
            "staff_driver_qualification_versions",
            "staff_driver_authorization_decisions",
            "staff_driver_readiness_decisions",
            "transport_vehicles",
            "transport_vehicle_versions",
            "transport_vehicle_evidence_versions",
            "transport_registry_command_receipts",
            "staff_driver_qualification_evidence_objects",
            "staff_driver_qualification_review_decisions",
            "transport_vehicle_evidence_review_decisions",
            "transport_vehicle_evidence_scan_facts",
        )
        for table in writer_tables:
            op.execute(f"DROP POLICY IF EXISTS {table}_0032_writer ON {table}")
        for table in (
            "transport_registry_command_receipts",
            "staff_driver_qualification_evidence_objects",
            "staff_driver_qualification_review_decisions",
            "transport_vehicle_evidence_review_decisions",
            "transport_vehicle_evidence_scan_facts",
        ):
            op.execute(f"DROP POLICY IF EXISTS {table}_select ON {table}")
        for table in ("user_notifications", "audit_events"):
            op.execute(f"DROP POLICY IF EXISTS {table}_0032_writer ON {table}")
        for trigger, table in (
            ("transport_registry_receipt_insert_guard", "transport_registry_command_receipts"),
            (
                "staff_driver_qualification_evidence_insert_guard",
                "staff_driver_qualification_evidence_objects",
            ),
            (
                "staff_driver_qualification_review_insert_guard",
                "staff_driver_qualification_review_decisions",
            ),
            (
                "transport_vehicle_evidence_review_insert_guard",
                "transport_vehicle_evidence_review_decisions",
            ),
            (
                "transport_vehicle_evidence_scan_insert_guard",
                "transport_vehicle_evidence_scan_facts",
            ),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        for table in IMMUTABLE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        for signature in POSTGRES_FUNCTIONS:
            op.execute(f"DROP FUNCTION IF EXISTS public.{signature}")
        _install_audit_realtime_bridge(transport_generic=False)
    else:
        for trigger in (
            "transport_registry_receipt_insert_guard",
            "staff_driver_qualification_evidence_insert_guard",
            "staff_driver_qualification_review_insert_guard",
            "transport_vehicle_evidence_review_insert_guard",
            "transport_vehicle_evidence_scan_insert_guard",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        for table in IMMUTABLE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_update")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_delete")
        _install_audit_realtime_bridge(transport_generic=False)
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)

"""Add the fail-closed staff driver and vehicle registry foundation.

Revision ID: 0031_driver_vehicle_registry
Revises: 0030_staff_screening_paths
Create Date: 2026-07-18

This revision is source-only until an explicit release cutover.  It records
versioned staff/vehicle facts and append-only human decisions, but deliberately
cannot authorize operational driving or child transport dispatch.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    StaffDriverAuthorizationDecision,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    TransportVehicle,
    TransportVehicleEvidenceVersion,
    TransportVehicleVersion,
)

revision = "0031_driver_vehicle_registry"
down_revision = "0030_staff_screening_paths"
branch_labels = None
depends_on = None

TABLES = (
    StaffDriverCapabilityVersion,
    StaffDriverQualificationVersion,
    StaffDriverAuthorizationDecision,
    TransportVehicle,
    TransportVehicleVersion,
    TransportVehicleEvidenceVersion,
    StaffDriverReadinessDecision,
)

IMMUTABLE_TABLES = (
    "staff_driver_capability_versions",
    "staff_driver_qualification_versions",
    "staff_driver_authorization_decisions",
    "transport_vehicle_versions",
    "transport_vehicle_evidence_versions",
    "staff_driver_readiness_decisions",
)

POSTGRES_FUNCTIONS = (
    "caresync_0031_immutable_fact()",
    "caresync_0031_capability_guard()",
    "caresync_0031_qualification_guard()",
    "caresync_0031_authorization_guard()",
    "caresync_0031_vehicle_guard()",
    "caresync_0031_vehicle_version_guard()",
    "caresync_0031_vehicle_evidence_guard()",
    "caresync_0031_readiness_guard()",
)


def _postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_immutable_fact() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          RAISE EXCEPTION '0031 immutable driver/vehicle fact cannot be changed'
            USING ERRCODE='23514';
        END $$
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0031_immutable_fact()"
        )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_capability_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE previous record; member_user uuid;
        BEGIN
          SELECT membership.user_id INTO member_user
          FROM public.organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id FOR UPDATE;
          IF member_user IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 capability actor or membership mismatch'
              USING ERRCODE='23514';
          END IF;
          SELECT version_number,effective_at INTO previous
          FROM public.staff_driver_capability_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
          ORDER BY version_number DESC LIMIT 1;
          IF NEW.version_number<>COALESCE(previous.version_number,0)+1
             OR (previous.effective_at IS NOT NULL AND NEW.effective_at<previous.effective_at) THEN
            RAISE EXCEPTION '0031 capability version sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.source_kind='screening_profile' AND NOT EXISTS (
            SELECT 1 FROM public.marketplace_screening_profiles AS profile
            WHERE profile.user_id=member_user
              AND profile.version=NEW.source_screening_profile_version
              AND profile.willing_to_drive=NEW.willing_to_drive
              AND profile.licence_jurisdiction IS NOT DISTINCT FROM NEW.licence_jurisdiction
              AND profile.licence_jurisdiction_other IS NOT DISTINCT FROM
                  NEW.licence_jurisdiction_other
              AND profile.licence_class IS NOT DISTINCT FROM NEW.licence_class
              AND profile.vehicle_access=NEW.vehicle_access
              AND profile.preferred_service_radius_km IS NOT DISTINCT FROM
                  NEW.preferred_service_radius_km
          ) THEN
            RAISE EXCEPTION '0031 capability screening profile mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_driver_capability_insert_guard BEFORE INSERT "
        "ON staff_driver_capability_versions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_capability_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_qualification_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE previous record; member_user uuid;
        BEGIN
          SELECT membership.user_id INTO member_user
          FROM public.organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id FOR UPDATE;
          IF member_user IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 qualification actor or membership mismatch'
              USING ERRCODE='23514';
          END IF;
          SELECT version_number,effective_at INTO previous
          FROM public.staff_driver_qualification_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
            AND qualification_type=NEW.qualification_type
          ORDER BY version_number DESC LIMIT 1;
          IF NEW.version_number<>COALESCE(previous.version_number,0)+1
             OR (previous.effective_at IS NOT NULL AND NEW.effective_at<previous.effective_at) THEN
            RAISE EXCEPTION '0031 qualification version sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.source_screening_document_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.staff_screening_document_versions AS source
            WHERE source.id=NEW.source_screening_document_version_id
              AND source.user_id=member_user
          ) THEN
            RAISE EXCEPTION '0031 qualification evidence owner mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_driver_qualification_insert_guard BEFORE INSERT "
        "ON staff_driver_qualification_versions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_qualification_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_authorization_guard() RETURNS trigger
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
        "CREATE TRIGGER staff_driver_authorization_insert_guard BEFORE INSERT "
        "ON staff_driver_authorization_decisions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_authorization_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_vehicle_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP='DELETE' OR NEW.id<>OLD.id OR NEW.organization_id<>OLD.organization_id
             OR NEW.owner_kind<>OLD.owner_kind
             OR NEW.staff_owner_membership_id IS DISTINCT FROM OLD.staff_owner_membership_id
             OR NEW.created_by_user_id<>OLD.created_by_user_id
             OR NEW.created_at<>OLD.created_at OR OLD.retired_at IS NOT NULL
             OR NEW.retired_at IS NULL OR NEW.retired_by_user_id IS NULL
             OR NEW.retirement_reason_code IS NULL THEN
            RAISE EXCEPTION '0031 vehicle is immutable except one-way retirement'
              USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.retired_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 vehicle retirement actor mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transport_vehicles_guard BEFORE UPDATE OR DELETE "
        "ON transport_vehicles FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_vehicle_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_vehicle_version_guard() RETURNS trigger
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
    op.execute(
        "CREATE TRIGGER transport_vehicle_versions_insert_guard BEFORE INSERT "
        "ON transport_vehicle_versions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_vehicle_version_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_vehicle_evidence_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE previous integer;
        BEGIN
          PERFORM 1 FROM public.transport_vehicles AS vehicle
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
            AND vehicle.retired_at IS NULL FOR UPDATE;
          IF NOT FOUND OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 vehicle evidence actor or vehicle mismatch'
              USING ERRCODE='23514';
          END IF;
          SELECT max(version_number) INTO previous
          FROM public.transport_vehicle_evidence_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
            AND evidence_type=NEW.evidence_type;
          IF NEW.version_number<>COALESCE(previous,0)+1 THEN
            RAISE EXCEPTION '0031 vehicle evidence version sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.recorded_at<COALESCE((SELECT max(recorded_at)
            FROM public.transport_vehicle_evidence_versions
            WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
              AND evidence_type=NEW.evidence_type),NEW.recorded_at) THEN
            RAISE EXCEPTION '0031 vehicle evidence time is out of order'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transport_vehicle_evidence_insert_guard BEFORE INSERT "
        "ON transport_vehicle_evidence_versions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_vehicle_evidence_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION public.caresync_0031_readiness_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE total integer; distinct_total integer; matched integer;
        BEGIN
          PERFORM 1 FROM public.organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id FOR UPDATE;
          IF NOT FOUND OR NOT EXISTS (
            SELECT 1 FROM public.organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.evaluated_by_user_id AND actor.status='active'
          ) THEN
            RAISE EXCEPTION '0031 readiness actor or membership mismatch'
              USING ERRCODE='23514';
          END IF;
          IF NEW.decision_sequence<>COALESCE((SELECT max(decision_sequence)
            FROM public.staff_driver_readiness_decisions
            WHERE organization_id=NEW.organization_id
              AND membership_id=NEW.membership_id),0)+1 THEN
            RAISE EXCEPTION '0031 readiness sequence is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.evaluated_at<COALESCE((SELECT max(evaluated_at)
            FROM public.staff_driver_readiness_decisions
            WHERE organization_id=NEW.organization_id
              AND membership_id=NEW.membership_id),NEW.evaluated_at) THEN
            RAISE EXCEPTION '0031 readiness evaluation time is out of order'
              USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.staff_driver_authorization_decisions AS auth_decision
            WHERE auth_decision.organization_id=NEW.organization_id
              AND auth_decision.membership_id=NEW.membership_id
              AND auth_decision.id=NEW.authorization_decision_id
              AND auth_decision.capability_version_id=NEW.capability_version_id
              AND auth_decision.operational_driver_ready=false
              AND auth_decision.dispatch_authorized=false
              AND auth_decision.reviewed_at<=NEW.evaluated_at
          ) THEN
            RAISE EXCEPTION '0031 readiness authorization mismatch'
              USING ERRCODE='23514';
          END IF;
          IF pg_catalog.jsonb_typeof(NEW.reason_codes::jsonb)<>'array'
             OR pg_catalog.jsonb_array_length(NEW.reason_codes::jsonb)<1
             OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements_text(
               NEW.reason_codes::jsonb) AS reason(value)
               WHERE length(trim(reason.value))=0) THEN
            RAISE EXCEPTION '0031 readiness reasons are invalid'
              USING ERRCODE='23514';
          END IF;
          SELECT count(*),count(DISTINCT value) INTO total,distinct_total
          FROM pg_catalog.jsonb_array_elements_text(NEW.reason_codes::jsonb) AS value;
          IF total<>distinct_total
             OR pg_catalog.jsonb_typeof(NEW.vehicle_evidence_version_ids::jsonb)<>'array' THEN
            RAISE EXCEPTION '0031 readiness evidence or reasons are invalid'
              USING ERRCODE='23514';
          END IF;
          SELECT count(*),count(DISTINCT replace(value,'-','')) INTO total,distinct_total
          FROM pg_catalog.jsonb_array_elements_text(
            NEW.vehicle_evidence_version_ids::jsonb
          ) AS value;
          IF total<>distinct_total OR (NEW.vehicle_id IS NULL AND total<>0) THEN
            RAISE EXCEPTION '0031 readiness vehicle evidence list is invalid'
              USING ERRCODE='23514';
          END IF;
          IF NEW.vehicle_id IS NOT NULL THEN
            IF NOT EXISTS (
              SELECT 1 FROM public.transport_vehicles AS vehicle
              WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
                AND vehicle.retired_at IS NULL AND (
                  vehicle.owner_kind='organization'
                  OR vehicle.staff_owner_membership_id=NEW.membership_id)
            ) THEN
              RAISE EXCEPTION '0031 readiness vehicle ownership mismatch'
                USING ERRCODE='23514';
            END IF;
            SELECT count(*) INTO matched
            FROM public.transport_vehicle_evidence_versions AS evidence
            JOIN pg_catalog.jsonb_array_elements_text(
              NEW.vehicle_evidence_version_ids::jsonb
            ) AS item ON replace(item.value,'-','')=replace(evidence.id::text,'-','')
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.vehicle_id=NEW.vehicle_id
              AND evidence.vehicle_version_id=NEW.vehicle_version_id;
            IF matched<>total THEN
              RAISE EXCEPTION '0031 readiness vehicle evidence mismatch'
                USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_driver_readiness_insert_guard BEFORE INSERT "
        "ON staff_driver_readiness_decisions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0031_readiness_guard()"
    )


def _sqlite_guards() -> None:
    for table in IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_immutable_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN "
                "SELECT RAISE(ABORT,'0031 immutable driver/vehicle fact cannot be changed'); END"
            )

    op.execute(
        """
        CREATE TRIGGER staff_driver_capability_insert_guard
        BEFORE INSERT ON staff_driver_capability_versions
        WHEN NOT EXISTS (
          SELECT 1 FROM organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
        ) OR NEW.version_number<>COALESCE((
          SELECT max(version_number) FROM staff_driver_capability_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),0)+1 OR NEW.effective_at<COALESCE((
          SELECT max(effective_at) FROM staff_driver_capability_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),NEW.effective_at) OR (
          NEW.source_kind='screening_profile' AND NOT EXISTS (
            SELECT 1 FROM organization_memberships AS membership
            JOIN marketplace_screening_profiles AS profile
              ON profile.user_id=membership.user_id
            WHERE membership.organization_id=NEW.organization_id
              AND membership.id=NEW.membership_id
              AND profile.version=NEW.source_screening_profile_version
              AND profile.willing_to_drive=NEW.willing_to_drive
              AND profile.licence_jurisdiction IS NEW.licence_jurisdiction
              AND profile.licence_jurisdiction_other IS NEW.licence_jurisdiction_other
              AND profile.licence_class IS NEW.licence_class
              AND profile.vehicle_access=NEW.vehicle_access
              AND profile.preferred_service_radius_km IS NEW.preferred_service_radius_km
          )
        )
        BEGIN
          SELECT RAISE(ABORT,'0031 capability sequence or ownership is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_driver_qualification_insert_guard
        BEFORE INSERT ON staff_driver_qualification_versions
        WHEN NOT EXISTS (
          SELECT 1 FROM organization_memberships AS membership
          WHERE membership.organization_id=NEW.organization_id
            AND membership.id=NEW.membership_id
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
        ) OR NEW.version_number<>COALESCE((
          SELECT max(version_number) FROM staff_driver_qualification_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
            AND qualification_type=NEW.qualification_type
        ),0)+1 OR NEW.effective_at<COALESCE((
          SELECT max(effective_at) FROM staff_driver_qualification_versions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
            AND qualification_type=NEW.qualification_type
        ),NEW.effective_at) OR (
          NEW.source_screening_document_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM organization_memberships AS membership
            JOIN staff_screening_document_versions AS source
              ON source.user_id=membership.user_id
            WHERE membership.organization_id=NEW.organization_id
              AND membership.id=NEW.membership_id
              AND source.id=NEW.source_screening_document_version_id
          )
        )
        BEGIN
          SELECT RAISE(ABORT,'0031 qualification sequence or ownership is invalid');
        END
        """
    )
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
    op.execute(
        """
        CREATE TRIGGER transport_vehicles_guard_update
        BEFORE UPDATE ON transport_vehicles
        WHEN NEW.id<>OLD.id OR NEW.organization_id<>OLD.organization_id
          OR NEW.owner_kind<>OLD.owner_kind
          OR NEW.staff_owner_membership_id IS NOT OLD.staff_owner_membership_id
          OR NEW.created_by_user_id<>OLD.created_by_user_id OR NEW.created_at<>OLD.created_at
          OR OLD.retired_at IS NOT NULL OR NEW.retired_at IS NULL
          OR NEW.retired_by_user_id IS NULL OR NEW.retirement_reason_code IS NULL
          OR NOT EXISTS (
            SELECT 1 FROM organization_memberships AS actor
            WHERE actor.organization_id=NEW.organization_id
              AND actor.user_id=NEW.retired_by_user_id AND actor.status='active'
          )
        BEGIN
          SELECT RAISE(ABORT,'0031 vehicle is immutable except one-way retirement');
        END
        """
    )
    op.execute(
        "CREATE TRIGGER transport_vehicles_guard_delete BEFORE DELETE ON transport_vehicles "
        "BEGIN SELECT RAISE(ABORT,'0031 vehicle cannot be deleted'); END"
    )
    op.execute(
        """
        CREATE TRIGGER transport_vehicle_versions_insert_guard
        BEFORE INSERT ON transport_vehicle_versions
        WHEN NOT EXISTS (
          SELECT 1 FROM transport_vehicles AS vehicle
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
            AND vehicle.retired_at IS NULL
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
        ) OR NEW.version_number<>COALESCE((
          SELECT max(version_number) FROM transport_vehicle_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
        ),0)+1 OR NEW.effective_at<COALESCE((
          SELECT max(effective_at) FROM transport_vehicle_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
        ),NEW.effective_at)
        BEGIN
          SELECT RAISE(ABORT,'0031 vehicle version sequence or ownership is invalid');
        END
        """
    )
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
    op.execute(
        """
        CREATE TRIGGER transport_vehicle_evidence_insert_guard
        BEFORE INSERT ON transport_vehicle_evidence_versions
        WHEN NOT EXISTS (
          SELECT 1 FROM transport_vehicles AS vehicle
          WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
            AND vehicle.retired_at IS NULL
        ) OR NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.recorded_by_user_id AND actor.status='active'
        ) OR NEW.version_number<>COALESCE((
          SELECT max(version_number) FROM transport_vehicle_evidence_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
            AND evidence_type=NEW.evidence_type
        ),0)+1 OR NEW.recorded_at<COALESCE((
          SELECT max(recorded_at) FROM transport_vehicle_evidence_versions
          WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.vehicle_id
            AND evidence_type=NEW.evidence_type
        ),NEW.recorded_at)
        BEGIN
          SELECT RAISE(ABORT,'0031 vehicle evidence sequence or ownership is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_driver_readiness_insert_guard
        BEFORE INSERT ON staff_driver_readiness_decisions
        WHEN NOT EXISTS (
          SELECT 1 FROM organization_memberships AS actor
          WHERE actor.organization_id=NEW.organization_id
            AND actor.user_id=NEW.evaluated_by_user_id AND actor.status='active'
        ) OR NEW.decision_sequence<>COALESCE((
          SELECT max(decision_sequence) FROM staff_driver_readiness_decisions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),0)+1 OR NEW.evaluated_at<COALESCE((
          SELECT max(evaluated_at) FROM staff_driver_readiness_decisions
          WHERE organization_id=NEW.organization_id AND membership_id=NEW.membership_id
        ),NEW.evaluated_at) OR NOT EXISTS (
          SELECT 1 FROM staff_driver_authorization_decisions AS authorization
          WHERE authorization.organization_id=NEW.organization_id
            AND authorization.membership_id=NEW.membership_id
            AND authorization.id=NEW.authorization_decision_id
            AND authorization.capability_version_id=NEW.capability_version_id
            AND authorization.operational_driver_ready=0
            AND authorization.dispatch_authorized=0
            AND authorization.reviewed_at<=NEW.evaluated_at
        ) OR json_valid(NEW.reason_codes)=0 OR json_type(NEW.reason_codes)<>'array'
          OR json_array_length(NEW.reason_codes)<1
          OR EXISTS (SELECT 1 FROM json_each(NEW.reason_codes)
                     WHERE length(trim(value))=0)
          OR (SELECT count(*) FROM json_each(NEW.reason_codes))<>
             (SELECT count(DISTINCT value) FROM json_each(NEW.reason_codes))
          OR json_valid(NEW.vehicle_evidence_version_ids)=0
          OR json_type(NEW.vehicle_evidence_version_ids)<>'array'
          OR (SELECT count(*) FROM json_each(NEW.vehicle_evidence_version_ids))<>
             (SELECT count(DISTINCT replace(value,'-',''))
              FROM json_each(NEW.vehicle_evidence_version_ids))
          OR (NEW.vehicle_id IS NULL AND json_array_length(
                NEW.vehicle_evidence_version_ids)>0)
          OR (NEW.vehicle_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM transport_vehicles AS vehicle
            WHERE vehicle.organization_id=NEW.organization_id AND vehicle.id=NEW.vehicle_id
              AND vehicle.retired_at IS NULL AND (
                vehicle.owner_kind='organization'
                OR vehicle.staff_owner_membership_id=NEW.membership_id)
          )) OR EXISTS (
            SELECT 1 FROM json_each(NEW.vehicle_evidence_version_ids) AS item
            WHERE NOT EXISTS (
              SELECT 1 FROM transport_vehicle_evidence_versions AS evidence
              WHERE evidence.organization_id=NEW.organization_id
                AND evidence.vehicle_id=NEW.vehicle_id
                AND evidence.vehicle_version_id=NEW.vehicle_version_id
                AND replace(evidence.id,'-','')=replace(item.value,'-','')
            )
          )
        BEGIN
          SELECT RAISE(ABORT,'0031 readiness sequence or evidence is invalid');
        END
        """
    )


def _postgres_rls_and_grants() -> None:
    for signature in POSTGRES_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute(
        """
        DO $revoke$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE ALL ON FUNCTION
              public.caresync_0031_immutable_fact(),
              public.caresync_0031_capability_guard(),
              public.caresync_0031_qualification_guard(),
              public.caresync_0031_authorization_guard(),
              public.caresync_0031_vehicle_guard(),
              public.caresync_0031_vehicle_version_guard(),
              public.caresync_0031_vehicle_evidence_guard(),
              public.caresync_0031_readiness_guard()
              FROM caresync_basic_app;
          END IF;
        END $revoke$
        """
    )
    org = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    reader = (
        "EXISTS (SELECT 1 FROM organization_memberships AS access_membership "
        "JOIN roles AS access_role ON "
        "access_role.organization_id=access_membership.organization_id "
        "AND access_role.id=access_membership.role_id WHERE "
        f"access_membership.organization_id={org} AND access_membership.user_id={user} "
        "AND access_membership.status='active' AND ("
        "access_role.permissions::jsonb @> '[\"transport:read\"]'::jsonb OR "
        "access_role.permissions::jsonb @> '[\"transport:manage\"]'::jsonb))"
    )
    for table in (
        "staff_driver_capability_versions",
        "staff_driver_qualification_versions",
        "staff_driver_authorization_decisions",
        "staff_driver_readiness_decisions",
    ):
        member = (
            "EXISTS (SELECT 1 FROM organization_memberships AS self_membership WHERE "
            f"self_membership.organization_id={table}.organization_id "
            f"AND self_membership.organization_id={org} "
            f"AND self_membership.id={table}.membership_id "
            f"AND self_membership.user_id={user} "
            "AND self_membership.status='active')"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ("
            f"(organization_id={org} AND {reader}) OR {member})"
        )

    op.execute("ALTER TABLE transport_vehicles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transport_vehicles FORCE ROW LEVEL SECURITY")
    vehicle_self = (
        "owner_kind='staff_personal' AND EXISTS (SELECT 1 FROM organization_memberships "
        "AS self_membership WHERE "
        "self_membership.organization_id=transport_vehicles.organization_id "
        f"AND self_membership.organization_id={org} "
        "AND self_membership.id=transport_vehicles.staff_owner_membership_id "
        f"AND self_membership.user_id={user} AND self_membership.status='active')"
    )
    op.execute(
        "CREATE POLICY transport_vehicles_select ON transport_vehicles FOR SELECT USING ("
        f"(organization_id={org} AND {reader}) OR ({vehicle_self}))"
    )
    for table in ("transport_vehicle_versions", "transport_vehicle_evidence_versions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ("
            f"(organization_id={org} AND {reader}) OR EXISTS ("
            "SELECT 1 FROM transport_vehicles AS vehicle WHERE "
            f"vehicle.organization_id={table}.organization_id "
            f"AND vehicle.id={table}.vehicle_id AND vehicle.owner_kind='staff_personal' "
            "AND EXISTS (SELECT 1 FROM organization_memberships AS self_membership WHERE "
            "self_membership.organization_id=vehicle.organization_id "
            f"AND self_membership.organization_id={org} "
            "AND self_membership.id=vehicle.staff_owner_membership_id "
            f"AND self_membership.user_id={user} AND self_membership.status='active')))"
        )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            GRANT SELECT ON TABLE
              staff_driver_capability_versions,
              staff_driver_qualification_versions,
              staff_driver_authorization_decisions,
              staff_driver_readiness_decisions,
              transport_vehicles,
              transport_vehicle_versions,
              transport_vehicle_evidence_versions
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        _postgres_guards()
        _postgres_rls_and_grants()
    else:
        _sqlite_guards()


def downgrade() -> None:
    bind = op.get_bind()
    populated = any(
        bool(bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {model.__tablename__} LIMIT 1)")))
        for model in TABLES
    )
    if populated:
        raise RuntimeError("0031 downgrade refused: driver or vehicle registry records exist")

    if bind.dialect.name == "postgresql":
        for trigger, table in (
            ("staff_driver_capability_insert_guard", "staff_driver_capability_versions"),
            ("staff_driver_qualification_insert_guard", "staff_driver_qualification_versions"),
            ("staff_driver_authorization_insert_guard", "staff_driver_authorization_decisions"),
            ("transport_vehicles_guard", "transport_vehicles"),
            ("transport_vehicle_versions_insert_guard", "transport_vehicle_versions"),
            (
                "transport_vehicle_evidence_insert_guard",
                "transport_vehicle_evidence_versions",
            ),
            ("staff_driver_readiness_insert_guard", "staff_driver_readiness_decisions"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        for table in IMMUTABLE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        for signature in POSTGRES_FUNCTIONS:
            op.execute(f"DROP FUNCTION IF EXISTS public.{signature}")
    else:
        for trigger in (
            "staff_driver_capability_insert_guard",
            "staff_driver_qualification_insert_guard",
            "staff_driver_authorization_insert_guard",
            "transport_vehicles_guard_update",
            "transport_vehicles_guard_delete",
            "transport_vehicle_versions_insert_guard",
            "transport_vehicle_versions_plate_guard",
            "transport_vehicle_evidence_insert_guard",
            "staff_driver_readiness_insert_guard",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        for table in IMMUTABLE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_update")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_delete")
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)

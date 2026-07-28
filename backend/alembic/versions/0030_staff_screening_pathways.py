"""Add confidential staff screening pathways and exact structured employment terms.

Revision ID: 0030_staff_screening_paths
Revises: 0029D_release_checkout_writer
Create Date: 2026-07-18

All 0030 data lives in additive sidecars so code containing these mappings can
still run safely against the retained 0028 database until an explicit cutover.
"""

from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    AtsApplicationScreeningSnapshot,
    AtsJobScreeningTerms,
    AtsOfferAcknowledgment,
    AtsOfferScreeningTerms,
    MarketplaceJobScreeningTerms,
    MarketplaceScreeningProfile,
    StaffScreeningApplicationShare,
    StaffScreeningCandidateConfirmation,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    StaffScreeningEmployerReview,
)
from app.basic.staff_screening_terms import default_structured_terms, offer_terms_digest

revision = "0030_staff_screening_paths"
down_revision = "0029D_release_checkout_writer"
branch_labels = None
depends_on = None

TABLES = (
    AtsJobScreeningTerms,
    MarketplaceJobScreeningTerms,
    MarketplaceScreeningProfile,
    AtsApplicationScreeningSnapshot,
    AtsOfferScreeningTerms,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    StaffScreeningCandidateConfirmation,
    StaffScreeningApplicationShare,
    StaffScreeningEmployerReview,
    AtsOfferAcknowledgment,
)

POSTGRES_FUNCTIONS = (
    "sync_marketplace_job_screening_from_terms()",
    "sync_marketplace_job_screening_from_listing()",
    "caresync_0030_immutable_fact()",
    "caresync_0030_coverage_guard()",
    "caresync_0030_snapshot_guard()",
    "caresync_0030_share_insert_guard()",
    "caresync_0030_review_insert_guard()",
    "caresync_0030_document_guard()",
    "caresync_0030_offer_terms_insert_guard()",
    "caresync_0030_offer_terms_guard()",
    "caresync_0030_share_guard()",
    "caresync_0030_offer_ack_guard()",
)


def _backfill_sidecars(bind) -> None:
    defaults = default_structured_terms()
    jobs = list(bind.execute(sa.text("SELECT id, organization_id FROM ats_jobs")).mappings())
    if jobs:
        bind.execute(
            AtsJobScreeningTerms.__table__.insert(),
            [
                {
                    "job_id": row["id"],
                    "organization_id": row["organization_id"],
                    **defaults,
                    "version": 1,
                }
                for row in jobs
            ],
        )

    offers = list(
        bind.execute(
            sa.text(
                "SELECT offer.id, offer.organization_id, offer.application_id, offer.version, "
                "offer.position_title,offer.start_date,offer.compensation,offer.hourly_rate,"
                "offer.notes,offer.terms,offer.expires_at,application.candidate_id "
                "FROM ats_offers AS offer JOIN ats_applications AS application "
                "ON application.organization_id=offer.organization_id "
                "AND application.id=offer.application_id"
            )
        ).mappings()
    )
    if offers:
        rows = []
        for row in offers:
            offer = SimpleNamespace(**row)
            rows.append(
                {
                    "offer_id": row["id"],
                    "organization_id": row["organization_id"],
                    "offer_version": row["version"],
                    **defaults,
                    "terms_digest": offer_terms_digest(
                        offer, defaults, candidate_id=row["candidate_id"]
                    ),
                }
            )
        bind.execute(AtsOfferScreeningTerms.__table__.insert(), rows)

    open_terms = list(
        bind.execute(
            sa.text(
                "SELECT terms.* FROM ats_job_screening_terms AS terms "
                "JOIN ats_jobs AS job ON job.id=terms.job_id "
                "AND job.organization_id=terms.organization_id WHERE job.status='open'"
            )
        ).mappings()
    )
    if open_terms:
        bind.execute(
            MarketplaceJobScreeningTerms.__table__.insert(),
            [
                {
                    "listing_id": row["job_id"],
                    **{key: row[key] for key in defaults},
                    "source_version": row["version"],
                }
                for row in open_terms
            ],
        )


def _postgres_projection() -> None:
    op.execute(
        """
        CREATE FUNCTION public.sync_marketplace_job_screening_from_terms() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.ats_jobs AS job
            WHERE job.id=NEW.job_id AND job.organization_id=NEW.organization_id
              AND job.status='open'
          ) THEN
            INSERT INTO public.marketplace_job_screening_terms
              (listing_id,position_shape,driving_requirement,vehicle_expectation,
               required_licence_jurisdiction,required_licence_jurisdiction_other,
               required_licence_class,minimum_driving_experience_months,service_area,
               service_windows,mileage_policy,driving_time_paid,screening_conditions,
               source_version)
            VALUES
              (NEW.job_id,NEW.position_shape,NEW.driving_requirement,NEW.vehicle_expectation,
               NEW.required_licence_jurisdiction,NEW.required_licence_jurisdiction_other,
               NEW.required_licence_class,NEW.minimum_driving_experience_months,NEW.service_area,
               NEW.service_windows,NEW.mileage_policy,NEW.driving_time_paid,
               NEW.screening_conditions,NEW.version)
            ON CONFLICT (listing_id) DO UPDATE SET
              position_shape=EXCLUDED.position_shape,
              driving_requirement=EXCLUDED.driving_requirement,
              vehicle_expectation=EXCLUDED.vehicle_expectation,
              required_licence_jurisdiction=EXCLUDED.required_licence_jurisdiction,
              required_licence_jurisdiction_other=EXCLUDED.required_licence_jurisdiction_other,
              required_licence_class=EXCLUDED.required_licence_class,
              minimum_driving_experience_months=EXCLUDED.minimum_driving_experience_months,
              service_area=EXCLUDED.service_area,service_windows=EXCLUDED.service_windows,
              mileage_policy=EXCLUDED.mileage_policy,
              driving_time_paid=EXCLUDED.driving_time_paid,
              screening_conditions=EXCLUDED.screening_conditions,
              source_version=EXCLUDED.source_version;
          ELSE
            DELETE FROM public.marketplace_job_screening_terms WHERE listing_id=NEW.job_id;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_job_screening_marketplace AFTER INSERT OR UPDATE "
        "ON ats_job_screening_terms FOR EACH ROW "
        "EXECUTE FUNCTION public.sync_marketplace_job_screening_from_terms()"
    )
    op.execute(
        """
        CREATE FUNCTION public.sync_marketplace_job_screening_from_listing() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          INSERT INTO public.marketplace_job_screening_terms
            (listing_id,position_shape,driving_requirement,vehicle_expectation,
             required_licence_jurisdiction,required_licence_jurisdiction_other,
             required_licence_class,minimum_driving_experience_months,service_area,
             service_windows,mileage_policy,driving_time_paid,screening_conditions,
             source_version)
          SELECT terms.job_id,terms.position_shape,terms.driving_requirement,
            terms.vehicle_expectation,terms.required_licence_jurisdiction,
            terms.required_licence_jurisdiction_other,terms.required_licence_class,
            terms.minimum_driving_experience_months,terms.service_area,
            terms.service_windows,terms.mileage_policy,terms.driving_time_paid,
            terms.screening_conditions,terms.version
          FROM public.ats_job_screening_terms AS terms
          WHERE terms.job_id=NEW.listing_id
          ON CONFLICT (listing_id) DO UPDATE SET
            position_shape=EXCLUDED.position_shape,
            driving_requirement=EXCLUDED.driving_requirement,
            vehicle_expectation=EXCLUDED.vehicle_expectation,
            required_licence_jurisdiction=EXCLUDED.required_licence_jurisdiction,
            required_licence_jurisdiction_other=EXCLUDED.required_licence_jurisdiction_other,
            required_licence_class=EXCLUDED.required_licence_class,
            minimum_driving_experience_months=EXCLUDED.minimum_driving_experience_months,
            service_area=EXCLUDED.service_area,service_windows=EXCLUDED.service_windows,
            mileage_policy=EXCLUDED.mileage_policy,
            driving_time_paid=EXCLUDED.driving_time_paid,
            screening_conditions=EXCLUDED.screening_conditions,
            source_version=EXCLUDED.source_version;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER marketplace_jobs_screening_projection AFTER INSERT OR UPDATE "
        "ON marketplace_jobs FOR EACH ROW "
        "EXECUTE FUNCTION public.sync_marketplace_job_screening_from_listing()"
    )


def _sqlite_projection() -> None:
    column_names = (
        "position_shape,driving_requirement,vehicle_expectation,"
        "required_licence_jurisdiction,required_licence_jurisdiction_other,"
        "required_licence_class,minimum_driving_experience_months,service_area,"
        "service_windows,mileage_policy,driving_time_paid,screening_conditions"
    )
    new_values = ",".join(f"NEW.{name}" for name in column_names.split(","))
    op.execute(
        f"""
        CREATE TRIGGER ats_job_screening_marketplace_insert
        AFTER INSERT ON ats_job_screening_terms
        WHEN EXISTS (SELECT 1 FROM ats_jobs WHERE id=NEW.job_id AND status='open')
        BEGIN
          INSERT OR REPLACE INTO marketplace_job_screening_terms
            (listing_id,{column_names},source_version)
          VALUES (NEW.job_id,{new_values},NEW.version);
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER ats_job_screening_marketplace_update
        AFTER UPDATE ON ats_job_screening_terms
        BEGIN
          DELETE FROM marketplace_job_screening_terms WHERE listing_id=NEW.job_id;
          INSERT OR REPLACE INTO marketplace_job_screening_terms
            (listing_id,{column_names},source_version)
          SELECT NEW.job_id,{new_values},NEW.version
          WHERE EXISTS (SELECT 1 FROM ats_jobs WHERE id=NEW.job_id AND status='open');
        END
        """
    )
    selected = ",".join(f"terms.{name}" for name in column_names.split(","))
    op.execute(
        f"""
        CREATE TRIGGER marketplace_jobs_screening_projection
        AFTER INSERT ON marketplace_jobs
        BEGIN
          INSERT OR REPLACE INTO marketplace_job_screening_terms
            (listing_id,{column_names},source_version)
          SELECT terms.job_id,{selected},terms.version
          FROM ats_job_screening_terms AS terms
          WHERE terms.job_id=NEW.listing_id;
        END
        """
    )


def _postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_immutable_fact() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          RAISE EXCEPTION '0030 immutable screening fact cannot be changed'
            USING ERRCODE='23514';
        END $$
        """
    )
    for table in (
        "staff_screening_document_versions",
        "staff_screening_candidate_confirmations",
        "staff_screening_employer_reviews",
        "ats_offer_screening_terms",
        "ats_offer_acknowledgments",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0030_immutable_fact()"
        )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_coverage_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE item text; total integer; distinct_total integer;
        BEGIN
          IF pg_catalog.jsonb_typeof(NEW.declared_coverage::jsonb)<>'array' THEN
            RAISE EXCEPTION '0030 declared coverage must be an array' USING ERRCODE='23514';
          END IF;
          SELECT count(*),count(DISTINCT value) INTO total,distinct_total
          FROM pg_catalog.jsonb_array_elements_text(NEW.declared_coverage::jsonb) AS value;
          IF total<1 OR total>2 OR total<>distinct_total OR EXISTS (
            SELECT 1 FROM pg_catalog.jsonb_array_elements_text(
              NEW.declared_coverage::jsonb
            ) AS value
            WHERE value NOT IN ('criminal_record_check','vulnerable_sector_search')
          ) THEN
            RAISE EXCEPTION '0030 declared coverage is invalid' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_versions_coverage_guard BEFORE INSERT "
        "ON staff_screening_document_versions FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_coverage_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_snapshot_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE matched integer;
        BEGIN
          IF TG_OP<>'INSERT' THEN
            RAISE EXCEPTION '0030 application screening snapshot is immutable'
              USING ERRCODE='23514';
          END IF;
          SELECT count(*) INTO matched
          FROM public.ats_applications AS application
          JOIN public.ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          JOIN public.marketplace_screening_profiles AS profile
            ON profile.user_id=candidate.claimed_user_id
          JOIN public.ats_job_screening_terms AS terms
            ON terms.organization_id=application.organization_id
           AND terms.job_id=application.job_id
          WHERE application.organization_id=NEW.organization_id
            AND application.id=NEW.application_id
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND profile.user_id=NEW.candidate_user_id
            AND profile.version=NEW.screening_profile_version
            AND profile.pathway=NEW.pathway
            AND terms.version=NEW.job_terms_version
            AND NEW.driver_declaration_snapshot::jsonb=pg_catalog.jsonb_build_object(
              'willing_to_drive',profile.willing_to_drive,
              'licence_jurisdiction',profile.licence_jurisdiction,
              'licence_jurisdiction_other',profile.licence_jurisdiction_other,
              'licence_class',profile.licence_class,
              'vehicle_access',profile.vehicle_access,
              'preferred_service_radius_km',profile.preferred_service_radius_km,
              'candidate_provided',true,'operational_driver_ready',false)
            AND NEW.job_terms_snapshot::jsonb=pg_catalog.jsonb_build_object(
              'position_shape',terms.position_shape,
              'driving_requirement',terms.driving_requirement,
              'vehicle_expectation',terms.vehicle_expectation,
              'required_licence_jurisdiction',terms.required_licence_jurisdiction,
              'required_licence_jurisdiction_other',terms.required_licence_jurisdiction_other,
              'required_licence_class',terms.required_licence_class,
              'minimum_driving_experience_months',terms.minimum_driving_experience_months,
              'service_area',terms.service_area,'service_windows',terms.service_windows::jsonb,
              'mileage_policy',terms.mileage_policy,
              'driving_time_paid',terms.driving_time_paid,
              'screening_conditions',terms.screening_conditions::jsonb);
          IF matched<>1 THEN
            RAISE EXCEPTION '0030 application snapshot candidate mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_application_screening_snapshots_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON ats_application_screening_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0030_snapshot_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_share_insert_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE matched integer;
        BEGIN
          SELECT count(*) INTO matched
          FROM public.ats_application_screening_snapshots AS snapshot
          JOIN public.ats_applications AS application
            ON application.organization_id=snapshot.organization_id
           AND application.id=snapshot.application_id
          JOIN public.ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          JOIN public.marketplace_screening_profiles AS profile
            ON profile.user_id=NEW.candidate_user_id
          JOIN public.staff_screening_document_versions AS version
            ON version.id=NEW.document_version_id
           AND version.user_id=NEW.candidate_user_id
          JOIN public.staff_screening_documents AS document
            ON document.id=version.document_id AND document.user_id=version.user_id
          JOIN public.staff_screening_candidate_confirmations AS confirmation
            ON confirmation.document_version_id=version.id
           AND confirmation.user_id=version.user_id
          WHERE snapshot.organization_id=NEW.organization_id
            AND snapshot.application_id=NEW.application_id
            AND snapshot.candidate_user_id=NEW.candidate_user_id
            AND snapshot.screening_profile_version=NEW.screening_profile_version
            AND profile.version=NEW.screening_profile_version
            AND profile.pathway=snapshot.pathway
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND document.current_version_number=version.version_number
            AND document.status='confirmed'
            AND (confirmation.expiry_date IS NULL OR confirmation.expiry_date>=CURRENT_DATE);
          IF matched<>1 THEN
            RAISE EXCEPTION '0030 screening share candidate or version mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_shares_insert_guard BEFORE INSERT "
        "ON staff_screening_application_shares FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_share_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_review_insert_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM public.staff_screening_application_shares AS share
            JOIN public.staff_screening_document_versions AS version
              ON version.id=share.document_version_id
             AND version.user_id=share.candidate_user_id
            WHERE share.organization_id=NEW.organization_id
              AND share.application_id=NEW.application_id
              AND share.id=NEW.share_id AND share.revoked_at IS NULL
              AND version.declared_coverage::jsonb ? NEW.requirement_class
          ) THEN
            RAISE EXCEPTION '0030 review does not match an active shared requirement'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_reviews_insert_guard BEFORE INSERT "
        "ON staff_screening_employer_reviews FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_review_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_document_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.current_version_number<>OLD.current_version_number AND NOT EXISTS (
            SELECT 1 FROM public.staff_screening_document_versions AS version
            WHERE version.document_id=NEW.id AND version.user_id=NEW.user_id
              AND version.version_number=NEW.current_version_number
          ) THEN
            RAISE EXCEPTION '0030 current screening version does not exist'
              USING ERRCODE='23514';
          END IF;
          IF NEW.status='confirmed' AND NOT EXISTS (
            SELECT 1 FROM public.staff_screening_document_versions AS version
            JOIN public.staff_screening_candidate_confirmations AS confirmation
              ON confirmation.document_version_id=version.id
             AND confirmation.user_id=version.user_id
            WHERE version.document_id=NEW.id AND version.user_id=NEW.user_id
              AND version.version_number=NEW.current_version_number
          ) THEN
            RAISE EXCEPTION '0030 confirmed document lacks current confirmation'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_documents_guard BEFORE UPDATE "
        "ON staff_screening_documents FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_document_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_offer_terms_insert_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM public.ats_offers AS offer
            JOIN public.ats_application_screening_snapshots AS snapshot
              ON snapshot.organization_id=offer.organization_id
             AND snapshot.application_id=offer.application_id
            WHERE offer.organization_id=NEW.organization_id
              AND offer.id=NEW.offer_id AND offer.version=NEW.offer_version
              AND (
                (NEW.position_shape='educator_only' AND snapshot.pathway IN
                  ('educator','student_educator','educator_driver'))
                OR (NEW.position_shape='driver_only' AND snapshot.pathway IN
                  ('driver','educator_driver'))
                OR (NEW.position_shape='educator_driver'
                  AND snapshot.pathway='educator_driver')
              )
              AND (
                NEW.position_shape='educator_only'
                OR (
                  COALESCE((snapshot.driver_declaration_snapshot::jsonb
                    ->>'willing_to_drive')::boolean,false)
                  AND (snapshot.driver_declaration_snapshot::jsonb
                    ->>'operational_driver_ready')::boolean=false
                  AND (snapshot.driver_declaration_snapshot::jsonb
                    ->>'licence_jurisdiction') IS NOT DISTINCT FROM
                      NEW.required_licence_jurisdiction
                  AND (snapshot.driver_declaration_snapshot::jsonb
                    ->>'licence_class') IS NOT DISTINCT FROM NEW.required_licence_class
                  AND (
                    NEW.required_licence_jurisdiction<>'OTHER'
                    OR (snapshot.driver_declaration_snapshot::jsonb
                      ->>'licence_jurisdiction_other') IS NOT DISTINCT FROM
                        NEW.required_licence_jurisdiction_other
                  )
                  AND (
                    (NEW.vehicle_expectation='personal_vehicle'
                      AND snapshot.driver_declaration_snapshot::jsonb
                        ->>'vehicle_access' IN ('personal_vehicle','either'))
                    OR (NEW.vehicle_expectation IN ('organization_vehicle','either')
                      AND snapshot.driver_declaration_snapshot::jsonb
                        ->>'vehicle_access'<>'none')
                  )
                )
              )
          ) THEN
            RAISE EXCEPTION '0030 offer duties exceed application disclosure'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_offer_screening_terms_insert_guard BEFORE INSERT "
        "ON ats_offer_screening_terms FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_offer_terms_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_offer_terms_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.ats_offer_screening_terms AS terms
            WHERE terms.organization_id=OLD.organization_id AND terms.offer_id=OLD.id
          ) AND (
            NEW.organization_id IS DISTINCT FROM OLD.organization_id
            OR NEW.application_id IS DISTINCT FROM OLD.application_id
            OR NEW.version IS DISTINCT FROM OLD.version
            OR NEW.position_title IS DISTINCT FROM OLD.position_title
            OR NEW.start_date IS DISTINCT FROM OLD.start_date
            OR NEW.compensation IS DISTINCT FROM OLD.compensation
            OR NEW.hourly_rate IS DISTINCT FROM OLD.hourly_rate
            OR NEW.notes IS DISTINCT FROM OLD.notes
            OR NEW.terms IS DISTINCT FROM OLD.terms
            OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
          ) THEN
            RAISE EXCEPTION '0030 offer contractual terms are immutable'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_offers_0030_terms_guard BEFORE UPDATE ON ats_offers "
        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0030_offer_terms_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_share_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP='DELETE' OR OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL
             OR NEW.id<>OLD.id OR NEW.candidate_user_id<>OLD.candidate_user_id
             OR NEW.organization_id<>OLD.organization_id
             OR NEW.application_id<>OLD.application_id
             OR NEW.document_version_id<>OLD.document_version_id
             OR NEW.screening_profile_version<>OLD.screening_profile_version
             OR NEW.shared_at<>OLD.shared_at THEN
            RAISE EXCEPTION '0030 screening share is immutable except one-way revocation'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_shares_guard BEFORE UPDATE OR DELETE "
        "ON staff_screening_application_shares FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_share_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.caresync_0030_offer_ack_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE matched integer;
        BEGIN
          SELECT count(*) INTO matched
          FROM public.ats_offers AS offer
          JOIN public.ats_offer_screening_terms AS terms
            ON terms.organization_id=offer.organization_id AND terms.offer_id=offer.id
          JOIN public.ats_applications AS application
            ON application.organization_id=offer.organization_id
           AND application.id=offer.application_id
          JOIN public.ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          WHERE offer.organization_id=NEW.organization_id AND offer.id=NEW.offer_id
            AND offer.status='accepted' AND offer.version=NEW.offer_version
            AND terms.offer_version=NEW.offer_version
            AND terms.terms_digest=NEW.terms_digest
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND NEW.driver_terms_acknowledged=
                (terms.driving_requirement<>'not_applicable');
          IF matched<>1 THEN
            RAISE EXCEPTION '0030 offer acknowledgment does not match accepted terms'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER ats_offer_acknowledgments_guard BEFORE INSERT "
        "ON ats_offer_acknowledgments FOR EACH ROW "
        "EXECUTE FUNCTION public.caresync_0030_offer_ack_guard()"
    )


def _sqlite_guards() -> None:
    for table in (
        "staff_screening_document_versions",
        "staff_screening_candidate_confirmations",
        "staff_screening_employer_reviews",
        "ats_offer_screening_terms",
        "ats_offer_acknowledgments",
    ):
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_immutable_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN "
                "SELECT RAISE(ABORT,'0030 immutable screening fact cannot be changed'); END"
            )
    op.execute(
        """
        CREATE TRIGGER staff_screening_versions_coverage_guard
        BEFORE INSERT ON staff_screening_document_versions
        WHEN json_valid(NEW.declared_coverage)=0
          OR json_type(NEW.declared_coverage)<>'array'
          OR json_array_length(NEW.declared_coverage)<1
          OR json_array_length(NEW.declared_coverage)>2
          OR EXISTS (
            SELECT 1 FROM json_each(NEW.declared_coverage)
            WHERE value NOT IN ('criminal_record_check','vulnerable_sector_search')
          )
          OR (SELECT count(*) FROM json_each(NEW.declared_coverage)) <>
             (SELECT count(DISTINCT value) FROM json_each(NEW.declared_coverage))
        BEGIN
          SELECT RAISE(ABORT,'0030 declared coverage is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_application_screening_snapshots_json_guard
        BEFORE INSERT ON ats_application_screening_snapshots
        WHEN CASE
          WHEN json_valid(NEW.driver_declaration_snapshot)=0
            OR json_valid(NEW.job_terms_snapshot)=0 THEN 1
          WHEN json_type(NEW.driver_declaration_snapshot)<>'object'
            OR json_type(NEW.job_terms_snapshot)<>'object' THEN 1
          WHEN (SELECT count(*) FROM json_each(NEW.driver_declaration_snapshot))<>8
            OR (SELECT count(DISTINCT key)
                FROM json_each(NEW.driver_declaration_snapshot))<>8 THEN 1
          WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.driver_declaration_snapshot)
            WHERE key NOT IN (
              'willing_to_drive','licence_jurisdiction',
              'licence_jurisdiction_other','licence_class','vehicle_access',
              'preferred_service_radius_km','candidate_provided',
              'operational_driver_ready'
            )
          ) THEN 1
          WHEN (SELECT count(*) FROM json_each(NEW.job_terms_snapshot))<>12
            OR (SELECT count(DISTINCT key) FROM json_each(NEW.job_terms_snapshot))<>12 THEN 1
          WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.job_terms_snapshot)
            WHERE key NOT IN (
              'position_shape','driving_requirement','vehicle_expectation',
              'required_licence_jurisdiction',
              'required_licence_jurisdiction_other','required_licence_class',
              'minimum_driving_experience_months','service_area','service_windows',
              'mileage_policy','driving_time_paid','screening_conditions'
            )
          ) THEN 1
          ELSE 0
        END
        BEGIN
          SELECT RAISE(ABORT,'0030 application snapshot JSON shape is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_application_screening_snapshots_insert_guard
        BEFORE INSERT ON ats_application_screening_snapshots
        WHEN NOT EXISTS (
          SELECT 1 FROM ats_applications AS application
          JOIN ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          JOIN marketplace_screening_profiles AS profile
            ON profile.user_id=candidate.claimed_user_id
          JOIN ats_job_screening_terms AS terms
            ON terms.organization_id=application.organization_id
           AND terms.job_id=application.job_id
          WHERE application.organization_id=NEW.organization_id
            AND application.id=NEW.application_id
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND profile.version=NEW.screening_profile_version
            AND profile.pathway=NEW.pathway
            AND terms.version=NEW.job_terms_version
            AND json_extract(NEW.driver_declaration_snapshot,'$.willing_to_drive')
                =profile.willing_to_drive
            AND json_extract(NEW.driver_declaration_snapshot,'$.licence_jurisdiction')
                IS profile.licence_jurisdiction
            AND json_extract(NEW.driver_declaration_snapshot,'$.licence_jurisdiction_other')
                IS profile.licence_jurisdiction_other
            AND json_extract(NEW.driver_declaration_snapshot,'$.licence_class')
                IS profile.licence_class
            AND json_extract(NEW.driver_declaration_snapshot,'$.vehicle_access')
                =profile.vehicle_access
            AND json_extract(NEW.driver_declaration_snapshot,'$.preferred_service_radius_km')
                IS profile.preferred_service_radius_km
            AND json_extract(NEW.driver_declaration_snapshot,'$.candidate_provided')=1
            AND json_extract(NEW.driver_declaration_snapshot,'$.operational_driver_ready')=0
            AND json_extract(NEW.job_terms_snapshot,'$.position_shape')=terms.position_shape
            AND json_extract(NEW.job_terms_snapshot,'$.driving_requirement')
                =terms.driving_requirement
            AND json_extract(NEW.job_terms_snapshot,'$.vehicle_expectation')
                =terms.vehicle_expectation
            AND json_extract(NEW.job_terms_snapshot,'$.required_licence_jurisdiction')
                IS terms.required_licence_jurisdiction
            AND json_extract(NEW.job_terms_snapshot,'$.required_licence_jurisdiction_other')
                IS terms.required_licence_jurisdiction_other
            AND json_extract(NEW.job_terms_snapshot,'$.required_licence_class')
                IS terms.required_licence_class
            AND json_extract(NEW.job_terms_snapshot,'$.minimum_driving_experience_months')
                =terms.minimum_driving_experience_months
            AND json_extract(NEW.job_terms_snapshot,'$.service_area') IS terms.service_area
            AND json(json_extract(NEW.job_terms_snapshot,'$.service_windows'))
                =json(terms.service_windows)
            AND json_extract(NEW.job_terms_snapshot,'$.mileage_policy') IS terms.mileage_policy
            AND json_extract(NEW.job_terms_snapshot,'$.driving_time_paid')
                =terms.driving_time_paid
            AND json(json_extract(NEW.job_terms_snapshot,'$.screening_conditions'))
                =json(terms.screening_conditions)
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 application snapshot candidate mismatch');
        END
        """
    )
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER ats_application_screening_snapshots_immutable_{operation.lower()} "
            f"BEFORE {operation} ON ats_application_screening_snapshots BEGIN "
            "SELECT RAISE(ABORT,'0030 application screening snapshot is immutable'); END"
        )
    op.execute(
        """
        CREATE TRIGGER staff_screening_shares_insert_guard
        BEFORE INSERT ON staff_screening_application_shares
        WHEN NOT EXISTS (
          SELECT 1 FROM ats_application_screening_snapshots AS snapshot
          JOIN ats_applications AS application
            ON application.organization_id=snapshot.organization_id
           AND application.id=snapshot.application_id
          JOIN ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          JOIN marketplace_screening_profiles AS profile
            ON profile.user_id=NEW.candidate_user_id
          JOIN staff_screening_document_versions AS version
            ON version.id=NEW.document_version_id
           AND version.user_id=NEW.candidate_user_id
          JOIN staff_screening_documents AS document
            ON document.id=version.document_id AND document.user_id=version.user_id
          JOIN staff_screening_candidate_confirmations AS confirmation
            ON confirmation.document_version_id=version.id
           AND confirmation.user_id=version.user_id
          WHERE snapshot.organization_id=NEW.organization_id
            AND snapshot.application_id=NEW.application_id
            AND snapshot.candidate_user_id=NEW.candidate_user_id
            AND snapshot.screening_profile_version=NEW.screening_profile_version
            AND profile.version=NEW.screening_profile_version
            AND profile.pathway=snapshot.pathway
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND document.current_version_number=version.version_number
            AND document.status='confirmed'
            AND (confirmation.expiry_date IS NULL OR confirmation.expiry_date>=date('now'))
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 screening share candidate or version mismatch');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_screening_documents_guard
        BEFORE UPDATE ON staff_screening_documents
        WHEN (
          NEW.current_version_number<>OLD.current_version_number AND NOT EXISTS (
            SELECT 1 FROM staff_screening_document_versions AS version
            WHERE version.document_id=NEW.id AND version.user_id=NEW.user_id
              AND version.version_number=NEW.current_version_number
          )
        ) OR (
          NEW.status='confirmed' AND NOT EXISTS (
            SELECT 1 FROM staff_screening_document_versions AS version
            JOIN staff_screening_candidate_confirmations AS confirmation
              ON confirmation.document_version_id=version.id
             AND confirmation.user_id=version.user_id
            WHERE version.document_id=NEW.id AND version.user_id=NEW.user_id
              AND version.version_number=NEW.current_version_number
          )
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 screening document current version is invalid');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_screening_reviews_insert_guard
        BEFORE INSERT ON staff_screening_employer_reviews
        WHEN NOT EXISTS (
          SELECT 1 FROM staff_screening_application_shares AS share
          JOIN staff_screening_document_versions AS version
            ON version.id=share.document_version_id
           AND version.user_id=share.candidate_user_id
          JOIN json_each(version.declared_coverage) AS coverage
            ON coverage.value=NEW.requirement_class
          WHERE share.organization_id=NEW.organization_id
            AND share.application_id=NEW.application_id
            AND share.id=NEW.share_id AND share.revoked_at IS NULL
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 review does not match an active shared requirement');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_offer_screening_terms_insert_guard
        BEFORE INSERT ON ats_offer_screening_terms
        WHEN NOT EXISTS (
          SELECT 1 FROM ats_offers AS offer
          JOIN ats_application_screening_snapshots AS snapshot
            ON snapshot.organization_id=offer.organization_id
           AND snapshot.application_id=offer.application_id
          WHERE offer.organization_id=NEW.organization_id
            AND offer.id=NEW.offer_id AND offer.version=NEW.offer_version
            AND (
              (NEW.position_shape='educator_only' AND snapshot.pathway IN
                ('educator','student_educator','educator_driver'))
              OR (NEW.position_shape='driver_only' AND snapshot.pathway IN
                ('driver','educator_driver'))
              OR (NEW.position_shape='educator_driver'
                AND snapshot.pathway='educator_driver')
            )
            AND (
              NEW.position_shape='educator_only'
              OR (
                json_extract(snapshot.driver_declaration_snapshot,'$.willing_to_drive')=1
                AND json_extract(
                  snapshot.driver_declaration_snapshot,'$.operational_driver_ready'
                )=0
                AND json_extract(
                  snapshot.driver_declaration_snapshot,'$.licence_jurisdiction'
                ) IS NEW.required_licence_jurisdiction
                AND json_extract(
                  snapshot.driver_declaration_snapshot,'$.licence_class'
                ) IS NEW.required_licence_class
                AND (
                  NEW.required_licence_jurisdiction<>'OTHER'
                  OR json_extract(
                    snapshot.driver_declaration_snapshot,'$.licence_jurisdiction_other'
                  ) IS NEW.required_licence_jurisdiction_other
                )
                AND (
                  (NEW.vehicle_expectation='personal_vehicle'
                    AND json_extract(
                      snapshot.driver_declaration_snapshot,'$.vehicle_access'
                    ) IN ('personal_vehicle','either'))
                  OR (NEW.vehicle_expectation IN ('organization_vehicle','either')
                    AND json_extract(
                      snapshot.driver_declaration_snapshot,'$.vehicle_access'
                    )<>'none')
                )
              )
            )
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 offer duties exceed application disclosure');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER ats_offers_0030_terms_guard
        BEFORE UPDATE ON ats_offers
        WHEN EXISTS (
          SELECT 1 FROM ats_offer_screening_terms AS terms
          WHERE terms.organization_id=OLD.organization_id AND terms.offer_id=OLD.id
        ) AND (
          NEW.organization_id IS NOT OLD.organization_id
          OR NEW.application_id IS NOT OLD.application_id
          OR NEW.version IS NOT OLD.version
          OR NEW.position_title IS NOT OLD.position_title
          OR NEW.start_date IS NOT OLD.start_date
          OR NEW.compensation IS NOT OLD.compensation
          OR NEW.hourly_rate IS NOT OLD.hourly_rate
          OR NEW.notes IS NOT OLD.notes
          OR NEW.terms IS NOT OLD.terms
          OR NEW.expires_at IS NOT OLD.expires_at
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 offer contractual terms are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_screening_shares_guard_update
        BEFORE UPDATE ON staff_screening_application_shares
        WHEN OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL
          OR NEW.id<>OLD.id OR NEW.candidate_user_id<>OLD.candidate_user_id
          OR NEW.organization_id<>OLD.organization_id
          OR NEW.application_id<>OLD.application_id
          OR NEW.document_version_id<>OLD.document_version_id
          OR NEW.screening_profile_version<>OLD.screening_profile_version
          OR NEW.shared_at<>OLD.shared_at
        BEGIN
          SELECT RAISE(ABORT,'0030 screening share is immutable except one-way revocation');
        END
        """
    )
    op.execute(
        "CREATE TRIGGER staff_screening_shares_guard_delete BEFORE DELETE "
        "ON staff_screening_application_shares BEGIN "
        "SELECT RAISE(ABORT,'0030 screening share cannot be deleted'); END"
    )
    op.execute(
        """
        CREATE TRIGGER ats_offer_acknowledgments_guard
        BEFORE INSERT ON ats_offer_acknowledgments
        WHEN NOT EXISTS (
          SELECT 1 FROM ats_offers AS offer
          JOIN ats_offer_screening_terms AS terms
            ON terms.organization_id=offer.organization_id AND terms.offer_id=offer.id
          JOIN ats_applications AS application
            ON application.organization_id=offer.organization_id
           AND application.id=offer.application_id
          JOIN ats_candidates AS candidate
            ON candidate.organization_id=application.organization_id
           AND candidate.id=application.candidate_id
          WHERE offer.organization_id=NEW.organization_id AND offer.id=NEW.offer_id
            AND offer.status='accepted' AND offer.version=NEW.offer_version
            AND terms.offer_version=NEW.offer_version
            AND terms.terms_digest=NEW.terms_digest
            AND candidate.claimed_user_id=NEW.candidate_user_id
            AND NEW.driver_terms_acknowledged=
                (terms.driving_requirement<>'not_applicable')
        )
        BEGIN
          SELECT RAISE(ABORT,'0030 offer acknowledgment does not match accepted terms');
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
              public.sync_marketplace_job_screening_from_terms(),
              public.sync_marketplace_job_screening_from_listing(),
              public.caresync_0030_immutable_fact(),
              public.caresync_0030_coverage_guard(),
              public.caresync_0030_snapshot_guard(),
              public.caresync_0030_share_insert_guard(),
              public.caresync_0030_review_insert_guard(),
              public.caresync_0030_document_guard(),
              public.caresync_0030_offer_terms_insert_guard(),
              public.caresync_0030_offer_terms_guard(),
              public.caresync_0030_share_guard(),
              public.caresync_0030_offer_ack_guard()
              FROM caresync_basic_app;
          END IF;
        END $revoke$
        """
    )
    org = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    manager = (
        "EXISTS (SELECT 1 FROM organization_memberships AS membership "
        "JOIN roles AS role ON role.organization_id=membership.organization_id "
        "AND role.id=membership.role_id WHERE membership.organization_id="
        f"{org} AND membership.user_id={user} AND membership.status='active' "
        "AND role.permissions::jsonb @> '[\"ats:manage\"]'::jsonb)"
    )
    reader = (
        "EXISTS (SELECT 1 FROM organization_memberships AS membership "
        "JOIN roles AS role ON role.organization_id=membership.organization_id "
        "AND role.id=membership.role_id WHERE membership.organization_id="
        f"{org} AND membership.user_id={user} AND membership.status='active' AND ("
        "role.permissions::jsonb @> '[\"ats:read\"]'::jsonb OR "
        "role.permissions::jsonb @> '[\"ats:manage\"]'::jsonb))"
    )
    op.execute("ALTER TABLE ats_job_screening_terms ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ats_job_screening_terms FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ats_job_screening_terms_read ON ats_job_screening_terms "
        f"FOR SELECT USING ((organization_id={org} AND {reader}) OR EXISTS ("
        "SELECT 1 FROM marketplace_jobs AS public_listing "
        "WHERE public_listing.listing_id=ats_job_screening_terms.job_id "
        "AND public_listing.organization_id=ats_job_screening_terms.organization_id))"
    )
    op.execute(
        "CREATE POLICY ats_job_screening_terms_manage ON ats_job_screening_terms "
        f"FOR ALL USING (organization_id={org} AND {manager}) "
        f"WITH CHECK (organization_id={org} AND {manager})"
    )

    op.execute("ALTER TABLE ats_offer_screening_terms ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ats_offer_screening_terms FORCE ROW LEVEL SECURITY")
    candidate_offer = (
        "EXISTS (SELECT 1 FROM ats_offers AS offer "
        "JOIN ats_applications AS application ON "
        "application.organization_id=offer.organization_id "
        "AND application.id=offer.application_id "
        "JOIN ats_candidates AS candidate ON "
        "candidate.organization_id=application.organization_id "
        "AND candidate.id=application.candidate_id "
        "WHERE offer.id=ats_offer_screening_terms.offer_id "
        "AND offer.organization_id=ats_offer_screening_terms.organization_id "
        f"AND candidate.claimed_user_id={user} "
        "AND (offer.status IN ('sent','accepted','declined','withdrawn') "
        "OR (offer.status='superseded' AND offer.sent_at IS NOT NULL)))"
    )
    op.execute(
        "CREATE POLICY ats_offer_screening_terms_select ON ats_offer_screening_terms "
        f"FOR SELECT USING ((organization_id={org} AND {manager}) OR {candidate_offer})"
    )
    op.execute(
        "CREATE POLICY ats_offer_screening_terms_manage_insert "
        "ON ats_offer_screening_terms FOR INSERT "
        f"WITH CHECK (organization_id={org} AND {manager})"
    )

    op.execute("ALTER TABLE ats_application_screening_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ats_application_screening_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ats_application_screening_snapshots_select "
        "ON ats_application_screening_snapshots FOR SELECT USING ("
        f"candidate_user_id={user} OR (organization_id={org} AND {manager}))"
    )
    op.execute(
        "CREATE POLICY ats_application_screening_snapshots_candidate_insert "
        "ON ats_application_screening_snapshots FOR INSERT "
        f"WITH CHECK (candidate_user_id={user})"
    )

    op.execute("ALTER TABLE marketplace_screening_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE marketplace_screening_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY marketplace_screening_profiles_owner ON marketplace_screening_profiles "
        f"FOR ALL USING (user_id={user}) WITH CHECK (user_id={user})"
    )
    op.execute(
        "CREATE POLICY marketplace_screening_profiles_employer_select "
        "ON marketplace_screening_profiles FOR SELECT USING ("
        f"{manager} AND (EXISTS (SELECT 1 FROM marketplace_profiles AS profile "
        "WHERE profile.user_id=marketplace_screening_profiles.user_id "
        "AND profile.discoverable=true "
        "AND profile.onboarding_completed_at IS NOT NULL) OR EXISTS ("
        "SELECT 1 FROM ats_candidates AS candidate "
        "JOIN ats_applications AS application "
        "ON application.organization_id=candidate.organization_id "
        "AND application.candidate_id=candidate.id "
        "JOIN ats_application_screening_snapshots AS snapshot "
        "ON snapshot.organization_id=application.organization_id "
        "AND snapshot.application_id=application.id "
        "WHERE candidate.claimed_user_id=marketplace_screening_profiles.user_id "
        f"AND candidate.organization_id={org})))"
    )
    for table in (
        "staff_screening_documents",
        "staff_screening_document_versions",
        "staff_screening_candidate_confirmations",
    ):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table}_owner" ON "{table}" FOR ALL '
            f"USING (user_id={user}) WITH CHECK (user_id={user})"
        )
    op.execute(
        "CREATE POLICY staff_screening_versions_shared_select "
        "ON staff_screening_document_versions FOR SELECT USING (EXISTS ("
        "SELECT 1 FROM staff_screening_application_shares AS share "
        "WHERE share.document_version_id=staff_screening_document_versions.id "
        f"AND share.organization_id={org} AND share.revoked_at IS NULL AND {manager}))"
    )
    op.execute(
        "CREATE POLICY staff_screening_confirmations_shared_select "
        "ON staff_screening_candidate_confirmations FOR SELECT USING (EXISTS ("
        "SELECT 1 FROM staff_screening_application_shares AS share "
        "WHERE share.document_version_id="
        "staff_screening_candidate_confirmations.document_version_id "
        f"AND share.organization_id={org} AND share.revoked_at IS NULL AND {manager}))"
    )
    op.execute(
        "CREATE POLICY staff_screening_documents_shared_select "
        "ON staff_screening_documents FOR SELECT USING (EXISTS ("
        "SELECT 1 FROM staff_screening_document_versions AS version "
        "JOIN staff_screening_application_shares AS share "
        "ON share.document_version_id=version.id "
        "WHERE version.document_id=staff_screening_documents.id "
        f"AND share.organization_id={org} AND share.revoked_at IS NULL AND {manager}))"
    )
    # PostgreSQL applies UPDATE policies to SELECT FOR SHARE. This lock-only
    # policy lets a manager stabilize a currently shared document during final
    # provisioning while WITH CHECK (false) forbids any manager-authored edit.
    op.execute(
        "CREATE POLICY staff_screening_documents_employer_lock "
        "ON staff_screening_documents FOR UPDATE USING (EXISTS ("
        "SELECT 1 FROM staff_screening_document_versions AS version "
        "JOIN staff_screening_application_shares AS share "
        "ON share.document_version_id=version.id "
        "WHERE version.document_id=staff_screening_documents.id "
        f"AND share.organization_id={org} AND share.revoked_at IS NULL AND {manager})) "
        "WITH CHECK (false)"
    )

    op.execute("ALTER TABLE staff_screening_application_shares ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_screening_application_shares FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY staff_screening_shares_owner ON staff_screening_application_shares "
        f"FOR ALL USING (candidate_user_id={user}) WITH CHECK (candidate_user_id={user})"
    )
    op.execute(
        "CREATE POLICY staff_screening_shares_employer_select "
        "ON staff_screening_application_shares FOR SELECT "
        f"USING (organization_id={org} AND {manager})"
    )
    op.execute(
        "CREATE POLICY staff_screening_shares_employer_lock "
        "ON staff_screening_application_shares FOR UPDATE "
        f"USING (organization_id={org} AND {manager}) WITH CHECK (false)"
    )

    op.execute("ALTER TABLE staff_screening_employer_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_screening_employer_reviews FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY staff_screening_reviews_employer_select "
        "ON staff_screening_employer_reviews FOR SELECT "
        f"USING (organization_id={org} AND {manager})"
    )
    op.execute(
        "CREATE POLICY staff_screening_reviews_employer_insert "
        "ON staff_screening_employer_reviews FOR INSERT "
        f"WITH CHECK (organization_id={org} AND reviewer_user_id={user} AND {manager})"
    )
    op.execute(
        "CREATE POLICY staff_screening_reviews_candidate_select "
        "ON staff_screening_employer_reviews FOR SELECT USING (EXISTS ("
        "SELECT 1 FROM staff_screening_application_shares AS share "
        "WHERE share.id=staff_screening_employer_reviews.share_id "
        f"AND share.candidate_user_id={user}))"
    )

    op.execute("ALTER TABLE ats_offer_acknowledgments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ats_offer_acknowledgments FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ats_offer_acknowledgments_select ON ats_offer_acknowledgments "
        f"FOR SELECT USING ((organization_id={org} AND {manager}) "
        f"OR candidate_user_id={user})"
    )
    op.execute(
        "CREATE POLICY ats_offer_acknowledgments_candidate_insert "
        "ON ats_offer_acknowledgments FOR INSERT "
        f"WITH CHECK (candidate_user_id={user})"
    )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app') THEN
            GRANT SELECT,INSERT,UPDATE ON TABLE
              ats_job_screening_terms,marketplace_screening_profiles,staff_screening_documents,
              staff_screening_application_shares TO caresync_basic_app;
            GRANT SELECT,INSERT ON TABLE
              ats_application_screening_snapshots,ats_offer_screening_terms,
              staff_screening_document_versions,
              staff_screening_candidate_confirmations,staff_screening_employer_reviews,
              ats_offer_acknowledgments
              TO caresync_basic_app;
            GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE marketplace_job_screening_terms
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind, checkfirst=False)
    _backfill_sidecars(bind)
    if bind.dialect.name == "postgresql":
        _postgres_projection()
        _postgres_guards()
        _postgres_rls_and_grants()
    else:
        _sqlite_projection()
        _sqlite_guards()


def _populated(bind, table: str) -> bool:
    return bool(bind.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM "{table}" LIMIT 1)')))


def _nondefault_terms(bind, table: str) -> bool:
    return bool(
        bind.scalar(
            sa.text(
                f"SELECT EXISTS(SELECT 1 FROM {table} WHERE "
                "position_shape<>'educator_only' OR driving_requirement<>'not_applicable' "
                "OR vehicle_expectation<>'none' OR required_licence_jurisdiction IS NOT NULL "
                "OR required_licence_jurisdiction_other IS NOT NULL "
                "OR required_licence_class IS NOT NULL "
                "OR minimum_driving_experience_months<>0 OR service_area IS NOT NULL "
                "OR CAST(service_windows AS TEXT)<>'[]' OR mileage_policy IS NOT NULL "
                "OR driving_time_paid=true OR CAST(screening_conditions AS TEXT)<>'[]')"
            )
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    protected = (
        "marketplace_screening_profiles",
        "ats_application_screening_snapshots",
        "staff_screening_documents",
        "staff_screening_document_versions",
        "staff_screening_candidate_confirmations",
        "staff_screening_application_shares",
        "staff_screening_employer_reviews",
        "ats_offer_acknowledgments",
    )
    if any(_populated(bind, table) for table in protected):
        raise RuntimeError("0030 downgrade refused: staff screening records exist")
    if _nondefault_terms(bind, "ats_job_screening_terms"):
        raise RuntimeError("0030 downgrade refused: structured job driving terms exist")
    if _nondefault_terms(bind, "ats_offer_screening_terms"):
        raise RuntimeError("0030 downgrade refused: structured offer driving terms exist")

    if bind.dialect.name == "postgresql":
        for trigger, table in (
            ("ats_job_screening_marketplace", "ats_job_screening_terms"),
            ("marketplace_jobs_screening_projection", "marketplace_jobs"),
            (
                "staff_screening_versions_coverage_guard",
                "staff_screening_document_versions",
            ),
            (
                "ats_application_screening_snapshots_guard",
                "ats_application_screening_snapshots",
            ),
            ("staff_screening_shares_insert_guard", "staff_screening_application_shares"),
            ("staff_screening_reviews_insert_guard", "staff_screening_employer_reviews"),
            ("staff_screening_documents_guard", "staff_screening_documents"),
            ("ats_offer_screening_terms_insert_guard", "ats_offer_screening_terms"),
            ("ats_offers_0030_terms_guard", "ats_offers"),
            ("staff_screening_shares_guard", "staff_screening_application_shares"),
            ("ats_offer_acknowledgments_guard", "ats_offer_acknowledgments"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        for table in (
            "staff_screening_document_versions",
            "staff_screening_candidate_confirmations",
            "staff_screening_employer_reviews",
            "ats_offer_screening_terms",
            "ats_offer_acknowledgments",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        for function in (
            "sync_marketplace_job_screening_from_terms()",
            "sync_marketplace_job_screening_from_listing()",
            "caresync_0030_immutable_fact()",
            "caresync_0030_coverage_guard()",
            "caresync_0030_snapshot_guard()",
            "caresync_0030_share_insert_guard()",
            "caresync_0030_review_insert_guard()",
            "caresync_0030_document_guard()",
            "caresync_0030_offer_terms_insert_guard()",
            "caresync_0030_offer_terms_guard()",
            "caresync_0030_share_guard()",
            "caresync_0030_offer_ack_guard()",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS public.{function}")
    else:
        for trigger in (
            "ats_job_screening_marketplace_insert",
            "ats_job_screening_marketplace_update",
            "marketplace_jobs_screening_projection",
            "staff_screening_versions_coverage_guard",
            "ats_application_screening_snapshots_json_guard",
            "ats_application_screening_snapshots_insert_guard",
            "ats_application_screening_snapshots_immutable_update",
            "ats_application_screening_snapshots_immutable_delete",
            "staff_screening_shares_insert_guard",
            "staff_screening_reviews_insert_guard",
            "ats_offer_screening_terms_insert_guard",
            "staff_screening_documents_guard",
            "ats_offers_0030_terms_guard",
            "staff_screening_shares_guard_update",
            "staff_screening_shares_guard_delete",
            "ats_offer_acknowledgments_guard",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        for table in (
            "staff_screening_document_versions",
            "staff_screening_candidate_confirmations",
            "staff_screening_employer_reviews",
            "ats_offer_screening_terms",
            "ats_offer_acknowledgments",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_update")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_delete")
    for model in reversed(TABLES):
        model.__table__.drop(bind, checkfirst=False)

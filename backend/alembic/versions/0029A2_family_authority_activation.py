"""Activate reviewed family authority without enabling release checkout.

Revision ID: 0029A2_authority_activation
Revises: 0029A1_family_evidence_vault
Create Date: 2026-07-17

This revision keeps the educator release context and attendance checkout closed.
It adds the second, independent consent evidence tuple and database-enforced
evidence-kind activation matrix for administrator-authored authority records.
"""

# The literal checks are mirrored by ``BasicBase.metadata`` for portable
# migration/schema comparisons.
# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

revision = "0029A2_authority_activation"
down_revision = "0029A1_family_evidence_vault"
branch_labels = None
depends_on = None


ACTIVATION_TABLES = (
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
)

ACTIVATION_COMMANDS = (
    "child.release.authorization.grant",
    "child.release.authorization.revoke",
    "child.release.rule.create",
    "child.release.rule.revoke",
    "organization.consent.policy.publish",
    "child.consent.record",
    "child.consent.withdraw",
)

CONFIDENTIAL_AUTHORITY_AUDIT_PREFIXES = (
    "family.authority.",
    "child.release.",
    "child.consent.",
    "organization.consent.",
)


def _preflight_empty_activation_history(*, downgrade: bool) -> None:
    """Refuse a lossy boundary change before the first schema mutation."""

    bind = op.get_bind()
    table_counts = {
        table_name: int(
            bind.execute(sa.text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
        )
        for table_name in ACTIVATION_TABLES
    }
    receipt_count = int(
        bind.execute(
            sa.text(
                "SELECT count(*) FROM childcare_command_receipts "
                "WHERE target_type IN ('release_authorization','release_rule','consent') "
                "OR command_type IN "
                "('child.release.authorization.grant',"
                "'child.release.authorization.revoke',"
                "'child.release.rule.create','child.release.rule.revoke',"
                "'organization.consent.policy.publish','child.consent.record',"
                "'child.consent.withdraw')"
            )
        ).scalar_one()
    )
    delegation_rows = 0
    if downgrade:
        delegation_rows = int(
            bind.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM family_authority_evidence "
                    " WHERE evidence_kind='signed_release_delegation') + "
                    "(SELECT count(*) FROM family_authority_evidence_objects "
                    " WHERE evidence_kind='signed_release_delegation')"
                )
            ).scalar_one()
        )
    if any(table_counts.values()) or receipt_count or delegation_rows:
        direction = "downgrade" if downgrade else "upgrade"
        raise RuntimeError(
            f"0029A2 {direction} refused before DDL because activation history "
            "cannot be safely transformed: "
            f"tables={table_counts}, receipts={receipt_count}, "
            f"signed_release_delegation_rows={delegation_rows}"
        )


def _install_audit_realtime_bridge(*, suppress_confidential_authority: bool) -> None:
    """Keep exact authority audit history out of the tenant-wide realtime stream.

    A2 has no educator release-context consumer, so it deliberately suppresses
    confidential authority audit rows rather than inventing a generic event.
    The child-head, null-identifier invalidation belongs to 0029B, where there
    is a bounded consumer for it.
    """

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        suppression = ""
        if suppress_confidential_authority:
            suppression = """
          IF NEW.action LIKE 'family.authority.%'
             OR NEW.action LIKE 'child.release.%'
             OR NEW.action LIKE 'child.consent.%'
             OR NEW.action LIKE 'organization.consent.%' THEN
            RETURN NEW;
          END IF;
            """
        op.execute(
            rf"""
            CREATE OR REPLACE FUNCTION public.realtime_from_audit_event()
            RETURNS trigger
            LANGUAGE plpgsql
            SET search_path = pg_catalog, public
            AS $bridge$
            BEGIN
              {suppression}
              INSERT INTO public.realtime_events
                (id, organization_id, event_type, entity_type, entity_id,
                 occurred_at, payload)
              VALUES
                (NEW.id, NEW.organization_id, NEW.action, NEW.entity_type,
                 NEW.entity_id, NEW.occurred_at,
                 pg_catalog.jsonb_build_object(
                   'source', 'audit_event', 'facility_id', NEW.facility_id
                 ));
              RETURN NEW;
            END
            $bridge$
            """
        )
        return

    op.execute("DROP TRIGGER IF EXISTS audit_events_realtime")
    when_clause = ""
    if suppress_confidential_authority:
        when_clause = """
        WHEN NEW.action NOT LIKE 'family.authority.%'
         AND NEW.action NOT LIKE 'child.release.%'
         AND NEW.action NOT LIKE 'child.consent.%'
         AND NEW.action NOT LIKE 'organization.consent.%'
        """
    op.execute(
        rf"""
        CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events
        {when_clause}
        BEGIN
          INSERT INTO realtime_events
            (id, organization_id, event_type, entity_type, entity_id,
             occurred_at, payload)
          VALUES
            (lower(hex(randomblob(16))), NEW.organization_id, NEW.action,
             NEW.entity_type, NEW.entity_id, NEW.occurred_at,
             json_object(
               'source', 'audit_event', 'facility_id', NEW.facility_id
             ));
        END
        """
    )


def _install_evidence_document_functions(*, include_delegation: bool) -> None:
    """Install the A1 vault functions with the exact active document vocabulary."""

    delegation_literal = ",'signed_release_delegation'" if include_delegation else ""
    op.execute(
        rf"""
        CREATE OR REPLACE FUNCTION public.caresync_family_evidence_object_link_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          link_is_current boolean := false;
          measured_reference text;
          measured_media_type text;
          measured_byte_size bigint;
          measured_sha256 character(64);
        BEGIN
          IF NEW.evidence_kind IN (
            'identity_document','custody_document','court_order',
            'signed_consent'{delegation_literal},'other_document'
          ) THEN
            IF NEW.evidence_object_id IS NULL THEN
              RAISE EXCEPTION 'document evidence requires one clean object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_object_link';
            END IF;

            SELECT true,object_value.storage_reference,object_value.media_type,
                   object_value.byte_size,object_value.content_sha256
              INTO link_is_current,measured_reference,measured_media_type,
                   measured_byte_size,measured_sha256
            FROM public.family_authority_evidence_objects AS object_value
            JOIN public.family_authority_evidence_object_assessments AS assessment
              ON assessment.organization_id=object_value.organization_id
             AND assessment.family_id=object_value.family_id
             AND assessment.evidence_object_id=object_value.id
             AND assessment.version_number=2
             AND assessment.decision='clean'
            WHERE object_value.organization_id=NEW.organization_id
              AND object_value.family_id=NEW.family_id
              AND object_value.id=NEW.evidence_object_id
              AND object_value.evidence_kind=NEW.evidence_kind
              AND object_value.status='clean';
            IF NOT COALESCE(link_is_current,false) THEN
              RAISE EXCEPTION 'document evidence object is not clean and current'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_object_link';
            END IF;

            IF TG_ARGV[0]='prepare' THEN
              IF NEW.storage_reference IS NULL OR NEW.media_type IS NULL
                 OR NEW.byte_size IS NULL OR NEW.content_sha256 IS NULL
                 OR NEW.storage_reference<>measured_reference
                 OR NEW.media_type<>measured_media_type
                 OR NEW.byte_size<>measured_byte_size
                 OR NEW.content_sha256<>measured_sha256 THEN
                RAISE EXCEPTION 'document evidence tuple is not the measured object tuple'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_authority_evidence_object_link';
              END IF;
              NEW.storage_reference:=NULL;
              NEW.media_type:=NULL;
              NEW.byte_size:=NULL;
              NEW.content_sha256:=NULL;
            ELSE
              NEW.storage_reference:=measured_reference;
              NEW.media_type:=measured_media_type;
              NEW.byte_size:=measured_byte_size;
              NEW.content_sha256:=measured_sha256;
            END IF;
          ELSIF NEW.evidence_object_id IS NOT NULL
                OR NEW.storage_reference IS NOT NULL
                OR NEW.media_type IS NOT NULL
                OR NEW.byte_size IS NOT NULL
                OR NEW.content_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'attestation and witness evidence cannot carry an object'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_object_link';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        rf"""
        CREATE OR REPLACE FUNCTION public.caresync_family_evidence_review_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          evidence_row public.family_authority_evidence%ROWTYPE;
          uploader_user_id uuid;
        BEGIN
          IF NEW.version_number<>2 OR NEW.decision<>'reviewed' THEN
            RETURN NEW;
          END IF;

          SELECT evidence.* INTO evidence_row
          FROM public.family_authority_evidence AS evidence
          WHERE evidence.organization_id=NEW.organization_id
            AND evidence.family_id=NEW.family_id
            AND evidence.id=NEW.evidence_id
          FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'reviewed evidence is missing'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_asset';
          END IF;

          IF evidence_row.recorded_by_user_id=NEW.actor_user_id THEN
            RAISE EXCEPTION 'evidence review requires a distinct maker and checker'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_maker_checker';
          END IF;

          IF evidence_row.evidence_kind IN (
            'identity_document','custody_document','court_order',
            'signed_consent'{delegation_literal},'other_document'
          ) THEN
            IF NEW.assessed_epistemic_status IS DISTINCT FROM 'document_observed'
               OR evidence_row.evidence_object_id IS NULL THEN
              RAISE EXCEPTION 'document evidence requires an observed clean object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_review_epistemic_kind';
            END IF;
            SELECT object_value.uploaded_by_user_id INTO uploader_user_id
            FROM public.family_authority_evidence_objects AS object_value
            JOIN public.family_authority_evidence_object_assessments AS assessment
              ON assessment.organization_id=object_value.organization_id
             AND assessment.family_id=object_value.family_id
             AND assessment.evidence_object_id=object_value.id
             AND assessment.version_number=2
             AND assessment.decision='clean'
            WHERE object_value.organization_id=evidence_row.organization_id
              AND object_value.family_id=evidence_row.family_id
              AND object_value.id=evidence_row.evidence_object_id
              AND object_value.evidence_kind=evidence_row.evidence_kind
              AND object_value.status='clean'
            FOR UPDATE OF object_value;
            IF uploader_user_id IS NULL THEN
              RAISE EXCEPTION 'document evidence object is not clean and current'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_review_object';
            ELSIF uploader_user_id=NEW.actor_user_id THEN
              RAISE EXCEPTION 'evidence uploader cannot approve their own object'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_authority_evidence_maker_checker';
            END IF;
          ELSIF NEW.assessed_epistemic_status IS DISTINCT FROM 'reported'
                OR evidence_row.evidence_object_id IS NOT NULL THEN
            RAISE EXCEPTION 'reported evidence cannot claim document observation'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_epistemic_kind';
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    for function_name in (
        "caresync_family_evidence_object_link_guard",
        "caresync_family_evidence_review_guard",
    ):
        op.execute(
            f"REVOKE ALL ON FUNCTION public.{function_name}() FROM PUBLIC"
        )


def _install_activation_guard() -> None:
    """Install the fail-closed semantic activation matrix."""

    op.execute(
        r"""
        CREATE FUNCTION public.caresync_family_authority_activation_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          command_receipt public.childcare_command_receipts%ROWTYPE;
          basis_kind text;
          basis_reviewer uuid;
          decision_kind text;
          decision_reviewer uuid;
          signer_kind text;
          signer_reviewer uuid;
          policy_requirement text;
        BEGIN
          SELECT receipt.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt
          WHERE receipt.organization_id=NEW.organization_id
            AND receipt.client_operation_id=NEW.created_operation_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'authority activation lacks its command receipt'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_activation_receipt';
          END IF;

          IF TG_TABLE_NAME='consent_policy_versions' THEN
            IF NEW.signer_authority_requirement='specific_reviewed_authority' THEN
              RAISE EXCEPTION 'specific reviewed consent authority is not activatable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_consent_policy_activatable_signer';
            END IF;
            IF NEW.content_text IS DISTINCT FROM pg_catalog.btrim(NEW.content_text)
               OR NEW.content_reference IS DISTINCT FROM
                    '/consent-policies/' || NEW.id::text
               OR NEW.content_sha256 IS DISTINCT FROM pg_catalog.encode(
                    pg_catalog.sha256(
                      pg_catalog.convert_to(NEW.content_text, 'UTF8')
                    ),
                    'hex'
                  ) THEN
              RAISE EXCEPTION 'consent policy content projection is not canonical'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_consent_policy_content_projection';
            END IF;
            RETURN NEW;
          END IF;

          IF TG_TABLE_NAME='child_consent_decisions' THEN
            PERFORM 1
            FROM public.family_authority_evidence AS evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id
              AND evidence.id IN (
                NEW.evidence_id, NEW.signer_authority_evidence_id
              )
            ORDER BY evidence.id
            FOR SHARE;

            SELECT evidence.evidence_kind,assessment.actor_user_id
              INTO decision_kind,decision_reviewer
            FROM public.family_authority_evidence AS evidence
            JOIN public.family_authority_evidence_assessments AS assessment
              ON assessment.organization_id=evidence.organization_id
             AND assessment.family_id=evidence.family_id
             AND assessment.evidence_id=evidence.id
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id
              AND evidence.id=NEW.evidence_id
              AND assessment.id=NEW.evidence_assessment_id
              AND assessment.version_number=2
              AND assessment.decision='reviewed'
              AND (evidence.expires_at IS NULL OR (
                evidence.expires_at>transaction_timestamp()
                AND NEW.effective_until<=evidence.expires_at
              ))
              AND NOT EXISTS (
                SELECT 1
                FROM public.family_authority_evidence_assessments AS terminal
                WHERE terminal.organization_id=assessment.organization_id
                  AND terminal.evidence_id=assessment.evidence_id
                  AND terminal.version_number=3
              );
            SELECT evidence.evidence_kind,assessment.actor_user_id
              INTO signer_kind,signer_reviewer
            FROM public.family_authority_evidence AS evidence
            JOIN public.family_authority_evidence_assessments AS assessment
              ON assessment.organization_id=evidence.organization_id
             AND assessment.family_id=evidence.family_id
             AND assessment.evidence_id=evidence.id
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id
              AND evidence.id=NEW.signer_authority_evidence_id
              AND assessment.id=NEW.signer_authority_evidence_assessment_id
              AND assessment.version_number=2
              AND assessment.decision='reviewed'
              AND (evidence.expires_at IS NULL OR (
                evidence.expires_at>transaction_timestamp()
                AND NEW.effective_until<=evidence.expires_at
              ))
              AND NOT EXISTS (
                SELECT 1
                FROM public.family_authority_evidence_assessments AS terminal
                WHERE terminal.organization_id=assessment.organization_id
                  AND terminal.evidence_id=assessment.evidence_id
                  AND terminal.version_number=3
              );
            IF decision_kind IS DISTINCT FROM 'signed_consent' THEN
              RAISE EXCEPTION 'consent decision requires reviewed signed consent'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_child_consent_decision_evidence_kind';
            END IF;
            IF command_receipt.actor_user_id IN (
              decision_reviewer, signer_reviewer
            ) THEN
              RAISE EXCEPTION 'authority activator must differ from evidence reviewers'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_family_authority_activation_maker_checker';
            END IF;
            IF NEW.signer_authority_basis='guardian_record' THEN
              IF signer_kind IS DISTINCT FROM 'guardian_attestation'
                 OR NOT EXISTS (
                   SELECT 1
                   FROM public.family_authority_people AS person
                   JOIN public.guardians AS guardian
                     ON guardian.organization_id=person.organization_id
                    AND guardian.family_id=person.family_id
                    AND guardian.id=person.source_guardian_id
                   WHERE person.organization_id=NEW.organization_id
                     AND person.family_id=NEW.family_id
                     AND person.id=NEW.signer_person_id
                     AND person.status='active'
                     AND person.current_person_version_id=NEW.signer_person_version_id
                     AND person.source_guardian_id IS NOT NULL
                     AND guardian.retired_at IS NULL
                 ) THEN
                RAISE EXCEPTION 'guardian consent authority requires live guardian provenance and attestation'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_child_consent_guardian_provenance';
              END IF;
            ELSIF NEW.signer_authority_basis='reviewed_custody_evidence' THEN
              IF signer_kind IS DISTINCT FROM 'custody_document' THEN
                RAISE EXCEPTION 'legal decision maker requires reviewed custody evidence'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_child_consent_signer_evidence_kind';
              END IF;
            ELSE
              RAISE EXCEPTION 'consent signer basis is not activatable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_child_consent_signer_basis_activatable';
            END IF;

            SELECT policy.signer_authority_requirement INTO policy_requirement
            FROM public.consent_policy_versions AS policy
            WHERE policy.organization_id=NEW.organization_id
              AND policy.purpose_code=NEW.purpose_code
              AND policy.id=NEW.policy_version_id;
            IF NOT (
              (policy_requirement='guardian_record'
                AND NEW.signer_authority_basis='guardian_record')
              OR (policy_requirement='legal_decision_maker'
                AND NEW.signer_authority_basis='reviewed_custody_evidence')
            ) THEN
              RAISE EXCEPTION 'consent signer basis does not exactly satisfy policy'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_child_consent_signer_authority';
            END IF;
            RETURN NEW;
          END IF;

          PERFORM 1
          FROM public.family_authority_evidence AS evidence
          WHERE evidence.organization_id=NEW.organization_id
            AND evidence.family_id=NEW.family_id
            AND evidence.id=NEW.basis_evidence_id
          FOR SHARE;
          SELECT evidence.evidence_kind,assessment.actor_user_id
            INTO basis_kind,basis_reviewer
          FROM public.family_authority_evidence AS evidence
          JOIN public.family_authority_evidence_assessments AS assessment
            ON assessment.organization_id=evidence.organization_id
           AND assessment.family_id=evidence.family_id
           AND assessment.evidence_id=evidence.id
          WHERE evidence.organization_id=NEW.organization_id
            AND evidence.family_id=NEW.family_id
            AND evidence.id=NEW.basis_evidence_id
            AND assessment.id=NEW.basis_evidence_assessment_id
            AND assessment.version_number=2
            AND assessment.decision='reviewed'
            AND (evidence.expires_at IS NULL OR (
              evidence.expires_at>transaction_timestamp()
              AND NEW.effective_until<=evidence.expires_at
            ))
            AND NOT EXISTS (
              SELECT 1 FROM public.family_authority_evidence_assessments AS terminal
              WHERE terminal.organization_id=assessment.organization_id
                AND terminal.evidence_id=assessment.evidence_id
                AND terminal.version_number=3
            );
          IF basis_kind IS NULL THEN
            RAISE EXCEPTION 'authority basis evidence is not current and reviewed'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_activation_evidence_current';
          ELSIF command_receipt.actor_user_id=basis_reviewer THEN
            RAISE EXCEPTION 'authority activator must differ from evidence reviewer'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_family_authority_activation_maker_checker';
          END IF;

          IF TG_TABLE_NAME='child_release_authorizations' THEN
            IF NEW.grantor_authority_basis='guardian_record' THEN
              IF basis_kind<>'guardian_attestation' OR NOT EXISTS (
                SELECT 1
                FROM public.family_authority_people AS person
                JOIN public.guardians AS guardian
                  ON guardian.organization_id=person.organization_id
                 AND guardian.family_id=person.family_id
                 AND guardian.id=person.source_guardian_id
                WHERE person.organization_id=NEW.organization_id
                  AND person.family_id=NEW.family_id
                  AND person.id=NEW.grantor_person_id
                  AND person.status='active'
                  AND person.current_person_version_id=NEW.grantor_person_version_id
                  AND person.source_guardian_id IS NOT NULL
                  AND guardian.retired_at IS NULL
              ) THEN
                RAISE EXCEPTION 'guardian release authority requires live guardian provenance and attestation'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_authorization_guardian_provenance';
              END IF;
            ELSIF NEW.grantor_authority_basis='reviewed_custody_evidence' THEN
              IF basis_kind<>'custody_document' THEN
                RAISE EXCEPTION 'custody release basis requires custody document'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_authorization_evidence_kind';
              END IF;
            ELSIF NEW.grantor_authority_basis='reviewed_delegation_evidence' THEN
              IF basis_kind<>'signed_release_delegation' OR NOT EXISTS (
                SELECT 1
                FROM public.family_authority_people AS person
                JOIN public.guardians AS guardian
                  ON guardian.organization_id=person.organization_id
                 AND guardian.family_id=person.family_id
                 AND guardian.id=person.source_guardian_id
                WHERE person.organization_id=NEW.organization_id
                  AND person.family_id=NEW.family_id
                  AND person.id=NEW.grantor_person_id
                  AND person.status='active'
                  AND person.current_person_version_id=NEW.grantor_person_version_id
                  AND person.source_guardian_id IS NOT NULL
                  AND guardian.retired_at IS NULL
              ) THEN
                RAISE EXCEPTION 'release delegation requires signed delegation and original guardian provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_authorization_delegation_provenance';
              END IF;
            ELSE
              RAISE EXCEPTION 'release authority basis is not activatable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_authorization_basis_activatable';
            END IF;
          ELSIF TG_TABLE_NAME='child_release_rules' THEN
            IF NEW.rule_kind NOT IN ('deny','manager_review') THEN
              RAISE EXCEPTION 'release rule kind is not activatable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_rule_kind_activatable';
            END IF;
            IF NEW.authority_basis_code='guardian_record' THEN
              IF basis_kind<>'guardian_attestation'
                 OR NEW.directing_person_id IS NULL OR NOT EXISTS (
                   SELECT 1
                   FROM public.family_authority_people AS person
                   JOIN public.guardians AS guardian
                     ON guardian.organization_id=person.organization_id
                    AND guardian.family_id=person.family_id
                    AND guardian.id=person.source_guardian_id
                   WHERE person.organization_id=NEW.organization_id
                     AND person.family_id=NEW.family_id
                     AND person.id=NEW.directing_person_id
                     AND person.status='active'
                     AND person.current_person_version_id=NEW.directing_person_version_id
                     AND person.source_guardian_id IS NOT NULL
                     AND guardian.retired_at IS NULL
                 ) THEN
                RAISE EXCEPTION 'guardian release rule requires live directing guardian provenance'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_rule_guardian_provenance';
              END IF;
            ELSIF NEW.authority_basis_code='reviewed_custody_evidence' THEN
              IF basis_kind<>'custody_document' THEN
                RAISE EXCEPTION 'custody release rule requires custody document'
                  USING ERRCODE='23514',
                        CONSTRAINT='ck_release_rule_evidence_kind';
              END IF;
            ELSE
              RAISE EXCEPTION 'release rule authority basis is not activatable'
                USING ERRCODE='23514',
                      CONSTRAINT='ck_release_rule_basis_activatable';
            END IF;
          END IF;
          RETURN NEW;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_activation_guard() FROM PUBLIC"
    )
    for table_name in ACTIVATION_TABLES:
        op.execute(
            f'CREATE TRIGGER "trg_{table_name}_activation_guard" '
            f'BEFORE INSERT ON public."{table_name}" FOR EACH ROW '
            "EXECUTE FUNCTION public.caresync_family_authority_activation_guard()"
        )


def _install_evidence_invalidation_invariant(*, include_signer_authority: bool) -> None:
    """Keep terminal evidence changes coupled to every dependent child head."""

    signer_union = ""
    if include_signer_authority:
        signer_union = r"""
            UNION
            SELECT signer_decision.child_id
            FROM public.child_consent_decisions AS signer_decision
            WHERE signer_decision.organization_id=NEW.organization_id
              AND signer_decision.family_id=NEW.family_id
              AND signer_decision.signer_authority_evidence_id=NEW.evidence_id
              AND signer_decision.signer_authority_evidence_assessment_id=
                  reviewed_assessment_id
              AND signer_decision.withdrawn_at IS NULL
              AND signer_decision.effective_until>transaction_timestamp()
        """
    op.execute(
        rf"""
        CREATE OR REPLACE FUNCTION public.caresync_family_authority_evidence_invariant()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $guard$
        DECLARE
          command_receipt public.childcare_command_receipts%ROWTYPE;
          reviewed_assessment_id uuid;
          uncovered_children integer;
        BEGIN
          SELECT receipt.* INTO command_receipt
          FROM public.childcare_command_receipts AS receipt
          WHERE receipt.organization_id=NEW.organization_id
            AND receipt.client_operation_id=NEW.created_operation_id;
          IF NOT FOUND OR command_receipt.target_type<>'authority_evidence'
             OR command_receipt.target_id<>NEW.evidence_id
             OR command_receipt.actor_user_id<>NEW.actor_user_id
             OR command_receipt.committed_version<>NEW.version_number
             OR command_receipt.command_type IS DISTINCT FROM (CASE NEW.decision
               WHEN 'reviewed' THEN 'family.authority.evidence.review'
               WHEN 'rejected' THEN 'family.authority.evidence.reject'
               WHEN 'invalidated' THEN 'family.authority.evidence.invalidate'
               WHEN 'superseded' THEN 'family.authority.evidence.supersede'
             END) THEN
            RAISE EXCEPTION 'evidence assessment lacks its exact command receipt'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_assessment_receipt';
          END IF;

          IF NEW.decision='reviewed' AND EXISTS (
            SELECT 1 FROM public.family_authority_evidence evidence
            WHERE evidence.organization_id=NEW.organization_id
              AND evidence.family_id=NEW.family_id AND evidence.id=NEW.evidence_id
              AND evidence.expires_at IS NOT NULL
              AND evidence.expires_at<=clock_timestamp()
          ) THEN
            RAISE EXCEPTION 'evidence expired before review committed'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_review_unexpired';
          END IF;
          IF NEW.version_number<>3 THEN RETURN NULL; END IF;

          SELECT assessment.id INTO reviewed_assessment_id
          FROM public.family_authority_evidence_assessments AS assessment
          WHERE assessment.organization_id=NEW.organization_id
            AND assessment.evidence_id=NEW.evidence_id
            AND assessment.version_number=2 AND assessment.decision='reviewed';
          IF reviewed_assessment_id IS NULL THEN
            RAISE EXCEPTION 'terminal evidence decision lacks reviewed predecessor'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_assessment_sequence';
          END IF;

          IF NEW.decision='superseded' AND NOT EXISTS (
            SELECT 1
            FROM public.family_authority_evidence AS replacement
            JOIN public.family_authority_evidence_assessments AS review
              ON review.organization_id=replacement.organization_id
             AND review.family_id=replacement.family_id
             AND review.evidence_id=replacement.id
             AND review.version_number=2 AND review.decision='reviewed'
            WHERE replacement.organization_id=NEW.organization_id
              AND replacement.family_id=NEW.family_id
              AND replacement.id=NEW.superseded_by_evidence_id
              AND (replacement.expires_at IS NULL
                OR replacement.expires_at>clock_timestamp())
              AND NOT EXISTS (
                SELECT 1 FROM public.family_authority_evidence_assessments AS terminal
                WHERE terminal.organization_id=replacement.organization_id
                  AND terminal.evidence_id=replacement.id
                  AND terminal.version_number=3
              )
          ) THEN
            RAISE EXCEPTION 'replacement evidence changed before commit'
              USING ERRCODE='40001',
                    CONSTRAINT='ck_authority_evidence_superseding_current';
          END IF;

          WITH affected(child_id) AS (
            SELECT authorization_record.child_id
            FROM public.child_release_authorizations AS authorization_record
            WHERE authorization_record.organization_id=NEW.organization_id
              AND authorization_record.family_id=NEW.family_id
              AND authorization_record.basis_evidence_id=NEW.evidence_id
              AND authorization_record.basis_evidence_assessment_id=
                  reviewed_assessment_id
              AND authorization_record.revoked_at IS NULL
              AND authorization_record.effective_until>transaction_timestamp()
            UNION
            SELECT rule.child_id
            FROM public.child_release_rules AS rule
            WHERE rule.organization_id=NEW.organization_id
              AND rule.family_id=NEW.family_id
              AND rule.basis_evidence_id=NEW.evidence_id
              AND rule.basis_evidence_assessment_id=reviewed_assessment_id
              AND rule.revoked_at IS NULL
              AND rule.effective_until>transaction_timestamp()
            UNION
            SELECT decision.child_id
            FROM public.child_consent_decisions AS decision
            WHERE decision.organization_id=NEW.organization_id
              AND decision.family_id=NEW.family_id
              AND decision.evidence_id=NEW.evidence_id
              AND decision.evidence_assessment_id=reviewed_assessment_id
              AND decision.withdrawn_at IS NULL
              AND decision.effective_until>transaction_timestamp()
            {signer_union}
          )
          SELECT count(*) INTO uncovered_children
          FROM affected
          WHERE NOT EXISTS (
            SELECT 1 FROM public.child_authority_heads AS head
            WHERE head.organization_id=NEW.organization_id
              AND head.family_id=NEW.family_id
              AND head.child_id=affected.child_id
              AND head.last_operation_id=NEW.created_operation_id
              AND head.xmin=pg_current_xact_id()::text::xid
          );
          IF uncovered_children<>0 THEN
            RAISE EXCEPTION 'evidence terminal decision did not bump every dependent child'
              USING ERRCODE='23514',
                    CONSTRAINT='ck_authority_evidence_child_revisions';
          END IF;
          RETURN NULL;
        END
        $guard$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.caresync_family_authority_evidence_invariant() FROM PUBLIC"
    )


def _set_postgres_activation_grants(*, enabled: bool) -> None:
    """Give the shared runtime role only the activated command columns."""

    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app') THEN
            REVOKE INSERT, UPDATE, DELETE ON TABLE
              public.child_release_authorizations,
              public.child_release_rules,
              public.consent_policy_versions,
              public.child_consent_decisions
            FROM caresync_basic_app;
          END IF;
        END
        $grants$
        """
    )
    if not enabled:
        return
    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app') THEN
            GRANT INSERT ON TABLE
              public.child_release_authorizations,
              public.child_release_rules,
              public.consent_policy_versions,
              public.child_consent_decisions
            TO caresync_basic_app;
            GRANT UPDATE (
              version, revoked_at, revoked_operation_id,
              revocation_reason_code, updated_at
            ) ON TABLE public.child_release_authorizations TO caresync_basic_app;
            GRANT UPDATE (
              version, revoked_at, revoked_operation_id,
              revocation_reason_code, updated_at
            ) ON TABLE public.child_release_rules TO caresync_basic_app;
            GRANT UPDATE (
              version, withdrawn_at, withdrawn_operation_id,
              withdrawal_reason_code, updated_at
            ) ON TABLE public.child_consent_decisions TO caresync_basic_app;
          END IF;
        END
        $grants$
        """
    )


def _alter_static_checks(*, activate: bool) -> None:
    """Install A2's portable static allowlists or restore the A1 scaffold."""

    object_kinds = (
        "evidence_kind IN ('identity_document','custody_document','court_order',"
        "'signed_consent','signed_release_delegation','other_document')"
        if activate
        else "evidence_kind IN ('identity_document','custody_document','court_order',"
        "'signed_consent','other_document')"
    )
    evidence_kinds = (
        "evidence_kind IN ('identity_document','custody_document','court_order',"
        "'guardian_attestation','signed_consent','signed_release_delegation',"
        "'staff_witness','other_document')"
        if activate
        else "evidence_kind IN ('identity_document','custody_document','court_order',"
        "'guardian_attestation','signed_consent','staff_witness','other_document')"
    )
    authorization_basis = (
        "grantor_authority_basis IN ('guardian_record','reviewed_custody_evidence',"
        "'reviewed_delegation_evidence')"
        if activate
        else "grantor_authority_basis IN ('guardian_record','reviewed_custody_evidence',"
        "'reviewed_delegation_evidence','other_reviewed_authority')"
    )
    rule_kinds = (
        "rule_kind IN ('deny','manager_review')"
        if activate
        else "rule_kind IN ('deny','supervised_only','named_recipient_only','manager_review')"
    )
    rule_basis = (
        "authority_basis_code IN ('guardian_record','reviewed_custody_evidence')"
        if activate
        else "authority_basis_code IN ('guardian_record','reviewed_custody_evidence',"
        "'reviewed_delegation_evidence','other_reviewed_authority')"
    )
    policy_signer = (
        "signer_authority_requirement IN ('guardian_record','legal_decision_maker')"
        if activate
        else "signer_authority_requirement IN ('guardian_record','legal_decision_maker',"
        "'specific_reviewed_authority')"
    )
    consent_basis = (
        "signer_authority_basis IN ('guardian_record','reviewed_custody_evidence')"
        if activate
        else "signer_authority_basis IN ('guardian_record','reviewed_custody_evidence',"
        "'reviewed_delegation_evidence','other_reviewed_authority')"
    )

    changes = (
        (
            "family_authority_evidence_objects",
            "ck_authority_evidence_objects_kind",
            object_kinds,
        ),
        ("family_authority_evidence", "ck_authority_evidence_kind", evidence_kinds),
        (
            "child_release_authorizations",
            "ck_release_authorizations_grantor_basis",
            authorization_basis,
        ),
        ("child_release_rules", "ck_release_rules_kind", rule_kinds),
        ("child_release_rules", "ck_release_rules_authority_basis", rule_basis),
        (
            "consent_policy_versions",
            "ck_consent_policy_versions_signer",
            policy_signer,
        ),
        (
            "child_consent_decisions",
            "ck_child_consent_decisions_signer_basis",
            consent_basis,
        ),
    )
    for table_name, constraint_name, expression in changes:
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(constraint_name, type_="check")
            batch.create_check_constraint(constraint_name, expression)


def upgrade() -> None:
    _preflight_empty_activation_history(downgrade=False)
    _alter_static_checks(activate=True)
    with op.batch_alter_table("consent_policy_versions") as batch:
        batch.drop_constraint("ck_consent_policy_versions_content", type_="check")
        batch.add_column(sa.Column("content_text", sa.Text(), nullable=False))
        batch.create_check_constraint(
            "ck_consent_policy_versions_content",
            "length(trim(title)) > 0 AND length(trim(content_reference)) > 0 "
            "AND length(content_text) BETWEEN 1 AND 20000 "
            "AND length(trim(content_text)) > 0",
        )
    with op.batch_alter_table("child_consent_decisions") as batch:
        batch.add_column(
            sa.Column("signer_authority_evidence_id", sa.Uuid(), nullable=False)
        )
        batch.add_column(
            sa.Column(
                "signer_authority_evidence_assessment_id", sa.Uuid(), nullable=False
            )
        )
        batch.create_foreign_key(
            "fk_child_consent_decisions_signer_authority_evidence",
            "family_authority_evidence",
            ["organization_id", "family_id", "signer_authority_evidence_id"],
            ["organization_id", "family_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_child_consent_decisions_signer_authority_assessment",
            "family_authority_evidence_assessments",
            [
                "organization_id",
                "family_id",
                "signer_authority_evidence_id",
                "signer_authority_evidence_assessment_id",
            ],
            ["organization_id", "family_id", "evidence_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_child_consent_decisions_distinct_evidence",
            "evidence_id <> signer_authority_evidence_id",
        )

    if op.get_bind().dialect.name == "postgresql":
        _install_evidence_document_functions(include_delegation=True)
        _install_activation_guard()
        _install_evidence_invalidation_invariant(include_signer_authority=True)
        _set_postgres_activation_grants(enabled=True)
    _install_audit_realtime_bridge(suppress_confidential_authority=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        destination_revision = context.get_revision_argument()
        if destination_revision not in {down_revision, "-1"}:
            raise RuntimeError(
                "0029A2 SQLite downgrade refused before DDL: first downgrade "
                "exactly to 0029A1_family_evidence_vault, then start a separate "
                "downgrade command"
            )
    _preflight_empty_activation_history(downgrade=True)
    if bind.dialect.name == "postgresql":
        _set_postgres_activation_grants(enabled=False)
        for table_name in reversed(ACTIVATION_TABLES):
            op.execute(
                f'DROP TRIGGER "trg_{table_name}_activation_guard" '
                f'ON public."{table_name}"'
            )
        op.execute("DROP FUNCTION public.caresync_family_authority_activation_guard()")
        _install_evidence_invalidation_invariant(include_signer_authority=False)
        _install_evidence_document_functions(include_delegation=False)

    with op.batch_alter_table("child_consent_decisions") as batch:
        batch.drop_constraint(
            "ck_child_consent_decisions_distinct_evidence", type_="check"
        )
        batch.drop_constraint(
            "fk_child_consent_decisions_signer_authority_assessment",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_child_consent_decisions_signer_authority_evidence",
            type_="foreignkey",
        )
        batch.drop_column("signer_authority_evidence_assessment_id")
        batch.drop_column("signer_authority_evidence_id")
    with op.batch_alter_table("consent_policy_versions") as batch:
        batch.drop_constraint("ck_consent_policy_versions_content", type_="check")
        batch.drop_column("content_text")
        batch.create_check_constraint(
            "ck_consent_policy_versions_content",
            "length(trim(title)) > 0 AND length(trim(content_reference)) > 0",
        )
    _alter_static_checks(activate=False)
    _install_audit_realtime_bridge(suppress_confidential_authority=False)

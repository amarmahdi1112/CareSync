\set ON_ERROR_STOP on

-- Run only after the database reaches the exact revision approved by the
-- current release plan (locally, `0043_org_wide_room_presence`). Never infer
-- that revision from the source-tree Alembic head. This script has two
-- deliberately distinct authority phases:
--   1. cluster-role provisioning/repair (SUPERUSER or CREATEROLE), and
--   2. database/schema grants (object owner or SUPERUSER).
-- A migration owner may run phase 2 only on pre-0032 schemas, after the cluster
-- administrator has already provisioned an exactly safe role. 0032 and later
-- include terminal repository-owner roles and therefore require SUPERUSER so
-- role repair and exact SECURITY DEFINER ownership remain atomic. Any missing
-- authority fails with a specific message instead of leaving a partially
-- trusted runtime identity.
-- Password provisioning remains external to source control.
SELECT pg_catalog.set_config('search_path', 'pg_catalog', false);

-- 0032 is an all-or-nothing command boundary.  Detect a partial migration
-- before provisioning cluster roles or changing any database ACL.  The deeper
-- policy, trigger, role, ownership, and privilege audit runs again after the
-- exact grants have been reconstructed below.
DO $transport_commands_shape_preflight$
DECLARE
    surface_present boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_catalog.unnest(ARRAY[
          'transport_registry_command_receipts',
          'staff_driver_qualification_evidence_objects',
          'staff_driver_qualification_review_decisions',
          'transport_vehicle_evidence_review_decisions',
          'transport_vehicle_evidence_scan_facts'
        ]::text[]) AS expected(name)
        WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.unnest(ARRAY[
          'caresync_0032_immutable_fact()',
          'caresync_0032_receipt_guard()',
          'caresync_0032_qualification_evidence_guard()',
          'caresync_0032_qualification_review_guard()',
          'caresync_0032_vehicle_review_guard()',
          'caresync_0032_vehicle_scan_guard()',
          'caresync_0032_execute_command(text,uuid,text,jsonb)'
        ]::text[]) AS expected(signature)
        WHERE pg_catalog.to_regprocedure('public.' || expected.signature) IS NOT NULL
    ) INTO surface_present;

    IF surface_present AND (
         5 <> (
           SELECT count(*)
           FROM pg_catalog.unnest(ARRAY[
             'transport_registry_command_receipts',
             'staff_driver_qualification_evidence_objects',
             'staff_driver_qualification_review_decisions',
             'transport_vehicle_evidence_review_decisions',
             'transport_vehicle_evidence_scan_facts'
           ]::text[]) AS expected(name)
           WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
         )
         OR 7 <> (
           SELECT count(*)
           FROM pg_catalog.unnest(ARRAY[
             'caresync_0032_immutable_fact()',
             'caresync_0032_receipt_guard()',
             'caresync_0032_qualification_evidence_guard()',
             'caresync_0032_qualification_review_guard()',
             'caresync_0032_vehicle_review_guard()',
             'caresync_0032_vehicle_scan_guard()',
             'caresync_0032_execute_command(text,uuid,text,jsonb)'
           ]::text[]) AS expected(signature)
           WHERE pg_catalog.to_regprocedure('public.' || expected.signature) IS NOT NULL
         )
         OR 10 <> (
           SELECT count(*)
           FROM pg_catalog.pg_trigger AS trigger
           JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
           JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
           WHERE namespace.nspname='public' AND NOT trigger.tgisinternal
             AND trigger.tgenabled<>'D' AND trigger.tgname IN (
               'transport_registry_command_receipts_immutable',
               'staff_driver_qualification_evidence_objects_immutable',
               'staff_driver_qualification_review_decisions_immutable',
               'transport_vehicle_evidence_review_decisions_immutable',
               'transport_vehicle_evidence_scan_facts_immutable',
               'transport_registry_receipt_insert_guard',
               'staff_driver_qualification_evidence_insert_guard',
               'staff_driver_qualification_review_insert_guard',
               'transport_vehicle_evidence_review_insert_guard',
               'transport_vehicle_evidence_scan_insert_guard'
             )
         )
         OR 14 <> (
           SELECT count(*)
           FROM pg_catalog.pg_class AS relation
           WHERE relation.oid IN (
             SELECT pg_catalog.to_regclass('public.' || expected.name)
             FROM pg_catalog.unnest(ARRAY[
               'staff_driver_capability_versions',
               'staff_driver_qualification_versions',
               'staff_driver_authorization_decisions',
               'staff_driver_readiness_decisions','transport_vehicles',
               'transport_vehicle_versions','transport_vehicle_evidence_versions',
               'transport_registry_command_receipts',
               'staff_driver_qualification_evidence_objects',
               'staff_driver_qualification_review_decisions',
               'transport_vehicle_evidence_review_decisions',
               'transport_vehicle_evidence_scan_facts',
               'audit_events','user_notifications'
             ]::text[]) AS expected(name)
           ) AND relation.relrowsecurity AND relation.relforcerowsecurity
         )
         OR 14 <> (
           SELECT count(*)
           FROM pg_catalog.pg_policy AS policy
           WHERE policy.polname=split_part(
                   policy.polrelid::pg_catalog.regclass::text,'.',2
                 ) || '_0032_writer'
             AND policy.polrelid IN (
               SELECT pg_catalog.to_regclass('public.' || expected.name)
               FROM pg_catalog.unnest(ARRAY[
                 'staff_driver_capability_versions',
                 'staff_driver_qualification_versions',
                 'staff_driver_authorization_decisions',
                 'staff_driver_readiness_decisions','transport_vehicles',
                 'transport_vehicle_versions','transport_vehicle_evidence_versions',
                 'transport_registry_command_receipts',
                 'staff_driver_qualification_evidence_objects',
                 'staff_driver_qualification_review_decisions',
                 'transport_vehicle_evidence_review_decisions',
                 'transport_vehicle_evidence_scan_facts',
                 'audit_events','user_notifications'
               ]::text[]) AS expected(name)
             )
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0032 transport command surface';
    END IF;
END
$transport_commands_shape_preflight$;

-- 0033 is an append-only billing command boundary.  Bootstrap is intentionally
-- revision-blind: runtime roles cannot read Alembic's private release marker.
-- Instead, either the complete catalog capability is present or no 0033
-- object may be present at all.  A partially applied/tampered boundary fails
-- before any role or ACL is changed.
DO $billing_ledger_shape_preflight$
DECLARE
    surface_present boolean;
BEGIN
    SELECT EXISTS (
      SELECT 1 FROM pg_catalog.unnest(ARRAY[
        'billing_sandbox_source_attestations','billing_command_preparations',
        'billing_command_terminals','billing_accounts',
        'billing_account_payer_versions','billing_rate_plans',
        'billing_rate_plan_versions','billing_agreements',
        'billing_agreement_versions','billing_invoices','billing_invoice_lines',
        'billing_payments','billing_allocations','billing_credits',
        'billing_journal_entries','billing_journal_lines','billing_reversals',
        'billing_command_receipts','billing_command_claims',
        'billing_0033_role_permission_backups'
      ]::text[]) AS expected(name)
      WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
    ) OR EXISTS (
      SELECT 1 FROM pg_catalog.unnest(ARRAY[
        'caresync_0033_immutable_fact()','caresync_0033_role_permission_guard()',
        'caresync_0033_source_attestation_guard()',
        'caresync_0033_attested_source_immutable()',
        'caresync_0033_actor_guard()','caresync_0033_version_guard()',
        'caresync_0033_invoice_line_guard()',
        'caresync_0033_allocation_guard()','caresync_0033_credit_guard()',
        'caresync_0033_journal_sequence_guard()',
        'caresync_0033_journal_validate()',
        'caresync_0033_effect_open_guard()',
        'caresync_0033_bundle_validate()','caresync_0033_receipt_guard()',
        'caresync_0033_claim_guard()','caresync_0033_terminal_claim()'
      ]::text[]) AS expected(signature)
      WHERE pg_catalog.to_regprocedure('public.' || expected.signature) IS NOT NULL
    ) INTO surface_present;

    IF NOT surface_present THEN
        RETURN;
    END IF;

    IF 20 <> (
         SELECT count(*) FROM pg_catalog.unnest(ARRAY[
           'billing_sandbox_source_attestations','billing_command_preparations',
           'billing_command_terminals','billing_accounts',
           'billing_account_payer_versions','billing_rate_plans',
           'billing_rate_plan_versions','billing_agreements',
           'billing_agreement_versions','billing_invoices','billing_invoice_lines',
           'billing_payments','billing_allocations','billing_credits',
           'billing_journal_entries','billing_journal_lines','billing_reversals',
           'billing_command_receipts','billing_command_claims',
           'billing_0033_role_permission_backups'
         ]::text[]) AS expected(name)
         WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
       )
       OR 16 <> (
         SELECT count(*) FROM pg_catalog.unnest(ARRAY[
           'caresync_0033_immutable_fact()','caresync_0033_role_permission_guard()',
           'caresync_0033_source_attestation_guard()',
           'caresync_0033_attested_source_immutable()',
           'caresync_0033_actor_guard()','caresync_0033_version_guard()',
           'caresync_0033_invoice_line_guard()',
           'caresync_0033_allocation_guard()','caresync_0033_credit_guard()',
           'caresync_0033_journal_sequence_guard()',
           'caresync_0033_journal_validate()',
           'caresync_0033_effect_open_guard()',
           'caresync_0033_bundle_validate()','caresync_0033_receipt_guard()',
           'caresync_0033_claim_guard()','caresync_0033_terminal_claim()'
         ]::text[]) AS expected(signature)
         WHERE pg_catalog.to_regprocedure('public.' || expected.signature) IS NOT NULL
       )
       OR 19 <> (
         SELECT count(*) FROM pg_catalog.pg_class AS relation
         WHERE relation.oid IN (
           SELECT pg_catalog.to_regclass('public.' || expected.name)
           FROM pg_catalog.unnest(ARRAY[
             'billing_sandbox_source_attestations','billing_command_preparations',
             'billing_command_terminals','billing_accounts',
             'billing_account_payer_versions','billing_rate_plans',
             'billing_rate_plan_versions','billing_agreements',
             'billing_agreement_versions','billing_invoices','billing_invoice_lines',
             'billing_payments','billing_allocations','billing_credits',
             'billing_journal_entries','billing_journal_lines','billing_reversals',
             'billing_command_receipts','billing_command_claims'
           ]::text[]) AS expected(name)
         ) AND relation.relrowsecurity AND relation.relforcerowsecurity
       )
       OR 36 <> (
         SELECT count(*) FROM pg_catalog.pg_policy AS policy
         WHERE policy.polrelid IN (
           SELECT pg_catalog.to_regclass('public.' || expected.name)
           FROM pg_catalog.unnest(ARRAY[
             'billing_sandbox_source_attestations','billing_command_preparations',
             'billing_command_terminals','billing_accounts',
             'billing_account_payer_versions','billing_rate_plans',
             'billing_rate_plan_versions','billing_agreements',
             'billing_agreement_versions','billing_invoices','billing_invoice_lines',
             'billing_payments','billing_allocations','billing_credits',
             'billing_journal_entries','billing_journal_lines','billing_reversals',
             'billing_command_receipts','billing_command_claims'
           ]::text[]) AS expected(name)
         )
       )
       OR 75 <> (
         SELECT count(*) FROM pg_catalog.pg_trigger AS trigger
         JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname='public' AND NOT trigger.tgisinternal
           AND trigger.tgenabled<>'D'
           AND (pg_catalog.left(relation.relname,8)='billing_'
                OR relation.relname='roles')
           AND relation.relname<>'billing_manual_activations'
       ) THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0033 billing ledger capability';
    END IF;
END
$billing_ledger_shape_preflight$;

-- 0036 is a separate private/manual boundary layered over the frozen 0033
-- sandbox.  It must either be wholly absent or retain its table, invoker view,
-- guard functions, policies, immutable activation triggers, and all thirteen
-- reviewed 0033 bundle-trigger rebindings.
DO $billing_manual_shape_preflight$
DECLARE
    surface_present boolean;
BEGIN
    SELECT pg_catalog.to_regclass('public.billing_manual_activations') IS NOT NULL
        OR pg_catalog.to_regclass(
             'public.billing_source_authorizations_0036'
           ) IS NOT NULL
        OR pg_catalog.to_regprocedure(
             'public.caresync_0036_bundle_validate()'
           ) IS NOT NULL
      INTO surface_present;
    IF NOT surface_present THEN
        RETURN;
    END IF;
    IF pg_catalog.to_regclass('public.billing_manual_activations') IS NULL
       OR pg_catalog.to_regclass(
            'public.billing_source_authorizations_0036'
          ) IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_0036_bundle_validate()'
          ) IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_0036_manual_activation_guard()'
          ) IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_0036_manual_activation_immutable()'
          ) IS NULL
       OR NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class relation
            WHERE relation.oid='public.billing_manual_activations'::regclass
              AND relation.relrowsecurity AND relation.relforcerowsecurity
          )
       OR 2 <> (
            SELECT count(*) FROM pg_catalog.pg_policy policy
            WHERE policy.polrelid='public.billing_manual_activations'::regclass
          )
       OR 2 <> (
            SELECT count(*) FROM pg_catalog.pg_trigger trigger
            WHERE trigger.tgrelid='public.billing_manual_activations'::regclass
              AND NOT trigger.tgisinternal AND trigger.tgenabled='O'
          )
       OR 13 <> (
            SELECT count(*) FROM pg_catalog.pg_trigger trigger
            JOIN pg_catalog.pg_proc procedure ON procedure.oid=trigger.tgfoid
            WHERE trigger.tgname LIKE '%\_0033\_bundle' ESCAPE '\'
              AND procedure.proname='caresync_0036_bundle_validate'
              AND NOT trigger.tgisinternal AND trigger.tgenabled='O'
          )
       OR NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class relation
            WHERE relation.oid=
              'public.billing_source_authorizations_0036'::regclass
              AND relation.relkind='v'
              AND 'security_invoker=true'=ANY(relation.reloptions)
          ) THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0036 manual billing boundary';
    END IF;
END
$billing_manual_shape_preflight$;

-- Freeze the semantic source and trigger topology before any role or grant
-- repair is attempted.  These are PostgreSQL 17 catalog identities from the
-- reviewed 0031/0032 migration head; formatting and identifier quoting are
-- the only normalization permitted.
DO $transport_commands_canonical_preflight$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
      WITH expected(signature,source_sha256,definition_sha256) AS (VALUES
        ('caresync_0032_execute_command(text,uuid,text,jsonb)',
         '37623fef02d09ffa3d447a723b08a91a75305c9c35f9773dfb4d1cd3ca865bfc',
         '7b2d38b6b710b44926e978a7c427970854bbad2b7418d24a1ddff9b7c428f912'),
        ('caresync_0032_immutable_fact()',
         'ded4efc3b93cde31ecfae1f7b973fb7aa6a6015635ebd027056d18eece43d58d',
         '79e4d1861bc8f0b0fe1f68b1887a266695e53bfe9a9d4e4c21b41047bcaa0017'),
        ('caresync_0032_receipt_guard()',
         'e4c9815101da4344caec4747d0a6a2c89705ec0305eda31dbcbe83a0683233b7',
         '54f21d98cd2dba952f7900171a4b0f062f2d0a4cb843ab7ff48ec9250f387959'),
        ('caresync_0032_qualification_evidence_guard()',
         'db6ff856bb6b5d9ecdbbf051ead18596d26c67390f8e4258ebae08553a0a896d',
         'ae496ca388e95048f7253b8d035b390f34716932f0a05bef573db7329dac3ccd'),
        ('caresync_0032_qualification_review_guard()',
         '8487caa806ee087de9fca8c79591a203b713aaeb9aa78653380a952bdd1942d7',
         'e5f73ece9fb01a45aaf90a827bddbf175e6954e1706af7c64d118be63e431600'),
        ('caresync_0032_vehicle_review_guard()',
         '18b11f2c1fd1328156c1893cd7455edd192b759f35b93c1615dab5a447c1d8d8',
         '68d1ebc5f00b001f6cf8e9293758df42783fa952c1605730514850b4e37237f8'),
        ('caresync_0032_vehicle_scan_guard()',
         'eb501eed98a5a1c0970dcfca3de5686d90e96e8196f57f97bedae09e64301445',
         'fa1c5eef6e0a7c7fef3bdb0a175a6d5b589d4df068130d987df395b89b7d6889'),
        ('caresync_0031_immutable_fact()',
         '9926a61f98a7976403f72317579d4a520694e2169ea41a12f0d8cfdb4f694894',
         '8bca3d642ac789c45276db119b5803cc7e89a1e2f60ac6359d5fc4a41fc051fd'),
        ('caresync_0031_capability_guard()',
         '5202b9d1d073ce77ac6598102137045044fa365fbc210460f47ecc6471e4b7da',
         'f5b58ac23c3873b780191ec2c550fefded433b3c18d3a8bec445d1637b467af6'),
        ('caresync_0031_qualification_guard()',
         '51b5d15aa29a0129ca16d9e428dce30c7b7dc4f016ef3c179da1f0dcf6ef360e',
         '010c72ac71c7af8182a0338101a8c09485f5f3732c25a642ef9b2bda47e8d0e4'),
        ('caresync_0031_authorization_guard()',
         'b79b3cc091fcff84017f4f6ef43d0c52a447ea689355767234577c364fdc9ae0',
         'dc1bcbfc51704de36901feb1f3fde7552acc27005bc763b133597712d5a1b745'),
        ('caresync_0031_vehicle_guard()',
         'f7f469f625dfc8da04573ad235d491e6fbbdf1de4d5e5a72246e0d4844c98b17',
         '30c665a45aec129510aa4e94d32aa74e4db3c71524e469896d7bec4349c3b5a5'),
        ('caresync_0031_vehicle_version_guard()',
         '862be173c22c86981bf46deeac2b3a9d3017d120aa1495ada39424e08e02f152',
         '77bd1a7da80965275a3320cbfa8cfac70cf5aa770c5d8ce44a6f7b9570628540'),
        ('caresync_0031_vehicle_evidence_guard()',
         '89b3977be4cc62a5ab1f2e0a8a7935bb583d40e3028956bd08a5f43a439a020d',
         'ec2f6cd75580c62051c989638a81e9dc43e0c07494f5a936f72cba210dabd27e'),
        ('caresync_0031_readiness_guard()',
         '7350e9e05051a4bb0aad827c6a4d99c4c8a8f6c8d11864d75a6f472444ffedc9',
         '4a5c66b4aa4778aa80482ed0eb5b03841ce4dc0683fc56837a303c3ada74731a')
      )
      SELECT 1 FROM expected
      LEFT JOIN pg_catalog.pg_proc AS procedure
        ON procedure.oid=pg_catalog.to_regprocedure('public.' || expected.signature)
      WHERE procedure.oid IS NULL
         OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
              pg_catalog.replace(pg_catalog.regexp_replace(
                pg_catalog.lower(procedure.prosrc),'[[:space:]]','','g'
              ),'"',''),'UTF8'
            )),'hex') IS DISTINCT FROM expected.source_sha256
         OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
              pg_catalog.replace(pg_catalog.regexp_replace(
                pg_catalog.lower(pg_catalog.pg_get_functiondef(procedure.oid)),
                '[[:space:]]','','g'
              ),'"',''),'UTF8'
            )),'hex') IS DISTINCT FROM expected.definition_sha256
    ) THEN
        RAISE EXCEPTION '0032 canonical repository function identity audit failed';
    END IF;

    IF 23<>(
      SELECT count(*) FROM pg_catalog.pg_trigger AS trigger
      JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
      JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname='public' AND NOT trigger.tgisinternal
        AND relation.relname IN (
          'staff_driver_capability_versions','staff_driver_qualification_versions',
          'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
          'transport_vehicles','transport_vehicle_versions',
          'transport_vehicle_evidence_versions','transport_registry_command_receipts',
          'staff_driver_qualification_evidence_objects',
          'staff_driver_qualification_review_decisions',
          'transport_vehicle_evidence_review_decisions',
          'transport_vehicle_evidence_scan_facts'
        )
    ) OR EXISTS (
      WITH expected(relname,tgname,proname,tgtype,event_sql) AS (VALUES
        ('staff_driver_capability_versions',
         'staff_driver_capability_insert_guard','caresync_0031_capability_guard',7,'insert'),
        ('staff_driver_capability_versions',
         'staff_driver_capability_versions_immutable','caresync_0031_immutable_fact',27,
         'deleteorupdate'),
        ('staff_driver_qualification_versions',
         'staff_driver_qualification_insert_guard','caresync_0031_qualification_guard',7,
         'insert'),
        ('staff_driver_qualification_versions',
         'staff_driver_qualification_versions_immutable','caresync_0031_immutable_fact',27,
         'deleteorupdate'),
        ('staff_driver_authorization_decisions',
         'staff_driver_authorization_insert_guard','caresync_0031_authorization_guard',7,
         'insert'),
        ('staff_driver_authorization_decisions',
         'staff_driver_authorization_decisions_immutable','caresync_0031_immutable_fact',27,
         'deleteorupdate'),
        ('staff_driver_readiness_decisions','staff_driver_readiness_insert_guard',
         'caresync_0031_readiness_guard',7,'insert'),
        ('staff_driver_readiness_decisions','staff_driver_readiness_decisions_immutable',
         'caresync_0031_immutable_fact',27,'deleteorupdate'),
        ('transport_vehicles','transport_vehicles_guard','caresync_0031_vehicle_guard',27,
         'deleteorupdate'),
        ('transport_vehicle_versions','transport_vehicle_versions_insert_guard',
         'caresync_0031_vehicle_version_guard',7,'insert'),
        ('transport_vehicle_versions','transport_vehicle_versions_immutable',
         'caresync_0031_immutable_fact',27,'deleteorupdate'),
        ('transport_vehicle_evidence_versions','transport_vehicle_evidence_insert_guard',
         'caresync_0031_vehicle_evidence_guard',7,'insert'),
        ('transport_vehicle_evidence_versions','transport_vehicle_evidence_versions_immutable',
         'caresync_0031_immutable_fact',27,'deleteorupdate'),
        ('transport_registry_command_receipts','transport_registry_receipt_insert_guard',
         'caresync_0032_receipt_guard',7,'insert'),
        ('transport_registry_command_receipts','transport_registry_command_receipts_immutable',
         'caresync_0032_immutable_fact',27,'deleteorupdate'),
        ('staff_driver_qualification_evidence_objects',
         'staff_driver_qualification_evidence_insert_guard',
         'caresync_0032_qualification_evidence_guard',7,'insert'),
        ('staff_driver_qualification_evidence_objects',
         'staff_driver_qualification_evidence_objects_immutable',
         'caresync_0032_immutable_fact',27,'deleteorupdate'),
        ('staff_driver_qualification_review_decisions',
         'staff_driver_qualification_review_insert_guard',
         'caresync_0032_qualification_review_guard',7,'insert'),
        ('staff_driver_qualification_review_decisions',
         'staff_driver_qualification_review_decisions_immutable',
         'caresync_0032_immutable_fact',27,'deleteorupdate'),
        ('transport_vehicle_evidence_review_decisions',
         'transport_vehicle_evidence_review_insert_guard',
         'caresync_0032_vehicle_review_guard',7,'insert'),
        ('transport_vehicle_evidence_review_decisions',
         'transport_vehicle_evidence_review_decisions_immutable',
         'caresync_0032_immutable_fact',27,'deleteorupdate'),
        ('transport_vehicle_evidence_scan_facts',
         'transport_vehicle_evidence_scan_insert_guard',
         'caresync_0032_vehicle_scan_guard',7,'insert'),
        ('transport_vehicle_evidence_scan_facts',
         'transport_vehicle_evidence_scan_facts_immutable',
         'caresync_0032_immutable_fact',27,'deleteorupdate')
      )
      SELECT 1 FROM expected
      LEFT JOIN pg_catalog.pg_trigger AS trigger
        ON trigger.tgrelid=pg_catalog.to_regclass('public.' || expected.relname)
       AND trigger.tgname=expected.tgname AND NOT trigger.tgisinternal
      LEFT JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid
      WHERE trigger.oid IS NULL OR trigger.tgenabled<>'O'
         OR trigger.tgtype<>expected.tgtype OR trigger.tgqual IS NOT NULL
         OR trigger.tgnargs<>0 OR procedure.proname IS DISTINCT FROM expected.proname
         OR procedure.pronamespace IS DISTINCT FROM pg_catalog.to_regnamespace('public')
         OR pg_catalog.replace(pg_catalog.regexp_replace(pg_catalog.lower(
              pg_catalog.pg_get_triggerdef(trigger.oid)
            ),'[[:space:]]','','g'),'"','') IS DISTINCT FROM
              'createtrigger' || expected.tgname || 'before' || expected.event_sql ||
              'onpublic.' || expected.relname || 'foreachrowexecutefunctionpublic.' ||
              expected.proname || '()'
    ) THEN
        RAISE EXCEPTION '0032 canonical protected trigger topology audit failed';
    END IF;
END
$transport_commands_canonical_preflight$;

-- 0041 is an additive, all-or-nothing safety boundary.  A pre-0041 database
-- takes the absent path without gaining any room-presence authority.  Once any
-- 0041 object is visible, however, the complete migration-owned catalog must
-- already be present before this bootstrap is allowed to provision roles or
-- repair ACLs.  The API repeats the same fail-closed attestation in
-- Database.has_live_room_presence_safety_board().
DO $live_room_presence_shape_preflight$
DECLARE
    surface_present boolean;
    relation_owner oid;
BEGIN
    SELECT EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'staff_room_presence_sessions',
        'staff_room_presence_events',
        'room_operational_exception_heads',
        'room_operational_exception_events'
      ]::text[]) AS expected(name)
      WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'caresync_0041_presence_row_guard()',
        'caresync_0041_event_immutable_guard()',
        'caresync_0041_presence_event_guard()',
        'caresync_0041_presence_bundle_guard()',
        'caresync_0041_exception_head_guard()',
        'caresync_0041_exception_event_guard()',
        'caresync_0041_exception_bundle_guard()'
      ]::text[]) AS expected(signature)
      WHERE pg_catalog.to_regprocedure(
              'public.' || expected.signature
            ) IS NOT NULL
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.pg_trigger AS trigger
      JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname='public'
        AND relation.relname IN (
          'staff_room_presence_sessions',
          'staff_room_presence_events',
          'room_operational_exception_heads',
          'room_operational_exception_events'
        )
        AND NOT trigger.tgisinternal
    ) INTO surface_present;

    IF NOT surface_present THEN
        RETURN;
    END IF;

    IF pg_catalog.to_regclass('public.alembic_version') IS NULL
       OR 1<>(
         SELECT count(*) FROM public.alembic_version
       )
       OR NOT EXISTS (
         SELECT 1 FROM public.alembic_version
         WHERE version_num IN (
           '0041_live_room_presence',
           '0042_billing_policy_recert',
           '0043_org_wide_room_presence'
         )
       ) THEN
        RAISE EXCEPTION
          '0041 room-presence objects require exact Alembic revision 0041_live_room_presence, 0042_billing_policy_recert, or 0043_org_wide_room_presence';
    END IF;

    IF 4<>(
      SELECT count(*)
      FROM pg_catalog.unnest(ARRAY[
        'staff_room_presence_sessions',
        'staff_room_presence_events',
        'room_operational_exception_heads',
        'room_operational_exception_events'
      ]::text[]) AS expected(name)
      WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
    ) OR 7<>(
      SELECT count(*)
      FROM pg_catalog.unnest(ARRAY[
        'caresync_0041_presence_row_guard()',
        'caresync_0041_event_immutable_guard()',
        'caresync_0041_presence_event_guard()',
        'caresync_0041_presence_bundle_guard()',
        'caresync_0041_exception_head_guard()',
        'caresync_0041_exception_event_guard()',
        'caresync_0041_exception_bundle_guard()'
      ]::text[]) AS expected(signature)
      WHERE pg_catalog.to_regprocedure(
              'public.' || expected.signature
            ) IS NOT NULL
    ) THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0041 room-presence table and function set';
    END IF;

    SELECT relation.relowner INTO STRICT relation_owner
    FROM pg_catalog.pg_class AS relation
    WHERE relation.oid=pg_catalog.to_regclass(
      'public.staff_room_presence_sessions'
    );
    IF 4<>(
      SELECT count(*)
      FROM pg_catalog.pg_class AS relation
      WHERE relation.oid IN (
        pg_catalog.to_regclass('public.staff_room_presence_sessions'),
        pg_catalog.to_regclass('public.staff_room_presence_events'),
        pg_catalog.to_regclass('public.room_operational_exception_heads'),
        pg_catalog.to_regclass('public.room_operational_exception_events')
      )
        AND relation.relkind='r'
        AND relation.relowner=relation_owner
        AND relation.relrowsecurity
        AND relation.relforcerowsecurity
    ) OR relation_owner=COALESCE(
      pg_catalog.to_regrole('caresync_basic_app'),
      0::oid
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence ownership or forced-RLS boundary is incomplete';
    END IF;

    IF 65<>(
      SELECT count(*)
      FROM pg_catalog.pg_attribute AS attribute
      WHERE attribute.attrelid IN (
        pg_catalog.to_regclass('public.staff_room_presence_sessions'),
        pg_catalog.to_regclass('public.staff_room_presence_events'),
        pg_catalog.to_regclass('public.room_operational_exception_heads'),
        pg_catalog.to_regclass('public.room_operational_exception_events')
      )
        AND attribute.attnum>0
        AND NOT attribute.attisdropped
    ) OR EXISTS (
      WITH expected(table_name,column_name) AS (VALUES
        ('staff_room_presence_sessions','id'),
        ('staff_room_presence_sessions','organization_id'),
        ('staff_room_presence_sessions','membership_id'),
        ('staff_room_presence_sessions','staff_shift_id'),
        ('staff_room_presence_sessions','facility_id'),
        ('staff_room_presence_sessions','room_id'),
        ('staff_room_presence_sessions','source'),
        ('staff_room_presence_sessions','started_at'),
        ('staff_room_presence_sessions','ended_at'),
        ('staff_room_presence_sessions','end_reason'),
        ('staff_room_presence_sessions','start_operation_id'),
        ('staff_room_presence_sessions','end_operation_id'),
        ('staff_room_presence_sessions','started_by_user_id'),
        ('staff_room_presence_sessions','ended_by_user_id'),
        ('staff_room_presence_sessions','version'),
        ('staff_room_presence_sessions','created_at'),
        ('staff_room_presence_sessions','updated_at'),
        ('staff_room_presence_events','id'),
        ('staff_room_presence_events','organization_id'),
        ('staff_room_presence_events','operation_id'),
        ('staff_room_presence_events','actor_user_id'),
        ('staff_room_presence_events','membership_id'),
        ('staff_room_presence_events','staff_shift_id'),
        ('staff_room_presence_events','facility_id'),
        ('staff_room_presence_events','event_type'),
        ('staff_room_presence_events','from_session_id'),
        ('staff_room_presence_events','to_session_id'),
        ('staff_room_presence_events','request_sha256'),
        ('staff_room_presence_events','intent'),
        ('staff_room_presence_events','result'),
        ('staff_room_presence_events','occurred_at'),
        ('staff_room_presence_events','created_at'),
        ('room_operational_exception_heads','id'),
        ('room_operational_exception_heads','organization_id'),
        ('room_operational_exception_heads','facility_id'),
        ('room_operational_exception_heads','scope_kind'),
        ('room_operational_exception_heads','scope_id'),
        ('room_operational_exception_heads','room_id'),
        ('room_operational_exception_heads','condition_code'),
        ('room_operational_exception_heads','state'),
        ('room_operational_exception_heads','current_fingerprint_sha256'),
        ('room_operational_exception_heads','current_evidence'),
        ('room_operational_exception_heads','opened_at'),
        ('room_operational_exception_heads','last_changed_at'),
        ('room_operational_exception_heads','acknowledged_at'),
        ('room_operational_exception_heads','acknowledged_by_user_id'),
        ('room_operational_exception_heads','acknowledgement_reason'),
        ('room_operational_exception_heads','resolved_at'),
        ('room_operational_exception_heads','version'),
        ('room_operational_exception_heads','created_at'),
        ('room_operational_exception_heads','updated_at'),
        ('room_operational_exception_events','id'),
        ('room_operational_exception_events','organization_id'),
        ('room_operational_exception_events','exception_id'),
        ('room_operational_exception_events','operation_id'),
        ('room_operational_exception_events','event_type'),
        ('room_operational_exception_events','actor_user_id'),
        ('room_operational_exception_events','cause_entity_type'),
        ('room_operational_exception_events','cause_entity_id'),
        ('room_operational_exception_events','previous_fingerprint_sha256'),
        ('room_operational_exception_events','current_fingerprint_sha256'),
        ('room_operational_exception_events','evidence'),
        ('room_operational_exception_events','reason'),
        ('room_operational_exception_events','occurred_at'),
        ('room_operational_exception_events','created_at')
      )
      SELECT 1 FROM expected
      WHERE NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute
        WHERE attribute.attrelid=pg_catalog.to_regclass(
                'public.' || expected.table_name
              )
          AND attribute.attname=expected.column_name
          AND attribute.attnum>0
          AND NOT attribute.attisdropped
      )
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence column catalog is not exact';
    END IF;

    IF EXISTS (
      WITH expected(
        table_name,column_name,udt_name,is_nullable,
        character_maximum_length,column_default
      ) AS (VALUES
        ('staff_room_presence_sessions','id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','organization_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','membership_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','staff_shift_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','facility_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','room_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','source','varchar',false,30,NULL),
        ('staff_room_presence_sessions','started_at','timestamptz',false,NULL,NULL),
        ('staff_room_presence_sessions','ended_at','timestamptz',true,NULL,NULL),
        ('staff_room_presence_sessions','end_reason','varchar',true,30,NULL),
        ('staff_room_presence_sessions','start_operation_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','end_operation_id','uuid',true,NULL,NULL),
        ('staff_room_presence_sessions','started_by_user_id','uuid',false,NULL,NULL),
        ('staff_room_presence_sessions','ended_by_user_id','uuid',true,NULL,NULL),
        ('staff_room_presence_sessions','version','int4',false,NULL,'1'),
        ('staff_room_presence_sessions','created_at','timestamptz',false,NULL,'now()'),
        ('staff_room_presence_sessions','updated_at','timestamptz',false,NULL,'now()'),
        ('staff_room_presence_events','id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','organization_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','operation_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','actor_user_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','membership_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','staff_shift_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','facility_id','uuid',false,NULL,NULL),
        ('staff_room_presence_events','event_type','varchar',false,40,NULL),
        ('staff_room_presence_events','from_session_id','uuid',true,NULL,NULL),
        ('staff_room_presence_events','to_session_id','uuid',true,NULL,NULL),
        ('staff_room_presence_events','request_sha256','bpchar',false,64,NULL),
        ('staff_room_presence_events','intent','json',false,NULL,NULL),
        ('staff_room_presence_events','result','json',false,NULL,NULL),
        ('staff_room_presence_events','occurred_at','timestamptz',false,NULL,NULL),
        ('staff_room_presence_events','created_at','timestamptz',false,NULL,'now()'),
        ('room_operational_exception_heads','id','uuid',false,NULL,NULL),
        ('room_operational_exception_heads','organization_id','uuid',false,NULL,NULL),
        ('room_operational_exception_heads','facility_id','uuid',false,NULL,NULL),
        ('room_operational_exception_heads','scope_kind','varchar',false,20,NULL),
        ('room_operational_exception_heads','scope_id','uuid',false,NULL,NULL),
        ('room_operational_exception_heads','room_id','uuid',true,NULL,NULL),
        ('room_operational_exception_heads','condition_code','varchar',false,100,NULL),
        ('room_operational_exception_heads','state','varchar',false,20,NULL),
        ('room_operational_exception_heads','current_fingerprint_sha256','bpchar',false,64,NULL),
        ('room_operational_exception_heads','current_evidence','json',false,NULL,NULL),
        ('room_operational_exception_heads','opened_at','timestamptz',false,NULL,NULL),
        ('room_operational_exception_heads','last_changed_at','timestamptz',false,NULL,NULL),
        ('room_operational_exception_heads','acknowledged_at','timestamptz',true,NULL,NULL),
        ('room_operational_exception_heads','acknowledged_by_user_id','uuid',true,NULL,NULL),
        ('room_operational_exception_heads','acknowledgement_reason','text',true,NULL,NULL),
        ('room_operational_exception_heads','resolved_at','timestamptz',true,NULL,NULL),
        ('room_operational_exception_heads','version','int4',false,NULL,'1'),
        ('room_operational_exception_heads','created_at','timestamptz',false,NULL,'now()'),
        ('room_operational_exception_heads','updated_at','timestamptz',false,NULL,'now()'),
        ('room_operational_exception_events','id','uuid',false,NULL,NULL),
        ('room_operational_exception_events','organization_id','uuid',false,NULL,NULL),
        ('room_operational_exception_events','exception_id','uuid',false,NULL,NULL),
        ('room_operational_exception_events','operation_id','uuid',false,NULL,NULL),
        ('room_operational_exception_events','event_type','varchar',false,30,NULL),
        ('room_operational_exception_events','actor_user_id','uuid',true,NULL,NULL),
        ('room_operational_exception_events','cause_entity_type','varchar',false,60,NULL),
        ('room_operational_exception_events','cause_entity_id','uuid',false,NULL,NULL),
        ('room_operational_exception_events','previous_fingerprint_sha256','bpchar',true,64,NULL),
        ('room_operational_exception_events','current_fingerprint_sha256','bpchar',false,64,NULL),
        ('room_operational_exception_events','evidence','json',false,NULL,NULL),
        ('room_operational_exception_events','reason','text',true,NULL,NULL),
        ('room_operational_exception_events','occurred_at','timestamptz',false,NULL,NULL),
        ('room_operational_exception_events','created_at','timestamptz',false,NULL,'now()')
      )
      SELECT 1
      FROM expected
      LEFT JOIN information_schema.columns AS actual
        ON actual.table_schema='public'
       AND actual.table_name=expected.table_name
       AND actual.column_name=expected.column_name
      WHERE actual.column_name IS NULL
         OR actual.udt_name<>expected.udt_name
         OR (actual.is_nullable='YES')<>expected.is_nullable
         OR actual.character_maximum_length
              IS DISTINCT FROM expected.character_maximum_length
         OR pg_catalog.regexp_replace(
              pg_catalog.lower(actual.column_default),
              '[[:space:]]','','g'
            ) IS DISTINCT FROM expected.column_default
         OR actual.is_identity<>'NO'
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence column types, nullability or defaults drifted';
    END IF;

    IF 42<>(
      SELECT count(*)
      FROM pg_catalog.pg_constraint AS constraint_row
      WHERE constraint_row.conrelid IN (
        pg_catalog.to_regclass('public.staff_room_presence_sessions'),
        pg_catalog.to_regclass('public.staff_room_presence_events'),
        pg_catalog.to_regclass('public.room_operational_exception_heads'),
        pg_catalog.to_regclass('public.room_operational_exception_events')
      )
        AND constraint_row.contype IN ('c','f','u')
    ) OR EXISTS (
      WITH expected(table_name,constraint_name) AS (VALUES
        ('staff_room_presence_sessions','fk_room_presence_sessions_membership'),
        ('staff_room_presence_sessions','fk_room_presence_sessions_shift'),
        ('staff_room_presence_sessions','fk_room_presence_sessions_facility'),
        ('staff_room_presence_sessions','fk_room_presence_sessions_room'),
        ('staff_room_presence_sessions','fk_room_presence_sessions_started_by'),
        ('staff_room_presence_sessions','fk_room_presence_sessions_ended_by'),
        ('staff_room_presence_sessions','uq_room_presence_sessions_org_id'),
        ('staff_room_presence_sessions','ck_room_presence_sessions_source'),
        ('staff_room_presence_sessions','ck_room_presence_sessions_end_reason'),
        ('staff_room_presence_sessions','ck_room_presence_sessions_terminal_bundle'),
        ('staff_room_presence_sessions','ck_room_presence_sessions_time_order'),
        ('staff_room_presence_sessions','ck_room_presence_sessions_version'),
        ('staff_room_presence_events','fk_room_presence_events_membership'),
        ('staff_room_presence_events','fk_room_presence_events_shift'),
        ('staff_room_presence_events','fk_room_presence_events_facility'),
        ('staff_room_presence_events','fk_room_presence_events_from_session'),
        ('staff_room_presence_events','fk_room_presence_events_to_session'),
        ('staff_room_presence_events','fk_room_presence_events_actor'),
        ('staff_room_presence_events','uq_room_presence_events_org_id'),
        ('staff_room_presence_events','uq_room_presence_events_operation'),
        ('staff_room_presence_events','ck_room_presence_events_type'),
        ('staff_room_presence_events','ck_room_presence_events_transition'),
        ('staff_room_presence_events','ck_room_presence_events_request_sha256'),
        ('room_operational_exception_heads','fk_room_operational_exceptions_facility'),
        ('room_operational_exception_heads','fk_room_operational_exceptions_room'),
        ('room_operational_exception_heads','fk_room_operational_exceptions_acknowledged_by'),
        ('room_operational_exception_heads','uq_room_operational_exceptions_org_id'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_scope'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_scope_identity'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_condition'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_state'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_fingerprint'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_state_bundle'),
        ('room_operational_exception_heads','ck_room_operational_exceptions_version'),
        ('room_operational_exception_events','fk_room_operational_exception_events_head'),
        ('room_operational_exception_events','fk_room_operational_exception_events_actor'),
        ('room_operational_exception_events','uq_room_operational_exception_events_org_id'),
        ('room_operational_exception_events','uq_room_operational_exception_events_operation'),
        ('room_operational_exception_events','ck_room_operational_exception_events_type'),
        ('room_operational_exception_events','ck_room_operational_exception_events_acknowledgement'),
        ('room_operational_exception_events','ck_room_operational_exception_events_current_fingerprint'),
        ('room_operational_exception_events','ck_room_operational_exception_events_previous_fingerprint')
      )
      SELECT 1 FROM expected
      LEFT JOIN pg_catalog.pg_constraint AS constraint_row
        ON constraint_row.conrelid=pg_catalog.to_regclass(
             'public.' || expected.table_name
           )
       AND constraint_row.conname=expected.constraint_name
      WHERE constraint_row.oid IS NULL
         OR NOT constraint_row.convalidated
         OR constraint_row.condeferrable
         OR constraint_row.condeferred
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence constraint catalog is not exact';
    END IF;

    IF 17<>(
      SELECT count(*)
      FROM (VALUES
        ('staff_room_presence_sessions','fk_room_presence_sessions_membership',
         ARRAY['organization_id','membership_id']::text[],
         'organization_memberships',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_sessions','fk_room_presence_sessions_shift',
         ARRAY['organization_id','staff_shift_id']::text[],
         'staff_shifts',ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_sessions','fk_room_presence_sessions_facility',
         ARRAY['organization_id','facility_id']::text[],
         'facilities',ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_sessions','fk_room_presence_sessions_room',
         ARRAY['organization_id','facility_id','room_id']::text[],
         'rooms',ARRAY['organization_id','facility_id','id']::text[]),
        ('staff_room_presence_sessions','fk_room_presence_sessions_started_by',
         ARRAY['started_by_user_id']::text[],
         'users',ARRAY['id']::text[]),
        ('staff_room_presence_sessions','fk_room_presence_sessions_ended_by',
         ARRAY['ended_by_user_id']::text[],
         'users',ARRAY['id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_membership',
         ARRAY['organization_id','membership_id']::text[],
         'organization_memberships',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_shift',
         ARRAY['organization_id','staff_shift_id']::text[],
         'staff_shifts',ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_facility',
         ARRAY['organization_id','facility_id']::text[],
         'facilities',ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_from_session',
         ARRAY['organization_id','from_session_id']::text[],
         'staff_room_presence_sessions',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_to_session',
         ARRAY['organization_id','to_session_id']::text[],
         'staff_room_presence_sessions',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','fk_room_presence_events_actor',
         ARRAY['actor_user_id']::text[],
         'users',ARRAY['id']::text[]),
        ('room_operational_exception_heads',
         'fk_room_operational_exceptions_facility',
         ARRAY['organization_id','facility_id']::text[],
         'facilities',ARRAY['organization_id','id']::text[]),
        ('room_operational_exception_heads',
         'fk_room_operational_exceptions_room',
         ARRAY['organization_id','facility_id','room_id']::text[],
         'rooms',ARRAY['organization_id','facility_id','id']::text[]),
        ('room_operational_exception_heads',
         'fk_room_operational_exceptions_acknowledged_by',
         ARRAY['acknowledged_by_user_id']::text[],
         'users',ARRAY['id']::text[]),
        ('room_operational_exception_events',
         'fk_room_operational_exception_events_head',
         ARRAY['organization_id','exception_id']::text[],
         'room_operational_exception_heads',
         ARRAY['organization_id','id']::text[]),
        ('room_operational_exception_events',
         'fk_room_operational_exception_events_actor',
         ARRAY['actor_user_id']::text[],
         'users',ARRAY['id']::text[])
      ) AS expected(
        source_table,constraint_name,source_columns,
        target_table,target_columns
      )
      JOIN pg_catalog.pg_constraint AS constraint_row
        ON constraint_row.conrelid=pg_catalog.to_regclass(
             'public.' || expected.source_table
           )
       AND constraint_row.conname=expected.constraint_name
       AND constraint_row.contype='f'
      JOIN pg_catalog.pg_class AS target_relation
        ON target_relation.oid=constraint_row.confrelid
       AND target_relation.relname=expected.target_table
       AND target_relation.relnamespace=pg_catalog.to_regnamespace('public')
      WHERE constraint_row.confdeltype='r'
        AND constraint_row.confupdtype='a'
        AND constraint_row.confmatchtype='s'
        AND ARRAY(
          SELECT source_attribute.attname::text
          FROM pg_catalog.unnest(constraint_row.conkey) WITH ORDINALITY
               AS source_key(attnum,position)
          JOIN pg_catalog.pg_attribute AS source_attribute
            ON source_attribute.attrelid=constraint_row.conrelid
           AND source_attribute.attnum=source_key.attnum
          ORDER BY source_key.position
        )=expected.source_columns
        AND ARRAY(
          SELECT target_attribute.attname::text
          FROM pg_catalog.unnest(constraint_row.confkey) WITH ORDINALITY
               AS target_key(attnum,position)
          JOIN pg_catalog.pg_attribute AS target_attribute
            ON target_attribute.attrelid=constraint_row.confrelid
           AND target_attribute.attnum=target_key.attnum
          ORDER BY target_key.position
        )=expected.target_columns
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence foreign-key bindings are not exact';
    END IF;

    IF 6<>(
      SELECT count(*)
      FROM (VALUES
        ('staff_room_presence_sessions','uq_room_presence_sessions_org_id',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','uq_room_presence_events_org_id',
         ARRAY['organization_id','id']::text[]),
        ('staff_room_presence_events','uq_room_presence_events_operation',
         ARRAY['organization_id','operation_id']::text[]),
        ('room_operational_exception_heads',
         'uq_room_operational_exceptions_org_id',
         ARRAY['organization_id','id']::text[]),
        ('room_operational_exception_events',
         'uq_room_operational_exception_events_org_id',
         ARRAY['organization_id','id']::text[]),
        ('room_operational_exception_events',
         'uq_room_operational_exception_events_operation',
         ARRAY['organization_id','operation_id']::text[])
      ) AS expected(table_name,constraint_name,column_names)
      JOIN pg_catalog.pg_constraint AS constraint_row
        ON constraint_row.conrelid=pg_catalog.to_regclass(
             'public.' || expected.table_name
           )
       AND constraint_row.conname=expected.constraint_name
       AND constraint_row.contype='u'
      WHERE ARRAY(
        SELECT attribute.attname::text
        FROM pg_catalog.unnest(constraint_row.conkey) WITH ORDINALITY
             AS key(attnum,position)
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid=constraint_row.conrelid
         AND attribute.attnum=key.attnum
        ORDER BY key.position
      )=expected.column_names
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence unique bindings are not exact';
    END IF;

    IF 19<>(
      SELECT count(*)
      FROM (VALUES
        ('room_operational_exception_events',
         'ck_room_operational_exception_events_acknowledgement',
         'a100609641796051d1a4db51522b78e4'),
        ('room_operational_exception_events',
         'ck_room_operational_exception_events_current_fingerprint',
         '3bdfe15d071912e8f875fca461f3c878'),
        ('room_operational_exception_events',
         'ck_room_operational_exception_events_previous_fingerprint',
         '11497e0a4515a28b186367f7885e6df4'),
        ('room_operational_exception_events',
         'ck_room_operational_exception_events_type',
         'd8cdefe5e40780c63658793e89473c6e'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_condition',
         '2242d81cb6211635b9e941f6eddbbef1'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_fingerprint',
         '3bdfe15d071912e8f875fca461f3c878'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_scope',
         '7a0d7a2097ca576a58a1ff5f4d11e0ce'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_scope_identity',
         '98a3d31be72918a393ce4fd93bc51714'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_state',
         'de2ac58c8db724e8d6c72ee0be642523'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_state_bundle',
         '1bbf99dba03b2cfc823490356e5c7a5d'),
        ('room_operational_exception_heads',
         'ck_room_operational_exceptions_version',
         '6627dd1a0965bddd3b469415dace01fe'),
        ('staff_room_presence_events',
         'ck_room_presence_events_request_sha256',
         'd55e1acd4e40cc35d5558d4665faf8c3'),
        ('staff_room_presence_events',
         'ck_room_presence_events_transition',
         '3739e4799562189e7817bd272c4d300b'),
        ('staff_room_presence_events',
         'ck_room_presence_events_type',
         'd2f3b9a676575471c7b6767b16d3a4ea'),
        ('staff_room_presence_sessions',
         'ck_room_presence_sessions_end_reason',
         '588b10c08b4ee4324760e483697ac6b6'),
        ('staff_room_presence_sessions',
         'ck_room_presence_sessions_source',
         '11a3be47b800b91a064c85a2992f4d2b'),
        ('staff_room_presence_sessions',
         'ck_room_presence_sessions_terminal_bundle',
         '24daa6c80a1eecad7c3740a59db821a5'),
        ('staff_room_presence_sessions',
         'ck_room_presence_sessions_time_order',
         'a4ac751ec7a0d40a0621a5f69435ff4b'),
        ('staff_room_presence_sessions',
         'ck_room_presence_sessions_version',
         '09dfe3415e59070ff342049fbf629214')
      ) AS expected(table_name,constraint_name,expression_md5)
      JOIN pg_catalog.pg_constraint AS constraint_row
        ON constraint_row.conrelid=pg_catalog.to_regclass(
             'public.' || expected.table_name
           )
       AND constraint_row.conname=expected.constraint_name
       AND constraint_row.contype='c'
      WHERE pg_catalog.md5(
              pg_catalog.replace(
                pg_catalog.regexp_replace(
                  pg_catalog.lower(pg_catalog.pg_get_expr(
                    constraint_row.conbin,
                    constraint_row.conrelid,
                    true
                  )),
                  '[[:space:]]','','g'
                ),
                '"',''
              )
            )=expected.expression_md5
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence CHECK expressions are not exact';
    END IF;

    IF 7<>(
      SELECT count(*)
      FROM (VALUES
        ('uq_room_presence_sessions_open_membership',
         'staff_room_presence_sessions',
         ARRAY['organization_id','membership_id']::text[],true,
         'ended_atisnull'),
        ('uq_room_presence_sessions_open_shift',
         'staff_room_presence_sessions',
         ARRAY['organization_id','staff_shift_id']::text[],true,
         'ended_atisnull'),
        ('ix_room_presence_sessions_room_live',
         'staff_room_presence_sessions',
         ARRAY['organization_id','facility_id','room_id','ended_at']::text[],
         false,''),
        ('ix_room_presence_events_membership_time',
         'staff_room_presence_events',
         ARRAY['organization_id','membership_id','occurred_at']::text[],
         false,''),
        ('uq_room_operational_exceptions_unresolved',
         'room_operational_exception_heads',
         ARRAY['organization_id','scope_kind','scope_id','condition_code']::text[],
         true,$predicate$state<>'resolved'$predicate$),
        ('ix_room_operational_exceptions_facility_state',
         'room_operational_exception_heads',
         ARRAY['organization_id','facility_id','state','last_changed_at']::text[],
         false,''),
        ('ix_room_operational_exception_events_timeline',
         'room_operational_exception_events',
         ARRAY['organization_id','exception_id','occurred_at']::text[],
         false,'')
      ) AS expected(
        index_name,table_name,column_names,is_unique,predicate
      )
      JOIN pg_catalog.pg_class AS index_relation
        ON index_relation.relname=expected.index_name
       AND index_relation.relnamespace=pg_catalog.to_regnamespace('public')
      JOIN pg_catalog.pg_index AS index_row
        ON index_row.indexrelid=index_relation.oid
      JOIN pg_catalog.pg_class AS table_relation
        ON table_relation.oid=index_row.indrelid
       AND table_relation.relname=expected.table_name
       AND table_relation.relnamespace=pg_catalog.to_regnamespace('public')
      JOIN pg_catalog.pg_am AS method ON method.oid=index_relation.relam
      WHERE index_row.indisunique=expected.is_unique
        AND index_row.indisvalid
        AND index_row.indisready
        AND index_row.indislive
        AND method.amname='btree'
        AND index_row.indnkeyatts=index_row.indnatts
        AND ARRAY(
          SELECT attribute.attname::text
          FROM pg_catalog.unnest(index_row.indkey) WITH ORDINALITY
               AS key(attnum,position)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid=index_row.indrelid
           AND attribute.attnum=key.attnum
          ORDER BY key.position
        )=expected.column_names
        AND pg_catalog.regexp_replace(
              pg_catalog.replace(pg_catalog.lower(COALESCE(
                pg_catalog.pg_get_expr(
                  index_row.indpred,index_row.indrelid,true
                ),
                ''
              )),'::text',''),
              '[[:space:]()]','','g'
            )=expected.predicate
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence index catalog is not exact';
    END IF;

    IF 4<>(
      SELECT count(*)
      FROM pg_catalog.pg_policy AS policy
      WHERE policy.polrelid IN (
        pg_catalog.to_regclass('public.staff_room_presence_sessions'),
        pg_catalog.to_regclass('public.staff_room_presence_events'),
        pg_catalog.to_regclass('public.room_operational_exception_heads'),
        pg_catalog.to_regclass('public.room_operational_exception_events')
      )
        AND policy.polname=(
          SELECT relation.relname || '_tenant'
          FROM pg_catalog.pg_class AS relation
          WHERE relation.oid=policy.polrelid
        )
        AND policy.polpermissive
        AND policy.polroles=ARRAY[0::oid]
        AND policy.polcmd='*'
        AND pg_catalog.replace(
              pg_catalog.regexp_replace(
                pg_catalog.regexp_replace(
                  pg_catalog.replace(
                    pg_catalog.replace(pg_catalog.lower(
                      pg_catalog.pg_get_expr(
                        policy.polqual,policy.polrelid,true
                      )
                    ),'pg_catalog.',''),
                    'public.',''
                  ),
                  '::(text|uuid|character varying|varchar)','','g'
                ),
                '[[:space:]()"]','','g'
              ),
              'fromorganization_membershipsasmembership',
              'fromorganization_membershipsmembership'
            )=$policy$organization_id=nullifcurrent_setting'app.current_organization_id',true,''andexistsselect1fromorganization_membershipsmembershipwheremembership.organization_id=nullifcurrent_setting'app.current_organization_id',true,''andmembership.user_id=nullifcurrent_setting'app.current_user_id',true,''andmembership.status='active'$policy$
        AND pg_catalog.replace(
              pg_catalog.regexp_replace(
                pg_catalog.regexp_replace(
                  pg_catalog.replace(
                    pg_catalog.replace(pg_catalog.lower(
                      pg_catalog.pg_get_expr(
                        policy.polwithcheck,policy.polrelid,true
                      )
                    ),'pg_catalog.',''),
                    'public.',''
                  ),
                  '::(text|uuid|character varying|varchar)','','g'
                ),
                '[[:space:]()"]','','g'
              ),
              'fromorganization_membershipsasmembership',
              'fromorganization_membershipsmembership'
            )=$policy$organization_id=nullifcurrent_setting'app.current_organization_id',true,''andexistsselect1fromorganization_membershipsmembershipwheremembership.organization_id=nullifcurrent_setting'app.current_organization_id',true,''andmembership.user_id=nullifcurrent_setting'app.current_user_id',true,''andmembership.status='active'$policy$
    ) THEN
        RAISE EXCEPTION
          '0041 active-membership tenant policy catalog is not exact';
    END IF;

    IF 8<>(
      SELECT count(*)
      FROM (VALUES
        ('staff_room_presence_sessions','staff_room_presence_sessions_row_guard',
         'caresync_0041_presence_row_guard',31,false),
        ('staff_room_presence_sessions','staff_room_presence_sessions_bundle_guard',
         'caresync_0041_presence_bundle_guard',21,true),
        ('staff_room_presence_events','staff_room_presence_events_insert_guard',
         'caresync_0041_presence_event_guard',7,false),
        ('staff_room_presence_events','staff_room_presence_events_immutable',
         'caresync_0041_event_immutable_guard',27,false),
        ('room_operational_exception_heads','room_operational_exception_heads_row_guard',
         'caresync_0041_exception_head_guard',31,false),
        ('room_operational_exception_heads','room_operational_exception_heads_bundle_guard',
         'caresync_0041_exception_bundle_guard',21,true),
        ('room_operational_exception_events','room_operational_exception_events_insert_guard',
         'caresync_0041_exception_event_guard',7,false),
        ('room_operational_exception_events','room_operational_exception_events_immutable',
         'caresync_0041_event_immutable_guard',27,false)
      ) AS expected(
        table_name,trigger_name,function_name,trigger_type,is_constraint
      )
      JOIN pg_catalog.pg_trigger AS trigger
        ON trigger.tgrelid=pg_catalog.to_regclass(
             'public.' || expected.table_name
           )
       AND trigger.tgname=expected.trigger_name
       AND NOT trigger.tgisinternal
      JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid
      WHERE procedure.proname=expected.function_name
        AND procedure.pronamespace=pg_catalog.to_regnamespace('public')
        AND trigger.tgtype=expected.trigger_type
        AND (trigger.tgconstraint<>0)=expected.is_constraint
        AND trigger.tgenabled='O'
        AND trigger.tgattr::text=''
        AND trigger.tgqual IS NULL
        AND (
          (NOT expected.is_constraint
           AND NOT trigger.tgdeferrable
           AND NOT trigger.tginitdeferred)
          OR
          (expected.is_constraint
           AND trigger.tgdeferrable
           AND trigger.tginitdeferred)
        )
    ) OR 8<>(
      SELECT count(*)
      FROM pg_catalog.pg_trigger AS trigger
      WHERE trigger.tgrelid IN (
        pg_catalog.to_regclass('public.staff_room_presence_sessions'),
        pg_catalog.to_regclass('public.staff_room_presence_events'),
        pg_catalog.to_regclass('public.room_operational_exception_heads'),
        pg_catalog.to_regclass('public.room_operational_exception_events')
      )
        AND NOT trigger.tgisinternal
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence trigger topology is not exact';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM (VALUES
        ('caresync_0041_presence_row_guard()',
         CASE WHEN EXISTS (
           SELECT 1 FROM public.alembic_version
           WHERE version_num='0043_org_wide_room_presence'
         ) THEN '7324cc1ec57481f779d8f7b8e5b8e841'
           ELSE '7f3c407496dbae87792b7c805b5e45b8'
         END),
        ('caresync_0041_event_immutable_guard()',
         'c0151b59c333111105787a1d98c8af7a'),
        ('caresync_0041_presence_event_guard()',
         '29c9d53306335d246d7497c7d7b8ade7'),
        ('caresync_0041_presence_bundle_guard()',
         'd6bd7fc6fc38f4a5c4dbd513c0618c4d'),
        ('caresync_0041_exception_head_guard()',
         '15363b94cf5baf80b88818e7b1ba3910'),
        ('caresync_0041_exception_event_guard()',
         '2b2f743859694f30d82f7050275278c8'),
        ('caresync_0041_exception_bundle_guard()',
         '0d0fdc0c2d147f713944a5240737ddcc')
      ) AS expected(signature,source_md5)
      JOIN pg_catalog.pg_proc AS procedure
        ON procedure.oid=pg_catalog.to_regprocedure(
             'public.' || expected.signature
           )
      JOIN pg_catalog.pg_language AS language
        ON language.oid=procedure.prolang
      WHERE NOT procedure.prosecdef
         OR procedure.prorettype<>'pg_catalog.trigger'::pg_catalog.regtype
         OR procedure.provolatile<>'v'
         OR procedure.proparallel<>'u'
         OR procedure.proleakproof
         OR procedure.proisstrict
         OR pg_catalog.pg_get_function_identity_arguments(procedure.oid)<>''
         OR language.lanname<>'plpgsql'
         OR procedure.proowner<>relation_owner
         OR pg_catalog.md5(
              pg_catalog.replace(
                pg_catalog.regexp_replace(
                  pg_catalog.lower(procedure.prosrc),
                  '[[:space:]]','','g'
                ),
                '"',''
              )
            )<>expected.source_md5
         OR COALESCE((
              SELECT pg_catalog.array_agg(
                       pg_catalog.replace(setting,' ','') ORDER BY setting
                     )
              FROM pg_catalog.unnest(procedure.proconfig) AS config(setting)
            ),ARRAY[]::text[]) NOT IN (
           ARRAY['search_path=pg_catalog']::text[],
           ARRAY['search_path=pg_catalog,public']::text[]
         )
    ) THEN
        RAISE EXCEPTION
          '0041 room-presence guard function catalog is not exact';
    END IF;
END
$live_room_presence_shape_preflight$;

DO $cluster_role$
DECLARE
    executor record;
    runtime record;
    membership record;
    database_setting record;
    can_manage_cluster_roles boolean;
BEGIN
    SELECT role.rolsuper, role.rolcreaterole
      INTO STRICT executor
    FROM pg_catalog.pg_roles AS role
    WHERE role.rolname = current_user;
    can_manage_cluster_roles := executor.rolsuper OR executor.rolcreaterole;

    SELECT role.* INTO runtime
    FROM pg_catalog.pg_roles AS role
    WHERE role.rolname = 'caresync_basic_app';

    IF runtime.oid IS NULL THEN
        IF NOT can_manage_cluster_roles THEN
            RAISE EXCEPTION
                'cluster-role provisioning required: create caresync_basic_app with a SUPERUSER/CREATEROLE identity before applying schema grants';
        END IF;
        CREATE ROLE caresync_basic_app LOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
        SELECT role.* INTO STRICT runtime
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = 'caresync_basic_app';
    END IF;

    IF can_manage_cluster_roles THEN
        ALTER ROLE caresync_basic_app
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;

        -- Remove every per-database override before setting the one permitted
        -- global role default. Startup also pins the connection's first query.
        FOR database_setting IN
            SELECT database.datname
            FROM pg_catalog.pg_db_role_setting AS setting
            JOIN pg_catalog.pg_database AS database
              ON database.oid = setting.setdatabase
            WHERE setting.setrole = runtime.oid
              AND setting.setdatabase <> 0
        LOOP
            EXECUTE pg_catalog.format(
                'ALTER ROLE caresync_basic_app IN DATABASE %I RESET ALL',
                database_setting.datname
            );
        END LOOP;
        ALTER ROLE caresync_basic_app RESET ALL;
        ALTER ROLE caresync_basic_app SET search_path = public, pg_catalog;

        -- NOINHERIT alone is insufficient because an explicit SET ROLE remains
        -- possible. Remove outgoing and incoming hierarchy edges; revocation
        -- failure aborts the bootstrap.
        FOR membership IN
            SELECT DISTINCT granted.rolname
            FROM pg_catalog.pg_auth_members AS edge
            JOIN pg_catalog.pg_roles AS app_role ON app_role.oid = edge.member
            JOIN pg_catalog.pg_roles AS granted ON granted.oid = edge.roleid
            WHERE app_role.rolname = 'caresync_basic_app'
        LOOP
            EXECUTE pg_catalog.format(
                'REVOKE %I FROM caresync_basic_app', membership.rolname
            );
        END LOOP;
        FOR membership IN
            SELECT DISTINCT member.rolname
            FROM pg_catalog.pg_auth_members AS edge
            JOIN pg_catalog.pg_roles AS app_role ON app_role.oid = edge.roleid
            JOIN pg_catalog.pg_roles AS member ON member.oid = edge.member
            WHERE app_role.rolname = 'caresync_basic_app'
        LOOP
            EXECUTE pg_catalog.format(
                'REVOKE caresync_basic_app FROM %I', membership.rolname
            );
        END LOOP;
    ELSE
        -- A schema-owning migration identity is allowed to apply grants only
        -- after a cluster administrator has made the role terminal and pinned.
        IF runtime.rolsuper OR runtime.rolbypassrls OR runtime.rolinherit
           OR runtime.rolcreaterole OR runtime.rolcreatedb OR runtime.rolreplication
           OR (CASE
                WHEN pg_catalog.array_length(runtime.rolconfig, 1) IS NULL THEN 0
                ELSE pg_catalog.array_length(runtime.rolconfig, 1)
              END) <> 1
           OR pg_catalog.replace(runtime.rolconfig[1], ' ', '') <>
              'search_path=public,pg_catalog'
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.pg_auth_members AS edge
                WHERE edge.member = runtime.oid OR edge.roleid = runtime.oid
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.pg_db_role_setting AS setting
                WHERE setting.setrole = runtime.oid AND setting.setdatabase <> 0
           ) THEN
            RAISE EXCEPTION
                'cluster-role repair required: a SUPERUSER/CREATEROLE identity must terminalize caresync_basic_app and reset its configuration';
        END IF;
    END IF;
END
$cluster_role$;

-- The 0032 repository uses a terminal login only for server-side evidence
-- ingestion and a separate NOLOGIN owner for SECURITY DEFINER execution.  A
-- 0031-or-earlier database takes the absent path and is left unchanged.
DO $transport_command_roles$
DECLARE
    executor record;
    role_record record;
    membership record;
    database_setting record;
    role_name text;
    command_owner_oid oid;
    evidence_oid oid;
    writer_oid oid;
BEGIN
    writer_oid := pg_catalog.to_regprocedure(
      'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
    );
    IF writer_oid IS NULL THEN
        RETURN;
    END IF;

    SELECT role.rolsuper INTO STRICT executor
    FROM pg_catalog.pg_roles AS role WHERE role.rolname=current_user;
    IF NOT executor.rolsuper THEN
        RAISE EXCEPTION
            '0032 transport runtime provisioning requires SUPERUSER so terminal roles and exact function ownership can be repaired atomically';
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_roles
      WHERE rolname='caresync_transport_command_owner'
    ) THEN
        CREATE ROLE caresync_transport_command_owner NOLOGIN
          NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_roles
      WHERE rolname='caresync_transport_evidence_ingest'
    ) THEN
        CREATE ROLE caresync_transport_evidence_ingest LOGIN
          NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
    END IF;

    ALTER ROLE caresync_transport_command_owner NOLOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
    ALTER ROLE caresync_transport_command_owner RESET ALL;
    ALTER ROLE caresync_transport_evidence_ingest LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
    ALTER ROLE caresync_transport_evidence_ingest RESET ALL;
    ALTER ROLE caresync_transport_evidence_ingest SET search_path = public, pg_catalog;

    FOR role_name IN SELECT name FROM pg_catalog.unnest(ARRAY[
      'caresync_transport_command_owner','caresync_transport_evidence_ingest'
    ]::text[]) AS role_to_repair(name)
    LOOP
        SELECT role.* INTO STRICT role_record
        FROM pg_catalog.pg_roles AS role WHERE role.rolname=role_name;
        FOR database_setting IN
          SELECT database.datname
          FROM pg_catalog.pg_db_role_setting AS setting
          JOIN pg_catalog.pg_database AS database ON database.oid=setting.setdatabase
          WHERE setting.setrole=role_record.oid AND setting.setdatabase<>0
        LOOP
            EXECUTE pg_catalog.format(
              'ALTER ROLE %I IN DATABASE %I RESET ALL',role_name,database_setting.datname
            );
        END LOOP;
        FOR membership IN
          SELECT DISTINCT granted.rolname
          FROM pg_catalog.pg_auth_members AS edge
          JOIN pg_catalog.pg_roles AS granted ON granted.oid=edge.roleid
          WHERE edge.member=role_record.oid
        LOOP
            EXECUTE pg_catalog.format('REVOKE %I FROM %I',membership.rolname,role_name);
        END LOOP;
        FOR membership IN
          SELECT DISTINCT member.rolname
          FROM pg_catalog.pg_auth_members AS edge
          JOIN pg_catalog.pg_roles AS member ON member.oid=edge.member
          WHERE edge.roleid=role_record.oid
        LOOP
            EXECUTE pg_catalog.format('REVOKE %I FROM %I',role_name,membership.rolname);
        END LOOP;
    END LOOP;

    SELECT oid INTO STRICT command_owner_oid FROM pg_catalog.pg_roles
    WHERE rolname='caresync_transport_command_owner';
    SELECT oid INTO STRICT evidence_oid FROM pg_catalog.pg_roles
    WHERE rolname='caresync_transport_evidence_ingest';
    IF EXISTS (
      SELECT 1 FROM pg_catalog.pg_shdepend AS dependency
      WHERE dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
        AND dependency.refobjid=command_owner_oid AND dependency.deptype='o'
        AND NOT (
          dependency.dbid=(SELECT oid FROM pg_catalog.pg_database
                           WHERE datname=pg_catalog.current_database())
          AND dependency.classid='pg_catalog.pg_proc'::pg_catalog.regclass
          AND dependency.objid=writer_oid
        )
    ) OR EXISTS (
      SELECT 1 FROM pg_catalog.pg_shdepend AS dependency
      WHERE dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
        AND dependency.refobjid=evidence_oid AND dependency.deptype='o'
    ) THEN
        RAISE EXCEPTION
          '0032 transport roles own forbidden database objects; reassign them before bootstrap';
    END IF;
END
$transport_command_roles$;

-- Ownership lets an application alter RLS, triggers, functions, or grants.
-- Never guess a replacement owner: the operator must deliberately reassign it.
DO $ownership$
DECLARE
    runtime_oid oid;
BEGIN
    SELECT role.oid INTO STRICT runtime_oid
    FROM pg_catalog.pg_roles AS role
    WHERE role.rolname = 'caresync_basic_app';
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_shdepend AS dependency
        WHERE dependency.refclassid =
              'pg_catalog.pg_authid'::pg_catalog.regclass
          AND dependency.refobjid = runtime_oid
          AND dependency.deptype = 'o'
    ) THEN
        RAISE EXCEPTION
            'caresync_basic_app owns database objects; reassign them to the migration owner';
    END IF;
END
$ownership$;

-- Grant repair requires ownership of this database and every non-system object
-- it sanitizes, unless the executor is SUPERUSER. This preflight happens before
-- any database/schema ACL mutation so an under-authorized run fails clearly.
DO $schema_authority$
DECLARE
    executor_oid oid;
    executor_super boolean;
    unauthorized_object text;
BEGIN
    SELECT role.oid, role.rolsuper
      INTO STRICT executor_oid, executor_super
    FROM pg_catalog.pg_roles AS role
    WHERE role.rolname = current_user;
    -- 0029C is a dormant all-or-nothing foundation. Detect either its table or
    -- any orphaned guard as evidence that C was attempted, then require the
    -- complete set before the first database/schema ACL mutation below. This
    -- precedes the SUPERUSER ownership bypass because completeness is not an
    -- ownership question.
    IF (
         pg_catalog.to_regclass(
           'public.facility_release_checkout_activations'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_immutable()'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_immutable()'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_insert_guard()'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_insert_guard()'
         ) IS NOT NULL
       ) AND (
         pg_catalog.to_regclass(
           'public.facility_release_checkout_activations'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_immutable()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_immutable()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_insert_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_insert_guard()'
         ) IS NULL
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete dormant 0029C release-checkout table and guard set';
    END IF;
    -- 0029D is also additive and all-or-nothing.  A retained 0028/0029C
    -- database takes the absent path; any attempted D object requires both C
    -- tables, all six D functions, and both exact enabled write guards.
    -- Trigger ownership follows attendance_intervals ownership, which is
    -- covered by the relation-owner preflight below.
    IF (
         pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_enabled(uuid)'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_replay(uuid)'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_attendance_interval_verified_release_guard()'
         ) IS NOT NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_commit_time_guard()'
         ) IS NOT NULL
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_trigger AS trigger
           WHERE trigger.tgname='attendance_intervals_verified_release_guard'
             AND NOT trigger.tgisinternal
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_trigger AS trigger
           WHERE trigger.tgname='zy_attendance_release_snapshots_commit_time'
             AND NOT trigger.tgisinternal
         )
       ) AND (
         pg_catalog.to_regclass(
           'public.facility_release_checkout_activations'
         ) IS NULL
         OR pg_catalog.to_regclass(
           'public.attendance_release_snapshots'
         ) IS NULL
         OR pg_catalog.to_regclass(
           'public.attendance_intervals'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_enabled(uuid)'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_replay(uuid)'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_attendance_interval_verified_release_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_release_snapshot_commit_time_guard()'
         ) IS NULL
         OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_trigger AS trigger
           JOIN pg_catalog.pg_class AS relation
             ON relation.oid=trigger.tgrelid
           JOIN pg_catalog.pg_namespace AS namespace
             ON namespace.oid=relation.relnamespace
           WHERE trigger.tgname='attendance_intervals_verified_release_guard'
             AND namespace.nspname='public'
             AND relation.relname='attendance_intervals'
             AND trigger.tgfoid=pg_catalog.to_regprocedure(
                   'public.caresync_attendance_interval_verified_release_guard()'
                 )
             AND trigger.tgenabled='O'
             AND trigger.tgtype=27
             AND NOT trigger.tgisinternal
         )
         OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_trigger AS trigger
           JOIN pg_catalog.pg_class AS relation
             ON relation.oid=trigger.tgrelid
           JOIN pg_catalog.pg_namespace AS namespace
             ON namespace.oid=relation.relnamespace
           WHERE trigger.tgname='zy_attendance_release_snapshots_commit_time'
             AND namespace.nspname='public'
             AND relation.relname='attendance_release_snapshots'
             AND trigger.tgfoid=pg_catalog.to_regprocedure(
                   'public.caresync_release_snapshot_commit_time_guard()'
                 )
             AND trigger.tgenabled='O'
             AND trigger.tgtype=7
             AND NOT trigger.tgisinternal
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS procedure
           WHERE procedure.oid IN (
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_activation_enabled(uuid)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_replay(uuid)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_attendance_interval_verified_release_guard()'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_snapshot_commit_time_guard()'
             )
           )
             AND (
               NOT procedure.prosecdef
               OR pg_catalog.array_length(procedure.proconfig, 1)
                  IS DISTINCT FROM 1
               OR pg_catalog.replace(procedure.proconfig[1], ' ', '') <>
                  'search_path=pg_catalog,public'
             )
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0029D release-checkout runtime function and trigger set';
    END IF;
    -- 0035 adds one optional, additive activation writer. If it is present it
    -- must remain a fixed-search-path SECURITY DEFINER function layered on the
    -- complete 0029D runtime; a partial or ordinary invoker function is never
    -- repaired into authority by this bootstrap.
    IF pg_catalog.to_regprocedure(
         'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
       ) IS NOT NULL AND (
         pg_catalog.to_regprocedure(
           'public.caresync_release_checkout_activation_enabled(uuid)'
         ) IS NULL
         OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS procedure
           WHERE procedure.oid=pg_catalog.to_regprocedure(
                   'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
                 )
             AND procedure.prosecdef
             AND procedure.provolatile='v'
             AND pg_catalog.array_length(procedure.proconfig, 1)=1
             AND pg_catalog.replace(procedure.proconfig[1], ' ', '')=
                 'search_path=pg_catalog,public'
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0035 release-checkout activation writer';
    END IF;
    IF NOT executor_super THEN
      IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_database AS database
        WHERE database.datname = pg_catalog.current_database()
          AND database.datdba <> executor_oid
    ) THEN
        RAISE EXCEPTION
            'schema-grant repair required: current user must own database % or be SUPERUSER',
            pg_catalog.current_database();
      END IF;

    SELECT pg_catalog.format('schema %I', namespace.nspname)
      INTO unauthorized_object
    FROM pg_catalog.pg_namespace AS namespace
    WHERE namespace.nspname !~ '^pg_'
      AND namespace.nspname <> 'information_schema'
      AND namespace.nspowner <> executor_oid
      AND namespace.nspowner <> (
            SELECT role.oid
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname = 'pg_database_owner'
          )
    ORDER BY namespace.nspname
    LIMIT 1;
    IF unauthorized_object IS NULL THEN
        SELECT pg_catalog.format(
                   '%I.%I', namespace.nspname, relation.relname
               )
          INTO unauthorized_object
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname !~ '^pg_'
          AND namespace.nspname <> 'information_schema'
          AND relation.relkind IN ('r', 'p', 'S')
          AND relation.relowner <> executor_oid
        ORDER BY namespace.nspname, relation.relname
        LIMIT 1;
    END IF;
    IF unauthorized_object IS NULL THEN
        SELECT procedure.oid::pg_catalog.regprocedure::text
          INTO unauthorized_object
        FROM pg_catalog.pg_proc AS procedure
        WHERE procedure.oid IN (
            pg_catalog.to_regprocedure(
                'public.caresync_charge_childcare_reconciliation(uuid,uuid,uuid)'
            ),
            pg_catalog.to_regprocedure('public.caresync_childcare_operation_guard()'),
            pg_catalog.to_regprocedure(
                'public.caresync_childcare_reconciliation_proof_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_childcare_immutable_ledger_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_childcare_contact_retirement_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_insert_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_transition_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_temporal_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_person_invariant()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_child_revision_invariant()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_evidence_invariant()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_receipt_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_receipt_invariant()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_actor_is_privileged(uuid)'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_evidence_object_write_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_evidence_object_invariant()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_evidence_object_link_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_evidence_review_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_authority_activation_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_activation_immutable()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_snapshot_immutable()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_activation_insert_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_snapshot_insert_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_activation_enabled(uuid)'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_replay(uuid)'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_attendance_interval_verified_release_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_snapshot_commit_time_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
            ),
            pg_catalog.to_regprocedure(
                'public.sync_marketplace_job_screening_from_terms()'
            ),
            pg_catalog.to_regprocedure(
                'public.sync_marketplace_job_screening_from_listing()'
            ),
            pg_catalog.to_regprocedure('public.caresync_0030_immutable_fact()'),
            pg_catalog.to_regprocedure('public.caresync_0030_coverage_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_snapshot_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_share_insert_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_review_insert_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_document_guard()'),
            pg_catalog.to_regprocedure(
                'public.caresync_0030_offer_terms_insert_guard()'
            ),
            pg_catalog.to_regprocedure('public.caresync_0030_offer_terms_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_share_guard()'),
            pg_catalog.to_regprocedure('public.caresync_0030_offer_ack_guard()'),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_presence_row_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_event_immutable_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_presence_event_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_presence_bundle_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_exception_head_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_exception_event_guard()'
            ),
            pg_catalog.to_regprocedure(
                'public.caresync_0041_exception_bundle_guard()'
            )
        )
          AND procedure.proowner <> executor_oid
        LIMIT 1;
    END IF;
      IF unauthorized_object IS NOT NULL THEN
        RAISE EXCEPTION
            'schema-grant repair required: current user does not own % and is not SUPERUSER',
            unauthorized_object;
      END IF;
    END IF;
    IF pg_catalog.to_regprocedure(
           'public.caresync_charge_childcare_reconciliation(uuid,uuid,uuid)'
       ) IS NULL
       OR pg_catalog.to_regprocedure('public.caresync_childcare_operation_guard()') IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_childcare_reconciliation_proof_guard()'
          ) IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_childcare_immutable_ledger_guard()'
          ) IS NULL
       OR pg_catalog.to_regprocedure(
            'public.caresync_childcare_contact_retirement_guard()'
          ) IS NULL THEN
        RAISE EXCEPTION
            'schema-grant repair requires revision 0028 guard functions; migrate to the exact reviewed revision 0043_org_wide_room_presence first';
    END IF;
    IF pg_catalog.to_regclass('public.family_authority_people') IS NOT NULL
       AND (
         pg_catalog.to_regprocedure(
           'public.caresync_family_authority_insert_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_transition_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_temporal_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_person_invariant()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_child_revision_invariant()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_evidence_invariant()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_receipt_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_receipt_invariant()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_authority_actor_is_privileged(uuid)'
         ) IS NULL
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0029A authority guard set';
    END IF;
    IF pg_catalog.to_regclass(
         'public.family_authority_evidence_objects'
       ) IS NOT NULL
       AND (
         pg_catalog.to_regprocedure(
           'public.caresync_family_evidence_object_write_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_evidence_object_invariant()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_evidence_object_link_guard()'
         ) IS NULL
         OR pg_catalog.to_regprocedure(
           'public.caresync_family_evidence_review_guard()'
         ) IS NULL
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0029A1 evidence-vault guard set';
    END IF;
    IF (
         pg_catalog.to_regprocedure(
           'public.caresync_family_authority_activation_guard()'
         ) IS NOT NULL
         OR EXISTS (
           SELECT 1 FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.consent_policy_versions'
                 )
             AND attribute.attname='content_text'
             AND attribute.attnum>0 AND NOT attribute.attisdropped
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.child_consent_decisions'
                 )
             AND attribute.attname IN (
               'signer_authority_evidence_id',
               'signer_authority_evidence_assessment_id'
             )
             AND attribute.attnum>0 AND NOT attribute.attisdropped
         )
       ) AND (
         pg_catalog.to_regprocedure(
           'public.caresync_family_authority_activation_guard()'
         ) IS NULL
         OR NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.consent_policy_versions'
                 )
             AND attribute.attname='content_text'
             AND attribute.attnum>0 AND NOT attribute.attisdropped
         )
         OR 2<>(
           SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.child_consent_decisions'
                 )
             AND attribute.attname IN (
               'signer_authority_evidence_id',
               'signer_authority_evidence_assessment_id'
             )
             AND attribute.attnum>0 AND NOT attribute.attisdropped
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0029A2 activation guard and columns';
    END IF;
    -- Revision 0030 is another additive, all-or-nothing capability. A retained
    -- 0028 database takes the absent path; any attempted 0030 relation or
    -- function must have the entire guarded/RLS boundary before ACL repair.
    IF (
         EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'ats_job_screening_terms','marketplace_job_screening_terms',
             'marketplace_screening_profiles','ats_application_screening_snapshots',
             'ats_offer_screening_terms','staff_screening_documents',
             'staff_screening_document_versions',
             'staff_screening_candidate_confirmations',
             'staff_screening_application_shares',
             'staff_screening_employer_reviews','ats_offer_acknowledgments'
           ]::text[]) AS expected(name)
           WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'sync_marketplace_job_screening_from_terms()',
             'sync_marketplace_job_screening_from_listing()',
             'caresync_0030_immutable_fact()','caresync_0030_coverage_guard()',
             'caresync_0030_snapshot_guard()','caresync_0030_share_insert_guard()',
             'caresync_0030_review_insert_guard()','caresync_0030_document_guard()',
             'caresync_0030_offer_terms_insert_guard()',
             'caresync_0030_offer_terms_guard()','caresync_0030_share_guard()',
             'caresync_0030_offer_ack_guard()'
           ]::text[]) AS expected(signature)
           WHERE pg_catalog.to_regprocedure(
             'public.' || expected.signature
           ) IS NOT NULL
         )
       ) AND (
         11<>(
           SELECT count(*) FROM pg_catalog.unnest(ARRAY[
             'ats_job_screening_terms','marketplace_job_screening_terms',
             'marketplace_screening_profiles','ats_application_screening_snapshots',
             'ats_offer_screening_terms','staff_screening_documents',
             'staff_screening_document_versions',
             'staff_screening_candidate_confirmations',
             'staff_screening_application_shares',
             'staff_screening_employer_reviews','ats_offer_acknowledgments'
           ]::text[]) AS expected(name)
           WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
         )
         OR 12<>(
           SELECT count(*) FROM pg_catalog.unnest(ARRAY[
             'sync_marketplace_job_screening_from_terms()',
             'sync_marketplace_job_screening_from_listing()',
             'caresync_0030_immutable_fact()','caresync_0030_coverage_guard()',
             'caresync_0030_snapshot_guard()','caresync_0030_share_insert_guard()',
             'caresync_0030_review_insert_guard()','caresync_0030_document_guard()',
             'caresync_0030_offer_terms_insert_guard()',
             'caresync_0030_offer_terms_guard()','caresync_0030_share_guard()',
             'caresync_0030_offer_ack_guard()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=
             pg_catalog.to_regprocedure('public.' || expected.signature)
           WHERE procedure.provolatile='v' AND NOT procedure.prosecdef
             AND pg_catalog.array_length(procedure.proconfig,1)=1
             AND pg_catalog.replace(procedure.proconfig[1],' ','')=
                 'search_path=pg_catalog,public'
         )
         OR 16<>(
           SELECT count(*) FROM pg_catalog.pg_trigger AS trigger
           WHERE trigger.tgname IN (
             'ats_job_screening_marketplace','marketplace_jobs_screening_projection',
             'staff_screening_document_versions_immutable',
             'staff_screening_candidate_confirmations_immutable',
             'staff_screening_employer_reviews_immutable',
             'ats_offer_screening_terms_immutable','ats_offer_acknowledgments_immutable',
             'staff_screening_versions_coverage_guard',
             'ats_application_screening_snapshots_guard',
             'staff_screening_shares_insert_guard','staff_screening_reviews_insert_guard',
             'staff_screening_documents_guard','ats_offer_screening_terms_insert_guard',
             'ats_offers_0030_terms_guard','staff_screening_shares_guard',
             'ats_offer_acknowledgments_guard'
           ) AND NOT trigger.tgisinternal AND trigger.tgenabled<>'D'
         )
         OR 10<>(
           SELECT count(*) FROM pg_catalog.pg_class AS relation
           WHERE relation.oid IN (
             SELECT pg_catalog.to_regclass('public.' || expected.name)
             FROM pg_catalog.unnest(ARRAY[
               'ats_job_screening_terms','marketplace_screening_profiles',
               'ats_application_screening_snapshots','ats_offer_screening_terms',
               'staff_screening_documents','staff_screening_document_versions',
               'staff_screening_candidate_confirmations',
               'staff_screening_application_shares',
               'staff_screening_employer_reviews','ats_offer_acknowledgments'
             ]::text[]) AS expected(name)
           ) AND relation.relrowsecurity AND relation.relforcerowsecurity
         )
         OR 23<>(
           SELECT count(*) FROM pg_catalog.pg_policy AS policy
           WHERE policy.polrelid IN (
             SELECT pg_catalog.to_regclass('public.' || expected.name)
             FROM pg_catalog.unnest(ARRAY[
               'ats_job_screening_terms','marketplace_screening_profiles',
               'ats_application_screening_snapshots','ats_offer_screening_terms',
               'staff_screening_documents','staff_screening_document_versions',
               'staff_screening_candidate_confirmations',
               'staff_screening_application_shares',
               'staff_screening_employer_reviews','ats_offer_acknowledgments'
             ]::text[]) AS expected(name)
           )
         )
         OR NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_policy AS policy
           WHERE policy.polrelid=
                 pg_catalog.to_regclass('public.ats_job_screening_terms')
             AND policy.polname='ats_job_screening_terms_read'
             AND pg_catalog.strpos(pg_catalog.lower(
                   pg_catalog.pg_get_expr(policy.polqual,policy.polrelid)
                 ),'marketplace_jobs')>0
             AND pg_catalog.strpos(pg_catalog.lower(
                   pg_catalog.pg_get_expr(policy.polqual,policy.polrelid)
                 ),'listing_id')>0
             AND pg_catalog.strpos(pg_catalog.lower(
                   pg_catalog.pg_get_expr(policy.polqual,policy.polrelid)
                 ),'ats_job_screening_terms.job_id')>0
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0030 staff-screening guard and RLS set';
    END IF;
    -- Revision 0031 is a read-only registry foundation. Any partial table,
    -- trigger, function, RLS, or policy set is unsafe to expose to runtime.
    IF (
         EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'staff_driver_capability_versions',
             'staff_driver_qualification_versions',
             'staff_driver_authorization_decisions',
             'staff_driver_readiness_decisions','transport_vehicles',
             'transport_vehicle_versions','transport_vehicle_evidence_versions'
           ]::text[]) AS expected(name)
           WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'caresync_0031_immutable_fact()','caresync_0031_capability_guard()',
             'caresync_0031_qualification_guard()',
             'caresync_0031_authorization_guard()','caresync_0031_vehicle_guard()',
             'caresync_0031_vehicle_version_guard()',
             'caresync_0031_vehicle_evidence_guard()',
             'caresync_0031_readiness_guard()'
           ]::text[]) AS expected(signature)
           WHERE pg_catalog.to_regprocedure('public.' || expected.signature) IS NOT NULL
         )
       ) AND (
         7<>(
           SELECT count(*) FROM pg_catalog.unnest(ARRAY[
             'staff_driver_capability_versions',
             'staff_driver_qualification_versions',
             'staff_driver_authorization_decisions',
             'staff_driver_readiness_decisions','transport_vehicles',
             'transport_vehicle_versions','transport_vehicle_evidence_versions'
           ]::text[]) AS expected(name)
           WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL
         )
         OR 8<>(
           SELECT count(*) FROM pg_catalog.unnest(ARRAY[
             'caresync_0031_immutable_fact()','caresync_0031_capability_guard()',
             'caresync_0031_qualification_guard()',
             'caresync_0031_authorization_guard()','caresync_0031_vehicle_guard()',
             'caresync_0031_vehicle_version_guard()',
             'caresync_0031_vehicle_evidence_guard()',
             'caresync_0031_readiness_guard()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=
             pg_catalog.to_regprocedure('public.' || expected.signature)
           WHERE procedure.provolatile='v' AND NOT procedure.prosecdef
             AND pg_catalog.array_length(procedure.proconfig,1)=1
             AND pg_catalog.replace(procedure.proconfig[1],' ','')=
                 'search_path=pg_catalog,public'
         )
         OR 13<>(
           SELECT count(*) FROM pg_catalog.pg_trigger AS trigger
           WHERE trigger.tgname IN (
             'staff_driver_capability_versions_immutable',
             'staff_driver_qualification_versions_immutable',
             'staff_driver_authorization_decisions_immutable',
             'staff_driver_readiness_decisions_immutable',
             'transport_vehicle_versions_immutable',
             'transport_vehicle_evidence_versions_immutable',
             'staff_driver_capability_insert_guard',
             'staff_driver_qualification_insert_guard',
             'staff_driver_authorization_insert_guard','transport_vehicles_guard',
             'transport_vehicle_versions_insert_guard',
             'transport_vehicle_evidence_insert_guard',
             'staff_driver_readiness_insert_guard'
           ) AND NOT trigger.tgisinternal AND trigger.tgenabled<>'D'
         )
         OR 7<>(
           SELECT count(*) FROM pg_catalog.pg_class AS relation
           WHERE relation.oid IN (
             SELECT pg_catalog.to_regclass('public.' || expected.name)
             FROM pg_catalog.unnest(ARRAY[
               'staff_driver_capability_versions',
               'staff_driver_qualification_versions',
               'staff_driver_authorization_decisions',
               'staff_driver_readiness_decisions','transport_vehicles',
               'transport_vehicle_versions','transport_vehicle_evidence_versions'
             ]::text[]) AS expected(name)
           ) AND relation.relrowsecurity AND relation.relforcerowsecurity
         )
         OR (CASE WHEN pg_catalog.to_regprocedure(
                    'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
                  ) IS NULL THEN 7 ELSE 14 END)<>(
           SELECT count(*) FROM pg_catalog.pg_policy AS policy
           WHERE policy.polrelid IN (
             SELECT pg_catalog.to_regclass('public.' || expected.name)
             FROM pg_catalog.unnest(ARRAY[
               'staff_driver_capability_versions',
               'staff_driver_qualification_versions',
               'staff_driver_authorization_decisions',
               'staff_driver_readiness_decisions','transport_vehicles',
               'transport_vehicle_versions','transport_vehicle_evidence_versions'
             ]::text[]) AS expected(name)
           )
         )
       ) THEN
        RAISE EXCEPTION
            'schema-grant repair requires the complete 0031 driver/vehicle registry';
    END IF;
END
$schema_authority$;

-- Database TEMP is granted to PUBLIC by PostgreSQL by default. It must be
-- removed: TEMP + EXECUTE on a trigger function permits a temporary-table
-- trigger to invoke the function outside the intended application table.
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON DATABASE %I FROM caresync_basic_app',
    pg_catalog.current_database()
) \gexec
SELECT pg_catalog.format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC',
    pg_catalog.current_database()
) \gexec
SELECT pg_catalog.format(
    'GRANT CONNECT ON DATABASE %I TO caresync_basic_app',
    pg_catalog.current_database()
) \gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON DATABASE %I FROM caresync_transport_command_owner, caresync_transport_evidence_ingest',
    pg_catalog.current_database()
)
WHERE pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec
SELECT pg_catalog.format(
    'GRANT CONNECT ON DATABASE %I TO caresync_transport_evidence_ingest',
    pg_catalog.current_database()
)
WHERE pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec

-- Remove object and schema privilege drift in every application/user schema,
-- including privileges inherited through PUBLIC. Intended grants are restored
-- below only for the public CareSync schema.
SELECT pg_catalog.format(
    'REVOKE CREATE ON SCHEMA %I FROM PUBLIC, caresync_basic_app', namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
\gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON SCHEMA %I FROM PUBLIC, caresync_basic_app, caresync_transport_command_owner, caresync_transport_evidence_ingest',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
  AND pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM PUBLIC, caresync_basic_app',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
\gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM caresync_transport_command_owner, caresync_transport_evidence_ingest',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
  AND pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC, caresync_basic_app',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
\gexec
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM caresync_transport_command_owner, caresync_transport_evidence_ingest',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
  AND pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec

-- At 0032, remove PUBLIC's implicit EXECUTE from every application-schema
-- function.  The supported application repositories are re-granted explicitly
-- below; the evidence-ingest identity receives only the 0032 writer.
SELECT pg_catalog.format(
    'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA %I FROM PUBLIC, caresync_basic_app, caresync_transport_command_owner, caresync_transport_evidence_ingest',
    namespace.nspname
)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname !~ '^pg_'
  AND namespace.nspname <> 'information_schema'
  AND pg_catalog.to_regprocedure(
        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
      ) IS NOT NULL
\gexec

GRANT USAGE ON SCHEMA public TO caresync_basic_app;
DO $transport_command_schema_usage$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NOT NULL THEN
        GRANT USAGE ON SCHEMA public
        TO caresync_transport_command_owner, caresync_transport_evidence_ingest;
    END IF;
END
$transport_command_schema_usage$;

-- Name the internal 0028 state explicitly as part of the allowlist contract,
-- even though the all-table revocation above has already removed its ACLs.
REVOKE ALL PRIVILEGES ON TABLE
    public.childcare_command_slots,
    public.childcare_command_reconciliation_budget_entries,
    public.childcare_command_reconciliation_budgets
FROM PUBLIC, caresync_basic_app;

-- Trigger functions are callable only through the triggers installed by the
-- migration owner. Revoke all five 0028 guards, including all SECURITY DEFINER
-- functions, from both direct and PUBLIC authority.
REVOKE ALL PRIVILEGES ON FUNCTION
    public.caresync_charge_childcare_reconciliation(uuid, uuid, uuid)
FROM PUBLIC, caresync_basic_app;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.caresync_childcare_operation_guard()
FROM PUBLIC, caresync_basic_app;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.caresync_childcare_reconciliation_proof_guard()
FROM PUBLIC, caresync_basic_app;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.caresync_childcare_immutable_ledger_guard()
FROM PUBLIC, caresync_basic_app;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.caresync_childcare_contact_retirement_guard()
FROM PUBLIC, caresync_basic_app;

-- Revision 0029A is staged additively. Revoke its trigger functions when the
-- kernel exists while keeping this bootstrap safe for a retained 0028 runtime.
DO $family_authority_function_revoke$
BEGIN
    IF pg_catalog.to_regclass('public.family_authority_people') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_insert_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_transition_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_temporal_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_person_invariant()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_child_revision_invariant()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_evidence_invariant()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_receipt_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_receipt_invariant()
        FROM PUBLIC, caresync_basic_app;
        -- Unlike the trigger-only guards, this fixed-search-path predicate is
        -- invoked by RLS while evaluating runtime queries.  Keep PUBLIC out,
        -- then grant only the exact execution right the policies require.
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_actor_is_privileged(uuid)
        FROM PUBLIC, caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_family_authority_actor_is_privileged(uuid)
        TO caresync_basic_app;
    END IF;
END
$family_authority_function_revoke$;

-- 0029B's read-only projection is called directly by the basic API.  At 0032
-- PUBLIC function execution has been removed globally, so restore only this
-- exact application repository when it exists.
DO $family_release_context_runtime_grant$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_family_release_context_inputs(uuid,uuid)'
       ) IS NOT NULL AND pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_release_context_inputs(uuid, uuid)
        FROM PUBLIC, caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_family_release_context_inputs(uuid, uuid)
        TO caresync_basic_app;
    END IF;
END
$family_release_context_runtime_grant$;

DO $family_evidence_vault_function_revoke$
BEGIN
    IF pg_catalog.to_regclass(
         'public.family_authority_evidence_objects'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_evidence_object_write_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_evidence_object_invariant()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_evidence_object_link_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_evidence_review_guard()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$family_evidence_vault_function_revoke$;

DO $family_authority_activation_function_revoke$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_family_authority_activation_guard()'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_authority_activation_guard()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$family_authority_activation_function_revoke$;

-- 0030 screening functions are trigger-only. Keep both PUBLIC and the runtime
-- role from invoking them directly; table RLS and the installed triggers are
-- the only supported enforcement path.
DO $staff_screening_function_revoke$
BEGIN
    IF pg_catalog.to_regclass('public.ats_job_screening_terms') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
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
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$staff_screening_function_revoke$;

-- 0031 functions are trigger-only. The runtime may read its own RLS-filtered
-- projection but cannot invoke guards or write registry facts directly.
DO $driver_vehicle_registry_function_revoke$
BEGIN
    IF pg_catalog.to_regclass(
         'public.staff_driver_capability_versions'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_0031_immutable_fact(),
            public.caresync_0031_capability_guard(),
            public.caresync_0031_qualification_guard(),
            public.caresync_0031_authorization_guard(),
            public.caresync_0031_vehicle_guard(),
            public.caresync_0031_vehicle_version_guard(),
            public.caresync_0031_vehicle_evidence_guard(),
            public.caresync_0031_readiness_guard()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$driver_vehicle_registry_function_revoke$;

-- 0033 billing functions are trigger-only guards.  The terminal-claim trigger
-- is SECURITY DEFINER, but remains callable only by its installed triggers.
DO $billing_ledger_function_revoke$
BEGIN
    IF pg_catalog.to_regclass('public.billing_accounts') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_0033_immutable_fact(),
            public.caresync_0033_role_permission_guard(),
            public.caresync_0033_source_attestation_guard(),
            public.caresync_0033_attested_source_immutable(),
            public.caresync_0033_actor_guard(),
            public.caresync_0033_version_guard(),
            public.caresync_0033_invoice_line_guard(),
            public.caresync_0033_allocation_guard(),
            public.caresync_0033_credit_guard(),
            public.caresync_0033_journal_sequence_guard(),
            public.caresync_0033_journal_validate(),
            public.caresync_0033_effect_open_guard(),
            public.caresync_0033_bundle_validate(),
            public.caresync_0033_receipt_guard(),
            public.caresync_0033_claim_guard(),
            public.caresync_0033_terminal_claim()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$billing_ledger_function_revoke$;

-- 0041 guard functions are trigger-only SECURITY DEFINER entry points.  Their
-- table triggers may invoke them, but neither PUBLIC nor the runtime role may
-- call them directly (including from a temporary relation).
DO $live_room_presence_function_revoke$
BEGIN
    IF pg_catalog.to_regclass(
         'public.staff_room_presence_sessions'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_0041_presence_row_guard(),
            public.caresync_0041_event_immutable_guard(),
            public.caresync_0041_presence_event_guard(),
            public.caresync_0041_presence_bundle_guard(),
            public.caresync_0041_exception_head_guard(),
            public.caresync_0041_exception_event_guard(),
            public.caresync_0041_exception_bundle_guard()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$live_room_presence_function_revoke$;

-- 0032 has one and only one directly executable repository.  Its owner is a
-- terminal NOLOGIN identity; callers retain their session_user so the function
-- can split ordinary commands from server-scanned evidence ingestion.  The
-- temporary CREATE right exists only inside this atomic DO statement because
-- PostgreSQL requires the new function owner to be able to create in the
-- containing schema at ownership-transfer time.
DO $transport_command_repository_grants$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NULL THEN
        RETURN;
    END IF;

    GRANT CREATE ON SCHEMA public TO caresync_transport_command_owner;
    ALTER FUNCTION public.caresync_0032_execute_command(text,uuid,text,jsonb)
      OWNER TO caresync_transport_command_owner;
    REVOKE CREATE ON SCHEMA public FROM caresync_transport_command_owner;

    REVOKE ALL PRIVILEGES ON FUNCTION
        public.caresync_0032_immutable_fact(),
        public.caresync_0032_receipt_guard(),
        public.caresync_0032_qualification_evidence_guard(),
        public.caresync_0032_qualification_review_guard(),
        public.caresync_0032_vehicle_review_guard(),
        public.caresync_0032_vehicle_scan_guard()
    FROM PUBLIC, caresync_basic_app, caresync_transport_command_owner,
         caresync_transport_evidence_ingest;
    REVOKE ALL PRIVILEGES ON FUNCTION
        public.caresync_0032_execute_command(text,uuid,text,jsonb)
    FROM PUBLIC, caresync_basic_app, caresync_transport_evidence_ingest;
    GRANT EXECUTE ON FUNCTION
        public.caresync_0032_execute_command(text,uuid,text,jsonb)
    TO caresync_basic_app, caresync_transport_evidence_ingest;

    GRANT SELECT ON TABLE
        public.users,
        public.organizations,
        public.organization_memberships,
        public.roles,
        public.notification_push_subscriptions,
        public.user_notification_preferences,
        public.staff_driver_capability_versions,
        public.staff_driver_qualification_versions,
        public.staff_driver_authorization_decisions,
        public.staff_driver_readiness_decisions,
        public.transport_vehicles,
        public.transport_vehicle_versions,
        public.transport_vehicle_evidence_versions,
        public.transport_registry_command_receipts,
        public.staff_driver_qualification_evidence_objects,
        public.staff_driver_qualification_review_decisions,
        public.transport_vehicle_evidence_review_decisions,
        public.transport_vehicle_evidence_scan_facts
    TO caresync_transport_command_owner;
    GRANT INSERT ON TABLE
        public.staff_driver_capability_versions,
        public.staff_driver_qualification_versions,
        public.staff_driver_authorization_decisions,
        public.staff_driver_readiness_decisions,
        public.transport_vehicles,
        public.transport_vehicle_versions,
        public.transport_vehicle_evidence_versions,
        public.transport_registry_command_receipts,
        public.staff_driver_qualification_evidence_objects,
        public.staff_driver_qualification_review_decisions,
        public.transport_vehicle_evidence_review_decisions,
        public.transport_vehicle_evidence_scan_facts,
        public.user_notifications,
        public.audit_events,
        public.realtime_events,
        public.user_realtime_events,
        public.notification_deliveries
    TO caresync_transport_command_owner;
    GRANT USAGE ON SEQUENCE
        public.realtime_events_sequence_id_seq,
        public.user_realtime_events_sequence_id_seq
    TO caresync_transport_command_owner;
    -- PostgreSQL requires UPDATE privilege on at least one column for every
    -- SELECT ... FOR UPDATE target.  These id-only grants are lock capability:
    -- context-table RLS rejects every resulting mutation, while append-only
    -- and vehicle guards reject changes on the registry fact tables.
    GRANT UPDATE (id) ON TABLE
        public.users,
        public.organizations,
        public.organization_memberships,
        public.roles,
        public.staff_driver_capability_versions,
        public.staff_driver_qualification_versions,
        public.staff_driver_authorization_decisions,
        public.transport_vehicles,
        public.transport_vehicle_versions,
        public.transport_vehicle_evidence_versions
    TO caresync_transport_command_owner;
    GRANT UPDATE (retired_at, retired_by_user_id, retirement_reason_code)
      ON TABLE public.transport_vehicles TO caresync_transport_command_owner;
    -- Existing notification triggers use ON CONFLICT DO NOTHING.  PostgreSQL
    -- requires SELECT only on the named arbiter columns; do not expose payloads.
    GRANT SELECT (id) ON TABLE public.user_realtime_events
      TO caresync_transport_command_owner;
    GRANT SELECT (notification_id, subscription_id)
      ON TABLE public.notification_deliveries TO caresync_transport_command_owner;

    GRANT SELECT ON TABLE
        public.transport_registry_command_receipts,
        public.staff_driver_qualification_evidence_objects,
        public.staff_driver_qualification_review_decisions,
        public.transport_vehicle_evidence_review_decisions,
        public.transport_vehicle_evidence_scan_facts
    TO caresync_basic_app;
END
$transport_command_repository_grants$;

-- Revision 0029C is still dormant. If its source-only foundation is present,
-- keep both the activation table and every trigger-only function completely
-- outside the runtime role until PostgreSQL command writing is certified.
DO $family_release_checkout_dormant_revoke$
BEGIN
    IF pg_catalog.to_regclass(
         'public.facility_release_checkout_activations'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.facility_release_checkout_activations
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_activation_immutable()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_snapshot_immutable()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_activation_insert_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_snapshot_insert_guard()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$family_release_checkout_dormant_revoke$;

-- Revision 0029D exposes only four narrow SECURITY DEFINER repositories.
-- The activation table and release snapshots remain inaccessible for direct
-- writes, and both write guards remain trigger-only.  The schema preflight
-- above guarantees this block cannot run against a partial D installation.
DO $family_release_checkout_runtime_grants$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_release_checkout_activation_enabled(uuid)'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_activation_enabled(uuid)
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_replay(uuid)
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_family_release_context_inputs_at(
                uuid, uuid, timestamp with time zone
            )
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_insert_snapshot(
                uuid, uuid, uuid, uuid, uuid, integer, uuid, uuid,
                uuid, uuid, uuid, uuid, integer, integer, text, text,
                text, text, timestamp with time zone,
                timestamp with time zone, text
            )
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_attendance_interval_verified_release_guard()
        FROM PUBLIC, caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_snapshot_commit_time_guard()
        FROM PUBLIC, caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_release_checkout_activation_enabled(uuid)
        TO caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_release_checkout_replay(uuid)
        TO caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_family_release_context_inputs_at(
                uuid, uuid, timestamp with time zone
            )
        TO caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_release_checkout_insert_snapshot(
                uuid, uuid, uuid, uuid, uuid, integer, uuid, uuid,
                uuid, uuid, uuid, uuid, integer, integer, text, text,
                text, text, timestamp with time zone,
                timestamp with time zone, text
            )
        TO caresync_basic_app;
    END IF;
END
$family_release_checkout_runtime_grants$;

-- Revision 0035 adds one owner/administrator activation writer. It does not
-- grant any direct activation-table privilege and remains absent-safe for
-- databases that have not reached the revision.
DO $family_release_checkout_activation_grant$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
       ) IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_release_checkout_activate_facility(
                uuid, uuid, uuid, text, text, text,
                boolean, boolean, boolean, boolean
            )
        FROM PUBLIC, caresync_basic_app;
        GRANT EXECUTE ON FUNCTION
            public.caresync_release_checkout_activate_facility(
                uuid, uuid, uuid, text, text, text,
                boolean, boolean, boolean, boolean
            )
        TO caresync_basic_app;
    END IF;
END
$family_release_checkout_activation_grant$;

-- Global identity records are not tenant-owned. API membership resolution is
-- required before any tenant table is accessed.
GRANT SELECT, INSERT, UPDATE ON TABLE public.users TO caresync_basic_app;

-- Basic mutable records use archive/status transitions instead of hard delete.
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.organizations,
    public.roles,
    public.organization_memberships,
    public.organization_onboarding,
    public.facilities,
    public.facility_programs,
    public.rooms,
    public.families,
    public.children,
    public.enrollments,
    public.attendance_days,
    public.attendance_intervals,
    public.daily_care_records,
    public.medication_plans,
    public.medication_administrations,
    public.incident_records,
    public.membership_room_assignments,
    public.staff_invitations,
    public.staff_invitation_rooms,
    public.password_reset_challenges,
    public.ats_jobs,
    public.ats_candidates,
    public.ats_applications,
    public.ats_candidate_invitations,
    public.ats_offers,
    public.ats_staff_provisionings,
    public.staff_shifts,
    public.staff_scheduled_shifts,
    public.staff_availability_profiles,
    public.staff_time_off_requests,
    public.staff_shift_templates,
    public.staff_coverage_target_profiles,
    public.staff_rotation_patterns,
    public.staff_open_shifts,
    public.staff_open_shift_engagements,
    public.staff_substitute_profiles,
    public.staff_shift_swap_requests,
    public.realtime_tickets,
    public.marketplace_profiles,
    public.marketplace_application_links,
    public.marketplace_interests,
    public.marketplace_realtime_tickets,
    public.ats_interviews,
    public.marketplace_onboarding_states,
    public.marketplace_document_analyses,
    public.marketplace_credential_documents,
    public.marketplace_credential_notifications,
    public.user_notifications,
    public.user_notification_preferences,
    public.notification_push_subscriptions,
    public.notification_deliveries,
    public.user_realtime_tickets
TO caresync_basic_app;

-- Care-network contacts are temporal facts. Only retirement metadata is
-- mutable; revision 0028 installs the matching immutable/provenance trigger.
GRANT SELECT, INSERT ON TABLE
    public.guardians, public.emergency_contacts
TO caresync_basic_app;

-- The authority kernel uses append-only facts plus tightly bounded one-way
-- transitions. It is optional at 0028 and complete-or-fail once 0029A exists.
DO $family_authority_grants$
BEGIN
    IF pg_catalog.to_regclass('public.family_authority_people') IS NOT NULL THEN
        GRANT SELECT ON TABLE
            public.family_authority_people,
            public.family_authority_person_versions,
            public.family_authority_evidence,
            public.family_authority_evidence_assessments,
            public.child_authority_heads,
            public.child_release_authorizations,
            public.child_release_rules,
            public.consent_policy_versions,
            public.child_consent_decisions,
            public.attendance_release_snapshots
        TO caresync_basic_app;
        GRANT INSERT ON TABLE
            public.family_authority_people,
            public.family_authority_person_versions,
            public.family_authority_evidence,
            public.family_authority_evidence_assessments,
            public.child_authority_heads
        TO caresync_basic_app;
        GRANT UPDATE (
            version, status, current_person_version_id, last_operation_id,
            retired_at, retired_operation_id, updated_at
        ) ON TABLE public.family_authority_people TO caresync_basic_app;
        GRANT UPDATE (closed_at, closed_operation_id)
        ON TABLE public.family_authority_person_versions TO caresync_basic_app;
        GRANT UPDATE (revision, last_operation_id, updated_at)
        ON TABLE public.child_authority_heads TO caresync_basic_app;
    END IF;
END
$family_authority_grants$;
DO $family_evidence_vault_grants$
BEGIN
    IF pg_catalog.to_regclass(
         'public.family_authority_evidence_objects'
       ) IS NOT NULL THEN
        GRANT SELECT, INSERT ON TABLE
            public.family_authority_evidence_objects,
            public.family_authority_evidence_object_assessments
        TO caresync_basic_app;
        GRANT UPDATE (status) ON TABLE
            public.family_authority_evidence_objects
        TO caresync_basic_app;
    END IF;
END
$family_evidence_vault_grants$;
DO $family_authority_activation_grants$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_family_authority_activation_guard()'
       ) IS NOT NULL THEN
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
$family_authority_activation_grants$;
DO $family_authority_activation_audit$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_family_authority_activation_guard()'
       ) IS NOT NULL AND (
         EXISTS (
           WITH activation_tables(relname) AS (VALUES
             ('child_release_authorizations'), ('child_release_rules'),
             ('consent_policy_versions'), ('child_consent_decisions')
           )
           SELECT 1
           FROM activation_tables AS activation
           LEFT JOIN pg_catalog.pg_class AS relation
             ON relation.relname=activation.relname
            AND relation.relnamespace='public'::pg_catalog.regnamespace
           WHERE relation.oid IS NULL
              OR NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app', relation.oid, 'SELECT'
                 )
              OR NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app', relation.oid, 'INSERT'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app', relation.oid, 'UPDATE'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app', relation.oid, 'DELETE'
                 )
         )
         OR NOT pg_catalog.has_table_privilege(
              'caresync_basic_app',
              'public.attendance_release_snapshots', 'SELECT'
            )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app',
              'public.attendance_release_snapshots', 'INSERT'
            )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app',
              'public.attendance_release_snapshots', 'UPDATE'
            )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app',
              'public.attendance_release_snapshots', 'DELETE'
            )
         OR EXISTS (
           WITH protected_tables(relname) AS (VALUES
             ('child_release_authorizations'), ('child_release_rules'),
             ('consent_policy_versions'), ('child_consent_decisions'),
             ('attendance_release_snapshots')
           ), expected_updates(relname,attname) AS (VALUES
             ('child_release_authorizations','version'),
             ('child_release_authorizations','revoked_at'),
             ('child_release_authorizations','revoked_operation_id'),
             ('child_release_authorizations','revocation_reason_code'),
             ('child_release_authorizations','updated_at'),
             ('child_release_rules','version'),
             ('child_release_rules','revoked_at'),
             ('child_release_rules','revoked_operation_id'),
             ('child_release_rules','revocation_reason_code'),
             ('child_release_rules','updated_at'),
             ('child_consent_decisions','version'),
             ('child_consent_decisions','withdrawn_at'),
             ('child_consent_decisions','withdrawn_operation_id'),
             ('child_consent_decisions','withdrawal_reason_code'),
             ('child_consent_decisions','updated_at')
           )
           SELECT 1
           FROM pg_catalog.pg_class AS relation
           JOIN protected_tables AS protected
             ON protected.relname=relation.relname
           JOIN pg_catalog.pg_attribute AS attribute
             ON attribute.attrelid=relation.oid
           WHERE relation.relnamespace='public'::pg_catalog.regnamespace
             AND attribute.attnum>0 AND NOT attribute.attisdropped
             AND pg_catalog.has_column_privilege(
                   'caresync_basic_app', relation.oid,
                   attribute.attnum, 'UPDATE'
                 ) IS DISTINCT FROM EXISTS (
                   SELECT 1 FROM expected_updates AS expected
                   WHERE expected.relname=relation.relname
                     AND expected.attname=attribute.attname
                 )
         )
         OR pg_catalog.has_function_privilege(
              'caresync_basic_app',
              'public.caresync_family_authority_activation_guard()',
              'EXECUTE'
            )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the 0029A2 activation privilege audit';
    END IF;
END
$family_authority_activation_audit$;
DO $family_release_checkout_dormant_audit$
BEGIN
    IF pg_catalog.to_regclass(
         'public.facility_release_checkout_activations'
       ) IS NOT NULL AND (
         pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.facility_release_checkout_activations',
           'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
         )
         OR pg_catalog.has_function_privilege(
           'caresync_basic_app',
           'public.caresync_release_checkout_activation_immutable()',
           'EXECUTE'
         )
         OR pg_catalog.has_function_privilege(
           'caresync_basic_app',
           'public.caresync_release_snapshot_immutable()',
           'EXECUTE'
         )
         OR pg_catalog.has_function_privilege(
           'caresync_basic_app',
           'public.caresync_release_checkout_activation_insert_guard()',
           'EXECUTE'
         )
         OR pg_catalog.has_function_privilege(
           'caresync_basic_app',
           'public.caresync_release_snapshot_insert_guard()',
           'EXECUTE'
         )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app received dormant 0029C release-checkout authority';
    END IF;
END
$family_release_checkout_dormant_audit$;
DO $family_release_checkout_runtime_audit$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_release_checkout_activation_enabled(uuid)'
       ) IS NOT NULL AND (
         NOT COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_activation_enabled(uuid)'
             ),
             'EXECUTE'
           ),
           false
         )
         OR NOT COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_replay(uuid)'
             ),
             'EXECUTE'
           ),
           false
         )
         OR NOT COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
             ),
             'EXECUTE'
           ),
           false
         )
         OR NOT COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
             ),
             'EXECUTE'
           ),
           false
         )
         OR COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_attendance_interval_verified_release_guard()'
             ),
             'EXECUTE'
           ),
           true
         )
         OR COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_release_snapshot_commit_time_guard()'
             ),
             'EXECUTE'
           ),
           true
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS procedure
           CROSS JOIN LATERAL pg_catalog.aclexplode(
             COALESCE(
               procedure.proacl,
               pg_catalog.acldefault('f', procedure.proowner)
             )
           ) AS privilege
           WHERE procedure.oid IN (
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_activation_enabled(uuid)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_replay(uuid)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_insert_snapshot(uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,integer,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text)'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_attendance_interval_verified_release_guard()'
             ),
             pg_catalog.to_regprocedure(
               'public.caresync_release_snapshot_commit_time_guard()'
             )
           )
             AND privilege.grantee=0
             AND privilege.privilege_type='EXECUTE'
         )
         OR pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.facility_release_checkout_activations',
           'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
         )
         OR NOT pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.attendance_release_snapshots',
           'SELECT'
         )
         OR pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.attendance_release_snapshots',
           'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.facility_release_checkout_activations'
                 )
             AND attribute.attnum>0
             AND NOT attribute.attisdropped
             AND pg_catalog.has_column_privilege(
                   'caresync_basic_app', attribute.attrelid,
                   attribute.attnum, 'SELECT, INSERT, UPDATE, REFERENCES'
                 )
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid=pg_catalog.to_regclass(
                   'public.attendance_release_snapshots'
                 )
             AND attribute.attnum>0
             AND NOT attribute.attisdropped
             AND pg_catalog.has_column_privilege(
                   'caresync_basic_app', attribute.attrelid,
                   attribute.attnum, 'INSERT, UPDATE, REFERENCES'
                 )
         )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the 0029D release-checkout runtime privilege audit';
    END IF;
END
$family_release_checkout_runtime_audit$;
DO $family_release_checkout_activation_audit$
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
       ) IS NOT NULL AND (
         NOT COALESCE(
           pg_catalog.has_function_privilege(
             'caresync_basic_app',
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
             ),
             'EXECUTE'
           ),
           false
         )
         OR COALESCE(
           pg_catalog.has_function_privilege(
             'public',
             pg_catalog.to_regprocedure(
               'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
             ),
             'EXECUTE'
           ),
           true
         )
         OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS procedure
           JOIN pg_catalog.pg_roles AS owner_role
             ON owner_role.oid=procedure.proowner
           WHERE procedure.oid=pg_catalog.to_regprocedure(
                   'public.caresync_release_checkout_activate_facility(uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)'
                 )
             AND (
               NOT procedure.prosecdef
               OR procedure.provolatile<>'v'
               OR owner_role.rolname='caresync_basic_app'
               OR pg_catalog.array_length(procedure.proconfig, 1)<>1
               OR pg_catalog.replace(procedure.proconfig[1], ' ', '')<>
                  'search_path=pg_catalog,public'
             )
         )
         OR pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.facility_release_checkout_activations',
           'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
         )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the 0035 release-checkout activation privilege audit';
    END IF;
END
$family_release_checkout_activation_audit$;
GRANT UPDATE (retired_at, retired_operation_id, updated_at)
    ON TABLE public.guardians, public.emergency_contacts
TO caresync_basic_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.marketplace_jobs,
    public.marketplace_profile_photos,
    public.child_profile_photos
TO caresync_basic_app;

-- 0038 is a globally readable but trigger-owned catalog invalidation stream.
-- Keep this capability-gated for legacy pre-0038 databases and metadata-only
-- development/test fixtures; it remains part of the reviewed retained chain.
DO $public_job_catalog_grant$
BEGIN
    -- The release marker is non-domain metadata. Its unconditional read makes
    -- staged 0037 absence distinguishable from a damaged 0038 installation.
    REVOKE ALL ON TABLE public.alembic_version
    FROM PUBLIC, caresync_basic_app;
    GRANT SELECT ON TABLE public.alembic_version
    TO caresync_basic_app;
    IF pg_catalog.to_regclass('public.public_job_catalog_events') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.public_job_catalog_events
        FROM PUBLIC, caresync_basic_app;
        GRANT SELECT ON TABLE public.public_job_catalog_events
        TO caresync_basic_app;
    END IF;
END
$public_job_catalog_grant$;

-- 0039 is the current reviewed retained release. If any admissions relation is
-- present, the complete six-table boundary must be present before least runtime
-- grants are reconstructed.
DO $admissions_decision_spine_grant$
DECLARE
    present_count integer;
BEGIN
    SELECT count(*) INTO present_count
    FROM pg_catalog.unnest(ARRAY[
      'admission_applications',
      'admission_application_preferences',
      'admission_waitlist_entries',
      'admission_offers',
      'admission_conversion_links',
      'admission_application_events'
    ]::text[]) AS expected(name)
    WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL;

    IF present_count=0 THEN
        RETURN;
    END IF;
    IF present_count<>6 THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0039 admissions decision spine';
    END IF;

    REVOKE ALL ON TABLE
      public.admission_applications,
      public.admission_application_preferences,
      public.admission_waitlist_entries,
      public.admission_offers,
      public.admission_conversion_links,
      public.admission_application_events
    FROM PUBLIC, caresync_basic_app;
    GRANT SELECT, INSERT ON TABLE
      public.admission_applications,
      public.admission_application_preferences,
      public.admission_waitlist_entries,
      public.admission_offers,
      public.admission_conversion_links,
      public.admission_application_events
    TO caresync_basic_app;
    GRANT UPDATE (
      status,
      version,
      child_first_name,
      child_last_name,
      child_normalized_name,
      child_date_of_birth,
      contact_first_name,
      contact_last_name,
      contact_relationship,
      contact_email,
      contact_normalized_email,
      contact_telephone,
      contact_normalized_telephone,
      internal_note,
      updated_by_user_id,
      last_operation_id,
      submitted_at,
      review_started_at,
      terminal_at,
      updated_at
    ) ON TABLE public.admission_applications
    TO caresync_basic_app;
    GRANT UPDATE (
      current_rank,
      current_lane_key,
      retired_by_user_id,
      retired_operation_id,
      retired_at
    ) ON TABLE public.admission_application_preferences
    TO caresync_basic_app;
    GRANT UPDATE (
      current_application_id,
      status,
      version,
      closure_reason,
      updated_by_user_id,
      last_operation_id,
      closed_at,
      updated_at
    ) ON TABLE public.admission_waitlist_entries
    TO caresync_basic_app;
    GRANT UPDATE (
      open_application_id,
      status,
      version,
      updated_by_user_id,
      last_operation_id,
      withdrawn_at,
      declined_at,
      accepted_at,
      updated_at
    ) ON TABLE public.admission_offers
    TO caresync_basic_app;

    IF EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'admission_applications',
        'admission_application_preferences',
        'admission_waitlist_entries',
        'admission_offers',
        'admission_conversion_links',
        'admission_application_events'
      ]::text[]) AS expected(name)
      JOIN pg_catalog.pg_class AS relation
        ON relation.oid=pg_catalog.to_regclass('public.' || expected.name)
      WHERE NOT relation.relrowsecurity OR NOT relation.relforcerowsecurity
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'admission_applications',
        'admission_application_preferences',
        'admission_waitlist_entries',
        'admission_offers',
        'admission_conversion_links',
        'admission_application_events'
      ]::text[]) AS expected(name)
      WHERE pg_catalog.has_table_privilege(
              'caresync_basic_app',
              pg_catalog.to_regclass('public.' || expected.name),
              'DELETE, TRUNCATE, REFERENCES, TRIGGER'
            )
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'admission_applications',
        'admission_application_preferences',
        'admission_waitlist_entries',
        'admission_offers',
        'admission_conversion_links',
        'admission_application_events'
      ]::text[]) AS expected(name)
      WHERE pg_catalog.has_table_privilege(
              'caresync_basic_app',
              pg_catalog.to_regclass('public.' || expected.name),
              'UPDATE'
            )
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'admission_applications',
        'admission_application_preferences',
        'admission_waitlist_entries',
        'admission_offers',
        'admission_conversion_links',
        'admission_application_events'
      ]::text[]) AS expected(name)
      WHERE NOT pg_catalog.has_table_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.name),
                  'SELECT'
                )
         OR NOT pg_catalog.has_table_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.name),
                  'INSERT'
                )
    ) OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('admission_applications', 'status'),
        ('admission_applications', 'version'),
        ('admission_applications', 'child_first_name'),
        ('admission_applications', 'child_last_name'),
        ('admission_applications', 'child_normalized_name'),
        ('admission_applications', 'child_date_of_birth'),
        ('admission_applications', 'contact_first_name'),
        ('admission_applications', 'contact_last_name'),
        ('admission_applications', 'contact_relationship'),
        ('admission_applications', 'contact_email'),
        ('admission_applications', 'contact_normalized_email'),
        ('admission_applications', 'contact_telephone'),
        ('admission_applications', 'contact_normalized_telephone'),
        ('admission_applications', 'internal_note'),
        ('admission_applications', 'updated_by_user_id'),
        ('admission_applications', 'last_operation_id'),
        ('admission_applications', 'submitted_at'),
        ('admission_applications', 'review_started_at'),
        ('admission_applications', 'terminal_at'),
        ('admission_applications', 'updated_at'),
        ('admission_application_preferences', 'current_rank'),
        ('admission_application_preferences', 'current_lane_key'),
        ('admission_application_preferences', 'retired_by_user_id'),
        ('admission_application_preferences', 'retired_operation_id'),
        ('admission_application_preferences', 'retired_at'),
        ('admission_waitlist_entries', 'current_application_id'),
        ('admission_waitlist_entries', 'status'),
        ('admission_waitlist_entries', 'version'),
        ('admission_waitlist_entries', 'closure_reason'),
        ('admission_waitlist_entries', 'updated_by_user_id'),
        ('admission_waitlist_entries', 'last_operation_id'),
        ('admission_waitlist_entries', 'closed_at'),
        ('admission_waitlist_entries', 'updated_at'),
        ('admission_offers', 'open_application_id'),
        ('admission_offers', 'status'),
        ('admission_offers', 'version'),
        ('admission_offers', 'updated_by_user_id'),
        ('admission_offers', 'last_operation_id'),
        ('admission_offers', 'withdrawn_at'),
        ('admission_offers', 'declined_at'),
        ('admission_offers', 'accepted_at'),
        ('admission_offers', 'updated_at')
      ) AS expected(table_name, column_name)
      WHERE NOT pg_catalog.has_column_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.table_name),
                  expected.column_name,
                  'UPDATE'
                )
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'admission_applications',
        'admission_application_preferences',
        'admission_waitlist_entries',
        'admission_offers',
        'admission_conversion_links',
        'admission_application_events'
      ]::text[]) AS expected_table(name)
      JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid=pg_catalog.to_regclass(
             'public.' || expected_table.name
           )
       AND attribute.attnum>0
       AND NOT attribute.attisdropped
      WHERE pg_catalog.has_column_privilege(
              'caresync_basic_app',
              attribute.attrelid,
              attribute.attnum,
              'UPDATE'
            )
        AND NOT EXISTS (
          SELECT 1
          FROM (VALUES
            ('admission_applications', 'status'),
            ('admission_applications', 'version'),
            ('admission_applications', 'child_first_name'),
            ('admission_applications', 'child_last_name'),
            ('admission_applications', 'child_normalized_name'),
            ('admission_applications', 'child_date_of_birth'),
            ('admission_applications', 'contact_first_name'),
            ('admission_applications', 'contact_last_name'),
            ('admission_applications', 'contact_relationship'),
            ('admission_applications', 'contact_email'),
            ('admission_applications', 'contact_normalized_email'),
            ('admission_applications', 'contact_telephone'),
            ('admission_applications', 'contact_normalized_telephone'),
            ('admission_applications', 'internal_note'),
            ('admission_applications', 'updated_by_user_id'),
            ('admission_applications', 'last_operation_id'),
            ('admission_applications', 'submitted_at'),
            ('admission_applications', 'review_started_at'),
            ('admission_applications', 'terminal_at'),
            ('admission_applications', 'updated_at'),
            ('admission_application_preferences', 'current_rank'),
            ('admission_application_preferences', 'current_lane_key'),
            ('admission_application_preferences', 'retired_by_user_id'),
            ('admission_application_preferences', 'retired_operation_id'),
            ('admission_application_preferences', 'retired_at'),
            ('admission_waitlist_entries', 'current_application_id'),
            ('admission_waitlist_entries', 'status'),
            ('admission_waitlist_entries', 'version'),
            ('admission_waitlist_entries', 'closure_reason'),
            ('admission_waitlist_entries', 'updated_by_user_id'),
            ('admission_waitlist_entries', 'last_operation_id'),
            ('admission_waitlist_entries', 'closed_at'),
            ('admission_waitlist_entries', 'updated_at'),
            ('admission_offers', 'open_application_id'),
            ('admission_offers', 'status'),
            ('admission_offers', 'version'),
            ('admission_offers', 'updated_by_user_id'),
            ('admission_offers', 'last_operation_id'),
            ('admission_offers', 'withdrawn_at'),
            ('admission_offers', 'declined_at'),
            ('admission_offers', 'accepted_at'),
            ('admission_offers', 'updated_at')
          ) AS expected_column(table_name, column_name)
          WHERE expected_column.table_name=expected_table.name
            AND expected_column.column_name=attribute.attname
        )
    ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the 0039 admissions privilege audit';
    END IF;
END
$admissions_decision_spine_grant$;

-- 0041 exposes RLS-filtered reads and append-only command records.  Mutable
-- heads receive only the terminal columns used by the server command path;
-- neither table-level UPDATE nor DELETE authority is granted.
DO $live_room_presence_runtime_grants$
DECLARE
    present_count integer;
BEGIN
    SELECT count(*) INTO present_count
    FROM pg_catalog.unnest(ARRAY[
      'staff_room_presence_sessions',
      'staff_room_presence_events',
      'room_operational_exception_heads',
      'room_operational_exception_events'
    ]::text[]) AS expected(name)
    WHERE pg_catalog.to_regclass('public.' || expected.name) IS NOT NULL;

    IF present_count=0 THEN
        RETURN;
    END IF;
    IF present_count<>4 THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0041 live room-presence boundary';
    END IF;

    REVOKE ALL PRIVILEGES ON TABLE
      public.staff_room_presence_sessions,
      public.staff_room_presence_events,
      public.room_operational_exception_heads,
      public.room_operational_exception_events
    FROM PUBLIC, caresync_basic_app;
    GRANT SELECT, INSERT ON TABLE
      public.staff_room_presence_sessions,
      public.staff_room_presence_events,
      public.room_operational_exception_heads,
      public.room_operational_exception_events
    TO caresync_basic_app;
    GRANT UPDATE (
      ended_at,
      end_reason,
      end_operation_id,
      ended_by_user_id,
      version,
      updated_at
    ) ON TABLE public.staff_room_presence_sessions
    TO caresync_basic_app;
    GRANT UPDATE (
      state,
      current_fingerprint_sha256,
      current_evidence,
      last_changed_at,
      acknowledged_at,
      acknowledged_by_user_id,
      acknowledgement_reason,
      resolved_at,
      version,
      updated_at
    ) ON TABLE public.room_operational_exception_heads
    TO caresync_basic_app;

    IF EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'staff_room_presence_sessions',
        'staff_room_presence_events',
        'room_operational_exception_heads',
        'room_operational_exception_events'
      ]::text[]) AS expected(name)
      WHERE NOT pg_catalog.has_table_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.name),
                  'SELECT'
                )
         OR NOT pg_catalog.has_table_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.name),
                  'INSERT'
                )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app',
              pg_catalog.to_regclass('public.' || expected.name),
              'UPDATE'
            )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app',
              pg_catalog.to_regclass('public.' || expected.name),
              'DELETE, TRUNCATE, REFERENCES, TRIGGER'
            )
         OR EXISTS (
              SELECT 1
              FROM pg_catalog.pg_class AS relation
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                COALESCE(
                  relation.relacl,
                  pg_catalog.acldefault('r',relation.relowner)
                )
              ) AS privilege
              WHERE relation.oid=pg_catalog.to_regclass(
                      'public.' || expected.name
                    )
                AND privilege.grantee=0
            )
    ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the 0041 room-presence table privilege audit';
    END IF;

    IF 16<>(
      SELECT count(*)
      FROM information_schema.column_privileges AS privilege
      WHERE privilege.table_schema='public'
        AND privilege.grantee='caresync_basic_app'
        AND privilege.privilege_type='UPDATE'
        AND privilege.table_name IN (
          'staff_room_presence_sessions',
          'staff_room_presence_events',
          'room_operational_exception_heads',
          'room_operational_exception_events'
        )
    ) OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('staff_room_presence_sessions','ended_at'),
        ('staff_room_presence_sessions','end_reason'),
        ('staff_room_presence_sessions','end_operation_id'),
        ('staff_room_presence_sessions','ended_by_user_id'),
        ('staff_room_presence_sessions','version'),
        ('staff_room_presence_sessions','updated_at'),
        ('room_operational_exception_heads','state'),
        ('room_operational_exception_heads','current_fingerprint_sha256'),
        ('room_operational_exception_heads','current_evidence'),
        ('room_operational_exception_heads','last_changed_at'),
        ('room_operational_exception_heads','acknowledged_at'),
        ('room_operational_exception_heads','acknowledged_by_user_id'),
        ('room_operational_exception_heads','acknowledgement_reason'),
        ('room_operational_exception_heads','resolved_at'),
        ('room_operational_exception_heads','version'),
        ('room_operational_exception_heads','updated_at')
      ) AS expected(table_name,column_name)
      WHERE NOT pg_catalog.has_column_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regclass('public.' || expected.table_name),
                  expected.column_name,
                  'UPDATE'
                )
    ) OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(ARRAY[
        'staff_room_presence_sessions',
        'staff_room_presence_events',
        'room_operational_exception_heads',
        'room_operational_exception_events'
      ]::text[]) AS expected_table(name)
      JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid=pg_catalog.to_regclass(
             'public.' || expected_table.name
           )
       AND attribute.attnum>0
       AND NOT attribute.attisdropped
      WHERE pg_catalog.has_column_privilege(
              'caresync_basic_app',
              attribute.attrelid,
              attribute.attnum,
              'UPDATE'
            )
        AND NOT EXISTS (
          SELECT 1
          FROM (VALUES
            ('staff_room_presence_sessions','ended_at'),
            ('staff_room_presence_sessions','end_reason'),
            ('staff_room_presence_sessions','end_operation_id'),
            ('staff_room_presence_sessions','ended_by_user_id'),
            ('staff_room_presence_sessions','version'),
            ('staff_room_presence_sessions','updated_at'),
            ('room_operational_exception_heads','state'),
            ('room_operational_exception_heads','current_fingerprint_sha256'),
            ('room_operational_exception_heads','current_evidence'),
            ('room_operational_exception_heads','last_changed_at'),
            ('room_operational_exception_heads','acknowledged_at'),
            ('room_operational_exception_heads','acknowledged_by_user_id'),
            ('room_operational_exception_heads','acknowledgement_reason'),
            ('room_operational_exception_heads','resolved_at'),
            ('room_operational_exception_heads','version'),
            ('room_operational_exception_heads','updated_at')
          ) AS expected_column(table_name,column_name)
          WHERE expected_column.table_name=expected_table.name
            AND expected_column.column_name=attribute.attname
        )
    ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the exact 0041 UPDATE-column audit';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM pg_catalog.pg_proc AS procedure
      CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(
          procedure.proacl,
          pg_catalog.acldefault('f',procedure.proowner)
        )
      ) AS privilege
      WHERE procedure.oid IN (
        pg_catalog.to_regprocedure(
          'public.caresync_0041_presence_row_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_event_immutable_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_presence_event_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_presence_bundle_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_exception_head_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_exception_event_guard()'
        ),
        pg_catalog.to_regprocedure(
          'public.caresync_0041_exception_bundle_guard()'
        )
      )
        AND privilege.privilege_type='EXECUTE'
        AND privilege.grantee IN (
          0::oid,
          pg_catalog.to_regrole('caresync_basic_app')
        )
    ) THEN
        RAISE EXCEPTION
          '0041 trigger-only guard functions retain direct execution authority';
    END IF;
END
$live_room_presence_runtime_grants$;

DO $public_job_catalog_audit$
DECLARE
    catalog_oid oid := pg_catalog.to_regclass(
        'public.public_job_catalog_events'
    );
    writer_oid oid := pg_catalog.to_regprocedure(
        'public.caresync_public_job_catalog_from_realtime()'
    );
    version_oid oid := pg_catalog.to_regclass('public.alembic_version');
    runtime_oid oid := (
        SELECT role.oid
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname='caresync_basic_app'
    );
    catalog_owner oid;
    writer_owner oid;
    rls_enabled boolean;
    rls_forced boolean;
    writer_is_definer boolean;
    writer_config text[];
BEGIN
    IF version_oid IS NULL OR runtime_oid IS NULL
       OR NOT pg_catalog.has_table_privilege(
            'caresync_basic_app',version_oid,'SELECT'
          )
       OR pg_catalog.has_table_privilege(
            'caresync_basic_app',version_oid,
            'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
          )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.aclexplode(
              COALESCE(
                (SELECT relation.relacl
                 FROM pg_catalog.pg_class AS relation
                 WHERE relation.oid=version_oid),
                pg_catalog.acldefault(
                  'r',
                  (SELECT relation.relowner
                   FROM pg_catalog.pg_class AS relation
                   WHERE relation.oid=version_oid)
                )
              )
            ) AS privilege
            WHERE privilege.grantee=0
               OR privilege.grantee NOT IN (
                    runtime_oid,
                    (SELECT relation.relowner
                     FROM pg_catalog.pg_class AS relation
                     WHERE relation.oid=version_oid)
                  )
               OR (
                    privilege.grantee=runtime_oid
                    AND privilege.privilege_type<>'SELECT'
                  )
          ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the Alembic release-marker privilege audit';
    END IF;

    IF catalog_oid IS NULL
       AND writer_oid IS NULL
       AND NOT EXISTS (
         SELECT 1
         FROM pg_catalog.pg_trigger AS trigger
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid=trigger.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname='public'
           AND relation.relname='realtime_events'
           AND trigger.tgname='realtime_events_public_job_catalog'
           AND NOT trigger.tgisinternal
       ) THEN
        RETURN;
    END IF;

    IF catalog_oid IS NULL OR writer_oid IS NULL THEN
        RAISE EXCEPTION
          'schema-grant repair requires the complete 0038 public job catalog boundary';
    END IF;

    SELECT relation.relowner,relation.relrowsecurity,relation.relforcerowsecurity
      INTO catalog_owner,rls_enabled,rls_forced
    FROM pg_catalog.pg_class AS relation
    WHERE relation.oid=catalog_oid AND relation.relkind='r';

    SELECT procedure.proowner,procedure.prosecdef,procedure.proconfig
      INTO writer_owner,writer_is_definer,writer_config
    FROM pg_catalog.pg_proc AS procedure
    WHERE procedure.oid=writer_oid
      AND procedure.prorettype='pg_catalog.trigger'::pg_catalog.regtype
      AND procedure.pronargs=0;

    IF catalog_owner IS NULL
       OR writer_owner IS NULL
       OR catalog_owner<>writer_owner
       OR writer_owner=(
            SELECT role.oid
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname='caresync_basic_app'
          )
       OR NOT rls_enabled
       OR rls_forced
       OR NOT writer_is_definer
       OR writer_config IS DISTINCT FROM
            ARRAY['search_path=pg_catalog']::text[]
       OR 1 <> (
            SELECT count(*)
            FROM pg_catalog.pg_policy AS policy
            WHERE policy.polrelid=catalog_oid
              AND policy.polname='public_job_catalog_events_public_read'
              AND policy.polcmd='r'
              AND policy.polpermissive
              AND pg_catalog.pg_get_expr(
                    policy.polqual,policy.polrelid,true
                  ) IN ('true','(true)')
              AND policy.polwithcheck IS NULL
          )
       OR 1 <> (
            SELECT count(*)
            FROM pg_catalog.pg_trigger AS trigger
            WHERE trigger.tgrelid=
                    pg_catalog.to_regclass('public.realtime_events')
              AND trigger.tgname='realtime_events_public_job_catalog'
              AND trigger.tgfoid=writer_oid
              AND trigger.tgenabled='O'
              AND NOT trigger.tgisinternal
          )
       OR NOT pg_catalog.has_table_privilege(
            'caresync_basic_app',catalog_oid,'SELECT'
          )
       OR pg_catalog.has_table_privilege(
            'caresync_basic_app',catalog_oid,
            'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
          )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',writer_oid,'EXECUTE'
          )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.aclexplode(
              COALESCE(
                (SELECT relation.relacl
                 FROM pg_catalog.pg_class AS relation
                 WHERE relation.oid=catalog_oid),
                pg_catalog.acldefault('r',catalog_owner)
              )
            ) AS privilege
            WHERE privilege.grantee=0
               OR privilege.grantee NOT IN (catalog_owner,runtime_oid)
               OR (
                    privilege.grantee=runtime_oid
                    AND privilege.privilege_type<>'SELECT'
                  )
          )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.aclexplode(
              COALESCE(
                (SELECT procedure.proacl
                 FROM pg_catalog.pg_proc AS procedure
                 WHERE procedure.oid=writer_oid),
                pg_catalog.acldefault('f',writer_owner)
              )
            ) AS privilege
            WHERE privilege.grantee=0
               OR privilege.grantee<>writer_owner
               OR privilege.privilege_type<>'EXECUTE'
          ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the 0038 public job catalog privilege audit';
    END IF;
END
$public_job_catalog_audit$;

-- These ledgers are append-only for the application role.
GRANT SELECT, INSERT ON TABLE
    public.attendance_events,
    public.daily_care_record_events,
    public.medication_plan_events,
    public.medication_administration_events,
    public.incident_record_events,
    public.audit_events,
    public.ats_events,
    public.staff_shift_events,
    public.staff_scheduled_shift_events,
    public.staff_workforce_events,
    public.childcare_command_receipts,
    public.childcare_command_claims,
    public.childcare_command_reconciliation_proofs,
    public.realtime_events,
    public.user_realtime_events
TO caresync_basic_app;

-- 0030 is capability-gated so this same bootstrap remains safe on retained
-- 0028. No grant below creates operational child-transport authority.
DO $staff_screening_grants$
BEGIN
    IF pg_catalog.to_regclass('public.ats_job_screening_terms') IS NOT NULL THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE
            public.ats_job_screening_terms,
            public.marketplace_screening_profiles,
            public.staff_screening_documents,
            public.staff_screening_application_shares
        TO caresync_basic_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
            public.marketplace_job_screening_terms
        TO caresync_basic_app;
        GRANT SELECT, INSERT ON TABLE
            public.ats_application_screening_snapshots,
            public.ats_offer_screening_terms,
            public.staff_screening_document_versions,
            public.staff_screening_candidate_confirmations,
            public.staff_screening_employer_reviews,
            public.ats_offer_acknowledgments
        TO caresync_basic_app;
    END IF;
END
$staff_screening_grants$;

-- 0031 exposes read-only, RLS-filtered self/manager projections. No INSERT,
-- UPDATE, DELETE, TRUNCATE, REFERENCES, or TRIGGER authority is granted.
DO $driver_vehicle_registry_grants$
BEGIN
    IF pg_catalog.to_regclass(
         'public.staff_driver_capability_versions'
       ) IS NOT NULL THEN
        GRANT SELECT ON TABLE
            public.staff_driver_capability_versions,
            public.staff_driver_qualification_versions,
            public.staff_driver_authorization_decisions,
            public.staff_driver_readiness_decisions,
            public.transport_vehicles,
            public.transport_vehicle_versions,
            public.transport_vehicle_evidence_versions
        TO caresync_basic_app;
    END IF;
END
$driver_vehicle_registry_grants$;

-- 0033 exposes only RLS-filtered reads and append-only command effects.  The
-- migration-owner-only source attestation, unified terminal slot, reversal
-- placeholder, and role-permission backup never receive runtime INSERT.
DO $billing_ledger_grants$
BEGIN
    IF pg_catalog.to_regclass('public.billing_accounts') IS NOT NULL THEN
        GRANT SELECT ON TABLE
            public.billing_sandbox_source_attestations,
            public.billing_command_preparations,
            public.billing_command_terminals,
            public.billing_accounts,
            public.billing_account_payer_versions,
            public.billing_rate_plans,
            public.billing_rate_plan_versions,
            public.billing_agreements,
            public.billing_agreement_versions,
            public.billing_invoices,
            public.billing_invoice_lines,
            public.billing_payments,
            public.billing_allocations,
            public.billing_credits,
            public.billing_journal_entries,
            public.billing_journal_lines,
            public.billing_reversals,
            public.billing_command_receipts,
            public.billing_command_claims
        TO caresync_basic_app;
        GRANT INSERT ON TABLE
            public.billing_command_preparations,
            public.billing_accounts,
            public.billing_account_payer_versions,
            public.billing_rate_plans,
            public.billing_rate_plan_versions,
            public.billing_agreements,
            public.billing_agreement_versions,
            public.billing_invoices,
            public.billing_invoice_lines,
            public.billing_payments,
            public.billing_allocations,
            public.billing_credits,
            public.billing_journal_entries,
            public.billing_journal_lines,
            public.billing_command_receipts,
            public.billing_command_claims
        TO caresync_basic_app;
        REVOKE ALL PRIVILEGES ON TABLE
            public.billing_0033_role_permission_backups
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$billing_ledger_grants$;

-- 0036 grants only leadership-RLS-filtered activation SELECT, owner-filtered
-- activation INSERT, and the invoker authorization view. Manual billing never
-- gains UPDATE, DELETE, processor, delivery, or money-movement authority.
DO $billing_manual_grants$
BEGIN
    IF pg_catalog.to_regclass('public.billing_manual_activations') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.billing_manual_activations,
            public.billing_source_authorizations_0036
        FROM PUBLIC, caresync_basic_app;
        GRANT SELECT,INSERT ON TABLE
            public.billing_manual_activations
        TO caresync_basic_app;
        GRANT SELECT ON TABLE
            public.billing_source_authorizations_0036
        TO caresync_basic_app;
        REVOKE ALL PRIVILEGES ON FUNCTION
            public.caresync_0036_bundle_validate(),
            public.caresync_0036_manual_activation_guard(),
            public.caresync_0036_manual_activation_immutable()
        FROM PUBLIC, caresync_basic_app;
    END IF;
END
$billing_manual_grants$;

-- Internal SECURITY DEFINER state receives no direct runtime privileges.
-- Sequence USAGE is mutation authority (nextval), so only the three sequences
-- required by intended append-only inserts are exposed; UPDATE is never granted.
GRANT USAGE, SELECT ON SEQUENCE
    public.ats_events_sequence_id_seq,
    public.realtime_events_sequence_id_seq,
    public.user_realtime_events_sequence_id_seq
TO caresync_basic_app;

DO $staff_screening_privilege_audit$
BEGIN
    IF pg_catalog.to_regclass('public.ats_job_screening_terms') IS NOT NULL AND (
         EXISTS (
           WITH expected(relname,can_update,can_delete) AS (VALUES
             ('ats_job_screening_terms',true,false),
             ('marketplace_job_screening_terms',true,true),
             ('marketplace_screening_profiles',true,false),
             ('staff_screening_documents',true,false),
             ('staff_screening_application_shares',true,false),
             ('ats_application_screening_snapshots',false,false),
             ('ats_offer_screening_terms',false,false),
             ('staff_screening_document_versions',false,false),
             ('staff_screening_candidate_confirmations',false,false),
             ('staff_screening_employer_reviews',false,false),
             ('ats_offer_acknowledgments',false,false)
           )
           SELECT 1 FROM expected
           LEFT JOIN pg_catalog.pg_class AS relation
             ON relation.oid=pg_catalog.to_regclass('public.' || expected.relname)
           WHERE relation.oid IS NULL
              OR NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'SELECT'
                 )
              OR NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'INSERT'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'UPDATE'
                 ) IS DISTINCT FROM expected.can_update
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'DELETE'
                 ) IS DISTINCT FROM expected.can_delete
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'TRUNCATE'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'REFERENCES'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'TRIGGER'
                 )
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'sync_marketplace_job_screening_from_terms()',
             'sync_marketplace_job_screening_from_listing()',
             'caresync_0030_immutable_fact()','caresync_0030_coverage_guard()',
             'caresync_0030_snapshot_guard()','caresync_0030_share_insert_guard()',
             'caresync_0030_review_insert_guard()','caresync_0030_document_guard()',
             'caresync_0030_offer_terms_insert_guard()',
             'caresync_0030_offer_terms_guard()','caresync_0030_share_guard()',
             'caresync_0030_offer_ack_guard()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=
             pg_catalog.to_regprocedure('public.' || expected.signature)
           WHERE pg_catalog.has_function_privilege(
                   'caresync_basic_app',procedure.oid,'EXECUTE'
                 )
              OR EXISTS (
                   SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
                     procedure.proacl,
                     pg_catalog.acldefault('f',procedure.proowner)
                   )) AS privilege
                   WHERE privilege.grantee=0
                     AND privilege.privilege_type='EXECUTE'
                 )
         )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the 0030 staff-screening privilege audit';
    END IF;
END
$staff_screening_privilege_audit$;

DO $driver_vehicle_registry_privilege_audit$
BEGIN
    IF pg_catalog.to_regclass(
         'public.staff_driver_capability_versions'
       ) IS NOT NULL AND (
         EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'staff_driver_capability_versions',
             'staff_driver_qualification_versions',
             'staff_driver_authorization_decisions',
             'staff_driver_readiness_decisions','transport_vehicles',
             'transport_vehicle_versions','transport_vehicle_evidence_versions'
           ]::text[]) AS expected(relname)
           JOIN pg_catalog.pg_class AS relation
             ON relation.oid=pg_catalog.to_regclass('public.' || expected.relname)
           WHERE NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'SELECT'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'INSERT'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'UPDATE'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'DELETE'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'TRUNCATE'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'REFERENCES'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'TRIGGER'
                 )
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'caresync_0031_immutable_fact()','caresync_0031_capability_guard()',
             'caresync_0031_qualification_guard()',
             'caresync_0031_authorization_guard()','caresync_0031_vehicle_guard()',
             'caresync_0031_vehicle_version_guard()',
             'caresync_0031_vehicle_evidence_guard()',
             'caresync_0031_readiness_guard()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=
             pg_catalog.to_regprocedure('public.' || expected.signature)
           WHERE pg_catalog.has_function_privilege(
                   'caresync_basic_app',procedure.oid,'EXECUTE'
                 )
              OR EXISTS (
                   SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
                     procedure.proacl,
                     pg_catalog.acldefault('f',procedure.proowner)
                   )) AS privilege
                   WHERE privilege.grantee=0
                     AND privilege.privilege_type='EXECUTE'
                 )
         )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the 0031 registry privilege audit';
    END IF;
END
$driver_vehicle_registry_privilege_audit$;

DO $billing_ledger_privilege_audit$
BEGIN
    IF pg_catalog.to_regclass('public.billing_accounts') IS NOT NULL AND (
         EXISTS (
           WITH expected(relname,can_insert) AS (VALUES
             ('billing_sandbox_source_attestations',false),
             ('billing_command_preparations',true),
             ('billing_command_terminals',false),
             ('billing_accounts',true),
             ('billing_account_payer_versions',true),
             ('billing_rate_plans',true),
             ('billing_rate_plan_versions',true),
             ('billing_agreements',true),
             ('billing_agreement_versions',true),
             ('billing_invoices',true),
             ('billing_invoice_lines',true),
             ('billing_payments',true),
             ('billing_allocations',true),
             ('billing_credits',true),
             ('billing_journal_entries',true),
             ('billing_journal_lines',true),
             ('billing_reversals',false),
             ('billing_command_receipts',true),
             ('billing_command_claims',true)
           )
           SELECT 1 FROM expected
           LEFT JOIN pg_catalog.pg_class AS relation
             ON relation.oid=pg_catalog.to_regclass('public.' || expected.relname)
           WHERE relation.oid IS NULL
              OR NOT pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'SELECT'
                 )
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,'INSERT'
                 ) IS DISTINCT FROM expected.can_insert
              OR pg_catalog.has_table_privilege(
                   'caresync_basic_app',relation.oid,
                   'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
                 )
              OR pg_catalog.has_any_column_privilege(
                   'caresync_basic_app',relation.oid,'UPDATE,REFERENCES'
                 )
              OR (
                   NOT expected.can_insert AND pg_catalog.has_any_column_privilege(
                     'caresync_basic_app',relation.oid,'INSERT'
                   )
                 )
         )
         OR pg_catalog.has_table_privilege(
              'caresync_basic_app','public.billing_0033_role_permission_backups',
              'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
            )
         OR pg_catalog.has_any_column_privilege(
              'caresync_basic_app','public.billing_0033_role_permission_backups',
              'SELECT,INSERT,UPDATE,REFERENCES'
            )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'caresync_0033_immutable_fact()',
             'caresync_0033_role_permission_guard()',
             'caresync_0033_source_attestation_guard()',
             'caresync_0033_attested_source_immutable()',
             'caresync_0033_actor_guard()','caresync_0033_version_guard()',
             'caresync_0033_invoice_line_guard()',
             'caresync_0033_allocation_guard()',
             'caresync_0033_credit_guard()',
             'caresync_0033_journal_sequence_guard()',
             'caresync_0033_journal_validate()',
             'caresync_0033_effect_open_guard()',
             'caresync_0033_bundle_validate()',
             'caresync_0033_receipt_guard()',
             'caresync_0033_claim_guard()',
             'caresync_0033_terminal_claim()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure
             ON procedure.oid=pg_catalog.to_regprocedure(
                  'public.' || expected.signature
                )
           WHERE pg_catalog.has_function_privilege(
                   'caresync_basic_app',procedure.oid,'EXECUTE'
                 )
         )
       ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the 0033 billing-ledger privilege audit';
    END IF;
END
$billing_ledger_privilege_audit$;

DO $billing_manual_privilege_audit$
BEGIN
    IF pg_catalog.to_regclass('public.billing_manual_activations') IS NOT NULL AND (
         NOT pg_catalog.has_table_privilege(
           'caresync_basic_app','public.billing_manual_activations','SELECT,INSERT'
         )
         OR pg_catalog.has_table_privilege(
           'caresync_basic_app','public.billing_manual_activations',
           'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
         )
         OR pg_catalog.has_any_column_privilege(
           'caresync_basic_app','public.billing_manual_activations',
           'UPDATE,REFERENCES'
         )
         OR NOT pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.billing_source_authorizations_0036','SELECT'
         )
         OR pg_catalog.has_table_privilege(
           'caresync_basic_app',
           'public.billing_source_authorizations_0036',
           'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
         )
         OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(ARRAY[
             'caresync_0036_bundle_validate()',
             'caresync_0036_manual_activation_guard()',
             'caresync_0036_manual_activation_immutable()'
           ]::text[]) AS expected(signature)
           JOIN pg_catalog.pg_proc AS procedure
             ON procedure.oid=pg_catalog.to_regprocedure(
                  'public.' || expected.signature
                )
           WHERE pg_catalog.has_function_privilege(
                   'caresync_basic_app',procedure.oid,'EXECUTE'
                 )
              OR EXISTS (
                   SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
                     procedure.proacl,
                     pg_catalog.acldefault('f',procedure.proowner)
                   )) privilege
                   WHERE privilege.grantee=0
                     AND privilege.privilege_type='EXECUTE'
                 )
         )
       ) THEN
        RAISE EXCEPTION
          'caresync_basic_app failed the 0036 manual-billing privilege audit';
    END IF;
END
$billing_manual_privilege_audit$;

-- Complete-or-fail 0032 attestation.  This is deliberately broader than the
-- grant statements above: it proves role topology, object ownership, function
-- identity/ACL, table and schema ACLs, RLS writer policies, enabled triggers,
-- and the required immutable schema before startup can expose the capability.
DO $transport_command_runtime_audit$
DECLARE
    owner_role record;
    ingest_role record;
    writer record;
    current_database_oid oid;
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NULL THEN
        RETURN;
    END IF;

    SELECT oid INTO STRICT current_database_oid FROM pg_catalog.pg_database
    WHERE datname=pg_catalog.current_database();
    SELECT role.* INTO STRICT owner_role FROM pg_catalog.pg_roles AS role
    WHERE role.rolname='caresync_transport_command_owner';
    SELECT role.* INTO STRICT ingest_role FROM pg_catalog.pg_roles AS role
    WHERE role.rolname='caresync_transport_evidence_ingest';
    SELECT procedure.*,pg_catalog.pg_get_userbyid(procedure.proowner) AS owner_name
      INTO STRICT writer
    FROM pg_catalog.pg_proc AS procedure
    WHERE procedure.oid=pg_catalog.to_regprocedure(
      'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
    );

    IF owner_role.rolcanlogin OR owner_role.rolsuper OR owner_role.rolbypassrls
       OR owner_role.rolinherit OR owner_role.rolcreaterole OR owner_role.rolcreatedb
       OR owner_role.rolreplication OR owner_role.rolconfig IS NOT NULL
       OR NOT ingest_role.rolcanlogin OR ingest_role.rolsuper OR ingest_role.rolbypassrls
       OR ingest_role.rolinherit OR ingest_role.rolcreaterole OR ingest_role.rolcreatedb
       OR ingest_role.rolreplication
       OR pg_catalog.array_length(ingest_role.rolconfig,1) IS DISTINCT FROM 1
       OR pg_catalog.replace(ingest_role.rolconfig[1],' ','')<>
          'search_path=public,pg_catalog'
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_auth_members AS edge
         WHERE edge.member IN (owner_role.oid,ingest_role.oid)
            OR edge.roleid IN (owner_role.oid,ingest_role.oid)
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_db_role_setting AS setting
         WHERE setting.setrole IN (owner_role.oid,ingest_role.oid)
           AND setting.setdatabase<>0
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_shdepend AS dependency
         WHERE dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
           AND dependency.refobjid=ingest_role.oid AND dependency.deptype='o'
       )
       OR 1<>(
         SELECT count(*) FROM pg_catalog.pg_shdepend AS dependency
         WHERE dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
           AND dependency.refobjid=owner_role.oid AND dependency.deptype='o'
           AND dependency.dbid=current_database_oid
           AND dependency.classid='pg_catalog.pg_proc'::pg_catalog.regclass
           AND dependency.objid=writer.oid
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_shdepend AS dependency
         WHERE dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
           AND dependency.refobjid=owner_role.oid AND dependency.deptype='o'
           AND NOT (
             dependency.dbid=current_database_oid
             AND dependency.classid='pg_catalog.pg_proc'::pg_catalog.regclass
             AND dependency.objid=writer.oid
           )
       )
       OR writer.owner_name<>'caresync_transport_command_owner'
       OR NOT writer.prosecdef OR writer.provolatile<>'v'
       OR pg_catalog.array_length(writer.proconfig,1) IS DISTINCT FROM 1
       OR pg_catalog.replace(writer.proconfig[1],' ','')<>
          'search_path=pg_catalog,public'
       OR EXISTS (
         SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
           writer.proacl,pg_catalog.acldefault('f',writer.proowner)
         )) AS privilege
         WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE'
       )
       OR NOT pg_catalog.has_function_privilege(
         'caresync_basic_app',writer.oid,'EXECUTE'
       )
       OR NOT pg_catalog.has_function_privilege(
         'caresync_transport_evidence_ingest',writer.oid,'EXECUTE'
       ) THEN
        RAISE EXCEPTION '0032 transport role or repository ownership audit failed';
    END IF;

    IF NOT pg_catalog.has_database_privilege(
         'caresync_transport_evidence_ingest',pg_catalog.current_database(),'CONNECT'
       )
       OR pg_catalog.has_database_privilege(
         'caresync_transport_evidence_ingest',pg_catalog.current_database(),'CREATE'
       )
       OR pg_catalog.has_database_privilege(
         'caresync_transport_evidence_ingest',pg_catalog.current_database(),'TEMPORARY'
       )
       OR pg_catalog.has_database_privilege(
         'caresync_transport_command_owner',pg_catalog.current_database(),'CREATE'
       )
       OR pg_catalog.has_database_privilege(
         'caresync_transport_command_owner',pg_catalog.current_database(),'TEMPORARY'
       )
       OR NOT pg_catalog.has_schema_privilege(
         'caresync_transport_evidence_ingest','public','USAGE'
       )
       OR NOT pg_catalog.has_schema_privilege(
         'caresync_transport_command_owner','public','USAGE'
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_namespace AS namespace
         WHERE namespace.nspname !~ '^pg_'
           AND namespace.nspname<>'information_schema'
           AND (
             pg_catalog.has_schema_privilege(
               'caresync_transport_evidence_ingest',namespace.oid,'CREATE'
             ) OR pg_catalog.has_schema_privilege(
               'caresync_transport_command_owner',namespace.oid,'CREATE'
             ) OR (
               namespace.nspname<>'public' AND (
                 pg_catalog.has_schema_privilege(
                   'caresync_transport_evidence_ingest',namespace.oid,'USAGE'
                 ) OR pg_catalog.has_schema_privilege(
                   'caresync_transport_command_owner',namespace.oid,'USAGE'
                 )
               )
             )
           )
       ) THEN
        RAISE EXCEPTION '0032 transport database or schema ACL audit failed';
    END IF;

    IF EXISTS (
         SELECT 1 FROM pg_catalog.pg_proc AS procedure
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=procedure.pronamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND procedure.oid<>writer.oid
           AND pg_catalog.has_function_privilege(
             'caresync_transport_evidence_ingest',procedure.oid,'EXECUTE'
           )
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_proc AS procedure
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=procedure.pronamespace
         CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(
           procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)
         )) AS privilege
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND privilege.grantee=0 AND privilege.privilege_type='EXECUTE'
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND relation.relkind IN ('r','p') AND (
             pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'SELECT'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'INSERT'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'UPDATE'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'DELETE'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'TRUNCATE'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'REFERENCES'
             ) OR pg_catalog.has_table_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'TRIGGER'
             ) OR pg_catalog.has_any_column_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'SELECT'
             ) OR pg_catalog.has_any_column_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'INSERT'
             ) OR pg_catalog.has_any_column_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'UPDATE'
             ) OR pg_catalog.has_any_column_privilege(
               'caresync_transport_evidence_ingest',relation.oid,'REFERENCES'
             )
           )
       ) OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_class AS sequence
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=sequence.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND sequence.relkind='S' AND (
             pg_catalog.has_sequence_privilege(
               'caresync_transport_evidence_ingest',sequence.oid,'USAGE'
             ) OR pg_catalog.has_sequence_privilege(
               'caresync_transport_evidence_ingest',sequence.oid,'SELECT'
             ) OR pg_catalog.has_sequence_privilege(
               'caresync_transport_evidence_ingest',sequence.oid,'UPDATE'
             )
           )
       ) THEN
        RAISE EXCEPTION '0032 evidence-ingest identity exceeds its repository-only ACL';
    END IF;

    IF EXISTS (
         SELECT 1 FROM pg_catalog.pg_proc AS procedure
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=procedure.pronamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND procedure.oid<>writer.oid
           AND pg_catalog.has_function_privilege(
             'caresync_transport_command_owner',procedure.oid,'EXECUTE'
           )
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND relation.relkind IN ('r','p') AND (
             pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'SELECT'
             ) IS DISTINCT FROM (relation.relname IN (
               'users','organizations','organization_memberships','roles',
               'notification_push_subscriptions','user_notification_preferences',
               'staff_driver_capability_versions','staff_driver_qualification_versions',
               'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
               'transport_vehicles','transport_vehicle_versions',
               'transport_vehicle_evidence_versions','transport_registry_command_receipts',
               'staff_driver_qualification_evidence_objects',
               'staff_driver_qualification_review_decisions',
               'transport_vehicle_evidence_review_decisions',
               'transport_vehicle_evidence_scan_facts'
             ))
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'INSERT'
             ) IS DISTINCT FROM (relation.relname IN (
               'staff_driver_capability_versions','staff_driver_qualification_versions',
               'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
               'transport_vehicles','transport_vehicle_versions',
               'transport_vehicle_evidence_versions','transport_registry_command_receipts',
               'staff_driver_qualification_evidence_objects',
               'staff_driver_qualification_review_decisions',
               'transport_vehicle_evidence_review_decisions',
               'transport_vehicle_evidence_scan_facts','audit_events','user_notifications',
               'realtime_events','user_realtime_events','notification_deliveries'
             ))
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'UPDATE'
             )
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'DELETE'
             )
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'TRUNCATE'
             )
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'REFERENCES'
             )
             OR pg_catalog.has_table_privilege(
               'caresync_transport_command_owner',relation.oid,'TRIGGER'
             )
             OR pg_catalog.has_any_column_privilege(
               'caresync_transport_command_owner',relation.oid,'UPDATE'
             ) IS DISTINCT FROM (relation.relname IN (
               'users','organizations','organization_memberships','roles',
               'staff_driver_capability_versions',
               'staff_driver_qualification_versions',
               'staff_driver_authorization_decisions','transport_vehicles',
               'transport_vehicle_versions','transport_vehicle_evidence_versions'
             ))
           )
       ) OR 13<>(
         SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
         JOIN pg_catalog.pg_class AS relation ON relation.oid=attribute.attrelid
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname='public' AND attribute.attnum>0
           AND NOT attribute.attisdropped
           AND (
             (attribute.attname='id' AND relation.relname IN (
               'users','organizations','organization_memberships','roles',
               'staff_driver_capability_versions',
               'staff_driver_qualification_versions',
               'staff_driver_authorization_decisions','transport_vehicles',
               'transport_vehicle_versions','transport_vehicle_evidence_versions'
             )) OR (relation.relname='transport_vehicles' AND attribute.attname IN (
               'retired_at','retired_by_user_id','retirement_reason_code'
             ))
           ) AND pg_catalog.has_column_privilege(
             'caresync_transport_command_owner',attribute.attrelid,
             attribute.attnum,'UPDATE'
           )
       ) OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_attribute AS attribute
         JOIN pg_catalog.pg_class AS relation ON relation.oid=attribute.attrelid
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND attribute.attnum>0 AND NOT attribute.attisdropped
           AND NOT (
             namespace.nspname='public' AND (
               (attribute.attname='id' AND relation.relname IN (
                 'users','organizations','organization_memberships','roles',
                 'staff_driver_capability_versions',
                 'staff_driver_qualification_versions',
                 'staff_driver_authorization_decisions','transport_vehicles',
                 'transport_vehicle_versions','transport_vehicle_evidence_versions'
               )) OR (relation.relname='transport_vehicles' AND attribute.attname IN (
                 'retired_at','retired_by_user_id','retirement_reason_code'
               ))
             )
           ) AND pg_catalog.has_column_privilege(
             'caresync_transport_command_owner',attribute.attrelid,
             attribute.attnum,'UPDATE'
           )
       ) OR 3<>(
         SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
         WHERE attribute.attnum>0 AND NOT attribute.attisdropped
           AND (
             (attribute.attrelid=pg_catalog.to_regclass('public.user_realtime_events')
               AND attribute.attname='id')
             OR (attribute.attrelid=pg_catalog.to_regclass('public.notification_deliveries')
               AND attribute.attname IN ('notification_id','subscription_id'))
           ) AND pg_catalog.has_column_privilege(
             'caresync_transport_command_owner',attribute.attrelid,
             attribute.attnum,'SELECT'
           )
       ) OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_attribute AS attribute
         JOIN pg_catalog.pg_class AS relation ON relation.oid=attribute.attrelid
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND attribute.attnum>0 AND NOT attribute.attisdropped
           AND NOT pg_catalog.has_table_privilege(
             'caresync_transport_command_owner',relation.oid,'SELECT'
           ) AND NOT (
             namespace.nspname='public' AND (
               (relation.relname='user_realtime_events' AND attribute.attname='id')
               OR (relation.relname='notification_deliveries'
                 AND attribute.attname IN ('notification_id','subscription_id'))
             )
           ) AND pg_catalog.has_column_privilege(
             'caresync_transport_command_owner',attribute.attrelid,
             attribute.attnum,'SELECT'
           )
       ) OR EXISTS (
         SELECT 1 FROM pg_catalog.pg_class AS sequence
         JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=sequence.relnamespace
         WHERE namespace.nspname !~ '^pg_' AND namespace.nspname<>'information_schema'
           AND sequence.relkind='S' AND (
             pg_catalog.has_sequence_privilege(
               'caresync_transport_command_owner',sequence.oid,'USAGE'
             ) IS DISTINCT FROM (
               namespace.nspname='public'
               AND sequence.relname IN (
                 'realtime_events_sequence_id_seq',
                 'user_realtime_events_sequence_id_seq'
               )
             ) OR pg_catalog.has_sequence_privilege(
               'caresync_transport_command_owner',sequence.oid,'SELECT'
             ) OR pg_catalog.has_sequence_privilege(
               'caresync_transport_command_owner',sequence.oid,'UPDATE'
             )
           )
       ) THEN
        RAISE EXCEPTION '0032 command owner exceeds its exact repository ACL';
    END IF;

    IF EXISTS (
         SELECT 1 FROM pg_catalog.unnest(ARRAY[
           'staff_driver_capability_versions','staff_driver_qualification_versions',
           'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
           'transport_vehicles','transport_vehicle_versions',
           'transport_vehicle_evidence_versions','transport_registry_command_receipts',
           'staff_driver_qualification_evidence_objects',
           'staff_driver_qualification_review_decisions',
           'transport_vehicle_evidence_review_decisions',
           'transport_vehicle_evidence_scan_facts'
         ]::text[]) AS expected(name)
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid=pg_catalog.to_regclass('public.' || expected.name)
         WHERE NOT pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'SELECT'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'INSERT'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'UPDATE'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'DELETE'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'TRUNCATE'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'REFERENCES'
               )
            OR pg_catalog.has_table_privilege(
                 'caresync_basic_app',relation.oid,'TRIGGER'
               )
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.unnest(ARRAY[
           'caresync_0032_immutable_fact()',
           'caresync_0032_receipt_guard()',
           'caresync_0032_qualification_evidence_guard()',
           'caresync_0032_qualification_review_guard()',
           'caresync_0032_vehicle_review_guard()',
           'caresync_0032_vehicle_scan_guard()'
         ]::text[]) AS expected(signature)
         WHERE pg_catalog.has_function_privilege(
           'caresync_basic_app',
           pg_catalog.to_regprocedure('public.' || expected.signature),'EXECUTE'
         ) OR pg_catalog.has_function_privilege(
           'caresync_transport_evidence_ingest',
           pg_catalog.to_regprocedure('public.' || expected.signature),'EXECUTE'
         )
       ) THEN
        RAISE EXCEPTION '0032 basic runtime read/DML or guard-function ACL audit failed';
    END IF;

    IF 14<>(
         SELECT count(*) FROM pg_catalog.pg_class AS relation
         WHERE relation.oid IN (
           SELECT pg_catalog.to_regclass('public.' || expected.name)
           FROM pg_catalog.unnest(ARRAY[
             'staff_driver_capability_versions','staff_driver_qualification_versions',
             'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
             'transport_vehicles','transport_vehicle_versions',
             'transport_vehicle_evidence_versions','transport_registry_command_receipts',
             'staff_driver_qualification_evidence_objects',
             'staff_driver_qualification_review_decisions',
             'transport_vehicle_evidence_review_decisions',
             'transport_vehicle_evidence_scan_facts',
             'audit_events','user_notifications'
           ]::text[]) AS expected(name)
         ) AND relation.relrowsecurity AND relation.relforcerowsecurity
       )
       OR EXISTS (
         SELECT 1 FROM pg_catalog.unnest(ARRAY[
           'staff_driver_capability_versions','staff_driver_qualification_versions',
           'staff_driver_authorization_decisions','staff_driver_readiness_decisions',
           'transport_vehicles','transport_vehicle_versions',
           'transport_vehicle_evidence_versions','transport_registry_command_receipts',
           'staff_driver_qualification_evidence_objects',
           'staff_driver_qualification_review_decisions',
           'transport_vehicle_evidence_review_decisions',
           'transport_vehicle_evidence_scan_facts',
           'audit_events','user_notifications'
         ]::text[]) AS expected(name)
         LEFT JOIN pg_catalog.pg_policy AS policy
           ON policy.polrelid=pg_catalog.to_regclass('public.' || expected.name)
          AND policy.polname=expected.name || '_0032_writer'
         WHERE policy.oid IS NULL OR policy.polcmd<>'*'
            OR NOT policy.polpermissive OR policy.polroles<>ARRAY[0::oid]
            OR pg_catalog.regexp_replace(
                 pg_catalog.regexp_replace(
                   pg_catalog.lower(pg_catalog.pg_get_expr(
                     policy.polqual,policy.polrelid
                   )), '::(pg_catalog\.)?name(\[\])?', '', 'g'
                 ), '[[:space:]()]', '', 'g'
               ) IS DISTINCT FROM
                   'current_user=''caresync_transport_command_owner''and'
                   'session_user=anyarray[''caresync_basic_app'','
                   '''caresync_transport_evidence_ingest'']'
            OR pg_catalog.regexp_replace(
                 pg_catalog.regexp_replace(
                   pg_catalog.lower(pg_catalog.pg_get_expr(
                     policy.polwithcheck,policy.polrelid
                   )), '::(pg_catalog\.)?name(\[\])?', '', 'g'
                 ), '[[:space:]()]', '', 'g'
               ) IS DISTINCT FROM
                   'current_user=''caresync_transport_command_owner''and'
                   'session_user=anyarray[''caresync_basic_app'','
                   '''caresync_transport_evidence_ingest'']'
       ) THEN
        RAISE EXCEPTION '0032 RLS writer policy audit failed';
    END IF;

    IF 11<>(
         SELECT count(*) FROM pg_catalog.pg_policy AS policy
         WHERE policy.polrelid IN (
           pg_catalog.to_regclass('public.users'),
           pg_catalog.to_regclass('public.organizations'),
           pg_catalog.to_regclass('public.organization_memberships'),
           pg_catalog.to_regclass('public.roles')
         )
       ) OR EXISTS (
         WITH constants(writer_expression) AS (VALUES (
           'current_user=''caresync_transport_command_owner''and'
           'session_user=anyarray[''caresync_basic_app'','
           '''caresync_transport_evidence_ingest'']'
         )), scopes(relname,scope_expression) AS (VALUES
           ('users',
            'id=nullifcurrent_setting''app.current_user_id''::text,true,''''::text::uuid'),
           ('organizations',
            'id=nullifcurrent_setting''app.current_organization_id''::text,true,''''::text::uuid'),
           ('organization_memberships',
            'organization_id=nullifcurrent_setting'
            '''app.current_organization_id''::text,true,''''::text::uuid'),
           ('roles',
            'organization_id=nullifcurrent_setting'
            '''app.current_organization_id''::text,true,''''::text::uuid')
         ), expected(relname,polname,permissive,using_expression,check_expression) AS (
           SELECT scopes.relname,scopes.relname || '_0032_lock',true,
                  constants.writer_expression || 'and' || scopes.scope_expression,
                  'false'
           FROM scopes CROSS JOIN constants
           UNION ALL
           SELECT scopes.relname,scopes.relname || '_0032_lock_no_mutation',false,
                  'current_user<>''caresync_transport_command_owner''or'
                    || constants.writer_expression || 'and' || scopes.scope_expression,
                  'current_user<>''caresync_transport_command_owner'''
           FROM scopes CROSS JOIN constants
         )
         SELECT 1 FROM expected
         LEFT JOIN pg_catalog.pg_policy AS policy
           ON policy.polrelid=pg_catalog.to_regclass('public.' || expected.relname)
          AND policy.polname=expected.polname
         WHERE policy.oid IS NULL OR policy.polcmd<>'w'
            OR policy.polpermissive IS DISTINCT FROM expected.permissive
            OR policy.polroles<>ARRAY[0::oid]
            OR pg_catalog.regexp_replace(
                 pg_catalog.regexp_replace(
                   pg_catalog.lower(pg_catalog.pg_get_expr(
                     policy.polqual,policy.polrelid
                   )), '::(pg_catalog\.)?name(\[\])?', '', 'g'
                 ), '[[:space:]()]', '', 'g'
               ) IS DISTINCT FROM expected.using_expression
            OR pg_catalog.regexp_replace(
                 pg_catalog.regexp_replace(
                   pg_catalog.lower(pg_catalog.pg_get_expr(
                     policy.polwithcheck,policy.polrelid
                   )), '::(pg_catalog\.)?name(\[\])?', '', 'g'
                 ), '[[:space:]()]', '', 'g'
               ) IS DISTINCT FROM expected.check_expression
       ) THEN
        RAISE EXCEPTION '0032 context row-lock policy audit failed';
    END IF;

    IF EXISTS (
         WITH expected(tgname,relname,proname) AS (VALUES
           ('transport_registry_command_receipts_immutable',
            'transport_registry_command_receipts','caresync_0032_immutable_fact'),
           ('staff_driver_qualification_evidence_objects_immutable',
            'staff_driver_qualification_evidence_objects','caresync_0032_immutable_fact'),
           ('staff_driver_qualification_review_decisions_immutable',
            'staff_driver_qualification_review_decisions','caresync_0032_immutable_fact'),
           ('transport_vehicle_evidence_review_decisions_immutable',
            'transport_vehicle_evidence_review_decisions','caresync_0032_immutable_fact'),
           ('transport_vehicle_evidence_scan_facts_immutable',
            'transport_vehicle_evidence_scan_facts','caresync_0032_immutable_fact'),
           ('transport_registry_receipt_insert_guard',
            'transport_registry_command_receipts','caresync_0032_receipt_guard'),
           ('staff_driver_qualification_evidence_insert_guard',
            'staff_driver_qualification_evidence_objects',
            'caresync_0032_qualification_evidence_guard'),
           ('staff_driver_qualification_review_insert_guard',
            'staff_driver_qualification_review_decisions',
            'caresync_0032_qualification_review_guard'),
           ('transport_vehicle_evidence_review_insert_guard',
            'transport_vehicle_evidence_review_decisions','caresync_0032_vehicle_review_guard'),
           ('transport_vehicle_evidence_scan_insert_guard',
            'transport_vehicle_evidence_scan_facts','caresync_0032_vehicle_scan_guard')
         )
         SELECT 1 FROM expected
         LEFT JOIN pg_catalog.pg_trigger AS trigger
           ON trigger.tgname=expected.tgname AND NOT trigger.tgisinternal
          AND trigger.tgenabled<>'D'
         LEFT JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
         LEFT JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid
         WHERE relation.relname IS DISTINCT FROM expected.relname
            OR procedure.proname IS DISTINCT FROM expected.proname
       ) THEN
        RAISE EXCEPTION '0032 trigger binding audit failed';
    END IF;

    IF EXISTS (
         WITH required(relname,attname) AS (VALUES
           ('transport_registry_command_receipts','client_operation_id'),
           ('transport_registry_command_receipts','request_sha256'),
           ('transport_registry_command_receipts','result_id'),
           ('staff_driver_qualification_evidence_objects','qualification_version_id'),
           ('staff_driver_qualification_evidence_objects','ciphertext_sha256'),
           ('staff_driver_qualification_evidence_objects','scanner_engine'),
           ('staff_driver_qualification_review_decisions','source_qualification_version_id'),
           ('staff_driver_qualification_review_decisions','result_qualification_version_id'),
           ('transport_vehicle_evidence_review_decisions','source_evidence_version_id'),
           ('transport_vehicle_evidence_review_decisions','result_evidence_version_id'),
           ('transport_vehicle_evidence_scan_facts','evidence_version_id'),
           ('transport_vehicle_evidence_scan_facts','scanner_version')
         )
         SELECT 1 FROM required
         LEFT JOIN pg_catalog.pg_attribute AS attribute
           ON attribute.attrelid=pg_catalog.to_regclass('public.' || required.relname)
          AND attribute.attname=required.attname AND attribute.attnum>0
          AND NOT attribute.attisdropped
         WHERE attribute.attnum IS NULL
       ) OR EXISTS (
         SELECT 1 FROM pg_catalog.unnest(ARRAY[
           'ck_transport_registry_receipt_command',
           'ck_transport_registry_receipt_request_sha256',
           'ck_transport_registry_receipt_not_operational',
           'ck_driver_qualification_evidence_content_sha256',
           'ck_driver_qualification_evidence_ciphertext_sha256',
           'ck_driver_qualification_evidence_scan_provenance',
           'ck_driver_qualification_evidence_not_operational',
           'ck_driver_qualification_review_decision',
           'ck_driver_qualification_review_not_operational',
           'ck_vehicle_evidence_review_decision',
           'ck_vehicle_evidence_review_not_operational',
           'ck_vehicle_evidence_scan_clean_only',
           'ck_vehicle_evidence_scan_provenance',
           'ck_vehicle_evidence_scan_not_operational'
         ]::text[]) AS expected(name)
         WHERE NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_constraint AS constraint_record
           WHERE constraint_record.conname=expected.name
         )
       ) THEN
        RAISE EXCEPTION '0032 transport command schema audit failed';
    END IF;
END
$transport_command_runtime_audit$;

-- The repository reaches its public/user realtime outboxes through two
-- SECURITY INVOKER triggers. Their exact bindings, context policies, and
-- privacy-minimized transport branch are part of the 0032 capability.
DO $transport_command_downstream_audit$
DECLARE
    audit_chain record;
    notification_chain record;
    audit_sql text;
    notification_sql text;
    audit_body text;
    notification_body text;
    audit_trigger_sql text;
    notification_trigger_sql text;
BEGIN
    IF pg_catalog.to_regprocedure(
         'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
       ) IS NULL THEN
        RETURN;
    END IF;

    IF 2<>(
      SELECT count(*) FROM pg_catalog.pg_trigger AS trigger
      JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
      JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname='public' AND NOT trigger.tgisinternal
        AND relation.relname IN ('audit_events','user_notifications')
    ) THEN
        RAISE EXCEPTION '0032 downstream trigger set audit failed';
    END IF;

    SELECT trigger.tgenabled,pg_catalog.pg_get_triggerdef(trigger.oid) trigger_definition,
           procedure.oid,procedure.pronamespace,procedure.proowner,procedure.proacl,
           procedure.proname,
           procedure.prosecdef,procedure.provolatile,procedure.proconfig,
           pg_catalog.pg_get_userbyid(procedure.proowner) owner_name,
           pg_catalog.pg_get_function_result(procedure.oid) result_type,
           procedure.prosrc function_source,
           pg_catalog.pg_get_functiondef(procedure.oid) function_definition
      INTO STRICT audit_chain
    FROM pg_catalog.pg_trigger AS trigger
    JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
    JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
    JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid
    WHERE namespace.nspname='public' AND relation.relname='audit_events'
      AND trigger.tgname='audit_events_realtime' AND NOT trigger.tgisinternal;

    SELECT trigger.tgenabled,pg_catalog.pg_get_triggerdef(trigger.oid) trigger_definition,
           procedure.oid,procedure.pronamespace,procedure.proowner,procedure.proacl,
           procedure.proname,
           procedure.prosecdef,procedure.provolatile,procedure.proconfig,
           pg_catalog.pg_get_userbyid(procedure.proowner) owner_name,
           pg_catalog.pg_get_function_result(procedure.oid) result_type,
           procedure.prosrc function_source,
           pg_catalog.pg_get_functiondef(procedure.oid) function_definition
      INTO STRICT notification_chain
    FROM pg_catalog.pg_trigger AS trigger
    JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid
    JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid=relation.relnamespace
    JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid
    WHERE namespace.nspname='public' AND relation.relname='user_notifications'
      AND trigger.tgname='user_notifications_push_realtime'
      AND NOT trigger.tgisinternal;

    audit_sql:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(audit_chain.function_definition),'[[:space:]]','','g'
    ),'"','');
    notification_sql:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(notification_chain.function_definition),'[[:space:]]','','g'
    ),'"','');
    audit_body:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(audit_chain.function_source),'[[:space:]]','','g'
    ),'"','');
    notification_body:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(notification_chain.function_source),'[[:space:]]','','g'
    ),'"','');
    audit_trigger_sql:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(audit_chain.trigger_definition),'[[:space:]]','','g'
    ),'"','');
    notification_trigger_sql:=pg_catalog.replace(pg_catalog.regexp_replace(
      pg_catalog.lower(notification_chain.trigger_definition),'[[:space:]]','','g'
    ),'"','');

    IF audit_chain.tgenabled<>'O' OR audit_chain.proname<>'realtime_from_audit_event'
       OR audit_chain.pronamespace<>pg_catalog.to_regnamespace('public')
       OR audit_chain.prosecdef OR audit_chain.provolatile<>'v'
       OR pg_catalog.array_length(audit_chain.proconfig,1) IS DISTINCT FROM 1
       OR pg_catalog.replace(audit_chain.proconfig[1],' ','')<>
          'search_path=pg_catalog,public'
       OR audit_chain.owner_name IN (
         'caresync_basic_app','caresync_transport_command_owner',
         'caresync_transport_evidence_ingest'
       ) OR pg_catalog.lower(audit_chain.result_type)<>'trigger'
       OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            audit_body,'UTF8'
          )),'hex')<>'09114a9bcefa8eba5e98b23ddf54b4d62cee9c0d3531d46a7b8702aaddb9a0ab'
       OR pg_catalog.strpos(
         audit_trigger_sql,'afterinsertonpublic.audit_eventsforeachrow'
       )=0 OR pg_catalog.strpos(audit_trigger_sql,'when(')>0
       OR pg_catalog.strpos(audit_sql,$transport_branch$ifnew.entity_type='transport_registry_command'theninsertintopublic.realtime_events(id,organization_id,event_type,entity_type,entity_id,occurred_at,payload)values(new.id,new.organization_id,'transport_registry.changed','transport_registry',null,new.occurred_at,pg_catalog.jsonb_build_object('source','audit_event','refresh_required',true));returnnew;endif;$transport_branch$)=0
       OR pg_catalog.strpos(audit_sql,'new.details')>0
       OR EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
         audit_chain.proacl,pg_catalog.acldefault('f',audit_chain.proowner)
       )) AS privilege WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE')
       OR pg_catalog.has_function_privilege(
         'caresync_basic_app',audit_chain.oid,'EXECUTE'
       ) OR pg_catalog.has_function_privilege(
         'caresync_transport_command_owner',audit_chain.oid,'EXECUTE'
       ) OR pg_catalog.has_function_privilege(
         'caresync_transport_evidence_ingest',audit_chain.oid,'EXECUTE'
       ) THEN
        RAISE EXCEPTION '0032 generic audit realtime bridge audit failed';
    END IF;

    IF notification_chain.tgenabled<>'O'
       OR notification_chain.proname<>'user_notification_enqueue_trigger'
       OR notification_chain.pronamespace<>pg_catalog.to_regnamespace('public')
       OR notification_chain.prosecdef OR notification_chain.provolatile<>'v'
       OR pg_catalog.array_length(notification_chain.proconfig,1) IS DISTINCT FROM 1
       OR pg_catalog.replace(notification_chain.proconfig[1],' ','')<>
          'search_path=pg_catalog'
       OR notification_chain.owner_name IN (
         'caresync_basic_app','caresync_transport_command_owner',
         'caresync_transport_evidence_ingest'
       ) OR pg_catalog.lower(notification_chain.result_type)<>'trigger'
       OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            notification_body,'UTF8'
          )),'hex')<>'940acca64555507f89b9bb365805193b891d4a5cd53b69e1ace17540c28a890e'
       OR pg_catalog.strpos(
         notification_trigger_sql,'afterinsertonpublic.user_notificationsforeachrow'
       )=0 OR pg_catalog.strpos(notification_trigger_sql,'when(')>0
       OR pg_catalog.strpos(notification_sql,$notification_insert$insertintopublic.user_realtime_events(id,user_id,organization_id,event_type,entity_type,entity_id,occurred_at,payload)values(new.id,new.user_id,new.organization_id,'notification.created','notification',new.id,new.created_at,pg_catalog.jsonb_build_object('source','notification_ledger'))onconflict(id)donothing;$notification_insert$)=0
       OR pg_catalog.strpos(
         notification_sql,'frompublic.notification_push_subscriptionsassubscription'
       )=0 OR pg_catalog.strpos(
         notification_sql,'leftjoinpublic.user_notification_preferencesaspreference'
       )=0 OR pg_catalog.strpos(
         notification_sql,'onconflict(notification_id,subscription_id)donothing;'
       )=0 OR pg_catalog.strpos(notification_sql,'exceptionwhenothersthen')=0
       OR pg_catalog.regexp_count(
         notification_sql,'pg_catalog\.set_config\('
       )<>3
       OR EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(
         notification_chain.proacl,
         pg_catalog.acldefault('f',notification_chain.proowner)
       )) AS privilege WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE')
       OR pg_catalog.has_function_privilege(
         'caresync_basic_app',notification_chain.oid,'EXECUTE'
       ) OR pg_catalog.has_function_privilege(
         'caresync_transport_command_owner',notification_chain.oid,'EXECUTE'
       ) OR pg_catalog.has_function_privilege(
         'caresync_transport_evidence_ingest',notification_chain.oid,'EXECUTE'
       ) THEN
        RAISE EXCEPTION '0032 user notification downstream trigger audit failed';
    END IF;

    IF 2<>(
      SELECT count(*) FROM pg_catalog.pg_class AS relation
      WHERE relation.oid IN (
        pg_catalog.to_regclass('public.user_realtime_events'),
        pg_catalog.to_regclass('public.notification_deliveries')
      ) AND relation.relrowsecurity AND relation.relforcerowsecurity
    ) OR 2<>(
      SELECT count(*) FROM pg_catalog.pg_policy AS policy
      WHERE policy.polrelid IN (
        pg_catalog.to_regclass('public.user_realtime_events'),
        pg_catalog.to_regclass('public.notification_deliveries')
      ) AND policy.polcmd IN ('a','*')
    ) OR EXISTS (
      SELECT 1 FROM (VALUES
        ('user_realtime_events','user_realtime_events_context_insert'),
        ('notification_deliveries','notification_deliveries_context_insert')
      ) AS expected(relname,polname)
      LEFT JOIN pg_catalog.pg_policy AS policy
        ON policy.polrelid=pg_catalog.to_regclass('public.' || expected.relname)
       AND policy.polname=expected.polname
      WHERE policy.oid IS NULL OR policy.polcmd<>'a' OR NOT policy.polpermissive
         OR policy.polroles<>ARRAY[0::oid] OR policy.polqual IS NOT NULL
         OR pg_catalog.regexp_replace(pg_catalog.regexp_replace(
              pg_catalog.replace(pg_catalog.lower(pg_catalog.pg_get_expr(
                policy.polwithcheck,policy.polrelid
              )),'pg_catalog.',''),'::(text|uuid)','','g'
            ),'[[:space:]()]','','g') IS DISTINCT FROM $context_policy$user_id=nullifcurrent_setting'app.current_user_id',true,''ororganization_id=nullifcurrent_setting'app.current_organization_id',true,''$context_policy$
    ) THEN
        RAISE EXCEPTION '0032 downstream RLS INSERT policy audit failed';
    END IF;
END
$transport_command_downstream_audit$;

-- Final fail-closed audit for cluster role, search path, database/schema
-- creation, ownership, every trigger-only guard, and the narrowly executable
-- 0029A authority-policy predicate. Detailed table/column allowlist verification
-- is repeated by Database.assert_basic_runtime_identity at every API and
-- push-worker startup.
DO $final_audit$
DECLARE
    runtime record;
BEGIN
    SELECT role.* INTO STRICT runtime
    FROM pg_catalog.pg_roles AS role
    WHERE role.rolname = 'caresync_basic_app';
    IF runtime.rolsuper OR runtime.rolbypassrls OR runtime.rolinherit
       OR runtime.rolcreaterole OR runtime.rolcreatedb OR runtime.rolreplication
       OR (CASE
            WHEN pg_catalog.array_length(runtime.rolconfig, 1) IS NULL THEN 0
            ELSE pg_catalog.array_length(runtime.rolconfig, 1)
          END) <> 1
       OR pg_catalog.replace(runtime.rolconfig[1], ' ', '') <>
          'search_path=public,pg_catalog'
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_auth_members AS membership
            WHERE membership.member = runtime.oid OR membership.roleid = runtime.oid
       )
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_db_role_setting AS setting
            WHERE setting.setrole = runtime.oid AND setting.setdatabase <> 0
       )
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_shdepend AS dependency
            WHERE dependency.refclassid =
                  'pg_catalog.pg_authid'::pg_catalog.regclass
              AND dependency.refobjid = runtime.oid
              AND dependency.deptype = 'o'
       )
       OR pg_catalog.has_database_privilege(
            'caresync_basic_app', pg_catalog.current_database(), 'CREATE'
       )
       OR pg_catalog.has_database_privilege(
            'caresync_basic_app', pg_catalog.current_database(), 'TEMPORARY'
       )
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_namespace AS namespace
            WHERE namespace.nspname !~ '^pg_'
              AND namespace.nspname <> 'information_schema'
              AND pg_catalog.has_schema_privilege(
                    'caresync_basic_app', namespace.oid, 'CREATE'
                  )
       )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',
            'public.caresync_charge_childcare_reconciliation(uuid,uuid,uuid)',
            'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',
            'public.caresync_childcare_operation_guard()', 'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',
            'public.caresync_childcare_reconciliation_proof_guard()', 'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',
            'public.caresync_childcare_immutable_ledger_guard()', 'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'caresync_basic_app',
            'public.caresync_childcare_contact_retirement_guard()', 'EXECUTE'
       )
       OR (
            pg_catalog.to_regclass('public.family_authority_people') IS NOT NULL
            AND (
              COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_insert_guard()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_transition_guard()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_temporal_guard()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_person_invariant()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_child_revision_invariant()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_evidence_invariant()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_receipt_guard()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_receipt_invariant()'
                  ),
                  'EXECUTE'
                ),
                true
              )
              OR NOT COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_authority_actor_is_privileged(uuid)'
                  ),
                  'EXECUTE'
                ),
                false
              )
              OR NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_proc AS procedure
                WHERE procedure.oid=pg_catalog.to_regprocedure(
                        'public.caresync_family_authority_actor_is_privileged(uuid)'
                      )
                  AND procedure.prosecdef
                  AND procedure.provolatile='s'
                  AND pg_catalog.array_length(procedure.proconfig, 1)=1
                  AND pg_catalog.replace(procedure.proconfig[1], ' ', '')=
                      'search_path=pg_catalog,public'
              )
              OR EXISTS (
                SELECT 1
                FROM pg_catalog.pg_proc AS procedure
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(
                    procedure.proacl,
                    pg_catalog.acldefault('f', procedure.proowner)
                  )
                ) AS privilege
                WHERE procedure.oid=pg_catalog.to_regprocedure(
                        'public.caresync_family_authority_actor_is_privileged(uuid)'
                      )
                  AND privilege.grantee=0
                  AND privilege.privilege_type='EXECUTE'
              )
            )
       )
       OR (
            pg_catalog.to_regclass(
              'public.family_authority_evidence_objects'
            ) IS NOT NULL
            AND (
              COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_evidence_object_write_guard()'
                  ), 'EXECUTE'
                ), true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_evidence_object_invariant()'
                  ), 'EXECUTE'
                ), true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_evidence_object_link_guard()'
                  ), 'EXECUTE'
                ), true
              )
              OR COALESCE(
                pg_catalog.has_function_privilege(
                  'caresync_basic_app',
                  pg_catalog.to_regprocedure(
                    'public.caresync_family_evidence_review_guard()'
                  ), 'EXECUTE'
                ), true
              )
            )
       ) THEN
        RAISE EXCEPTION
            'caresync_basic_app failed the final terminal least-privilege audit';
    END IF;
END
$final_audit$;

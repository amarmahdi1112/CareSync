# CareSync local release 0039

Last updated: 2026-07-23

## Release state

The checked-in local launcher and the retained PostgreSQL 17 cluster on port
5434 share the single Alembic head `0039_admissions_decision_spine`. The guarded
retained cutover completed on 2026-07-23 at 05:27:43 America/Edmonton from
exactly `0038_public_job_catalog_outbox`.

Revision 0039 adds a private, administrator-operated admissions lifecycle for
one prospective child per application:

`draft -> submitted -> under_review -> waitlisted|offered -> accepted|declined|withdrawn`

It provides versioned intake, deterministic waitlist lanes, program offers,
material correction, withdrawal/decline, duplicate review and atomic conversion
into the existing canonical Family, Child and pending unassigned Enrollment
command spine. The pre-existing derived intake-remediation queue remains a
separate projection over records that already exist.

Revision 0039 adds no parent or public admissions account, document
upload/signing, outbound email, automatic room placement, billing activation,
invoice/payment/provider behavior, funding decision or transport authority.
Verified child release and private/manual billing remain separate
owner-controlled boundaries. `facility_release_checkout_activations` and
`billing_manual_activations` both remain empty.

## Recorded retained-cutover evidence

The guarded launcher quiesced application writers, captured and reopened the
exact retained 0038 logical backup, restored it on a fresh PostgreSQL 17 target
at `127.0.0.1:56555/caresync`, restored both required evidence bundles into
fresh no-clobber vaults and migrated the retained database only after every
restore proof succeeded.

- Source revision: `0038_public_job_catalog_outbox`.
- Source and disposable restore: 16,445 rows across all 135 public source
  tables.
- Canonical source/restore row digest:
  `7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
- Family-evidence restore: zero source objects, zero rejected objects and zero
  restored objects, with a private receipt.
- Staff/transport-evidence restore: zero source ownership relationships and
  zero restored objects, with a private receipt.
- Retained result: `0039_admissions_decision_spine`, 141 public tables plus one
  public view and exactly 16,445 rows.
- Retained product counts: 110 families, 203 children and 197 enrollments.
- All six admission tables contain zero rows:
  `admission_applications`, `admission_application_preferences`,
  `admission_waitlist_entries`, `admission_offers`,
  `admission_conversion_links` and `admission_application_events`.
- Facility-release and manual-billing activation counts remain `0/0`.

The canonical private artifacts use backup stem
`caresync-postgres-20260723-052743-592770`:

- database backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-052743-592770.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-052743-592770.json.manifest.json`;
- exact database restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-052743-592770.json.gz.receipt.json`;
- family-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-052743-592770.vaults/family-evidence.receipt.json`; and
- staff/transport-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-052743-592770.vaults/staff-transport.receipt.json`.

These artifacts remain on the internal permission-capable filesystem. The T7
project volume is an ExFAT source mirror and is not authoritative for
owner-private directories or `0600` recovery evidence.

## Admissions command and database boundary

The migration adds six forced-RLS tenant tables. It extends the exact
childcare-command receipt targets with `admission_application`,
`admission_waitlist` and `admission_offer`, and unions `admissions:read`,
`admissions:manage` and `admissions:decide` into the existing system owner and
administrator permissions without replacing custom permission arrays.

The restricted runtime receives bounded reads, command-path inserts and exact
column-level lifecycle updates. It receives no admission-domain `DELETE`, no
event or conversion update and no ownership authority. Database command-row and
deferred command-bundle guards bind organization, actor, operation, versions,
event, receipt, audit and realtime provenance. Startup and runtime-role
bootstrap attest the exact tables, columns, constraints, indexes, forced-RLS
policies, grants, triggers, function ownership, fixed search paths and function
definitions before admitting the capability.

Every mutation uses one actor-bound operation ID and immutable receipt. Exact
retry returns the committed result; changed intent or stale application,
waitlist or offer versions write nothing. Acceptance reviews a signed digest of
the current duplicate candidate set and then creates or explicitly reuses
canonical records in one transaction. Family, Child and Enrollment nested
operations use deterministic operation IDs. An injected failure or conflicting
concurrent enrollment/reparent operation rolls back the complete acceptance.

Realtime entity types are `admission_application`, `admission_waitlist` and
`admission_offer`; the existing ATS `application` type remains distinct.
Realtime and notification payloads carry bounded identifiers and state only,
never child/contact intake or internal notes. Canonical REST reload establishes
truth before a client advances its cursor.

## Integrated acceptance

Final source and release acceptance passed:

- backend full suite: 1,997 passed, 105 explicitly opt-in cases skipped and
  seven recorded warnings in 714.74 seconds;
- focused backend admissions/migration/realtime matrix: 22 passed in 17.41
  seconds;
- fresh PostgreSQL 17 admissions gate: 1 passed in 10.88 seconds;
- independent PostgreSQL 17 rerun: 1 passed in 11.42 seconds;
- administrator focused admissions/recovery matrix: 12 files / 92 tests;
- administrator full suite: 125 files / 841 tests, plus TypeScript and the Vite
  production build;
- staff app: 272 tests plus TypeScript; and
- browser extension: 78 tests plus TypeScript and its production build.

The PostgreSQL proof covers populated 0038-to-0039 migration, an empty
round-trip, forced RLS and ACLs, lifecycle and conversion rollback, reverse
preference lanes, and acceptance-versus-enrollment/reparent races. Forty-one
release-pin checks, Ruff and Python bytecode compilation also passed.

## Integrated live-local acceptance

After promotion:

- `GET /api/v1/health` returned 200 with PostgreSQL connected;
- the administrator on port 5174 returned 200;
- the separate billing sandbox API on port 3302 and frontend on port 5274 both
  returned 200; and
- the signed-in retained Admissions workspace loaded and refreshed the
  pipeline, deterministic waitlist, protected draft form, non-PII application
  register, canonical existing-record remediation and enrollment-to-billing
  readiness projection without a visible error surface.

The retained browser smoke performed no write. All admission tables remained
empty. Destructive application lifecycle, waitlist, offer and conversion
acceptance stayed on disposable PostgreSQL so no synthetic admissions history
was added to retained data.

These automated and live-local results do not constitute production,
regulatory, privacy, accessibility, physical-operator, payment-provider or
third-party delivery acceptance.

## Mandatory maintenance order

For a non-empty retained database whose revision differs from
`0039_admissions_decision_spine`, `scripts/start-basic.sh` must preserve this
order:

1. stop only verified CareSync API and push-worker processes;
2. prove that no application writer or other database client remains;
3. create and reopen-verify one private same-snapshot logical backup;
4. capture and verify every required evidence bundle, or prove the
   corresponding authoritative vault is empty;
5. restore the database exactly into a fresh, explicitly confirmed disposable
   PostgreSQL target and verify every count plus the canonical row digest;
6. restore each required evidence bundle into a new no-clobber disposable
   vault and require its private receipt;
7. repeat writer and database-session checks;
8. migrate the retained database to exactly
   `0039_admissions_decision_spine`;
9. rebuild and audit restricted runtime grants;
10. attest the complete admissions tables, guards, RLS, ACL, ownership and
    realtime contract; and
11. start the push worker, API and clients only after every gate passes.

The launcher never uses `alembic upgrade head` against the retained database.
Ports 5432, 5433 and 5434 remain forbidden as restore-verification targets.
Neither migration nor startup may create a facility-release or manual-billing
activation.

## Next bounded slice

Product slice `0040_billing_readiness_batch_planner` is the next bounded slice.
It adds a read-only setup planner and explicitly reviewed reuse of canonical
billing commands. It introduces no schema migration, so the retained Alembic
head remains exactly `0039_admissions_decision_spine`. It does not activate
billing, issue an invoice, record a payment, contact a payment provider or
create funding behavior. Its architecture, implementation and disposable
evidence remain separate from this completed 0039 release.

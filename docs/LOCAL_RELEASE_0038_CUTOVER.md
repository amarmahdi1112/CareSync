# CareSync local release 0038

Last updated: 2026-07-23

## Release state

The checked-in local launcher and the retained PostgreSQL 17 cluster on port
5434 share the single Alembic head `0038_public_job_catalog_outbox`. The
guarded retained cutover completed on 2026-07-23 from exactly
`0037_billing_agreement_scope`.

Revision 0038 adds one privacy-safe durable public-job catalog event boundary.
It lets an unaffiliated candidate replay the fact that a formerly public
listing changed or closed, including after that listing disappears from the
current public projection. The public event carries only:

- its sequence and event identities;
- the public listing identity;
- `job.updated` or `job.status_changed`;
- the bounded public status and listing version; and
- the event timestamp.

It carries no organization identity, candidate identity, listing text,
application data, interview data, offer data, or other tenant-private content.
Draft and never-public jobs are absent. A paused job remains private until it
is reopened. Canonical ATS and marketplace reads remain the source of current
listing truth; the outbox is an invalidation/replay boundary, not a second job
record.

Revision 0038 does not activate verified child release or private/manual
billing. `facility_release_checkout_activations` and
`billing_manual_activations` both remain empty.

## Recorded retained-cutover evidence

The guarded launcher quiesced application writers, captured the exact retained
0037 database, reopened and verified the private logical backup, restored it on
a fresh PostgreSQL 17 target on port 56553, restored both required evidence
bundles into fresh no-clobber vaults, and migrated the retained database only
after every restore proof succeeded.

- The source backup and disposable restore contain 16,335 rows across all 134
  public source tables at revision `0037_billing_agreement_scope`.
- The canonical row digest on both source and restore is
  `f0c93cd10395d24816292fc20b761ce262bb666ffeeab5776959c5bc817b5472`.
- The family-evidence and staff/transport-evidence restores each contain zero
  objects. Both produced private restore receipts with mode `0600`.
- The retained database reports `0038_public_job_catalog_outbox`, 135 public
  tables plus one public view, 110 families and 203 children.
- The retained total is 16,339 rows. The four post-backup rows are two public
  catalog events plus one organization realtime ticket and one user realtime
  ticket created when the signed-in browser reconnected.
- Exactly one retained job is eligible for the public catalog. The migration
  created one backfill event and the current public projection contains that
  one listing: eligible/backfill/projection counts are `1/1/1`.
- Every backfill identity agrees with its canonical parent realtime event.
- The canonical source tables used by the projection have `FORCE ROW LEVEL
  SECURITY`.
- `public_job_catalog_events` has row-level security enabled and intentionally
  not forced. The restricted runtime has `SELECT` only, with no direct
  `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, trigger, reference, or ownership
  authority.
- `PUBLIC` has no table, sequence, or function grant on the catalog boundary.
- `caresync_public_job_catalog_from_realtime` is `SECURITY DEFINER`, has the
  fixed `pg_catalog` search path, and is owned by the same non-runtime owner as
  the catalog table.
- The `realtime_events_public_job_catalog` trigger is present and enabled.
- The facility-release and manual-billing activation tables each contain zero
  rows.

The canonical private artifacts use the backup stem
`caresync-postgres-20260723-022822-921802`:

- database backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.manifest.json`;
- exact database restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.json.gz.receipt.json`;
- family-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.vaults/family-evidence.receipt.json`; and
- staff/transport-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.vaults/staff-transport.receipt.json`.

These artifacts are retained on the internal permission-capable filesystem.
The T7 project volume remains an ExFAT source mirror and is not authoritative
for owner-private directories or `0600` evidence.

## Database and replay boundary

The migration freezes its 0038 schema independently of later ORM evolution.
It requires the 0037 canonical ATS and realtime source tables to exist and to
be `FORCE RLS`, temporarily relaxes only the migration owner's FORCE behavior
inside the migration transaction for the bounded backfill, then restores and
verifies both source protections before commit.

The projection trigger and its function insert the public event in the same
transaction as the canonical tenant realtime event. Duplicate or inconsistent
projection identity fails the parent transaction rather than silently
diverging. Startup attests the exact revision, catalog constraints and indexes,
trigger and function, RLS policies, ownership, search path, and restricted
grants before enabling public replay.

Unaffiliated candidate replay reads only the public catalog event table.
Candidate clients treat each event as an invalidation, refresh the canonical
public jobs/applications/interviews/offers surface, and advance their durable
checkpoint only after the canonical refresh succeeds. Ordered replay,
deduplication, retry after refresh failure, listing removal, foreground/resume,
and unmount behavior are covered by the mobile acceptance suite.

## Integrated acceptance

The final source and release acceptance passed:

- backend full suite: 1,979 passed, 104 explicitly opt-in cases skipped;
- focused backend release matrix: 915 passed, 2 skipped;
- isolated PostgreSQL 17 0038 behavior and migration gates: 3/3;
- administrator: 808/808;
- staff app: 272/272;
- browser extension: 78/78.

The administrator and staff TypeScript gates passed, and the administrator and
extension production builds remained green. The API, administrator portal and
separate billing sandbox all reported healthy after promotion. A signed-in
Jobs browser session reconnected to realtime and displayed canonical retained
data.

These automated and live-local results do not constitute production,
regulatory, privacy, accessibility, physical-operator, payment-provider, or
third-party delivery acceptance.

## Mandatory maintenance order

For a non-empty retained database whose revision differs from
`0038_public_job_catalog_outbox`, `scripts/start-basic.sh` must preserve this
order:

1. stop only verified CareSync API and push-worker processes;
2. prove that no application writer or other database client remains;
3. create and re-open-verify one private same-snapshot logical backup;
4. capture and verify every required evidence bundle, or prove the
   corresponding authoritative vault is empty;
5. restore the database exactly into a fresh, explicitly confirmed disposable
   PostgreSQL target and verify every count plus the canonical row digest;
6. restore each required evidence bundle into a new no-clobber disposable
   vault and require its private receipt;
7. repeat writer and database-session checks;
8. migrate the retained database to exactly
   `0038_public_job_catalog_outbox`;
9. rebuild and audit restricted runtime grants;
10. attest the complete public-catalog table/function/trigger/RLS/ownership
    boundary; and
11. start the push worker, API and clients only after every gate passes.

The launcher never uses `alembic upgrade head` against the retained database.
Ports 5432, 5433 and 5434 remain forbidden as restore-verification targets.
Neither migration nor startup may create a facility-release or manual-billing
activation.

## Next bounded slice

At the 0038 checkpoint, revision `0039_admissions_decision_spine` was the next
planned bounded slice. Its intended boundary was an administrator-operated,
exact-retry admissions lifecycle, deterministic waitlist history, program
offers and duplicate-safe conversion into the existing Family, Child and
pending unassigned Enrollment command spine.

Its locked boundary is recorded in
`docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md`. Revision 0039 subsequently
passed the guarded backup, exact restore, restricted-role, migration,
regression and live-local acceptance process. Its current retained evidence is
recorded in `docs/LOCAL_RELEASE_0039_CUTOVER.md`.

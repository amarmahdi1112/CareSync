# Backend migration

## Sources of truth

1. Git `HEAD` in `Discover_timesheet copy` describes the public baseline.
2. Its working tree contains private company features and algorithms.
3. The React frontend documents the behavior clients currently expect.
4. `caresync-backend/storage/caresync.db` documents the live legacy schema.

## Method

The migration is behavioral rather than a line-by-line translation. Before each
module is replaced, representative inputs and outputs are captured in
characterization tests. The Python implementation must pass those tests before the
module is marked verified.

Historical compatibility slices include all 40 live PostgreSQL table mappings, authentication,
organization-scoped family and child workflows, legacy invoicing/credits and invoice AI,
signatures, CSV/PDF imports, automatic Alberta/daycare closures, the V2 claim simulator,
and the default independently audited V3 attendance scheduler. The
simulator's seeded randomness, fairness, capacity controls, audit trail, and final
totals match a compiled-TypeScript golden fixture. Empty enrollment dates also no
longer trigger the legacy invalid-date logging crash. The active frontend scheduling
pipeline now uses REST end to end and persists validated generated batches to the
existing `scheduled_attendance` table in one organization-scoped transaction while
retaining session metadata for warnings and audit context. Generated schedule drafts
carry input hashes and algorithm versions; the
review screen exposes completion and critical warnings, blocks incomplete or manually
invalidated V3 schedules from export, validates exact five-minute time/capacity edits, and clearly labels transient
batches versus saved database schedules. The legacy compatibility invoicing API includes a
read-only billing-run preflight, but default Basic does not expose or use those routes. Its
replacement source boundary is `0033_billing_ledger`, designed independently as a synthetic-only,
append-only CAD ledger and `/billing` workspace rather than as behavioral parity with the old
invoicing system. Its canonical workspace exposes eight collections including full historical
`payer_versions`, and each synthetic invoice pins the exact payer-version plus guardian provenance
used at record time so later reassignment cannot change invoice history. 0033 command writes are
PostgreSQL-only on explicitly attested and allowlisted
disposable loopback high ports; SQLite never authorizes them. The React application
no longer includes Apollo, GraphQL documents, or a GraphQL provider.

PDF claim imports now match parsed names against active organization children using
conservative normalized-name and date-of-birth evidence. The save endpoint repeats
matching server-side and ambiguous names remain available for manual Name Sync review.

Historical migration order:

1. Foundation, configuration, database safety, logging, and errors
2. Authentication, authorization, organizations, users, and activity history
3. Families, guardians, children, emergency contacts, and funding
4. Pricing, imports, file processing, and relationship detection
5. Scheduling, attendance, claims, and auditing algorithms
6. Invoicing, payments, credits, recurring work, PDFs, and email
7. Signatures, letterheads, AI features, exports, and administration
8. React REST-client conversion and frontend corrections

The old order is retained as project history, not current release truth. The
checked-in launcher, source and retained runtime now share
`0039_admissions_decision_spine`. Its guarded 2026-07-23 promotion restored
exactly 16,445 source rows across 135 tables at 0038, preserved 110 families,
203 children and 197 enrollments, and retained 141 public tables plus one view.
The public-job catalog and administrator admissions boundaries are released;
the historical 0036 manual-billing protocol and 0037 agreement-scope repair
remain intact, and both owner-controlled activation tables remain empty. Final
acceptance recorded 1,997 backend tests passed with 105 skips and seven
warnings, 841 administrator tests, 272 staff-app tests, 78 extension tests and
two independent green PostgreSQL 17 admissions runs. Product slice
`0040_billing_readiness_batch_planner` is verified in source and through
retained live read-only API acceptance. It introduces no schema migration; the
retained Alembic head remains exactly
`0039_admissions_decision_spine`. Signed-in administrator browser-click
acceptance remains pending.

The 0033 sandbox still has no real processor or money movement, automatic
invoice delivery, refund, tax/funding authority, parent portal or production
commerce cutover. The separate 0036 private/manual protocol records only
reviewed off-platform facts after explicit owner activation.

Archived code, generated output, zipped duplicates, and experimental scripts are not
ported unless the feature-parity audit proves they implement active behavior.

## Legacy test baseline

The initial Jest run found 704 passing assertions and two failing assertions. The
remaining suite failures came from Jest incorrectly collecting compiled declaration
files, duplicated `dist` tests, archived tests with removed imports, and macOS `._`
metadata. The 704 passing assertions are behavioral parity targets; generated and
archived test-discovery failures are not application requirements.

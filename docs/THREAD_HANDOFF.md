> [!IMPORTANT]
> **Retained-release commands supersede legacy instructions below (2026-07-26).**
> The remainder of this document is preserved verbatim for product and audit
> context. For the retained `0039_admissions_decision_spine` to
> `0042_billing_policy_recert` release, do not execute any older startup,
> migration, cutover, restore, or rollback command found below. The canonical
> contract is `scripts/BASIC_RELEASE_CLI_CONTRACT.md`. Its current two-phase
> operator flow is:
>
> ```text
> scripts/basic-release.sh prepare [--clone-port 55000..60999]
> scripts/basic-release.sh commit \
>   --receipt /absolute/private/run/candidate-receipt.json \
>   --confirm "COMMIT CARESYNC RETAINED 0039 TO 0042"
> ```
>
> Finalized emergency rollback requires the candidate, commit and finalization
> receipts. Interrupted intent-only rollback supplies only the candidate receipt;
> it omits both finalized-receipt flags and is accepted only when the run contains
> its exact durable commit-attempt intent. Both use the exact confirmation phrase
> `ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039`.
>

# CareSync Rebuild — Thread Handoff

Last updated: 2026-07-23 (America/Edmonton)

This is the durable, sanitized continuation context for CareSync. It contains
no passwords, tokens or API keys.

## Required context loading order

Every continuation task must load these documents before choosing or changing
product scope:

1. `docs/ULTIMATE_PRODUCT_CONSTITUTION.md` for the complete long-term feature
   universe and research north star;
2. `docs/PRODUCT_IMPLEMENTATION_LEDGER.md` for sequence and completion state;
3. `docs/THREAD_HANDOFF.md` for the current runtime, release and active-work truth;
4. `docs/MVP_READINESS_AUDIT.md` for the honest quality and release boundary;
5. `docs/FAMILY_AUTHORITY_ARCHITECTURE.md` for the enclosing 0029 sequence; and
6. `docs/FAMILY_RELEASE_CHECKOUT_ARCHITECTURE.md` for the 0029C/D source boundary; and
7. `docs/STAFF_SCREENING_TRANSPORT_ARCHITECTURE.md` for the released 0030
   screening-to-hire boundary, 0031 read-only registry, 0032 evidence/review
   command layer and later transport sequence; and
8. `docs/BILLING_FINANCE_ARCHITECTURE.md` for the separate childcare-finance books,
   immutable receivables subledger, Alberta/CRA rule boundary, capability gates and staged
   billing certification sequence, including the 0033 synthetic foundation and
   owner-activated 0036 private/manual boundary; and
9. `docs/LOCAL_RELEASE_0039_CUTOVER.md` for the current retained revision,
   guarded database/vault evidence and admissions release boundary;
10. `docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md` for the released 0039
    lifecycle, database and administrator contract;
11. `docs/LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md` for the verified
    0041 operational boundary;
12. `docs/PRODUCT_SLICE_0041_LIVE_ROOM_PRESENCE_SAFETY_BOARD_RELEASE_NOTE.md`
    for the disposable 0041 evidence and remaining acceptance;
13. `docs/PRODUCT_SLICE_0042_BILLING_POLICY_RECERTIFICATION_RELEASE_NOTE.md`
    for the 0042 source-integrity repair and proof; and
14. `docs/LOCAL_RELEASE_0038_CUTOVER.md` for the preceding historical
    public-job catalog replay release.

The Product Constitution is intentionally much larger than the MVP. Its ideas
remain authoritative backlog and design context, but they are not implied to be
implemented until the ledger and audit explicitly say so.

## Current objective

### Current verified source 0041/0042 checkpoint

Checked-in source and `scripts/start-basic.sh` target
`0042_billing_policy_recert`. Retained PostgreSQL 17 on port 5434 remains
exactly at `0039_admissions_decision_spine`; no 0041 or 0042 retained migration
or cutover occurred. Do not restart retained services through the 0042-pinned
launcher until the guarded retained promotion is separately authorized and
completed.

0041 implements server-confirmed staff room-presence intervals, exact-retry
start/move/end transitions, child-operation room gating, factual operational
configured-target boards, append-only exception episodes and bounded
realtime/notifications. Unknown or incoherent source facts fail visibly. It
does not certify regulatory ratios, qualifications, capacity, supervision or
compliance.

0042 recertifies the complete frozen 0033 PostgreSQL billing-policy catalog.
It accepts only exact whole profile A or the audited dump/restore profile B,
rejects mixed/tampered/unknown catalogs and recreates all 36 canonical policies
transactionally. It adds no billing product behavior or authority.

The populated disposable clone preserved all 16,508 rows across 140 pre-0041
business tables through `0041 -> 0039 -> 0042` and
`0042 -> 0041 -> 0042`. Exact identities are:

- count digest:
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`;
- row digest:
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`;
- pre-0041 backup SHA-256:
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`;
  and
- populated pre-0042 backup SHA-256:
  `55be096d31c90b33cb7f19e625b472defbb60387d4dd56a7fb1fdec0f9a7490c`.

Final automated evidence is all 135 backend test files passed; focused backend
45 passed / one opt-in skipped; fresh PostgreSQL 17 0041 and 0042 proofs each
passed; source-head runtime-grant/backup 39 and billing certificate eight
passed; administrator 22 files / 193 tests plus TypeScript/build passed; Staff
app 297 plus TypeScript, Expo Doctor 20/20 and 782-module Android export
passed. The Android HBC SHA-256 is
`a3667d6da9e033c3a28fec98cf2e9edf4f5ffed51fbeefc0a2bb2c3769aec0fe`.

Next required work is signed-in administrator and physical Android 0041
acceptance, then a permission-safe retained backup/evidence restore, exact
disposable replay, restricted-runtime certification and an explicit retained
cutover decision. The source release notes are not cutover records.

### Retained 0039 release checkpoint (unchanged)

The retained port-5434 database remains at
`0039_admissions_decision_spine`. The guarded 2026-07-23 05:27:43
America/Edmonton cutover captured and exactly restored the retained 0038 source
before migration: 16,445 rows across all 135 public source tables, including
110 families and 203 children. Source and fresh port-56555 restore share row
digest
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both evidence-vault restores contained zero objects and produced private
receipts.

The migrated retained result has 141 public tables plus one view and exactly
16,445 rows, including 110 families, 203 children and 197 enrollments. All six
admission tables remain empty. Facility-release and manual-billing activation
counts remain `0/0`.

Revision 0039 provides the private administrator admissions lifecycle:
versioned intake, deterministic waitlist lanes, program offers, material
correction, decline/withdrawal, exact retry, duplicate review and atomic
Family/Child/pending Enrollment conversion. Its six tables are forced-RLS;
runtime lifecycle updates are exact-column only; events and conversion links
are immutable; and database provenance/bundle guards bind each command to
receipt, audit and PII-free realtime facts. The existing derived
existing-record remediation queue remains separate.

The canonical private backup stem is
`caresync-postgres-20260723-052743-592770`. Database/vault paths, migration,
grant and smoke evidence are listed in
`docs/LOCAL_RELEASE_0039_CUTOVER.md`.

Final integrated acceptance passed 1,997 backend tests with 105 explicit
opt-in skips and seven warnings, a focused 22-test backend matrix, two
independent green PostgreSQL 17 admissions runs, administrator 125 files / 841
tests, staff app 272 tests and extension 78 tests. TypeScript, production
builds, 41 release-pin checks, Ruff and bytecode compilation passed.

API, administrator and billing sandbox health returned 200. The signed-in
retained Admissions workspace loaded and refreshed pipeline, waitlist,
protected draft, non-PII register, remediation and billing readiness without a
visible error or write. Destructive lifecycle/conversion proof remained
disposable and retained admissions stayed empty.

Development continues from this integrated retained 0039 baseline. Product
slice `0040_billing_readiness_batch_planner` is now verified in source and
through retained live read-only API acceptance. It adds a deterministic,
privacy-bounded setup plan and no-write preview, then reuses only the existing
canonical account, payer, rate and agreement command protocol after explicit
review. It does not introduce a schema migration, so the retained Alembic head
and release pin remain exactly `0039_admissions_decision_spine`. It does not
activate billing, issue invoices, record payments, contact a provider or
create funding behavior.

Retained 0040 acceptance returned schema v1 for 2026-07-23 with 111 groups:
102 account/payer and nine manual review. Apply was unavailable because manual
activation remains absent. A one-group preview returned one `account_open`
intent and zero blocks without changing any operational billing or activation
row. API 3002 and administrator 5174 were healthy and the setup route returned
HTTP 200. Automated evidence is backend planner 9 passed, portable billing 34
passed / 1 skipped, PostgreSQL 17 RLS/no-write 1 passed, administrator 128
files / 865 tests, and a green 881-module production build. This is live
API/read-only acceptance; the signed-in administrator browser-click
walkthrough remains pending.

### Historical retained 0038 release checkpoint

At that checkpoint, the retained port-5434 database, source and launcher target
shared `0038_public_job_catalog_outbox`. The guarded 2026-07-23 cutover captured and
exactly restored the retained 0037 source before migration: 16,335 rows across
all 134 public source tables, including 110 families and 203 children. Source
and fresh port-56553 restore share row digest
`f0c93cd10395d24816292fc20b761ce262bb666ffeeab5776959c5bc817b5472`.
Both evidence-vault restores contained zero objects and produced private
`0600` receipts.

The migrated retained result at that checkpoint had 135 public tables plus one
view, 16,339 total
rows, 110 families and 203 children. Two catalog event rows and one
organization and one user realtime ticket created by the signed-in browser
reconnect account exactly for the four-row difference. One job was eligible,
one event was backfilled, and one listing is in the current public projection
(`1/1/1`). All backfill event identities match their canonical parents.

Revision 0038 provides privacy-safe durable replay of formerly public listing
edits and final closure. The public rows carry event/listing identities,
bounded type/status/version and time only—never organization identity, listing
text, candidate-private data or tenant-private workflow facts. Canonical
ATS/marketplace reads still author current state.

The source ATS and realtime tables remain `FORCE RLS`. The catalog table has
RLS enabled without FORCE, the restricted runtime has `SELECT` only and
`PUBLIC` has no grant. Its enabled trigger calls a `SECURITY DEFINER` function
with fixed `pg_catalog` search path; function and table share a non-runtime
owner. The retained facility-release and manual-billing activation tables
remain empty.

The canonical private backup stem is
`caresync-postgres-20260723-022822-921802`. Database/vault paths, migration and
grant evidence are listed in `docs/LOCAL_RELEASE_0038_CUTOVER.md`.

Final integrated acceptance passed 1,979 backend tests with 104 explicit
opt-in skips, a focused 915-pass/2-skip matrix, 3/3 isolated PostgreSQL gates,
administrator 808/808, staff app 272/272 and extension 78/78. API,
administrator and billing sandbox health passed. Signed-in Jobs reconnected to
realtime and showed canonical retained data.

Development subsequently continued from that integrated retained 0038 baseline
into `0039_admissions_decision_spine`, whose completed guarded release is
recorded above.

### Historical retained 0037 release checkpoint

At that checkpoint, the retained port-5434 database, source and launcher target shared
`0037_billing_agreement_scope`. The 2026-07-23 guarded cutover captured and
exactly restored the retained 0036 source before migration: 16,309 rows across
all 134 public tables, including 110 families and 203 children. Both required
evidence bundles restored with private receipts. The migrated retained result
still has 134 public tables plus one view and preserves the same families and
children.

Revision 0037 is a billing-integrity repair, not a new command protocol.
Enrollment-backed agreements are unique by organization, account and
enrollment; historical null-enrollment agreements keep a partial
organization/account/child fallback; and the superseded all-row account/child
constraint is absent. Revision 0036 remains the private/manual billing protocol
schema. The retained facility-release and manual-billing activation tables are
both empty.

The canonical database backup, manifests, database restore receipt and both
evidence-bundle receipts are listed in
`docs/LOCAL_RELEASE_0037_CUTOVER.md`.

Final integrated acceptance passed 1,969 backend tests with 102 explicit
opt-in cases skipped, administrator 808/808 plus TypeScript and production
build, staff app 260/260 plus TypeScript, and extension 78/78 plus production
build. Required canonical ATS/marketplace OpenAPI routes are present; legacy
hiring prefixes and retired routes are absent. The retained hiring preflight
reports zero pending private invitations, zero invitation-bound applications
and zero draft offers.

Signed-in Admissions, Billing, Family, Child and Jobs checks passed. The
enrollment-to-billing projection reports 0 setup-ready records out of 197
active child records and retains an actionable item for every unresolved
record. Family invoices remain settlement authority and child summaries remain
charge-attribution only.

Development then continued from that integrated retained 0037 baseline into
`0038_public_job_catalog_outbox`, whose completed guarded release is recorded
above.

### Historical retained 0036 release checkpoint

At that checkpoint, the retained port-5434 database, source and launcher target
shared `0036_billing_manual_mode`. The 2026-07-22 guarded cutover captured and exactly
restored the retained 0028 source before migration: 16,260 rows across 77
tables, including 110 families and 203 children. The migrated retained result
has 134 public tables plus one view and preserves the same 110 families and 203
children.

The canonical backup, matching manifest and exact-restore receipt are:

- `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.gz`;
- `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.manifest.json`; and
- `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260722-232512-277485.json.gz.receipt.json`.

The exact 0028 source had no family or staff/transport evidence tables and no
corresponding vault bytes, so this cutover correctly required no evidence
bundle. The retained `facility_release_checkout_activations` and
`billing_manual_activations` tables are both empty. Do not infer either
owner-controlled activation from schema availability.

Final integrated acceptance passed 1,094 backend tests with 101 explicit
opt-in cases skipped, administrator 790/790 plus production build and zero
production audit findings, staff app 265/265 plus TypeScript and the recorded
Expo SDK 57 Doctor/export evidence, and extension 78/78 plus TypeScript/build
and zero production audit findings. API health reported PostgreSQL connected
and the administrator frontend returned HTTP 200.

Development then continued from this integrated retained 0036 baseline. The next
bounded product integration is enrollment-to-billing readiness and
family/child finance summaries over private/manual billing. Family invoices
remain the settlement authority; child views may attribute charges but must
not invent child-level payment or outstanding status. Verified release and
manual billing remain owner-controlled and unactivated until a real operator
reviews their readiness.

### Historical pre-0036 implementation checkpoints

The narrative below preserves dated implementation and certification evidence.
Any statement in it that calls 0029–0033 source-only, calls a retained 0028
head current, or reports an older suite count describes its historical
checkpoint and does not override the current release checkpoint above.

CareSync is an Alberta-first childcare operations platform being hardened as a
local functional MVP. The Basic foundation now extends through candidate/ATS,
staff operations, daily care, medication, incidents, notifications, rota,
workforce planning, Staff Exchange and the released child-domain command spine.

The latest no-migration integration checkpoint makes those modules communicate through one
transactional realtime spine. The backend and administrator share a closed entity vocabulary;
unknown producer names and the phantom `enrollment_batch` event fail tests. Mounted portal
consumers re-read canonical REST state before advancing their socket cursor, the persistent session
shell quietly refreshes organization facts, and medication/workforce notification actions resolve
the exact current tenant-scoped record before focusing it. A new realtime Admissions page derives
actionable lifecycle/placement review work from existing 0028 records. It does not claim a durable
waitlist, an admission decision, data completeness or regulatory certification. No retained
database migration or rewrite belongs to this checkpoint.

The staff app now advances an organization cursor only after its core operational read and exact
mounted workflow have both acknowledged the same invalidation. Candidate tenant and user-private
streams keep separate cursors; the latter treats `marketplace.*` as quiet identity-bound canonical
work, not notification attention. Replaced sockets, unmounts, identity/membership mismatches,
failed reads and sign-out persistence races cannot commit a cursor. Public job and exact
candidate-owned tenant invalidations are safely expanded, but replay of an unrelated
organization's final-listing closure still requires a future durable public-catalog outbox.

The earlier 2026-07-22 integration checkpoint passed 959 backend tests (90 explicit opt-in
PostgreSQL skips), 677 administrator tests plus TypeScript and the 857-module production build,
and 252 staff-app tests plus TypeScript. The restarted Basic API reported healthy PostgreSQL connectivity at
`/api/v1/health`, rejected unauthenticated Admissions access, and accepted both authenticated
realtime streams. The signed-in Admissions browser smoke showed all seven current contradiction
cases, exact family/child remediation links and no warning/error console entries. Leave the local
administrator on `http://127.0.0.1:5174` and the API on `http://127.0.0.1:3002`; neither service
startup nor this integration checkpoint changes the retained `0028_childcare_command_spine` head.

The later 0029 authority/release closeout and recovery-consistency hardening supersede those
current-source counts without changing the retained release: 1,040 backend tests passed, with 94
deliberately opt-in disposable-PostgreSQL/scanner/operator/recovery cases skipped and seven
non-failing dependency warnings; the focused
authority/realtime backend matrix passed 47 tests plus Ruff; the administrator passed 107 test
files / 691 tests and its production build; and the staff app passed 263 tests and TypeScript.
The API was then restarted directly under the restricted `caresync_basic_app` runtime identity,
without the migration launcher. `/api/v1/health` returned 200 with PostgreSQL connected, the new
authority-summary route appeared in OpenAPI, unauthenticated access returned 401, and the signed-in
child profile rendered its owner-only summary with the intended retained-0028 capability-
unavailable state. An exact consent receipt URL remained contained and the browser console had no
warning or error. Realtime and notification sockets reconnected after restart.

The isolated live-local Alembic head is `0028_childcare_command_spine`. Its
source, migration, restricted-role, backup/restore, concurrency, admin and
regression gates are complete, and its release evidence is recorded below.
The active bounded slice is `0029_family_authority`: custody/release rules,
authorized pickup, consent evidence and immutable checkout-recipient snapshots.
Its architecture is locked in `docs/FAMILY_AUTHORITY_ARCHITECTURE.md`; source
implementation is proceeding in additive source slices and no local release/cutover has been claimed.
The revised 0029A kernel, 0029A1 evidence vault and exact source revision
`0029A2_authority_activation`, strict schemas and layered runtime feature gates,
family workspace, authority-person create/replace/retire lifecycle and
authority-evidence record/review/reject/invalidate/supersede lifecycle are
implemented and verified in source. A1 adds no-clobber private upload, server-measured object
identity, quarantine/scan, clean-object binding/download, maker/checker, private bundle/restore and
report-only reconciliation. A2 adds the fail-closed evidence activation matrix, administrator
release authorization/rule commands and immutable policy/consent commands. B adds the
source-verified, minimum-necessary expiring educator release-context GET, hardened database
projection, generic realtime invalidation and memory-only staff review panel.
`0029C_verified_release_checkout` supplies the immutable portable foundation and
`0029D_release_checkout_writer` supplies the source-verified restricted PostgreSQL normal-release
writer, exact replay and runtime readiness boundary. The staff flow is wired behind the
authenticated per-facility server capability; incomplete or ineligible facilities fail closed and
never fall back to legacy checkout. The retained database was last observed at
0028 with zero authority tables after the recorded empty-schema migration
incident below. C/D plus the explicit 0035 activation writer are now in the
checked-in 0036 promotion target, but no retained migration, facility
activation, production operator certification or cutover is claimed. Software
override remains deferred.

The latest authority integration adds an owner/administrator-only child-profile summary over the
current and explicitly focused release-authorization, release-rule and consent records. It is
minimum-necessary, bounded, tenant/family/child/revision coherent, constant-query and rechecks
current membership/role immediately before projection. Generic `child_authority_head` realtime
invalidation refreshes the family workspace, the child summary and the staff release context
without carrying a child, family or authority-record identifier. Exact receipt links never
substitute a nearby record. On retained revision 0028 the summary fails before ORM access and
shows a finite capability-unavailable state; that is intentional, not activation.

The verified-release mobile flow now uses latest-request-wins context reads, immediate realtime
and identity/scope invalidation, current-boundary-safe 401/403 handling, protected ambiguous
operations, single-submit orchestration and accessible busy-state behavior. No context or
confidential detail is persisted locally, and no stale response can revoke a replacement session
or overwrite a newer lease. This is source verification only; the bounded signed-in authority
operator proof described below does not exercise physical Android checkout. Physical Android
acceptance, facility activation and retained cutover remain open.

The 2026-07-22 family-authority operator certification passed all 16 closed cases through signed-in
public HTTP routes on a fresh caller-provisioned loopback PostgreSQL 17 database at exact
`0029D_release_checkout_writer`, under `caresync_basic_app`, with ClamAV 1.5.3 definitions 28068.
It covered owner registration, administrator invitation/activation, production multipart upload
and exact retry, real clean scanning and exact retry, byte-exact private download, evidence
recording, maker review rejection with attested no-write, independent checker review, reviewed
authority activation and exact retry, PII-free realtime invalidation through a public ticket and
WebSocket replay, and the administrative summary. Preflight and postflight proved the same system
identifier and revision, expected synthetic rows and zero unexpected sessions. The private,
no-clobber, redacted mode-`0600` receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
its SHA-256 is `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
It is owned by uid 501, has one link and is 2,261 bytes. It records no credential, email, person or
record identifier, document bytes, vault/database path or scanner absolute path. The harness did
not provision, migrate, drop or truncate the database, contact a protected port or access retained
data, and the receipt grants neither release nor cutover authority.

The subsequent 2026-07-22 exact-0029D synthetic artifact-recovery consistency gate also passed.
It restored the already-fixed four-artifact database/evidence set into one caller-created scratch
cluster and a new private vault, reproduced 90 tables / 61 rows and one evidence object, matched the
database row digest and evidence inventory/bytes, and left zero unexpected sessions. Its private
joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
The receipt truth is intentionally narrow: recovery consistency is true, while source-writer
quiescence, authoritative source completeness, authoritative same-snapshot capture, unexpected
source-vault exclusion, target-schema authenticity, migration, cutover, release and purge authority
are false. Protected ports and retained data were not used. The next 0029 recovery gate is a
writer-frozen authoritative capture attestation, followed separately by physical/operator,
accessibility/privacy/regulatory, migration/activation and explicit cutover decisions.

That real PostgreSQL run also exposed and closed three adapter defects without widening grants.
Immutable evidence/assessment and consent-policy reads now rely on the already-held canonical
family/organization aggregate lock instead of row locks that require `UPDATE`; A2 first commits
explicitly preserve receipt -> authorization/rule/consent target -> authority-head ordering; and
the first response expires its ORM identity map after commit so database-trigger-authored receipt
timestamps are reloaded exactly like replay. Confidential workspace/policy reads and command
replays recheck the current owner/administrator role after their canonical aggregate lock and fail
403 before projection after role loss. The administrator now presents an actor-specific
maker/checker queue: a maker may reject a wrong submission but cannot review it, while a distinct
owner/administrator can review. Typed person, object, evidence, authorization, rule and consent
links focus and highlight only the addressed row and never substitute a nearby record.

The independent additive `0030_staff_screening_paths` source slice is also verified but not
released. It adds confidential CRC/VSS documents and employer review, educator/student/driver/
combined pathways, structured job and offer duties, exact application disclosure and exact offer
acknowledgment. Pure-driver and student provisioning remain blocked. Educator and combined
pathways can receive educator-only access with no room assignment only after current employer ECE
verification, accepted human CRC/VSS review and exact offer acceptance. Candidate licence/vehicle
claims never create operational driver or child-transport authority. The full evidence and open
release work are recorded in `docs/PRODUCT_IMPLEMENTATION_LEDGER.md`.
Completed candidates can manage and version their screening records from the staff-app profile;
interrupted confirmations resume, name mismatches require explicit reconciliation and same-pathway
driver-declaration changes do not reopen completed onboarding. Application disclosure snapshots
remain immutable and changed evidence applies through withdrawal/reapplication.

The additive `0031_driver_vehicle_registry` source foundation is also staged and unreleased. It
adds immutable driver/qualification facts, independent employer authorization, versioned personal
vehicle/evidence metadata and a private self projection. PostgreSQL RLS/runtime grants are
read-only, the administrator manager workspace remains unavailable, and the staff-app view appears
only behind the exact complete schema marker. Every source, API and client boundary keeps
`operational_driver_ready=false` and `dispatch_authorized=false`; 0031 contains no child, address,
plan, route, manifest, trip or dispatch workflow. Portable gates are green, but a disposable
PostgreSQL 17 high-port gate is also recorded as green. Every registry mutation and release gate
remained open at the 0031 boundary.

The accepted third slice, source revision `0032_transport_commands`, is now source-verified and
unreleased. It adds exact-retry registry commands, encrypted clean-scanned qualification
and vehicle evidence, independent immutable review and expiry/readiness attention records. Its
PostgreSQL design uses a dedicated `NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS` writer owner and a
separate server-only evidence-ingest identity. The normal API and evidence-ingest identities
receive only the exact command-function `EXECUTE` lane and no direct table DML. The administrator
and staff app remain behind the exact full 0032 capability marker. The frozen runtime boundary
pins both canonical hashes for 15 repository/guard functions and the exact topology of 23 enabled
protected-table triggers, plus exact context-lock policies and column ACLs.

0032 source verification is recorded as separate non-additive results: portable backend 123/123;
fresh disposable PostgreSQL 17 behavior/tamper gate 7/7; administrator TypeScript, 591/591 tests
and production build; staff-app TypeScript and 227/227 tests. It still fixes
`operational_driver_ready=false` and
`dispatch_authorized=false` everywhere and contains no child/address/transport-plan/route/manifest/
run/trip/handoff/dispatch/GPS authority. No retained migration or runtime cutover occurred; retained
PostgreSQL remains at `0028_childcare_command_spine`.

The independent finance source track now reaches `0033_billing_ledger`, a verified-source,
synthetic-only and unreleased CAD receivables foundation. It adds versioned accounts/payers,
rates/agreements, visibly watermarked synthetic invoice/payment/allocation/credit facts, balanced
journals, exact preparation/receipt/absence recovery and a capability-gated `/billing` workspace.
Command writes are PostgreSQL-only on explicitly attested, allowlisted test organizations at
disposable loopback high ports; SQLite never authorizes them. No retained migration, real invoice,
PDF/delivery, processor or money movement, refund, tax/funding authority, export or parent portal is
claimed. Retained PostgreSQL remains at `0028_childcare_command_spine`.

The 2026-07-18 operator-defect pass also repaired the administrator family directory so optional
statistics cannot hide its 110 valid records, normalized stored legacy notification destinations
onto the closed route allowlist and made staff-rota dialogs body-portal, viewport-bounded and
internally scrollable. The subsequent 0031/0032 work keeps those fixes green and brings the
administrator through its current no-migration operational checkpoint at 95 files / 614 tests.

The 2026-07-21 no-migration operational checkpoint made notifications exact work-item navigation
rather than generic page links across both clients, while retaining generic lock-screen copy and
authenticated canonical reads. It also added a strict read-only room daily-close preview assembled
from existing attendance, daily-care, medication and incident facts. The preview is available in the
administrator Today workspace and staff-app Records workspace, is bounded to organization/facility/
room/date, and explicitly makes no completeness, compliance or guardian-delivery claim. Backend
regression is 941 passed / 90 explicit opt-in PostgreSQL skips; current staff-app regression is
242/242 plus TypeScript. No migration or retained-database write was needed, and the retained head
remains `0028_childcare_command_spine`.

Live verification then found and closed an optional-capability authorization loop, an ordinary
closed-websocket log exception, and a dead-end enrollment-placement readiness link. Pending-family
placement contradictions now route to an exact family-status task that identifies the child,
family and enrollment and exposes the real edit action; other placement contradictions keep their
generic child-record lane. Dashboard readiness rows are semantic links. Administrator verification
is now 95 files / 614 tests plus TypeScript and an 848-module production build. The retained database
and revision were not changed.
The original V3 attendance
analyzer/scheduler remains hidden from Basic and is preserved for later
advanced integration.

## Non-negotiable boundaries

- Work only in the isolated rebuild unless the user explicitly targets the
  original app.
- Preserve the PostgreSQL database name `caresync` and the isolated runtime
  boundaries below.
- Never reset the active Basic database or delete retained records without an
  explicit backup/release decision.
- Never run Alembic against protected local ports 5432, 5433 or 5434 without
  the exact, command-scoped protected-target opt-in and the recorded backup/
  target-verification procedure. Tests must use a disposable port.
- Never run `alembic upgrade head` or `alembic check` against retained 5434
  while source contains an unreleased migration. Startup is pinned to the
  checked-in released revision, not source `head`.
- Authentication, membership, permission, staff hierarchy and PostgreSQL RLS
  are backend boundaries; UI hiding is never authorization.
- The staged 0029 privileged-actor RLS helper is fail-closed for API-managed
  transaction-local identity/organization context, but it is not proof against
  arbitrary SQL executed with the shared runtime role. Commandized membership/
  role separation is required before production release.
- Planned staff assignments and server-recorded actual clock evidence remain
  separate.
- Realtime is an invalidation channel. Canonical REST reads and immutable
  operation receipts decide whether a mutation committed.
- The staged 0032 repository may record registry evidence and review only. It must keep
  `operational_driver_ready=false` and `dispatch_authorized=false`; neither a database fact,
  capability marker nor client may imply child-transport authority.
- 0032 storage/ciphertext/scanner provenance is server-authored. An authenticated self-service
  caller may upload bytes only through the bounded ingest endpoint; it cannot assert or overwrite
  storage identity, hashes or clean-scan provenance, and restricted runtime identities receive no
  direct registry-table DML.
- Never copy secrets into source, tests, logs or this handoff.

## Project locations

- Original private app: `/Volumes/T7/v1_backup/Documents/Projects/Active/CareSync-Private`
- Isolated rebuild: `/Volumes/T7/v1_backup/Documents/Projects/Active/CareSync-Private-Rebuild`
- Administrator React client: `frontend-redesign/`
- FastAPI backend: `backend/`
- Expo staff app: `/Users/amarmuha/Documents/Codex/2026-07-13/hel/CareSync-Staff`
- Browser extension: `browser-extension/`
- Complete product north star: `docs/ULTIMATE_PRODUCT_CONSTITUTION.md`
- MVP audit: `docs/MVP_READINESS_AUDIT.md`
- Product ledger: `docs/PRODUCT_IMPLEMENTATION_LEDGER.md`
- Rota architecture: `docs/STAFF_ROTA_ARCHITECTURE.md`
- Workforce architecture: `docs/WORKFORCE_PLANNING_ARCHITECTURE.md`
- Staff Exchange architecture: `docs/STAFF_EXCHANGE_ARCHITECTURE.md`
- Child-record command-spine architecture: `docs/CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md`
- Family-authority architecture: `docs/FAMILY_AUTHORITY_ARCHITECTURE.md`
- Family-authority evidence vault: `docs/FAMILY_AUTHORITY_EVIDENCE_VAULT_ARCHITECTURE.md`
- Family-authority release context: `docs/FAMILY_AUTHORITY_RELEASE_CONTEXT_ARCHITECTURE.md`
- Family verified-release checkout: `docs/FAMILY_RELEASE_CHECKOUT_ARCHITECTURE.md`
- Staff screening and child-transport sequence: `docs/STAFF_SCREENING_TRANSPORT_ARCHITECTURE.md`
- Admissions decision spine: `docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md`
- Current retained release: `docs/LOCAL_RELEASE_0039_CUTOVER.md`
- Runtime notes: `docs/REBUILD_RUNTIME.md`

## Local runtime boundary

- Original frontend: `http://127.0.0.1:5173`
- Rebuild administrator frontend: `http://127.0.0.1:5174`
- Original FastAPI: `http://127.0.0.1:3001`
- Rebuild FastAPI: `http://127.0.0.1:3002`
- Legacy rebuild PostgreSQL: `127.0.0.1:5433/caresync` (preserved evidence)
- Active Basic PostgreSQL: `127.0.0.1:5434/caresync`
- Metro: `http://127.0.0.1:8081`

The API runtime uses restricted role `caresync_basic_app`; migrations use a
separate owner identity. Source is on the T7 drive, while PostgreSQL data lives
on the internal disk. Startup removes macOS AppleDouble `._*` sidecars before
Alembic/Vite scanning.

Alembic fails closed on local ports 5432, 5433 and 5434 unless development uses
the exact command-scoped
`CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true` opt-in. Tests cannot bypass
this guard; seven focused tests cover it. `scripts/start-basic.sh` now pins
`RELEASED_REVISION=0039_admissions_decision_spine`, performs no Alembic command
when retained state matches and never infers a newer source head. It
requires exactly one nonblank `alembic_version` row and fails before backup or
migration on empty, blank or multi-head provenance.

The retained database is now at `0039_admissions_decision_spine`. Its guarded
0038-to-0039 promotion followed exact database and evidence-bundle
backup/restore. The earlier 0037-to-0038, 0036-to-0037 and 0028-to-0036
promotions remain historical evidence. Revisions 0029–0036 remain behind separate explicit
facility/manual-billing activations; both activation tables are empty. The
synthetic 0033 sandbox still cannot write on SQLite or protected ports
5432/5433/5434.

Use `scripts/start-rebuild.sh` / `scripts/stop-rebuild.sh` for Basic. The 5433
compatibility backend has separate explicit helpers and is not the default.

## Implemented product boundary

- Public entry, owner registration, authentication and resumable organization/
  facility onboarding.
- Organization, facility, Daycare/OSC program and repeatable room setup.
- Families, guardians, emergency contacts, children, photos, enrollments,
  room-age recommendations and rosters.
- Private administrator admissions: versioned applications, deterministic
  waitlist lanes, program offers, duplicate review, exact retry and atomic
  conversion to Family, Child and pending unassigned Enrollment. The derived
  existing-record remediation queue remains a distinct projection.
- Child attendance plus staff-shift gating for child operational mutations.
- Candidate marketplace, OCR-assisted credential onboarding, jobs,
  applications, interviews, offers, acceptance and staff provisioning.
- The released 0038 public-job catalog outbox durably invalidates formerly
  public listing edits and closure for unaffiliated candidates while exposing
  no organization identity, listing text or candidate/tenant-private facts.
- Staff access/assignment, clock-in/out, room daybook, medication and incident
  workflows with immutable evidence and correction histories.
- User-private notifications, generic push payloads, resumable realtime
  invalidation and exact organization-bound work-item navigation after a fresh
  canonical read.
- Factual room daily-close preview across attendance, six daily-care categories,
  medication outcomes and incident status. It is private/read-only, reconciles
  room and per-child totals, and is explicitly not completion certification,
  compliance evaluation or guardian delivery.
- Daily staff rota: draft/edit/publish/cancel, educator response, alternate-time
  resolution, scheduled/ad-hoc clocking and planned-versus-actual
  reconciliation.
- Workforce planning: recurring availability, time-off lifecycle, reusable
  shift templates and facility/room operational coverage targets.
- Staff Exchange: recurring rotation drafts, open-shift interest and explicit
  manager offers, staff-owned substitute opt-in, and consent plus manager
  approval for atomic whole-shift cover/trade replacement.
- Child-domain command spine: optimistic versions, exact-retry operation IDs,
  actor-private reconciliation, append-only receipts, temporal family contacts,
  active enrollment invariants, program-scoped capacity checks and actionable
  record-readiness routes.
- Released local in 0036: confidential family-authority workspace, complete
  authority-person lifecycle, private evidence-object upload/quarantine/scan/download and
  authority-evidence record/review/reject/invalidate/supersede lifecycle, plus A2 administrator
  release authorization/rule and policy/consent commands. Verified-release
  checkout remains unchanged until explicit per-facility activation; retained
  activation count is zero.
- Released local in 0036: 0030 confidential screening-to-hire, the 0031 read-only private
  driver/vehicle registry and the 0032 exact-retry registry command/evidence/review boundary.
  Their capability-gated clients are deliberately non-authorizing. They are in
  retained PostgreSQL, but none grants operational child transport authority.

The browser extension remains a separate operational utility. The advanced V3
attendance analyzer remains hidden from Basic navigation and is not part of
this workforce slice.

## Foundational `0026_staff_workforce` safety contract

- Missing availability means unspecified; a saved empty profile means
  explicitly unavailable. Reset is a tombstone, not a runtime row delete, and
  exposes the recorded operation ID for response-loss recovery.
- Availability mismatch is soft only at publication. A manager must give a
  nonblank audited reason stored on the published shift. Blank evidence is also
  rejected by a database check.
- Approved time off is a hard, non-overridable membership-wide conflict across
  facilities. Publishing against approved leave and approving against any
  published overlap serialize on the same staff lane; one side must fail.
- Time-off categories are `vacation`, `sick`, `personal`, `medical`,
  `bereavement`, `unpaid` and `other`. The server authors `can_cancel`.
- Administrators can read/decide educator workforce rows only; owners retain
  the organization-wide view.
- Templates use facility-local weekday/time, reject DST gaps/folds and create
  ordinary drafts. Exact instantiate retry is checked before mutable template
  state so edit/deactivation cannot break response-loss recovery.
- Coverage emits 15-minute required/published/acknowledged/declined/draft
  cells. Assignment gap excludes declined publications; confirmation gap uses
  acknowledged assignments.
- Current projections use optimistic `updated_at`, caller UUID operations,
  immutable events, forced tenant RLS and least grants. A retry superseded by a
  later mutation returns `409 operation_superseded`, never a false receipt.

## `0027_staff_exchange` safety contract

- Rotation patterns are reusable planning sources. Preview is bounded and
  digest-bound; generation revalidates every occurrence and creates ordinary
  drafts only, never silently published work.
- Open-shift interest is not an assignment. Only explicit educator acceptance
  of a manager offer can atomically fill the post and create one published,
  acknowledged scheduled shift.
- Approved leave remains a hard blocker. Staff-authored acceptance may record an
  availability exception, but no manager can override approved leave through
  the exchange flow.
- Substitute discovery requires active assignment and staff opt-in and omits
  private notes, leave categories/reasons and the identity of the person being
  replaced.
- Counterparty consent moves a cover/trade request to manager review; it never
  changes a shift. Manager approval rechecks exact source versions and all
  constraints, then cancels and replaces the whole request all-or-none.
- One schedule cannot simultaneously source an open-shift replacement and a
  swap. Provenance and unique source indexes prevent duplicate replacements.
- Every mutation uses immutable exact-retry receipts, forced tenant RLS, least
  grants and deterministic locking. Mobile retains one encrypted identity-bound
  unresolved rota command; realtime only invalidates canonical REST state.

## Released `0028_childcare_command_spine` safety contract

- The audit found that guardian/emergency-contact replacement calls runtime
  `DELETE` even though the restricted PostgreSQL role intentionally lacks that
  privilege. `0028` fixes this with temporal retirement/history, not a broader
  destructive grant.
- Family, child, enrollment and placement commands gain positive versions,
  client operation IDs and an append-only tenant receipt ledger. Same intent
  replays; changed intent and stale versions fail without partial writes.
- New enrollment begins pending and unassigned, then uses the existing
  approval-first DOB/capacity validator. One child has at most one open
  organization enrollment in the bounded MVP policy.
- Existing imported null/false/missing values remain unchanged and become
  human review signals. They are never converted into denial, consent,
  authorization or non-compliance.
- A derived record-readiness queue gives administrators direct remediation
  paths. It is operational review, not a legal-compliance certificate.
- Verified pickup/custody/consent evidence and immutable checkout-recipient
  snapshots are explicitly staged for `0029_family_authority`; until then,
  checkout remains attendance evidence only.
- The verified `0028` gate set includes: actor-private durable
  reconciliation of an unresolved command after reload; active-family checks
  across enrollment and placement; evidence-safe retroactive enrollment ends;
  immutable one-way PostgreSQL care-network retirement; resolvable readiness
  routes; bounded purpose-specific family and child directory/selector
  responses; program-scoped licensed capacity; commitment-safe room/program
  shrink and deactivation; creation/retirement receipts enforced for every new
  care-network row; restricted-role writable startup; and NOBYPASSRLS plus
  deterministic concurrency checks. Those source and local-release gates are
  now closed; physical operator and regulatory acceptance remain separate.
- Alberta's current regulation defines licensed capacity separately for daycare,
  preschool and out-of-school care. The sealed backup agrees: its facility has
  separate 160-space Daycare and 160-space OSC programs. In `0028`,
  `facility_programs.capacity` is authoritative; do not sum both programs under
  the ambiguous legacy `facilities.licensed_capacity` field. Preserve that field
  until a later licence-record migration gives it an explicit meaning or retires
  it.

## Historical 0028 migration and release evidence

This section preserves the 0028 checkpoint and the source-only state that
followed it. Its old revision pins and “not released” statements are historical
and do not override the retained 0039 checkpoint at the top of this handoff.

At that checkpoint, the frozen released source baseline and isolated live-local
database both extended through `0028_childcare_command_spine`; working source
additionally contained staged, unreleased 0029A/A1/A2/B/C/D, verified-source
0030/0031/0032 and synthetic-only verified-source 0033 work. The verified
pre-migration backup for that checkpoint is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260717-120050-877200.json.gz`;
its manifest is beside it as
`caresync-postgres-20260717-120050-877200.json.manifest.json`.
It is a private v2 artifact containing 1,830 rows across all 71 pre-migration
tables. Its compressed SHA-256 is
`64220acf9e233ef81571305324239b77d9c9cd70df0dfd761ef21d41ae89553d`,
its uncompressed JSON-lines SHA-256 is
`712000703124bdb9e4e7b98ec21955e8003ac0db2718044e1868da541cfae893`, and its
canonical row-only SHA-256 is
`5378a43b7dd7c5bb058dac5790a9ba6a15d60adf81de075e56b715580767c325`.
The exact restore receipt is retained under
`~/Library/Application Support/CareSync Basic/restore-verifications/`.
T7 project copies are ExFAT mirrors only. The canonical internal backup
directory is `0700`, its artifacts are `0600`, and future startup cutovers use
that internal location by default.

Before live Alembic ran, startup quiesced CareSync writers, created the backup
from one read-only snapshot, restored it into a fresh disposable PostgreSQL 17
database and verified every table count and the row-only digest. The live
upgrade then added six empty command/reconciliation tables, increasing the
public table count from 71 to 77 without rewriting imported product records.
All six tables have RLS enabled and forced. The runtime remains
`caresync_basic_app`, non-superuser, NOBYPASSRLS, with a pinned
`public, pg_catalog` path and no owned database objects.

Final gates recorded 387 passing default backend tests with 41 expected opt-in
database skips; 38/38 isolated PostgreSQL application/concurrency checks; 1/1
fresh-process `0027 -> 0028 -> 0027 -> 0028` migration gate; maintained-source
Ruff and bytecode compilation green; and successful full-schema restore drills.
The administrator client passed 471 tests across 79 files, TypeScript and an
830-module build. The staff app passed 138 tests, TypeScript, Expo Doctor 20/20
and a 740-module Android export on the current Expo SDK 57 patch set.

Post-cutover API health and the administrator portal returned 200. An already
authenticated client re-established both realtime streams after restart. A
full operator walkthrough of the new child-domain command UI, physical-device
acceptance, accessibility, privacy and Alberta regulatory review remain
separate from this local technical release.

During later 0029 verification, a plain Alembic command inherited `.env` and
briefly applied the empty `0029A_family_authority_kernel` schema to retained
port 5434. Before recovery, all ten new tables and all authority/new-target
receipts were confirmed empty. The exact empty-only downgrade restored
`0028_childcare_command_spine`; an independent read-only transaction then
confirmed revision 0028 and zero authority tables. This was a temporary schema
advance, not a row migration, and remains part of the permanent record.

The private post-recovery v2 backup is
`/Users/amarmuha/Documents/Codex/2026-07-13/hel/caresync-incident-backups/caresync-postgres-20260717-200103-673906.json.gz`;
its manifest is beside it and its compressed SHA-256 is
`d83dfaea0410f03c591d441c5b0f6fe96e863d32f1204e154d34fb3390480fad`.
An exact fresh-disposable restore reproduced revision 0028, 1,834 rows across
77 tables including `alembic_version`, 203 children, 110 families and zero
authority tables. The backup directory is `0700` and artifacts are `0600`.

The incident produced two operational hardening changes. Alembic now blocks
ports 5432, 5433 and 5434 unless development supplies the exact command-scoped
`CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true`; tests cannot bypass the
guard and seven tests cover it. `scripts/start-basic.sh` is now pinned to
`RELEASED_REVISION=0039_admissions_decision_spine`, skips Alembic when retained
state matches and never infers a target from a newer source head.

### A/A1/A2/B/C/D family authority — pending guarded 0036 cutover

The corrected source kernel adds ten canonical empty authority/evidence tables and six additive
legacy composite identities; A1 adds two evidence-object tables and one nullable unique object link
on evidence. A2 activates four existing administrator decision tables, adds immutable policy
`content_text`, adds a second distinct consent signer-authority evidence tuple and adds the
`signed_release_delegation` document kind. Its strict schemas, layered feature gates, confidential
family workspace, authority-person
create/full-replace/terminal-retire services and authority-evidence
record/review/reject/invalidate/supersede lifecycle are verified. Exact retry,
immutable assessment history, historical lifecycle closure, actor privacy,
stable child-head invalidation, missing-head rollback, direct-SQL constraints
and restricted-role behavior are covered.

A1 implements strict PDF/JPEG/PNG multipart intake, no-clobber private publication, measured
media/size/SHA-256, version-one quarantine, fixed-adapter ClamAV scanning, a resource-bounded
isolated document parser, terminal clean/rejected assessment history, exact-retry receipts,
single-use clean-object evidence binding, private clean download and distinct maker/checker review.
Rejected and invalid-document bytes remain canonical private objects. The backup companion bundle
includes every persisted byte, and the reconciler is report-only and never deletes.

A2 writes `child_release_authorizations`, bounded `deny`/`manager_review`
`child_release_rules`, immutable `consent_policy_versions` and withdraw-only
`child_consent_decisions`. The exact positive lanes are guardian attestation, custody document and
original-guardian signed release delegation for authorization; guardian/custody for rules; and a
distinct `signed_consent` tuple plus guardian-attestation or custody-document signer authority for
consent. Every unlisted pairing is non-activating. Policy callers submit readable immutable
`content_text`; the server derives its hash and `/consent-policies/{id}` reference. The A2 startup
gate proves structural shape, forced RLS, triggers and exact grants before an A2 ORM query. At the
A2 boundary, `attendance_release_snapshots` remained SELECT-only; staged C source extends that
boundary without changing retained state.

The 2026-07-18 closeout recorded 170/170 passing focused authority regressions and relevant
Ruff/bytecode gates. The administrator passed TypeScript, 81 test files / 501 tests and a
production build of 834 modules. These counts overlap. A disposable PostgreSQL 17 run passed 3/3
A2 gates covering fresh migration to `0029A2_authority_activation`, no drift, bootstrap/runtime
identity, forced RLS/exact grants, positive activation commits, database-negative matrix and
maker/checker behavior, and populated downgrade refusal. The disposable cluster was removed and
protected ports were not contacted. At that historical checkpoint these source gates did not
establish a signed-in scanner/vault operation or local release; the later hardened synthetic
scanner receipt remains adapter proof only.

`0029B_release_context` adds no authority or attendance mutation. It exposes one strict no-store
GET through a hardened narrow projection, deterministic fail-closed composer and separate
structural runtime detector; emits only generic null-entity authority-head invalidation; and keeps
the staff response in memory behind a monotonic expiry lease. The staff panel is read-only and
does not call or claim verified checkout.

The 2026-07-18 B closeout passed 84/84 portable API/composer/migration/detector tests and 7/7 real
disposable PostgreSQL tests on an unprotected high port. The PostgreSQL proof covered the complete
detector, fail-closed rejection after a hardening revoke, restoration, the operational gate matrix,
the 400-transition common-snapshot race and exact projection/migration behavior. The administrator
remained green at 81 test files / 501 tests plus TypeScript/build;
the staff app passed 153/153 tests, TypeScript and an Android export transforming 744 modules.
The complete default backend regression passed 648 with 81 explicit opt-in skips and zero failures.
The disposable cluster was removed and protected ports 5432/5433/5434 were untouched. These are
source/disposable proofs only.

The owner/admin child-profile summary adds a separate no-store projection and does not reuse the
educator B response. It accepts either no focus query or exactly one typed
`focus=release_authorization|release_rule|consent` plus a UUID `record_id`; malformed, partial,
duplicate or unknown query keys fail with a typed validation response, and a missing or wrong-child
target fails without nearest-record substitution. Projection is bounded to 200 rows per lane,
bulk-loads evidence/person facts at a constant query count, rechecks current owner/admin membership
under lock and omits contact, evidence, provenance, confidential reason and policy-body data.
Canonical `child_authority_head` events carry a null entity ID and invalidate the family, child
summary and staff release-context consumers.

`0029C_verified_release_checkout` has strict Python and TypeScript contracts, the portable atomic
command/exact-retry foundation, dormant facility activation and activated-facility legacy closure.
`0029D_release_checkout_writer` adds the restricted PostgreSQL normal-release writer, post-lock
database time, same-transaction event/receipt/snapshot/interval bundle, exact actor-bound replay,
runtime detector and least-privilege bootstrap. The staff confirmation flow is imported behind the
server capability and protects recoverable pending operations. Disposable PostgreSQL evidence is
recorded in the product ledger. No retained migration, facility activation, operator walkthrough
or production certification is claimed. C/D provide only the normal verified-release workflow;
software override remains deliberately deferred.

### Staged 0030 staff screening — not released

`0030_staff_screening_paths` is candidate-to-offer and bounded educator provisioning source. Raw
screening files remain in the confidential encrypted vault; application disclosure and employer
review bind exact immutable versions. PostgreSQL RLS/ACL/policy drift is startup- and
bootstrap-audited, including the superuser bootstrap path. The complete backend suite passed
841 tests with 87 explicit opt-in skips and zero failures. A separate disposable PostgreSQL 17 run
passed 4/4 screening and provisioning gates. The administrator passed 549 tests plus
TypeScript/build; the staff app passed 205 tests plus TypeScript. Counts overlap and do not claim a
retained release. Signed-in 0030 scanner/vault operation, vault key rotation/reconciliation,
retention/purge, concurrency,
immutable ECE evidence binding, police-check freshness, self-review separation and all operational
vehicle/transport authority remain open. The completed-candidate evidence-versioning and
reapplication UX is source-verified but remains unreleased with 0030.

### Staged 0031 driver/vehicle registry — read-only and not released

`0031_driver_vehicle_registry` supplies append-only driver declarations, latest-per-type
qualification facts, independent authorization decisions, immutable vehicle/evidence versions and
explicit incomplete/blocked readiness facts. It enforces independent review and prevents an
authorization from outliving its exact verified licence. Forced PostgreSQL RLS and the runtime role
permit reads only. The only HTTP addition is the fail-closed capability marker plus the signed-in
member's private no-store registry projection. Admin manager navigation stays absent; the staff
app presents the projection read-only and rejects any expanded/private/authority-granting payload.

Focused backend verification passed 21 tests; an independent compatibility run passed 18 tests
and Ruff. Admin passed TypeScript/build and 560 tests. Mobile passed TypeScript and 209 tests. These
overlap and do not claim release. Portable SQLite reached 0031. A fresh isolated PostgreSQL 17
high-port certification passed 1/1 comprehensive gate, including full migration, forced RLS,
restricted grants, two-dimensional self isolation, immutable facts, reviewer/expiry guards, bounded
private projection and populated-downgrade refusal. It caught and closed one PostgreSQL reserved-word
syntax defect and one organization-context RLS gap. The bounded command/evidence/review workflows
and generic expiry attention are implemented by verified-source 0032 below; every child transport
plan/dispatch/trip workflow remains open. Retained port 5434 was not migrated and remains at 0028.

### Verified-source 0032 transport registry commands — not released

`0032_transport_commands` is the accepted third slice above the read-only 0031 registry. Its
bounded command families cover driver declaration/withdrawal, server-ingested qualification
evidence, independent qualification review, driver-authorization decisions, vehicle create/
version/retire, server-ingested vehicle evidence, independent vehicle-evidence review and
point-in-time readiness evaluation.

The non-negotiable implementation shape is:

- exact actor/organization/operation binding, a canonical request digest and one atomic result,
  audit event and retry receipt;
- a dedicated non-login/non-superuser/non-bypass-RLS owner for the only PostgreSQL
  `SECURITY DEFINER` command repository;
- `EXECUTE`-only normal-runtime and server-only evidence-ingest lanes, with no direct table DML;
- encrypted source objects, server-measured hash/size/media metadata and clean scanner provenance
  that cannot be asserted by the client;
- current same-tenant manager review with reviewer distinct from the subject/owner and source
  uploader;
- latest-version, current-authorization and expiry-aware readiness records with generic,
  deduplicated attention destinations; and
- exact capability-gated administrator/mobile surfaces that fail closed on partial, extra,
  crossed-tenant or authority-granting payloads.

The migration/detector/bootstrap/repository/API contract is frozen and canonically sealed. Startup
and bootstrap pin normalized `prosrc` plus `pg_get_functiondef` hashes for all 15 command/guard
functions and the exact 23 enabled protected-table triggers. The verification matrix proves role
ownership, exact grants, no direct DML, forced RLS, lock-without-mutation, exact retry, rollback,
tenant/actor isolation, concurrent revocation safety, independent review, clean-scan binding,
expiry/latest-version evaluation and unconditional false authority. Tamper cases cover weakened
function source retaining marker text, replica-only and extra triggers, context-policy drift and
column-ACL drift.

The portable backend gate passed 123/123 and the fresh disposable PostgreSQL 17 command/tamper gate
passed 7/7. Administrator TypeScript, 591/591 tests and production build passed. Staff-app
TypeScript and 227/227 tests passed. Focused suite counts overlap these results and are not summed.

The next source-only readiness pass now keeps 0030 schema availability separate from confidential
document upload readiness. When 0030 exists, startup probes the private staff vault, active key and
scanner independently of the 0032 evidence database identity; retained 0028 skips that probe. The
health route and `/marketplace/me` publish only generic readiness, and the staff app disables only
new/replacement screening uploads while preserving history, pending confirmation, declarations and
sharing. A connection-invalidated 0030 commit retains ciphertext and requires a canonical history
reload before retry; deterministic failures still delete their unadopted object. Reads fail closed
when a row names any key ID other than the configured active ID. This is a safety boundary, not a
historical keyring or rotation claim.

The source-only staff/transport vault preflight is now a backup-derived, report-only control. It
pins verified logical backup artifacts, derives and de-duplicates the three encrypted evidence
inventories, validates their distinct ownership shapes, performs descriptor-relative no-follow
ciphertext size/digest measurement and writes one private no-clobber receipt. It never opens a
database, loads a key, decrypts, restores, migrates, deletes or purges. Every receipt says
`consistencyAuthority=false`, `purgeAuthority=false` and
`blocker=snapshot_boundary_unproven`; it therefore cannot close the authoritative same-snapshot
backup/restore, orphan-adoption or purge gates.

The companion encrypted-vault bundle now closes deterministic archive/verify/disposable-restore
for the exact inventory in one verified logical backup. It preserves all screening, qualification
and vehicle history, validates ownership and ciphertext metadata, rejects any missing, unexpected,
linked, non-private, duplicate or tampered object, and writes only private no-clobber artifacts.
Restore recreates a new root and publishes its receipt only after exact remeasurement. This is not
writer-quiescence evidence and does not include the separate `staff-screening-vault.key`; key
custody, key-ID coverage and rotation/rewrap remain explicit gates.

This bundle does not own the separate transport evidence-ingest database
credential. Retained password-authenticated PostgreSQL requires the
`caresync_transport_evidence_ingest` login role password to be provisioned from
the stable private `transport-evidence-ingest.password` used by the API. A role
that is only created/normalized, without having that password set, leaves
evidence ingest unavailable; retained cutover needs a non-printing provisioning
step and a password-authenticated intake probe.

Real scanner/vault operation, vault-key custody and rotation, crash reconciliation, retention/
legal-hold/purge policy, writer-frozen retained capture/restore attestation, operator and
physical-device acceptance, accessibility/privacy/regulatory acceptance and an explicit retained
cutover decision remain release work.
Protected ports 5432/5433/5434 must not be used for disposable gates. Retained port 5434 remains
released 0028.

0032 always records `operational_driver_ready=false` and `dispatch_authorized=false`. It has no
child, family address, transport plan/consent, route, manifest, run, trip, handoff, dispatch,
GPS/location tracking or offline trip pack. Do not use it as a foundation for ad-hoc child rides.

The final verification commands are separate records and their counts must not be summed. The full
default backend suite passed 935 tests, skipped 90 expected explicit opt-in PostgreSQL tests, had
zero failures and emitted 7 deprecation warnings. The 0032 portable subset passed 123/123 and the
separate fresh disposable PostgreSQL 17 gate passed 7/7. The administrator passed TypeScript,
591/591 tests and a production build of 843 modules. The staff app passed TypeScript and 227/227
tests. Neither the skipped PostgreSQL tests nor the warnings are represented as production,
operator, physical-device or retained-cutover certification.

### Verified-source 0033 billing ledger — synthetic only and not released

`0033_billing_ledger` replaces neither the legacy invoicing data nor the retained Basic release.
Its bounded command set opens an account, assigns a payer, publishes a rate version, establishes an
agreement, records a synthetic invoice, records a synthetic manual payment, allocates payment and
issues a synthetic credit. All effects use integer CAD minor units, append-only/versioned facts,
balanced journal entries, actor-private operation IDs, server-prepared request hashes, exact retry,
mutually exclusive receipt/absence terminals, audit and generic realtime invalidation.

The write boundary is PostgreSQL-only and requires test mode, writable sandbox mode, the exact
disposable-target attestation, an allowlisted organization, synthetic-source attestations and a
loopback high port other than 5432, 5433 or 5434. SQLite supports portable schema and
disabled/shadow-read gates only. The normal restricted role has only the exact 0033 append/select
surface; startup rejects partial schema, grants, policies, functions or trigger topology.

The administrator `/billing` route is owner/administrator permission gated and labels every invoice
`TEST/SYNTHETIC — NOT A REAL INVOICE`. Its eight canonical collections are accounts, full
historical `payer_versions`, rate plans, agreements, invoices, payments, allocations and credits.
Every invoice pins the exact payer-version and guardian provenance used at record time, so later
payer reassignment affects future work without rewriting, relabelling or invalidating prior
invoices. All pages are assembled under one snapshot token; drift, duplicates, crossed tenancy,
missing references and arithmetic disagreement fail closed. Basic `/invoicing/*` remains NotFound.

Focused evidence is PostgreSQL 16 6/6, fresh disposable PostgreSQL 17 6/6 after the final
trigger/detector edits, portable SQLite 8/8 with command writes forbidden, administrator 110 test
files / 746 tests plus TypeScript and production build, and whole backend 1048 passed with 100
intentionally opt-in PostgreSQL tests skipped and 7 deprecation warnings recorded.

Signed-in synthetic browser acceptance passed. The sandbox boundary loaded; an account opened with
Priya as payer version 1; a rate and agreement were created; and a CAD 100.00 invoice was issued for
a fully covered August period. Reassigning the account to Samir as payer version 2 preserved
Priya/version 1 on the invoice. A CAD 40.00 receipt, CAD 20.00 allocation and CAD 10.00 credit left
CAD 70.00 outstanding and CAD 20.00 unapplied; reports/readiness reconciled and live snapshots
advanced. The run exposed a July effective-period gap. The corrected client requires full inclusive
agreement and pinned-rate coverage, disables Review when coverage is incomplete, and was visually
reverified. This is synthetic source acceptance, not retained-runtime or production evidence.

0033 has no real invoice/PDF/statement generation or delivery, processor, capture/settlement,
refund/chargeback, tax determination or receipt, Alberta funding rule/claim, accounting close or
export, parent portal, retained migration or production cutover. Synthetic configured funding and
tax arithmetic are not eligibility, legal/accounting advice or external financial facts.

The 0029 privileged-actor helper fails closed under API-managed
transaction-local user and organization GUCs. The shared runtime role can set
custom GUCs, so these policies do not secure arbitrary SQL using that role;
future commandized membership/role separation must close that production
boundary.

The live-local retained runtime was re-read in an explicitly read-only
transaction after recovery: port 5434 is at
`0028_childcare_command_spine` and contains zero authority tables. No product
or authority rows were migrated or rewritten, but the temporary schema advance
is disclosed above. Snapshot INSERT remains withheld from the retained runtime;
the 0029C attendance provenance, server-time restriction recomputation,
verification-policy and checkout race gates recorded in the checkout
architecture cannot be waived by UI or service code.

ClamAV is installed on the development host. Independent review hardened the adapter against
ClamAV's default clean verdict on resource-limit exhaustion: `clamscan` now receives
`--alert-exceeds-max=yes`, while `clamdscan` fails closed until its daemon-side policy can be
attested. The replacement 2026-07-22 synthetic scanner certification passed clean,
harmless-test-signature rejection, configured-unavailable and post-version scan-process-failure
cases, normalized raw version output, enforced a complete receipt shape and wrote the private
mode-0600 receipt documented in `docs/FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`. Focused Ruff, 17
real-inclusive scanner/certification tests and 17 staff-vault hardening tests passed. Detached
`main-63`, `daily-28068` and `bytecode-339` signatures were independently verified with `sigtool`
under `ClamAV_datafiles_release`. The earlier receipt is superseded, not deleted. A passing receipt
proves only this bounded adapter behavior; it is not a signed-in authority operator flow or 0029
cutover. The staged 0029C portable writer and legacy closure are not runtime activation, PostgreSQL
certification or permission to write a retained release snapshot. B remains read-only.

The later signed-in synthetic-only operator receipt closes the separate bounded A/A1/A2 public-
HTTP maker/checker and scanner/vault workflow described above; it does not broaden the scanner-only
receipt or certify physical checkout. The still later synthetic exact-0029D joint receipt closes
only consistency of the four fixed recovery artifacts and their restored database/vault result.
It does not prove that an authoritative source was complete or writer-frozen when those artifacts
were captured. Neither the operator receipt nor either component restore receipt grants recovery,
release or cutover authority by itself.

The report-only reconciler does not authorize purge. A future purge requires two verified
snapshots with authoritative `snapshotEstablishedAt`, at least 30 days of unchanged absence,
writer/database quiescence, exact purge-plan digest confirmation and durable per-object receipts.

## Deliberately later workforce work

- Partial-shift trades, split coverage and multi-party exchanges.
- Automatic award/bidding algorithms and safe replacement optimization.
- Leave balances, accrual, blackout periods and document policy.
- Break/rest/overtime/statutory-holiday and employment-rule evaluation.
- Qualification-aware and attendance/ratio-aware regulatory coverage.
- Timesheet correction/approval, payroll/time export and complete HR records.
- Labor budgets, demand forecasting, optimization and safe replacement search.
- Calendar synchronization and manager mobile authoring.

Non-blocking Staff Exchange scale hardening also remains: cursor pagination and
prefetching for high-cardinality reads, production load tests, a durable outbox
with bounded competing-engagement fanout, resource-scoped advisory locks and
possible deferred constraint triggers for the remaining application-enforced
cross-row provenance rules.

Remote Expo/FCM delivery credentials and full terminated-app push acceptance
also remain deployment work. A local Android development client proves native
installation and local connectivity, not production push delivery.

Physical-device/operator, accessibility, privacy and regulatory acceptance
remain required despite the green automated and runtime gates. The prior 0027
signed-in browser evidence remains historical; the 0028 child-command operator
walkthrough is still open.

## 0041/0042 continuation override

The detailed historical records below preserve dated evidence. Continue from
these current facts:

- retained port 5434 remains at `0039_admissions_decision_spine`; checked-in
  source and the launcher target are `0042_billing_policy_recert`;
- no 0041 or 0042 retained migration/cutover occurred, and retained services
  must not be restarted through the 0042-pinned launcher until guarded
  promotion is authorized;
- backup stem `caresync-postgres-20260723-052743-592770` captured exactly
  16,445 rows across 135 source tables at 0038; fresh port-56555 restore matched
  row digest
  `7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`;
- both required vault restores contained zero objects and produced private
  receipts;
- retained 0039 has 141 public tables plus one view and exactly 16,445 rows,
  including 110 families, 203 children and 197 enrollments; all six admissions
  tables are empty;
- admissions is a private administrator lifecycle with deterministic waitlist,
  program offers, exact retry, duplicate review and atomic canonical
  conversion; remediation remains a separate derived projection;
- verified child release and private manual billing remain separately
  owner-controlled, and both retained activation tables are empty;
- integrated acceptance is backend 1,997 passed / 105 skipped / seven warnings,
  focused backend 22, two green PostgreSQL 17 runs, administrator 125 files /
  841 tests, staff app 272 and extension 78, with TypeScript/build, release-pin,
  Ruff and bytecode gates green;
- API, administrator and billing sandbox health are green; signed-in Admissions
  loaded every canonical read projection without a visible error or write, and
  destructive lifecycle proof stayed disposable;
- `0040_billing_readiness_batch_planner` is verified in source and retained
  live read-only API acceptance, limited to deterministic setup planning,
  no-write preview and explicitly reviewed reuse of canonical account, payer,
  rate and agreement commands; it has no schema migration, activation,
  invoice, payment, provider or funding behavior, and retained Alembic stays
  exactly at 0039;
- focused 0040 evidence is backend planner 9 passed, portable billing 34 passed
  / 1 skipped, PostgreSQL 17 RLS/no-write 1 passed, administrator 128 files /
  865 tests and a green 881-module production build;
- the separately backed-up port-3302/5274 billing sandbox is disposable test
  preparation explicitly migrated from 0033 to 0039, not an 0040 migration or
  retained cutover;
- signed-in administrator browser-click acceptance for
  `/billing?view=setup` remains pending; and
- verified 0041 adds actual room-presence truth, exact-retry transitions,
  child-operation room gating, factual configured-target boards, append-only
  exceptions and canonical realtime/notifications without making a regulatory
  compliance claim;
- verified 0042 accepts only exact whole billing-policy profiles A/B,
  canonicalizes all 36 frozen 0033 policies and adds no billing authority;
- disposable migration preservation is 16,508 rows / 140 pre-0041 business
  tables, count digest
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`,
  row digest
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`,
  pre-0041 backup SHA
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`
  and pre-0042 backup SHA
  `55be096d31c90b33cb7f19e625b472defbb60387d4dd56a7fb1fdec0f9a7490c`;
- final 0041/0042 evidence is all 135 backend files, focused 45 passed / one
  opt-in skipped, both fresh PostgreSQL 17 gates, administrator 193 and Staff
  app 297 with TypeScript/build/Doctor/export gates green;
- load `docs/LOCAL_RELEASE_0039_CUTOVER.md`,
  `docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md`,
  `docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md` and
  `docs/PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md`,
  `docs/LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md`,
  `docs/PRODUCT_SLICE_0041_LIVE_ROOM_PRESENCE_SAFETY_BOARD_RELEASE_NOTE.md`
  and `docs/PRODUCT_SLICE_0042_BILLING_POLICY_RECERTIFICATION_RELEASE_NOTE.md`
  with the required context set.

## Historical 0038 continuation override

The detailed historical records below preserve the 0038 checkpoint:

- retained port 5434, source, Alembic head and the checked-in launcher target
  are `0038_public_job_catalog_outbox`;
- backup stem `caresync-postgres-20260723-022822-921802` captured exactly
  16,335 rows across 134 source tables at 0037; fresh port-56553 restore matched
  row digest
  `f0c93cd10395d24816292fc20b761ce262bb666ffeeab5776959c5bc817b5472`;
- both required vault restores contained zero objects and produced private
  `0600` receipts;
- retained 0038 has 135 public tables plus one view and 16,339 rows, including
  two catalog rows and the organization/user realtime tickets created by live
  browser reconnect; it preserves 110 families and 203 children;
- eligible public job, migration backfill and current projection counts are
  `1/1/1`, and every backfill identity matches its canonical parent;
- source tables remain `FORCE RLS`; catalog RLS is enabled without FORCE;
  runtime access is `SELECT` only; `PUBLIC` has no grant; the enabled trigger
  uses the attested `SECURITY DEFINER`, fixed-`pg_catalog`, non-runtime-owned
  function;
- verified child release and private manual billing remain separately
  owner-controlled, and both retained activation tables are empty;
- integrated acceptance is backend 1,979 passed/104 skipped, focused
  915/2, PostgreSQL 3/3, administrator 808/808, staff app 272/272 and extension
  78/78; API, administrator and billing sandbox are healthy and signed-in Jobs
  is realtime-connected;
- at that checkpoint `0039_admissions_decision_spine` was the next planned
  architecture-only slice; it has since completed the guarded release above;
  and
- load `docs/LOCAL_RELEASE_0038_CUTOVER.md` and
  `docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md` with the required context
  set.

## Historical 0037 continuation override

The detailed historical prompts below preserve dated evidence. Continue from
these current facts:

- retained port 5434, source, Alembic head and the checked-in launcher target
  are `0037_billing_agreement_scope`;
- the guarded 0036-to-0037 cutover exactly restored 16,309 rows across 134
  source tables, verified both evidence bundles, preserved 110 families and
  203 children, and retained 134 public tables plus one view;
- 0037 scopes ordinary immutable billing agreements to an enrollment and
  preserves a partial null-enrollment legacy fallback; it does not replace the
  0036 private/manual command protocol;
- verified child release and private manual billing remain separately
  owner-controlled, and both retained activation tables are empty;
- enrollment-to-billing readiness and family/child finance summaries are
  integrated; family invoices own settlement truth and child summaries are
  attribution-only;
- the supported hiring boundary is canonical ATS/marketplace, with zero
  mounted legacy hiring prefixes and no legacy-record migration required;
- at that checkpoint, `0038_public_job_catalog_outbox` was the next bounded
  slice; it has since completed the guarded local release recorded above; and
- load `docs/LOCAL_RELEASE_0037_CUTOVER.md` with the required context set.

## Historical 0036 continuation override

The detailed suggested prompt below preserves historical evidence but its old
instructions to keep 0029–0033 source-only and pin the launcher to 0028 are
superseded. Continue from these current facts:

- retained port 5434, source, Alembic head and the checked-in launcher target are
  `0036_billing_manual_mode`;
- the guarded retained cutover is recorded with its 16,260-row / 77-table
  exact 0028 restore, preserved 110 families / 203 children, 134-table plus
  one-view retained result, private backup/manifest/receipt and green
  restricted-role health;
- do not fabricate either activation: verified child release remains
  per-facility owner/administrator review, and private manual billing remains
  per-organization owner review; both activation tables are empty;
- 0036 manual billing records off-platform facts only and has no processor,
  money movement, automatic issue, delivery, tax advice or funding submission;
  and
- continue from the integrated 0036 baseline into bounded
  enrollment-to-billing readiness and family/child finance summaries without
  inventing child-level settlement truth; and
- load `docs/LOCAL_RELEASE_0036_CUTOVER.md` with the required context set.

## Historical suggested continuation prompt

> Continue CareSync by loading, in order,
> `docs/ULTIMATE_PRODUCT_CONSTITUTION.md`,
> `docs/PRODUCT_IMPLEMENTATION_LEDGER.md`,
> `docs/THREAD_HANDOFF.md` and
> `docs/MVP_READINESS_AUDIT.md` and
> `docs/FAMILY_AUTHORITY_ARCHITECTURE.md` and
> `docs/FAMILY_RELEASE_CHECKOUT_ARCHITECTURE.md` and
> `docs/STAFF_SCREENING_TRANSPORT_ARCHITECTURE.md` and
> `docs/BILLING_FINANCE_ARCHITECTURE.md`. Treat the recorded live
> `0028_childcare_command_spine` release as complete. Treat the corrected
> `0029A_family_authority_kernel` persistence, `0029A1_family_evidence_vault` and exact
> `0029A2_authority_activation` revision, strict schemas and verified
> workspace/person/object/evidence/administrator-activation lifecycles as source only, with the retained
> database restored to 0028 after the documented empty-schema migration
> incident. Preserve the protected-port Alembic guard and the isolated
> runtime, exact-retry, consent, temporal-history and planned-versus-actual
> boundaries. Do not treat the API-managed-GUC RLS helper as protection against
> arbitrary SQL with the shared runtime role. Preserve A1's no-clobber private storage,
> quarantine/scan, clean-object binding, maker/checker, canonical rejected-byte retention,
> four-artifact backup consistency set and report-only/no-delete reconciler. Treat the hardened
> local synthetic ClamAV receipt as bounded adapter proof only. Preserve the separate private
> signed-in synthetic-only A/A1/A2 operator receipt as proof of the public-HTTP multipart,
> scanner/vault, maker/checker, exact-replay, generic realtime and admin-summary path on a fresh
> disposable exact-0029D database; it is not physical-device, retained-release or cutover evidence.
> Preserve the separate joint artifact-recovery receipt
> `family-authority-joint-recovery-20260722T172958Z.json` and its hash
> `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a` as bounded proof that one
> already-fixed four-artifact set restored consistently. It deliberately leaves writer quiescence,
> authoritative source completeness/same-snapshot capture, target-schema authenticity and all
> cutover/release/purge authority false. Writer-frozen authoritative capture, physical-device
> acceptance, retained activation and cutover remain open.
> Preserve A2's fail-closed activation
> matrix, two distinct consent evidence lanes, immutable server-hashed policy content, exact grants
> and structural runtime gate. Preserve source-verified `0029B_release_context` as a strict,
> expiring, memory-only read projection with generic invalidation and no checkout claim. Treat
> `0029C_verified_release_checkout` and `0029D_release_checkout_writer` as source verified for the
> normal release path, including the restricted PostgreSQL writer and capability-gated staff flow,
> but not operator evidence, retained migration, facility activation or cutover. Keep software
> override deferred. Treat `0030_staff_screening_paths` as source verified but unreleased: preserve
> confidential exact-version CRC/VSS disclosure and human review, exact structured offer
> acknowledgment, educator-only provisioning gates, driver/student blocks and the absolute absence
> of operational transport authority. Treat `0031_driver_vehicle_registry` as verified-source,
> read-only and unreleased. Treat `0032_transport_commands` as a verified-source, unreleased
> evidence/review command slice: preserve the dedicated non-login writer owner,
> EXECUTE-only normal/evidence-ingest lanes, encrypted clean-scanned evidence, independent exact-
> version review, exact retry, bounded reads, canonical 15-function/23-trigger attestation and
> expiry/readiness records. Keep
> `operational_driver_ready=false` and `dispatch_authorized=false` and do not add or infer child,
> address, plan, route, manifest, trip, handoff, dispatch or GPS authority. Source verification is
> not retained cutover, operator acceptance or transport permission. Retained PostgreSQL stays at
> 0028. Do not reinterpret expected opt-in
> PostgreSQL/scanner skips as executed database or operator evidence. Continue through the remaining
> locked `0029_family_authority` release gates rather than inventing more source scope: writer-frozen
> authoritative database/vault capture attestation, physical Android and checkout/operator
> acceptance, accessibility/privacy/regulatory review, retained migration, facility activation and
> explicit cutover. C/D remain verified source only until those gates are recorded.
> Treat `0033_billing_ledger` as verified source, synthetic only and unreleased. Preserve its visible
> `TEST/SYNTHETIC — NOT A REAL INVOICE` label, disabled-by-default capability, PostgreSQL-only
> command writes on explicitly attested and allowlisted disposable loopback high ports, synthetic
> source lineage, CAD integer minor units, immutable versions, balanced journal, exact
> preparation/receipt/absence recovery, least grants and coherent snapshot-token paging. SQLite may
> provide disabled/shadow reads but never 0033 commands. Keep `/invoicing/*` unavailable in Basic.
> Do not migrate retained 5434, import legacy invoice rows or claim real invoice delivery/PDF,
> processor or money movement, refunds, tax/funding authority, receipts, exports, parent portal or
> production cutover. Retained PostgreSQL stays at 0028.
> Keep the complete
> Product Constitution as the long-term feature north star without pretending
> its backlog is already built, and keep the hidden V3 analyzer outside this
> phase.

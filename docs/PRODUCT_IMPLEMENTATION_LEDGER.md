# CareSync Product Implementation Ledger

Last updated: 2026-07-28

## Purpose

This is the master product index for the private CareSync rebuild. It prevents feature work,
release evidence and deliberately deferred scope from becoming scattered across chat history.
Detailed architecture documents remain authoritative for their individual domains; this ledger
records sequence and completion state.

## Status vocabulary

- **Released local**: migrated into the isolated PostgreSQL runtime, restarted and smoke-tested.
- **Verified source**: implementation and isolated gates are complete but the live-local cutover
  has not yet been recorded.
- **In implementation**: architecture is locked and code is actively being built.
- **Queued**: accepted product direction, not yet implemented.
- **Later**: intentionally outside the current bounded phase.

## Release train

| Revision / phase | Product capability | Backend | Admin | Staff app | Live-local status |
|---|---|---:|---:|---:|---|
| `0001`–`0024` | Tenant foundation, childcare records, care operations, ATS/marketplace, realtime notifications and push infrastructure | Complete | Complete for released slices | Complete for released slices | **Released local** |
| `0025_staff_rota` | Planned staff shifts, educator responses, clock reconciliation and immutable rota evidence | Complete | Complete | Complete | **Released local** |
| `0026_staff_workforce` | Availability, time off, shift templates, operational coverage and audited availability overrides | Complete | Complete | Complete | **Released local** |
| `0027_staff_exchange` | Recurring rotations, open shifts, manager offers, substitute pool and consent/approval-based whole-shift swaps | Complete | Complete | Complete | **Released local** |
| `0028_childcare_command_spine` | Versioned exact-retry child records, non-destructive care-network edits, enrollment invariants and record-readiness queue | Complete | Complete for the bounded command UI; operator walkthrough remains | Regression green: 138 tests/typecheck; no new authority | **Released local** |
| `0029_family_authority` | Custody/release rules, authorized pickup, consent evidence and immutable checkout-recipient snapshots | Complete in the retained schema; restricted writer and recovery controls remain intact | Actor-specific maker/checker workspace, exact authority focus and per-facility activation status/command are released | Server-gated verified pickup and protected exact-retry recovery are released | **Released local in 0036; no retained facility is activated; physical/operator and regulatory acceptance remain** |
| `0030_staff_screening_paths` | Confidential CRC/VSS evidence, educator/student/driver pathways, structured job and offer duties, exact disclosure and offer acknowledgment | Complete in the retained schema; no operational transport authority | Connected screening, identity reconciliation and structured hiring contracts are released | Connected candidate screening and exact hiring contracts are released with outage-safe capability fallback | **Released local in 0036; live scanner/key custody and physical-device acceptance remain separate** |
| `0031_driver_vehicle_registry` | Immutable staff driver/qualification facts, independent employer review, personal-vehicle evidence and private self projection | Complete in the retained schema with read-only projection grants | Registry projection is available only through the intended capability/permission boundary | Capability-gated private registry is released | **Released local in 0036; operational readiness and child dispatch remain false** |
| `0032_transport_commands` | Exact-retry registry commands, encrypted clean-scanned driver/vehicle evidence, independent review and expiry/readiness records | Complete retained command boundary with restricted writer/evidence identities | Capability-gated manager workspace released | Capability-gated self-service registry released | **Released local in 0036; evidence readiness does not authorize child transport** |
| `0033_billing_ledger` | CAD receivables foundation with full payer/rate/agreement history, immutable invoice/payment/allocation/credit facts, balanced journal and exact recovery | Complete retained foundation; synthetic sandbox controls remain distinct | Eight-collection `/billing` workspace released behind capability and permission gates | Not applicable | **Released local as the foundation for 0036; no real command is available without the separate manual activation** |
| `0034_transport_role_permissions` | Upgrade-safe owner/administrator transport registry permission repair | Complete; existing custom permissions preserved | Intended leaders receive the bounded registry permissions | No new staff authority | **Released local in 0036** |
| `0035_release_checkout_activation` | Explicit one-way per-facility verified-release activation after server-computed authority readiness | Complete; narrow exact-retry writer and immutable activation | Settings exposes readiness, blockers and typed irreversible confirmation | Existing checkout changes only after the facility activation exists | **Released local in 0036; activation table remains empty** |
| `0036_billing_manual_mode` | Private/local manual receivables for off-platform charge and payment facts | Complete separate activation/provenance boundary; 0033 sandbox remains unchanged | Owner activation, canonical workspace and printable local invoice record are released | Not applicable | **Released local; activation table remains empty; no processor, money movement, automatic issue or delivery exists** |
| `0037_billing_agreement_scope` | Enrollment-scoped immutable billing agreements with a partial legacy-null account/child fallback | Complete; old all-row account/child uniqueness is absent and no billing fact was rewritten | Enrollment-to-billing readiness and family/child finance projections are integrated | Not applicable | **Released local; historical 0037 head; manual-billing protocol remains 0036 and unactivated** |
| `0038_public_job_catalog_outbox` | Privacy-safe durable replay of public job catalog changes, including final-listing closure | Complete retained projection/trigger/replay boundary | Canonical Jobs surface and realtime connection verified | Ordered, deduplicated public-catalog invalidation with canonical refresh before checkpoint | **Released local; historical head included in retained 0039** |
| `0039_admissions_decision_spine` | Administrator admissions lifecycle, deterministic waitlist, offers and duplicate-safe canonical conversion | Complete retained command/RLS/recovery boundary | Complete pipeline, detail, exact recovery and conversion review | Not applicable in this bounded slice | **Released local; retained head 0039** |
| `0040_billing_readiness_batch_planner` | Read-only setup planning plus explicitly reviewed reuse of canonical billing commands | Complete verified source/API boundary; no migration | Complete source; signed-in browser-click walkthrough pending | Not applicable | **Verified product slice; retained head and release pin remain 0039; no activation, invoice, payment, provider or funding behavior** |
| `0041_live_room_presence` | Server-confirmed staff room presence and factual operational configured-target room board | Complete source, migration, exact-retry, RLS/recovery and disposable PostgreSQL boundary | Strict board, exception and recovery surfaces complete; signed-in walkthrough pending | Strict current-room, move/end and child-operation gate complete; physical walkthrough pending | **Verified source; retained PostgreSQL 5434 remains at 0039** |
| `0042_billing_policy_recert` | Exact recertification of the frozen 0033 PostgreSQL billing-policy catalog | Complete whole-catalog A/B certificate and transactional 36-policy canonicalization | No new product UI; existing regression green | No new product UI; existing regression green | **Verified source integrity repair; ancestor of target 0043, retained PostgreSQL 5434 remains at 0039** |
| `0043_org_wide_room_presence` | Organization-wide owner/administrator access to active rooms while clocked in | Additive recertification of the 0041 start guard; all non-leader assignment and existing provenance checks remain | Existing room-selection workflow; no new authority surface | Existing room-selection workflow; no new authority surface | **Verified source; checked-in launcher target 0043, retained PostgreSQL 5434 remains at 0039** |

## Verified 0041 through 0043 source train

Checked-in source and `scripts/start-basic.sh` now target
`0043_org_wide_room_presence`. This is not the retained runtime state. The
retained PostgreSQL 17 database on port 5434 remains exactly at
`0039_admissions_decision_spine`; no 0041 through 0043 retained cutover was
performed.

`0041_live_room_presence` adds the server-confirmed current-room fact for an
on-duty staff member, exact-retry start/move/end transitions, immutable event
history, child-operation room gating, administrator and staff live
projections, append-only operational exception episodes, strict target bundles
and canonical realtime/notification invalidation. Unknown or incoherent source
facts fail visibly. The board is operational configured-target evidence only,
not ratio, qualification, capacity, supervision or regulatory certification.

`0042_billing_policy_recert` is a narrow integrity repair. It accepts only the
exact canonical profile A or audited PostgreSQL dump/restore profile B for all
36 frozen 0033 billing policies, rejects mixed/tampered/unknown catalogs,
transactionally recreates the canonical definitions under relation locks and
requires profile A at postflight. Downgrade preserves the secure policy
catalog. It creates no billing capability, activation or financial behavior.

`0043_org_wide_room_presence` additively recertifies the 0041 start guard.
Clocked-in owners and administrators may select any active room in their active
shift facility without receiving a room-scope assignment. Other roles still
require an active assignment, and the existing permission, shift, facility,
tenant, provenance, overlap and immutability checks remain in force. It adds no
transport, ratio or regulatory-compliance authority.

The populated disposable proof preserved 16,508 rows across all 140 pre-0041
business tables through `0041 -> 0039 -> 0042` and
`0042 -> 0041 -> 0042`. Exact source identities are:

- count digest:
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`;
- row digest:
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`;
- pre-0041 backup SHA-256:
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`;
  and
- populated pre-0042 backup SHA-256:
  `55be096d31c90b33cb7f19e625b472defbb60387d4dd56a7fb1fdec0f9a7490c`.

Final source evidence is:

- every one of the 135 backend test files passed in a memory-safe sweep;
- focused backend after 0042: 45 passed and one explicit opt-in case skipped;
- fresh PostgreSQL 17 0041 boundary: one passed;
- fresh PostgreSQL 17 0042 profile A, A-to-B dump/restore, runtime certificate,
  tamper and canonicalization proof: one passed;
- source-head runtime-grant/backup checks: 39 passed;
- billing runtime-certificate checks: eight passed;
- Ruff, Python bytecode and launcher shell syntax passed;
- administrator: 22 files / 193 tests, TypeScript and production build passed;
  and
- Staff app: 297 tests, TypeScript, Expo Doctor 20/20 and a 782-module Android
  export passed. The HBC bundle SHA-256 is
  `a3667d6da9e033c3a28fec98cf2e9edf4f5ffed51fbeefc0a2bb2c3769aec0fe`.

Remaining gates are the signed-in administrator 0041 walkthrough, physical
Android room-presence walkthrough, permission-safe retained backup/evidence
restore, exact disposable replay from that retained snapshot, restricted-role
certification and a separately authorized retained cutover.

Normative evidence:

- `docs/LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md`;
- `docs/PRODUCT_SLICE_0041_LIVE_ROOM_PRESENCE_SAFETY_BOARD_RELEASE_NOTE.md`;
  and
- `docs/PRODUCT_SLICE_0042_BILLING_POLICY_RECERTIFICATION_RELEASE_NOTE.md`.

## Verified 0040 source/product slice

`0040_billing_readiness_batch_planner` is complete as a bounded source/product
slice. It adds no Alembic revision; the retained head and checked-in release pin
remain exactly `0039_admissions_decision_spine`.

The planner exposes a privacy-bounded deterministic plan and read-only preview
at:

- `GET /api/v1/billing/readiness/batch-plan`; and
- `POST /api/v1/billing/readiness/batch-plan/preview`.

Retained live read-only acceptance returned schema v1 for organization-local
2026-07-23 with 111 groups: 102 account/payer and nine manual-review.
`apply_available=false` and `manual_activation_required=true` truthfully
preserved the absent owner activation. A live one-group preview was read-only,
returned one `account_open` intent, zero blocks and preserved the supplied
operation identifier. Exact post-preview counts remained zero for every
operational billing table and manual activation, while the role backup table
remained at three rows. The retained head stayed 0039. API port 3002 and
administrator port 5174 were healthy, and the setup route returned HTTP 200.
This is live API/read-only acceptance, not a recorded browser-click walkthrough.

Final automated evidence is:

- focused backend planner: 9 passed;
- portable billing: 34 passed, 1 skipped;
- fresh PostgreSQL 17 RLS/no-write proof: 1 passed;
- administrator frontend: 128 files / 865 tests passed; and
- production build: 881 modules transformed with only the existing chunk-size
  advisory.

A separate disposable billing sandbox was backed up before operator testing to
`/Volumes/CareSyncTests/caresync-billing-sandbox-backups/caresync-56544-pre0039-20260723-065358.dump`
with SHA-256
`3e198aef786ec7a0bc03d6eb9a2978c3c248024a693cf301d3492789198a44f6`.
That disposable database was explicitly migrated from 0033 to 0039, its
restricted grants were rebuilt, API port 3302 restarted healthy, both planner
routes became live, manual activation remained zero, and administrator port
5274 was confirmed wired to 3302. This is disposable test-sandbox preparation,
not an 0040 schema migration or retained cutover.

Plan and preview cannot write. Apply is separately gated and reuses only the
existing account, payer, rate and agreement preparation/command/receipt
protocol. Exact snapshot preflight, one-command-at-a-time execution, canonical
refresh and remaining-intent re-preview stop on drift or uncertainty. 0040
cannot activate billing, issue an invoice, record a payment, create a credit,
contact a provider or introduce funding behavior.

The normative records are
`docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md` and
`docs/PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md`.
Signed-in browser-click acceptance remains pending.

## Released 0039 local promotion

At the completed retained 0039 promotion checkpoint,
`scripts/start-basic.sh` and the retained port-5434 database shared exactly
`0039_admissions_decision_spine`. The guarded 2026-07-23 05:27:43
America/Edmonton cutover quiesced writers, captured the exact 0038 source and
restored all 16,445 rows across 135 public tables on fresh PostgreSQL 17 port
56555. Source and restore shared canonical row digest
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both required evidence-vault restores contained zero objects and produced
private receipts.

The retained result has 141 public tables plus one view and exactly 16,445
rows. It preserves all 110 families, 203 children and 197 enrollments. All six
admission tables remain empty because retained acceptance was read-only.
Verified child release and private manual billing remain unactivated (`0/0`).

Revision 0039 releases a private administrator admissions lifecycle with
versioned intake, deterministic waitlist lanes, program offers, exact retry,
duplicate review and atomic Family/Child/pending Enrollment conversion. The
derived existing-record remediation queue remains separate. Six forced-RLS
tables, exact column-level runtime updates, immutable event/conversion facts,
actor-bound receipts, database command provenance/bundle guards, generic
notifications and PII-free realtime invalidations define the boundary.

Final acceptance passed 1,997 backend tests with 105 explicit opt-in skips and
seven warnings, a focused 22-test backend matrix, two independent green
PostgreSQL 17 admissions runs, administrator 125 files / 841 tests, staff app
272 tests and extension 78 tests. Administrator and staff TypeScript,
administrator/extension production builds, 41 release-pin checks, Ruff and
bytecode compilation passed. The signed-in retained Admissions workspace
loaded and refreshed every canonical read projection without a visible error
or write; destructive lifecycle proof remained disposable.

The canonical backup stem is
`caresync-postgres-20260723-052743-592770`; complete retained evidence is in
`docs/LOCAL_RELEASE_0039_CUTOVER.md`.

The later `0040_billing_readiness_batch_planner` source/product slice is now
verified under the separate boundary above. It introduced no schema migration,
so this retained 0039 release evidence and head remain unchanged.

## Historical released 0038 local promotion

At that checkpoint, `scripts/start-basic.sh` and the retained port-5434
database shared exactly `0038_public_job_catalog_outbox`. The guarded
2026-07-23 cutover quiesced
writers, captured the exact 0037 source and restored all 16,335 rows across 134
public tables on a fresh PostgreSQL 17 target on port 56553. Source and restore
shared the canonical row digest
`f0c93cd10395d24816292fc20b761ce262bb666ffeeab5776959c5bc817b5472`.
Both required evidence-vault restores contained zero objects and produced
private `0600` receipts.

The retained result has 135 public tables plus one view and preserves all 110
families and 203 children. Its 16,339 total rows consist of the exact source
plus two public catalog events and one organization and one user realtime
ticket created by the signed-in browser reconnect. Exactly one retained job is
eligible, the migration created one backfill event and the latest public
projection contains that listing (`1/1/1`). All backfill identities agree with
their canonical parent events.

The source ATS and realtime tables retain `FORCE RLS`.
`public_job_catalog_events` has RLS enabled without FORCE so the tightly
attested definer path can project cross-tenant public lifecycle facts. The
runtime role has `SELECT` only and `PUBLIC` has no grant. The enabled trigger
calls a `SECURITY DEFINER` function with fixed `pg_catalog` search path whose
owner matches the table owner and is not the runtime role. The projection
carries no organization identity, listing text, candidate-private fact, or
tenant-private workflow data.

Final acceptance passed 1,979 backend tests with 104 explicit opt-in skips, a
focused 915-pass/2-skip matrix, 3/3 isolated PostgreSQL 17 gates,
administrator 808/808, staff app 272/272 and extension 78/78. The API,
administrator and separate billing sandbox were healthy, and signed-in Jobs
reconnected to realtime. The canonical backup stem is
`caresync-postgres-20260723-022822-921802`; complete retained evidence is in
`docs/LOCAL_RELEASE_0038_CUTOVER.md`.

Neither owner-controlled product boundary changed: verified child release and
private manual billing remained unactivated (`0/0`). Revision
`0039_admissions_decision_spine` subsequently completed the guarded local
release recorded above.

## Historical released 0037 local promotion

At that checkpoint, `scripts/start-basic.sh` and the retained port-5434
database shared exactly
`0037_billing_agreement_scope`. The 2026-07-23 guarded cutover quiesced writers,
captured and exactly restored 16,309 rows across all 134 source tables at
0036, verified the family and staff/transport evidence bundles, then migrated
the retained database and rebuilt restricted grants. The retained result has
134 public tables plus one view and preserves all 110 families and 203
children.

The billing agreement identity is now the exact enrollment for ordinary
records, while historical null-enrollment records retain a partial
account/child uniqueness rule. The superseded all-row account/child constraint
is absent. This is an integrity repair, not a new billing mode:
`0036_billing_manual_mode` remains the private/manual protocol boundary and
`billing_manual_activations` remains empty. The separate facility-release
activation table also remains empty.

The enrollment-to-billing readiness projection and family/child finance
summaries are integrated. Family invoices remain the settlement authority;
child views attribute charges without inventing child-level paid or outstanding
truth. Live Admissions, Billing, Family and Child checks passed and showed 0
setup-ready records out of 197 active child records, with each unresolved
record represented as an actionable item.

Hiring now has one supported server/client boundary: employer ATS under
`/api/v1/ats` and candidate marketplace under `/api/v1/marketplace`, including
the employer marketplace projection. Live OpenAPI contains zero legacy hiring
prefixes and the unused legacy client adapters are retired. The retained
preflight found zero pending private invitations, zero invitation-bound
applications and zero draft offers, so no legacy hiring record migration was
required.

Final integrated acceptance passed 1,969 backend tests with 102 explicit
opt-in cases skipped, administrator 808/808 plus TypeScript and production
build, staff app 260/260 plus TypeScript, and extension 78/78 plus production
build. The canonical backup, manifests, restore receipts and route/runtime
evidence are in `docs/LOCAL_RELEASE_0037_CUTOVER.md`.

At this historical checkpoint, the next bounded slice was
`0038_public_job_catalog_outbox`. That slice has since completed the guarded
local release recorded above.

## Historical released 0036 local promotion

At that checkpoint, `scripts/start-basic.sh` and the retained port-5434
database shared exactly `0036_billing_manual_mode`. The 2026-07-22 guarded
cutover quiesced writers,
captured 16,260 rows across 77 source tables at exactly 0028, restored every
count and the canonical row digest on a disposable PostgreSQL 17 target, then
migrated the retained database and rebuilt the restricted grants. The retained
result has 134 public tables plus one view and preserves all 110 families and
203 children.

Neither gated product boundary is silently enabled. Verified family release
requires an explicit privileged activation for each ready facility. Private
manual billing requires an explicit owner activation for each server-
allowlisted organization. Both retained activation tables remain empty. The
current private single-tenant runtime can derive
its sole active organization only for that server allowlist; a future
multi-tenant runtime must configure each intended UUID explicitly. Details and
the canonical backup, manifest, restore receipt and final acceptance counts are
in `docs/LOCAL_RELEASE_0036_CUTOVER.md`.

Final integrated acceptance passed 1,094 backend tests with 101 explicit
opt-in cases skipped, administrator 790/790 plus production build and zero
production audit findings, staff app 265/265 plus TypeScript and recorded Expo
SDK 57 evidence, and extension 78/78 plus TypeScript/build and zero production
audit findings. API health reported PostgreSQL connected and the signed-in
Billing and Settings surfaces truthfully showed both owner-controlled
activations still pending.

## Released phase: `0027_staff_exchange`

The safety contract is:

- recurring rotations generate reviewable drafts and never silently publish;
- open-shift interest is not an assignment;
- only explicit educator acceptance of a manager offer can fill an open shift;
- offer acceptance creates one ordinary published, acknowledged scheduled shift atomically;
- approved leave remains a hard blocker;
- substitute coverage never exposes another educator's leave reason;
- peer swap consent never reassigns work by itself;
- manager approval performs an all-or-none cancel-and-replace swap with immutable provenance;
- every mutation uses exact-retry operation receipts, forced tenant RLS and least grants; and
- the backup-first `0026 -> 0027` cutover preserved all existing product records, created only
  additive exchange projections/provenance and passed the restricted-role release gates.

At its release checkpoint, source and live-local database shared head
`0027_staff_exchange`. That revision remains frozen in history; its evidence is
recorded in `docs/STAFF_EXCHANGE_ARCHITECTURE.md` and
`docs/REBUILD_RUNTIME.md`.

## Released phase: `0028_childcare_command_spine`

The child, family, enrollment and administrator audit produced
`0028_childcare_command_spine`, defined in
`docs/CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md`. It fixes the restricted-role
family-edit failure, brings exact retry and optimistic versions to child-domain
commands, prevents contradictory open enrollments, routes new enrollment
through approval-first placement and adds an actionable record-readiness queue
without guessing legacy facts.

At the 0028 release checkpoint, source and live-local database shared
`0028_childcare_command_spine`. That head is now a historical checkpoint; the
retained runtime subsequently advanced through the guarded additive chain to
0036. The guarded 0028 cutover backed up and exactly
restore-verified all 1,830 pre-migration rows across 71 tables, then added six
empty RLS-forced command/reconciliation tables. Release evidence is recorded in
`docs/CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md`, `docs/REBUILD_RUNTIME.md` and
`docs/THREAD_HANDOFF.md`.

## Active product track

The guarded 0038-to-0039 local promotion is complete. Family authority remains
conservative: imported unknown facts are not converted into consent or denial,
and no facility changes checkout behavior until explicit activation.
Screening/transport adds evidence and review records but no child dispatch
authority. Billing adds an owner-activated private/manual record of
off-platform facts but no processor, money movement, automatic issue,
delivery, tax advice or funding submission.

Development continues from the integrated retained 0039 baseline.
Enrollment-to-billing readiness, family/child finance summaries, canonical
ATS/marketplace routing, public-catalog replay and the administrator admissions
decision spine are complete for their bounded local contracts. Product slice
`0040_billing_readiness_batch_planner` is also verified in source and through
retained live read-only API acceptance. Its signed-in administrator
browser-click walkthrough remains pending; the next bounded product slice must
be selected explicitly rather than inferred from this ledger.

### Historical no-migration integration nervous system checkpoint

This checkpoint is preserved as evidence from before the retained 0036 and
0037 promotions. References below to a retained 0028 head, source-only
0029–0033 work, or older suite counts describe that checkpoint and do not
override the current release train and evidence above.

The current Basic source now has an executable cross-feature communication contract rather than
an informal collection of page refreshes. `contracts/realtime_entity_contract.json` is the shared
backend/admin entity vocabulary. Backend source analysis rejects unknown or unbounded outbox
entity producers, while migrated disposable-0028 acceptance tests prove representative facility,
program, room, family, child, enrollment, attendance, care, ATS and workforce commands commit the
expected realtime row with their canonical transaction. Successful placement batches emit one
ordinary `enrollment` event per placement; failed batches emit none, and the former phantom
`enrollment_batch` event is forbidden.

The administrator portal registers mounted canonical reloads through one invalidation registry.
Realtime events are quiet hints, not state: every matching REST reload must settle successfully
before the socket cursor advances. Organization changes also rebuild the persistent session shell
and organization choices without discarding a still-valid login; tenant, membership or selected-
organization contradictions fail closed. Medication and rota/workforce notifications now open an
exact server-resolved plan or row. Malformed, stale, crossed-tenant or substituted targets do not
fall back to a nearby record. The runtime audit also prevents an older Children request from
overwriting a newer invalidation, refreshes Discover Talent inside the ATS checkpoint, keeps an
opened exact medication plan in the same canonical checkpoint as its room-day, and removes the
Transport Registry's duplicated hardcoded selector.

The staff app now treats its organization, candidate tenant and user-private streams as three
independent checkpoint domains. A staff cursor waits for the parent operational read and exact
mounted workflow; a candidate cursor waits for the complete career workspace; private
`marketplace.*` events wait for the identity-bound mounted candidate surface without implying a
banner or push. Membership/identity mismatch, unmount, failed read, stale socket generation and
sign-out persistence races all reject advancement. The safe marketplace stream includes public job
lifecycle and exact candidate-owned tenant rows while excluding drafts, unrelated tenants and
other candidates.

The new Admissions surface is a read-only derived intake queue over retained family, child,
enrollment, program and room facts. It makes lifecycle and placement contradictions actionable and
realtime-aware, but it is deliberately **not** a persistent waitlist, an admissions decision
system, a completeness attestation or regulatory certification. This checkpoint adds no migration
and does not move retained PostgreSQL beyond `0028_childcare_command_spine`.

One honest retained-schema limit remains: an unaffiliated candidate who never applied, expressed
interest or joined the organization cannot receive a replayable event when that organization closes
its final public listing, because the 0028 public projection removes the only safe organization
discovery row. Foreground canonical refresh is correct; fully live replay needs a later durable
public-catalog outbox migration.

The earlier integration checkpoint on 2026-07-22 passed 959 backend tests, 677 administrator tests
and 252 staff-app tests. Its runtime proof remains valid: after restarting the Basic API from the
verified source, `/api/v1/health` returned 200 with PostgreSQL connected, unauthenticated Admissions
access failed closed at 401, both authenticated realtime sockets reconnected, and a signed-in
browser reloaded the seven current Admissions conflicts with exact canonical actions and no console
warning or error. The administrator remains available at `http://127.0.0.1:5174` and the Basic API
at `http://127.0.0.1:3002`. This evidence did not migrate, rewrite or promote the retained database;
its Alembic head remains `0028_childcare_command_spine`.

The later 0029 authority/release closeout and recovery-consistency hardening supersede those
current-source counts without changing the retained release: the complete backend passes 1,040
tests with 94 deliberately opt-in disposable-PostgreSQL/scanner/operator/recovery cases skipped and
seven non-failing dependency warnings; the
focused authority/realtime backend matrix passes 47 tests plus Ruff; the administrator passes 107
test files / 691 tests and its production build; and the staff app passes 263 tests and TypeScript.

The revised ten-table 0029A kernel plus two-table A1 evidence vault and exact revision
`0029A2_authority_activation`, strict schemas and layered runtime feature gates,
confidential workspace projection, authority-person create/replace/retire
services and authority-evidence record/review/reject/invalidate/supersede
lifecycle are **verified source**, not released. A1 adds private no-clobber document publication,
server-measured media/size/hash, quarantine and fixed-adapter scan commands, isolated document
structure validation, clean-object binding/download, maker/checker review, exact bundle/restore
inventory and report-only reconciliation. Exact retry, historical
lifecycle closure, terminal retirement, actor privacy, owner/administrator
authorization, affected-child head invalidation, missing-head rollback,
direct-SQL constraints and restricted-role PostgreSQL behavior are covered.
Confidential workspace/policy reads and historical command replays acquire the canonical aggregate
lock before rechecking the actor's current owner/administrator role; role loss fails 403 before a
confidential projection. The administrator separates evidence recorded by the signed-in maker
from items ready for that actor to review, never offers Review to the maker, and uses exact typed
record focus without fallback substitution.
Rejected or invalid-document bytes remain canonical private objects and are not implicitly
deleted. The reconciler reports integrity/orphan candidates and never purges. A future purge
requires two authoritative snapshots, `snapshotEstablishedAt`, at least 30 days unchanged,
quiescence, an exact confirmed plan digest and durable receipts.

A2 activates administrator grant/revoke, bounded `deny`/`manager_review` rule create/revoke,
immutable consent-policy publish/list and consent record/withdraw. Its positive evidence matrix is
fail-closed: guardian attestation, custody document and original-guardian signed release
delegation lanes for release authority; guardian/custody lanes for rules; and separate
`signed_consent` decision evidence from guardian-attestation or custody-document signer authority.
Policy callers submit readable immutable `content_text`; the server derives SHA-256 and the
canonical policy reference. The activation runtime gate proves A2 schema, triggers, forced RLS and
exact grants before any A2 ORM query. At the A2 boundary,
`attendance_release_snapshots` remained SELECT-only downstream scaffolding; the staged C source
extends that boundary without changing the retained database.

`0029B_release_context` now supplies the source-verified, minimum-necessary expiring educator read
projection and deterministic restriction composition. It performs no checkout or authority
mutation.

An owner/administrator child-profile summary now projects bounded current authority plus an exact
release-authorization, release-rule or consent receipt target. It rechecks current membership and
role under lock, bulk-loads evidence and recipient facts at a constant query count, enforces exact
organization/family/child/revision coherence, and omits contact, evidence, signer and confidential
reason data. Generic `child_authority_head` invalidation refreshes family, child-summary and staff
consumers without an identifying event payload. Retained 0028 fails closed before any summary ORM
query and exposes only a finite capability-unavailable state.

`0029C_verified_release_checkout` remains the immutable foundation and portable contract boundary.
`0029D_release_checkout_writer` adds the restricted PostgreSQL command writer, exact actor/org/
operation replay, post-lock database time, same-transaction event/receipt/snapshot/interval bundle,
runtime readiness detector and least-privilege bootstrap contract. The staff confirmation flow is
now wired behind the authenticated per-facility server capability; activated but ineligible or
partially migrated facilities never fall back to the legacy close. A protected operation remains
recoverable after permissions or shift eligibility changes. No retained facility is activated, the
retained database remains pinned to 0028, and no migration or cutover has occurred. This phase
implements only the normal verified release path; any software override remains deliberately
deferred.

The mobile orchestration additionally prevents double submit, renders progress immediately,
invalidates authority state immediately on realtime/scope/token/background changes and applies
401/403 revocation only to the session boundary that made the request. Stale responses cannot
revoke a replacement session; ambiguous operations remain protected for exact retry, while
private server detail never becomes user copy.

The final C verification commands are recorded independently and must not be added together. The
full default backend suite passed 798 tests, skipped 81 explicit opt-in PostgreSQL tests, had zero
failures and emitted 7 warnings. The focused integrated C/B/backend matrix passed 234 tests.
Because the dormant ACL/bootstrap source received its final adjustment while the full suite was
running, that boundary was rerun afterward and passed 17 targeted tests. The administrator passed
TypeScript, 501/501 tests and the production build of 834 modules. The staff app passed TypeScript
and 181/181 tests. The 81 skips are not PostgreSQL evidence, and the warnings are recorded rather
than interpreted as certification. These gates verify only the portable source boundary.

The additive D closeout passed 86/86 checkout service/API/error/mutation/adapter tests, 98/98
combined readiness/bootstrap/adapter/context-detector tests, 12/12 D structural tests and Ruff.
The staff capability integration passed its focused backend gates; the staff app passed TypeScript
and 183/183 tests. A fresh disposable PostgreSQL 17 cluster on an unprotected high port passed 2/2
destructive proof cases covering empty D-to-C-to-D roundtrip, exact readiness and ACL tamper
detection, activated legacy-checkout closure, unbundled interval rejection, injected rollback with
zero partial records, atomic commit, exact replay without duplicates, operation-bound replay
privacy, immutable release history and populated downgrade refusal. Exact replay after permission
and shift eligibility loss is included in the final disposable gate. These counts overlap and do
not authorize a retained migration or facility activation.

The later signed-in operator run found and closed three PostgreSQL adapter defects without
broadening the runtime ACL. Immutable evidence/assessment and consent-policy reads no longer ask
PostgreSQL for row locks that require `UPDATE`; the already-held family/organization aggregate lock
provides serialization. A2 first commits explicitly flush receipt, then immutable authorization/
rule/consent target, then authority head, matching the database guard. Post-commit response
projection expires ORM state so trigger-authored receipt timestamps are reloaded and the first
response matches exact replay.

The development host now has ClamAV. Independent review found that ClamAV resource-limit exhaustion
could otherwise be reported as clean, so the adapter now forces `clamscan --alert-exceeds-max=yes`
and fails closed for `clamdscan` until daemon-side `AlertExceedsMax` can be attested. The hardened
2026-07-22 opt-in synthetic-only certification passed clean, harmless-test-signature rejection,
configured-unavailable and post-version scan-process-failure cases. Raw version output is
normalized and only a complete closed evidence shape can be written as a receipt. The current
private redacted receipt is documented in `docs/FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`. Focused
Ruff passed; 17 real-inclusive scanner/certification tests and 17 staff-vault hardening tests
passed. Detached `main-63`, `daily-28068` and `bytecode-339` definition signatures were independently
verified with `sigtool`, all under `ClamAV_datafiles_release`; an updater warning was not accepted as
proof. That scanner-only receipt does not itself prove a signed-in authority operator flow.

A separate 2026-07-22 actual CLI certification passed all 16 signed-in public-HTTP A/A1/A2 cases on
a fresh caller-provisioned loopback PostgreSQL 17 database at exact
`0029D_release_checkout_writer`, under `caresync_basic_app`, with ClamAV 1.5.3/28068. Preflight and
postflight proved the same system/revision, exact expected synthetic counts and zero unexpected
sessions; the harness contacted no protected port or retained data and performed no provision,
migration, drop or truncate. Its private mode-`0600`, no-clobber, redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`
with SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
It closes only the bounded synthetic signed-in authority operator gate and grants neither release
nor cutover authority. The retained database remains released `0028_childcare_command_spine`.

A separate exact-0029D synthetic artifact-recovery consistency run restored the four fixed
database/vault artifacts into a caller-created scratch cluster and a new vault. It matched 90
tables / 61 rows, one evidence object, the canonical row digest and the complete restored-vault
reconciliation. Its private joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
This closes only `artifactRecoveryConsistencyOnly`: the receipt explicitly leaves source-writer
quiescence, authoritative source completeness/same-snapshot capture, unexpected source-vault
exclusion, target-schema authenticity, migration, cutover, release and purge authority false.
Retained port 5434 was not contacted or migrated.

### No-migration operational checkpoint: exact notifications and daily close

The 2026-07-21 operational pass completed two cross-product slices without a schema revision or
retained-database mutation. Authenticated notification actions now use a closed server-authored
route/entity contract. Invalid or legacy destinations serialize without an action, lock-screen
payloads remain generic, and both clients canonically reopen the exact authorized application,
interview, offer, incident, schedule, shift, open-shift or swap record. The administrator restores
the relevant facility/room/date or rota week before focusing the record. The staff app refreshes
canonical candidate, incident and rota resources before deciding that a target is stale, and resets
pending navigation at organization, workplace, scope or token boundaries. An unfinished incident
draft is deliberately preserved over an incoming incident target; Back reveals the already resolved
record without discarding the draft.

`GET /api/v1/care/rooms/{room_id}/daily-close-preview?date=YYYY-MM-DD` now supplies a factual,
read-only room/day roll-up from existing attendance, care, medication and incident records. It
requires all four corresponding read permissions. Educators are limited to the current
facility-local date and an assigned active room; organization-wide roles may inspect one bounded
historical room/day, including immutable attendance-day room snapshots. The projection contains
identity/photo, attendance interval arithmetic, six care counts, medication outcomes, incident
statuses, five factual attention flags and reconciled totals. It contains no care notes, medication
instructions, incident narratives, guardian data, completeness claim, compliance certification or
delivery workflow. Queries are bulk/constant-count and responses are private/no-store.

The administrator exposes this as a keyboard-accessible Today-page tab with strict boundary parsing,
sequenced realtime refresh and a non-destructive stale-refresh warning. The staff app exposes it as
Records -> Close preview for the selected assigned room, with authenticated photos, search and
factual filters; its payload remains in component memory only. Current-source regression evidence is
backend 941 passed / 90 explicit opt-in PostgreSQL skips, administrator 95 files / 614 tests plus
TypeScript and production build, and staff app 242 tests plus TypeScript. These results overlap and
do not promote the retained release beyond `0028_childcare_command_spine`.

The same live-local pass closed three integration defects found during browser verification. The
optional 0032 transport capability probe may now fail closed on retained revision 0028 without
starting a global authorization-revalidation loop; ordinary protected-request 403 responses keep
their existing revalidation behavior. Realtime hot-reload disconnect races are normalized only for
the exact already-closed uvloop transport signature, while unrelated runtime failures still surface.
Record-readiness placement blockers caused by a Pending family now name the affected child and
family, explain the contradiction, and open an exact organization-scoped family-status review with
Who / What / Action guidance, the bound enrollment ID, an Edit family status action and a safe
alternative to end care. Readiness rows retain native keyboard-accessible link semantics. No record
was changed while verifying this remediation path.

The 2026-07-18 A2 closeout recorded 170/170 passing focused authority regression tests; relevant
Ruff/bytecode gates passed. The administrator passed TypeScript, 81 test files / 501 tests and a
production build of 834 modules. The counts overlap. A separate disposable restricted-role
PostgreSQL 17 run passed 3/3 A2 gates covering fresh migration to
`0029A2_authority_activation`, no drift, bootstrap/runtime identity, forced RLS/exact grants,
positive activation commits, database-negative matrix and maker/checker behavior, and populated
downgrade refusal. The disposable cluster was removed and protected ports were not contacted.
At that 2026-07-18 checkpoint, none of these source gates substituted for real scanner or
operator/cutover evidence. A later hardened synthetic ClamAV adapter receipt closes only the
bounded scanner-adapter proof and still does not claim production readiness.

The 2026-07-18 B closeout passed 84/84 portable API/composer/migration/detector tests. A real
disposable PostgreSQL run on an unprotected high port passed 7/7, including complete runtime
detection, fail-closed rejection after a hardening revoke, restoration, the operational gate
matrix, the 400-transition common-snapshot race and exact migration/projection behavior. The
administrator remained green at 81 test files / 501 tests plus TypeScript/build.
The staff app passed 153/153 tests, TypeScript and an Android export transforming 744 modules. The
complete default backend regression passed 648 with 81 explicit opt-in skips and zero failures;
the counts overlap earlier regressions. The disposable cluster was removed and protected ports
5432/5433/5434 were untouched. This verifies the read-only B source boundary only. Later C/D and
synthetic scanner proofs do not alter B and still do not certify signed-in operator readiness or a
retained cutover.

The 0029 privileged-actor RLS helper fails closed under the API-managed
transaction-local user/organization context. It is not a security boundary
against arbitrary SQL executed with the shared runtime role, which can set
those custom GUCs. Commandized membership/role separation remains required
before production release.

During verification, a plain Alembic command inherited `.env` and briefly
applied the empty 0029A schema to retained port 5434. All ten new tables and all
authority/new-target receipts were empty. The empty-only downgrade restored
`0028_childcare_command_spine`, and an independent read-only verification
confirmed zero authority tables. A private post-recovery v2 backup at
`/Users/amarmuha/Documents/Codex/2026-07-13/hel/caresync-incident-backups/caresync-postgres-20260717-200103-673906.json.gz`
has compressed SHA-256
`d83dfaea0410f03c591d441c5b0f6fe96e863d32f1204e154d34fb3390480fad`.
Its exact fresh-disposable restore reproduced revision 0028, 1,834 rows across
77 tables including `alembic_version`, 203 children, 110 families and zero
authority tables. No product or authority rows were migrated or rewritten, but
the temporary schema advance is part of the permanent release record.

At that 2026-07-18 hardening checkpoint, Alembic blocked protected local ports
5432, 5433 and 5434 by default. Development could bypass only with the exact
command-scoped `CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true`; tests could
not bypass the guard, and seven tests covered it. The launcher was then pinned
to `RELEASED_REVISION=0028_childcare_command_spine`, performed no Alembic
command when retained state matched, and never upgraded retained data to a
staged source head. It also rejected an empty, blank or multi-row
`alembic_version` table before backup or migration, so ambiguous provenance
could not enter an unbacked migration path.

That launcher pin is a historical fact, not current source truth. The port and
provenance guards remain, but `scripts/start-basic.sh` now pins exactly
`RELEASED_REVISION=0039_admissions_decision_spine`. The retained database shares
that revision after the exact guarded cutover recorded at the top of this
ledger.

At that same historical checkpoint, the bounded slices after the active
family-authority kernel were:

1. enrollment intake, waitlist, admissions decisions and required-document completeness;
2. full child/family document-vault lifecycle and broader annual evidence review;
3. room transitions, enrollment history and capacity-aware placement workflows;
4. attendance exceptions and family-facing arrival/departure evidence beyond the 0029 release kernel;
5. child care plans, allergies, health needs, medication and incident follow-through;
6. family communication, announcements, acknowledgements and conversation boundaries;
7. administrator dashboards, action queues, search, audit trails and cross-module navigation;
8. advance the synthetic-only 0033 ledger through separately reviewed document, processor,
   funding, tax, parent and accounting-release stages without treating source verification as
   real finance; and
9. reporting, exports, compliance evidence, retention and disaster-recovery drills.

The newly accepted staff-screening and child-transport track is defined in
`docs/STAFF_SCREENING_TRANSPORT_ARCHITECTURE.md`. Its first independent slice adds confidential
criminal-record/vulnerable-sector document review to candidate onboarding and staff records as the
additive `0030_staff_screening_paths` revision. Registration remains the existing four-field
identity/credential boundary; pathway, screening and driver declarations follow authentication.
Driver, personal-vehicle, child transport-plan and dispatch work follows only after the current
verified-release boundary is proven; a vehicle claim never creates transport authority by itself.

### Staged source checkpoint: `0030_staff_screening_paths`

The bounded screening-to-hire slice is now **verified source**, not released. It adds four explicit
candidate pathways (`educator`, `student_educator`, `driver`, `educator_driver`), encrypted and
versioned CRC/VSS source documents, candidate-confirmed transcription, exact application-scoped
disclosure shares, append-only employer decisions, structured job/offer driving terms and an exact
offer-version digest acknowledgment. OCR remains transcription assistance only; it never decides
suitability. Ordinary ATS cards, realtime payloads and notifications do not expose raw police-check
content or private storage references.

Provisioning is deliberately narrower than recruitment. Pure-driver and student pathways remain
blocked until dedicated least-privilege roles exist. Educator and combined-path candidates receive
only the existing educator role, with no room assignments and no transport authority, and only
after a current employer-verified ECE credential, accepted human CRC/VSS reviews and the exact
accepted offer acknowledgment all agree. A candidate-provided licence or vehicle declaration can
never set operational driver readiness.

The database boundary is additive and all-or-nothing. SQLite migration triggers and PostgreSQL
functions, forced RLS, least grants, immutable facts, exact snapshots and policy definitions are
startup-audited. Partial schema, trigger, function, policy or ACL drift refuses startup and refuses
the runtime-role bootstrap, including when bootstrap is executed by a superuser. Restricted
employer review locks are operationally proven while direct employer mutation of shared screening
facts remains rejected. Unversioned ORM-only SQLite scaffolds are recognized as legacy with 0030
disabled only in test/development; production, PostgreSQL and every Alembic-managed database remain
fail-closed.

The 2026-07-18 closeout passed the complete default backend suite with **841 passed**, **87 explicit
opt-in PostgreSQL skips**, zero failures and seven recorded deprecation warnings. A separate fresh
disposable PostgreSQL 17 database on an unprotected high port passed **4/4** explicit 0030 tests:
fresh migration and restricted `caresync_basic_app` identity; open-listing visibility; atomic
application/snapshot/share creation; confidential source view and two human reviews; cross-tenant
denial; denied manager fact mutation; provisioning-lock visibility; policy-drift startup/bootstrap
refusal and repair; populated downgrade refusal; the complete educator credential/offer/hire path;
and explicit student/pure-driver provisioning blocks. The focused portable backend matrix passed
54/54. The administrator passed TypeScript, 86 test files / 549 tests and its production build; the
staff app passed TypeScript and 205/205 tests. These counts overlap and are recorded independently.

Completed candidates now have a dedicated screening-record manager in the staff app. It appends a
new immutable source version instead of overwriting evidence, resumes interrupted confirmations
(including multiple pending documents in sequence), prevents another upload while confirmation is
open and requires explicit same-person reconciliation for a name mismatch. Same-pathway driver
declaration changes increment their disclosure version without reopening already completed
certificate, experience or identity onboarding. Existing application disclosure snapshots remain
immutable; changed evidence is attached to a future application after withdrawal/reapplication.

No retained migration, runtime restart or data rewrite occurred. The retained database and running
service remain at released revision `0028_childcare_command_spine`. Signed-in 0030 scanner/vault
operation, release-vault key custody/rotation, crash-orphan reconciliation, inode-bound scan/parse handling,
retention/legal-hold/purge rules, immutable ECE evidence binding, no-expiry police-check freshness,
screening concurrency stress and self-review separation remain open release work. Vehicle
verification, driver authorization, insurance, child transport plans,
dispatch, manifests, addresses, handoff and vehicle sweep are intentionally outside 0030.

### Staged source foundation: `0031_driver_vehicle_registry`

The next additive source revision now provides the first **read-only registry foundation**. It adds
append-only staff driver declarations, latest-per-type qualification facts, independent employer
authorization decisions, staff-personal/organization vehicle identities, immutable vehicle and
encrypted-evidence metadata versions and explicit incomplete/blocked readiness decisions. Exact
version sequences, immutable history, one-way vehicle retirement, active independent reviewers,
current verified licence evidence and authorization validity bounded by the referenced licence
expiry are enforced in both SQLite and PostgreSQL migration guards.

Every 0031 authorization and readiness record is constrained to
`operational_driver_ready=false` and `dispatch_authorized=false`. Candidate declarations, accepted
job terms, an employer's registry authorization and a vehicle on file therefore remain distinct
from permission to transport a child. The source adds forced PostgreSQL RLS, read-only restricted
runtime grants, complete startup drift detection and a private/no-store
`GET /api/v1/staff/self/transport-registry`. That response contains only the signed-in member's
bounded projection and omits storage references, hashes, child records, addresses, plans, routes,
manifests, trips and dispatch data.

The administrator parses the exact server marker but keeps its manager navigation, search and
route unavailable because 0031 exposes no manager command capability. The staff app shows the
private projection only when the complete 0031 marker is present; it rejects extra fields, crossed
tenancy, stale references, invalid lifecycle ordering, private metadata and any readiness/dispatch
claim. No demonstration data or mutation controls are substituted.

Verification passed 21 focused backend checks plus an independent 18-test 0031/0030 lifecycle
matrix and Ruff. The administrator passed TypeScript/build and 87 test files / 560 tests. The staff
app passed TypeScript and 209/209 tests. Portable SQLite migration reached 0031. One comprehensive
opt-in PostgreSQL 17 certification passed on a fresh high-port cluster. It proved the complete
upgrade through 0031, forced RLS, read-only restricted-role grants, user-and-organization isolation,
append-only history, independent review, licence-bounded authorization, private projection and
populated-downgrade refusal. That run exposed and closed a reserved-keyword migration error and a
cross-organization self-policy gap before source verification was accepted. The bounded manager/
staff registry commands, evidence/review records, organization-vehicle management and generic
expiry attention are implemented in the verified 0032 source slice below. Real scanner/vault
operation, retention/purge and every child-transport workflow remain open. No retained migration, runtime
release, service mutation or data rewrite occurred; retained PostgreSQL remains at
`0028_childcare_command_spine`.

### Verified source implementation: `0032_transport_commands`

The accepted third slice is **verified source and unreleased**. Its bounded
contract is a registry command/evidence/review layer above 0031:

- actor-private organization-scoped operation IDs, canonical request digests and atomic
  result/audit/receipt commits provide exact retry and changed-intent conflict handling;
- an authenticated self-service client may submit document bytes only through the bounded ingest
  endpoint; storage identity, hashes, ciphertext and scanner provenance are measured and authored
  by the server and cannot be asserted by the client;
- qualification and vehicle decisions bind immutable source/result versions and require a current
  independent manager who is neither the subject/owner nor the source uploader;
- declarations, authorization decisions, vehicles, vehicle versions, evidence, reviews and
  readiness evaluations are append-only except for one-way vehicle retirement; and
- expiry/readiness records remain evidence-only, with generic attention destinations and no
  private document content in notifications.

PostgreSQL uses one narrow `SECURITY DEFINER` command repository owned by a
dedicated `NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS` role. The normal restricted API identity and a
separate server-only evidence-ingest terminal identity receive the exact `EXECUTE` surface for
their lanes and no direct table DML. Startup and bootstrap pin normalized `prosrc` and
`pg_get_functiondef` SHA-256 identities for 15 functions plus the exact 23 enabled protected-table
triggers, context-lock policies and id-only lock ACLs.

All 0032 facts, receipts, APIs and client parsers must keep
`operational_driver_ready=false` and `dispatch_authorized=false`. The slice contains no child,
address, transport plan/consent, route, manifest, run, trip, handoff, dispatch, GPS/location or
offline-trip authority. Administrator and mobile work remains behind the exact full 0032
capability marker; partial, extra, crossed-tenant or authority-granting responses fail closed.

Verification is recorded separately because the suites overlap: portable backend 123/123; fresh
disposable PostgreSQL 17 command/concurrency/compatibility and tamper attestation 7/7; administrator
TypeScript, 591/591 tests and production build; staff-app TypeScript and 227/227 tests. The evidence
vault additionally passed its inode-bound clean-scan/encryption and legacy-plaintext scrub checks,
and manager/self projections have constant-statement bounded reads with truthful truncation. The
complete default backend regression passed 935 tests, skipped 90 explicit opt-in PostgreSQL tests
and emitted 7 deprecation warnings; the skips are not represented as executed PostgreSQL evidence.

The client contract is intentionally bounded. Self qualification declarations and document
uploads remain self-service; a manager reviews exact evidence versions but cannot impersonate a
staff member to declare or upload on that person's behalf. Upload controls are absent when the
server does not advertise evidence ingest. Self histories return at most 20 authorization and 50
vehicle records with explicit truncation; manager workspaces independently cap staff and vehicle
projections at 200 and 100. Both clients retain one immutable ambiguous operation for exact retry, bind evidence
retry to SHA-256/size/media/normalized filename, and require canonical refresh plus the full
operation UUID before local abandonment. The staff app deletes only validated, direct-child
CareSync cache files under two fixed prefixes, with bounded inventory and deletion limits.

A source-only staff/transport vault preflight now derives the exact encrypted-object inventory from
one verified logical backup, pins and rechecks the backup artifacts while measuring ciphertext, and
walks the private vault descriptor-relative without following links. It validates the distinct 0030
document, 0032 qualification and shared vehicle-review ownership shapes; checks ciphertext size and
digest without loading a key or decrypting; and records missing, mismatched, unsafe, unexpected and
indeterminate objects in a private no-clobber receipt. The receipt explicitly fixes
`consistencyAuthority=false`, `purgeAuthority=false` and `blocker=snapshot_boundary_unproven`. It is
inventory evidence only: it has no database, migration, restore, delete or purge path.

The companion `staff_transport_vault_bundle.py` recovery path is now implemented and source
verified. It uses that same pinned backup-derived inventory and descriptor-relative traversal,
rejects every preflight finding, creates a deterministic private no-clobber archive and manifest,
and restores only into a new private root with exact ciphertext re-verification and an optional
no-clobber receipt. It retains all 0030/0032 source rows and shared vehicle history, binds byte size,
ciphertext SHA-256 and encryption-key ID metadata, and never loads or decrypts key material. The
bundle closes artifact recovery relative to one verified logical backup; it deliberately preserves
`databaseVaultConsistencyAuthority=false` and `purgeAuthority=false` because writer quiescence and
the logical backup's live snapshot boundary are not proved. The separate
`staff-screening-vault.key` custody, historical-key coverage and rotation/rewrap workflow remain
explicit release gates.

Remaining release gates are real retained scanner/vault operation, historical keyring custody/
rotation, ambiguous-object adoption and crash recovery, writer-frozen authoritative database/vault
capture attestation, retention/legal-hold/purge authorization, operator and physical-device review,
accessibility/privacy/regulatory acceptance and an explicit cutover decision. Retained PostgreSQL
and the running release remain at `0028_childcare_command_spine`.

### Verified source implementation: `0033_billing_ledger` — synthetic only

`0033_billing_ledger` is **verified source, synthetic only and unreleased**. It adds a bounded
append-only CAD receivables foundation rather than porting or activating the legacy invoicing
system. Its command surface is account open, payer assignment, rate version publish, agreement
establish, invoice issue, payment record, payment allocation and credit issue. Each command binds
organization, actor, operation ID, canonical intent hash, synthetic source versions, domain effect,
balanced journal, audit/realtime event and terminal receipt in one exact-retry boundary. A prepared
operation may instead be finalized as absent; receipt and absence terminals are mutually exclusive.

Command writes are PostgreSQL-only and require test mode, writable sandbox mode, the exact
disposable billing attestation, a loopback high port outside 5432/5433/5434, an explicit
organization allowlist and immutable synthetic-source attestations. SQLite is portable schema and
disabled/shadow-read evidence only and never authorizes a 0033 command. The normal restricted role
receives exact append/select grants, no general update/delete authority, and startup rejects an
incomplete 0033 boundary. All amounts are integer CAD minor units; payer, rate and agreement history
is versioned; invoice, payment, allocation, credit and journal facts are immutable.

The administrator `/billing` workspace is capability- and permission-gated and visibly marks every
invoice `TEST/SYNTHETIC — NOT A REAL INVOICE`. Its eight canonical collections are accounts, full
historical `payer_versions`, rate plans, agreements, invoices, payments, allocations and credits.
It provides overview/action queues, explicit payer selection, account detail, pre-command amount
previews, invoice detail, provenance and protected recovery. Each invoice pins the exact payer
version and guardian provenance used at record time, so a later reassignment affects future work
without rewriting, relabelling or invalidating prior invoices. The client assembles bounded pages
under one snapshot token and refuses partial, drifted, duplicate, crossed-tenant, dangling-reference
or arithmetically inconsistent projections. Basic `/invoicing/*` remains NotFound.

Focused evidence is deliberately recorded without summing overlapping suites: PostgreSQL 16 6/6;
fresh disposable PostgreSQL 17 6/6 after the final trigger/detector edits; portable SQLite 8/8 with
command writes forbidden; administrator 110 test files / 746 tests plus TypeScript and production
build; and whole backend 1048 passed, 100 intentionally opt-in PostgreSQL tests skipped and 7
deprecation warnings recorded.

Signed-in synthetic browser acceptance passed. The sandbox loaded; an account opened with Priya as
payer version 1; the rate and agreement were created; and a CAD 100.00 invoice was issued for a
fully covered August period. Payer reassignment to Samir version 2 preserved Priya/version 1 on the
invoice. A CAD 40.00 receipt, CAD 20.00 allocation and CAD 10.00 credit reconciled to CAD 70.00
outstanding and CAD 20.00 unapplied; reports/readiness reconciled and live snapshots advanced. The
walkthrough exposed a July effective-period gap. Full inclusive agreement and pinned-rate coverage
is now required, Review is disabled when coverage is incomplete, and the corrected state was
visually reverified.

0033 contains no real invoice document or delivery, PDF, processor, money movement or settlement,
refund/chargeback workflow, tax determination or receipt, Alberta funding rule pack or claim,
accounting close/export, parent portal or retained cutover. Synthetic funding splits and configured
tax arithmetic do not establish eligibility, legal treatment or accountant approval. Retained
PostgreSQL and the running service remain at `0028_childcare_command_spine`.

For the 0029 family-authority train specifically, the bounded signed-in synthetic operator gate is
closed, and the bounded four-artifact recovery-consistency subgate is closed separately. The next
recovery gate is writer-frozen authoritative-source capture attestation; neither the operator
receipt, either component restore receipt nor the bounded joint receipt proves that capture
boundary or authorizes cutover. Physical checkout/operator, accessibility/privacy/regulatory,
retained migration, facility activation and explicit cutover decisions remain later gates.

The audit may reorder these slices when a safety or data-integrity dependency requires it.

The closed `0028` local release gates cover actor-private durable command
reconciliation, database-immutable temporal care-network history, active-family
lifecycle consistency, evidence-safe enrollment endings, resolvable readiness
actions, purpose-specific bounded family/child contracts, program-scoped
licensed capacity, commitment-safe room changes, restricted-role migration
visibility and deterministic PostgreSQL concurrency. Physical operator,
accessibility, privacy and regulatory acceptance remain outside that technical
release claim.

### `0028` live checkpoint

| Gate | Current state | Closure evidence required |
|---|---|---|
| Family directory and selectors | **Released local** | Operator and accessibility acceptance remain |
| Child directory privacy cutover | **Released local** | Operator and privacy acceptance remain |
| Family/child/enrollment lifecycle | **Released local** | Alberta policy validation remains |
| Temporal care-network history | **Released local** | Production monitoring/retention policy remains |
| Exact-retry crash recovery | **Released local**; 471 admin tests and server certification green | Full signed-in operator interruption walkthrough remains |
| Program and room capacity | **Released local** | Regulatory interpretation remains operator/legal work |
| Record-readiness actions | **Released local** | Operator wording/usability acceptance remains |
| Release migration | **Complete** at live-local head `0028_childcare_command_spine` | Production deployment is a separate release decision |

This table is updated as evidence closes. “Implemented” is deliberately not synonymous with
“verified” or “released.”

## Later workforce work

- partial-shift trades and split coverage;
- leave balances, accrual, blackout periods and supporting documents;
- breaks, rest periods, overtime, premiums and statutory-holiday evaluation;
- qualification-aware or child-ratio regulatory coverage certification;
- timesheet correction/approval and payroll export;
- labor budgets, demand forecasting and constrained optimization;
- calendar synchronization, closed-loop callout escalation and manager mobile authoring; and
- any production location/geofencing feature, which requires a separate privacy decision.

The released exchange slice also has non-blocking scale hardening reserved for production-sized
organizations: cursor pagination and prefetching for rotation/open-history reads, load tests for
high-cardinality facilities, a durable outbox with batched terminal-engagement fanout,
resource-scoped advisory lock lanes and deferred database constraints for the remaining
application-enforced cross-row provenance rules.

## Product guardrails

- Planned work, actual clock evidence and child attendance remain distinct truths.
- No release upgrade deletes or guesses historical records.
- No client invents permission, lifecycle or eligibility state; the server authors it.
- No ambiguous network response is presented as success.
- Realtime messages invalidate; canonical REST reads establish durable truth.
- Sensitive notifications remain generic until an authenticated record is opened.
- Automated coverage is operational planning, not regulatory certification.
- Physical-device, accessibility, privacy, restore and operator acceptance remain explicit
  production-release gates even when automated suites are green.

## Authoritative supporting documents

- `docs/THREAD_HANDOFF.md`
- `docs/ULTIMATE_PRODUCT_CONSTITUTION.md`
- `docs/MVP_READINESS_AUDIT.md`
- `docs/LOCAL_RELEASE_0039_CUTOVER.md`
- `docs/PRODUCT_SLICE_0041_LIVE_ROOM_PRESENCE_SAFETY_BOARD_RELEASE_NOTE.md`
- `docs/PRODUCT_SLICE_0042_BILLING_POLICY_RECERTIFICATION_RELEASE_NOTE.md`
- `docs/LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md`
- `docs/LOCAL_RELEASE_0038_CUTOVER.md`
- `docs/ADMISSIONS_DECISION_SPINE_ARCHITECTURE.md`
- `docs/STAFF_ROTA_ARCHITECTURE.md`
- `docs/WORKFORCE_PLANNING_ARCHITECTURE.md`
- `docs/STAFF_EXCHANGE_ARCHITECTURE.md`
- `docs/CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md`
- `docs/FAMILY_AUTHORITY_ARCHITECTURE.md`
- `docs/FAMILY_AUTHORITY_EVIDENCE_VAULT_ARCHITECTURE.md`
- `docs/FAMILY_RELEASE_CHECKOUT_ARCHITECTURE.md`
- `docs/STAFF_SCREENING_TRANSPORT_ARCHITECTURE.md`
- `docs/BILLING_FINANCE_ARCHITECTURE.md`
- `docs/FAMILY_AUTHORITY_KERNEL_SCHEMA.md`
- `docs/FAMILY_AUTHORITY_API_CONTRACT.md`
- `docs/REBUILD_RUNTIME.md`

Each completed phase must update this ledger and its domain architecture before handoff.

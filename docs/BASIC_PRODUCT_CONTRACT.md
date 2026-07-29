# CareSync Basic — Product Contract

Status: released local through 0039; later source implementation verified  
Checked-in release target: `0043_org_wide_room_presence`
Retained runtime: `0039_admissions_decision_spine` after exact guarded 0038-to-0039 cutover  
Stage: Basic  
Analyzer/scheduler: deliberately excluded

## Purpose

CareSync Basic is the dependable operating record for a Canadian daycare. It establishes identity,
tenancy, licensed locations, care rooms, household records, child enrollment, actual daily
attendance, staffing and account settings. Its bounded private/manual receivables module records
reviewed invoices and off-platform payments; it does not process money, deliver invoices
automatically, submit funding, provide tax advice, perform predictive scheduling or expose general
AI assistance or advanced reporting.

## Release boundary

### Included in the checked-in target

- Public product entry
- Owner account registration and login
- Resumable organization and first-facility onboarding
- Licensed Daycare/OSC programs and rooms
- Room rosters with current occupancy and an explicit unassigned queue
- Private administrator admission applications, deterministic waitlist, offers,
  exact retry, duplicate review and atomic canonical conversion
- Separate record-derived admissions and intake remediation
- Families, editable guardians, emergency contacts, and consents
- Children, health facts, and strictly placed facility enrollment
- Actual check-in, check-out, absence, and attendance history
- Server-confirmed staff room-presence intervals and a factual operational
  configured-target room board (verified source; retained cutover pending)
- Assigned-room care daybook with reasoned correction and void history
- Written-authorization medication plans and immutable administration facts
- Internal incident draft, review, finalization, and manual external-report tracking
- DOB-based, capacity-aware room recommendations that require manager approval
- Staff accounts, role and room access, staff rota, jobs and hiring
- In-app operational notifications and canonical realtime refresh
- Runtime-gated driver and vehicle evidence/compliance registry without dispatch authority
- Runtime-gated private/manual CAD accounts, rates, agreements, invoice records, off-platform
  payments, allocations and credits after explicit immutable owner activation
- Enrollment-to-billing readiness plus family settlement and child
  charge-attribution summaries; a child view never invents paid/outstanding truth
- One canonical hiring boundary through employer ATS and candidate marketplace
- Privacy-safe durable public-job catalog invalidation and replay for
  unaffiliated candidates, without tenant-private hiring content
- Operational dashboard using only real Basic records
- Organization, profile, and password settings
- Tenant authorization and mutation audit events

### Deferred

- V3 scheduling and all scheduling UI
- The future Analyzer
- Claims and claim imports
- Payment processors, money movement, automatic invoice delivery, refunds, subscription commerce,
  tax advice and funding submission
- Live third-party portal automation by the browser extension; the released
  Basic API includes only the bounded local name-matching companion adapter,
  while live portal/provider acceptance remains separate
- General document management and advanced reports; the canonical billing invoice record is the
  bounded current exception
- Parent portal and family self-service
- Family messaging, announcements and externally delivered notifications

Deferred source code may remain in the repository, but the Basic client must not expose a navigation
item, search result, shortcut or usable direct route. Deferred backend routers are disabled by
default. Runtime-gated Basic features are different from deferred features: their checked-in routes
stay absent from navigation until the server capability and caller permission are confirmed. Manual
billing additionally remains non-writable until an allowlisted organization's owner performs the
explicit 0036 activation. The guarded retained 0039 cutover has completed, but
neither the facility-release nor organization-billing activation was created
by that cutover. Checked-in source now extends through verified
`0041_live_room_presence`, the narrow 0042 billing-policy recertification and
the additive `0043_org_wide_room_presence` role repair, but none of those
revisions has been applied to retained port 5434. Revision 0039
releases the private administrator admissions spine; revision 0038 releases
public-job catalog replay; revision 0037 remains the agreement-scope repair and
0036 remains the manual-billing protocol.

## Information architecture

```text
Public
├── Landing
├── Product
├── Pricing
├── Security
├── Sign in
└── Create account

Onboarding
├── Organization
├── First facility
├── Programs and rooms
└── Review and activate

Workspace
├── Dashboard
├── Admissions
├── Today
├── Families
├── Children
├── Rooms
├── Attendance
├── Medication
├── Incidents
├── Staff & access
├── Staff rota
├── Jobs & hiring
├── Billing & finance (runtime-gated)
├── Driver & vehicle registry (runtime-gated)
└── Settings
```

## Data ownership

```text
Organization
├── Memberships
├── Facilities
│   ├── Programs
│   ├── Rooms
│   ├── Enrollments
│   └── Attendance
├── Families
│   ├── Guardians
│   ├── Emergency contacts
│   └── Children
├── Audit events
└── Onboarding state
```

Every product request is resolved through an active organization membership. Missing membership fails closed. Organization filtering in the API is mandatory; PostgreSQL row-level security is the second boundary. Cross-organization references are rejected even when individual record identifiers are valid.

## Licensed program meaning

`Program type` is the controlled licensed-service category. Basic currently
supports `daycare` and `out_of_school_care`, displayed as **Daycare** and
**OSC (Out-of-School Care)**. A facility may operate either service or both.

`Program name` is the organization's friendly operating label. Each selected
type becomes a separate facility program with its own name, capacity, optional
age range, and rooms. Onboarding supports any number of rooms, requires at least
one, and assigns every room to one of the selected programs. Basic currently has
no room-count entitlement or artificial UI limit. The database permits at most
one program of each type per facility; rooms provide the operational
subdivisions beneath that service.

Schema revision `0003_program_license_types` makes the category required,
normalizes only known legacy aliases, rejects ambiguous rows without deleting
or merging them, and preserves the forced tenant RLS policy.

## Room roster and enrollment placement contract

`GET /api/v1/room-rosters?facility_id=...` is the Basic room-workspace read.
It returns every room for the selected facility, each room's capacity and
current occupancy, the children attached by open enrollment, and a separate
`unassigned_children` collection. Facility and child data remain organization
scoped; a facility outside the active tenant is not disclosed.

New enrollment writes require all three placement levels: facility, program,
and room. The child, facility, program, and room must be active and belong to
the active organization; the program must belong to the facility, the room
must belong to both, and the room must have enrollment capacity. A child may
not have a second open enrollment at the same facility.

`PATCH /api/v1/enrollments/{enrollment_id}` supports an atomic move by accepting
`program_id` and `room_id` together. Sending both as null deliberately places
the enrollment in the unassigned queue; sending only one, mixing a room with
the wrong program/facility, selecting inactive records, or exceeding room
capacity is rejected. Reactivating an enrollment again requires a complete,
valid placement. An active child cannot be deactivated while an open enrollment
remains.

## Family care-network mutation contract

`PATCH /api/v1/families/{family_id}` is the single tenant-scoped edit boundary
for family details, consents, the primary guardian, the secondary guardian, and
emergency contacts. Its omission and removal semantics are intentional:

- Omitting a care-network section preserves its stored records.
- Supplying a guardian object updates the existing guardian in place when one
  exists, preserving its identifier; explicit null removes that role.
- Supplying `emergency_contacts` replaces the list as one unit; null or an empty
  list removes all emergency contacts.
- Scalar fields, guardians, contacts, and the mutation audit event commit in one
  transaction. Validation or uniqueness failure rolls back every part.
- Audit details contain changed field and section names, not copied guardian or
  contact values.

Cross-organization reads and writes fail closed and do not reveal whether a
foreign family exists.

## Temporary verification policy

Email identity, organization identity, and licensed-facility identity are
separate verification concerns. Operational states such as draft/active remain
separate from verification states.

- New owner emails are currently marked verified immediately with a timestamp
  and method `temporary_auto_approval`.
- New organizations and facilities are currently marked verified with the same
  explicitly temporary method.
- The Settings UI describes this as local-phase auto-approval and never implies
  an Alberta, government, registry, or licensing review.
- Verification fields are read only through self-service APIs.
- A genuinely pending email fails closed at login and bearer-token
  authentication.
- No raw email-verification tokens are stored. A future mail flow should use
  hashed one-time challenges with expiry and consumption timestamps.
- Migration backfills use the distinct method `migration_backfill` so future
  audits can distinguish migrated approvals from live policy decisions.

Schema revision `0002_verification_foundation` establishes this contract
without modifying the frozen revision-zero migration.

## Attendance meaning

Basic attendance is an actual operating record, never generated schedule output.

- One attendance day represents one child at one facility on one service date.
- A day may contain multiple check-in/check-out intervals.
- An absence has a reason and no active interval.
- A correction never erases history; it records actor, reason, and before/after state.
- A child cannot be checked into two open intervals at once.
- Check-out cannot precede check-in.
- Synthetic V3 records remain isolated from these tables.

## Medication and incident boundary

- A family-level emergency-medical checkbox is never treated as medication authorization.
- Medication plans require separately recorded written-authorization evidence, original-label
  verification, labelled directions, storage facts, and explicit activation.
- Administration, refusal, omission, correction, and void events retain immutable actor snapshots.
- Incident records are internal working records until a human records an external confirmation.
- CareSync does not submit to Alberta, Childcare Connect, emergency services, police, or Child
  Intervention, and does not assign ministry statuses automatically.
- Medication and incident records have no automated hard-delete policy. Alberta's explicit
  two-year rule is not represented as applying to these records.

## DOB room-placement boundary

- Room eligibility is calculated in complete calendar months on the displayed effective date.
- Active historical enrollments use the facility's current local date; future enrollments use
  their start date.
- A room must have an explicit inclusive minimum and maximum age and available capacity.
- One eligible room still requires approval. Several eligible rooms require an explicit choice.
- Approval re-locks and revalidates the child, enrollment, facility, program, room, age, date,
  and capacity. A recommendation never silently changes a placement.
- Editing a date of birth never silently relocates an already placed child.

## Clean database rule

- Original PostgreSQL `caresync` on 5432: untouched.
- Legacy rebuild clone `caresync` on 5433: retained as migration/regression evidence.
- Basic PostgreSQL `caresync` on 5434: Alembic-owned, isolated from both legacy databases, and
  released at `0039_admissions_decision_spine`. New Basic records are created only through the Basic
  registration and operating flows.
- No legacy family, child, schedule, claim, invoice, or attendance rows are copied into Basic automatically.

## Required end-to-end acceptance path

```text
visit landing
→ create owner account
→ complete organization and facility onboarding
→ create the operating rooms
→ register a family and child
→ enroll the child
→ check the child in
→ check the child out
→ view the completed attendance record
→ update organization/profile settings
```

This path is covered by the backend acceptance suite on PostgreSQL 17. The
runtime-role test uses a disposable database to create two organizations, prove
cross-tenant records are filtered by RLS, and prove cross-tenant writes fail.
It does not run against the live Basic database on 5434.

## Historical foundation integrity checkpoint

The following read-only audit was recorded at the earlier foundation release
and is preserved as historical evidence:

- Both canonical program types are represented with no null or noncanonical
  program category.
- No program/room capacity, duplicate-room, enrollment-placement,
  child-activity, cross-tenant relationship, or completed-onboarding invariant
  violations were detected.
- All 16 expected Basic tables have RLS enabled and forced. Eighteen policies
  are present, and the restricted runtime role has no superuser or bypass-RLS
  capability.
- The runtime role sees no organization or family rows without tenant context
  and sees its scoped rows when valid context is set.
- The live Alembic head is `0003_program_license_types`.

Backend validation on 2026-07-14 completed with 223 tests passed, one
disposable-PostgreSQL RLS test skipped because its opt-in test port was not
provided, and Ruff reporting all checks passed. Five existing Starlette
HTTP-status deprecation warnings remain visible in the suite.

## Current 0039 retained-release checkpoint

The 2026-07-23 guarded cutover captured and exactly restored the retained 0038
source before migrating it. The backup and disposable PostgreSQL 17 port-56555
restore each contain 16,445 rows across all 135 public source tables, including
110 families and 203 children, with canonical row digest
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both evidence-vault restores contained zero objects. The migrated retained
database reports `0039_admissions_decision_spine`, 141 public tables plus one
view, exactly 16,445 rows, 110 families, 203 children and 197 enrollments. All
six admission tables and both activation tables remain empty.

Revision 0039 releases the private administrator lifecycle, deterministic
waitlist, program offers, exact retry, duplicate review and atomic canonical
conversion. It adds no public/parent portal, automatic room placement,
billing/payment/funding behavior or transport authority.

The canonical database artifact stem is
`caresync-postgres-20260723-052743-592770`; complete artifacts and acceptance
are recorded in
[LOCAL_RELEASE_0039_CUTOVER.md](LOCAL_RELEASE_0039_CUTOVER.md). Final
acceptance passed backend 1,997 / 105 skipped / seven warnings, administrator
841, staff 272, extension 78 and two independent PostgreSQL 17 admission runs.

`0040_billing_readiness_batch_planner` is verified as a bounded source/product
slice with retained live read-only API acceptance. It adds deterministic setup
waves and no-write preview, then reuses only the existing canonical
account/payer/rate/agreement commands after explicit review. It introduces no
schema migration; the retained Alembic head remains exactly
`0039_admissions_decision_spine`. Signed-in administrator browser-click
acceptance remains pending.

## Current 0041–0043 release-target checkpoint

Checked-in source and `scripts/start-basic.sh` are pinned to
`0043_org_wide_room_presence`. Retained PostgreSQL 17 on port 5434 remains at
`0039_admissions_decision_spine`; the source pin must not be confused with a
completed retained cutover.

0041 adds four tenant-owned room-presence and operational-exception tables,
exact-retry command/event bundles, strict child-operation room gating,
administrator and staff projections, and canonical realtime/notification
invalidation. It reports operational configured-target evidence only and does
not certify ratios, qualifications, capacity, supervision or compliance.

0042 is a policy-catalog integrity repair. It recognizes only the exact
canonical or audited PostgreSQL dump/restore rendering of the 36 frozen 0033
billing policies, transactionally recreates canonical definitions and rejects
missing, mixed, tampered or unknown catalogs. It adds no product behavior or
billing authority.

0043 is an additive 0041 guard recertification for organization-wide owner and
administrator roles. While clocked in, those roles may select any active room
in the active shift facility without receiving a room-scope assignment; all
other roles still require an active room assignment. The migration preserves
the 0041 permission, shift, facility, tenant, provenance and immutability
checks and adds no transport or regulatory-compliance authority.

The populated disposable clone preserved all 16,508 rows across 140 pre-0041
business tables through both migration round trips. Its count digest is
`19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`
and row digest is
`ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`.
The complete 135-file backend sweep, focused 45-pass/1-skip matrix, fresh
PostgreSQL 17 proofs, administrator 193 tests and Staff app 297 tests passed.
Signed-in administrator and physical Android 0041 acceptance, guarded retained
backup/restore and explicit cutover remain open.

## Historical 0038 retained-release checkpoint

The 2026-07-23 guarded cutover captured and exactly restored the retained 0037
source before migrating it. The backup and disposable PostgreSQL 17 restore
each contain 16,335 rows across all 134 public source tables, including 110
families and 203 children. The guarded family and staff/transport evidence
recovery requirements also passed. The migrated retained database reports
`0038_public_job_catalog_outbox`, 135 public tables plus one public view, and
the same 110 families and 203 children.

Revision 0038 releases a forced-RLS public-safe projection and durable outbox
for replaying public listing changes, including removal of a closed
organization's last listing, to unaffiliated candidates. The replay contains no
draft, organization, candidate, application, interview, offer, credential, or
free-text tenant-private data. Revision 0037 remains the agreement-scope repair
and revision 0036 remains the manual-billing protocol. The facility-release and
manual-billing activation tables both remain empty.

The canonical database artifact stem is
`caresync-postgres-20260723-022822-921802`; its backup, manifests and exact
restore receipt are recorded in
[CUTOVER_BACKUP_RESTORE_RUNBOOK.md](CUTOVER_BACKUP_RESTORE_RUNBOOK.md). Final
integrated acceptance passed 1,979 backend tests (104 explicit opt-in cases
skipped), 808 administrator tests, 272 staff-app tests, 78 extension tests, and
the fresh PostgreSQL 17 public-job acceptance gate at 3/3.

Revision 0039 admissions subsequently completed the guarded release recorded
above.

## Historical 0037 retained-release checkpoint

The preceding 2026-07-23 guarded cutover captured and exactly restored the
retained 0036 source before migrating it. The backup and disposable restore
each contain 16,309 rows across all 134 public source tables, including 110
families and 203 children. The family and staff/transport evidence bundles also
restored with private receipts. The migrated retained database reported
`0037_billing_agreement_scope`, 134 public tables plus one public view, and the
same 110 families and 203 children.

Enrollment-backed agreements became unique by organization, account and
enrollment. Historical null-enrollment agreements retained a partial
organization/account/child uniqueness rule, and the old all-row account/child
constraint was absent. Revision 0036 remained the manual-billing protocol; both
activation tables were empty.

The canonical backup, manifests and exact restore receipts are recorded in
[LOCAL_RELEASE_0037_CUTOVER.md](LOCAL_RELEASE_0037_CUTOVER.md). Integrated
acceptance passed 1,969 backend tests (102 explicit opt-in cases skipped), 808
administrator tests plus TypeScript/build, 260 staff-app tests plus TypeScript,
and 78 extension tests plus build.

## Historical 0036 retained-release checkpoint

The 2026-07-22 guarded cutover captured and exactly restored the retained 0028
source before migrating it. The backup and disposable restore each contain
16,260 rows across 77 source tables, including 110 families and 203 children.
The migrated retained database reports `0036_billing_manual_mode`, 134 public
tables plus one public view, and the same 110 families and 203 children.

The canonical backup, matching manifest and exact-restore receipt are recorded
in [LOCAL_RELEASE_0036_CUTOVER.md](LOCAL_RELEASE_0036_CUTOVER.md). Neither
`facility_release_checkout_activations` nor `billing_manual_activations`
contains a row; release checkout remains on its unactivated path and private
manual billing remains activation-pending.

Final integrated acceptance passed 1,094 backend tests (101 explicit opt-in
cases skipped), 790 administrator tests plus production build and zero
production audit findings, 265 staff-app tests plus TypeScript and recorded
Expo SDK 57 evidence, and 78 extension tests plus TypeScript/build and zero
production audit findings. These automated and local-runtime facts do not
replace physical-operator, accessibility, privacy, regulatory, accountant,
payment-provider or live third-party portal acceptance.

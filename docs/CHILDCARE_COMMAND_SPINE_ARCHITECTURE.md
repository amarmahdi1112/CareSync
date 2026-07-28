# CareSync Child-Record Command Spine Architecture

Last updated: 2026-07-23

## Status

Revision `0028_childcare_command_spine` is the released historical foundation
described by this document. At its recorded checkpoint, source and database
shared 0028 after the guarded backup, exact disposable restore, migration,
restricted-role, PostgreSQL concurrency and regression gates passed. The
retained live-local database has since advanced through the guarded 0029–0038
train to `0039_admissions_decision_spine`; the command-spine invariants remain
in force. Both owner-controlled activation tables remain empty. Physical
operator, accessibility, privacy and Alberta regulatory acceptance remain
separate from this local technical release.

This phase hardens the existing family, child, enrollment and room-placement foundation. It does
not itself claim that custody, pickup authority, consent evidence or admissions
are complete. Later guarded releases installed the bounded authority and
administrator admissions capabilities on this command spine without weakening
its invariants.

## Why this phase comes first

The released foundation already has tenant RLS, full family and child profiles, imported records,
room rosters, DOB-aware placement recommendations, atomic capacity checks, attendance exact retry,
audit-to-realtime outbox delivery and strong attendance-versus-placement concurrency tests.

The audit found four boundaries that must be corrected before adding more child-domain screens:

1. family care-network replacement calls `DELETE` for guardians and emergency contacts while the
   real restricted runtime role intentionally has no `DELETE` privilege, so those edits fail and
   roll back under live PostgreSQL;
2. family, child, enrollment and placement writes have no client operation receipt or optimistic
   version and can duplicate or silently overwrite after interruption or concurrent editing;
3. direct enrollment can bypass approval-first DOB placement and the database does not prevent a
   child from holding multiple open organization enrollments; and
4. the administrator has no actionable record-readiness queue, so incomplete or contradictory
   legacy facts remain invisible until another workflow fails.

The verified pre-`0028` evidence contains 110 families, 203 children and 197 active enrollments.
It also contains review signals: 105 families have no dedicated emergency-contact row, one family
has no primary guardian, three current enrollments are unassigned, four non-active families still
have active children/open enrollments, and eleven children have an unknown immunization marker.
All assigned children currently fit their configured room age ranges and no room is over capacity.
These are signals for human review, not permission to invent facts or automatically deactivate care.

## External requirements that shape the model

This architecture is product engineering, not a legal certification. Current authoritative Alberta
material nevertheless establishes important design inputs:

- Schedule 1 sections 22 to 24 of the Early Learning and Child Care Regulation require an up-to-date
  child record that includes a completed enrollment form, parent and emergency contact information,
  relevant health information and required written health-care consent; the record must be available
  for inspection, and portable emergency information must accompany children off premises.
- Schedule 1 section 4 requires prior written off-site-activity consent that has not been retracted.
- Alberta's Childcare Family Portal describes informed consent for child, parent/guardian and
  enrollment details.
- Alberta PIPA guidance says collection normally requires a stated purpose, an identified privacy
  contact and consent that can be changed or withdrawn subject to legal limits.

References checked 2026-07-17:

- https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html
- https://www.alberta.ca/alberta-childcare-family-portal
- https://www.alberta.ca/collecting-personal-information

The current three family consent booleans and pickup flags cannot satisfy those evidence needs.
Revision `0028` must label them as legacy profile markers and must not reinterpret `false`, null or
missing as denied, withdrawn, absent or non-compliant.

## Product truth hierarchy

1. A family record may be drafted before it is ready for enrollment.
2. Missing, unknown, declined, waived, not-applicable and explicitly false are different facts.
3. A child profile is not an enrollment, and an enrollment is not a room placement.
4. One MVP child has at most one open organization enrollment. A future multi-facility policy must
   be represented explicitly across profiles, attendance, billing and capacity before relaxing it.
5. New enrollment starts unassigned and pending. Human-approved DOB/capacity placement activates
   the enrollment; no direct-create route silently bypasses that validator.
6. A room recommendation is operational assistance, never automatic authority to move a child.
7. Family archive/inactivation cannot strand an active child or open enrollment.
8. Existing imported facts are preserved. `0028` may expose them for review but may not fabricate
   historical forms, consent, emergency contacts, command IDs or authority decisions.
9. Realtime only invalidates. Canonical REST state and immutable command receipts decide truth.
10. Attendance checkout remains attendance checkout until the later release-authority phase records
    the recipient and an immutable authority snapshot.
11. A `pending` family is an intake draft, not an operational care relationship. It may hold child
    profile drafts, but it cannot create or approve an enrollment; an active family with active
    children or an open enrollment cannot transition back to `pending`.
12. Closing an enrollment cannot place already-recorded attendance or regulated care evidence
    outside the enrollment interval. Retroactive endings require a separate correction workflow
    when later evidence exists.

## Persistence boundary

### Versioned projections

`families`, `children` and `enrollments` receive a positive integer `version`. Every successful
domain command increments exactly one authoritative projection version. Existing rows start at
version 1; no synthetic historical operation is created.

The response contract returns the version. Update, lifecycle, placement and archive commands carry
`expected_version`; a stale version returns a structured `409 stale_childcare_resource` with the
current version and writes nothing.

### Immutable command receipts

`childcare_command_receipts` is append-only and tenant-scoped. Each row records:

- organization and globally unique client operation ID;
- command type, target type and target ID;
- SHA-256 of a canonical, purpose-bounded request rather than a duplicate PII payload;
- actor, optional facility, committed target version and commit time; and
- the minimum non-sensitive outcome metadata needed to resolve an interrupted request.

The runtime role receives `SELECT` and `INSERT`, never `UPDATE` or `DELETE`. Forced RLS is both
tenant- and actor-scoped: one staff identity cannot enumerate or forge another identity's command
receipts. Same operation ID plus the same command hash returns the
recorded outcome and current canonical projection with `replayed=true`. Reusing the operation ID
for different intent returns `409 operation_reused`. Exactly one audit/outbox event exists for the
first commit; replay emits nothing.

An actor-private receipt-status read takes the same operation advisory lock before reading the
primary database. The administrator keeps a durable, non-PII unresolved-command journal before
sending a mutation and reconciles it after reload or a lost response. A reconciliation that finds
no receipt records an actor-private non-PII **absence tombstone under the same operation lock**
before returning a non-cacheable structured `404`; a delayed mutation carrying that operation ID
must then be rejected without writes. Only the exact actor-, organization- and operation-bound
`operation_finalized_absent` proof is terminal. Unknown operations and terminal operations owned
by another actor produce the same current-actor proof and response shape; neither terminal kind nor
owner is exposed. A separate actor-scoped proof may record that privacy-preserving decision while
the global operation slot remains the no-write authority. The browser records it as `absent_final`,
never automatically resends the poisoned operation ID, and permits a reviewed new command with a new ID
only after the operator retires that journal entry. Plain or malformed `404`, offline,
authentication, protocol and tenant-boundary failures remain unresolved. This makes the proved
`404` final rather than merely “not committed yet.” A matching non-cacheable `200` refreshes
canonical state. Receipt and absence-tombstone retention must outlive every supported offline-return
interval. Journal entries are identity-bound by actor and organization, and receipt responses
repeat the organization ID so the client can verify the same boundary independently. Browser tabs
share one durable journal and one conservative mutation lane; the lease covers persist-and-send as
well as reconciliation, so one tab cannot overtake another tab's request.
Canonical action routes are
also target-bound: family and child receipts name their exact profile route, while enrollment
receipts name the owning child route plus the exact enrollment ID query. A safe-looking but
metadata-mismatched route never clears the journal.

### Non-destructive family care-network history

Guardians and emergency contacts receive temporal retirement metadata and the operation that
created or retired the row. Current responses select only non-retired rows. A replacement command
retires the previous snapshot and inserts the new snapshot in one transaction; it never hard
deletes care-network evidence.

The restricted role remains without guardian/contact `DELETE` or general `UPDATE`. It may perform
only the one-way current-to-retired transition fields required by the temporal command. PostgreSQL
guards reject PII/provenance rewrites and every update to an already-retired row. This deliberately
fixes the live grant mismatch by aligning code with the least-privilege contract rather than
broadening a runtime permission that would destroy or rewrite evidence.

Legacy rows may retain a null creation operation because `0028` must not fabricate history. Every
new runtime insert, however, is bound at the database boundary to the active operation receipt,
same family and allowed command type; it cannot start retired. Retirement is likewise bound to the
active receipt and may not predate creation. The writable Basic PostgreSQL process must run as the
restricted `caresync_basic_app` identity (non-superuser, `NOBYPASSRLS`); startup fails closed rather
than accepting an owner connection that would bypass these controls.

Partial unique indexes keep at most one current primary and one current secondary guardian during
this compatibility phase. A later stable-person model removes that two-slot household limitation.

### Enrollment invariants

The database and application jointly enforce:

- one open (`pending`, `active` or `paused`) organization enrollment per child;
- program and room are both null or both present;
- an assigned room belongs to the enrollment facility and program;
- start date is not before the child's date of birth;
- family, child, facility, program and room remain inside one tenant; and
- family transition away from `active` cannot commit while an active child or open enrollment
  remains.

New enrollment records contain facility and start date, begin `pending`, and have no program/room.
Placement approval carries operation ID and expected enrollment version, runs the existing
facility-local DOB/capacity validator, and then records the chosen program/room and activates the
enrollment atomically. Existing assigned active enrollments are preserved.

## Time and capacity vocabulary

All decisions use the facility timezone, never server or browser `date.today()` as an accidental
business clock.

- **open**: lifecycle status is pending, active or paused;
- **current**: active, assigned and its effective date interval covers the facility date;
- **reserved**: assigned and open but future-effective, or paused under the current seat-reserving
  compatibility policy;
- **unassigned**: open with neither program nor room; and
- **historical**: ended or outside its closed date interval.

Capacity validation evaluates interval overlap at the proposed effective date. The current room
roster shows current children; reserved and unassigned records are visibly separate and never
silently counted as present.

For Alberta facility-based care, licensed capacity is program-type scoped: daycare, preschool and
out-of-school care each have their own licensed maximum. The imported configuration confirms this
shape (one facility currently carries separate 160-space Daycare and 160-space OSC programs), so
`facility_programs.capacity` is the authoritative licensed-program ceiling in `0028`. Room totals
and overlapping current/reserved placements may not exceed their program and room ceilings.
`facilities.licensed_capacity` is retained as ambiguous legacy data and must not be misused as a
sum-of-programs ceiling. A later migration must either give it an explicit physical/site meaning or
retire it after licence records become first-class. Program or room shrink/deactivation must fail
when it would strand a current or reserved commitment. The source of truth for this vocabulary is
the current [Alberta Child Care Licensing Regulation](https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html),
which defines licensed capacity separately for each care-program type.

## API command contract

The first bounded command set is:

- create/update family and replace a care-network section;
- create/update child;
- create enrollment;
- update enrollment lifecycle or placement;
- approve single/batch DOB placement; and
- change family status or child active state.

Create and approval commands require `client_operation_id`. Mutation commands require both
`client_operation_id` and `expected_version`. Meaning-changing fields freeze after an ambiguous
network result until the exact operation is retried or its receipt is resolved.

The server owns transition capability fields and returns structured error codes. Generic `PATCH`
must not invent a lifecycle transition that has a named guarded command.

List endpoints remain read-only projections. Full family and child PII belongs in authenticated
detail responses, not directory summaries. Family and child surfaces use separate bounded
directory contracts, while the family surface also exposes minimal family and billing selectors.
Directory search executes on the server across tenant-scoped current records; list responses never
contain consent, notes, medical data, historical enrollment detail, retired contacts or an
unbounded household graph. The child directory may expose only the single open-enrollment placement
summary required to distinguish current, reserved, unassigned and needs-review records. Stable
pagination, query budgets and `private, no-store` response handling are release requirements.

## Record-readiness projection

`GET /api/v1/child-record-readiness` is a derived, tenant-scoped action queue. It does not call a
record legally compliant. Each item has a stable code, severity, affected family/child/enrollment,
facility where relevant, human explanation and server-authored action route.

The initial codes include:

- missing current primary guardian;
- no reachable parent/guardian telephone;
- no dedicated emergency contact;
- non-active family with active child/open enrollment;
- open unassigned enrollment;
- room age or facility/program/room coherence review;
- unknown immunization marker; and
- duplicate open enrollment if legacy reconciliation ever discovers one.

False legacy consent markers are not categorized as missing consent. Versioned consent evidence
does not exist until the following authority phase.

The administrator dashboard shows bounded counts and the highest-priority records with direct
links to family, child, room and placement workflows. Realtime family/child/enrollment/room events
refresh the queue through canonical REST. A failed facility refresh preserves successful facility
results and does not poison the entire realtime cursor.

Every readiness action route must resolve to a workflow that can truthfully explain or remediate
the item. Unassigned enrollment routes go to approval-first room review. Assigned but incoherent
legacy placement cannot masquerade as an unassigned approval; until a reasoned reconciliation
command exists it routes to the child/enrollment record and remains explicitly unresolved.

## Migration and legacy reconciliation

The local cutover is complete:

1. CareSync writers were quiesced and a private same-snapshot v2 `0027` backup was created;
2. all 1,830 pre-migration rows across 71 tables restored into a fresh disposable PostgreSQL 17
   target with exact table counts and canonical row digest;
3. fresh-process `0027 -> 0028 -> 0027 -> 0028` passed, and populated-history downgrade refusal
   remained atomic;
4. live migration added only the six empty command/reconciliation tables and explicit metadata;
5. legacy create/last operation IDs and legacy consent/pickup values remained unchanged; and
6. the restricted runtime role, forced RLS, grants, concurrency and full regression gates passed
   before the local release was recorded.

The migration does not archive, assign, authorize, consent, contact, place or deactivate any
existing person. Existing inconsistencies become review items.

## Administrator UX

- Family and child details remain full routes, not side drawers.
- Family editing clearly labels existing booleans as legacy profile markers until evidence exists.
- Ambiguous writes show `Retry exact command`; they do not silently unlock changed intent.
- Enrollment creation selects facility and start date, then routes the unassigned record to the
  existing placement-review experience.
- Family archive and child deactivation show an impact preview and direct blockers.
- Child form limits exactly match FastAPI.
- The dashboard gets a calm, prioritized `Record readiness` queue rather than turning transport
  failures into a misleading records warning.
- Keyboard, focus restoration, 390 px layout and reduced-motion behavior are release gates.

## Acceptance contract and release evidence

All automated migration/database, command/concurrency and client regression items below passed for
the local technical release. The signed-in child-command walkthrough, 390 px visual review,
accessibility checks and operator scenarios remain hands-on MVP acceptance rather than hidden
assumptions.

### Migration and database

- `0027 -> 0028 -> 0027 -> 0028` on fresh SQLite and PostgreSQL 17.
- Forced RLS, one tenant policy and least grants on the receipt ledger and temporal rows.
- Restricted-role family care-network replacement succeeds with no `DELETE` privilege.
- Runtime-role attempts to forge another actor's receipt, rewrite temporal PII/provenance or update
  an already-retired care-network row fail at the database boundary.
- Runtime-role attempts to insert a current contact without matching creation provenance, insert an
  already-retired contact or retire one under an unrelated operation fail at the database boundary.
- Writable Basic PostgreSQL startup refuses a superuser, owner or `BYPASSRLS` connection; migration
  ownership remains a separate, explicit process.
- Partial unique and composite coherence constraints reject invalid enrollment state.
- Existing row counts and all imported PII hashes remain unchanged except explicit additive
  metadata/version columns.

### Commands and concurrency

- Same operation plus same intent replays one recorded commit; different intent conflicts.
- Lost-response create never duplicates family, child or enrollment.
- Reload/crash reconciliation waits behind the original operation lock and resolves committed
  versus absent without persisting the command's PII intent in browser storage.
- If reconciliation wins before a delayed mutation arrives, its absence tombstone makes the later
  mutation a controlled no-write rejection; if mutation wins, reconciliation returns its receipt.
- Receipt `200` and finalized-absence `404` responses are explicitly private and non-cacheable;
  only the strict structured absence proof may unlock an operator-reviewed new operation ID.
- The shared receipt/absence operation slot is enforced on every supported writable database.
  PostgreSQL uses the database guard and disposable race proof; a writable SQLite Basic runtime
  must use the same transactional slot serialization or refuse to start rather than claim exact
  reconciliation it cannot provide.
- Organization switching and simultaneous browser tabs cannot claim, clear or bypass another
  identity's unresolved command; receipt metadata mismatch fails closed.
- Stale expected version writes nothing for family, child, enrollment and placement.
- Two-facility enrollment creation produces one winner under both lock orders.
- Archive versus enrollment, DOB edit versus placement, placement versus check-in and last-room-seat
  races produce a complete winner or a controlled conflict, never a partial state.
- Family pending/archive versus child activation/enrollment/placement, retroactive ending versus
  historical attendance and overlapping placement batches preserve the same invariant under both
  lock orders.
- Every first commit creates one audit event, one realtime invalidation and one command receipt.

### Readiness and clients

- Missing and unknown facts remain distinct and no legacy false value is reinterpreted.
- Readiness totals reconcile to a direct database query without exposing PII in logs.
- Admin exact-retry locks, strict parsers, organization switching and realtime partial recovery
  have automated tests.
- Automated client coverage is green; signed-in desktop/390 px visual review, accessibility checks
  and operator scenarios remain open hands-on acceptance gates.
- Full backend, administrator, staff-app regression, Ruff, TypeScript, build and Expo gates remain
  green even though the staff app receives no release-authority enforcement in `0028`.
- Every pre-existing PostgreSQL concurrency suite reaches its original RLS, attendance, placement
  or capacity race assertion using the explicit `0028` family/child/enrollment commands; a stale
  fixture that exits early with `422` is a failed gate, not a skipped compatibility detail.

## Historical successor foundation: `0029_family_authority`

`0029` builds on the command ledger and temporal person records:

- family-bound stable authority people and immutable fact versions;
- child-specific release grants and restrictions with effective, expiry and revocation states;
- reviewed evidence metadata;
- purpose-specific consent policies/decisions and withdrawal history;
- minimum-necessary release context; and
- normal checkout with an immutable recipient/decision snapshot.

The 0029 sequence is now installed in retained 0039, but no facility activation
was inferred from schema promotion. Full document-vault,
emergency-reunification and software-override capabilities remain outside this
phase. Software override remains deferred until normal release is independently
proven.

Until that phase is released and legacy records are reviewed, CareSync must not market attendance
checkout as verified child release.

Admissions 0039 is released locally and builds on these command, placement,
exact-retry and review invariants rather than bypassing them. Product slice
`0040_billing_readiness_batch_planner` is verified in source and retained live
read-only API acceptance. Its reviewed Apply flow reuses canonical billing
commands and exact recovery rather than bypassing them; it adds no migration or
new billing authority.

# CareSync 0039 Admissions Decision Spine Architecture

Last updated: 2026-07-23

## Status and release boundary

`0039_admissions_decision_spine` is a released, bounded local capability. The
checked-in launcher and retained port-5434 PostgreSQL 17 database share that
single head after the guarded 2026-07-23 promotion from
`0038_public_job_catalog_outbox`.

The guarded cutover captured and exactly restored all 16,445 rows across the
135-table 0038 source on fresh PostgreSQL 17 port 56555 with row digest
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both required evidence-vault restores contained zero objects. The retained
result has 141 public tables plus one view, 16,445 rows, 110 families, 203
children and 197 enrollments. All six admissions tables remain empty because
the signed-in retained smoke was read-only. Complete evidence is in
[`LOCAL_RELEASE_0039_CUTOVER.md`](LOCAL_RELEASE_0039_CUTOVER.md); the preceding
0038 evidence remains historical in
[`LOCAL_RELEASE_0038_CUTOVER.md`](LOCAL_RELEASE_0038_CUTOVER.md).

0039 creates an administrator-operated admissions lifecycle for one prospective
child per application:

`draft -> submitted -> under_review -> waitlisted|offered -> accepted|declined|withdrawn`

It adds deterministic waitlist history, program offers, exact-retry decisions,
and duplicate-safe conversion into the existing Family, Child, and pending
unassigned Enrollment command spine.

0039 does **not** add parent login, a public application portal, outbound email,
document upload or signing, billing commands, payment or funding behavior,
automatic room placement, or regulatory certification.

## Grounded current truth

The retained
[`backend/app/api/basic/admissions.py`](../backend/app/api/basic/admissions.py)
endpoint is intentionally a derived, read-only remediation queue over existing
Family, Child, Guardian, EmergencyContact, and Enrollment records. Its schema
continues to advertise `read_only=true` and `waitlist_supported=false` because
that route describes only the existing-record remediation projection.

That existing queue remains useful and remains separate. It answers, “Which
already-created records need repair?” It cannot answer, “Who applied, where are
they in review, what did the organization offer, or which accepted application
created these operational records?” The released
[`backend/app/api/basic/admissions_decisions.py`](../backend/app/api/basic/admissions_decisions.py)
owns those persistent application, waitlist, offer, decision and conversion
facts.

0039 builds on the released invariants in
[`CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md`](CHILDCARE_COMMAND_SPINE_ARCHITECTURE.md):

- Family, Child, and Enrollment are different records.
- Family, Child, and Enrollment projections are versioned.
- a child has at most one open organization enrollment;
- a new enrollment starts `pending` and unassigned;
- room placement remains a later human-approved DOB/capacity command;
- exact retry is decided by an immutable actor-bound operation receipt;
- realtime invalidates and canonical REST reloads truth; and
- existing imported facts are never converted into invented historical facts.

The retained 0039 evidence contains 110 families, 203 children and 197
enrollments. All six admission tables contain zero rows. None of the imported or
pre-existing records was treated as proof that an admissions application or
decision occurred.

## Product truth and non-negotiable invariants

1. One application represents one prospective child and one primary adult
   contact. Siblings use separate applications and may reuse one reviewed Family.
2. Application, Family, Child, offer, Enrollment, and room placement remain
   distinct facts changed only by named commands.
3. `accepted` means the offer, application, immutable conversion link, and
   canonical Family/Child/pending unassigned Enrollment committed atomically.
4. Possible duplicates require current human review. Reuse is explicit and
   versioned; creating a distinct person requires a bounded override reason.
   Application values never overwrite canonical person records.
5. One application has at most one current waitlist entry, one open offer, and
   one conversion link. Waitlist position is deterministic, not an entitlement.
6. Admission records are not hard-deleted. Events, receipts, audit, and
   realtime payloads retain only IDs, versions, states, and bounded reason codes.
7. Every tenant foreign key includes `organization_id`; every first commit has
   one receipt and event; replay emits neither again.
8. Existing `/admissions/intake-queue` cases remain derived remediation signals
   and are never backfilled as historical applications.

## Lifecycle

### Application states

| Current state | Allowed next state | Command and meaning |
|---|---|---|
| none | `draft` | `admission.application.create`; administrator records the minimum intake facts |
| `draft` | `draft` | `admission.application.update`; correct child, contact, or ranked preferences |
| `draft` | `submitted` | `admission.application.submit`; freeze the initial submitted snapshot |
| `submitted` | `under_review` | `admission.application.review.start` |
| `submitted` | `withdrawn` | `admission.application.withdraw`; operator records an off-platform withdrawal request |
| `under_review` | `waitlisted` | `admission.waitlist.enter` |
| `under_review` | `offered` | `admission.offer.issue` |
| `under_review` | `declined` | `admission.application.decline`; provider decision |
| `under_review` | `withdrawn` | `admission.application.withdraw` |
| `waitlisted` | `under_review` | `admission.waitlist.reopen_review` |
| `waitlisted` | `offered` | `admission.offer.issue`; current queue priority is preserved |
| `waitlisted` | `declined` | `admission.application.decline` |
| `waitlisted` | `withdrawn` | `admission.application.withdraw` |
| `offered` | prior `under_review` or `waitlisted` | `admission.offer.withdraw`; provider retracts the open offer |
| `offered` | `declined` | `admission.offer.decline`; operator records the family's off-platform decline |
| `offered` | `accepted` | `admission.offer.accept_and_convert`; atomic canonical handoff |
| `offered` | `withdrawn` | `admission.application.withdraw` |

`accepted`, `declined`, and `withdrawn` are terminal in 0039. Reapplication
creates a new application and preserves the old decision history.

An application correction after submission is a named
`admission.application.correct` command. It returns the application to
`under_review`, closes an active waitlist entry with reason `facts_changed`, and
requires an open offer to be withdrawn first. This prevents a material child,
contact, facility, program, or start-date change from silently retaining an old
decision.

### Offer states

An offer is `open`, `accepted`, `declined`, or `withdrawn`. 0039 does not
implement automatic expiry or a background expiry job. An optional
`respond_by_date` is informational; the server does not claim that time alone
changed the record.

An offer names one active facility, one active program, and one proposed start
date. It contains no room ID, price, subsidy, payment term, transportation
promise, or regulatory assurance. The UI must say that room placement remains
required after acceptance.

### Waitlist states and ordering

A waitlist entry is `active`, `offered`, or `closed`.

- entering the waitlist creates the one current entry and an immutable
  `priority_at`;
- issuing an offer changes that entry to `offered` without losing
  `priority_at`;
- withdrawing that offer reactivates the same entry;
- acceptance, decline, withdrawal, material correction, or explicit review
  reopening closes it with a bounded closure reason; and
- displayed position is computed within the selected facility/program lane by
  `(priority_at, id)`.

No 0039 command manually reorders, backdates, boosts, or certifies a waitlist
entry.

## Additive persistence boundary

| Additive table | Purpose and principal invariants |
|---|---|
| `admission_applications` | Versioned lifecycle head with tenant, non-PII reference, `source='administrator_entry'`, status, child/contact intake, bounded internal note, actors, and timestamps. Display and normalized values are retained, but normalized values are not identities or list fields. |
| `admission_application_preferences` | Temporal ranked facility/program/start-date rows. Replacement retires the current set and inserts the full new set; no runtime delete. One current row per rank and no duplicate current lane. |
| `admission_waitlist_entries` | Versioned active/offered/closed queue record with selected lane snapshot, immutable `priority_at`, closure reason, actors, and timestamps. One current entry per application. |
| `admission_offers` | Versioned facility/program/start-date offer with optional respond-by date, prior application state, open/accepted/declined/withdrawn state, and actor timestamps. One open offer per application; no room or financial terms. |
| `admission_conversion_links` | Append-only one-to-one link from accepted application/offer to canonical Family, Child, and pending Enrollment, resolution mode, acceptance operation, review-proof digest, actor, and commit time. Same-tenant composite foreign keys; no update/delete. |
| `admission_application_events` | Append-only application-version timeline with command, from/to states, bounded reason, actor, operation, and occurrence time. No intake PII or note body. |

### Existing command receipt extension

0039 reuses `childcare_command_slots`, `childcare_command_receipts`, absence
claims, actor-private reconciliation proofs, and their operation-lock ordering.
The receipt target allowlist expands to:

- `admission_application`;
- `admission_waitlist`; and
- `admission_offer`.

The canonical receipt action route is
`/admissions/applications/{application_id}`. The existing actor-private
`GET /childcare-commands/{client_operation_id}` remains the interrupted-command
reconciliation endpoint.

## Database invariants, RLS, and grants

Every new table has forced tenant RLS using
`app.current_organization_id`. Authentication continues to set the current user
and active organization before domain access, as defined in
[`backend/app/api/basic/dependencies.py`](../backend/app/api/basic/dependencies.py).

Dedicated permissions are `admissions:read`, `admissions:manage`, and
`admissions:decide`. The migration unions them into existing system owner and
administrator roles without replacing custom arrays. Educators receive none.

The restricted runtime receives bounded projection reads, command-path inserts,
guarded lifecycle updates, insert-only event/conversion access, and no
admission-domain delete.

Constraints and deferred guards enforce positive versions, valid states,
same-tenant facility/program relationships, an active program in its facility,
one current waitlist/open offer/conversion per application, accepted application
to accepted offer/conversion coherence, pending unassigned conversion
Enrollment coherence, and immutable event/receipt/priority/conversion
provenance.

Application code still owns lifecycle transition validation and readable error
codes. Database guards are the final defense against a bypassing or defective
writer.

## Exact-retry command contract

Mutation schemas use `extra='forbid'`. Every command carries
`client_operation_id`; non-create commands carry
`expected_application_version`; offer/waitlist commands also carry the changed
record's expected version.

The server locks the operation, hashes bounded intent, replays an exact receipt
or rejects reuse, locks dependent records in stable UUID order, validates
versions/transition/scope/review proof, and commits domain change, event, audit,
outbox, optional notification, and receipt together. It returns canonical
detail with `replayed` and committed versions.

A stale version, invalid transition, changed duplicate candidate set, lost
permission, or failed nested childcare command writes nothing.

## Duplicate-safe acceptance conversion

### Review projection

`GET /admissions/applications/{id}/conversion-candidates` returns bounded
same-tenant candidates based on:

- exact date of birth plus normalized child name;
- normalized primary-contact email or telephone against current Guardians; and
- Families already connected to those candidate children or guardians.

The response contains only the minimum IDs, display labels, versions, match
reasons, and whether a Child already has an open Enrollment. It also returns a
short-lived signed review token bound to organization, application ID/version,
offer ID/version, candidate IDs/versions, and expiry. The token contains no
PII.

### Explicit resolution modes

`admission.offer.accept_and_convert` requires the current review token and one
mode:

1. `create_family_and_child`: allowed with no candidates, or after
   `confirmed_distinct_person` acknowledgment of every current candidate;
2. `reuse_family_create_child`: requires the chosen current Family and version;
3. `reuse_child`: requires the chosen current Child and Family versions and no
   open Enrollment.

If selected canonical data differs from the application, acceptance never
rewrites it. The operator corrects the canonical record through the existing
Family/Child commands or corrects the application and repeats review.

### Atomic handoff

The acceptance transaction:

1. locks the acceptance operation, application, offer, waitlist entry, reviewed
   candidates, selected Family/Child, facility, and program in canonical order;
2. verifies the signed review set is still current;
3. creates an active Family plus primary Guardian from the accepted contact, or
   reuses a currently active Family; it does not invent consent, pickup,
   emergency, or authority facts or auto-activate an existing Family;
4. creates an active Child from the reviewed intake, or reuses a currently
   active Child without importing medical facts or auto-activating a record;
5. creates one pending unassigned Enrollment for the offered facility and start
   date using the 0028 validators;
6. inserts the immutable conversion link;
7. marks the offer and application accepted and closes any waitlist entry;
8. records admission plus Family/Child/Enrollment audit and realtime facts; and
9. commits all records or none.

Nested Family, Child, and Enrollment operation IDs are deterministic UUIDv5
derivations of the client acceptance operation and fixed component labels.
They use the existing command-receipt machinery, so a lost response cannot
duplicate any target and an interrupted retry returns the same IDs.

A concurrent acceptance has one winner. A second operation returns the
existing conversion as `admission_already_converted` without changing it. The
existing one-open-enrollment constraint remains the final protection against
duplicate operational enrollment.

## Canonical REST projections

0039 adds:

- `GET /admissions/workspace` — bounded counts and pipeline lanes;
- `GET /admissions/applications` — minimal paginated directory;
- `POST /admissions/applications` — exact-retry draft creation;
- `GET /admissions/applications/{id}` — authorized detail and timeline;
- named application, waitlist, offer, decline, withdrawal, and acceptance
  command endpoints;
- `GET /admissions/waitlist` — deterministic lane and computed position;
- `GET /admissions/applications/{id}/conversion-candidates`; and
- the existing `/admissions/intake-queue` unchanged as record remediation.

List and waitlist responses omit contact email, telephone, date of birth,
internal notes, and full candidate graphs. Detail responses use
`private, no-store`, strict schemas, bounded timelines, stable ordering, and
organization verification on every identifier.

## Administrator UX

`/admissions` becomes a command center with **Pipeline** status counts,
**Waitlist** facility/program lanes and honest non-guarantee copy, and the
current **Existing-record remediation** queue.

Application details use the full route
`/admissions/applications/:applicationId`, never a side drawer. The page shows
the child/contact intake, ranked preferences, immutable transition timeline,
current waitlist or offer, conversion state, and one context-valid next action.

The acceptance screen refreshes candidates immediately, explains create/reuse
matches, requires distinct-person confirmation where needed, states that room
placement follows, previews the Family/Child/pending Enrollment effect, and
links success to child and placement review.

Ambiguous writes enter the existing durable operation journal and show “Retry
exact command.” They never silently enable a changed action. Organization
switching clears application detail and unresolved commands remain
actor/organization bound.

Keyboard navigation, focus restoration, reduced motion, readable status text,
390 px layout, and screen-reader announcements for transition results are
release gates.

## Realtime, notifications, and integration

The executable entity contract gains `admission_application`,
`admission_waitlist`, and `admission_offer`.

The existing `application` type remains ATS-only. Admission events must never
be published under that ambiguous name.

Every admission command writes a tenant outbox invalidation in its transaction.
Payloads contain entity type, entity ID, version, and `refresh_required`; they
contain no child/contact PII. The Admissions surface reloads canonical REST
before advancing the cursor and coalesces admission, Family, Child, Enrollment,
facility, program, and room invalidations.

Acceptance publishes the admission event plus the canonical Family/Child/
Enrollment events created by the nested command spine. Consumers may coalesce
them, but none is omitted.

Durable in-app notifications are limited to a submitted application for active
members with `admissions:decide` and a completed conversion for authorized
managers other than the actor.

The title/body are generic. The strict destination is
`/admissions/applications/{uuid}` with matching
`admission_application` entity identity. No notification is proof of external
delivery, and 0039 calls no email or push provider inside a business
transaction. The canonical notification and realtime rules remain those in
[`REALTIME_NOTIFICATION_ARCHITECTURE.md`](REALTIME_NOTIFICATION_ARCHITECTURE.md).

## Migration, backfill, downgrade, and promotion

The migration is additive from the released 0038 head:

1. create the six admission tables, indexes, composite foreign keys, guards,
   forced RLS policies, and least grants;
2. extend command receipt target constraints and strict response literals;
3. extend system owner/administrator permissions by set union;
4. extend the realtime entity contract and notification destination allowlist;
5. create no admission row, decision, preference, waitlist entry, offer,
   conversion, receipt, or event for retained data; and
6. leave Family, Child, Enrollment, remediation, billing, authority, and hiring
   facts unchanged.

Before retained migration, writers were quiesced and the exact 0038 database
and required evidence bundles were backed up, disposable-restored and
digest-verified. The 0039 migration ran first against that exact disposable
restore.

Fresh and empty-schema `0038 -> 0039 -> 0038 -> 0039` passed. Downgrade remains
allowed only when every admission table is empty and no 0039 receipt,
notification, or realtime row depends on an admission entity. Otherwise it
refuses atomically; it never deletes populated admission history to make an old
schema fit.

Release promotion preserved the retained 110 families, 203 children and 197
enrollments and the exact 16,445-row canonical digest. The six new admission
tables began and remain empty. No launcher, migration or test activated family
release or manual billing.

## Privacy and explicit exclusions

0039 stores child and adult contact PII and therefore:

- has no unauthenticated admissions API;
- exposes no parent or candidate account;
- never places PII in realtime, notification, receipt, URL, or logs;
- does not collect medical narratives, government identifiers, custody
  evidence, consent, signatures, documents, payment data, or transportation
  instructions;
- does not treat contact matching as identity verification;
- does not promise waitlist priority, capacity, eligibility, licensing, funding,
  or regulatory compliance; and
- does not introduce hard deletion, retention automation, legal holds, or
  production privacy certification.

Parent identity and self-service, outbound communications, document vault,
billing agreements/invoices, funding claims, room placement, and regulatory
certification remain separate later releases.

## Executable acceptance matrix

The named cases are implemented release deliverables. Their final source,
PostgreSQL and retained evidence is recorded below and in
[`LOCAL_RELEASE_0039_CUTOVER.md`](LOCAL_RELEASE_0039_CUTOVER.md).

| ID | Automated case | Required evidence |
|---|---|---|
| M01 | migrate disposable populated 0038 to 0039 | all pre-existing counts and canonical digests preserved; six admission tables empty |
| M02 | fresh `0038 -> 0039 -> 0038 -> 0039` | one head, identical schema fingerprint, system permissions repaired by union |
| M03 | empty downgrade | succeeds without touching non-admission tables |
| M04 | populated downgrade | refuses atomically with every admission row intact |
| DB01 | cross-tenant reads and foreign keys | forced RLS hides rows; cross-tenant references fail |
| DB02 | restricted runtime grants | no admission `DELETE`; immutable event/conversion update fails |
| DB03 | uniqueness and deferred guards | second current waitlist/open offer/conversion and accepted-without-conversion fail |
| C01 | lost-response create/update | same operation and intent replay one commit; changed intent conflicts |
| C02 | optimistic concurrency | stale application, waitlist, or offer version writes nothing |
| C03 | lifecycle matrix | every allowed edge succeeds; every undeclared edge returns a stable conflict code |
| C04 | material correction | closes waitlist, refuses with open offer, returns to review, preserves timeline |
| W01 | concurrent waitlist entry | one current entry wins and position ordering is deterministic |
| W02 | offer withdrawal from waitlist | original priority reactivates; no duplicate entry is created |
| O01 | issue offer | active facility/program only; no room, billing, or capacity promise is written |
| O02 | provider/family decline and withdrawal | correct terminal status and waitlist/offer closure, with actor/source distinction |
| X01 | accept with new Family and Child | one active Family, Child, pending unassigned Enrollment, conversion, and receipts commit |
| X02 | accept by reusing Family | no duplicate Family; new Child and Enrollment remain tenant-bound |
| X03 | accept by reusing Child | canonical PII is unchanged; one new pending Enrollment only |
| X04 | stale duplicate review token | controlled conflict and zero writes |
| X05 | create-new with candidates | requires current reviewed candidates and `confirmed_distinct_person` reason |
| X06 | reuse Child with open Enrollment | rejected by service and database invariants |
| X07 | two concurrent acceptances | exactly one conversion; loser returns canonical existing conversion |
| X08 | injected failure after nested child creation | entire acceptance, nested receipts, events, audits, and outbox roll back |
| R01 | command receipt reconciliation race | receipt-versus-finalized-absence behavior matches the 0028 operation slot |
| RT01 | each lifecycle command | one admission invalidation; canonical reload precedes cursor advance |
| RT02 | acceptance | admission plus Family/Child/Enrollment invalidations commit together and coalesce safely |
| N01 | actionable notification | correct authorized recipients, stable dedupe key, generic content, strict matching route/entity |
| API01 | directory/waitlist privacy | no DOB, contact data, note, or unbounded candidate graph |
| API02 | detail authorization | active membership plus admission permission; organization switch fails closed |
| UI01 | pipeline and detail behavior | full-route workflow, exact-retry lock, safe deep links, no side drawer |
| UI02 | responsive/accessibility | keyboard/focus, screen reader, reduced motion, and 390 px review pass |
| REG01 | complete regressions | backend, admin, staff app, extension, Ruff, TypeScript, and production builds remain green |
| LIVE01 | guarded local promotion | exact backup/restore evidence, restricted grants, signed-in lifecycle smoke, retained head 0039 |

Principal test entry points:

```text
backend/tests/test_basic_admissions_decision_spine.py
backend/tests/test_basic_admissions_decision_spine_migration.py
backend/tests/test_basic_postgres_admissions_decision_spine.py
backend/tests/test_basic_realtime_entity_contract.py
frontend-redesign/src/features/admissions/admissionsDecisionApi.test.ts
frontend-redesign/src/features/admissions/admissionsFactsCommands.test.ts
frontend-redesign/src/features/admissions/AdmissionApplicationPage.test.ts
frontend-redesign/src/features/admissions/AdmissionApplicationPage.render.test.ts
frontend-redesign/src/features/admissions/AdmissionsDecisionWorkspace.render.test.ts
frontend-redesign/src/api/childcareCommandJournal.test.ts
frontend-redesign/src/api/childcareCommandReceipt.test.ts
frontend-redesign/src/api/childcareCommandRecovery.test.ts
frontend-redesign/src/childcare-commands/ChildcareCommandRecoveryContext.test.ts
frontend-redesign/src/childcare-commands/ChildcareCommandRecoverySurface.test.ts
```

The final focused backend matrix passed 22 tests. The fresh PostgreSQL 17 gate
passed in 10.88 seconds and an independent rerun passed in 11.42 seconds. The
administrator admissions/recovery matrix passed 12 files / 92 tests; the full
administrator suite passed 125 files / 841 tests plus TypeScript/build. The
complete backend passed 1,997 tests with 105 explicit opt-in skips and seven
warnings; staff passed 272 tests plus TypeScript; extension passed 78 tests plus
TypeScript/build; release-pin checks, Ruff and bytecode compilation passed.

The signed-in retained workspace then loaded and refreshed pipeline, waitlist,
protected draft, non-PII register, remediation and billing-readiness data with
no visible error and no write. Destructive lifecycle and conversion proof
remained on disposable PostgreSQL, and retained admissions stayed empty. This
is a local technical release, not production or regulatory certification.

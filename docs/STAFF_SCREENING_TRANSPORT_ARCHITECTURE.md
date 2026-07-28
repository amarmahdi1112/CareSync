# CareSync staff screening and child transport architecture

## Product boundary

This phase turns staff screening and home/school transport into explicit, reviewable workflows.
It does not treat access to a car as permission to transport a child, expose family addresses to
the general staff directory, infer legal suitability from OCR, or allow an educator to improvise
a private ride outside an approved dispatch.

The product supports three independent employment capabilities:

- educator/care duties;
- driver/transport duties; and
- a combined role in which the same employee may hold both capabilities.

Each capability is effective-dated. A suspended or expired driver capability blocks new trips but
does not silently suspend otherwise-authorized educator work.

## Alberta research baseline

- The current Alberta Early Learning and Child Care Regulation requires an adult staff member or
  volunteer with unsupervised child access to provide a criminal-record check that includes a
  vulnerable-sector search, dated no earlier than six months before commencing, and renewed every
  three years. A new person may have an eight-week submission window but must not have unsupervised
  access before the check is provided. CareSync must keep the source rule, effective date and human
  decision version instead of reducing this to a permanent boolean:
  <https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html>
- The Alberta facility-based licensing handbook also describes current criminal-record and
  vulnerable-sector evidence for applicable people with access to children or child records, and
  directs programs providing child transport to assess Traffic Safety Act requirements:
  <https://open.alberta.ca/publications/child-care-licensing-handbook-facility-based-programs>
- Alberta's commercial-carrier guidance is a separate applicability source; CareSync must not
  assume every vehicle or trip is governed identically:
  <https://www.alberta.ca/education-manual-for-commercial-carriers>
- Alberta distinguishes driver licence classes and says a Class 4 licence includes a school or
  kindergarten bus seating fewer than 25 people. Passenger-carrier and operating-authority rules
  vary by the service and vehicle, while child-restraint duties vary by the child's age/weight:
  <https://www.alberta.ca/upgrade-commercial-licence>
  <https://www.alberta.ca/commercial-carrier-certificates-and-operating-status>
  <https://www.alberta.ca/occupant-restraint-laws>
- Exact renewal, insurance, vehicle, restraint, employment and municipal requirements remain
  versioned rule-pack decisions reviewed with the operator/licensing and insurance professionals.

## Candidate and staff screening

### Candidate onboarding

1. Create the account with legal name, email and password.
2. Choose a pathway: educator, student educator, driver, or educator + driver.
3. Upload each required source document; retain the original encrypted object and a rendered
   review copy.
4. OCR may propose document type, subject name, date of birth when present, issuing body, issue
   date, reference number and expiry/recheck date. Every extracted field carries confidence and
   source-region evidence.
5. The candidate confirms transcription only. An authorized employer reviewer decides whether the
   document is current, applicable and acceptable. The model never makes a suitability decision.
6. A name/date mismatch opens identity reconciliation. It does not silently rewrite the account or
   discard the document.

Required screening-document classes are modeled separately:

- criminal-record check;
- vulnerable-sector search;
- child-intervention record check when the organization's approved policy requires it;
- ECE certification or student-enrolment evidence;
- first-aid/CPR evidence;
- driver licence and applicable class/restrictions;
- driver abstract when the approved role policy requires it; and
- vehicle/insurance evidence only when a personal vehicle is proposed.

Candidate-owned document states are `uploaded`, `analysis_pending`, `candidate_review`,
`confirmed`, `expired`, `superseded` and `withdrawn`. An employer's `accepted` or `rejected`
decision is a separate append-only fact scoped to the exact application, disclosed document
version and requirement class. It never changes the candidate's global document state, so one
organization's decision cannot leak into or govern another organization's review.

### Confidentiality

- Raw screening documents are HR-vault records, not room-operation records.
- Educators, dispatchers and other candidates never receive the police-check image or result text.
- Operational services receive a derived readiness fact only, such as `driver_ready=true`, plus
  the governing decision/version and expiry.
- Notifications say that a document needs attention; sensitive findings never appear in push
  notification bodies, analytics or ordinary audit detail.

## Jobs, applications and offers

Every listing declares a position shape:

- `educator_only`, `driver_only`, or `educator_driver`;
- driving `not_applicable`, `preferred`, or `required`;
- organization vehicle, personal vehicle, either, or no vehicle expectation;
- required licence class/endorsement and minimum approved experience;
- service area and typical windows without exposing child addresses;
- pay range, mileage/expense policy and whether driving time is paid; and
- conditions that must be complete before start or before the first driving assignment.

A later offer cannot add driving duties invisibly. Driving responsibility, personal-vehicle use,
compensation and conditions are versioned offer terms requiring explicit candidate acceptance.

## Vehicle readiness

Vehicle source is explicit: organization-owned, staff personal, rental or contractor. Personal
vehicle readiness keeps these records separate:

- owner/authorized-use evidence;
- registration;
- applicable automobile and business-use coverage confirmation;
- insurer/organization approval decision;
- inspection and defect status;
- make/model/year/plate with restricted visibility;
- seat and approved-restraint capacity by child requirement;
- accessibility capabilities; and
- effective/expiry dates.

One expired or rejected prerequisite makes the vehicle unavailable for new dispatches. Historical
trips retain the exact driver, vehicle and readiness versions used at departure.

## Child transport authority

Home or school transport begins with a child-specific, effective-dated plan containing:

- guardian request and signed consent version;
- approved origins, destinations and receiving people;
- normal schedule and exception policy;
- medical, accessibility, restraint and emergency requirements;
- people permitted to request or cancel a trip;
- failed-handoff instructions; and
- facility approval and review date.

An urgent parent request is not itself a dispatch. The approved plan and all current readiness
facts must still be satisfied, or an authorized manager records a separately designed exception
workflow that keeps the child in program custody until a lawful safe path exists.

## Dispatch state machine

```text
requested
→ reviewed
→ assigned driver + vehicle
→ readiness preflight passed
→ manifest sealed
→ boarding verified
→ departed
→ destination arrived
→ approved receiver handoff
→ vehicle sweep
→ completed
```

Exceptional states are `cancelled`, `delayed`, `failed_handoff`, `vehicle_out_of_service`,
`incident_open` and `returned_to_facility`. State transitions are append-only commands with exact
retry receipts and realtime invalidations.

The departure preflight checks the exact child, consent, driver, vehicle, shift, route, capacity,
restraint, portable emergency record, weather/risk decision and receiving plan. It also removes the
driver from on-site staffing/ratio availability for the trip interval.

## Staff-app trip mode

After accepting an assigned run, the staff app changes to a focused trip workspace:

- only the assigned run and children are visible;
- child addresses become available only after the dispatch is sealed and expire after completion;
- the manifest supports deliberate boarding/deboarding and headcounts;
- child safety facts are minimum-necessary and available offline through an encrypted, expiring
  trip pack with post-trip reconciliation;
- navigation may be opened from the assigned stop without creating a permanent staff address
  book;
- receiver handoff uses the approved-person record and server-authoritative time;
- failed handoff keeps the child in custody and opens the escalation instructions; and
- a deliberate front-to-back vehicle sweep is required before completion.

CareSync will not use permanent employee location tracking, background surveillance, facial
recognition or an automatic police/suitability decision.

## Administrator workspace

The portal needs five connected queues:

1. screening documents awaiting authorized review;
2. upcoming expiries and recheck deadlines;
3. drivers/vehicles blocked from assignment with a safe resolution path;
4. transport requests awaiting plan or dispatch approval; and
5. active/delayed/failed-handoff trips with realtime status.

Every queue links to the exact person, vehicle, child plan or trip version without exposing more
private data than the reviewer needs.

## Data and command families

Likely records:

- `staff_screening_documents`, `staff_screening_document_versions`,
  `staff_screening_reviews`;
- `staff_capabilities`, `driver_qualifications`, `driver_authorizations`;
- `vehicles`, `vehicle_document_versions`, `vehicle_readiness_decisions`;
- `child_transport_plans`, `child_transport_plan_versions`, `transport_consents`;
- `transport_requests`, `transport_runs`, `transport_run_stops`,
  `transport_run_manifest_entries`;
- `transport_events`, `transport_command_receipts`, and minimum-public realtime events.

All child-custody mutations use one command spine, actor/facility scope, immutable event history,
exact retry semantics and bounded public failures.

## Delivery order

1. Add criminal/vulnerable-sector document classes and confidential review lifecycle to candidate
   onboarding and the staff profile.
2. Add educator/driver/combined job requirements and versioned offer conditions.
3. Build driver and vehicle registries with readiness calculation and expiry lockout.
4. Build child transport plans and guardian consent without dispatch.
5. Build administrator dispatch and ratio/schedule integration.
6. Build staff-app trip mode, handoff, sweep and realtime updates.
7. Add encrypted offline trip continuity, incident/breakdown handling and evidence export.

This phase begins after the current verified child-release milestone reaches its disposable
PostgreSQL and connected-device gates; the screening-document slice can start first because it is
independent of live transport dispatch.

## Accepted first implementation slice

The first additive revision is `0030_staff_screening_paths`. It is candidate-to-offer complete
but deliberately grants no operational transport authority.

- Account registration remains limited to first name, last name, email and password.
- Post-authentication onboarding adds `educator`, `student_educator`, `driver` and
  `educator_driver` pathways.
- Criminal-record and vulnerable-sector evidence uses a dedicated confidential document/version,
  candidate-confirmation, application-share and authorized employer-review lifecycle. It does not
  reuse the general certificate/resume analysis table.
- Candidate driving declarations are always labelled candidate-provided. They may describe licence
  class, vehicle access and preferred service radius, but can never produce `driver_ready`.
- Listings and offers gain structured educator/driver duties, vehicle expectations, service windows,
  mileage/paid-driving terms and immutable candidate acknowledgment of the exact offer version.
- Police findings, full OCR text, document numbers, dates of birth and storage paths do not enter
  ordinary ATS cards, realtime payloads, push text or analytics.
- Provisioning must not create an active child-access membership when an activated screening policy
  requires readiness and the application has no current employer-approved screening decision.

Licence/abstract verification, insurance, vehicle approval, child transport plans, addresses,
dispatch, manifests, handoff, routing and vehicle sweep remain in the following transport release.
This separation prevents a reliable-car declaration or accepted driving offer from becoming child
transport permission.

## Accepted second implementation slice

The additive `0031_driver_vehicle_registry` revision is a read-only registry foundation, not an
operational transport release.

- It records immutable, sequential staff driver declarations and current qualification lanes.
- Employer authorization requires a different active reviewer and cannot outlive the exact
  referenced verified driver licence.
- Organization and staff-personal vehicle identities have immutable physical/evidence versions;
  retirement is one-way.
- PostgreSQL RLS and restricted runtime grants are read-only. Partial schema, trigger, policy or
  grant drift fails startup.
- `/staff/self` advertises an exact capability marker and the only registry endpoint returns the
  signed-in staff member's bounded private projection with `Cache-Control: private, no-store`.
- The staff app presents that projection read-only. The administrator manager workspace stays
  absent because no manager command capability exists yet.
- Every layer fixes `operational_driver_ready=false` and `dispatch_authorized=false` and rejects an
  authority-granting response.

0031 intentionally has no upload, registration, review, suspension, renewal or readiness mutation
API. It contains no child transport plan, address, route, manifest, dispatch, trip, handoff, GPS or
offline trip pack. Those commands require their own exact-retry receipts, evidence-vault lifecycle,
permissions, concurrency and disposable PostgreSQL gates before any UI is exposed.

## Accepted third implementation slice

The additive `0032_transport_commands` source revision is the bounded transport-registry
evidence, review and command layer. It is not a child-transport or dispatch release, and this
architecture acceptance alone is not verification evidence; the later recorded disposable and
client gates establish source verification only.

The allowed command families are limited to:

- append or withdraw a staff driver declaration;
- ingest an encrypted, clean-scanned driver-qualification evidence object;
- append an independent review of one exact qualification-evidence version;
- append a driver-authorization decision bound to exact capability and qualification versions;
- create, version or retire a registry vehicle;
- ingest an encrypted, clean-scanned vehicle-evidence version;
- append an independent review of one exact vehicle-evidence version; and
- append a point-in-time readiness evaluation and its generic expiry-attention records.

Every command uses an actor-private, organization-scoped client operation ID and a canonical
request digest. The result fact, audit record and retry receipt commit together. An exact retry
returns the original result; reuse of the operation ID for changed intent fails. Clients keep the
operation ID through an ambiguous response and reconcile through the receipt rather than issuing a
new command.

PostgreSQL exposes one narrow `SECURITY DEFINER` repository function. Its owner is a dedicated
`NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS` command role. The normal restricted API identity and a
separate server-only evidence-ingest identity receive only the exact `EXECUTE` surface required by
their lanes; neither receives direct table DML. Evidence commands are rejected from the normal API
database identity. The evidence-ingest adapter, not a client form, supplies server-measured object
identity, encrypted storage reference, ciphertext digest, scanner engine/version and scan time.
Only clean scanned evidence may become a review source.

Review remains maker/checker:

- the reviewer must be a current authorized manager in the same organization;
- the reviewer must differ from the staff member or vehicle owner under review;
- the reviewer must also differ from the source uploader/recorder; and
- a decision binds immutable source and result versions, never a mutable “current document.”

Readiness is an evidence record, not transport permission. Evaluation uses the latest effective
declaration/capability, current authorization, exact verified qualification versions, current
vehicle version and current verified vehicle evidence. Expired evidence blocks the evaluation;
near-expiry facts create generic, deduplicated attention records without putting private document
content in notification text. Concurrent revocation, retirement or evidence change must serialize
with evaluation so a stale snapshot cannot be presented as current.

At this slice every database constraint, receipt, API schema and client parser still fixes
`operational_driver_ready=false` and `dispatch_authorized=false`. The revision creates no child
transport plan or consent, child/home/school address, route, manifest, run, trip, handoff,
dispatch, GPS/location tracking or offline trip pack. Those require later architecture and their
own custody, minimum-necessary disclosure, capacity, ratio, preflight and departure gates.

Administrator and staff clients may expose 0032 only after the server returns the exact complete
0032 capability contract. A partial, extra, crossed-tenant or authority-granting marker fails
closed. The verified administrator workspace is gated by `transport:manage`; the staff app exposes
only its bounded self-service projection. Evidence actions are independently disabled unless the
server advertises a usable ingest path. Neither client invents mutation or transport authority.

### Third-slice source verification closed; release gates still open

At the 2026-07-21 checkpoint, 0032 is verified source against portable tests and fresh disposable
PostgreSQL 17 clusters. It is still unreleased. The completed source gates are concrete:

1. the migration, detector, restricted-role bootstrap, repository, API and exact capability
   contract are frozen as one all-or-nothing boundary;
2. the dedicated writer owner, evidence-ingest terminal identity, exact function grants, forced
   RLS and absence of direct runtime table DML are proven;
3. exact replay, changed-intent rejection, atomic rollback, actor/tenant isolation,
   concurrent revocation safety, independent review, uploader/reviewer separation and clean-scan
   binding are tested;
4. latest-version/expiry evaluation, generic deduplicated attention records and unconditional
   false authority flags are tested;
5. canonical normalized source hashes pin all 15 repository/guard functions and the exact 23
   enabled protected-table triggers; weakened bodies, trigger topology and ACL/policy drift fail
   startup and bootstrap attestation; and
6. capability-gated administrator and staff-app integrations pass their full test, typecheck and
   build gates.

The remaining operational-acceptance gates are real scanner/vault operation,
vault-key custody and rotation, crash reconciliation,
retention/legal-hold/purge, backup/restore, operator and physical-device
walkthroughs, and accessibility/privacy/regulatory acceptance. The later
guarded retained cutovers installed the schema but did not satisfy those
operator/provider gates or create transport authority.

### Source-only document-intake readiness hardening

The 2026-07-21 operational hardening pass separates the staged 0030 schema from its confidential
upload pipeline. Startup probes the private vault, active encryption key and scanner once whenever
0030 is present. At the earlier retained-0028 checkpoint no staged vault was
created or scanned; the current retained schema includes 0030 but still
requires the independent runtime probe. New 0030 uploads
and 0032 evidence commands fail closed unless that shared pipeline is ready. Existing document
metadata, authenticated source retrieval attempts, pending candidate confirmation, exact sharing
and employer review stay separate from upload availability. Health and candidate bootstrap expose
only a non-diagnostic `ready`/`unavailable` or Boolean capability; neither returns vault paths,
key/scanner diagnostics or evidence facts. The staff app hides only new/replacement upload controls
when intake pauses and preserves history, declarations, confirmation and sharing.

A lost database response during a 0030 document commit is now treated as an unknowable outcome.
CareSync retains the ciphertext, returns stable reload-before-retry recovery instructions and does
not issue an automatic second upload. A deterministic failed transaction still compensates by
removing the unadopted ciphertext. Historical-key rotation is not claimed: reads currently require
the row's `encryption_key_id` to match the configured active ID exactly, so an informal key or ID
change fails closed instead of silently trying the wrong key. A release keyring, coverage proof and
rewrap/rotation receipts remain mandatory before any deliberate rotation.

### Backup-bound encrypted-vault recovery set

The source now includes a non-mutating preflight for the shared staff/transport encrypted vault. A
verified logical backup is the sole expected-inventory source. The preflight pins and rechecks the
backup and manifest, derives the exact union of 0030 screening versions, 0032 qualification objects
and vehicle evidence versions, rejects cross-domain aliases and validates the one original uploader
behind shared vehicle review history. Vault and output traversal are descriptor-relative and
no-follow; ciphertext size and SHA-256 are measured without reading key material or decrypting the
document. Findings remain explicit as missing, mismatched, unsafe, unexpected or indeterminate.

The mode-0600 receipt is no-clobber and binds backup/manifest/row hashes, revisions, inventory,
ownership relationships and per-key-ID counts. It always records
`consistencyAuthority=false`, `purgeAuthority=false` and
`blocker=snapshot_boundary_unproven`. There is no live-database, migration, archive, restore,
decryption, deletion or purge route in this report-only tool.

`backend/scripts/staff_transport_vault_bundle.py` adds the recovery artifact that the preflight
deliberately did not claim. It keeps the verified database backup and manifest pinned while deriving
the same exact 0030/0032 inventory, refuses every missing, mismatched, unsafe, unexpected or
indeterminate vault state, and stores every referenced ciphertext. Historical screening versions,
qualification evidence and vehicle `provided`/`verified`/`rejected`/`expired`/`revoked` review
relationships remain represented; a shared vehicle object is archived once with all source
relationships preserved in its private manifest. The archive is deterministic, uncompressed,
mode-0600 and no-clobber. Its deterministic private manifest binds the compressed backup,
backup-manifest and row-stream hashes, exact revisions, storage ownership, plaintext/ciphertext
measurements and encryption-key IDs.

Verification re-derives the inventory from the database artifact and rejects duplicate, undeclared,
linked, compressed, non-private, size-mismatched or digest-mismatched archive members. Restore only
creates a new mode-0700 private root, writes mode-0600 ciphertext without merging, re-runs exact
vault analysis, synchronizes the tree and optionally writes a no-clobber receipt. No confidential
bytes are decrypted.

This closes deterministic ciphertext backup/restore for one verified logical backup; it does not
turn that backup into proof that live database writers and vault writers were quiescent at one
instant. Bundle manifests therefore retain
`databaseVaultConsistencyAuthority=false`, `purgeAuthority=false` and
`limitation=logical_backup_snapshot_boundary_unproven`. The encrypted bundle also does **not**
contain `staff-screening-vault.key`. Operators must separately retain that mode-0600 key under
approved custody, prove every manifest key ID is covered before cutover and keep key rotation/rewrap
as an explicit operation. Current runtime reads still require the row key ID to equal the active
configured key ID.

## Verification and release state

The 0030 source boundary is verified against portable tests and a fresh disposable restricted-role
PostgreSQL 17 database. The 0031 read-only boundary also passed a fresh PostgreSQL 17 high-port gate
covering full migration, forced RLS, restricted grants, user-and-organization isolation, immutable
facts, independent-review and licence-expiry guards, bounded self projection and populated-downgrade
refusal. Revisions 0030–0034, including the owner/administrator transport
permission repair, were installed by the guarded 0036 cutover and remain in
the retained `0039_admissions_decision_spine` schema. The 0037/0038 checkpoints
remain historical, and neither public-job replay nor admissions adds child-
transport or dispatch authority. Restricted-role health and
signed-in capability checks passed; this still creates no operational child-
transport or dispatch authority. The explicit evidence and unresolved
operator/provider work are recorded in `docs/PRODUCT_IMPLEMENTATION_LEDGER.md`.

Before live screening or transport evidence can be treated as operationally accepted, CareSync
still requires a real malware-scanner adapter and operator proof,
release vault-key custody and rotation, crash reconciliation, explicit retention/legal-hold/purge
rules, concurrency stress, immutable ECE evidence binding, police-check freshness for documents
without an expiry and separation of candidate self-review from employer review. The completed-
candidate versioning/reapplication path is locally available within those
truthful gates. Operational driver and child-transport authority remain a
later release even after the screening gates close.

The accepted 0032 architecture was staged beyond 0031 and is now part of the
retained local schema, while its operational authority remains false. The
portable backend gate passed 123/123; the fresh disposable PostgreSQL 17 command/tamper gate passed
7/7; the administrator passed TypeScript, 591/591 tests and a production build; and the staff app
passed TypeScript and 227/227 tests. The complete default backend regression passed 935 tests with
90 expected opt-in PostgreSQL skips and seven deprecation warnings. These are separate, overlapping
verification records and are not summed. Later integrated release evidence
supersedes these historical suite counts: 0037 remains recorded in
`docs/LOCAL_RELEASE_0037_CUTOVER.md`, 0038 is recorded in
`docs/LOCAL_RELEASE_0038_CUTOVER.md`, and current 0039 evidence is recorded in
`docs/LOCAL_RELEASE_0039_CUTOVER.md`.

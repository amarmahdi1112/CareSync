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

# CareSync MVP readiness audit

Last updated: 2026-07-23

## Decision statement

CareSync is being hardened as a **local functional MVP**, not declared a
production-ready childcare SaaS. The current release candidate demonstrates
the core administrator, candidate, hiring, staff, attendance, daily-care,
medication and incident workflows against one authoritative FastAPI/PostgreSQL
backend. The current source also includes a daily staff rota with educator
responses, planned-versus-actual clock reconciliation, recurring availability,
time-off decisions, reusable shift templates, operational coverage targets,
recurring rotations, open coverage, substitute opt-in and consent/approval-based
whole-shift exchanges.
Commercial launch remains blocked until the production controls in
this document are completed and independently exercised.

The retained port-5434 database remains at
`0039_admissions_decision_spine`. The checked-in source and launcher now target
verified-source `0042_billing_policy_recert`; no 0041 or 0042 retained cutover
has occurred. The guarded 2026-07-23 retained 0039 promotion captured and
exactly restored the 16,445-row / 135-table 0038 source, verified two
zero-object evidence-vault restores with private receipts, and preserved all
110 families, 203 children and 197 enrollments. Revision 0039 adds the private
administrator admissions lifecycle while retaining the 0038 public-job replay,
0037 agreement-scope repair and 0036 private/manual billing protocol. Facility
release and private manual billing each retain a separate explicit activation;
migration and startup activated neither.

The advanced V3 attendance analyzer/scheduler remains intentionally hidden from
the Basic product. It is preserved for later integration and is not part of the
MVP acceptance boundary.

## Preserved data and runtime boundary

- The active Basic database is `caresync` in the isolated PostgreSQL 17 cluster
  on port `5434`, still at `0039_admissions_decision_spine`.
- Checked-in source extends through `0041_live_room_presence` and
  `0042_billing_policy_recert`; this source state is verified only on
  disposable databases and must not be described as the retained runtime.
- The API runtime uses the restricted `caresync_basic_app` role. Migrations run
  separately as the local migration owner.
- The retained legacy clone on port `5433` is not the default runtime.
- The original project and legacy data were not deleted during hardening.
- The active database contains the migrated organization, facility, rooms,
  families and children required for realistic local testing.
- The current cutover backup is
  `~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-052743-592770.json.gz`;
  its matching manifest is beside it and its exact-restore receipt is under
  `~/Library/Application Support/CareSync Basic/restore-verifications/`.
  The backup and port-56555 disposable restore each contain 16,445 rows across
  all 135 public source tables at 0038, including 110 families and 203
  children, with canonical row digest
  `7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
  The family and staff/transport evidence bundles each restored zero objects
  and have sibling private receipts.
- The historical 0038 cutover backup is
  `~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.gz`.
  Its exact 16,335-row / 134-table 0037 restore and 0038 promotion remain
  recorded in `docs/LOCAL_RELEASE_0038_CUTOVER.md`.
- The historical 0037 cutover backup is
  `~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-005011-912450.json.gz`.
  Its exact 16,309-row / 134-table 0036 restore and 0037 promotion remain
  recorded in `docs/LOCAL_RELEASE_0037_CUTOVER.md`.
- The historical 0036 cutover backup is
  `~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.gz`.
  Its exact 16,260-row / 77-table 0028 restore and later 0036 promotion remain
  recorded in `docs/LOCAL_RELEASE_0036_CUTOVER.md`.
- The historical verified pre-`0028` backup is
  `~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260717-120050-877200.json.gz`.
  Its compressed SHA-256 is
  `64220acf9e233ef81571305324239b77d9c9cd70df0dfd761ef21d41ae89553d`;
  its uncompressed JSON-lines SHA-256 is
  `712000703124bdb9e4e7b98ec21955e8003ac0db2718044e1868da541cfae893`;
  and its row-only SHA-256 is
  `5378a43b7dd7c5bb058dac5790a9ba6a15d60adf81de075e56b715580767c325`.
  The v2 manifest records 1,830 rows across all 71 pre-migration tables, and a
  fresh disposable restore matched every table count and the row-only digest.
  The canonical internal directory is `0700` and its files are `0600`; T7
  project copies are ExFAT mirrors and not the permission-authoritative archive.
- A separate private post-0029-verification-recovery v2 backup is retained at
  `/Users/amarmuha/Documents/Codex/2026-07-13/hel/caresync-incident-backups/caresync-postgres-20260717-200103-673906.json.gz`.
  Its compressed SHA-256 is
  `d83dfaea0410f03c591d441c5b0f6fe96e863d32f1204e154d34fb3390480fad`.
  An exact restore into a fresh disposable PostgreSQL instance reproduced
  revision `0028_childcare_command_spine`, 1,834 rows across 77 tables including
  `alembic_version`, 203 children, 110 families and zero 0029 authority tables.

## Implemented MVP vertical slices

### Identity and tenancy

- Email/password login and current-session restore.
- Explicit organization context on protected requests.
- Multi-organization choice and switching in the admin portal.
- Organization membership, role and permission enforcement in the API.
- Fail-closed handling is required whenever an account, organization or
  membership boundary is revoked; ordinary feature-level permission denial is
  kept distinct from tenancy loss.

### Organization, family and child operations

- Organization, facility, program and room setup.
- Room age ranges and approval-based age/DOB room recommendation.
- Family and child records, guardian relationships and room enrolment.
- Full family and child profile routes rather than detail drawers.
- Child photos and room rosters.
- A private administrator Admissions lifecycle with versioned intake,
  submission/review, deterministic waitlist lanes, program offers,
  correction/withdrawal/decline and duplicate-reviewed atomic conversion into
  canonical Family, Child and pending unassigned Enrollment records.
- A separate derived Admissions review queue that identifies actionable
  family-lifecycle, enrollment and room-placement contradictions and routes to
  the exact owning workflow. It does not invent an application, decision,
  completeness attestation or regulatory certification.

### Cross-feature communication

- One shared backend/admin realtime entity vocabulary, with automated rejection of unknown or
  unbounded command producers.
- Transactional outbox acceptance covering representative organization, childcare, ATS and
  workforce commands at the retained 0028 schema boundary.
- Mounted admin screens re-read canonical REST state after matching invalidations; a socket cursor
  advances only after all matching reloads succeed.
- Organization changes refresh the persistent session shell without replacing a valid login, while
  organization/membership/role contradictions fail closed.
- Medication and workforce notification actions re-resolve the exact tenant-scoped record and
  fail visibly on malformed, stale or unauthorized targets instead of selecting a fallback.
- Request sequencing prevents an older Children or candidate-discovery response from overwriting a
  newer realtime snapshot, and an opened exact medication plan refreshes in the same checkpoint as
  the surrounding room-day projection.
- Staff, candidate-tenant and user-private mobile streams use separate encrypted checkpoints. A
  checkpoint waits for its parent and exact mounted canonical surface, and rejects identity,
  membership, unmount, stale-connection or failed-read races.
- Candidate-private `marketplace.*` invalidations refresh the mounted profile/onboarding/career
  state quietly. Only a separate eligible notification-ledger row can create attention.
- Routine synchronization remains quiet. Notifications are reserved for decisions, responses and
  remediation work rather than being used as an internal event bus.
- Admissions uses the distinct `admission_application`, `admission_waitlist`
  and `admission_offer` realtime entities. Payloads omit intake/contact PII,
  canonical REST reloads before cursor advancement, and the ATS `application`
  entity remains separate.

### Public candidate marketplace and ATS

- Independent candidate account creation and onboarding.
- Certificate/student pathways, OCR-assisted credential extraction, explicit
  candidate confirmation and credential-image history.
- Public job discovery, applications and immutable job snapshots.
- Privacy-safe durable public-catalog invalidations replay open-listing edits
  and final closure to unaffiliated candidates without exposing organization,
  listing-text, candidate or tenant-private workflow data.
- Candidate status history, interviews with counter-proposals, offers with
  expiry/terms, acceptance and employee provisioning.
- Employer listings, applicant pipeline, interviews, offers, withdrawal and
  staff assignment.
- Employer offer creation and publication are one atomic, idempotent command;
  retrying an ambiguous response cannot supersede the offer just sent.

### Staff operations

- Employee workplace selection and server-authoritative permissions.
- Staff assignment, credential and open-shift projection.
- Location-free staff clock-in/out for the current local test configuration.
- Child mutations blocked unless the employee has a confirmed open shift.
- Daily staff rota with a facility-aware weekly administrator planner, private
  drafts, optimistic draft editing, publication, cancellation with a reason
  and manager resolution of educator alternate-time proposals.
- Staff-app My Shifts views for Today, Upcoming and History, with acknowledge,
  decline and propose-alternate actions. Facility-local date/time entry rejects
  ambiguous or nonexistent daylight-saving times.
- Planned assignments remain separate from server-timestamped actual shift
  evidence. An acknowledged published assignment can link one actual clock
  record; existing ad-hoc clocking remains visible as `unscheduled`.
- Canonical reconciliation identifies upcoming, active, completed, late,
  missed, cancelled and unscheduled work and powers the administrator's
  planned-versus-actual monitor.
- Schedule-response ambiguity is protected by an encrypted identity-scoped
  mobile checkpoint. Admin forms and the app retain the exact operation ID
  after network/protocol ambiguity and block changed intent until exact retry.
- Workforce planning now includes staff-owned weekly availability, explicit
  unavailable-versus-unspecified semantics, membership-wide time-off requests,
  manager approval/decline/cancellation, reusable facility-local shift
  templates and bounded 15-minute coverage projections.
- Approved leave is an absolute publication blocker across facilities. An
  availability mismatch alone may be overridden with a nonblank reason stored
  on the published shift and immutable audit/event evidence. Declined
  assignments are excluded from operational coverage safety.
- The staff app persists one identity-scoped workforce mutation before sending
  it and reconciles ambiguous outcomes through exact operation receipts. The
  administrator portal uses the same fail-closed optimistic/idempotent contract.
- Room/facility closure uses an impact preview, hard live-operation blockers,
  visible dependency warnings, exact-name confirmation and a required reason.
- New child/staff operational starts serialize with closure. A closed room or
  program cannot accept a new child check-in, while existing staff shifts can
  still be closed safely after assignment or room deactivation.
- Room roster and child safety context.
- Child check-in/check-out with idempotent retries and response-loss recovery.
- Daily care events for meals/bottles, diapers, toilet, sleep, mood and
  activities, with authorized correction/void history.
- Pending Care Recovery Center with encrypted identity-scoped persistence,
  strict restored-queue integrity checks, serialized mutations, capped retry
  backoff, realtime/foreground recovery, per-facility replay boundaries and
  child-day stream isolation. Local work is removed only after the backend
  returns its exact immutable create-operation receipt and matching tenancy,
  attendance, child, facility and room boundary.
- Definitive first-response care validation errors stay editable. Ambiguous
  responses retain the original command/UUID, and an encrypted-storage failure
  locks that exact in-memory attempt rather than allowing a duplicate command.
- Medication daybook, plan gating, administration/refusal/omission, immutable
  snapshots and correction history.
- Incident drafting, encrypted unfinished local drafts, versioned server drafts
  and explicit internal-review handoff.
- Read-only daily-close preview for one bounded room/day, combining factual
  attendance duration/state, six care counts, medication outcomes, incident
  statuses and five attention flags without exposing narratives or claiming
  completeness, compliance or guardian delivery.
- Realtime invalidation followed by canonical REST refresh before durable cursor
  advancement.
- A user-private notification ledger/stream with strict recipient boundaries,
  generic lock-screen payloads, exact authorized record navigation, preference
  handling and identity/workplace-bound navigation cleanup.
- The Android development-client APK has been built, installed and launched on
  a connected Pixel through ADB, using reverse tunnels for Metro and the local
  API. This validates native installation and local connectivity, not remote
  operating-system push delivery.

### Data and backend safety

- The retained live-local database is at released head
  `0039_admissions_decision_spine`. Revisions 0029–0039 are present in the
  retained schema, but their runtime meaning remains bounded: neither
  owner-controlled activation exists, screening/transport evidence never
  grants operational child transport, and the 0036 manual billing protocol
  cannot command until owner activation. Revision 0037 changes agreement
  identity, not billing authority. Revision 0038 adds only a minimal
  public-catalog invalidation/replay fact; canonical ATS/marketplace reads
  remain authoritative. Revision 0039 adds six forced-RLS admissions tables,
  exact command provenance and duplicate-safe conversion, but no public/parent
  admissions or automatic room, billing, funding or transport authority.
  Before the final guarded promotion, one plain
  Alembic command inherited `.env` and briefly applied the empty 0029A schema
  to retained port 5434. All ten new tables and all authority/new-target
  receipts were empty; an exact empty-only downgrade restored 0028, and an
  independent read-only check confirmed zero authority tables. No product or
  authority rows were migrated or rewritten, but the temporary schema advance
  is recorded rather than described as never having occurred. Revisions `0025`
  through `0027` add rota, workforce planning
  and Staff Exchange while preserving actual clock evidence as a separate
  truth. Revision `0028` adds versioned exact-retry child-domain commands and
  non-destructive temporal care-network history. That earlier incident is
  preserved as history and is separate from the later successful guarded
  0028-to-0036 cutover and the subsequent guarded 0036-to-0037 and
  0037-to-0038 and 0038-to-0039 cutovers.
- PostgreSQL row-level-security/grant bootstrap for the runtime role.
- Alembic operations fail closed on protected local ports 5432, 5433 and 5434.
  Development requires the exact command-scoped
  `CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true` opt-in; tests cannot
  bypass it, and seven focused tests cover the guard. Startup is pinned to
  `RELEASED_REVISION=0039_admissions_decision_spine`, skips Alembic when retained
  state already matches and never upgrades retained data to an inferred
  source `head`.
- Attendance operation IDs are unique and safely replayable.
- Daily-care create/mutation operation IDs are PostgreSQL advisory-locked.
  Concurrent exact create retries return one canonical record and the immutable
  recorded-operation receipt; a changed command reusing that ID returns `409`.
- Candidate projections suppress employer-only draft offers.
- AppleDouble `._*` metadata is removed from source before Alembic/Vite scans
  the T7 volume.
- Database writes are enabled only in the isolated Basic runtime.
- Rota mutations are exactly idempotent; changed-intent operation-ID reuse is
  rejected. Advisory locks serialize each educator's schedule lane and
  overlapping non-cancelled assignments are refused.
- Staff-self schedule responses recheck organization and membership ownership
  before returning an idempotent replay, preventing cross-educator response
  disclosure.
- Migration `0025` is additive to existing clock evidence: prior actual shifts
  retain a null planned link and appear as unscheduled. It performs no guessed
  historical rota backfill and deletes no existing clock event.
- Migration `0026_staff_workforce` is additive and live. It
  adds availability, leave, template, coverage-target and append-only workforce
  event tables plus the scheduled-shift availability override evidence field.
  Projection "deletes" are tombstones; the runtime role receives no table
  `DELETE`, and the immutable event table receives no `UPDATE` or `DELETE`.
- Disposable PostgreSQL 17 verification exercised `0025 -> 0026 -> 0025 ->
  0026`, forced tenant RLS, least grants and the publication/leave and
  publication/availability race orders. The live five-table boundary was also
  verified for forced RLS, one tenant policy per table and expected grants.
- Revision `0027_staff_exchange` adds recurring rotation drafts, open shifts,
  explicit staff acceptance of manager offers, staff-owned substitute opt-in
  and consent plus manager approval for atomic whole-shift replacement. Its
  five projections and existing workforce ledger use forced RLS and least
  grants; no interest or peer consent silently assigns work.
- Revision `0028_childcare_command_spine` adds six RLS-forced
  command/reconciliation tables, positive record versions, actor-private exact
  operation receipts, temporal guardian/emergency-contact retirement, active
  enrollment invariants, program-scoped capacity checks and actionable
  readiness routes. The restricted runtime owns no database objects and cannot
  mutate append-only history.

## Verification evidence

The table below records the completed `0028_childcare_command_spine` local release
evidence.

| Surface | Evidence |
|---|---|
| Backend lint | All maintained Python source passed Ruff; generated legacy ORM snapshot excluded; bytecode compilation passed |
| Backend tests | 387 passed, 41 expected opt-in database skips |
| Real PostgreSQL tests | Final application/RLS/concurrency matrix passed 38/38; backup/restore database drills passed |
| Migration | Fresh-process `0027 -> 0028 -> 0027 -> 0028` passed 1/1; populated-history downgrade refusal was atomic; live head is `0028_childcare_command_spine` |
| Python dependencies | `uv pip check` passed; `pip-audit` found no known vulnerabilities |
| Admin portal | 79 test files / 471 tests passed; TypeScript and production build passed, transforming 830 modules |
| Admin dependencies | production `npm audit` found zero vulnerabilities |
| Staff app | 138 tests passed; TypeScript passed; Expo Doctor 20/20; Android export passed at 740 modules on Expo SDK 57 patch releases |
| Live local release | Private v2 backup and exact disposable restore receipt retained; `0028_childcare_command_spine` applied on PostgreSQL 17 port 5434; all six new tables have forced RLS and begin empty |
| Live data preservation | All 1,830 rows across the 71-table pre-migration schema matched exact counts and row digest before cutover; live schema is additive at 77 public tables |
| Runtime smoke | API health and admin portal returned 200; an authenticated client re-established both realtime streams after restart |
| Signed-in operator smoke | Full child-domain command walkthrough remains an explicit hands-on acceptance item |

The later 2026-07-21 no-migration operational checkpoint did not change that
released-0028 evidence table. Its current-source regression is 941 backend tests
passed with 90 explicit opt-in PostgreSQL skips, 614 administrator tests plus
TypeScript/build, and 242 staff-app tests plus TypeScript. It covers exact
notification work-item navigation and the factual room daily-close preview; it
does not imply a migration, retained-release promotion or production acceptance.

Subsequent live-local verification also proved the Dashboard-to-family-status remediation path for
Pending-family enrollment contradictions, including exact child/enrollment binding, permission
guidance, one family editor and native link semantics. The optional transport capability no longer
restarts authenticated workspace bootstrap on its expected retained-schema 403, and an exact
closed-transport websocket race is handled as a disconnect rather than an application error.

The completed 2026-07-22 integration checkpoint supersedes the earlier current-source counts
without changing the released-0028 evidence above: 959 backend tests passed with 90 explicit
opt-in PostgreSQL skips; 105 administrator test files / 677 tests, TypeScript and the 857-module
production build passed; and 252 staff-app tests plus TypeScript passed. Runtime proof used the
actual `/api/v1/health` contract, confirmed PostgreSQL connectivity, confirmed unauthenticated
Admissions fails closed, observed both authenticated realtime sockets reconnect, and reloaded the
signed-in seven-case Admissions queue with exact canonical actions and no browser warning/error.
This is local functional evidence, not production, regulatory, accessibility or physical-device
acceptance, and it performed no retained migration or data rewrite.

The later 0029 authority/release closeout and recovery-consistency hardening supersede those
current-source totals, not the retained 0028 release evidence: 1,040 backend tests passed with 94
deliberately opt-in disposable-PostgreSQL/scanner/operator/recovery cases skipped and seven
non-failing dependency warnings; the focused
authority/realtime backend matrix passed 47 tests plus Ruff; the administrator passed 107 test
files / 691 tests and its production build; and the staff app passed 263 tests and TypeScript.

These are necessary automated gates, not substitutes for physical-device,
operator, accessibility, privacy and regulatory acceptance testing.

### Staged 0029A/A1/A2/B/C/D family authority — not an MVP release

The canonical `0029A_family_authority_kernel`, additive
`0029A1_family_evidence_vault` and exact revision `0029A2_authority_activation`, strict schemas,
layered runtime gates, confidential family workspace, authority-person
create/full-replace/terminal-retire services and authority-evidence
record/review/reject/invalidate/supersede lifecycle are verified in source on
disposable databases. Historical exact retry, immutable assessment history,
terminal lifecycle state, actor privacy, owner/administrator authorization,
affected-child revision invalidation, missing-head rollback, direct-SQL
constraints and restricted-role PostgreSQL behavior are covered.
Confidential workspace/policy reads and command replay projections now acquire the canonical
aggregate lock before rechecking the actor's current owner/administrator role; role loss fails 403
without projecting authority data. The administrator distinguishes evidence recorded by the
current maker from evidence ready for that actor's review, permits the maker to reject but never
review their own submission, and focuses only the exact typed authority record addressed by a
receipt link.

A1 adds server-authored, no-clobber private PDF/JPEG/PNG upload; measured media, size and SHA-256;
quarantine and fixed-adapter scan commands; resource-bounded isolated document parsing; clean-only
download and single-use evidence binding; and a reviewer distinct from the uploader/recorder for
document approval. Rejected and invalid-document bytes remain canonical private records. A
four-artifact database/vault backup consistency set is implemented, and the vault reconciler is
report-only and never deletes.

A2 adds administrator release authorization grant/revoke, bounded `deny`/`manager_review` rule
create/revoke, immutable policy publish/list and child consent record/withdraw. Its exact positive
lanes use guardian attestation, custody document and original-guardian signed release delegation;
consent always separates `signed_consent` decision evidence from guardian-attestation or
custody-document signer authority. Policy content is readable immutable `content_text`; the server
derives its SHA-256 and canonical reference. The activation gate proves schema shape, triggers,
forced RLS and exact grants before an A2 ORM query. At the A2 boundary,
`attendance_release_snapshots` remained SELECT-only scaffolding; staged C source extends it without
changing retained state.

The 2026-07-18 A2 closeout recorded 170/170 focused authority regression tests; relevant
Ruff/bytecode gates passed. The administrator passed TypeScript, 81 test files / 501 tests and a
production build of 834 modules. These counts overlap. A disposable PostgreSQL 17 run passed 3/3
A2 gates covering fresh migration, no drift, bootstrap/runtime identity, forced RLS/exact grants,
positive activation commits, database-negative matrix and maker/checker behavior, and populated
downgrade refusal. Its cluster was removed and protected ports were not contacted. At that
historical checkpoint those source gates did not substitute for scanner or operator evidence. The
later hardened synthetic scanner receipt closes only the bounded adapter proof. The separate
signed-in synthetic-only operator receipt recorded below closes the bounded public-HTTP A/A1/A2
maker/checker and scanner/vault gate, not physical-device or retained operation.

B adds a strict, no-store, minimum-necessary release-context GET through a hardened narrow
database projection and deterministic fail-closed composer. It requires the exact permission,
open facility shift, active attendance interval and room/facility scope. Its generic realtime
event carries no child or authority-record ID, and the staff app keeps the canonical response only
in memory behind a monotonic expiry lease. The panel is read-only; it does not call attendance
checkout, persist a recipient decision or claim verified release.

The 2026-07-18 B closeout passed 84/84 portable API/composer/migration/detector tests. A real
disposable PostgreSQL run on an unprotected high port passed 7/7, covering the complete structural
detector, fail-closed rejection after a hardening revoke, restoration, the operational gate matrix,
the 400-transition common-snapshot race and exact projection/migration behavior. The administrator
remained green at 81 test files / 501 tests plus TypeScript/build;
the staff app passed 153/153 tests, TypeScript and an Android export transforming 744 modules.
The complete default backend regression passed 648 with 81 explicit opt-in skips and zero failures.
These counts overlap earlier regressions. The disposable cluster was removed and protected ports
5432, 5433 and 5434 were untouched. These are source/disposable proofs, not a local release.

`0029C_verified_release_checkout` contains strict Python and TypeScript contracts, canonical intent
hashing, a portable atomic command/exact-retry foundation, dormant facility activation and
activated-facility legacy checkout/correction closure. The additive
`0029D_release_checkout_writer` supplies the restricted PostgreSQL normal-release writer,
post-lock database time, same-transaction event/receipt/snapshot/interval bundle, exact replay,
runtime readiness detector and least-privilege bootstrap. The staff confirmation flow is wired
behind the authenticated per-facility capability; activated-but-ineligible or partially migrated
facilities never fall back to legacy checkout. No retained facility is activated, no retained
database migration or cutover has occurred, and software override remains deferred.

The latest source integration also adds the owner/admin child-profile authority summary and its
closed exact receipt focus. Its service rechecks current role under lock, is bounded and constant-
query, and omits confidential authority source detail. Generic identifier-free head events
invalidate family, admin-child and staff contexts. The mobile release flow guards replacement
sessions, stale responses, double submit and ambiguous retry while clearing authority state
immediately on realtime, identity, scope, token and lifecycle changes. These are not signed-in
operator or physical-device acceptance.

The real signed-in PostgreSQL run also closed three source defects without expanding privileges.
Immutable evidence/assessment and consent-policy reads use the already-held family/organization
aggregate lock instead of row locks that require `UPDATE`; A2 first commits explicitly flush
receipt, immutable authorization/rule/consent target and then authority head; and the first
post-commit response expires ORM state so trigger-authored receipt timestamps reload from the
database and match exact replay.

The final verification commands are reported independently; their counts are not additive. The
full default backend suite passed 798 tests, skipped 81 expected explicit opt-in PostgreSQL tests,
had zero failures and emitted 7 warnings. The focused integrated C/B/backend matrix passed 234
tests. The dormant ACL/bootstrap source received its final adjustment while the full suite was
running, so its final post-run targeted verification was also run and passed 17 tests. The
administrator passed TypeScript, 501/501 tests and the 834-module production build. The staff app
passed TypeScript and 181/181 tests. The 81 skips remain unexecuted opt-in PostgreSQL coverage, and
the warnings are not treated as release evidence. These results close the portable source gate
only.

The privileged-actor RLS helper fails closed when the API authors its
transaction-local user and organization context. That protects API-managed
queries; it does not protect against arbitrary SQL executed with the shared
runtime role because that role can set custom GUCs. A future commandized
membership/role boundary must close that limitation before production release.

The retained local database has been independently re-read in an explicitly
read-only transaction after the empty-schema incident and recovery: it is at
`0028_childcare_command_spine` with zero authority tables. The private
post-recovery backup and fresh-disposable exact restore are recorded above.
The development host now has `clamscan`, and the hardened 2026-07-22 synthetic-only adapter proof is
recorded in `FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`. It proves bounded local clean,
test-signature rejection, configured-unavailable and post-version scan-process-failure behavior;
it is not by itself a signed-in authority flow or retained 0029 cutover.

A separate actual CLI run passed all 16 signed-in public-HTTP operator cases on a fresh
caller-provisioned loopback PostgreSQL 17 database at exact
`0029D_release_checkout_writer`, using `caresync_basic_app` and ClamAV 1.5.3/28068. It proved real
multipart upload/scan/download, exact retries without duplicates, maker 409 with attested no-write,
independent checker review, authority activation, generic PII-free realtime ticket/WebSocket replay
and the admin summary. Preflight/postflight proved the same system and revision, expected synthetic
counts and zero unexpected sessions. The harness did not provision, migrate, drop or truncate its
target, contact protected ports or access retained data. The private uid-501, mode-`0600`, one-link,
2,261-byte redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
It contains no credential, email, UUID or local-path leakage and grants neither release nor cutover
authority. The staged C portable foundation, D restricted PostgreSQL writer and legacy closure do
not authorize retained-runtime use. B remains read-only and does not write a release snapshot.
No 0029 local or production release is claimed.

The separate 2026-07-22 synthetic exact-0029D joint recovery-consistency run restored the four
already-fixed database/vault artifacts into a caller-created scratch cluster and a new private
vault. It reproduced 90 tables / 61 rows and one evidence object and matched both the canonical
database digest and restored-vault reconciliation. Its private joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
The receipt records `artifactRecoveryConsistencyOnly=true` and
`recoveryConsistencyProven=true`. Source-writer quiescence, authoritative source completeness,
authoritative same-snapshot capture, unexpected source-vault exclusion, target-schema
authenticity, migration, cutover, release and purge authority are explicitly false. It used no
protected port and did not contact or modify retained 5434.

No current tool purges vault objects. Any future purge must require two verified snapshots with
authoritative `snapshotEstablishedAt`, at least 30 days unchanged absence, decisive quiescence,
exact purge-plan digest confirmation and durable per-object receipts.

### Verified-source 0032 transport-registry commands — outside the MVP release

The accepted `0032_transport_commands` architecture adds only a command/evidence/review layer to
the staged 0031 registry. It is **source-verified and unreleased**. It must not be counted as part
of the retained local functional MVP or as operational transport authority.

The intended boundary is deliberately narrow:

- exact actor/organization/operation binding, canonical request digests and atomic result/audit/
  receipt commits;
- one PostgreSQL `SECURITY DEFINER` repository owned by a dedicated `NOLOGIN`, `NOSUPERUSER`,
  `NOBYPASSRLS` command role;
- exact `EXECUTE`-only lanes for the normal restricted API and separate server-only evidence
  ingest identity, with no direct runtime table DML;
- encrypted qualification and vehicle evidence with server-measured object and clean scanner
  provenance that a client cannot assert;
- independent human review bound to immutable evidence versions, with the reviewer distinct from
  the subject/vehicle owner and source uploader;
- exact retry/change conflict handling and non-authorizing, latest-version/expiry-aware readiness
  records with generic attention notifications; and
- administrator/mobile surfaces hidden behind the exact full 0032 capability marker.

Every 0032 database fact, receipt, API and client must keep
`operational_driver_ready=false` and `dispatch_authorized=false`. 0032 contains no child or family
address, transport plan/consent, route, manifest, run, trip, handoff, dispatch, GPS/location or
offline trip pack. It therefore cannot authorize a staff member, vehicle or ride to transport a
child.

The source evidence is complete: 15 canonical function bodies and 23 protected triggers are pinned;
portable backend passed 123/123; fresh disposable PostgreSQL 17 behavior/tamper certification
passed 7/7; administrator TypeScript, 591/591 tests and production build passed; staff-app
TypeScript and 227/227 tests passed. The complete default backend regression passed 935 tests with
90 expected opt-in PostgreSQL skips and 7 deprecation warnings. The suites overlap and are not
summed, and skipped PostgreSQL tests are not certification. A private report-only vault preflight
now proves backup-derived inventory and ciphertext measurement without decryption, but deliberately
grants neither consistency nor purge authority because its snapshot boundary is unproven. Real
scanner/vault operation, historical key custody/rotation, ambiguous-object recovery, authoritative
same-snapshot backup/restore and retention/legal-hold/purge authorization,
operator and physical-device acceptance and accessibility/privacy/regulatory acceptance remain
production blockers. Protected ports 5432, 5433 and 5434 are not disposable
targets. Retained PostgreSQL is released at 0036.

For 0029 family authority, the bounded signed-in operator and fixed-artifact recovery-consistency
gates are now recorded separately. The next recovery boundary is writer-frozen authoritative-
source capture attestation. The operator receipt, either component restore receipt and the bounded
joint receipt do not prove that capture or authorize retained release/cutover.

### 0033/0036/0037 billing ledger — released local, activation pending

`0033_billing_ledger` provides the verified synthetic foundation and
`0036_billing_manual_mode` adds a separate private/local, owner-activated
boundary. Revision `0037_billing_agreement_scope` repairs immutable agreement
scope without changing that protocol. The retained database contains all three
revisions. The bounded source provides
versioned account/payer/rate/agreement facts, visibly watermarked synthetic
invoice/payment/allocation/credit facts, integer CAD amounts, balanced journals, exact
preparation/receipt/absence recovery and a capability-gated administrator workspace. Its eight
canonical collections include full historical `payer_versions`; every invoice pins its exact
payer-version and guardian provenance so later reassignment cannot rewrite or invalidate history.
Writes are
PostgreSQL-only and require test mode, sandbox mode, exact disposable-target attestation, an
allowlisted organization, synthetic-source attestations and a loopback high port outside
5432/5433/5434. SQLite never authorizes 0033 commands.

Enrollment-backed agreements are unique by organization, account and
enrollment. A partial organization/account/child uniqueness rule remains only
for historical null-enrollment agreements, and the old all-row account/child
constraint is absent. The live read-only readiness and family-summary
projections connect Admissions, Billing, Family and Child while keeping family
invoices as settlement authority. Child views attribute charges only. Live
acceptance reports 0 setup-ready of 197 active child records and keeps every
unresolved record actionable.

Manual mode is not a relaxed sandbox. It requires the exact local development
server attestation, a tenant allowlist and an immutable organization-owner
activation. It records only charges and payment facts completed outside
CareSync. It provides no processor, money movement, automatic issue, external
delivery, refund, tax advice, funding submission or settlement. The checked-in
launcher may derive only the sole active private organization for the server
allowlist; multiple active organizations require explicit UUID configuration.

Focused evidence is PostgreSQL 16 6/6; fresh disposable PostgreSQL 17 6/6 after the final
trigger/detector edits; portable SQLite 8/8 with command writes forbidden; administrator 110 test
files / 746 tests plus TypeScript and production build; and whole backend 1048 passed with 100
intentionally opt-in PostgreSQL tests skipped and 7 deprecation warnings recorded.

Signed-in synthetic browser acceptance passed: the sandbox boundary loaded; an account opened with
Priya as payer version 1; a rate and agreement were created; and a CAD 100.00 invoice was issued for
a fully covered August period. Payer reassignment to Samir version 2 preserved Priya/version 1 on
that invoice. A CAD 40.00 receipt, CAD 20.00 allocation and CAD 10.00 credit reconciled to CAD 70.00
outstanding and CAD 20.00 unapplied; reports/readiness reconciled and live snapshots advanced. The
walkthrough exposed a July effective-period gap. Full inclusive agreement and pinned-rate coverage
is now required, Review is disabled when coverage is incomplete, and the corrected state was
visually reverified. This remains synthetic sandbox evidence, not
owner-activated retained financial operation or production acceptance.

The administrator can render the canonical invoice record and use the browser's
print/save-PDF action. That local rendering is not external delivery, a tax
receipt or evidence of payment. The boundary still has no processor, money
movement or settlement, refund/chargeback, tax determination, funding rule pack
or claim, accountant-approved export, parent portal or production
authorization. Configured arithmetic is not
eligibility or accountant-approved treatment. Basic `/invoicing/*` remains
unavailable.

## Remaining hands-on MVP acceptance

The latest independent component-level runs are green. Full MVP/operator
acceptance still needs Amar's hands-on review:

- Run a physical Android flow: candidate registration, certificate capture,
  application, interview response, offer acceptance, provisioning, staff
  clock-in, roster, child attendance, care, medication and incident handoff.
- Run an operator smoke flow in the admin portal and confirm realtime updates
  across both clients.
- Run the 0041 room-presence flow: administrator room board and exception
  review, physical Android clock-in with ambiguous-room selection, room move,
  child-operation room gate, access loss and terminal clock-out recovery.
- Run the full daily-rota loop: create/edit a draft, publish, acknowledge,
  scheduled clock-in/out and verify planned-versus-actual reconciliation. Also
  exercise decline, alternate proposal/manager resolution, cancellation,
  explicit unscheduled clocking and an interrupted exact retry.
- Run the full workforce loop: save and reset availability, verify an explicit
  unavailable profile, submit/approve/decline/cancel time off, prove the hard
  leave/publication conflict, publish with an audited availability override,
  instantiate a template, and inspect assignment and confirmation gaps. Repeat
  an interrupted workforce mutation from both clients.
- Run the Staff Exchange loop: generate rotation drafts, post an open shift,
  express interest, send and accept an offer, opt into the substitute pool,
  complete peer consent and manager approval for a cover/trade, and exercise an
  interrupted exact retry without creating duplicate replacement work.
- Complete Android FCM credential provisioning for the now-linked Expo/EAS
  project and install the successfully completed signed development build,
  explicitly
  enable the Expo provider/worker, then exercise foreground, background,
  terminated-app and tap-through remote notification cases. The local provider
  is currently disabled because no Expo delivery credentials are configured.
- Record every defect discovered by the physical smoke; do not waive a safety
  defect merely to label the build an MVP.

The installed development client can exercise native modules, local
notifications, realtime sockets and the notification ledger. It does **not**
constitute end-to-end evidence for Expo -> FCM -> device delivery. Likewise,
the administrator portal supports in-app notifications and generic browser
notifications while open, but durable closed-browser Web Push has not been
implemented.

## `0039_admissions_decision_spine` released local checkpoint

Source, launcher and retained port 5434 agree on
`0039_admissions_decision_spine`. The guarded launcher quiesced writers,
captured the exact 16,445-row / 135-table 0038 source, restored it on fresh
PostgreSQL 17 port 56555 and verified canonical row digest
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both required evidence-vault restores contained zero objects and produced
private receipts.

The retained result has 141 public tables plus one view and exactly 16,445
rows, including 110 families, 203 children and 197 enrollments. All six
admission tables remain empty. The facility-release and manual-billing
activation tables also remain empty.

Revision 0039 releases a private administrator admissions decision spine:
versioned intake, deterministic waitlist lanes, program offers, material
correction, decline/withdrawal, exact retry, duplicate review and atomic
conversion to Family, Child and pending unassigned Enrollment. The existing
derived remediation queue remains separate. Admission tables are forced-RLS;
runtime updates are exact-column only; events/conversions are immutable; and
database provenance/bundle guards bind each command to its receipt, audit and
PII-free realtime effect.

Final acceptance passed 1,997 backend tests with 105 explicit opt-in skips and
seven warnings, a focused 22-test backend matrix, two independent PostgreSQL 17
admissions runs, administrator 125 files / 841 tests, staff app 272 tests and
extension 78 tests. TypeScript, production builds, 41 release-pin checks, Ruff
and bytecode compilation passed.

The signed-in retained workspace loaded and refreshed pipeline, deterministic
waitlist, protected draft, non-PII register, canonical remediation and billing
readiness without a visible error or write. Destructive lifecycle/conversion
proof remained disposable, and retained admission rows stayed at zero.
Complete artifacts and acceptance details are in
`docs/LOCAL_RELEASE_0039_CUTOVER.md`.

This remains a local technical release. It adds no parent/public admissions,
document signing/upload, outbound delivery, automatic placement,
billing/payment/funding behavior, transport authority or production
certification.

## Verified `0040_billing_readiness_batch_planner` source/product slice

Product slice `0040_billing_readiness_batch_planner` is verified in source and
through retained live read-only API acceptance. It introduces no schema
migration or release-pin change; the retained Alembic head remains exactly
`0039_admissions_decision_spine`.

The planner exposes deterministic, privacy-bounded account/payer, rate,
agreement, ready and manual-review waves at
`GET /api/v1/billing/readiness/batch-plan`, plus a no-write canonical intent
preview at
`POST /api/v1/billing/readiness/batch-plan/preview`. Apply remains separately
gated and reuses only the existing account, payer, rate and agreement command,
receipt and exact-recovery protocol. It cannot activate billing, issue an
invoice, record a payment, create a credit, contact a provider or create
funding behavior.

Retained acceptance returned schema v1 for organization-local 2026-07-23 with
111 groups: 102 account/payer and nine manual review. It truthfully reported
`apply_available=false` and `manual_activation_required=true`; a one-group
preview returned one `account_open` intent, zero blocks and preserved the
operation identifier. Every operational billing table and manual activation
remained at zero afterward, the role backup table remained at three rows, and
the retained head stayed 0039. API port 3002 and administrator port 5174 were
healthy and the setup route returned HTTP 200. This is live API/read-only
acceptance, not signed-in browser-click acceptance.

Final 0040 evidence is focused backend 9 passed, portable billing 34 passed /
1 skipped, fresh PostgreSQL 17 RLS/no-write 1 passed, administrator 128 files /
865 tests, and a green 881-module production build with only the existing
chunk-size advisory. The separate port-3302/5274 billing sandbox was backed up,
explicitly migrated from 0033 to 0039 and had restricted grants rebuilt; it is
disposable test preparation, not an 0040 migration or retained cutover.
Complete boundaries and evidence are in
`docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md` and
`docs/PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md`.
The signed-in administrator browser-click walkthrough remains pending.

## Verified `0041_live_room_presence` and `0042_billing_policy_recert` source

0041 and 0042 are complete, verified source slices. Checked-in source and the
launcher now target `0042_billing_policy_recert`; retained PostgreSQL 17 on port
5434 remains exactly at `0039_admissions_decision_spine`. No retained
migration, service restart through the new launcher or cutover occurred.

0041 provides server-confirmed staff room-presence sessions, exact-retry
start/move/end, child-operation room gating, factual operational
configured-target boards, append-only exception episodes and canonical
realtime/notification invalidation. Missing or incoherent source facts fail
visibly. This is not a regulatory ratio, qualification, capacity, supervision
or compliance certificate.

0042 is a narrow 0033 billing-policy integrity repair. It accepts only exact
whole-catalog profile A or the audited PostgreSQL dump/restore profile B,
rejects mixed/tampered/unknown catalogs, locks the protected relations and
recreates exactly 36 canonical policies. Downgrade preserves the secure policy
catalog. It activates no billing capability and adds no financial behavior.

The populated PostgreSQL 17 clone preserved 16,508 rows across all 140
pre-0041 business tables through both migration round trips. Exact identities
are:

- count digest
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`;
- row digest
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`;
- pre-0041 backup SHA-256
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`;
  and
- populated pre-0042 backup SHA-256
  `55be096d31c90b33cb7f19e625b472defbb60387d4dd56a7fb1fdec0f9a7490c`.

Automated evidence is all 135 backend files passed, focused backend 45 passed
and one opt-in skipped, one fresh PostgreSQL 17 proof for each of 0041 and
0042, source-head runtime-grant/backup 39 passed, billing-certificate eight
passed, administrator 22 files / 193 tests with TypeScript/build, and Staff app
297 tests with TypeScript, Expo Doctor 20/20 and a 782-module Android export.
The Android HBC SHA-256 is
`a3667d6da9e033c3a28fec98cf2e9edf4f5ffed51fbeefc0a2bb2c3769aec0fe`.

The retained release remains blocked on the signed-in administrator and
physical Android 0041 walkthroughs, permission-safe retained backup/evidence
restore, exact disposable replay, restricted-role certificate and explicit
cutover authorization. These open release gates do not invalidate the
completed source evidence.

## Historical `0038_public_job_catalog_outbox` released local checkpoint

At that checkpoint, source, launcher and retained port 5434 agreed on
`0038_public_job_catalog_outbox`. The guarded launcher quiesced writers,
captured the exact 16,335-row / 134-table 0037 source, restored it on fresh
PostgreSQL 17 port 56553 and verified the canonical row digest
`f0c93cd10395d24816292fc20b761ce262bb666ffeeab5776959c5bc817b5472`.
Both required vault restores contained zero objects and produced private
`0600` receipts.

The retained result at that checkpoint had 135 public tables plus one view,
16,339 total rows, 110
families and 203 children. The four post-backup rows are two catalog events and
one organization and one user realtime ticket created by the live signed-in
browser reconnect. The retained eligible-job, migration-backfill and current
public-projection counts are `1/1/1`, and every backfill identity agrees with
its canonical parent event.

The canonical source tables remain `FORCE RLS`. The catalog table has RLS
enabled without FORCE, the runtime role has `SELECT` only and `PUBLIC` has no
grant. Its enabled trigger calls a `SECURITY DEFINER` function with fixed
`pg_catalog` search path; the function and table share a non-runtime owner.
Public rows contain no organization identity, listing text, candidate-private
data, or tenant-private workflow data.

The canonical private artifacts are listed in
`docs/LOCAL_RELEASE_0038_CUTOVER.md`. Final integrated suites passed 1,979
backend tests with 104 explicit opt-in skips, a focused 915-pass/2-skip matrix,
3/3 isolated PostgreSQL gates, 808 administrator tests, 272 staff-app tests and
78 extension tests. API, administrator and billing sandbox health passed, and
signed-in Jobs reconnected to realtime.

The honest default state remained review-gated: no facility was
verified-release activated and no organization was manual-billing activated.
This was a local technical release, not physical-operator, accessibility,
privacy, regulatory, accountant, payment-provider or live third-party
acceptance. Revision `0039_admissions_decision_spine` subsequently completed
the guarded local release recorded above.

## Historical `0037_billing_agreement_scope` released local checkpoint

At that checkpoint, source, launcher and retained port 5434 agreed on
`0037_billing_agreement_scope`. The guarded launcher quiesced writers, captured
the exact 16,309-row / 134-table 0036 source, restored and digest-verified it on
a fresh PostgreSQL 17 target, restored both required evidence bundles, migrated
retained data exactly, rebuilt restricted grants and restarted services. The
retained result has 134 public tables plus one view and preserves all 110
families and 203 children.

The canonical private artifacts are listed in
`docs/LOCAL_RELEASE_0037_CUTOVER.md`. Final integrated suites passed 1,969
backend tests (102 explicit opt-in skips), 808 administrator tests plus
TypeScript/build, 260 staff-app tests plus TypeScript, and 78 extension tests
plus build. Required canonical ATS/marketplace routes are present; legacy
hiring prefixes and retired routes are absent. Signed-in Admissions, Billing,
Family, Child and Jobs checks passed.

The honest default state remains review-gated: no facility is verified-release
activated and no organization is manual-billing activated. Revision 0036
remains the manual protocol; 0037 only repairs agreement scope. Local release
does not replace physical-operator, accessibility, privacy, regulatory,
accountant, payment-provider or live third-party acceptance.

At that checkpoint, `0038_public_job_catalog_outbox` was the next bounded
slice. It has since completed the guarded local release recorded above.

## Historical `0036_billing_manual_mode` released local checkpoint

At that checkpoint, source, launcher and retained port 5434 agreed on
`0036_billing_manual_mode`. The guarded launcher quiesced writers, captured the
exact 16,260-row / 77-table 0028 source, restored and digest-verified it on a
fresh PostgreSQL 17 target, migrated retained data exactly, rebuilt restricted
grants, bound the restricted transport credential and restarted services. The
retained result has 134 public tables plus one view and preserves all 110
families and 203 children.

The canonical private backup, matching manifest and restore receipt are listed
in `docs/LOCAL_RELEASE_0036_CUTOVER.md`. The final integrated suites passed
1,094 backend tests (101 explicit opt-in skips), 790 administrator tests plus
build/audit, 265 staff-app tests plus TypeScript/Expo evidence, and 78 extension
tests plus TypeScript/build/audit.

The honest default state remains review-gated: no facility is verified-release
activated and no organization is manual-billing activated. Those rows can be
created only through their privileged in-product reviews. Local release does
not replace physical-operator, accessibility, privacy, regulatory, accountant,
payment-provider or live third-party acceptance.

## `0028_childcare_command_spine` local release checkpoint

At its recorded release checkpoint, source and live-local database shared
`0028_childcare_command_spine`. That is now a historical checkpoint; the
retained runtime subsequently completed the 0036 promotion described above.
It then completed the guarded 0037 and 0038 promotions recorded in the
historical and current checkpoints above.
The guarded 0028 cutover quiesced CareSync writers,
created a private same-snapshot v2 backup, restored and digest-verified all
1,830 pre-migration rows across 71 tables on a fresh disposable PostgreSQL 17
target, then added six empty RLS-forced command/reconciliation tables.

Recorded technical evidence is 387 passing default backend tests, 38/38
isolated PostgreSQL application/concurrency checks, 1/1 fresh-process migration
round trip, maintained-source lint/compilation green, 471 administrator tests
plus TypeScript/production build, and 138 staff-app tests plus TypeScript, Expo
Doctor and Android export. API health, administrator frontend and authenticated
realtime reconnection passed after cutover.

This is a local technical release, not production readiness. Physical-device
operator walkthrough, accessibility, privacy, Alberta regulatory validation,
production deployment and remote notification acceptance remain open.

## Production and commercial launch blockers

### Authentication and account security

- Real email verification and organization/license verification.
- Secure password reset, MFA/passkeys, session rotation/revocation, suspicious
  login detection and production rate limits.
- Recovery, ownership transfer, break-glass and privileged-action approval.
- Independent penetration testing and abuse testing.

### Privacy, tenancy and records governance

- Complete PIPA privacy program, consent/authority records, retention schedules,
  legal holds, correction/access/export workflows and defensible deletion.
- Canadian production hosting and vendor/subprocessor assessment.
- Object storage with tenant isolation, encryption, signed access, malware
  scanning and lifecycle policies for photos, credentials and documents.
- Recurring off-site/production restore drills, tenant export and tested
  disaster recovery. The exact local 0028 restore drill is complete.

### Reliability and delivery

- Production deployment topology, secrets manager, TLS, WAF/rate limiting,
  observability, alerting, runbooks, SLOs and on-call ownership.
- Durable background jobs for OCR, notifications and long-running work.
- Email/SMS/push delivery with preferences, retries, dead-letter handling and
  delivery evidence.
- Supported mobile release pipeline, signed builds, crash reporting, forced
  upgrade policy and offline-conflict testing.

### Realtime/push hardening backlog

The current pipeline is safe for the local MVP boundary, but these known P2
items remain before production scale:

- Replace the worker's scan across every active user with indexed/partitioned
  work discovery, per-user failure evidence and operational metrics.
- Batch Expo receipt lookups instead of issuing one receipt request per
  delivery, and add retention jobs for expired tickets, old realtime events and
  terminal delivery rows.
- Eagerly cancel `receipt_pending` work when a subscription is revoked. The
  current path remains safe but can perform stale receipt checks.
- Define and monitor the expected at-least-once edge around worker crashes and
  token transfer. Payloads remain generic and PII-free, which limits exposure,
  but duplicate wake-up attempts remain possible.
- Add bounded write/backpressure timeouts to the marketplace WebSocket path,
  matching the other realtime streams.
- Run the worker and API under a production supervisor with liveness/readiness
  and restart policy; the local startup check is not production supervision.
- Encrypt provider delivery addresses at the application layer or move them to
  a managed secrets/endpoint store. They are RLS-protected today, but not
  separately encrypted by the application.
- Production-scale the released `0038_public_job_catalog_outbox` with explicit
  event retention/partitioning policy, volume and reconnect soak tests, and
  operational lag/repair monitoring. Its local durable final-listing replay is
  released; these scale controls are not.

### Childcare and workforce completeness

- Operator/regulatory validation of Alberta licensing, ratios, supervision,
  records, medication, incident, illness and emergency workflows.
- Parent/guardian app and custody/pickup authority workflows.
- Workforce capabilities beyond the implemented daily rota, weekly planning and
  whole-shift exchange slices: bulk publication/automatic award, partial-shift
  trades, leave balances/accrual, breaks, qualifications, regulatory ratio
  certification, overtime rules, timesheet approval,
  payroll/time export, labor forecasting and complete HR records.
- Server-backed cross-device pending-care recovery cases and administrator
  resolution/lookup. The current device recovery center exposes the immutable
  reference but does not pretend a server support case exists.
- Production childcare finance remains blocked. The 0036 private/manual
  protocol and 0037 agreement-scope repair do not provide automatic invoice
  lifecycle/delivery, payment processing or settlement, refunds, funding
  claims, tax receipts, accountant-approved exports, parent self-service or
  production cutover.
- The bounded administrator `0039_admissions_decision_spine` is released
  locally with deterministic waitlist history, offers and duplicate-safe
  canonical conversion. Parent admissions, documents/signatures, outbound
  communications, nutrition, operational transportation, emergency drills and
  inspection-ready reporting remain later work.
- `0040_billing_readiness_batch_planner` is verified as a no-migration
  source/product slice with retained live read-only API acceptance. Its
  signed-in administrator browser-click walkthrough remains open; no billing
  activation, invoice, payment, provider or funding acceptance is implied.
- Accessibility conformance and usability testing with real administrators,
  educators and families.

The comprehensive capability destination and research record remains in
`docs/ULTIMATE_PRODUCT_CONSTITUTION.md`. Items in that registry are not implied
to be implemented unless they are explicitly listed as verified in this audit.

## Known dependency exception

The Expo SDK 57 development toolchain currently resolves a transitive
`uuid@7.0.3` advisory through Expo configuration tooling. It is not imported by
CareSync application code, and the available forced npm remediation would
downgrade Expo to an incompatible SDK. Do not force that downgrade. Track the
upstream Expo dependency and re-audit on every SDK update.

## MVP and production release rule

No feature is complete because its screen renders. MVP, production and
commercial release claims require:

1. an authoritative backend contract and tenant boundary;
2. validated input and output schemas;
3. safe retry/idempotency behavior for mutations;
4. fail-closed authorization loss;
5. canonical refresh/realtime behavior;
6. automated tests and production builds;
7. physical-device and operator acceptance evidence; and
8. documented recovery from interruption and partial failure.

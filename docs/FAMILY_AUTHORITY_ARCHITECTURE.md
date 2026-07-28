# CareSync Family Authority Architecture

Last updated: 2026-07-23

## Status

Architecture corrected after an independent ultra audit rejected the first, never-released 0029
schema draft. The active source sequence is implemented and verified through the C/D normal-
release boundary: the `0029A_family_authority_kernel`, additive
`0029A1_family_evidence_vault`, `0029A2_authority_activation` administrator commands and B's
minimum-necessary expiring educator read projection, C's portable atomic foundation and D's
restricted PostgreSQL normal-release writer. The sequence is built on released
`0028_childcare_command_spine`. It does not implement software override, legal interpretation, a
guardian portal or an emergency-reunification system. The original source
milestone itself authorized no live migration, facility activation or
production-readiness claim; later guarded cutovers installed it without
creating an activation.

The sequence is installed in the retained `0039_admissions_decision_spine`
schema. Revision 0035 supplies the explicit privileged facility activation,
but the completed guarded promotions through 0039 created no activation row; schema
availability is not operational authority. Revision 0038's public-job replay
and revision 0039's admissions boundary are unrelated to family-release
activation and inferred no authority fact.

The canonical A/A1/A2/B/C/D schemas and current admin/staff API/UI slices are verified in source and
disposable gates. A/A1 contain the no-write family workspace; exact-retry
authority-person create, full-facts replace and terminal retire commands; private document
upload/quarantine/scan/download; and the complete evidence record, review, reject, invalidate and
supersede lifecycle. A2 activates the reviewed evidence matrix and exact administrator
release-authorization, bounded rule and policy/consent commands. B adds one read-only, expiring,
minimum-necessary educator release-context GET plus generic realtime invalidation and a memory-only
staff review panel. C/D add the capability-gated normal verified-release flow, restricted atomic
writer, exact replay and legacy closure for activated facilities. The sequence proves immutable
historical receipts, current canonical replay, one audit/realtime invalidation per first commit,
stable child-head invalidation and missing-head rollback on disposable SQLite and restricted-role
PostgreSQL databases. The normal API has no general snapshot or attendance DML; D writes the
release bundle only through its exact restricted command boundary. A hardened synthetic scanner
adapter receipt, a bounded signed-in synthetic-only A/A1/A2 operator receipt and a separate
synthetic exact-0029D four-artifact recovery-consistency receipt exist. The latter proves only that
the fixed database/vault artifacts restore consistently; it did not itself
authorize migration or cutover. Later guarded 0036–0039 cutover evidence is
separate. Physical-device/checkout-operator acceptance and facility activation
remain open.

At the earlier 0028 checkpoint, an empty 0029A schema was briefly applied
during verification and then returned by the exact empty-only downgrade; the
recovery, row baseline and a full post-recovery backup/restore were verified.
That incident was not a release or cutover. A/A1/A2/B/C/D were later installed
through the recorded guarded 0036 promotion and remained installed through the
historical 0037/0038 checkpoints and current retained 0039 release. No facility
activation or authority fact was inferred by any promotion. All pre-release
PostgreSQL proof used disposable unprotected high ports; the later retained
cutovers followed the separate guarded process.

The exact persistence contract is recorded in `FAMILY_AUTHORITY_KERNEL_SCHEMA.md`. ORM and
migration definitions must match it exactly; implementation drift is not an alternate design.

Delivery is deliberately staged:

1. `0029A` — canonical persistence, exact-command provenance, admin-only commands and readiness;
2. `0029A1` — private server-measured evidence objects, quarantine, scanning and maker/checker;
3. `0029A2` — evidence-kind activation plus release authorization/rule and consent commands;
4. `0029B` — minimum-necessary, expiring read-only release context with realtime invalidation; and
5. `0029C` — portable atomic normal-release foundation plus reviewed facility activation and legacy
   attendance-only closure; and
6. `0029D` — restricted PostgreSQL normal-release writer, exact replay, runtime readiness and
   least-privilege bootstrap.

Software override is deferred beyond `0029C` until normal release is independently proven.

## Safety problem

The existing checkout records attendance time, child, facility and staff actor. It does not record
the recipient, identity check, release authority, restriction set or an immutable authority
snapshot. Existing `authorized_pickup` and family consent booleans are legacy profile markers.
They remain unchanged and never become grants, denials, signatures or verified evidence.

## Product truth

1. A contact is not automatically a stable person; a person is not automatically a guardian; a
   guardian is not automatically authorized to receive every child.
2. Release authority is child-specific, positive, evidence-backed, effective-dated and revocable.
3. A restriction is separate from a grant and takes precedence. Unknown or conflict means block
   and human escalation, never permission.
4. Consent is purpose-specific and never implied by pickup authority.
5. Server/database time and state decide authority; browser/device time is evidence only.
6. Realtime invalidates. Canonical REST state plus immutable command receipts decide truth.
7. Checkout and its recipient/decision snapshot commit atomically or not at all.
8. Later changes never rewrite a historical release snapshot.
9. Court-order contents and legal conflicts are not interpreted by CareSync.
10. Existing attendance checkout must not be marketed as verified release until 0029 enforcement,
    review and release gates pass.

## Bounded scope

### Included

- stable family authority people with immutable fact versions;
- one lockable, monotonically increasing authority revision per child;
- child-specific positive release authorizations;
- child-specific blocking/review release rules;
- purpose-specific, policy-versioned consent evidence and withdrawal;
- minimum-necessary release-context projections;
- exact-retry authority commands using the 0028 ledger;
- normal checkout with explicit recipient and immutable recipient/decision snapshot;
- an explicit future override evidence shape, without enabling an override command;
- forced tenant RLS, least grants, immutable evidence/history and concurrency tests;
- admin family/child authority workspaces and staff recipient-selection flow; and
- readiness items for unreviewed legacy markers and missing current authority.

### Deferred

- automated court-order interpretation or OCR-as-legal-verification;
- guardian accounts/self-service delegation and multi-household payer redesign;
- biometrics, face recognition, public kiosk QR/PIN and building credentials as release authority;
- generalized e-signature/document-vault platform;
- transport/school handoff, emergency reunification and a full offline continuity plane;
- custody-aware communication across every module; and
- the hidden V3 analyzer.

## Domain model

### Authority head

`child_authority_heads` contains at most one tenant-bound row per child and a positive `revision`.
Legacy children with no row are represented as unreviewed/revision zero by read projections; reads
never create data. The first reviewed child-specific authority command creates revision one. Every
later authority mutation locks the family, child and head and increments exactly once. A shared
person change locks and increments every affected child head in stable child-ID order. Release
checkout, when later introduced, must also lock and recompute the complete digest at server time;
the head alone is not treated as proof against expiry or passage of time.

### Stable people and facts

`family_authority_people` is the stable identity within a family. It contains status/version and
optional provenance links to an existing guardian or emergency-contact snapshot without rewriting
that 0028 history.

`family_authority_person_versions` contains immutable person facts plus a narrowly guarded one-way
closure transition. At most one version is current; every active authority person must have exactly
one current version after its creation transaction. Replacing facts closes the prior version with
server time and an operation receipt, inserts a new version and bumps all affected child heads in
one exact command.

Replacement and retirement use one transaction-stable dependency cutoff, lock affected child rows
and heads in stable child-ID order, and fail closed if any referenced child lacks its authority
head. Historical exact retry returns the immutable receipt committed by that command plus the
current person projection. Workspace and exact-retry projections hold a shared lock on the family
command row before their first mutable aggregate read; every implemented writer holds the same row
for update. A projection therefore cannot mix a pre-transition person/evidence row with
post-transition history under PostgreSQL `READ COMMITTED`.

The lock does not make a route-level role decision durable. Before any confidential workspace,
policy or exact-retry command projection, the service rechecks the actor's current active
owner/administrator membership after acquiring the family or organization aggregate lock. Role
loss returns `403 family_authority_access_revoked` before projection and never mutates the
historical receipt.

### Evidence assets and assessments

`family_authority_evidence_objects` records the immutable server-measured identity of one private
document version and permits only a guarded, one-way status transition from `quarantined` to
`clean` or `rejected`. `family_authority_evidence_object_assessments` is the append-only quarantine
and terminal scanner-decision stream. Rejected bytes remain canonical private custody records;
they are not downloadable or attachable and are not implicitly purged.

`family_authority_evidence` is an immutable intake asset: kind, source label, exact optional
object link and copied measured storage tuple, issue/capture/expiry times and operation provenance.
It stores the exact recorder as immutable domain provenance, so forced actor-private receipt RLS
does not erase maker identity for a later checker. It contains no mutable review state.
`family_authority_evidence_assessments` is an append-only assessment stream. The first
assessment is immutable version two and either reviews or rejects the asset; only reviewed version
two may receive terminal version-three invalidation or supersession. The current state is derived
from the highest assessment version, not a mutable pointer.

Downstream authority records must pin the exact reviewed assessment, not only the asset ID. The
assessment must still be the latest, the asset must be unexpired, and the dependent window may not
extend past evidence expiry. Invalidation or supersession makes dependent authority ineffective
without rewriting its historical rows and bumps each affected child head exactly once.

The current API accepts no client-supplied storage tuple, object key, scanner verdict or
issuer-verification claim. The A1 tenant/family-bound upload registry issues the opaque key and
proves exact object version, server-measured media/size/hash, quarantine and clean scan state before
stored bytes can be attached, reviewed or downloaded. A document reviewer must differ from both
its uploader and evidence recorder; a non-document reviewer must differ from its recorder. Until
the separate A2 evidence-kind/authority-basis gate closes, administrative review is not legal
interpretation and cannot activate release or consent.
Confidential evidence and assessment metadata is not exposed through the ordinary educator API.
The database policy proves that access through the API-managed transaction context carries a
matching tenant, authenticated actor and active owner/administrator membership. It is defense in
depth, not proof against arbitrary SQL issued through the shared runtime credential, because that
credential can set the same PostgreSQL context variables.

Immutable evidence assets, evidence assessments and consent policies deliberately retain no
runtime `UPDATE` grant. PostgreSQL row locks require that privilege, so activation reads those rows
without `FOR SHARE` while holding the canonical family or organization aggregate lock that every
corresponding writer takes for update. This preserves serialization without weakening the
least-grant ACL.

### Release authorization and rules

`child_release_authorizations` records a reviewed positive grant for one child/person over an exact
effective interval, with bounded identity-verification requirement, evidence, exact grantor person
version and documented grantor-authority basis. Revocation is a guarded one-way transition.
Overlapping active grants for the same child/person are rejected; replacement is explicit.

`child_release_rules` records deny, supervised-only, named-recipient-only or manager-review rules.
Rules have effective/expiry/revocation time, evidence and a confidential reason. Educator
projections expose only a decision, safe explanation code and escalation instruction.

### Consent

`consent_policy_versions` is immutable after publication and defines a bounded purpose, content
hash, effective interval and signer-authority requirement. Current policy windows for one purpose
cannot overlap.

`child_consent_decisions` binds one child and family, bounded purpose, exact same-purpose policy
version, signer person version, documented signer-authority basis, decision, scope,
effective/expiry time and evidence. Withdrawal is one-way and does not rewrite the original
decision. Pickup authority never implies consent authority. `0029A` stores immutable intake and
administrative assessment history but does not yet permit it to activate consent or unrelated care
workflow gates.

### Release snapshot

`attendance_release_snapshots` is append-only and one-to-one with a committed checkout event and
closed interval. It contains the exact child/family/facility/day/interval, recipient stable person
and person version, displayed name/relationship, authorization/version, authority revision and
restriction digest, identity-verification method/result, evidence fingerprints, decision policy,
staff actor, request/commit times, operation/request hash and override facts where applicable.

Attendance correction creates linked compensating evidence; it never mutates this snapshot.

## Authority decision

Normal release succeeds only when:

1. the child has an open interval at the facility and the actor has a confirmed open shift plus
   assigned-room or organization-wide release scope;
2. the recipient stable person and current person version belong to the child's family;
3. an effective, non-expired, non-revoked authorization exists for that exact child/person;
4. the submitted identity-verification method satisfies that authorization;
5. no active deny/review restriction blocks the release;
6. the client-provided authority revision/digest matches the locked canonical decision; and
7. the full request matches the 0028-style exact operation hash.

No software override command is enabled in `0029A`–`0029D`. A future proposal must use a bounded
reason code, written justification, exact actor membership/permission snapshot, recipient identity
facts, immediate audit/outbox signal, mandatory review queue and explicit do-not-release exclusions.
Until separately approved, exceptional cases follow the facility's restricted manual protocol and
the child remains on site in CareSync.

## Command and retry contract

New target types are `authority_person`, `authority_evidence_object`, `authority_evidence`, `release_authorization`,
`release_rule`, `consent` and `attendance_release`. Their receipt target ID is the exact stable
person, evidence object, evidence, authorization, rule, policy/decision or release record ID; child/family
coherence is independently proven by composite keys and command-context guards. The vocabulary
reserves all of those target and command lanes. A/A1 enable create/replace/retire person,
upload/scan evidence object and record/review/reject/invalidate/supersede evidence. A2 enables the
bounded authorization, rule, policy and consent commands. B adds only a read projection and no
command receipt or mutation. C/D add the exact `attendance_release` command and restricted
snapshot bundle; ordinary runtime table DML remains unavailable. Override remains deferred.

Every command carries `client_operation_id`; every mutation of a versioned aggregate carries
`expected_version` or `expected_authority_revision`. Same operation and canonical intent replays
one receipt. Changed recipient, time, evidence, verification, revision or purpose returns
`409 operation_reused`. An unresolved response freezes the exact intent until receipt
reconciliation proves committed or finalized absent.

`childcare_command_receipts.committed_version` is the exact committed target version: person
aggregate version for person commands; evidence object/scan-assessment version 1 or 2; evidence
asset/assessment version 1, 2 or 3; grant/rule/
decision version; policy version number; and immutable release-snapshot version 1. Child
authority-head revision is
a separately returned side effect and never substitutes for the receipt target version. Database
guards reject a mismatched receipt atomically.

For an A2 first commit the enforced database order is receipt, immutable authorization/rule/
consent target, then child authority head. Explicit flushes prevent ORM table ordering from placing
the guarded head before its target. After commit, response projection expires ORM state and reloads
database-trigger-authored receipt timestamps, so the first response and an exact replay expose the
same canonical receipt.

For every authority receipt, the request hash is exactly 64 lowercase hexadecimal characters and
the outcome is an exact one-key object containing only the canonical target-bound `action_route`.
Arbitrary routes, extra outcome metadata and PII-bearing receipt payloads are rejected atomically.

## API projections

Implemented in the current A/A1/A2/B/C/D source:

- `GET /families/{family_id}/authority`;
- authority-person create/version/retire commands;
- private evidence-object upload, scan and clean download;
- authority-evidence record/review/reject/invalidate/supersede commands;
- child release-authorization grant/revoke and bounded release-rule create/revoke commands;
- consent-policy list/publication and child-consent record/withdraw commands;
- read-only `GET /children/{child_id}/release-context?facility_id=...` in `0029B`;
- owner/admin-only `GET /children/{child_id}/authority-summary`; and
- capability-gated `POST /attendance/release-check-out` through the C/D normal-release boundary.

The authority summary accepts no query parameters, or exactly
`focus=release_authorization|release_rule|consent` with one UUID `record_id`. Partial, duplicate or
unknown query keys and malformed values return typed 422; a missing or wrong-child exact target
returns typed 404. It never substitutes a nearest record. The private no-store projection is
bounded to 200 rows per lane, performs a second current membership/owner-admin role check under
row locks, maintains constant query count, and omits contact data, evidence, grantor/signer
provenance, confidential reasons and policy body/hash.

There is no release mutation route in `0029A` or `0029B`; C/D provide the separately gated normal
release command.

The release context returns tenant/facility/room/child/attendance identifiers, generation time,
authority revision/digest, blockers and eligible opaque authority recipients. It is not a reusable
authorization token.

## Authorization and privacy

- Owners/administrators manage authority and consent.
- In source-verified `0029B`, clocked-in, assigned educators with `release:read` receive only the
  minimum-necessary expiring release context. The C/D client can submit a normal verified release
  only when the exact per-facility capability is active and every server gate is recomputed.
- Override is restricted to separately authorized owners/administrators.
- Ordinary educators never receive court-order text, confidential dispute reasons, unrelated
  contact data or consent history unrelated to release.
- Realtime carries identifiers/invalidation hints only. Push/OS notifications remain generic.
- No new authority table permits runtime `DELETE`.

## Database and concurrency contract

All twelve A/A1 tables use composite organization foreign keys and `ENABLE/FORCE ROW LEVEL SECURITY`.
Every policy calls a fixed-search-path, `SECURITY DEFINER` privileged-actor predicate that fails
closed for a missing or malformed API context, requires organization equality, and requires an
active owner/administrator membership outside its narrow schema-owner maintenance bypass. The
helper is revoked from `PUBLIC`; only the runtime role receives `EXECUTE`. These checks harden
API-managed transactions, but they are not a per-user database identity boundary: arbitrary SQL
running as the shared runtime role can set the same GUCs and must not be treated as proven
unprivileged isolation.

The A/A1 role boundary starts with `SELECT` on the authority tables and bounded writes to people,
person versions, evidence objects/assessments/assets and child heads. A2 adds `INSERT` on
authorizations, rules, policy versions and consent decisions plus only their explicit
revoke/withdraw transition columns. B does not grant educators direct table access: it grants the
shared runtime only the exact fixed-search-path definer projection and guards application access
with `release:read`, open-shift and scope checks. D grants only exact restricted writer callables,
not general snapshot/attendance DML. No authority table grants runtime `DELETE`. Command-context triggers bind organization, actor,
operation, command type and target.

Lock order begins with the exact operation slot, then family, child IDs in sorted order, authority
heads, facility, attendance day/interval, person/version and authority records. C/D checkout
versus revocation, new restriction, person replacement and second checkout must have exactly one
serial winner and no partial state.

## Migration contract

- Add structures, checks, indexes, triggers, RLS and grants only.
- Start all 0029 authority/evidence/snapshot tables empty; do not synthesize child heads.
- Preserve every legacy boolean and imported row byte-for-byte.
- Generate review/readiness signals; never synthesize authority or consent.
- Refuse downgrade after 0029 evidence or release history exists.
- Prove fresh `0028 -> 0029 -> 0028 -> 0029`, restricted-role startup and populated-history
  downgrade refusal.
- Keep retained/local protected database ports fail closed for Alembic by default and never target
  unreleased `head` from normal startup.

The empty-only downgrade path was exercised during the retained-database incident described in
the status section, followed by independent revision/table/row verification and a full backup
restore. That recovery proves the empty downgrade path; it does not authorize a retained cutover.

## Client contract

The family profile gets an in-page Authority & consent workspace; the child profile gets a
minimum-necessary effective summary. History remains on full routes or accessible dialogs, never
a side drawer. The source implementation keeps that child projection owner/administrator-only,
omits contact, evidence, provenance, confidential-reason and policy-content fields, and resolves
release/consent receipt routes to one exact focused record. A stale, malformed or cross-child
target fails visibly without selecting a different record. This remains staged source until the
documented deployment gates close.

The authority workspace also exposes the maker/checker boundary directly. Evidence recorded by
the signed-in maker is labeled separately and has no Review action; that maker may reject an
incorrect submission, while a distinct active owner/administrator may review or reject it. Person,
object, evidence, authorization, rule and consent links scroll, focus and highlight only the exact
typed row. Missing records and malformed or prototype-like query keys never select a nearby
record, and workspace/policy refreshes are latest-request-wins and unmount-safe.

In `0029C`, checkout becomes explicit recipient selection and final confirmation. Staff must be
online with a fresh, explicitly expiring canonical context, active shift and no unresolved command.
The browser/device journal persists only non-PII operation metadata and the exact request hash; the
sensitive frozen intent remains encrypted in the purpose-built pending-operation store. A
stale/revoked/expired context forces refetch and reselection. Success is accepted only when the full
immutable recipient, authorization, verification, interval, event, operation and tenant receipt
echoes match.

The C/D restricted writer proves the closed attendance interval and exact checkout
event/actor/operation/timestamps; validates authorization at authoritative server commit time;
locks and recomputes active restrictions and their digest; enforces the authorization verification-
policy matrix; binds evidence and decision-policy hashes to canonical inputs; and serializes
checkout against revoke, rule, head and person changes. The ordinary runtime role retains no
general snapshot/attendance mutation lane; only the exact D command callable can commit the bundle.

## Release gates

The server-controlled upload/object registry, clean-state binding and maker/checker boundary are
implemented in A1 source. The development host now has a real ClamAV installation and an opt-in,
synthetic-only certification harness documented in `FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`.
That scanner-only proof does not make A1 live-operational.

A separate 2026-07-22 actual CLI certification passed all 16 signed-in public-HTTP A/A1/A2 cases
on a fresh caller-provisioned loopback PostgreSQL 17 database at exact
`0029D_release_checkout_writer`, under `caresync_basic_app`, using ClamAV 1.5.3/28068. It included
multipart upload/scan/download and exact retries, maker 409 with attested no-write, independent
checker review, reviewed activation and exact replay, PII-free realtime ticket/WebSocket replay and
the admin summary. Preflight/postflight proved the same system and revision, expected synthetic
counts and zero unexpected sessions. The private uid-501, mode-`0600`, one-link, 2,261-byte,
no-clobber redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
It contains no credential, email, UUID or local-path leakage. The harness did not provision,
migrate, drop or truncate its target, contact a protected port or access retained data. The receipt
granted neither release nor cutover authority; retained PostgreSQL was still
at 0028 at that certification checkpoint. The later guarded 0036 through 0039
release evidence, not this synthetic receipt, establishes the current retained
schema.

The separate synthetic exact-0029D joint recovery run restored the four fixed artifacts into a
caller-created scratch cluster and new vault, matching 90 tables / 61 rows, one evidence object,
the canonical database digest and restored-vault inventory. Its private no-clobber receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
It proves `recoveryConsistencyProven=true` only. Source-writer quiescence, authoritative source
completeness/same-snapshot capture, source-vault unexpected-entry exclusion, target-schema
authenticity, migration, cutover, release and purge authority remain false. The next recovery gate
is writer-frozen authoritative-source capture attestation; neither the operator receipt nor either
component restore receipt substitutes for that boundary.

The A2 activation matrix and B minimum-necessary expiring educator context are implemented and
verified in source/disposable gates. The 2026-07-18 B closeout passed 84/84 portable
API/composer/migration/detector tests and 7/7 real disposable PostgreSQL tests at an unprotected
high port, including complete detector, revoke rejection/restoration, the operational gate matrix
and the 400-transition common-snapshot race. The administrator remained green
at 81 test files / 501 tests plus TypeScript/build; the staff app passed 153/153 plus TypeScript and
an Android export of 744 modules. These are overlapping source gates, not operator or release
evidence. The complete default backend regression passed 648 with 81 explicit opt-in skips and
zero failures. Those are historical B counts. C/D later added the normal-release boundary and a
fresh disposable PostgreSQL 17 gate passed 2/2 destructive proof cases. The latest authority/
realtime focused backend matrix passes 47 tests and Ruff; frontend focus passes 18 tests and
TypeScript; the broader administrator passes 691 tests and build; and mobile passes 263 tests and
TypeScript. Mobile 401/403 handling revokes only the still-current identity/token boundary, stale
responses cannot revoke a replacement session, exact pending operations remain protected, and
submit/reconcile locks prevent dismissal or double execution.

- migration/round-trip/downgrade-refusal and RLS/least-grant gates;
- writer-frozen authoritative database/private-byte capture attestation; the bounded recovery-
  consistency and report-only reconciliation integrity gates are already recorded separately;
- installed ClamAV with fresh definitions plus a retained private receipt from the synthetic
  clean/test-signature/failed-scan proof before any A1 cutover;
- exact-retry, stale-version and immutable-history API tests;
- PostgreSQL races for authority creation/revocation/person-version changes in `0029A`, then
  checkout/revoke, checkout/rule, checkout/person-version and double checkout before `0029C`;
- cross-tenant and direct-SQL forgery/immutability tests;
- admin/staff strict parsing, ambiguity lock, realtime refresh and generic-notification tests;
- full backend/admin/staff regression, lint, typecheck and builds;
- signed-in desktop/390px UI and physical Android checkout/operator walkthrough; and
- separate accessibility, privacy and Alberta operator/regulatory acceptance.

Green automated gates permit a local technical release only. They do not establish legal validity
of custody evidence or production readiness.

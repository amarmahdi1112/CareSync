# CareSync 0029A/A1/A2 Family Authority Schema Contract

Last updated: 2026-07-18

## Status and boundary

This is the canonical persistence contract for `0029A_family_authority_kernel`, the additive
`0029A1_family_evidence_vault`, and source-only revision
`0029A2_authority_activation`. It is subordinate to `FAMILY_AUTHORITY_ARCHITECTURE.md` and
`FAMILY_AUTHORITY_EVIDENCE_VAULT_ARCHITECTURE.md`, and intentionally excludes release-context APIs, checkout
enforcement, software override, guardian self-service and activation of consent as a gate for
unrelated care workflows. A migration or ORM mapping that differs from this contract is drift, not
an alternate design.

All 0029A tables start empty. Reads project a missing child authority head as unreviewed revision
zero; reads never create or promote authority. Existing contact pickup flags and consent booleans
remain unchanged legacy facts.

The A/A1/A2 migrations, ORM mappings, family workspace, person commands, private object upload/scan
boundary, complete evidence lifecycle and administrator activation commands are verified in source
and disposable gates. Runtime commands currently insert into `family_authority_people`,
`family_authority_person_versions`,
`family_authority_evidence`, `family_authority_evidence_assessments`, `child_authority_heads`,
`family_authority_evidence_objects`, `family_authority_evidence_object_assessments`,
`child_release_authorizations`, `child_release_rules`, `consent_policy_versions` and
`child_consent_decisions`; object and revocation/withdrawal rows permit only their guarded one-way
transitions. `attendance_release_snapshots` remains SELECT-only scaffolding for 0029C.

There has been no 0029 release or retained cutover. The retained database is back at 0028 with no
authority rows or tables after an empty 0029A schema was briefly applied and then removed through
the exact empty-only downgrade. Its revision, table absence and row baseline were independently
verified, followed by a complete post-recovery backup/restore verification.

## Exact command receipt expansion

`childcare_command_receipts.target_type` permits exactly:

- `family`
- `child`
- `enrollment`
- `authority_person`
- `authority_evidence`
- `authority_evidence_object`
- `release_authorization`
- `release_rule`
- `consent`
- `attendance_release`

For every new type, `target_id` is the exact stable person, evidence object, evidence, authorization, rule,
policy/decision or future release record UUID. It is not a family or child shortcut. Every
operation column below has a composite foreign key from `(organization_id, operation_id)` to
`childcare_command_receipts(organization_id, client_operation_id)` with `ON DELETE RESTRICT`.
PostgreSQL command guards additionally bind organization, actor, operation, command type, target
type and target record, and require the receipt to have been inserted in the same transaction by
the 0028 `xmin = pg_current_xact_id()` proof.

The receipt `committed_version` is also exact: person aggregate/version number for person commands;
object version 1 for upload and assessment version 2 for scan; version 1 for evidence record;
version 2 for evidence review or rejection; version 3 for evidence
invalidation or supersession; the resulting grant/rule/decision version; the published policy
version number; and version 1 for a future immutable release snapshot. Head revision is a separate
child side effect. A receipt with an arbitrary positive but incorrect version must roll back with
every domain/head write.

Authority receipts accept only a 64-character lowercase hexadecimal request hash and an outcome
JSON object with exactly one string key, `action_route`. The route must be the exact canonical
target-bound route: `/families/{family_id}?authority_person_id={person_id}` for a person,
`/families/{family_id}?authority_evidence_object_id={object_id}` for an evidence object,
`/families/{family_id}?authority_evidence_id={evidence_id}` for evidence,
`/children/{child_id}?release_authorization_id={authorization_id}` for an authorization,
`/children/{child_id}?release_rule_id={rule_id}` for a rule,
`/consent-policies/{policy_id}` for a policy, `/children/{child_id}?consent_id={decision_id}` for a
child consent decision, or `/attendance/releases/{release_id}` for a future release snapshot.
Additional outcome keys, malformed hashes and target-mismatched routes fail atomically.

## Additive legacy identities

The migration adds these unique identities without changing row values:

- `children(organization_id, family_id, id)`
- `guardians(organization_id, family_id, id)`
- `emergency_contacts(organization_id, family_id, id)`
- `attendance_days(organization_id, facility_id, child_id, id)`
- `attendance_intervals(organization_id, attendance_day_id, id)`
- `attendance_events(organization_id, attendance_day_id, id)`

They are required for same-family and exact-attendance snapshot foreign keys.

## Canonical tables

### `family_authority_people`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id` UUID, required
- `version` positive integer, initially 1
- `status` one of `active`, `retired`
- `current_person_version_id` UUID, nullable only when retired
- `source_guardian_id`, `source_emergency_contact_id` UUID, nullable and mutually exclusive
- `created_operation_id`, `last_operation_id` UUID, required
- `retired_at`, `retired_operation_id`, nullable one-way retirement pair
- `created_at`, `updated_at`, server timestamps

Required identities and links:

- unique `(organization_id, id)` and `(organization_id, family_id, id)`
- same-family links to `families`, `guardians` and `emergency_contacts`
- deferred `(organization_id, family_id, id, current_person_version_id)` link to the exact person
  version
- partial unique legacy-source links when non-null

An active person has one exact current version and no retirement fields. A retired person has no
current version and has both retirement fields. Runtime updates may only replace the current
version while incrementing `version` by one, or retire once; facts and provenance are immutable.

### `family_authority_person_versions`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `person_id` UUID, required
- `version_number` positive integer
- `first_name`, `last_name` non-blank strings
- `middle_name`, `preferred_name` nullable or nonblank strings
- `relationship_kind` one of `parent`, `legal_guardian`, `foster_parent`, `grandparent`,
  `adult_sibling`, `aunt_uncle`, `family_friend`, `caseworker`, `transport_provider`, `other`
- `relationship_detail`, required only for `other`
- `email`, `primary_phone`, nullable or nonblank
- `created_operation_id` UUID, required
- `closed_at`, `closed_operation_id`, nullable one-way closure pair
- `created_at` server timestamp

Required identities include `(organization_id, id)`,
`(organization_id, family_id, person_id, id)` and a unique version number per person. A partial
unique index allows at most one unclosed version. A deferred PostgreSQL constraint trigger proves
that every active person has exactly one open version matching `current_person_version_id`, while
a retired person has none. `(organization_id, created_operation_id)` is also unique so one exact
person command cannot manufacture more than one fact version. `relationship_detail` is nonblank
exactly when `relationship_kind=other` and null otherwise.

### `family_authority_evidence_objects`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id` UUID, required
- `evidence_kind`, one of the six document evidence kinds, including
  `signed_release_delegation`
- `object_version`, exactly 1
- `storage_reference`, opaque relative key, required and tenant-unique
- `media_type`, exactly `application/pdf`, `image/jpeg` or `image/png`
- `byte_size`, between 1 and 52,428,800
- `content_sha256`, exactly 64 lowercase hexadecimal characters
- `original_filename`, optional bounded display-only metadata
- `status`, one of `quarantined`, `clean`, `rejected`
- `uploaded_by_user_id`, `uploaded_operation_id`, required
- `created_at`, finite server timestamp

The object ID, tenant/family/kind, storage reference, object version, measured media/size/hash,
display filename, uploader, operation and creation time are immutable. Only `status` may change,
once, from `quarantined` to `clean` or `rejected`. The opaque key is server-authored and the exact
stored inode is kept outside web/static roots at private modes; database rows contain metadata,
not bytes. Composite foreign keys bind family, active organization membership and exact upload
receipt provenance. One upload operation creates at most one object.

### `family_authority_evidence_object_assessments`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `evidence_object_id` UUID, required
- `version_number`, exactly 1 or 2
- `decision`, one of `quarantined`, `clean`, `rejected`
- `scanner_engine`, `scanner_version`, `scanner_signature`, nullable under the exact transition
  shape
- `reason_code`, null or one of `malware_detected`, `invalid_document`
- `actor_user_id`, `operation_id`, required
- `created_at`, finite server timestamp

Version one is exactly `quarantined` with no scanner metadata and shares the upload operation.
Version two is terminal: `clean` requires scanner engine/version and no signature/reason;
`rejected` requires scanner engine/version and a bounded reason, with an optional malware
signature. The stream is append-only and unique per object/version and per operation. Database
invariants require the object status and assessment stream to agree and require exact current
command-receipt provenance.

### `family_authority_evidence`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id` UUID, required
- `evidence_kind` one of `identity_document`, `custody_document`, `court_order`,
  `guardian_attestation`, `signed_consent`, `signed_release_delegation`, `staff_witness`,
  `other_document`
- `source_label` non-blank string
- `evidence_object_id`, nullable same-family/same-tenant object link, unique when present
- `recorded_by_user_id`, exact recorder and active organization-membership identity, required
- `storage_reference`, `media_type`, `byte_size`, `content_sha256`, all null or all present
- `issued_at`, `captured_at`, `expires_at`, nullable timestamps
- `created_operation_id` UUID, required
- `created_at` server timestamp

`storage_reference` is 1–500 characters, begins with an ASCII alphanumeric character, contains
only `[A-Za-z0-9._/-]`, and contains no empty, `.` or `..` path segment. It is not an absolute
path, URI, query, fragment or public URL. `media_type` is a lowercase `type/subtype` value whose
components begin alphanumerically and otherwise contain only `[a-z0-9!#$&^_.+-]`. `byte_size` is
between 1 and 52,428,800 inclusive. SHA-256 is exactly 64 lowercase hexadecimal characters. Every
timestamp is finite on PostgreSQL. The asset is immutable and unique by
`(organization_id, created_operation_id)`. It stores no public URL or document bytes and carries no
review or issuer-verification claim. PostgreSQL binds `recorded_by_user_id` to the current command
actor and immutable receipt actor in the insert transaction; review never needs visibility into a
different actor's private receipt to recover the maker identity.

The current API requires one clean, current, same-kind, same-family object for every document kind
and forbids an object for `guardian_attestation` and `staff_witness`. When the object link is
present, database guards copy and require exact equality with the server-measured object tuple;
clients never author those facts. One object may bind at most one evidence asset. A document asset
cannot be inserted without a clean object link, while non-document assets retain a null object link
and null storage tuple.

### `family_authority_evidence_assessments`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `evidence_id` UUID, required
- `version_number`, exactly 2 for the first assessment and 3 for a terminal transition
- `decision` one of `reviewed`, `rejected`, `invalidated`, `superseded`
- `assessed_epistemic_status`, `reported` or `document_observed` exactly for `reviewed`, null
  otherwise
- `reason_code`, null exactly for `reviewed`; rejected values are `insufficient_evidence`,
  `information_mismatch`, `unreadable`, `unsupported`, `entered_in_error`, `other`; invalidation
  values are `authority_changed`, `document_revoked`, `information_corrected`,
  `entered_in_error`, `other`; supersession uses exactly `superseded`
- `confidential_note`, null unless `reason_code=other`, then required nonblank with at most 1,000
  characters
- `superseded_by_evidence_id`, present exactly for `superseded`
- `actor_user_id`, `created_operation_id`, required
- `created_at`, finite server timestamp

Assessments are append-only and unique by `(organization_id, evidence_id, version_number)` and
`(organization_id, created_operation_id)`. Composite links bind the target and any replacement to
the same family. The state machine is exact: an unreviewed version-one asset may receive one
version-two `reviewed` or `rejected` assessment; only a reviewed version two may receive a terminal
version-three `invalidated` or `superseded` assessment. Rejection, invalidation and supersession are
terminal. Supersession names a distinct same-family asset whose latest assessment is reviewed and
whose evidence is unexpired. The current state is derived from the highest assessment version;
there is no mutable current pointer.

A direct PostgreSQL review guard enforces the epistemic and maker/checker boundary: document
review requires `document_observed` and a reviewer distinct from the uploader and recorder;
non-document review requires `reported` and a reviewer distinct from the recorder. Rejection is
non-activating and does not require a distinct actor. All actors remain subject to the current
owner/administrator policy at commit.

### `child_authority_heads`

Columns:

- `organization_id`, `family_id`, `child_id` UUID, with `child_id` the primary key
- `revision` positive integer
- `created_operation_id`, `last_operation_id` UUID, required
- `created_at`, `updated_at`, server timestamps

It has unique `(organization_id, child_id)` and `(organization_id, family_id, child_id)` identities
and an exact same-family child link. The first reviewed child-specific command creates revision 1.
Every later authority mutation changes only `revision = old + 1`, `last_operation_id` and the
server timestamp. Shared-person mutations lock and bump affected children in stable child-ID order.

### `child_release_authorizations`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `child_id`, `recipient_person_id` UUID, required
- `verification_policy_code` one of `government_photo_id`, `documented_familiarity`,
  `government_photo_id_or_documented_familiarity`,
  `government_photo_id_and_secondary_check`
- `grantor_person_id`, `grantor_person_version_id` UUID, required
- `grantor_authority_basis` one of `guardian_record`, `reviewed_custody_evidence`,
  `reviewed_delegation_evidence`
- `basis_evidence_id`, `basis_evidence_assessment_id` UUID, required and linked to the exact latest
  reviewed assessment
- `effective_from`, `effective_until` required finite half-open interval
- `version` positive integer, initially 1
- `created_operation_id` UUID, required
- `revoked_at`, `revoked_operation_id`, `revocation_reason_code`, nullable one-way triplet
- `revocation_reason_code` one of `authority_withdrawn`, `safety_change`, `superseded`,
  `entered_in_error`
- `created_at`, `updated_at`, server timestamps

All child, recipient, grantor-version, evidence and assessment links include organization and
family. A dependent effective window may not extend past a finite evidence expiry. Active
intervals for the same child/recipient may not overlap. Revocation increments the record version
and child revision and cannot be undone.

The activation trigger admits only `guardian_record` + current reviewed `guardian_attestation`,
`reviewed_custody_evidence` + current reviewed `custody_document`, or
`reviewed_delegation_evidence` + current reviewed `signed_release_delegation`. Guardian and
delegation grantors must retain original live-guardian provenance, preventing re-delegation. The
command actor must differ from the reviewer.

### `child_release_rules`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `child_id` UUID, required
- `rule_kind` one of `deny`, `manager_review`
- `scope_kind` one of `all_recipients`, `specific_person`
- `scope_person_id` UUID, present exactly for specific-person scope
- `directing_person_id`, `directing_person_version_id`, nullable together
- `authority_basis_code` one of `guardian_record`, `reviewed_custody_evidence`
- `basis_evidence_id`, `basis_evidence_assessment_id` UUID, required and linked to the exact latest
  reviewed assessment
- `safe_explanation_code` one of `release_restricted`, `manager_review_required`, consistent with
  rule kind
- `confidential_reason` non-blank text
- `effective_from`, `effective_until` required finite half-open interval
- `version` positive integer, initially 1
- `created_operation_id` UUID, required
- `revoked_at`, `revoked_operation_id`, `revocation_reason_code`, nullable one-way triplet
- `created_at`, `updated_at`, server timestamps

Same-family links apply to every person. Identical non-revoked rule/scope lanes may not overlap.
The guardian basis requires one explicit current directing person with live-guardian provenance
and current reviewed `guardian_attestation`; the custody basis may omit a directing person and
requires current reviewed `custody_document`. `supervised_only` and `named_recipient_only` are not
representable in A2 because their complete enforcement semantics remain deferred.

### `consent_policy_versions`

Columns:

- `id` UUID primary key
- `organization_id` UUID, required
- `purpose_code` one of `off_site_activity`, `emergency_health_care`,
  `medication_administration`, `internal_media`, `external_media`, `marketing`, `research`,
  `optional_service`, `information_sharing`
- `version_number` integer between 1 and 2,147,483,647 inclusive
- `title`, `content_reference` non-blank strings
- `content_text` immutable nonblank text, 1 through 20,000 characters
- `content_sha256` exactly 64 lowercase hexadecimal characters
- `signer_authority_requirement` one of `guardian_record`, `legal_decision_maker`
- `effective_from`, `effective_until` required finite half-open interval
- `created_operation_id` UUID, required
- `published_at` server timestamp

It is immutable, unique by organization/purpose/version and has no overlapping policy window for
one purpose. The service derives `content_sha256` from exact UTF-8 `content_text` and derives
`content_reference` as `/consent-policies/{id}`; callers author neither field.

### `child_consent_decisions`

Columns:

- `id` UUID primary key
- `organization_id`, `family_id`, `child_id` UUID, required
- `purpose_code`, `policy_version_id` required and linked to the exact same-purpose policy
- `signer_person_id`, `signer_person_version_id`, `signer_authority_basis` required
- `signer_authority_evidence_id`, `signer_authority_evidence_assessment_id` UUID, required and
  linked to the exact latest reviewed signer-authority assessment
- `evidence_id`, `evidence_assessment_id` UUID, required and linked to the exact latest reviewed
  signed-consent decision assessment
- `decision` one of `granted`, `declined`
- `scope_kind` one of `policy`, `facility`, `named_activity`
- `scope_facility_id`, present only for facility scope
- `scope_reference`, non-blank only for named-activity scope
- `effective_from`, `effective_until` required finite half-open interval
- `version` positive integer, initially 1
- `created_operation_id` UUID, required
- `withdrawn_at`, `withdrawn_operation_id`, `withdrawal_reason_code`, nullable one-way triplet
- `withdrawal_reason_code` one of `signer_withdrew`, `authority_changed`, `superseded`,
  `entered_in_error`
- `created_at`, `updated_at`, server timestamps

The signer version and both evidence/assessment tuples are same-family. Decision evidence and
signer-authority evidence IDs must differ. Decision evidence is exactly current reviewed
`signed_consent`. A `guardian_record` policy requires signer basis `guardian_record`, live-guardian
provenance and current reviewed `guardian_attestation`; a `legal_decision_maker` policy requires
signer basis `reviewed_custody_evidence` and current reviewed `custody_document`. The command actor
must differ from both reviewers. The dependent effective window may not extend past either evidence expiry.
Non-withdrawn decisions for the same child/purpose may not overlap. Withdrawal increments the
record version and child revision and cannot be undone.

### `attendance_release_snapshots`

This table is created empty for the future `0029C` atomic checkout and still receives no runtime
INSERT grant after A2.

Columns:

- identity: `id`, `organization_id`, `family_id`, `facility_id`, `child_id`,
  `attendance_day_id`, `attendance_interval_id`, `checkout_event_id`
- recipient: `recipient_person_id`, `recipient_person_version_id`, `recipient_display_name`,
  `recipient_relationship`
- decision: `authorization_id`, `authorization_version`, `authority_revision`,
  `restriction_digest_sha256`, `verification_method`, `verification_result`, `evidence_id`,
  `evidence_assessment_id`, `evidence_assessment_version`, `evidence_digest_sha256`,
  `decision_policy_version`
- actor/time: `actor_user_id`, `requested_at`, `committed_at`
- command: `client_operation_id`, `request_hash`
- reserved mode: `release_mode`, `override_reason_code`, `override_justification`

It has exact composite same-family child/person/version/authorization links and exact composite
day/interval/event links. Interval, checkout event and client operation are each one-to-one within
the organization. Versions are positive; hashes are lowercase hexadecimal; commit time is not
before request time. Through A2 `release_mode` is `normal`, both override fields are null, and no
runtime insertion is permitted. A future override proposal requires a separate migration.

## PostgreSQL enforcement and grants

Every table has `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY` and one policy using
`caresync_family_authority_actor_is_privileged(organization_id)`. That fixed-search-path,
`SECURITY DEFINER` helper fails closed when either API-set GUC is missing or malformed, requires
`app.current_organization_id` to match the row organization, and requires the
`app.current_user_id` actor to hold an active owner/administrator membership in that organization.
A narrow schema-owner session-user bypass exists only for owner restore/repair while forced RLS is
active. The helper and trigger functions are revoked from `PUBLIC`; the runtime role receives only
the helper `EXECUTE` needed for policy evaluation.

This is defense in depth for authenticated API-managed transaction context, not a proof against
arbitrary raw SQL using the shared runtime credential. That credential can set the same GUCs and
is not a per-user database identity. Any future direct-SQL or shared-role threat boundary requires
separate commandized membership/role isolation rather than an RLS claim this milestone does not
prove.

Runtime table access is exact:

- all twelve A/A1/A2 tables: `SELECT`;
- people, person versions, evidence objects, object assessments, evidence assets, evidence
  assessments and child heads: `INSERT`;
- people: `UPDATE` only for `version`, `status`, `current_person_version_id`,
  `last_operation_id`, `retired_at`, `retired_operation_id` and `updated_at`;
- person versions: `UPDATE` only for `closed_at` and `closed_operation_id`;
- child heads: `UPDATE` only for `revision`, `last_operation_id` and `updated_at`;
- evidence objects: `UPDATE` only for the guarded one-way `status` transition;
- release authorizations, release rules, consent policies and consent decisions: `INSERT`;
- release authorizations and release rules: `UPDATE` only for `version`, `revoked_at`,
  `revoked_operation_id`, `revocation_reason_code` and `updated_at`;
- consent decisions: `UPDATE` only for `version`, `withdrawn_at`, `withdrawn_operation_id`,
  `withdrawal_reason_code` and `updated_at`;
- consent policies and attendance release snapshots: no runtime `UPDATE`;
- attendance release snapshots: no runtime `INSERT`; and
- every 0029A/A1/A2 table: no runtime `DELETE`.

PostgreSQL guards enforce exact same-transaction command provenance, immutable facts and
assessments, the evidence state machine, one-way closure/retirement/revocation/withdrawal, revision
increments, exact latest reviewed assessments, the activation matrix, distinct consent evidence
lanes and signer basis. The activation guard is fixed-search-path, non-public and deliberately not
executable by the runtime role; it runs only as a table trigger.

Overlapping temporal lanes are rejected under concurrency. SQLite service validation is useful for
portable tests but never substitutes for the PostgreSQL direct-SQL and race gates.

The family workspace and exact-retry person/evidence loaders acquire `FOR SHARE` on the family row
before their first mutable aggregate read. Every implemented family-authority writer acquires
`FOR UPDATE` on that same row after operation serialization. Multi-statement projections therefore
observe one coherent command boundary rather than two `READ COMMITTED` snapshots.

Person replacement and retirement discover all non-revoked or non-withdrawn child dependencies
whose `effective_until` is later than one transaction-stable cutoff. Service discovery uses SQL
`current_timestamp()` and the deferred database invariant uses `transaction_timestamp()`, so
expiry between discovery and head updates cannot create an untyped partial failure. Every affected
child head must already exist and increment exactly once; a missing head fails closed.

Temporal evidence checks use `clock_timestamp()` and require each downstream effective window to
fit within evidence expiry. Deferred invariants recheck that the pinned assessment remains the
latest reviewed assessment and the evidence remains unexpired. Expiry is also re-evaluated on every
later authority decision; a child head alone is never proof against time passage.

Evidence record/review/reject commands do not change child heads. Review and rejection use distinct
receipt commands so their immutable provenance is unambiguous. Invalidation or supersession
discovers every distinct child with a nonterminal, active-or-future dependency on the assessment,
including both the consent decision-evidence and signer-authority-evidence lanes,
uses one transaction-stable cutoff, and increments each existing child head exactly once. A missing
referenced head fails closed. Record receipts commit version 1, review/reject version 2, and
invalidate/supersede version 3 against the stable evidence target ID.

Object upload commits object and quarantined-assessment version 1. A conclusive scan commits one
clean/rejected assessment version 2 plus the matching one-way object status change. Scanner
infrastructure failure commits neither a terminal assessment nor a receipt. The object-link guards
require document evidence to pin one exact clean object and copy its measured tuple; clean bytes
are remeasured at bind, review and download.

## Downgrade refusal

Before removing A2, `0029A2_authority_activation` counts all four activation tables, all matching
receipts/commands and every `signed_release_delegation` object/evidence row. Any history refuses
downgrade before DDL because A1 cannot represent it. An empty A2 may downgrade exactly to
`0029A1_family_evidence_vault`; SQLite requires that exact destination in a separate Alembic
command so a multi-revision batch cannot leave temporary tables.

Before dropping anything, the 0029A1 downgrade counts both object tables, every linked evidence row
and every object command/receipt. Any object history refuses downgrade to 0029A because that state
cannot be represented there. An empty A1 may downgrade exactly to A; on SQLite this is intentionally
a separate Alembic command so the predecessor schema is restored before any further downgrade.

Before dropping the kernel, the 0029A migration counts every new table, every receipt using a new target
type and every command in the family-authority, child-release, child-consent or attendance-release
namespaces with owner-visible RLS preflight. Any count refuses and atomically rolls back downgrade.
Only a completely empty kernel can return to 0028, at which point triggers/policies/tables are
removed in dependency order, the original three receipt target types are restored, and only the
six additive legacy identities are removed.

That empty-only path was exercised during the retained-database incident recorded above and the
database was verified back at 0028 before a full backup/restore test. This was a recovery exercise,
not a release gate approval. Protected local database ports now fail closed for Alembic unless the
exact development-only command-scoped opt-in is supplied; normal retained startup must stay pinned
to the released revision rather than unreleased `head`.

The evidence-object possession, clean-scan and maker/checker boundary is implemented in A1, and
the exact administrator activation matrix plus release authorization/rule and consent commands
are implemented in A2. The 2026-07-18 source closeout recorded 170/170 passing authority
regressions, TypeScript plus 81/501 administrator tests and an 834-module production build, and
3/3 disposable PostgreSQL A2 gates covering migration/runtime shape, exact grants, positive and
negative activation behavior, maker/checker and downgrade refusal. Retained port 5434 remains at
released `0028_childcare_command_spine`; a synthetic-only real-scanner harness is documented in
`FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`, but no 0029 cutover or signed-in authority operator proof
is claimed.
`0029B_release_context` now provides the source-verified minimum-necessary expiring educator read
projection. Its 2026-07-18 closeout passed 84/84 portable API/composer/migration/detector tests,
7/7 real disposable PostgreSQL tests on an unprotected high port (including the full gate matrix
and common-snapshot concurrency proof), and the 153/153 staff-app regression plus
TypeScript and a 744-module Android export. The complete default backend regression passed 648
with 81 explicit opt-in skips and zero failures. Protected ports were untouched. `0029C` atomic
verified checkout remains unbuilt; B neither enables nor claims it.

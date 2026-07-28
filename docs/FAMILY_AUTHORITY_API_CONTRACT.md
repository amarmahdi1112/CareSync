# CareSync 0029A/A1/A2 Family Authority API Contract

Last updated: 2026-07-22

## Status and authority

This is the canonical HTTP and schema boundary for `0029A_family_authority_kernel`, the additive
`0029A1_family_evidence_vault`, and the source-only activation revision
`0029A2_authority_activation`. It is subordinate to
`FAMILY_AUTHORITY_ARCHITECTURE.md`, `FAMILY_AUTHORITY_EVIDENCE_VAULT_ARCHITECTURE.md` and
`FAMILY_AUTHORITY_KERNEL_SCHEMA.md`. The executable request and response definitions live in
`backend/app/basic/family_authority_schemas.py`; routes and services must use them rather than
redeclare looser payloads.

The A/A1/A2 contract in this document is an owner/administrator persistence, review and
authority-activation boundary. A separate, source-verified B companion now exposes the strict
read-only educator release context defined by
`FAMILY_AUTHORITY_RELEASE_CONTEXT_ARCHITECTURE.md` and
`backend/app/basic/family_release_context_schemas.py`. Neither contract enforces checkout, enables
software override, interprets legal documents, creates a guardian account or activates consent as
a gate for unrelated care workflows. Atomic verified checkout remains staged for 0029C.

Current source implementation includes `GET /families/{family_id}/authority`; authority-person
create, replace and retire; private evidence-object upload, scan and clean-object download; and
evidence record, review, reject, invalidate and supersede. A2 implements release-authorization
grant/revoke, release-rule create/revoke, consent-policy list/publish and child-consent
record/withdraw under the exact matrix below. The current ORM includes the A1/A2 additions, so the
workspace and every A2 route fail closed unless their complete structural and least-grant gates
are present. A/A1 people and evidence routes remain available on a complete A1 schema; they do not
query A2-only columns. The source routes and strict admin client are verified by portable and
disposable restricted-role PostgreSQL gates. The retained 0028 runtime returns a contained typed
503 before issuing an authority-table query. `attendance_release_snapshots` remains SELECT-only
scaffolding for 0029C. There is no 0029 release or retained cutover, and the development host has
an installed hardened ClamAV scanner plus separate scanner-adapter, signed-in synthetic-only
operator and four-artifact recovery-consistency receipts. None authorizes retained activation or
cutover, and the recovery receipt does not change API availability or authority.

The B companion surface is exactly
`GET /children/{child_id}/release-context?facility_id={facility_id}`. It accepts no request body or
operation ID, writes no command/audit/outbox/attendance state, returns `Cache-Control: no-store`,
and is not a bearer authorization. On retained 0028 or any partial B shape it fails with typed
`503 family_authority_release_context_unavailable` before an A2 authority query. Its complete
request/response, scope, privacy, expiry and B/C boundary remain canonical in the B architecture
document rather than being duplicated loosely here.

## Common parsing rules

- Every request, nested tuple, projection and receipt rejects unknown fields.
- Strings are trimmed before domain validation. A provided string that becomes blank is rejected.
- IDs in paths are authoritative and are not repeated in request bodies. Services must bind path
  IDs into the command target scope before exact-retry hashing.
- All timestamps are timezone-aware UTC. Naive datetimes and non-zero UTC offsets are rejected.
- Every effective window is finite and closed/open: `[effective_from, effective_until)`, with both
  endpoints required and `effective_until > effective_from`.
- Every persisted content hash is exactly 64 lowercase hexadecimal characters. Consent-policy
  callers submit canonical `content_text`, not a hash or reference; the server derives both.
- A create command may generate its target UUID on the server after reserving the operation. A
  replay resolves the exact target through its immutable command receipt; it never creates a new
  target.
- Validation and string/time normalization happen before the canonical intent is hashed. The
  command hash excludes `client_operation_id` but includes every other body field plus the
  purpose-bound command name, target type and route-bound target scope.
- A first child-specific authority mutation accepts `expected_authority_revision=0` and creates
  revision one. Later child mutations require the exact positive current revision.
- Services derive actor, tenant, server timestamps, review provenance, operation columns and safe
  release explanation codes. Clients cannot submit them.

## Exact tagged tuples

Ambiguous groups are never represented as independent nullable fields.

### Authority-person source

Exactly one source shape is required on person creation:

- `{"kind":"manual"}`
- `{"kind":"guardian","guardian_id":"..."}`
- `{"kind":"emergency_contact","emergency_contact_id":"..."}`

Legacy contact rows remain historical source facts. Selecting one does not promote its legacy
pickup flag or consent booleans into authority.

### Evidence object and copied storage identity

Clients never submit a `storage` tuple, object key, media type, byte size, hash, scanner result,
reviewer, or issuer-verification claim. A document first enters the tenant/family-bound multipart
upload route. The server generates its object ID/key and measures its media type, byte size and
SHA-256. The object projection exposes the bounded display filename and measured metadata, but not
the private storage reference. A document evidence-intake request then submits only the exact
clean, same-family `evidence_object_id`; non-document evidence forbids that field.

The evidence response projects `storage` as either null or one complete server-derived copy of the
bound object's measured tuple. `storage_reference` is 1–500 characters, begins
with an ASCII alphanumeric character, contains only `[A-Za-z0-9._/-]`, and contains no empty, `.`
or `..` path segment. It is never an absolute path, URI, query, fragment or public URL.
`media_type` is a lowercase `type/subtype` value whose two components begin alphanumerically and
otherwise contain only `[a-z0-9!#$&^_.+-]`. `byte_size` is between 1 and 52,428,800 bytes
inclusive. `content_sha256` is exactly 64 lowercase hexadecimal characters. Partial tuples are
structurally impossible. Document bytes and public URLs never appear in this API.

Review provenance is carried only by `current_assessment.actor_user_id` and
`current_assessment.created_at`, together with that immutable assessment's ID, version and
decision. An unreviewed evidence asset has `current_assessment=null`. There are no
`reviewed_by_user_id` or `reviewed_at` evidence columns or response fields.

### Release-rule scope

Exactly one scope is required:

- `{"kind":"all_recipients"}`
- `{"kind":"specific_person","person_id":"..."}`

`named_recipient_only` accepts only `specific_person`. `safe_explanation_code` is response-only
and derived from `rule_kind`; confidential reasoning is never used as an educator-safe message.

### Consent scope

Exactly one scope is required:

- `{"kind":"policy"}`
- `{"kind":"facility","facility_id":"..."}`
- `{"kind":"named_activity","reference":"..."}`

No unused facility or activity field can accompany another scope.

## Exact command vocabulary

Only these reserved 0029 command names are valid. The three person commands and five evidence
commands are implemented in 0029A; the two object commands are implemented in A1; and all seven
release/rule/consent commands shown below are implemented behind the A2 activation gate:

| Command | Target type | Receipt target |
| --- | --- | --- |
| `family.authority.person.create` | `authority_person` | new stable person ID |
| `family.authority.person.replace` | `authority_person` | exact stable person ID |
| `family.authority.person.retire` | `authority_person` | exact stable person ID |
| `family.authority.evidence_object.upload` | `authority_evidence_object` | new stable object ID |
| `family.authority.evidence_object.scan` | `authority_evidence_object` | exact stable object ID |
| `family.authority.evidence.record` | `authority_evidence` | new evidence ID |
| `family.authority.evidence.review` | `authority_evidence` | exact stable evidence ID |
| `family.authority.evidence.reject` | `authority_evidence` | exact stable evidence ID |
| `family.authority.evidence.invalidate` | `authority_evidence` | exact stable evidence ID |
| `family.authority.evidence.supersede` | `authority_evidence` | exact stable evidence ID |
| `child.release.authorization.grant` | `release_authorization` | new authorization ID |
| `child.release.authorization.revoke` | `release_authorization` | exact authorization ID |
| `child.release.rule.create` | `release_rule` | new rule ID |
| `child.release.rule.revoke` | `release_rule` | exact rule ID |
| `organization.consent.policy.publish` | `consent` | new policy-version ID |
| `child.consent.record` | `consent` | new child-decision ID |
| `child.consent.withdraw` | `consent` | exact child-decision ID |

Names using underscore-separated namespaces, `update`, `delete`, checkout or override are not
aliases and must be rejected.

## Admin routes

Paths below are relative to the existing Basic API router. Every implemented mutation route
requires the same owner/administrator management permission, writable-database guard and
exact-retry ledger used by the released 0028 child-record commands.

| Method and path | Request schema | Resource response | Command |
| --- | --- | --- | --- |
| `GET /families/{family_id}/authority` | none | `FamilyAuthorityWorkspaceResponse` | none |
| `POST /families/{family_id}/authority/people` | `AuthorityPersonCreateRequest` | `AuthorityPersonCommandResponse` | person create |
| `POST /families/{family_id}/authority/people/{person_id}/versions` | `AuthorityPersonReplaceRequest` | `AuthorityPersonCommandResponse` | person replace |
| `POST /families/{family_id}/authority/people/{person_id}/retire` | `AuthorityPersonRetireRequest` | `AuthorityPersonCommandResponse` | person retire |
| `POST /families/{family_id}/authority/evidence-objects` | strict multipart: operation ID, document kind, one file | `AuthorityEvidenceObjectCommandResponse` | object upload |
| `POST /families/{family_id}/authority/evidence-objects/{object_id}/scan` | `AuthorityEvidenceObjectScanRequest` | `AuthorityEvidenceObjectCommandResponse` | object scan |
| `GET /families/{family_id}/authority/evidence-objects/{object_id}/download` | none | private attachment stream | none |
| `POST /families/{family_id}/authority/evidence` | `AuthorityEvidenceRecordRequest` | `AuthorityEvidenceCommandResponse` | evidence record |
| `POST /families/{family_id}/authority/evidence/{evidence_id}/review` | `AuthorityEvidenceReviewRequest` | `AuthorityEvidenceCommandResponse` | evidence review |
| `POST /families/{family_id}/authority/evidence/{evidence_id}/reject` | `AuthorityEvidenceRejectRequest` | `AuthorityEvidenceCommandResponse` | evidence reject |
| `POST /families/{family_id}/authority/evidence/{evidence_id}/invalidate` | `AuthorityEvidenceInvalidateRequest` | `AuthorityEvidenceCommandResponse` | evidence invalidate |
| `POST /families/{family_id}/authority/evidence/{evidence_id}/supersede` | `AuthorityEvidenceSupersedeRequest` | `AuthorityEvidenceCommandResponse` | evidence supersede |
| `POST /children/{child_id}/release-authorizations` | `ReleaseAuthorizationGrantRequest` | `ReleaseAuthorizationCommandResponse` | authorization grant |
| `POST /children/{child_id}/release-authorizations/{authorization_id}/revoke` | `ReleaseAuthorizationRevokeRequest` | `ReleaseAuthorizationCommandResponse` | authorization revoke |
| `POST /children/{child_id}/release-rules` | `ReleaseRuleCreateRequest` | `ReleaseRuleCommandResponse` | rule create |
| `POST /children/{child_id}/release-rules/{rule_id}/revoke` | `ReleaseRuleRevokeRequest` | `ReleaseRuleCommandResponse` | rule revoke |
| `GET /consent-policies` | none | `list[ConsentPolicyVersionResponse]` | none |
| `POST /consent-policies` | `ConsentPolicyPublishRequest` | `ConsentPolicyCommandResponse` | policy publish |
| `POST /children/{child_id}/consents` | `ChildConsentRecordRequest` | `ChildConsentCommandResponse` | consent record |
| `POST /children/{child_id}/consents/{decision_id}/withdraw` | `ChildConsentWithdrawRequest` | `ChildConsentCommandResponse` | consent withdraw |

Every row above is implemented in source. Workspace reads and all release/rule/policy/consent
routes require the complete `family_authority_activation_enabled` gate. A/A1 object and
person/evidence routes keep their narrower gates so a complete A1 deployment can still manage its
evidence without issuing an A2 ORM query. Route registration or a request schema alone is never an
availability signal.

For implemented routes, person/evidence creation, evidence recording and object upload return HTTP
201 for first commit and exact replay. Object scan, person replacement/retirement and evidence
review/rejection/invalidation/supersession return HTTP 200. Download is not a command and returns
only a current clean object as a private attachment. Every mutation replay returns the same
immutable receipt and the current canonical resource projection. If a later command advanced or
retired a person, retrying an older command therefore returns that older receipt alongside the
newer current projection. Replay never changes the canonical object or repeats scanner work,
assessment history, audit, realtime/outbox or authority-head effects. A retried multipart upload
is remeasured under a new private candidate before the exact receipt is known; an exact replay
deletes that candidate. Activation commands preserve the same exact-retry rule: identical
canonical intent returns the original receipt and current projection; changed-intent reuse fails.

Workspace and exact-retry projections acquire a shared family command lock before reading mutable
person/evidence aggregates. Implemented writers acquire the corresponding exclusive row lock, so
one response cannot combine state from opposite sides of a concurrent replace, retire, review or
terminal evidence transition.

After that family or organization aggregate lock, every confidential workspace/policy read and
historical command replay projection rechecks the actor's current active owner/administrator
membership. A role decision made by route dependencies is not durable; role loss fails with 403
before the confidential projection and does not modify the immutable receipt.

The family workspace is an admin-only projection. It contains stable people/current fact versions,
evidence-object metadata and current scan assessment, evidence metadata, and per-child
authorizations, rules and consent decisions. It does not expose the private object key. Missing
`child_authority_heads` project as `reviewed=false, authority_revision=0`; reads never insert rows.

## Mutation bodies

### Person commands

Creation carries `client_operation_id`, one tagged `source` and a complete `facts` object.
Replacement carries `client_operation_id`, `expected_version` and a complete replacement `facts`
object. It is not a patch. Retirement carries only `client_operation_id` and `expected_version`.
The relationship detail is required only when `relationship_kind=other` and forbidden otherwise.

### Evidence-object upload and scan

Upload is strict multipart with exactly `client_operation_id`, a document-only `evidence_kind` and
one `file`. It accepts PDF, JPEG or PNG by server-observed signature; the MIME header is advisory
and conflicting input fails. The server receive boundary and file stream each enforce configured
size limits. Version one is always `quarantined`. The scan body contains only
`client_operation_id` and `expected_version=1`; the server invokes its fixed scanner adapter and
the client cannot author a verdict. Conclusive clean or rejected scan creates version two. Missing,
failed, stale-definition or unverified scanner state returns a typed 503 and leaves the canonical
object quarantined for an exact retry.

Only a clean current object can be downloaded or attached. Download streams the already-open,
server-remeasured inode as an attachment with `Cache-Control: private, no-store`, `Pragma:
no-cache`, `X-Content-Type-Options: nosniff`, a server-generated filename and the measured content
length. Rejected bytes remain canonical private custody records but cannot be downloaded or used.

### Evidence intake and assessment

Evidence recording carries `client_operation_id`, bounded evidence kind, a nonblank source label,
optional finite UTC issue/capture/expiry timestamps, and an exact `evidence_object_id` for document
kinds. It creates immutable version-one intake metadata in the `unreviewed` lifecycle state. For a
document, the service locks and remeasures one clean, same-kind, same-family, unused object and
copies its server-owned tuple; `guardian_attestation` and `staff_witness` forbid an object. The
request accepts no storage tuple, review decision, reviewer or issuer-verification claim.

Review carries `client_operation_id`, `expected_version=1`, and an assessed epistemic status of
`reported` or `document_observed`. Rejection is a separate unambiguous command carrying
`expected_version=1` and a bounded reason. Invalidation carries `expected_version=2` and a bounded
reason and is valid only after a reviewed assessment.
Supersession also requires reviewed version two and one distinct same-family replacement evidence
asset whose current assessment is reviewed and whose evidence has not expired. These assessment
rows are immutable. Rejected, invalidated and superseded evidence is terminal; correction records a
new asset rather than rewriting history.

Rejected reasons are `insufficient_evidence`, `information_mismatch`, `unreadable`, `unsupported`,
`entered_in_error` or `other`. Invalidation reasons are `authority_changed`, `document_revoked`,
`information_corrected`, `entered_in_error` or `other`. A confidential note of at most 1,000
characters is required exactly for `other` and forbidden otherwise. Supersession derives the fixed
reason `superseded`; clients submit only the replacement evidence ID.

For document evidence, `review` requires `document_observed` and a reviewer distinct from both the
object uploader and evidence recorder. For non-document evidence, review requires `reported` and a
reviewer distinct from the recorder. Each actor must still be an active owner/administrator at
commit. Rejection remains non-activating and may be performed by the maker. Administrative review
is not legal interpretation and is never authority by itself. A2 may consume only a current
reviewed assessment through one of the explicit positive lanes below. Every unlisted
evidence/basis combination remains non-activating.

The administrator mirrors that boundary: a maker sees their submission as recorded by them and is
never offered Review, but may Reject an incorrect submission; a distinct active owner or
administrator may Review or Reject it.

The strict request schemas accept any positive `expected_version` so malformed/non-positive input
fails structurally without encoding state in parsing. The service then requires current evidence
version 1 for review/reject and version 2 for invalidate/supersede. A positive but wrong or stale
value returns a typed HTTP 409; it is not an HTTP 422 schema failure.

### Release authorization

Grant carries `client_operation_id`, `expected_authority_revision`, recipient person ID, bounded
verification policy, one exact reviewed grantor person/version/authority/evidence tuple, and a
finite effective window. Revoke carries both the record `expected_version`, child
`expected_authority_revision`, and one bounded reason code. Revocation is one-way.

The grant activation matrix is exact:

| Grantor authority basis | Required current reviewed evidence | Additional provenance |
| --- | --- | --- |
| `guardian_record` | `guardian_attestation` | grantor is the current authority person sourced from the live guardian record |
| `reviewed_custody_evidence` | `custody_document` | no implicit guardian promotion |
| `reviewed_delegation_evidence` | `signed_release_delegation` | grantor still has original live-guardian provenance; a delegate cannot re-delegate |

`other_reviewed_authority`, identity documents, court orders, staff witness, signed consent and
`other_document` are non-activating in A2. The command actor must differ from the evidence
reviewer, the evidence must remain current and reviewed, and the command window cannot outlive
evidence expiry.

### Release rule

Create carries `client_operation_id`, `expected_authority_revision`, rule kind, tagged scope,
optional exact directing person/version, reviewed authority basis, reviewed evidence ID,
confidential nonblank reason and a finite window. Revoke carries both expected versions and one
bounded reason. Rule-safe explanation is derived by the server:

- `deny` -> `release_restricted`
- `supervised_only` -> `supervision_required`
- `named_recipient_only` -> `named_recipient_only`
- `manager_review` -> `manager_review_required`

A2 activates only `deny` and `manager_review`. `supervised_only` and
`named_recipient_only` stay blocked until their missing supervision/recipient semantics are
designed. Rule authority is limited to `guardian_record` + `guardian_attestation` or
`reviewed_custody_evidence` + `custody_document`. The guardian lane requires one explicit current
directing guardian person/version; the custody lane may omit a directing person. The same
current-review, expiry and activator-not-reviewer rules apply.

### Consent policy and decision

Policy publication carries an explicit version number from 1 through 2,147,483,647, bounded
purpose, nonblank title, immutable `content_text` of at most 20,000 characters, bounded signer
requirement and finite window. The server derives SHA-256 from the exact UTF-8 content and sets the
immutable canonical reference to `/consent-policies/{policy_id}`. The readable policy content is
returned to the administrator before a decision is recorded. The server sets publication time.
Same-purpose windows cannot overlap.

A child decision carries `expected_authority_revision`, the exact same-purpose policy ID, exact
signer person/version/authority tuple, two distinct reviewed evidence tuples, bounded decision,
tagged scope and finite window. The decision-evidence lane is always `signed_consent`. The
separate signer-authority lane is exact:

| Published policy requirement | Signer authority basis | Required signer-authority evidence | Additional provenance |
| --- | --- | --- | --- |
| `guardian_record` | `guardian_record` | `guardian_attestation` | signer is sourced from the live guardian record |
| `legal_decision_maker` | `reviewed_custody_evidence` | `custody_document` | no implicit guardian or pickup promotion |

`specific_reviewed_authority` is not activatable in A2. The decision evidence ID must differ from
the signer-authority evidence ID; both assessments must be current and reviewed, neither evidence
may expire before the decision ends, and the command actor must differ from both reviewers. Invalidation or
supersession of either dependency advances each affected child head exactly once. Withdrawal
carries record and child expected versions plus one bounded reason. Pickup authority never
satisfies or implies consent authority.

## A2 runtime and database gate

The A2 HTTP surface is enabled only when startup proves the complete activation shape. On
PostgreSQL that includes all four activation tables, the policy text and separate signer-authority
columns, exact static constraints, forced RLS, activation triggers/function hardening and exact
runtime grants. The runtime role receives SELECT and INSERT on release authorizations, release
rules, policy versions and consent decisions; UPDATE exists only on the explicit revocation or
withdrawal columns. It receives no table-wide UPDATE or DELETE. Consent policies remain immutable,
and `attendance_release_snapshots` remains SELECT-only with no runtime INSERT. Structural
incompleteness produces `503 family_authority_activation_unavailable` before an A2 ORM query.

The immutable evidence, assessment and consent-policy tables retain no runtime `UPDATE` grant.
Activation reads therefore do not request PostgreSQL row locks that require that privilege; they
are serialized by the already-held canonical family or organization aggregate lock. A2 first
commits explicitly flush receipt, then authorization/rule/consent target, then authority head so
the database target/head guard observes the required order without relying on ORM table ordering.

## Response and receipt boundary

Every mutation response has exactly:

- `resource`: the canonical admin projection after commit;
- `receipt`: `FamilyAuthorityCommandReceiptResponse`; and
- `replayed`: whether the operation was resolved from an existing receipt.

Evidence projections contain immutable asset facts, exact `recorded_by_user_id`, aggregate
version, lifecycle state, computed effective state (including expiry), `valid_now`, server
evaluation time and the current immutable assessment. The assessment exposes exact
`actor_user_id` and `created_at` provenance; it does not
invent mutable reviewer fields on the evidence asset. Full assessment history belongs on a future
evidence-detail projection. Time passage does not mutate the asset or manufacture a receipt.

The receipt contains only organization/operation IDs, exact command and target types, exact target
ID, committed version/time, optional facility ID and a validated local action route. It never
contains names, phone/email, source labels, storage references, hashes, evidence facts, authority
basis, confidential reasons, consent choices or an arbitrary outcome object. The existing
`GET /childcare-commands/{client_operation_id}` reconciliation route must expose the same
minimum receipt field set for these commands.

After a first commit, response projection expires ORM identity state before reading the receipt.
This reloads database-trigger-authored canonical timestamps and makes the first response use the
same persisted receipt projection as every exact replay.

For authority commands, PostgreSQL accepts only a 64-character lowercase hexadecimal request hash
and an outcome object containing exactly one string key, `action_route`. Canonical routes are:

- person: `/families/{family_id}?authority_person_id={person_id}`
- evidence object: `/families/{family_id}?authority_evidence_object_id={object_id}`
- evidence: `/families/{family_id}?authority_evidence_id={evidence_id}`
- release authorization: `/children/{child_id}?release_authorization_id={authorization_id}`
- release rule: `/children/{child_id}?release_rule_id={rule_id}`
- consent policy: `/consent-policies/{policy_id}`
- child consent: `/children/{child_id}?consent_id={decision_id}`
- future release snapshot: `/attendance/releases/{release_id}`

The administrator recognizes these route maps through own properties only. Person, evidence object,
evidence, authorization, rule and consent links open the correct workspace/tab, scroll to and
highlight the exact typed row, and never fall back to another record when the target is absent or
the query is malformed.

Additional outcome keys, arbitrary routes, malformed hashes and PII-bearing receipt metadata fail
atomically. All family-authority responses, including failures, are private and carry
`Cache-Control: no-store`.

Entity responses may contain confidential authority/evidence fields only on the admin routes
above. They must not be reused as educator, realtime, push or OS-notification payloads.

Outside the narrow schema-owner restore/repair bypass, all twelve A/A1/A2 table policies require the API-set
tenant and actor GUCs plus a matching active owner/admin membership and fail closed when either
setting is missing or malformed. That protects API-managed transactions; it is not proof against
arbitrary raw SQL through the shared runtime credential, which can set those GUCs. The ordinary
educator API remains the enforced product boundary until a later phase introduces a stronger
per-user database identity design.

## Failure semantics

- Structural/schema rejection: HTTP 422 before any operation slot or domain row is written.
- Unsupported, empty or signature/MIME-mismatched upload: HTTP 422.
- Whole multipart body or file-size limit: typed HTTP 413 (`evidence_upload_body_too_large` or
  `evidence_file_too_large`).
- A malware-clean file that fails structural PDF/image validation commits terminal object version
  two as `rejected` with `reason_code=invalid_document`; the scan response is HTTP 200, but no
  evidence record or download is permitted.
- Missing tenant-bound path resource: HTTP 404 without disclosing cross-tenant existence.
- Reused operation with different canonical intent: HTTP 409 `operation_reused`.
- Object version/state/kind/single-use conflict: typed HTTP 409, including
  `stale_evidence_object`, `evidence_object_not_clean`, `evidence_object_kind_mismatch` or
  `evidence_object_already_bound`.
- Missing or changed private bytes: HTTP 409 `evidence_object_integrity_failed`.
- Maker/checker conflict: HTTP 409 `maker_checker_required`.
- Configured scanner missing, scan failure, unverified or stale definitions: typed HTTP 503; no
  terminal assessment is appended and the object remains quarantined.
- Stale record or authority revision: HTTP 409 with the existing typed stale-version contract.
- Evidence expiry before review: HTTP 409 `authority_evidence_expired`.
- A supersession replacement that is stale, terminal or expired: HTTP 409
  `replacement_evidence_not_current`.
- Privilege lost before database commit or a confidential replay projection: HTTP 403
  `family_authority_access_revoked`.
- A child-head or evidence-state race at commit: typed HTTP 409, including
  `authority_revision_changed` or `authority_evidence_state_changed`.
- Overlap, inactive/stale person version, unreviewed evidence, signer-policy mismatch or other
  fail-closed domain conflict: HTTP 409 with a stable non-confidential code.
- Retained 0028 or a partial A/A1 schema: HTTP 503 `family_authority_unavailable` (or the narrower
  `family_evidence_vault_unavailable` object-route gate) without an authority-table query. A partial
  A2 shape returns `family_authority_activation_unavailable` on workspace/activation routes while
  preserving schema-safe A/A1 evidence operations.
- Read-only or reconciliation-unavailable state: existing 0028 service-unavailable behavior.

Validation is not authorization. Services and PostgreSQL guards still prove tenant/family/child
coherence, reviewed evidence, exact current versions, signer requirements, overlap exclusion,
same-transaction command provenance and monotonic revision changes.

## Source verification record

The 2026-07-18 A2 closeout recorded 170/170 passing focused authority regression tests. The
administrator client passed TypeScript, 81 test files / 501 tests and a production build
transforming 834 modules; the only diagnostic was the existing oversized-chunk advisory. A
disposable PostgreSQL 17 run passed 3/3 A2 gates covering fresh migration/runtime identity,
forced-RLS and exact grants, positive activation commits, direct negative matrix enforcement,
maker/checker rejection and populated downgrade refusal. Protected ports 5432/5433/5434 were not
used. These are source/disposable proofs only: retained port 5434 remains released
`0028_childcare_command_spine` and no 0029 cutover occurred. At that checkpoint, the later hardened
synthetic-only ClamAV adapter and 0029C/D normal verified-checkout source boundary did not yet prove
a signed-in authority operator flow, facility activation or retained release.

The separate 2026-07-18 B closeout passed 84/84 portable API/composer/migration/detector tests and
7/7 real disposable PostgreSQL tests on an unprotected high port, including complete detector,
hardening-revoke rejection/restoration, the operational gate matrix and the 400-transition
common-snapshot race. The administrator remained green at 81 test files /
501 tests plus TypeScript/build; the staff app passed 153/153 tests, TypeScript and an Android
export transforming 744 modules. Protected ports 5432/5433/5434 were untouched. B is verified as
a read-only source boundary only; the complete default backend regression passed 648 with 81
explicit opt-in skips and zero failures. The retained database remains at 0028, B itself claims no
operator or cutover authority, and B writes neither checkout nor a release snapshot. The later
bounded local scanner and signed-in operator receipts do not change that B boundary.

The separate 2026-07-22 actual CLI certification passed all 16 signed-in public-HTTP A/A1/A2 cases
on a fresh caller-provisioned loopback PostgreSQL 17 database at exact
`0029D_release_checkout_writer` under `caresync_basic_app`, with real ClamAV 1.5.3/28068. It
observed multipart upload and scan exact retries without duplicate objects/assessments, byte-exact
private download, maker review rejection with attested no-write, independent checker review,
reviewed authority activation and exact replay, the administrative summary, and the canonical
PII-free invalidation through a public realtime ticket/WebSocket replay. Preflight/postflight
proved the same system and revision, expected synthetic rows and zero unexpected sessions. The
private mode-`0600`, no-clobber redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
It grants neither release nor cutover authority, did not exercise the C/D checkout command, and
does not replace physical-device/operator, accessibility/privacy/regulatory or retained
activation/cutover gates.

The later synthetic exact-0029D artifact-recovery consistency gate restored the already-fixed
database backup/manifest and evidence bundle/manifest as one bound set, matching 90 tables / 61
rows and one evidence object. Its private joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
That receipt proves recovery consistency only. It explicitly denies source-writer quiescence,
authoritative source completeness/same-snapshot capture, target-schema authenticity and every
migration, release, cutover or purge authority. It therefore neither activates these endpoints nor
changes the retained 0028 capability-unavailable behavior.

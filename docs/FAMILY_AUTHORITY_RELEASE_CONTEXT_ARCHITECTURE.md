# CareSync 0029B Family-Authority Release Context Architecture

Last updated: 2026-07-22

## Status and decision

This document records the locked design and source-verified implementation of
`0029B_release_context`, the bounded slice after `0029A2_authority_activation`. The migration,
strict read-only API/composer/repositories, structural runtime detector, generic realtime
invalidation and staff-app review surface exist in source and have passed portable and disposable
PostgreSQL gates. They have not been applied to the retained database and are not a local or
production release. The retained 0028 runtime therefore keeps the endpoint unavailable behind its
typed pre-query runtime gate.

0029B exposes one minimum-necessary, expiring, read-only educator projection:

`GET /children/{child_id}/release-context?facility_id={facility_id}`

It does not check a child out, mutate attendance, create a command receipt, write a release
snapshot, capture an identity-check result, create an override, or issue an authorization token.
The response is preparation data that may become stale immediately after it is returned. A future
0029C command must recompute every gate under lock at authoritative server commit time.

The retained database remains at the released 0028 boundary. All 0029B database verification used
disposable SQLite databases and a disposable PostgreSQL cluster on an unprotected high port.
Ports 5432, 5433 and 5434 were not contacted.

## Existing source boundary

The design is based on the current source, not an assumed greenfield access model:

- 0029A/A1 persist stable authority people, immutable fact versions, evidence objects, evidence
  assessments and child authority heads.
- 0029A2 activates finite release authorizations and only the `deny` and `manager_review` release
  rule kinds. `supervised_only` and `named_recipient_only` remain non-activatable.
- Every A2 child authority mutation advances `child_authority_heads.revision`. Person and evidence
  changes advance every live-or-future dependent child head.
- Family-authority RLS is intentionally owner/administrator-only. An educator cannot and must not
  receive the admin workspace, evidence, grantor provenance, court-order metadata or confidential
  rule reason.
- Staff operational access currently comes from active organization membership, JSON role
  permissions, active room assignments, a server-owned open `staff_shifts` row, and the assigned
  attendance roster.
- The current staff app obtains canonical state through REST, receives resumable database-outbox
  invalidations, and persists a cursor only after the canonical refresh succeeds.
- The current `/attendance/check-out` route is attendance-only and does not prove recipient or
  release authority. 0029B does not make that route safe or verified.

## Safety properties

0029B must preserve all of these properties:

1. The absence of a positive, current authorization never becomes permission.
2. An active deny or manager-review rule always removes the affected recipient from normal
   eligibility. An all-recipient rule blocks all normal recipient selection.
3. Unknown, internally inconsistent or unsupported decision material fails closed.
4. Server/database time determines all effective windows. Device time never activates authority.
5. The educator sees only facts needed to identify an eligible recipient and perform the allowed
   identity-check workflow.
6. Realtime is an invalidation hint only. REST remains canonical.
7. The response expires independently of realtime because authority can change through time
   passage without a database write.
8. A response identifier or digest is not a bearer capability and is never accepted as proof of
   release.
9. The GET performs no domain, command, audit, notification or outbox write.
10. No 0029B implementation may call the legacy checkout route after presenting the context as a
    verified release decision.

## Exact HTTP contract

### Request

Method and path:

```text
GET /api/v1/children/{child_id}/release-context?facility_id={facility_id}
```

Required headers are the existing bearer token and, when required by the existing multi-tenant
contract, `X-Organization-ID`. There is no request body, operation ID, requested time, recipient,
identity result or override field.

The query surface is strict. `facility_id` must appear exactly once. Unknown query parameters,
duplicate parameters, malformed UUIDs and a request body return 422 before an authority query.

### Successful response

The response schema rejects extra fields at every level. All UUIDs are canonical lower-case,
hyphenated strings and all timestamps are UTC. `fresh_for_ms` is an integer from 1 through 30,000.

```json
{
  "schema_version": "release-context-v1",
  "decision_policy_version": "release-context-v1",
  "organization_id": "00000000-0000-0000-0000-000000000000",
  "facility_id": "00000000-0000-0000-0000-000000000000",
  "room_id": "00000000-0000-0000-0000-000000000000",
  "child_id": "00000000-0000-0000-0000-000000000000",
  "attendance_day_id": "00000000-0000-0000-0000-000000000000",
  "attendance_interval_id": "00000000-0000-0000-0000-000000000000",
  "staff_shift_id": "00000000-0000-0000-0000-000000000000",
  "evaluated_at": "2026-07-18T12:00:00.000000Z",
  "expires_at": "2026-07-18T12:00:30.000000Z",
  "fresh_for_ms": 30000,
  "authority_revision": 7,
  "restriction_digest_sha256": "ddc97498440b29337c51557fdfba1503074cc332bdd69538d3603b02238e342b",
  "decision": "recipient_selection_available",
  "blockers": [],
  "eligible_recipients": [
    {
      "recipient_person_id": "00000000-0000-0000-0000-000000000000",
      "recipient_person_version_id": "00000000-0000-0000-0000-000000000000",
      "display_name": "Example Recipient",
      "preferred_name": null,
      "relationship_label": "Grandparent",
      "authorization_id": "00000000-0000-0000-0000-000000000000",
      "authorization_version": 1,
      "verification_policy_code": "government_photo_id_or_documented_familiarity",
      "verification_methods": [
        "government_photo_id",
        "documented_familiarity"
      ]
    }
  ]
}
```

Exact response enums are:

- `decision`: `recipient_selection_available` or `blocked`;
- `blockers`: a deduplicated ordered list drawn from
  `authority_not_reviewed`, `release_restricted`, `manager_review_required`,
  `verification_workflow_unavailable`, `recipient_identity_ambiguous`, and
  `no_active_release_authorization`; and
- `verification_methods`: one or both of `government_photo_id` and
  `documented_familiarity`.

The verification-policy projection is exact:

| Stored policy | `verification_methods` | Eligible in B |
| --- | --- | --- |
| `government_photo_id` | `['government_photo_id']` | yes |
| `documented_familiarity` | `['documented_familiarity']` | yes |
| `government_photo_id_or_documented_familiarity` | both, in the table order | yes |
| `government_photo_id_and_secondary_check` | none | no; safe blocker |

`government_photo_id_and_secondary_check` is persisted vocabulary but has no exact secondary-check
input, result or snapshot representation. It cannot be advertised as executable.

`display_name` is the normalized legal first, optional middle and last name joined with one ASCII
space. `preferred_name` is returned separately when present. `relationship_label` is a
server-formatted label from the bounded relationship kind; the bounded detail is used only when
the kind is `other`. Phone, email and address are forbidden.

Eligible recipients are sorted by canonical `recipient_person_id`, not database insertion order or
locale-sensitive name order. The client may visually sort a copy, but it must retain each exact
identifier binding.

### Response headers

Every 200 and every authority-context failure carries:

```text
Cache-Control: private, no-store
Pragma: no-cache
X-Content-Type-Options: nosniff
Vary: Authorization, X-Organization-ID
```

The route does not support conditional GET, shared caches, service-worker caching or offline
fallback.

## Access and operational gates

Introduce one dedicated permission, `release:read`. Add it to the source owner, administrator and
educator system-role templates. The B migration appends it only to existing `is_system=true` roles
whose keys are `owner`, `administrator` or `educator`; it does not silently grant it to custom
roles. Downgrade removes only this new permission from those system roles.

The route requires all of the following at evaluation time:

1. an active user and active membership in the selected organization;
2. an active organization;
3. `release:read` in the current role permission list;
4. one open staff shift owned by that exact membership at the exact requested facility;
5. an active requested facility;
6. one open attendance interval for the exact child at that facility;
7. an active child and active room matching the attendance day; and
8. either organization-wide release scope (`owner` or `administrator`) or an active membership
   assignment to that exact room and facility.

Unlike the general `require_open_shift` helper, release-context access has no owner/administrator
clock-in bypass. Organization-wide leaders may omit a room assignment, but they must still have an
open shift at the facility. A shift at another facility never qualifies.

Gate failures occur before the confidential authority projection is loaded. Wrong-tenant,
wrong-facility, wrong-room and unassigned-child lookups return the same scoped 404 boundary used by
the attendance roster. A known, assigned child with no open interval returns typed 409
`child_not_on_site`. Missing or wrong-facility shift returns typed 409 `open_shift_required` or
`open_shift_facility_mismatch`. Missing permission returns 403.

The route must not call `ensure_writable`; it remains available in a deliberately read-only
database process after its structural runtime gate passes.

## Eligibility and blocker semantics

All comparisons use one captured `evaluated_at` and closed/open windows:

```text
effective_from <= evaluated_at < effective_until
```

An authorization is a candidate only when all of the following are true:

- it belongs to the exact organization, family and child;
- it is not revoked and is effective at `evaluated_at`;
- its recipient stable person is active and has one coherent current fact version;
- its exact supporting evidence assessment is still the latest `reviewed` assessment;
- the evidence has not expired; and
- its verification policy is one of the three executable B policies above.

Grantor identity, grantor fact currency and grantor evidence are provenance, not educator-facing
identity facts. A historical grantor version is not silently substituted with a current version.
Any later administrative change that should end a grant must use revocation or evidence
invalidation; the child revision and realtime signal then invalidate B context.

A release rule participates in the restriction set only when it is unrevoked, effective, backed
by its exact latest reviewed and unexpired assessment, and has an A2-activatable kind. The two B
rules compose as follows:

| Kind | Scope | Result |
| --- | --- | --- |
| `deny` | `all_recipients` | block all normal recipient selection |
| `deny` | `specific_person` | remove that person from eligibility |
| `manager_review` | `all_recipients` | block all normal selection; contact a manager outside B |
| `manager_review` | `specific_person` | remove that person; no approval is synthesized |

When both kinds apply, `deny` has display precedence, but both remain in the canonical digest.
Rules do not overwrite grants; they independently filter them.

Decision construction is deterministic:

1. A missing child authority head returns revision zero, `blocked`, no recipients and only
   `authority_not_reviewed`.
2. Any all-recipient active rule returns `blocked`, no recipients and its safe blocker codes in
   precedence order: `release_restricted`, then `manager_review_required`.
3. Otherwise, remove candidates affected by a specific-person rule.
4. Remove candidates whose verification policy is not executable. If that was the only reason no
   candidate remains, return `verification_workflow_unavailable`.
5. If two remaining records have the same case-insensitive visible name, preferred name and
   relationship, return `recipient_identity_ambiguous` with no candidates until an administrator
   resolves the records.
6. If at least one unambiguous candidate remains, return `recipient_selection_available`, an empty
   blocker list and only those candidates.
7. If effective candidates existed but specific-person rules removed all of them, return
   `blocked` with the applicable safe rule code(s), deduplicated in the same precedence order.
8. Otherwise return `blocked` with `no_active_release_authorization`.

The response never lists a blocked person's name or explains which rule affected which person.
The UI says only that normal release is unavailable and directs staff to the facility's manager
process. There is no software approval or override in B.

A structural contradiction—duplicate active authorization for a recipient, incoherent current
person version, malformed rule/safe-code pair, cross-family row, impossible assessment sequence or
head/row revision invariant failure—returns 409 `release_context_inconsistent` and no recipient
data. It is not reduced to “no authorization.”

## Canonical restriction digest

The digest binds the complete set of effective, evidence-valid release restrictions at
`evaluated_at`, including restrictions for people who do not currently have a positive grant. It
does not include confidential reasons, evidence identifiers, evidence hashes, directing-person
provenance, display names or grant data.

The canonical document is:

```json
{
  "decision_policy_version": "release-context-v1",
  "rules": [
    {
      "effective_from": "2026-07-18T10:00:00.000000Z",
      "effective_until": "2026-07-19T10:00:00.000000Z",
      "rule_id": "00000000-0000-0000-0000-000000000000",
      "rule_kind": "deny",
      "rule_version": 1,
      "safe_explanation_code": "release_restricted",
      "scope_kind": "specific_person",
      "scope_person_id": "00000000-0000-0000-0000-000000000000"
    }
  ]
}
```

For `all_recipients`, `scope_person_id` is JSON `null`; the key is never omitted. Rules are sorted
lexicographically by canonical lower-case `rule_id`. Object keys are serialized in ascending code
point order with UTF-8, `ensure_ascii=false`, separators `(',', ':')`, no insignificant whitespace
and no trailing newline. UUIDs are lower-case and hyphenated. UTC timestamps always contain six
fractional digits and `Z`. Integers use base-10 without a sign or leading zero. The digest is the
lower-case hexadecimal SHA-256 of those exact bytes.

The empty rule set therefore hashes the canonical bytes for:

```text
{"decision_policy_version":"release-context-v1","rules":[]}
```

Do not substitute a database JSON textual representation, Pydantic's default dump or locale-aware
sorting. One pure canonicalizer and fixed golden vectors must be shared by B tests and reused by
C's commit-time recomputation.

`authority_revision` and `restriction_digest_sha256` have different jobs. The revision detects any
authority aggregate mutation; the digest identifies the exact effective restriction composition.
Neither proves that a grant remains effective after time passes.

## Expiring freshness

Set `RELEASE_CONTEXT_MAX_TTL_MS = 30000`.

`expires_at` is the earliest of:

- `evaluated_at + 30 seconds`; and
- the next strictly future `effective_from` or `effective_until` among coherent, unrevoked,
  evidence-current release authorizations and rules for the child.

Evidence expiry is also considered defensively even though A2 creation already bounds a dependent
window by evidence expiry. A terminal evidence assessment or explicit revocation is a mutation and
uses realtime/head invalidation; time passage uses this expiry calculation.

`fresh_for_ms` is the floor of `(expires_at - evaluated_at)` in milliseconds. A non-positive value
must be reevaluated rather than returned.

The mobile client records monotonic request start and response-receive times. Its in-memory lease
deadline is:

```text
received_monotonic + max(0, fresh_for_ms - round_trip_ms)
```

It does not extend freshness because the device wall clock is slow or changed. It also treats the
context as stale immediately on every organization realtime event, socket reset, organization/facility/
room change, staff bootstrap change, app backgrounding or loss of online canonical refresh. A
future C confirmation always refetches when the B lease is stale.

## PostgreSQL projection boundary

The existing A2 policies intentionally permit confidential authority-table reads only for an
active owner/administrator actor. Expanding those table policies to ordinary educators would
expose evidence, grantor provenance and confidential rule reasons through the shared runtime role.
0029B must not do that.

The B migration creates one narrow PostgreSQL function:

```text
public.caresync_family_release_context_inputs(uuid, uuid)
```

The arguments are `(child_id, facility_id)`. The function is `SECURITY DEFINER`, has the exact
`search_path=pg_catalog,public`, uses no dynamic SQL, is revoked from `PUBLIC`, and grants execute
only to `caresync_basic_app`. Its owner is the migration/schema owner, not the runtime role.

The function performs one statement-snapshot projection and validates the API-set
`app.current_organization_id` and `app.current_user_id` against active user, membership,
organization, current role/permission, exact facility shift, attendance interval and room scope.
Missing or malformed context fails closed. It obtains a shared lock on the same family row that
all A/A1/A2 authority writers take for update, so the authority head, people, grants, rules and
assessments come from one side of a concurrent authority mutation.

The internal result contains only the gate identifiers, captured server time, head revision,
minimum recipient facts, active/future authorization decision fields, effective restriction
decision fields and next transition time required by the pure composer. It never returns document
metadata, evidence IDs/hashes, grantor/directing-person facts, confidential reasons, phone, email,
address, consent records or private storage data. The Python boundary validates this internal
shape strictly before composing the public response.

PostgreSQL authority-table RLS and current table grants remain unchanged. In particular, an
educator still receives zero rows from a direct authority-table SELECT. The new function is the
only educator projection boundary. The disclosed shared-runtime-role/GUC limitation remains: the
database role is not a per-end-user identity boundary, so the API and credential boundary remain
security-critical.

SQLite uses the same pure composer after equivalent application-enforced tenant, membership,
permission, shift, attendance and room-scope queries. Portable and PostgreSQL golden vectors must
produce byte-identical digest and response decisions.

## Migration and runtime gate

Proposed revision:

```text
revision = "0029B_release_context"
down_revision = "0029A2_authority_activation"
```

The revision identifier remains below Alembic's existing 32-character PostgreSQL column limit.
The migration is additive and creates no authority or release domain row. It:

1. appends `release:read` to the three existing system-role templates in database data;
2. creates and hardens `caresync_family_release_context_inputs` on PostgreSQL;
3. creates a generic release-context invalidation trigger on child-head insert/revision update;
4. installs the equivalent SQLite invalidation trigger;
5. sanitizes family-authority audit bridging before those events reach the tenant realtime
   stream; and
6. grants only the exact new function execution required by the runtime role.

No new table is required. There is no runtime `INSERT`, `UPDATE` or `DELETE` grant on an authority
table for B. Because B persists no history, an exact B-to-A2 downgrade drops the B function and
triggers and removes the system-role permission; it never alters A2 authority rows.

Add `Database.has_family_authority_release_context()` as a structural, descendant-compatible
detector. On PostgreSQL it verifies function signature, owner boundary, `SECURITY DEFINER`, fixed
search path, no PUBLIC execute, exact runtime execute, trigger definitions, unchanged A2 forced
RLS/grants and the sanitized audit bridge. On SQLite it verifies the B trigger and the complete A2
shape. A partial B boundary is false.

Startup sets `app.state.family_authority_release_context_enabled` only when A2 and every B check
pass. The route calls a distinct gate before any A2/B projection query and returns:

```json
{
  "detail": {
    "code": "family_authority_release_context_unavailable"
  }
}
```

with HTTP 503. It must not fall back to legacy contact pickup flags, the admin workspace or an
empty eligible list. Future B descendants remain enabled by structural checks; the detector must
not require Alembic head equality.

## Realtime invalidation

Every insert or revision update of `child_authority_heads` creates exactly one generic durable
organization realtime event in the same transaction:

```json
{
  "type": "family_authority.release_context_invalidated",
  "entity_type": "child_authority_head",
  "entity_id": null,
  "payload": {
    "source": "authority_head",
    "scope": "release_context"
  }
}
```

The event deliberately contains no child, family, person, evidence, authorization or rule ID.
Educator clients discard every in-memory release context for that organization and refetch the
currently visible on-site child when needed. This broader invalidation is preferable to leaking a
child authority change to staff assigned to another room.

The existing audit-to-realtime bridge must suppress `family.authority.*`, `child.release.*`,
`child.consent.*` and `organization.consent.*` audit rows rather than forwarding their admin
action type or target ID to the ordinary organization stream. Child-head changes already produce
the exact generic invalidation above; duplicating them through the audit bridge adds no safety.
Authority administration that does not change a child head does not change a release context and
needs no educator event. No B event enters OS push or user-notification content.

Migration, runtime-detector and shared-contract tests require `child_authority_head` as the sole
canonical database-trigger entity identity, require a null entity ID, reject the legacy
`release_context` identity and reject child/family identifiers in event payloads.

Shift clock-in/out, attendance interval changes, room assignment changes, membership/role changes,
facility/room status changes and child placement changes already have or must gain durable safe
invalidations before B is enabled. The client invalidates first and advances its realtime cursor
only after the corresponding canonical staff bootstrap/roster/context refresh succeeds. A replay
limit or cursor-ahead reset clears the context before rebuilding canonical state.

Time-boundary expiry does not need an event. The local monotonic lease handles it.

## Client cache, journal and UX contract

The staff app adds a strict release-context parser and API client separate from the current
attendance client. Its context cache is memory-only and keyed by exact organization, user,
membership, shift, facility, room, child, attendance day and interval IDs. It is never written to
AsyncStorage, SecureStore, filesystem, analytics, crash breadcrumbs, logs, notification payloads
or a URL.

The B GET is not a command, so it creates no pending-operation record and no reconciliation
journal. The existing realtime cursor may remain in `SecureCursorCheckpoint`; it contains no PII
and is advanced only after canonical refresh. A future C frozen intent belongs in a new encrypted
release-operation store and must not reuse `PendingAttendanceOperationStore` without adding the
exact recipient, revision, digest, verification and immutable receipt checks.

The B mobile UI is a read-only “Review release context” panel opened from an on-site child. It:

- shows a clear expiry/refresh state and disables itself while offline or stale;
- lists only `eligible_recipients` and their safe identity-check options;
- maps blocker codes to audited local copy and never displays a server-supplied arbitrary reason;
- tells staff to contact a manager when blocked or when an expected person is absent;
- never displays evidence, legal text, phone/email or confidential admin reasoning; and
- contains no “Confirm release” or checkout mutation in B.

The existing staff-app “Check out” action remains an unverified attendance action until C. B must
not place the read-only panel in front of that button in a way that implies the later legacy call
was authority-verified. Until C atomically replaces the flow, the B panel stays behind an explicit
development/release-preparation gate and the existing safety copy continues to state that release
authority is not yet verified in CareSync.

The administrator frontend does not consume the educator response. Its A2 workspace remains the
only place for confidential authority administration. A separate owner/admin child-profile summary
projects only minimum-necessary current status and an explicitly addressed historical receipt; it
has its own strict response contract and never reuses the educator B shape.

## Concurrency and time boundaries

The B projection is advisory but must still be internally coherent:

- family shared lock first for all authority material;
- one statement-owned `evaluated_at` for every effective/expiry comparison;
- deterministic person, authorization and rule ordering;
- one active open interval at the exact facility;
- one open shift at the exact facility; and
- no projection assembled across opposite sides of an A2 mutation.

An A2 revoke, new rule, person replacement/retirement, evidence invalidation/supersession and B
read must have a serial before-or-after result for authority material. The writer remains ordered
operation slot -> family -> child -> head -> dependent rows. B takes no operation slot and only a
shared family lock.

Attendance checkout, shift clock-out, room unassignment or facility deactivation may win
immediately after a valid response. That is expected: B is not commit authorization. Realtime and
the 30-second lease invalidate the client, while C must lock and recheck those rows atomically.

Effective boundaries are exact. At `effective_from` a row participates; at `effective_until` it
does not. A context generated just before a future start/end expires at that boundary even if its
30-second cap would be later. Database and Python timestamp normalization must preserve
microseconds.

## Failure semantics

- 401: missing, invalid, inactive or auth-version-stale identity.
- 403: inactive organization access or missing `release:read`.
- 404: tenant/facility/room/child scope not visible to this actor.
- 409 `open_shift_required`: no exact active facility shift.
- 409 `open_shift_facility_mismatch`: the actor is clocked in elsewhere.
- 409 `child_not_on_site`: scoped child has no exact open interval.
- 409 `release_context_inconsistent`: canonical authority inputs contradict an invariant.
- 503 `family_authority_release_context_unavailable`: A2/B structural or hardening gate incomplete.
- 200 `blocked`: a coherent context exists, but normal recipient selection is unavailable for one
  of the bounded safe blocker reasons.

Network failure never returns cached context as fresh. A malformed 200 response is a client
protocol failure and locks the release-preparation panel until a valid canonical refetch.

## Prerequisite defects and bounded corrections

These source findings were closed or explicitly made fail-closed in the source-verified B slice.
They remain part of the release contract and must not regress:

1. **Secondary-check representation is absent.** A2 accepts
   `government_photo_id_and_secondary_check`, while the future snapshot has no exact secondary
   method/result tuple. B must exclude it. Prefer also rejecting new A2 grants with typed
   `verification_policy_not_activatable` until C adds a reviewed exact representation.
2. **Authority audit events are too specific for the ordinary tenant stream.** The generic 0011
   bridge forwards admin authority action type and opaque target ID organization-wide. Sanitize
   those actions and add the generic head invalidation above before educator context is exposed.
3. **Educator RLS correctly blocks direct A2 reads.** Do not weaken it. Implement the narrow
   definer projection and prove direct educator SELECT remains empty/denied.
4. **The current mobile checkout is a legacy bypass.** B cannot be marketed or released as
   verified checkout. C must atomically replace or gate every legacy checkout entry point.
5. **`create_release_rule` currently acquires `_lock_child_boundary` twice consecutively.** Remove
   the duplicate and retain one auditable family -> child -> head lock acquisition before adding
   B concurrency proof.
6. **Operational invalidation coverage needs an explicit inventory.** Prove membership role,
   room assignment, shift, attendance, facility/room and placement mutations all invalidate the
   staff bootstrap/roster/context path; add safe events where a path is missing.
7. **At the original B checkpoint, no live A/A1/A2 cutover or scanner readiness existed.** The
   later 2026-07-22 bounded synthetic operator proof closes only the signed-in public-HTTP
   A/A1/A2 scanner/vault, maker/checker, exact-replay and generic realtime-delivery gate on a
   caller-provisioned empty loopback database. It does not waive joint database/vault recovery,
   physical-device or checkout-operator acceptance, accessibility/privacy/regulatory review, or
   retained-database migration, activation and cutover gates.

## Bounded implementation sequence

The ten steps below are complete for source/disposable verification. They are not a retained
database cutover checklist receipt and do not authorize enabling the feature on the retained
runtime.

1. Add failing pure tests for the response schema, rule composition, verification-policy mapping,
   canonical digest vectors and time boundaries.
2. Close the secondary-policy, duplicate-lock and authority-realtime privacy defects above.
3. Add the B migration: system permission, hardened PostgreSQL projection function, safe head
   trigger, SQLite trigger and exact downgrade.
4. Add structural runtime detection, startup state and the typed pre-query 503 gate.
5. Implement a pure release-context composer and two input repositories: hardened PostgreSQL
   function output and equivalent portable SQLite/application queries.
6. Add the strict GET route and private no-store middleware coverage. Do not call
   `ensure_writable` and do not write an audit/outbox row.
7. Add generic realtime invalidation and prove cursor advancement only after canonical refresh.
8. Add the staff-app strict client, monotonic in-memory lease and read-only review panel behind the
   B preparation feature gate.
9. Run the complete portable, real PostgreSQL, admin frontend and mobile gates below.
10. Update the architecture/API/schema ledgers truthfully: B source verified or blocked, retained
    database still 0028, no C checkout claim.

## Verification matrix

### Pure and portable backend

- strict request/query and response parsing, including every extra/ambiguous field;
- golden digest vectors for empty, one-rule and multi-rule sets;
- order independence across database insertion and query order;
- digest sensitivity to every included field and insensitivity to confidential excluded fields;
- exhaustive `deny`/`manager_review` x all/specific scope composition with zero, one and multiple
  authorizations;
- all four verification policies, with secondary-check fail-closed;
- missing head, expired/revoked grant, retired recipient, stale assessment and evidence expiry;
- exact start/end microsecond behavior and next-transition TTL shortening;
- 401/403/404/409/503/200-blocked semantics;
- runtime gate proves no A2 query when B is absent or partial;
- read-only database mode succeeds without writes;
- no command receipt, audit event, realtime event or notification is created by GET; and
- response/log/privacy assertions forbid family ID, contacts, evidence, grantor, directing person,
  confidential reason, consent and storage fields.

### Migration and SQLite

- fresh `0 -> A -> A1 -> A2 -> B` plus Alembic check;
- exact `A2 -> B -> A2 -> B` repeatability;
- system-role permission append/remove without changing custom roles;
- head insert and revision-update generic invalidation, exactly once each;
- sanitized authority audit bridge payload; and
- legacy attendance, contact and consent rows byte-for-byte unchanged.

### Real disposable PostgreSQL

- use a guarded disposable high port only; protected 5432/5433/5434 are never contacted;
- function is exact signature, `SECURITY DEFINER`, fixed search path, non-runtime owner, no PUBLIC
  execute and exact runtime execute;
- A2 tables retain forced RLS and exact grants; educator direct SELECT cannot expose rows;
- forged tenant, actor, child, facility, shift and room scope fail closed inside the function;
- owner/admin organization-wide scope still requires exact open facility shift;
- runtime identity/startup accepts complete B and rejects every partial hardening mutation;
- concurrent GET vs authorization revoke, rule create/revoke, person replace/retire and evidence
  terminal transition yields a coherent before-or-after result, never mixed rows/digest;
- concurrent GET vs shift clock-out, attendance checkout and room unassignment never creates a
  durable authorization claim and the next canonical read is blocked;
- generic realtime event has null entity ID and the exact safe payload; and
- full upgrade/downgrade proof tears the disposable cluster down afterward.

### Administrator frontend

- A2 family workspace remains owner/admin-only and functionally unchanged;
- no educator response type is reused by the admin workspace;
- authority mutations cause only generic educator-safe realtime invalidation;
- no confidential reason/evidence enters realtime, notification, command journal or browser URL;
- complete tests, TypeScript check and production build remain green.

### Staff mobile

- strict parser rejects missing/extra IDs, malformed times/hashes, duplicate recipients,
  out-of-order/unknown enums and mismatched tenant/facility/child bindings;
- API uses the exact organization header and never falls back to safety-card legacy pickup flags;
- monotonic lease subtracts round-trip time and expires at the earlier server boundary;
- background, logout, organization/facility/room/shift change, socket reset and every organization event clear
  memory immediately;
- context never reaches SecureStore/AsyncStorage, queued operations, logs or push content;
- cursor persists only after successful canonical refresh;
- blocked and absent-recipient UX has no confidential detail and directs staff to a manager;
- offline/malformed/stale state disables the panel;
- no B component invokes `/attendance/check-out` or claims verified release; and
- unit/component tests, TypeScript check, Expo export/build and physical Android walkthrough pass.

## Source verification record

The 2026-07-18 B closeout passed 84/84 portable backend tests covering the strict API, pure
composer/repository behavior and migration/runtime boundary. A real disposable PostgreSQL run on
an unprotected high port passed 7/7 tests, including the complete detector, detector rejection
after a hardening revoke, restoration, the operational gate matrix, a 400-transition
non-overlapping shift/attendance race, hardened projection access and exact migration behavior.
The disposable cluster was torn down; protected ports 5432, 5433 and 5434 were untouched.
The complete portable/default backend regression passed 648 tests with 81 explicitly opt-in
PostgreSQL/backup tests skipped and zero failures.

The administrator regression remained green at 81 test files / 501 tests, TypeScript and the
production build. The staff app passed 153/153 tests, TypeScript and an Android export transforming
744 modules. B keeps its canonical response in memory behind the monotonic expiry lease, clears it
on every organization event and lifecycle change, and presents only the read-only review panel.

The later synthetic-only signed-in operator run exercised production multipart upload and real
ClamAV, attested maker-review rejection without a write, independent checker review, clean private
download, reviewed authorization plus exact replay, the administrative summary, and the canonical
PII-free `child_authority_head` invalidation through a signed-in realtime ticket/WebSocket replay.
Its private mode-0600, no-clobber redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
This validates the generic invalidation plumbing observed by that bounded A/A1/A2 flow. It does
not turn B into an authorization token, exercise B eligibility or the C/D checkout command, or
substitute for physical-device/checkout-operator, accessibility, privacy or Alberta regulatory
acceptance.

A later synthetic exact-0029D joint recovery-consistency receipt independently binds and restores
one fixed database/evidence-vault artifact set. It reports 90 tables / 61 rows and one evidence
object, with SHA-256
`da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a` for
`family-authority-joint-recovery-20260722T172958Z.json`. That is infrastructure evidence only: it
does not make B an authorization token, prove writer-frozen authoritative capture, enable a route,
activate a facility or authorize retained cutover.

The retained database remains at `0028_childcare_command_spine`; no 0029 migration or cutover is
claimed. After this original B closeout, the host gained a hardened synthetic-only ClamAV adapter
receipt, the bounded signed-in A/A1/A2 operator receipt above, and an additive C/D source boundary
with an atomic normal verified-release writer, immutable snapshot bundle, exact replay and
activated-facility legacy closure. Those later proofs are documented in
`FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`, `CUTOVER_BACKUP_RESTORE_RUNBOOK.md` and
`FAMILY_RELEASE_CHECKOUT_ARCHITECTURE.md`; they do not make B an authorization token and do not
constitute facility activation, physical checkout acceptance or retained cutover.

## Explicit B/C boundary

0029B ends after an expiring read projection. It deliberately has no:

- release POST/PUT/PATCH/DELETE route;
- client operation ID or childcare command receipt;
- recipient selection commit;
- identity verification input/result;
- attendance event or interval mutation;
- `attendance_release_snapshots` INSERT grant;
- software approval, exception or override;
- offline authorization; or
- closure of the legacy attendance-only checkout bypass.

0029C must introduce one atomic normal-release command that locks and revalidates active
membership/permission, exact facility shift, room scope, child/open interval, recipient/current
person version, authorization/evidence, current authority revision, complete restriction digest
and verification method. It must create the checkout event, close the interval, insert the immutable
release snapshot, audit/outbox signal and exact command receipt in one transaction or do none of
them. It must also disable every legacy checkout path when the C runtime gate is active and prove
response-loss reconciliation against the exact immutable receipt.

The B response may be submitted back to C only as optimistic expected identifiers/revision/digest.
C never trusts its eligibility, time, name, relationship, method list or expiry and never treats it
as a signed or bearer authorization token.

# CareSync normal verified child release — 0029C/D architecture

## Status and boundary

`0029C_verified_release_checkout` is the portable foundation after the read-only 0029B release
context; `0029D_release_checkout_writer` is its restricted PostgreSQL normal-release writer,
runtime-readiness and least-privilege boundary. The complete sequence and
revision 0035's explicit activation writer are installed in the retained
`0038_public_job_catalog_outbox` schema. They remain operationally inactive
because the retained facility-activation table is empty; installation alone
never authorizes verified release. The 0038 public-job replay release is an
unrelated public-safe projection and grants no family-release authority; the
next 0039 admissions slice likewise cannot activate this workflow implicitly.

0029C/D implement one normal child-release workflow. They do not implement an override, an offline
authorization, a manager exception, or legal interpretation. If the normal workflow cannot prove
the current release conditions, the child stays checked in and staff contact a manager.

## Frozen product decisions

- A fresh 0029B context is preparation data, not an authorization token.
- The final command independently recomputes current conditions at a database-owned decision time.
- `requested_at` is copied from the server-authored 0029B `evaluated_at` instant. The device clock
  never supplies it; it binds exact intent and freshness but never decides eligibility or the
  checkout timestamp.
- Staff choose one person from a fresh, unambiguous recipient list. Two different records with the
  same visible name, preferred name and relationship block selection until an administrator fixes
  the records.
- Recipient names and relationships in the immutable result are always copied from the current
  server record. The client cannot submit them.
- Normal verification supports two concrete method/result pairs:
  - `government_photo_id` / `verified`;
  - `documented_familiarity` / `documented_familiarity`.
- `government_photo_id_or_documented_familiarity` permits either pair.
- `government_photo_id_and_secondary_check` remains unavailable until a real secondary-check data
  model exists. It is never represented by a generic checkbox.
- Verified-release attendance intervals cannot initially be reopened or shortened through ordinary
  attendance correction. A future correction model must preserve separate compensating evidence.

## Command contract

The source route is registered as:

```text
POST /api/v1/attendance/release-check-out
```

Runtime availability is exact and per facility: C/D schema and grants must pass structural
attestation and the facility must have the immutable activation row. The current retained release
therefore keeps the route unavailable for every unactivated facility. PostgreSQL writing occurs only through D's restricted command callable;
the ordinary runtime role receives no general snapshot or attendance-table DML.

The strict `release-checkout-command-v1` intent contains only:

- client operation ID and UTC `requested_at`;
- child and facility IDs;
- expected room, attendance day, attendance interval and staff shift IDs;
- selected recipient person and current person-version IDs;
- selected authorization ID and version;
- expected authority revision, restriction digest and `release-context-v1` decision policy;
- one valid verification method/result pair.

It contains no name, relationship, contact, document, evidence identifier, free-text note, checkout
time or manager decision. Unknown fields are rejected.

The strict `release-checkout-v1` success envelope contains:

- an immutable release resource with the exact organization, facility, room, child, attendance,
  shift, actor, recipient, authorization, verification, revision, digest and operation facts;
- server-derived display name and relationship;
- database-owned checkout and commit timestamps;
- the purpose-bound request hash;
- one exact command receipt targeting the release resource; and
- `replayed`, which distinguishes the first response from an exact historical retry.

The public response omits family ID, evidence IDs, evidence content, contact information and
internal review details. Every response is private and non-cacheable.

## Exact retry behavior

The operation ID is serialized before current release conditions are evaluated.

- Same operation and byte-equivalent canonical intent returns the original immutable release and
  receipt, even if a later authority or shift change occurred.
- Same operation with any changed intent returns a bounded conflict.
- If the client cannot determine the outcome, it retains one encrypted, identity-bound pending
  operation and locks further release-changing actions until the exact result is reconciled.
- Roster state alone never proves that this operation released the child.

## Database transaction

One transaction performs the complete release or none of it:

1. Serialize the operation and resolve an exact historical retry first.
2. Confirm active user, organization, membership, role and both `attendance:record` and the new
   `release:checkout` permission.
3. Lock family, child and current authority revision in the shared project lock order.
4. Confirm the active facility and its release-checkout activation record.
5. Confirm one exact open staff shift at that facility for every role.
6. Confirm active enrollment, room and room assignment unless the role is organization-wide.
7. Lock the exact attendance day and one open attendance interval.
8. Lock the selected current person version, authorization, reviewed evidence and current release
   rules in canonical order.
9. Capture one database decision instant after blocking locks and recompute the normal release
   decision, rule digest and verification-policy match.
10. Apply existing care-time completion rules using the server checkout instant.
11. Create the checkout event, close the interval, increment the attendance-day version, insert the
    immutable release snapshot, command receipt, private audit entry and generic realtime update.
12. Commit once.

The immutable snapshot records the exact actor membership/role, staff shift, room scope basis,
room assignment when applicable, verification policy/method/result, recipient person version,
authorization version, authority revision and decision-time digests.

## Facility activation and legacy behavior

0029C introduces an immutable per-facility activation row. Merely having the migration installed
does not activate the workflow.

For an activated facility:

- new calls to the old attendance-only checkout route are refused with a typed product response;
- an already-committed historical operation can still return its original result;
- ordinary attendance correction cannot close an open interval or rewrite an interval that has an
  immutable release record;
- older clients fail closed instead of silently using attendance-only checkout; and
- both administrator and educator roles still require the exact open facility shift.

Facilities without an activation row remain explicitly legacy attendance-only during source
development and must never be labelled as verified release.

Revision `0035_release_checkout_activation` adds the explicit cutover control without activating
any facility during migration. An authenticated owner or administrator must open the exact
facility's Settings page and review the server-computed readiness checklist. Activation is
available only when the database is writable, the restricted checkout writer is available, the
organization and facility are active, the actor is still privileged, and every active or paused
enrollment has one current authorization whose verification policy the normal checkout path can
execute. The operator must affirm all four consequences and type
`ACTIVATE VERIFIED RELEASE CHECKOUT`.

The command is scoped to one organization and facility and carries a client operation ID. The
database rechecks membership, facility state and authority coverage inside the write transaction,
then inserts one immutable activation record through a security-definer function with a fixed
search path. An uncertain response can only be retried with the exact same operation and intent;
that retry returns the original receipt. There is deliberately no deactivation, override, bulk
activation or automatic activation path. Legacy attendance checkout closes only after this
immutable activation exists.

## Isolated staff-app flow

The staff flow is:

```text
fresh evaluation
→ select an unambiguous recipient
→ choose an allowed verification method
→ confirm the completed identity check
→ review the final summary
→ submit the normal release
→ receive or reconcile the exact immutable result
```

Any organization realtime event, connection loss, app backgrounding, facility/room/shift change,
lease expiry or refreshed context clears the selection. The flow is online-only. The protected
pending operation contains opaque IDs, revisions, digests, timestamps and the verification pair;
it contains no name, relationship, evidence or legal text and has no volatile-memory fallback.

The controller, panel, client and protected pending-operation store are imported by
`LiveStaffScreen` behind the exact authenticated per-facility capability. An unavailable,
incomplete or ineligible facility fails closed and never falls back to the legacy close.

Context GET and submit/reconcile 401/403 responses revoke only the still-current identity, token,
membership and organization boundary that made the request; a stale response cannot revoke a
replacement session. Realtime, background, connection, token and scope changes invalidate the
lease and choices immediately. Submit/reconcile renders progress synchronously, is single-flight,
locks dismissal and preserves an ambiguous exact pending operation. Event-handler failures cannot
undo a confirmed immutable receipt.

## Implementation status

1. Strict Python and TypeScript contracts, canonical request hashing and the verification matrix
   are complete.
2. The dormant `0029C_verified_release_checkout` migration, immutable activation model and expanded
   snapshot facts are complete in source.
3. Structural C/D detection, runtime readiness and least-privilege bootstrap are implemented and
   fail closed on partial shape or grant drift.
4. The portable SQLite atomic path and restricted PostgreSQL D writer passed their separate source
   and disposable-database acceptance matrices.
5. Activated-facility legacy checkout and correction closure is implemented in source. No retained
   facility is activated.
6. The staff confirmation flow is live-wired behind the exact server capability and protects
   current session identity plus recoverable pending operations.
7. Full backend, focused integrated C/B/D, administrator and staff-app source gates passed. A fresh
   disposable PostgreSQL 17 D gate passed 2/2 destructive proof cases.
8. The bounded synthetic signed-in A/A1/A2 operator review is recorded separately with a private
   receipt. It did not execute `/attendance/release-check-out`; C/D physical checkout-operator
   review and accessibility/privacy/regulatory acceptance remain mandatory. The
   later guarded 0036–0039 retained migrations and cutovers are separate
   evidence; they created no facility activation.
9. A separate synthetic exact-0029D four-artifact recovery-consistency run passed and retained a
   private joint receipt. It proves the fixed artifacts restore consistently, not that their source
   was complete, authoritative or writer-frozen.

## Required consistency tests

The portable database suite covers both commit orders for release versus authorization change, rule
change, person-version change, evidence state change, shift close, membership/permission change,
room unassignment, facility/room deactivation, attendance correction and a second checkout.
Every result is required to be either one complete release bundle or a bounded no-write outcome.
Exact retry, changed-intent reuse, response loss and failure between each write stage are also
covered. The disposable PostgreSQL D matrix proves atomic commit/rollback, exact replay,
activated legacy closure, ACL/readiness tamper rejection and populated downgrade refusal.

## Portable source verification evidence

The final commands below are recorded independently and their test counts must not be added:

- full default backend: 798 passed, 81 expected explicit opt-in PostgreSQL skips, zero failures and
  7 warnings;
- focused integrated C/B/backend matrix: 234 passed;
- post-run dormant ACL/bootstrap verification: 17 passed, rerun because its final source adjustment
  occurred while the full default suite was running;
- administrator: TypeScript, 501/501 tests and the production build of 834 modules passed; and
- staff app: TypeScript and 181/181 tests passed.

The 81 skipped tests were not executed PostgreSQL evidence. The warnings are recorded without being
treated as certification. These are historical C portable counts. The later D closeout passed
86/86 checkout service/API/error/mutation/adapter tests, 98/98 combined readiness/bootstrap/
adapter/context-detector tests, 12/12 structural tests, Ruff and 2/2 fresh disposable PostgreSQL
17 proof cases. The latest mobile hardening passes 263/263 plus TypeScript. The separate bounded
synthetic A/A1/A2 signed-in operator run passed maker/checker, scanner/vault, exact-replay, generic
realtime and administrative-summary cases; its private receipt and hash are recorded in
`FAMILY_AUTHORITY_ARCHITECTURE.md`. That run did not execute the C/D release-checkout command.
The later synthetic joint recovery-consistency run matched 90 tables / 61 rows and one evidence
object; its private receipt
`family-authority-joint-recovery-20260722T172958Z.json` has SHA-256
`da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a` and explicitly denies
writer quiescence, authoritative completeness/same-snapshot capture and every
release/cutover authority. The later guarded retained cutovers supply their own
database/vault evidence, but physical-device and checkout-operator evidence,
facility activation and production certification remain open. Software
override remains deferred.

No source test or migration proof is permission to activate a real facility.

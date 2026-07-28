# CareSync Product Slice 0041 Source Release Note

Last updated: 2026-07-23

## Classification

Product slice: `0041_live_room_presence_and_safety_board`  
Alembic revision: `0041_live_room_presence`  
Status: **verified source; retained cutover not performed**  
Checked-in source head: `0042_billing_policy_recert`  
Retained PostgreSQL 17 head on port 5434: `0039_admissions_decision_spine`

This is source and disposable-database release evidence. It is not a local
cutover record. The retained database on port 5434 was not migrated, restarted
or used for destructive acceptance. Historical retained release evidence in
`LOCAL_RELEASE_0039_CUTOVER.md` remains authoritative.

## Delivered

0041 adds the missing actual-room fact for an on-duty staff member and uses it
to connect staff clock truth, child attendance, rooms and configured
operational staffing targets. It adds:

- server-authored staff room-presence start, move, end, clock-out and
  access-revocation transitions;
- exact-retry operation receipts and immutable room-presence event history;
- fail-closed child-operation gating when the actor has no coherent current
  room presence;
- terminal cleanup paths that remain available when stale or invalid source
  facts must be closed;
- administrator room boards and a bounded current-room staff projection;
- explicit `unknown`, attention and configured-target states;
- append-only operational exception episodes and acknowledgements;
- tenant-scoped realtime invalidation and generic notifications;
- strict administrator and Staff app response parsing; and
- one-time release reconciliation without inventing historical room presence.

The migration adds exactly four tenant tables:

- `staff_room_presence_sessions`;
- `staff_room_presence_events`;
- `room_operational_exception_heads`; and
- `room_operational_exception_events`.

The migration does not rewrite attendance, staff shifts, schedules, room
assignments, coverage targets, enrollments, children or existing billing facts.

## Safety boundary

0041 reports factual operational configured-target evidence. It does not
calculate or certify Alberta ratios, staff qualifications, licensed capacity,
group size, supervision adequacy or regulatory compliance. Planned shifts,
actual clock records, room-access grants, room-presence intervals and child
attendance remain distinct sources of truth.

Missing, future-dated, invalid-timezone, crossed-facility, crossed-room or
otherwise incoherent source facts fail visibly. Acknowledgement records only
that an authorized person is reviewing a signal; it is not approval, waiver,
resolution or compliance certification.

## Disposable migration and data-preservation proof

The populated disposable PostgreSQL 17 clone began at retained-equivalent
revision 0039 with 140 pre-0041 business tables and 16,508 rows. Its exact
source identities were:

- count digest:
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`;
- row digest:
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`;
- logical backup:
  `/Volumes/T7/.caresync-tmp/0041-proof/populated-0039-pre0041.dump`; and
- backup SHA-256:
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`.

All pre-0041 table counts and both digests remained exact through the
`0041 -> 0039 -> 0042` migration sequence and the later
`0042 -> 0041 -> 0042` recertification round trip. The four 0041 tables
remained empty in the preservation proof, and the restricted runtime identity
passed after the final 0042 promotion. The backup SHA-256 remained unchanged.

The retained port-5434 database stayed at 0039 throughout this work.

## Verification

| Gate | Result |
|---|---|
| Backend complete source sweep | All 135 test files passed using the memory-safe one-file sweep |
| Focused 0041/0042 backend matrix | 45 passed, 1 explicit opt-in case skipped |
| Fresh PostgreSQL 17 0041 boundary | 1 passed |
| Source-head runtime grant and backup checks | 39 passed |
| Billing runtime-certificate checks | 8 passed |
| Ruff and Python bytecode compilation | Passed |
| Administrator focused regression | 22 files, 193 tests passed |
| Administrator TypeScript and production build | Passed |
| Staff app regression | 297 tests passed |
| Staff TypeScript | Passed |
| Expo Doctor | 20/20 |
| Android export | Passed; 782 modules |
| Android HBC bundle SHA-256 | `a3667d6da9e033c3a28fec98cf2e9edf4f5ffed51fbeefc0a2bb2c3769aec0fe` |
| Signed-in administrator walkthrough | Pending |
| Physical Android walkthrough | Pending |
| Retained 5434 migration/cutover | **Not performed** |

The PostgreSQL proof covers exact migration and downgrade behavior, forced RLS,
least grants, immutable event ledgers, command-bundle guards, exact retry,
cross-tenant rejection, room/facility integrity, access loss and safe terminal
cleanup. Client evidence covers strict contracts, target-zero handling,
unknown-source handling, realtime refresh, stale states and protected command
recovery.

## Acceptance still required

Before retained promotion, an authorized operator must:

1. preserve and reopen-verify a permission-safe retained backup and all required
   evidence bundles under the guarded cutover procedure;
2. migrate a fresh exact restore to the checked-in 0042 source head and repeat
   the complete runtime certificate;
3. complete the signed-in administrator room-board walkthrough;
4. complete the physical Android clock-in, room-select, move, child-operation
   gate and clock-out walkthrough;
5. record accessibility, privacy and operator observations; and
6. separately authorize the retained migration.

No retained migration is implied by this source release note.

## Architecture

The normative design and product-language boundary is
[`LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md`](LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md).

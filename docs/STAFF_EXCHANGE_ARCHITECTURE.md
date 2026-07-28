# CareSync Staff Exchange and Recurring Rota Architecture

Last updated: 2026-07-17

## Status

Revision `0027_staff_exchange` is released locally. The source and isolated live-local database
both report Alembic head `0027_staff_exchange`; the backup-first cutover and the release gates in
this document are recorded below.

This phase adds recurring rota patterns, open shifts, manager offers, substitute opt-in and
whole-shift swaps. It extends the existing planned rota. It does not merge planned assignments,
actual clock evidence or child attendance.

## Product truth hierarchy

1. A rotation pattern is a reusable planning source, not a staff assignment.
2. A generated rotation occurrence is an ordinary draft scheduled shift.
3. An open-shift posting is an opportunity, not a staff assignment.
4. Staff interest asks a manager to consider the educator; it does not reserve or assign work.
5. A targeted manager offer is still not an assignment until the educator explicitly accepts.
6. Offer acceptance atomically fills the posting and creates one published, acknowledged
   scheduled shift.
7. Substitute opt-in permits proactive offers but does not guarantee work or expose another
   educator's identity, health information, leave category or leave reason.
8. Peer swap consent moves a request to manager review. It never changes a schedule by itself.
9. Manager swap approval atomically cancels the original assignment or assignments and creates
   acknowledged replacements. Partial completion is forbidden.
10. Server-recorded clock events remain the only evidence that work occurred.

## Persistence boundary

The additive migration introduces five current projections:

- `staff_rotation_patterns` — a named, versioned facility-local rotation with validated JSON
  slots and a `draft -> active -> retired` lifecycle;
- `staff_open_shifts` — a draft, posted, filled or cancelled coverage opportunity;
- `staff_open_shift_engagements` — staff interests and manager offers with kind-specific
  lifecycles;
- `staff_substitute_profiles` — staff-owned facility opt-in for proactive coverage offers; and
- `staff_shift_swap_requests` — a whole-shift cover or reciprocal trade request.

The existing append-only `staff_workforce_events` ledger is expanded for exact operation
receipts. Runtime `DELETE` remains unavailable. Current records use terminal states or
tombstones. All new tables require forced tenant RLS, one organization policy and least grants.

The supported downgrade intentionally purges `0027` exchange projections and their `0027` event
receipts because `0026` cannot represent those records. It preserves the legacy workforce event
history and restores forced RLS. This destructive downgrade behavior is for disposable migration
verification, not a production rollback substitute; release recovery remains backup-first.

`staff_scheduled_shifts` receives nullable provenance:

- `origin_type` in `rotation`, `open_shift` or `swap`;
- `origin_id` for the source projection;
- `origin_occurrence_key`, unique within that source; and
- `supersedes_schedule_id` for an open-shift replacement or swap replacement.

The three origin fields are all null or all non-null. Existing null provenance means a manual or
pre-`0027` assignment. A rotation occurrence cannot supersede another schedule. Swap replacements
must supersede one source schedule. One source schedule cannot be superseded twice.

## Recurring rotations

Rotation slots contain a stable slot UUID, cycle-week index, weekday, staff membership, optional
room, local start/end time and optional note. The pattern anchor is a facility-local Monday;
cycle length is bounded. Overnight slots and intra-pattern overlap for one educator are invalid.

- Draft patterns may be edited.
- Activation validates the complete immutable snapshot, active assignment scope and facility
  timezone.
- Active patterns cannot be edited; a later change is represented by a new draft/version.
- Retirement prevents new generation but preserves history and schedule provenance.
- Preview is bounded and returns every candidate occurrence plus an explicit readiness/conflict
  reason and a deterministic snapshot digest.
- Generation requires the preview digest, revalidates the complete snapshot and is all-or-none.
- A stale digest returns `409 preview_stale`; overlap, approved leave, inactive assignment, room
  scope and DST failures write nothing.
- Successful generation creates ordinary drafts only. Publishing remains an explicit rota action.
- Exact generation retry is resolved from the immutable event receipt before mutable pattern or
  conflict state is consulted.

## Open shifts and offers

Manager flow:

```text
draft --post--> open --accepted offer--> filled
  |                |
  +--cancel--------+--cancel
```

An optional source schedule marks replacement coverage. Filling that posting cancels the source
and creates its acknowledged replacement in the same transaction. A posting cannot be filled
twice.

Engagements are either:

- `interest`: interested, withdrawn, offered or not-selected; or
- `offer`: offered, accepted, declined, withdrawn or expired.

Staff can express or withdraw interest in an eligible open posting. Managers may send a targeted
offer directly or from an interest. Interest never assigns work. Offer acceptance locks the
posting, engagement, staff rota lane, source schedule when present and relevant leave constraints.
It then creates one published and acknowledged scheduled shift, records provenance, marks the
post filled and terminalizes every competing pending engagement atomically.

Approved leave is always a hard blocker. An educator may explicitly accept an opportunity outside
their recurring availability; the durable schedule records that staff-authored exception without
presenting it as a manager override.

## Substitute pool

Each staff member controls a facility-scoped opt-in projection. The manager discovery list shows
only active, assigned staff who opted in and only operational eligibility required to make an
offer. It must not disclose other staff leave details or private notes. Resetting the preference
uses a tombstone rather than row deletion.

## Whole-shift swaps

Supported requests are a one-way cover request or a reciprocal trade between two future published
shifts. Partial interval trades remain later work.

```text
pending_counterparty --accept--> pending_manager --approve--> approved
        |                              |
        +--decline/cancel/expire       +--reject/cancel/expire
```

Creation snapshots the exact original schedule identifiers and versions. Counterparty acceptance
confirms the exact proposal only. Manager approval rechecks source versions, actual-clock links,
active assignment, facility/room scope, approved leave and overlap under deterministic rota locks.
Approval performs cancel-and-replace with stable derived operation identifiers and returns every
original and replacement identifier in one immutable receipt. No write survives if any part
fails.

## API and client boundaries

- Manager routes live under `/api/v1/staff-exchange` and require staff-management permission.
- Educator routes live under `/api/v1/staff/self/exchange`, require a complete staff identity and
  fixed shift permission, and expose only the authenticated membership's records.
- Every list is date/facility bounded and server-authors `can_*` capabilities.
- Clients strictly validate tenant, facility, lifecycle, provenance and exact receipt fields.
- Realtime is invalidation-only; canonical REST refresh completes before cursor advancement.
- Notification payloads are generic until the authenticated notification ledger is opened.
- Admin mutation dialogs freeze meaning-changing fields after an ambiguous outcome.
- Mobile persists one encrypted, identity-scoped exchange command before sending and prevents a
  second unresolved rota mutation across clock, schedule-response, workforce and exchange stores.
- Network/408/425/429/5xx keeps exact intent; 401/403 keeps intent and reauthorizes; definitive
  409/422 clears only after canonical refresh.

### Canonical exchange contract

The released `0027` clients and server use the persistence/consent names below. Aliases such as
`source_schedule_id` and `target_schedule_id` are deliberately not accepted because they obscure
which educator consented to which assignment.

- Rotation responses include a positive server-assigned `version` and nullable
  `retirement_reason`. The reason is null for draft/active patterns and nonblank for retired
  patterns. A rotation slot is normalized to a membership while also returning the staff user
  identity needed by the manager UI.
- Swap creation sends `kind`, `requester_schedule_id`, `counterparty_membership_id`, nullable
  `counterparty_schedule_id`, and the requester's nullable `note`, alongside the operation id.
- `cover` requires a null counterparty schedule. `trade` requires a counterparty schedule owned by
  the selected counterparty and in the same facility.
- Swap responses include `requester_schedule` and nullable `counterparty_schedule` safe summaries,
  plus `counterparty_response_note`, `manager_decision_reason`, and `cancellation_reason` as
  distinct evidence. They must never be collapsed into one mutable decision note.
- An approved cover has `requester_replacement_schedule_id` only. An approved trade has both
  `requester_replacement_schedule_id` and `counterparty_replacement_schedule_id`. No replacement
  identifier exists before approval or after a terminal non-approved decision.
- Swap-candidate rows carry a stable `candidate_key`, `kind`, counterparty identity, nullable
  counterparty schedule summary, eligibility reasons and server-authored `can_propose`. Cover
  discovery cannot require the counterparty to already have a shift.
- Manager substitute discovery is privacy-safe: it returns identity, facility, opt-in and
  operational eligibility only. A staff-owned substitute note and all leave details are omitted.
- Manager approval/rejection returns the complete strict swap projection. Exact operation id,
  terminal state, reason and replacement cardinality form the client acknowledgement.

## Release acceptance gates

- Migration `0026 -> 0027 -> 0026 -> 0027` on fresh SQLite and PostgreSQL 17.
- Forced RLS, one tenant policy, least mutable grants and append-only ledger grants.
- Exact retry, changed-intent operation reuse and superseded receipt tests for every mutation.
- Concurrent double offer acceptance proves exactly one filled post and one schedule.
- Source replacement acceptance proves cancel-and-create atomicity in both race orders.
- Rotation preview digest, DST, overlap, leave, inactive scope and all-or-none generation tests.
- Interest never creates a schedule; accepting an offer creates published+acknowledged provenance.
- Competing interests/offers terminalize consistently after fill.
- Substitute discovery proves opt-in, assignment and privacy boundaries.
- Swap peer response and manager approval tests prove no early reassignment and all-or-none
  cancel-and-replace, including concurrent source mutation.
- Strict admin/mobile parser, exact-retry lock, realtime recovery and notification routing tests.
- Full backend, admin, staff-app, Expo Doctor, production build/export and signed-in responsive
  browser gates.
- Verified live backup and recorded live migration/head/grants/counts before the phase is called
  released locally. Physical operator/device acceptance remains a separate production gate.

## Recorded local release evidence

- The pre-cutover live head was `0026_staff_workforce`. The verified backup is
  `backend/backups/caresync-postgres-20260717-013825.json.gz`; the manifest is
  `backend/backups/caresync-postgres-20260717-013825.json.manifest.json`. The gzip contains 1,665
  rows across 66 tables in 1,666 JSON-lines. Its compressed SHA-256 is
  `230aa2265e2b8298e43992547256c99ee1bd0b9e010ae805f2d984a0d0f7df00`; the uncompressed
  JSON-lines SHA-256 is
  `3a37e26517b8f1b6fd9214ea74a02035f7bd8ad6eb598202404d573e726be203`. Gzip integrity and
  owner-only file permissions were verified before migration.
- Fresh PostgreSQL 17.8 verification passed all 8/8 exchange migration, RLS, realtime and race
  checks before downgrade, the restricted non-superuser/NOBYPASSRLS migration-owner downgrade
  check passed 1/1, and the re-upgraded head passed the same 8/8 checks again. The isolated test
  cluster was stopped without touching the retained live PostgreSQL runtime.
- The full backend suite passed 332 tests with 26 expected opt-in PostgreSQL skips, and full Ruff
  passed. The administrator client passed 337/337 tests across 62 files and its production build
  completed at 817 modules. The staff app passed 134/134 tests and TypeScript, Expo Doctor 20/20,
  and Android export at 739 modules.
- The live migration preserved users 2, organizations 1, memberships 2, facilities 1, rooms 5,
  families 110, children 203, ATS applications 1 and actual staff shifts 2. Scheduled shifts
  remained 0. Public tables increased additively from 66 to 71; all five exchange projections
  began at 0.
- All five exchange tables and `staff_workforce_events` have RLS enabled and forced with one
  organization policy each. The exchange projections grant the runtime role
  SELECT/INSERT/UPDATE but not DELETE; the immutable workforce ledger grants SELECT/INSERT but
  not UPDATE/DELETE.
- Live schema inspection verified `ix_staff_shift_swaps_requester_sched`,
  `ix_staff_shift_swaps_counterparty_sched`, `uq_scheduled_shifts_origin_occurrence` and
  `uq_scheduled_shifts_supersedes`, together with the nullable scheduled-shift provenance
  columns.
- The live OpenAPI exposes 31 staff-exchange paths and 35 operations. Unauthenticated manager and
  educator reads both returned 401. API health and the administrator frontend returned 200, and
  signed-in browser smoke rendered the authenticated Staff rota, Staff Exchange workspace,
  rotation controls and the expected empty live-local exchange states. Open coverage, substitute
  pool and peer-swap tabs were exercised without mutation; the 390 px layout had no horizontal
  overflow, and the browser console reported zero warnings or errors.

## Non-blocking scale hardening

The released local slice has no unresolved code-level release blocker. Before a large production
tenant, add cursor pagination and relation prefetching to high-cardinality rotation and educator
open-history reads, then load-test the 500-pattern/slot ceiling. Move terminal competing-offer
fanout to a durable outbox with bounded batches, narrow organization-wide advisory lanes to the
affected resource, and consider deferred constraint triggers for the remaining cross-row
provenance rules that are currently enforced transactionally by the application.

## Deliberately later

- partial-shift trades, split shifts and multi-party exchanges;
- automatic award or bidding algorithms;
- leave balances and employment-rule evaluation;
- regulatory ratio or qualification certification;
- payroll/timesheet approval and labor-cost optimization;
- calendar synchronization and closed-loop emergency escalation; and
- production geofencing or location evidence.

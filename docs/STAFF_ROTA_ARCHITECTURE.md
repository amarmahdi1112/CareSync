# CareSync Daily Staff Rota and Clock Reconciliation

Last updated: 2026-07-16

## Implementation status

The daily-rota vertical slice is implemented across the FastAPI backend, the
administrator portal and the Expo staff app. Migrations `0025_staff_rota` and
`0026_staff_workforce` are applied to the isolated local PostgreSQL 17
development database; the live head is `0026_staff_workforce`. This document
describes the implemented rota boundary. The additive workforce slice supplies
availability, time off, reusable templates and operational coverage targets
without changing the planned-versus-actual separation below. Payroll and
regulatory ratio scheduling remain later work.

The administrator portal now provides a facility-aware weekly planner, draft
creation and editing, publication, cancellation with a reason, alternate-time
approval/rejection and a planned-versus-actual monitor. The staff app provides
facility-local Today, Upcoming and History views, accept/decline/propose-
alternate actions, cancellation and clock reconciliation detail, and an
explicit scheduled-shift clock-in action. Existing ad-hoc clocking remains
available and is labelled as unscheduled in reconciliation.

## Product boundary

This slice introduces a planned staff rota without weakening the existing server-timestamped
clock ledger. A planned shift is an assignment. An actual shift is evidence of work. They are
stored separately and linked only when the educator deliberately clocks into the published
assignment.

Existing location-free ad-hoc clock-in remains supported. An actual shift without a planned
shift is displayed truthfully as `unscheduled`; it is not hidden or retroactively rewritten.
Location is not collected by this slice.

## Data architecture

- `staff_scheduled_shifts` stores the current planned interval and lifecycle projection.
- `staff_scheduled_shift_events` is the immutable idempotency and decision ledger.
- `staff_shifts` remains the server-authored actual clock record and gains an optional,
  one-to-one `scheduled_shift_id` link.
- `staff_shift_events` remains the immutable clock-in/clock-out receipt ledger.

Migration `0026_staff_workforce` adds adjacent planning projections and an
append-only workforce event ledger. It also adds
`staff_scheduled_shifts.availability_override_reason`; it does not merge leave,
availability or templates into the actual clock ledger. See
`docs/WORKFORCE_PLANNING_ARCHITECTURE.md` for that contract.

Migration `0025_staff_rota` is additive for the live records: existing actual shifts and clock
events are preserved, their new planned-shift link starts null, and reconciliation therefore
reports them honestly as unscheduled. The migration does not guess or backfill a historical rota.
Downgrade testing belongs on disposable databases; downgrading a live database after rota writes
would deliberately discard the new planned-shift tables and must not be treated as routine
rollback.

Every timestamp is an aware instant. Local date and time entry is converted with the selected
facility's IANA timezone. Day grouping is also evaluated in that facility timezone.

## Planned-shift lifecycle

```text
draft --publish--> published --cancel--> cancelled
  |                    |
  +------cancel--------+

published response:
pending --acknowledge--> acknowledged
pending --decline------> declined
pending --propose------> alternate_proposed
alternate_proposed --manager accepts--> acknowledged with revised interval
alternate_proposed --manager rejects--> pending
```

Published shifts cannot be silently edited. Draft edits require the caller's last-seen
`updated_at`; a stale update returns `409 stale_schedule`. A manager resolving an alternate
proposal must also present the last-seen timestamp. Accepting an alternate adopts the proposed
interval and acknowledges the shift; rejecting it preserves the original interval and returns
the current projection to a clean `pending` state. The rejected proposal and manager decision
remain in the immutable event/audit history rather than being exposed as a current educator note.

Publication now rechecks approved leave and declared availability while holding
the same membership schedule lane. Approved leave is a hard, cross-facility
conflict. Missing availability is unspecified and does not block; a saved empty
profile is explicitly unavailable. A mismatch may proceed only with a nonblank
manager reason persisted on the shift, operation event and audit record.

## Safety and concurrency invariants

1. Every mutation carries a caller-generated `client_operation_id`.
2. An exact retry returns the same canonical resource; reuse with changed intent returns 409.
3. Tenant/resource ownership is checked before an idempotent replay can be returned. After that
   authorization boundary, operation-ledger lookup happens before lifecycle validation so
   response-loss recovery works without disclosing another educator's shift.
4. PostgreSQL advisory locks serialize operation IDs and each educator's rota lane.
5. Overlapping non-cancelled shifts for one membership are rejected.
6. Draft reassignment locks old and new membership lanes in deterministic order.
7. A planned shift can link to at most one actual shift.
8. Scheduled clock-in requires the same active membership and facility, a published and
   acknowledged assignment, no prior actual link, and the clock-in window from two hours before
   planned start through four hours after planned end. Outside that window, the user must make
   an explicit unscheduled clock-in.
9. Omitted `scheduled_shift_id` preserves the explicit unscheduled clock workflow.
10. Staff self-service never exposes another educator's schedule or an unpublished draft.
11. Organization and user boundaries are rechecked in strict client response parsers before
    local state is changed.
12. Ambiguous mobile/admin outcomes retain and reuse the exact operation ID. They are not
    presented as successful until a canonical server response is verified.
13. The mobile app encrypts one unresolved schedule-response command in an identity-scoped
    secure-store key. Storage failure blocks sending; transport/timeout/rate-limit/server or
    malformed-response ambiguity keeps the exact command locked for retry.
14. A definitive first-response client rejection may be corrected and resubmitted with a new
    operation ID. Authentication loss never clears a possibly committed response merely to make
    the interface look clean.
15. Cancellation requires a non-blank reason and is refused after an actual clock record has
    linked to the assignment.
16. Published assignments and educator decisions create audited realtime invalidations and
    user-private notification-ledger entries. WebSocket events invalidate; REST responses remain
    canonical.
17. Staff actions remain locked until the protected pending-response store has completed its
    startup integrity check; a slow restore cannot race a new response.
18. Alternate-time receipts compare canonical instants, not textual timezone-offset formatting,
    while still rejecting any materially different interval.
19. Create, draft edit, publish and alternate acceptance revalidate the educator's active
    membership plus facility/room assignment at decision time; a stale assignment cannot be
    promoted into an active rota obligation.
20. Leave approval and schedule publication serialize on the same membership lane; exactly one
    side can commit for overlapping intervals.
21. Alternate-time acceptance cannot move a published shift into approved leave.
22. Availability changes do not rewrite an already-published assignment. The publication decision
    is evaluated against the profile committed while the schedule lane is held.

## Reconciliation projection

The server computes, rather than trusts the client to infer:

- `upcoming`: no actual record and the expected start has not exceeded the five-minute grace
  period.
- `active`: linked actual shift is currently open and was not late.
- `completed`: linked actual shift is closed and was not late.
- `late`: no linked clock-in more than five minutes after start, or the linked clock-in occurred
  after that grace period. A late result remains late after the actual shift closes.
- `missed`: the scheduled interval ended without a linked actual shift.
- `cancelled`: planned shift was cancelled.
- `unscheduled`: actual shift has no planned-shift link.

The response also exposes `minutes_late`, scheduled and actual instants, facility/room labels,
and the facility timezone. The admin portal uses those canonical fields for planned-versus-actual
monitoring. The mobile app calculates human-readable start/end variance only from these
server-authored instants; it does not invent attendance evidence from the device clock.

## API boundary

Manager operations:

- `POST /api/v1/staff-schedules`
- `PATCH /api/v1/staff-schedules/{schedule_id}` (draft only, optimistic)
- `GET /api/v1/staff-schedules`
- `POST /api/v1/staff-schedules/{schedule_id}/publish`
- `POST /api/v1/staff-schedules/{schedule_id}/cancel`
- `POST /api/v1/staff-schedules/{schedule_id}/alternate/accept`
- `POST /api/v1/staff-schedules/{schedule_id}/alternate/reject`
- `GET /api/v1/staff-schedules/reconciliation`

Educator operations:

- `GET /api/v1/staff/self/schedules`
- `POST /api/v1/staff/self/schedules/{schedule_id}/acknowledge`
- `POST /api/v1/staff/self/schedules/{schedule_id}/decline`
- `POST /api/v1/staff/self/schedules/{schedule_id}/propose-alternate`
- `POST /api/v1/staff/self/shifts/clock-in` with optional `scheduled_shift_id`
- existing `POST /api/v1/staff/self/shifts/clock-out`

Schedule lists use the strict envelope:

```json
{
  "items": [],
  "total": 0,
  "generated_at": "2026-07-16T00:00:00Z"
}
```

The admin reconciliation envelope separates `scheduled` and `unscheduled` rows and includes
their exact totals. Queries are bounded; lifetime schedule history is never returned implicitly.

Manager endpoints require the existing staff-management permission boundary. Staff-self
endpoints return only the authenticated membership's published schedules and cancellations that
were previously published; unpublished drafts and drafts cancelled before publication remain
private to managers. A service-date filter is interpreted using the selected facility's IANA
timezone. Explicit range queries require aware timestamps.

## Realtime and notifications

- Organization realtime events invalidate admin rota and clock-monitor projections.
- User-private assignment notifications route educators to `/shifts`.
- Educator response notifications route authorized managers to `/staff-rota`.
- Push payloads remain generic and PII-free; authenticated clients resolve prose from the
  notification ledger.
- Realtime is an invalidation channel. REST remains the canonical source of schedule and clock
  state.

## Client interruption and recovery behavior

- Admin create/edit/publish/cancel/proposal-resolution commands reuse their operation ID after
  network, timeout, throttling, server or protocol ambiguity.
- While an ambiguous admin form command is unresolved, fields that would change its meaning are
  locked and the operator sees an explicit exact-retry state.
- The mobile app writes the exact educator response to protected storage before sending it. A
  different shift or response type cannot replace that unresolved intent.
- A response-loss retry may succeed even when the canonical schedule already reflects the first
  attempt; local lifecycle guards do not block the exact protected retry.
- Staff shift clock operations preserve their existing protected retry behavior and include the
  planned-shift identifier on both clock-in and clock-out when the open shift is scheduled.
- If room/facility assignment is later revoked, protected child operations stay locked, but the
  employee can still close their already-open shift using its server-confirmed facility and
  planned-shift link.

## Acceptance gates for this slice

- Tenant, permission, facility, room, and educator-scope tests.
- Exact retry and changed-intent collision tests for every lifecycle action.
- Stale draft and stale proposal-resolution tests.
- Timezone-naive, invalid interval, overlong, overlap, and DST boundary tests.
- Scheduled and unscheduled clock tests, including changed-payload replay rejection.
- Late, active, completed, missed, cancelled, and unscheduled reconciliation tests.
- PostgreSQL concurrent create/link tests plus migration, RLS, and runtime-grant checks.
- Admin parser/model/page tests and production build.
- Mobile parser, protected-operation, grouping, response, clock-link, realtime, and navigation
  tests plus Expo typecheck/Doctor/export.

## Verification evidence

Verified against the source containing this slice on 2026-07-16:

| Surface | Result |
|---|---|
| Backend lint | `ruff check app tests alembic` passed |
| Backend ordinary suite | 310 passed; 17 expected opt-in PostgreSQL skips |
| PostgreSQL 17 | 11/11 focused workforce, rota and runtime-grant tests passed |
| Migration | Disposable `0025 -> 0026 -> 0025 -> 0026` passed; live head is `0026_staff_workforce` |
| Administrator portal | 57 test files / 305 tests, TypeScript and production build passed; 809 modules transformed |
| Staff app | 114 tests, TypeScript, Expo Doctor 20/20 and Android export passed at 732 modules |
| Independent exact-fix review | No blocking finding remained after clean alternate rejection, unpublished-cancelled-draft filtering, equivalent-instant receipt, closed-late reconciliation and protected-store startup-gate fixes |

The verified release backup is
`backend/backups/caresync-postgres-20260716-222537.json.gz`. Its compressed SHA-256 is
`eadee6f37b15619220ca4c9da5d3e96f50896bddbe700467b66e69af466670cd`; its uncompressed
JSON-lines SHA-256 is
`c399a0509ef7abe0b0f05d892f375a3ce82ce6c0582cd09bdbad3050df94b2ff`. The manifest records
1,644 rows across 61 tables and the stream contains 1,645 lines.

The live local-development release completed at `0026_staff_workforce`. Each of the five new
tables has RLS enabled and forced, one tenant policy and verified runtime grants. The migration
preserved users 2, organizations 1, memberships 2, facilities 1, rooms 5, families 110, children
203, ATS applications 1 and actual staff shifts 2. Scheduled shifts and all five new workforce
tables start at 0, so no historical plan or workforce projection was fabricated.

API health returned 200, the complete workforce route set is registered, the unauthenticated
availability boundary returned 401, the administrator portal returned 200 and Metro remained
running. Signed-in browser verification covered all four workforce tabs and the template dialog;
the 390 px viewport had no horizontal overflow and browser diagnostics contained zero warnings
or errors. Physical-device/operator rota and workforce acceptance remains a separate release
step.

## Live release checklist

The release operator must complete these steps in order. Automated success does not waive the
last physical/operator acceptance steps.

Status at the 2026-07-16 handoff: steps 1 through 7 are complete for the live `0026` release.
Steps 8 through 10 require the operator and physical staff device.

1. Create and integrity-check a pre-migration backup of the live local-development database.
2. Run the frozen `0025 -> 0026 -> 0025 -> 0026` chain against a disposable fresh PostgreSQL 17
   cluster; verify runtime grants, forced tenant RLS, concurrent serialization and downgrade /
   re-upgrade behavior.
3. Run backend lint, the ordinary suite and the opt-in PostgreSQL rota tests.
4. Run administrator typecheck, all tests and the production build.
5. Run staff-app typecheck, all tests, Expo Doctor and a production Android export.
6. Apply through `0026_staff_workforce` to the isolated live development database and verify the
   recorded Alembic head, five workforce tables, rota/workforce columns, indexes, grants and
   forced RLS policies.
7. Verify API health, complete workforce route registration, unauthenticated denial,
   administrator/Metro reachability and signed-in desktop/390 px browser behavior.
8. In the administrator portal, create, edit and publish a test draft; in the app acknowledge it,
   clock into it and clock out; verify live planned-versus-actual reconciliation.
9. Exercise decline, alternate proposal, manager accept/reject, cancellation, a deliberately
   unscheduled clock and an interrupted exact retry.
10. Record physical-device, accessibility and operator findings. Do not label the slice accepted
    while a safety or tenancy defect remains open.

## Deliberately later increments

This is the reliable daily-rota foundation. Weekly availability, time-off
requests, reusable one-shift templates and operational coverage targets now
exist in the additive workforce slice. The following capabilities remain
deliberately deferred and must not be inferred from the current screens:

- recurring rotations and bulk-copy/publish workflows;
- leave balances, accrual, blackout dates and supporting-document policy;
- open-shift posting/bidding, manager offers, swaps, partial-shift trades and substitute pools;
- paid/unpaid breaks, split shifts, on-call work and required rest periods;
- qualification/credential expiry constraints and role-specific coverage;
- regulatory child-ratio certification, attendance-driven staffing demand, live replacement
  search and qualification-aware coverage;
- overtime, statutory-holiday, premium, collective-agreement and employment-standard rules;
- timesheet correction/approval, exception evidence, payroll/accounting export and pay statements;
- labor budgets, schedule optimization, demand forecasting and workforce analytics;
- calendar subscription/sync, manager mobile authoring and cross-facility rotation;
- closed-loop callout, no-show escalation and emergency staffing workflows; and
- production geofencing or location evidence. Location collection remains disabled by product
  choice and would require a separate privacy and regulatory decision.

Those increments can be added without collapsing the planned-versus-actual separation above.

# CareSync Workforce Planning: Availability, Time Off, Templates and Coverage

Last updated: 2026-07-16

## Status

This additive slice is implemented in the FastAPI backend, administrator portal and Expo staff
app on top of the Daily Staff Rota. Source migration `0026_staff_workforce` extends, rather than
replaces, migration `0025_staff_rota`; planned shifts and actual clock evidence remain separate.

The source, disposable-database and isolated live-local release gates for `0026` are complete.
The active local-development Alembic head is `0026_staff_workforce`.

## Release evidence

The verified release backup is
`backend/backups/caresync-postgres-20260716-222537.json.gz`. Its compressed SHA-256 is
`eadee6f37b15619220ca4c9da5d3e96f50896bddbe700467b66e69af466670cd`; the uncompressed
JSON-lines SHA-256 is
`c399a0509ef7abe0b0f05d892f375a3ce82ce6c0582cd09bdbad3050df94b2ff`. The manifest records
1,644 rows across 61 tables and the stream contains 1,645 lines.

Final automated gates passed:

- backend ordinary suite: 310 passed with 17 expected opt-in PostgreSQL skips;
- focused PostgreSQL workforce/rota/grant suite: 11 passed;
- administrator portal: 57 test files / 305 tests, TypeScript and production build green; the
  build transformed 809 modules; and
- staff app: 114 tests, TypeScript, Expo Doctor 20/20 and Android export green at 732 modules.

The live migration preserved users 2, organizations 1, memberships 2, facilities 1, rooms 5,
families 110, children 203, ATS applications 1 and actual staff shifts 2. Scheduled shifts and
all five new workforce tables start at 0. Each new table has RLS enabled and forced, one tenant
policy and verified runtime grants.

Runtime smoke returned API health 200, registered the complete workforce route set, returned
401 at the unauthenticated availability boundary, served the administrator portal with 200 and
left Metro running. A signed-in browser smoke found all four workforce tabs and the template
dialog clean, no horizontal overflow at 390 px and zero browser warnings or errors.

Physical-device/operator, accessibility, privacy and regulatory acceptance remain separate.
Remote Expo/FCM delivery also remains deployment work.

## Persistence boundary

Migration `0026_staff_workforce` adds:

- `staff_availability_profiles`, a soft-reset recurring availability projection;
- `staff_time_off_requests`, the current leave-request lifecycle projection;
- `staff_shift_templates`, reusable facility-local shift shapes;
- `staff_coverage_target_profiles`, soft-reset weekly operational targets;
- `staff_workforce_events`, the append-only exact-operation ledger; and
- `staff_scheduled_shifts.availability_override_reason`, the durable publication justification.

The runtime role can select, insert and update current projections but cannot delete them. It can
select and append workforce events but cannot update or delete the event ledger. All five new
tables have tenant RLS enabled and forced in PostgreSQL. Availability and coverage "delete"
operations create tombstones; they never require runtime `DELETE` privilege.

## Product boundary

The slice adds four related capabilities:

1. an educator-owned recurring weekly availability profile for each assigned facility;
2. auditable time-off requests and manager decisions;
3. reusable manager-authored shift templates that instantiate ordinary draft shifts; and
4. manager-authored operational coverage targets with a bounded 15-minute projection.

Coverage targets are planning goals. They are not Alberta licensing, ratio or regulatory
certification. Child attendance, educator qualifications and regulatory ratios remain separate
future constraints.

## Truth hierarchy

- A published scheduled shift remains the current work assignment.
- A server-recorded actual shift remains evidence that work occurred.
- Approved time off is a hard scheduling constraint.
- Declared availability is a staff preference and prospective planning constraint.
- A manager may override an availability mismatch only with a non-blank reason recorded on the
  schedule, immutable event and audit entry.
- A manager may not override approved time off while publishing a shift. The leave must first be
  resolved through its own audited lifecycle.
- Changing availability never hides, rewrites or cancels an already-published shift.
- A shift template creates a normal draft. It never bypasses assignment, overlap, leave,
  availability, publication or clocking rules.

## Availability semantics

Availability is scoped to one active organization membership and one active assigned facility.
Weekly windows use the facility's IANA timezone and `weekday` values `0..6`, where `0` is Monday.
Each window is a non-overnight local wall-time interval with `start_local < end_local`.
Overlapping same-day windows are invalid.

- No profile means **unspecified** and does not block publication.
- A saved profile with an empty window list means **explicitly unavailable**.
- Replacing a profile is optimistic and idempotent.
- Resetting/deleting a profile returns it to unspecified through a tombstone. Canonical GET and
  DELETE responses expose the tombstone's operation receipt so a lost response can be reconciled.
- DST conversion is evaluated against the actual service date when a planned shift is checked;
  ambiguous or nonexistent wall times are never guessed.
- Staff-self routes require a complete marketplace profile when one exists, an active
  organization membership and the fixed `shift:clock` permission.

## Time-off lifecycle

```text
pending --manager approves--> approved --staff/manager cancels--> cancelled
   |                                |
   +--manager declines----------> declined
   +--staff/manager cancels------> cancelled
```

Categories are `vacation`, `sick`, `personal`, `medical`, `bereavement`, `unpaid` and `other`.
Requests store aware instants plus the selected facility and expose facility-local presentation.
The server authors `can_cancel`; clients do not infer cancellation rights from dates or status.
Leave is membership-wide within the organization even though the selected facility supplies
timezone and manager context. Leave requested through facility A therefore blocks an overlapping
publication at facility B.

Approval is rejected while an overlapping published shift exists. Publication is rejected while
approved leave overlaps. Drafts may exist during pending or approved leave so managers can see
and repair the conflict before publication.

Administrators see and decide only educator leave/availability rows, matching the staff
hierarchy. Owners retain the organization-wide workforce view. Staff may cancel their own pending
or approved request; declined and cancelled requests are terminal.

## Shift-template semantics

Templates store one non-overnight weekday/local-time interval in the facility timezone and an
optional active room. Instantiation validates active staff/facility/room scope, weekday, DST,
interval length and rota overlap, then creates an ordinary draft shift. Publication still applies
approved-leave and availability rules.

An exact instantiation retry is bound to caller intent and is resolved before consulting mutable
current template state. A response-loss retry therefore still succeeds after the template is
edited or deactivated, while preserving the default note resolved on the first attempt.
Deactivated rooms remain readable for historical labels but cannot be used for new mutations.

## Coverage projection

Coverage rules are recurring local weekly windows scoped to a facility or one room. Each window
has an operational `required_staff` target. The projection is limited to 31 facility-local days
and emits canonical 15-minute cells containing at least:

- required staff;
- published assignments;
- acknowledged assignments;
- declined assignments;
- draft assignments;
- assignment gap; and
- confirmation gap.

Published-but-declined assignments must not make a cell look safely staffed. Assignment gap is
`max(required - (published - declined), 0)` and confirmation gap is
`max(required - acknowledged, 0)`. The administrator UI shows both risks. These operational
targets are not regulatory ratio certification.

## Safety invariants

1. Every mutation uses a caller-generated UUID operation identifier.
2. Exact retries return canonical committed state; changed-intent reuse returns `409`. If a later
   mutation superseded an action receipt, retrying the old action returns explicit
   `409 operation_superseded` instead of a false last-operation receipt.
3. Tenant and resource ownership are checked before an idempotent receipt is returned.
4. Mutable replacements and decisions require the caller's last-seen aware `updated_at`.
5. PostgreSQL locks serialize operation IDs, availability profiles, time-off decisions, template
   mutation, coverage-target replacement and relevant staff schedule lanes.
6. Current projections have immutable event ledgers and actor-scoped audit entries.
7. New tables use tenant RLS enabled and forced, with least-privilege runtime grants.
8. Staff can edit only their own availability and time-off resources.
9. Manager endpoints retain staff-management permission and role-hierarchy boundaries;
   administrators cannot read or decide owner/administrator personal leave.
10. All list endpoints are bounded; facility-local dates are interpreted only in the selected
    facility timezone.
11. Realtime events invalidate clients; REST responses remain canonical.
12. Remote/local notification payloads remain generic and PII-free until an authenticated ledger
    read resolves the text.
13. Mobile writes one identity-scoped unresolved workforce command to protected storage before
    sending it. Ambiguous outcomes retain that exact command for reconciliation.
14. Admin forms lock meaning-changing fields while an ambiguous operation awaits exact retry.
15. Availability override reason is stored on the published shift so later audits do not depend
    on mutable current availability.

## Acceptance gates

- Availability unspecified/empty/windowed semantics and same-day overlap validation.
- Facility timezone, DST gap, DST ambiguity and date-boundary tests.
- Staff self ownership, manager permission and cross-tenant failure tests.
- Exact retry, changed-intent reuse and stale optimistic-decision tests.
- Approved-leave versus publication conflict tests in both transaction orders.
- Availability-override reason and immutable audit/event tests.
- Template instantiation produces an ordinary draft and cannot bypass overlap/scope checks.
- Coverage cells prove published, acknowledged, declined, draft, assignment-gap and
  confirmation-gap calculations.
- PostgreSQL concurrent decisions, RLS, grants and frozen migration upgrade/downgrade/re-upgrade.
- Strict admin/mobile response parsers, realtime recovery and secure pending-operation tests.
- Full backend, administrator, mobile, Expo Doctor, Android export and production-build gates.

## Deliberately later workforce increments

The implemented slice is weekly planning, not complete workforce management. Later increments
include:

- recurring rotations, bulk copy/publish and calendar synchronization;
- open-shift posting/bidding, manager offers, substitutes, swaps and partial-shift trades;
- leave balances, accrual, blackout calendars and supporting-document policy;
- paid/unpaid breaks, split shifts, rest periods, overtime and statutory-holiday rules;
- qualification-aware and attendance/ratio-aware coverage certification;
- timesheet correction/approval, payroll export and complete HR records; and
- labor budgets, demand forecasting, safe replacement search and schedule optimization.

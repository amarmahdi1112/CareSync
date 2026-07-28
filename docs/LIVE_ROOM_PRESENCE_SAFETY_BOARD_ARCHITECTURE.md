# CareSync Live Room Presence and Operational Safety Board

Last updated: 2026-07-23

## Status

`0041_live_room_presence_and_safety_board` is implemented and verified in
source and on disposable PostgreSQL 17 after
`0040_billing_readiness_batch_planner`. The checked-in source head is now
`0042_billing_policy_recert`; the retained PostgreSQL 17 database on port 5434
remains at `0039_admissions_decision_spine`. No retained 0041 or 0042 cutover
has occurred.

The exact source-release evidence, migration-preservation digests and remaining
operator gates are recorded in
`PRODUCT_SLICE_0041_LIVE_ROOM_PRESENCE_SAFETY_BOARD_RELEASE_NOTE.md`.

The slice introduces one missing operational fact: which room an on-duty staff
member is currently serving. It then combines that fact with current child
attendance, room configuration and the already implemented operational staffing
targets to produce a factual live room board.

This architecture is deliberately not an Alberta child-to-staff ratio engine,
licensing interpretation, supervision certification or compliance decision.
Its language is limited to:

- confirmed children currently on site in a room;
- confirmed on-duty staff currently present in that room;
- the configured room-capacity value;
- the organization's configured operational staffing target;
- missing, stale or internally inconsistent source facts; and
- human acknowledgement that an operational signal is being reviewed.

The slice advances the foundation needed by future `ROOM-005`, `ROOM-006`,
`ROOM-008`, `ROOM-012`, `ROOM-013` and `STAFF-006` work in
`docs/ULTIMATE_PRODUCT_CONSTITUTION.md`. It does not complete or mark any of
those regulatory and qualification-aware controls as implemented.

## Why this is the next slice

The current Basic product already has:

- current child attendance intervals bound to a facility and room;
- server-authored actual staff clock records;
- planned shifts that may identify a room;
- active membership-to-room assignments;
- configured room capacity;
- recurring facility and room operational staffing targets;
- room rosters, administrator and staff room surfaces;
- exact-retry mutation patterns;
- tenant-scoped realtime invalidation; and
- user-private notification ledgers.

The missing link is current staff room presence. An actual shift proves that a
person clocked in at a facility; it does not prove which room they currently
serve. A planned room, a room-access grant and a staff member's only available
room are useful inputs, but none may be silently rewritten as historical actual
presence.

Without that fact, CareSync cannot honestly connect attendance, rooms, staffing
and operational coverage. Nutrition, emergency rosters, qualification-aware
ratios, break coverage and transportation all depend on the same location
truth. Recording it first is the smallest end-to-end slice that materially
improves the childcare MVP without exposing a new external provider or reviving
legacy code.

## User outcome

After a staff member clocks in:

1. CareSync opens a server-confirmed room-presence session when the room is
   unambiguous.
2. If the room is ambiguous or unavailable, the actual shift remains valid but
   the staff member is visibly **not located in a room** and cannot perform
   child operations until they select an eligible room.
3. A staff member can explicitly move from one eligible room to another. The
   move ends one session and starts the next at one server-authored instant.
4. Clock-out closes any current room-presence session in the same transaction.
5. Administrators see each room's confirmed on-site children, confirmed
   room-present staff, configured capacity, active configured staffing target
   and current operational signals.
6. Staff see the same bounded facts for their current authorized room.
7. Child attendance and care mutations require both an open actual shift and a
   matching current room-presence session.

The board never displays `compliant`, `non-compliant`, `licensed ratio met`,
`safe ratio` or equivalent claims. The strongest positive state is
**No current configured-target signal**, accompanied by the standing boundary:

> Operational configured-target evidence only. CareSync does not calculate or
> certify regulatory ratios, qualifications, group-size rules, licensing
> compliance or adequate supervision.

## Explicit non-goals

`0041` does not:

- encode or interpret Alberta ratio, group-size, supervision or staff-
  qualification rules;
- decide whether an educator's ECE credential qualifies them for a regulatory
  ratio;
- infer current room presence from a schedule, access grant, job title,
  certificate, GPS, Wi-Fi, Bluetooth, camera or device proximity;
- collect geolocation or background tracking;
- create staff timesheets, breaks, overtime, payroll or wage facts;
- change planned rota truth, actual clock truth or child attendance truth;
- add room-to-room child movement, trip, school-run or transportation dispatch;
- create an emergency offline roster or claim offline-current headcounts;
- introduce manager-authored historical room-presence correction;
- add an offline room-presence mutation queue;
- send child/staff names, counts, medical facts or room details to a lock
  screen;
- notify on every count change;
- activate external email, SMS, push, payment, funding or licensing providers;
- import any legacy ratio, staffing, scheduler or attendance-automation table;
  or
- treat acknowledgement as resolution, approval, waiver or compliance.

Historical correction, effective-dated rule packs, employer staff-
qualification history and regulatory certification require later bounded
slices.

## Product truth hierarchy

1. A planned shift is an assignment, not actual work.
2. An actual staff shift is facility-level clock evidence, not room presence.
3. A room-access assignment is authorization, not evidence that the staff
   member is in that room.
4. A room-presence session is the sole `0041` source for confirmed staff in a
   room.
5. A child counts as confirmed on site only from an open attendance interval,
   never from enrollment or a planned schedule.
6. Room configured capacity, program licensed capacity, facility legacy
   capacity, group-size limits and physical space limits remain distinct.
   `0041` compares only against `rooms.capacity` and labels it **configured room
   capacity**.
7. A recurring coverage target remains an organization's operational target.
   It is not a regulatory threshold.
8. Missing configuration is `not_configured`, not zero and not success.
9. Missing, crossed, stale or contradictory source facts produce `unknown` or a
   data-quality signal, never a green state.
10. Acknowledgement means only that an authorized person has seen the signal
    and recorded a reason. Only changed source facts can clear a derived
    condition.
11. Realtime events invalidate. A canonical REST projection establishes
    current truth.
12. An old cached projection may be displayed only as visibly stale evidence;
    it cannot continue to show a current positive state.

## Vocabulary

- **actual shift**: one server-authored `staff_shifts` interval;
- **current room presence**: a room-presence session with no `ended_at`, linked
  to the authenticated staff member's open actual shift;
- **located staff**: a distinct active membership with one valid current room
  presence;
- **unlocated staff**: a distinct membership with an open actual shift at the
  facility and no valid current room presence;
- **confirmed on-site child**: a distinct child with an open attendance
  interval at the projection instant;
- **active target window**: the one non-overlapping configured operational
  coverage window containing the facility-local projection time;
- **condition**: deterministic arithmetic or source-integrity state;
- **exception episode**: persisted evidence that one actionable condition
  opened and later resolved;
- **acknowledged**: a human recorded that an active episode is being reviewed;
- **resolved**: the authoritative source facts no longer produce the condition;
- **unknown**: CareSync cannot prove the arithmetic from a coherent source
  snapshot; and
- **stale**: the client no longer has a recent canonical projection.

## Additive migration contract

`0040` intentionally adds no schema revision. The `0041` Alembic revision
therefore follows `0039_admissions_decision_spine` directly:

```text
0039_admissions_decision_spine
  └── 0041_live_room_presence
```

The shorter Alembic identifier is intentional: the retained
`alembic_version.version_num` column is `varchar(32)`. The product-slice name
remains `0041_live_room_presence_and_safety_board`.

The migration is additive. It creates four tenant-owned tables and the exact
indexes, foreign keys, checks, RLS policies, mutation guards and restricted
runtime grants described below. It does not alter, delete, relabel or backfill
an existing attendance, staff shift, schedule, room assignment, coverage
target, room, enrollment or child row.

### `staff_room_presence_sessions`

One row is one actual interval in one room.

Required columns:

- `id`;
- `organization_id`;
- `membership_id`;
- `staff_shift_id`;
- `facility_id`;
- `room_id`;
- `source`, limited to `scheduled_room`, `single_assignment` or
  `staff_selected`;
- `started_at`, always server-authored;
- `ended_at`, nullable until terminal;
- `end_reason`, null while open and otherwise one of `moved`, `staff_ended`,
  `clocked_out` or `access_revoked`;
- `start_operation_id`;
- `end_operation_id`, nullable until terminal;
- `started_by_user_id`;
- `ended_by_user_id`, nullable until terminal;
- `version`, beginning at one and incremented exactly once when the session
  closes; and
- `created_at` and `updated_at`.

Required database invariants:

- tenant-composite foreign keys bind membership, actual shift, facility and
  room to the same organization;
- the room belongs to the stored facility;
- the actual shift belongs to the same membership and facility;
- `ended_at`, `end_reason`, `end_operation_id` and `ended_by_user_id` are all
  null or all terminally populated;
- `ended_at >= started_at`;
- one partial unique index permits at most one open session per organization
  and membership;
- one partial unique index permits at most one open session per organization
  and actual shift;
- a session's identity, scope, room, source, start instant and start provenance
  are immutable;
- an ended session cannot be reopened or changed;
- the only runtime update is the one-way open-to-ended transition;
- runtime delete is forbidden; and
- overlapping sessions for the same membership are rejected while the
  membership presence lane is held. PostgreSQL must enforce the no-overlap
  invariant independently of an untrusted client; portable SQLite tests must
  exercise the equivalent application guard.

No row stores a child name, staff name, schedule note, medical fact, GPS value
or device identifier.

### `staff_room_presence_events`

This is the immutable command receipt and decision ledger.

Required columns:

- `id`;
- `organization_id`;
- `operation_id`, unique within the organization;
- `actor_user_id`;
- `membership_id`;
- `staff_shift_id`;
- `facility_id`;
- `event_type`, limited to `started`, `moved`, `ended`,
  `clock_started_presence`, `clock_ended_presence` or
  `access_revoked_presence`;
- `from_session_id`, nullable when starting;
- `to_session_id`, nullable when ending;
- `request_sha256`;
- canonical, PII-free `intent`;
- canonical, PII-free `result`;
- `occurred_at`; and
- `created_at`.

Shape checks enforce which session references are allowed for each event type.
The event table is insert/select only. It has no runtime update or delete
grant. Exact retry returns its immutable result after current authorization and
actor ownership are re-established.

### `room_operational_exception_heads`

One head represents one open-to-resolved episode for one condition and scope.

Required columns:

- `id`;
- `organization_id`;
- `facility_id`;
- `scope_kind`, `facility` or `room`;
- `scope_id`, equal to the facility ID for a facility scope and the room ID for
  a room scope;
- `room_id`, null only for a facility scope;
- `condition_code`;
- `state`, `open`, `acknowledged` or `resolved`;
- `current_fingerprint_sha256`;
- PII-free canonical `current_evidence`;
- `opened_at`;
- `last_changed_at`;
- `acknowledged_at`, `acknowledged_by_user_id` and
  `acknowledgement_reason`, all null unless acknowledged;
- `resolved_at`, null until resolved;
- `version`; and
- `created_at` and `updated_at`.

Initial condition codes are closed:

- `confirmed_children_above_configured_room_capacity`;
- `confirmed_staff_below_configured_room_target`;
- `open_shift_staff_without_current_room`;
- `present_child_without_active_room`; and
- `source_integrity_unknown`.

A partial unique index allows at most one unresolved episode for
`(organization_id, scope_kind, scope_id, condition_code)`. A resolved episode
is never reopened; recurrence creates a new episode. No acknowledgement can
change the condition code, scope, opening evidence or source facts.

`current_evidence` contains counts, configured values and closed reason codes
only. It contains no person identity, narrative care data, medical information
or schedule notes.

### `room_operational_exception_events`

This immutable table records `opened`, `materially_changed`,
`acknowledged` and `resolved` events.

Required columns:

- `id`;
- `organization_id`;
- `exception_id`;
- `operation_id`, unique within the organization;
- `event_type`;
- `actor_user_id`, nullable only for server-derived events;
- `cause_entity_type` and `cause_entity_id`;
- `previous_fingerprint_sha256`;
- `current_fingerprint_sha256`;
- PII-free canonical `evidence`;
- `reason`, required only for acknowledgement;
- `occurred_at`; and
- `created_at`.

Server-derived operation IDs are deterministic from the committed source
operation/event and condition identity. This makes recomputation and worker
retry duplicate-safe. Human acknowledgement uses the caller's operation ID.
The table is insert/select only.

### Database mutation guards

The migration must install PostgreSQL guards that reject:

- direct or cross-tenant scope changes;
- a presence start without its matching operation event;
- a presence terminal update without the matching operation event;
- a move whose source end and destination start are not bound to the same move
  event and instant;
- a second open session for one staff/shift lane;
- mutation or deletion of an immutable event;
- manual resolution of a derived exception;
- acknowledgement without a matching actor-bound acknowledgement event;
- acknowledgement of a foreign-tenant, resolved or stale-version episode; and
- any runtime DML performed outside the command's transaction-local operation
  context.

The application cannot weaken these controls by using the migration owner.
The normal API continues to run as the restricted, non-superuser,
`NOBYPASSRLS` runtime identity.

## Exact API boundary

### Staff self reads

- `GET /api/v1/staff/self/room-presence`
- `GET /api/v1/staff/self/room-safety/live`

The first response returns the authenticated membership's open actual shift,
current room-presence session, eligible active assigned rooms and whether a
room decision is required. The second returns only the current authorized
room's bounded live board. It never exposes another room merely because both
rooms belong to the same organization.

### Staff self commands

- `POST /api/v1/staff/self/room-presence/start`
- `POST /api/v1/staff/self/room-presence/move`
- `POST /api/v1/staff/self/room-presence/end`

Start intent:

```json
{
  "client_operation_id": "uuid",
  "staff_shift_id": "uuid",
  "facility_id": "uuid",
  "room_id": "uuid"
}
```

Move intent:

```json
{
  "client_operation_id": "uuid",
  "expected_session_id": "uuid",
  "expected_version": 1,
  "destination_room_id": "uuid",
  "reason": "Moved to provide scheduled room coverage"
}
```

End intent:

```json
{
  "client_operation_id": "uuid",
  "expected_session_id": "uuid",
  "expected_version": 1,
  "reason": "Leaving room duties while remaining clocked in"
}
```

Clients cannot supply a membership, user, start/end instant, source or
exception state. Reasons are trimmed, bounded and must contain at least five
non-whitespace characters.

The existing clock-in request gains an optional `room_id`. The server:

1. uses the acknowledged published shift room when it is present and still
   authorized;
2. otherwise uses an explicitly supplied eligible room;
3. otherwise may use the only active room assignment in the selected
   facility; and
4. otherwise commits the actual shift without room presence and returns
   `room_presence_required=true` plus the bounded eligible-room choices.

It never guesses among multiple rooms. An invalid planned room is a visible
data-quality blocker and is not silently replaced.

Clock-out remains available even when room access has changed. It closes any
current presence session at the same server instant and in the same
transaction. Clock-out may never be blocked merely because the board cannot
produce a positive state.

### Manager reads and command

- `GET /api/v1/room-safety/live?facility_id={facility_id}`
- `GET /api/v1/room-safety/exceptions?facility_id={facility_id}&state={state}`
- `GET /api/v1/room-safety/exceptions/{exception_id}/action-target`
- `POST /api/v1/room-safety/exceptions/{exception_id}/acknowledge`

Exception history is cursor-paginated and bounded. The action-target endpoint
returns only organization, facility, room, visibility and current state; it
does not return a notification-supplied URL or sensitive narrative.

Acknowledgement intent:

```json
{
  "client_operation_id": "uuid",
  "expected_version": 3,
  "reason": "Coverage call is in progress; manager is monitoring the room"
}
```

There is no manual `resolve`, `dismiss`, `waive`, `approve` or `mark compliant`
command. Source facts resolve a condition.

### Command responses

Every command response includes:

- `organization_id`;
- `client_operation_id`;
- `request_sha256`;
- `replayed`;
- immutable `receipt`;
- the affected resource identity;
- current resource `version` where applicable;
- current self-presence or exception projection; and
- `generated_at`.

The immutable receipt proves the original command result. The accompanying
current projection may legitimately show that the session later moved/ended
or the exception later resolved. A client clears a protected pending command
only when the receipt matches its organization, actor, command kind, operation
ID, request digest and intended resource transition.

## Idempotency, interruption and concurrency

### Canonical intent and exact replay

The request digest includes:

- command kind;
- organization and authenticated actor;
- actual shift;
- source session and expected version where applicable;
- source/destination facility and room;
- normalized reason; and
- acknowledgement episode and expected version where applicable.

For each command:

1. authenticate and restore the active organization;
2. verify the actor may access the named resource without disclosing foreign
   existence;
3. acquire the operation-ID lane;
4. look up the actor-owned operation event;
5. return the immutable receipt on exact match;
6. return `409 operation_reused` on changed intent;
7. acquire the membership-presence lane and any affected room/scope lanes in
   deterministic UUID order;
8. revalidate current shift, assignment, room, facility and expected version;
9. write the head/session change, immutable event, audit and realtime
   invalidation atomically; and
10. commit before returning success.

Exact replay is evaluated after authorization but before current lifecycle
rules. A start retry may therefore return its original receipt after the staff
member later moved, and an acknowledgement retry may return after the episode
resolved. A different actor receives not-found behavior rather than another
person's receipt.

### Presence lane rules

- One membership can occupy at most one room at an instant.
- Presence requires an open actual shift for the same membership and facility.
- Start requires an active membership, active facility, active room and active
  room assignment.
- Move closes the source and opens the destination at one database/server
  instant in one transaction.
- Move requires an active assignment to the destination and a current,
  unchanged source session.
- End cannot be backdated.
- No command creates a gap or overlap through a client-supplied timestamp.
- A stale source session/version returns a structured `409`; the client must
  refresh before creating a new operation.
- Voluntary room-assignment removal and room deactivation are blocked while a
  current presence depends on them.
- Membership suspension/revocation remains authoritative. It atomically ends
  any current presence with `access_revoked`, invalidates the staff session and
  does not fabricate a clock-out.
- Facility/room closure retains its existing impact-preview and exact-
  confirmation behavior and gains current room presence as a hard live
  dependency.

### Client recovery

The Expo app stores at most one unresolved presence command in encrypted,
identity-scoped storage before sending it. Storage failure blocks the send.
Timeout, disconnect, throttling, server error or malformed response retains
the exact operation for retry. A different room action cannot replace it.

Presence is online-only in `0041`. The device never advances local current-room
truth before a matching server receipt. App reinstall or secure-store loss
cannot be presented as proof that a command failed; the staff member must
refresh canonical current presence before another mutation is enabled.

Existing queued care commands are not retargeted after a room move. The server
revalidates their original child, attendance day, room and current presence.
A mismatch remains a reviewable failure rather than being silently moved to a
different room.

## Canonical live projection

### Snapshot boundary

The server evaluates one facility from one coherent database snapshot using a
single server-authored aware `as_of` instant and the facility's IANA timezone.
The client cannot ask for a past instant in `0041`.

The response includes:

- `schema_version = "live-room-safety-v1"`;
- `organization_id`;
- `facility_id`;
- `facility_timezone`;
- `as_of`;
- `generated_at`;
- the canonical realtime cursor/snapshot marker;
- facility totals;
- one row per active facility room;
- active exception references; and
- closed data-quality reason codes.

The primary projection contains counts and identifiers, not child/staff names.
Authorized users open the existing room roster or staff workspace for
identity-level follow-up.

### Child arithmetic

For room `R` at `as_of = T`:

```text
confirmed_children(R, T)
  = count(distinct attendance_day.child_id)
    where attendance_day.facility_id = selected facility
      and attendance_day.room_id = R
      and attendance_day.status = present
      and an attendance interval exists with
          checked_in_at <= T
          and (checked_out_at is null or checked_out_at > T)
```

Enrollment, expected attendance, room roster membership, claim schedule and a
daily-care event never make a child present.

Facility reconciliation is:

```text
facility_confirmed_children
  = sum(room confirmed children)
    + present_children_without_active_room
```

A duplicate open interval for one child, a present day without a usable room,
a crossed room/facility reference or another impossible state makes the
affected arithmetic `unknown` and opens `source_integrity_unknown`; CareSync
does not deduplicate corrupt source into a green value.

### Staff arithmetic

For room `R` at `T`:

```text
confirmed_staff(R, T)
  = count(distinct room_presence.membership_id)
    where room_presence.room_id = R
      and room_presence.started_at <= T
      and room_presence.ended_at is null
      and linked actual shift is open at T
      and membership, facility, room and assignment remain active
```

Facility reconciliation is:

```text
open_shift_staff
  = count(distinct membership with an open actual shift at the facility)

located_staff
  = count(distinct membership with a valid current room presence)

unlocated_staff
  = open_shift_staff - located_staff
```

Schedules never count as staff. An invalid or duplicate presence makes the
affected result `unknown`; it is not silently ignored.

### Configured room-capacity state

For a known child count and positive `rooms.capacity`:

```text
within_configured_capacity
  when confirmed_children <= room.capacity

above_configured_capacity
  when confirmed_children > room.capacity
```

The result is `unknown` if either source cannot be proved. The label always
says **configured room capacity**. `0041` does not compare or combine
`facilities.licensed_capacity`, program licensed capacity, physical floor area,
group size or age-mix rules.

### Configured operational-target state

Coverage windows are interpreted in the facility timezone using the existing
non-overlapping, 15-minute-aligned target contract.

Room target state is:

- `target_met`: an active room-specific target exists and confirmed room staff
  is greater than or equal to `required_staff`;
- `confirmed_staff_below_target`: an active room-specific target exists and
  confirmed room staff is below it;
- `outside_configured_window`: a room target profile exists but no window
  covers the current facility-local time;
- `not_configured`: no room target profile exists; or
- `unknown`: target or staff source coherence cannot be proved.

A facility-wide target is evaluated only against facility-wide open actual
staff. It is not divided among rooms and is never inherited by a room. If both
facility and room profiles exist, both factual results may be displayed
separately.

An unlocated staff member does not count toward a room target. The UI says
**confirmed room staff below configured target**, acknowledging that resolving
an unlocated staff record may change the next canonical result.

### Overall and freshness states

Room/facility state is:

- `attention` when an actionable condition is active;
- `unknown` when a required source is incoherent or the client projection is
  stale;
- `no_active_configured_target_signal` only when all evaluated conditions are
  clear; or
- `not_evaluated` where configuration intentionally supplies no target window.

`not_configured` and `outside_configured_window` are neutral, visible states;
they are never converted to success.

The client treats a projection as stale after 60 seconds without a successful
canonical refresh, on realtime disconnect/reset, on app foreground before
refresh, or on organization/facility change. A stale card loses positive
color and actions that depend on current arithmetic are disabled. Manual
refresh can restore current state; a cached timestamp cannot.

## Exception derivation and acknowledgement

The server opens an exception episode only for one of the closed condition
codes. Routine source changes remain quiet.

A material change is:

- a new condition;
- recurrence after resolution;
- confirmed child count increasing while above configured capacity;
- confirmed staff count decreasing while below the active target;
- a configured threshold changing while the condition remains active; or
- the set of source-integrity reason codes worsening or changing.

A non-material count refresh does not create another episode or notification.
Material worsening of an acknowledged episode returns it to `open`, increments
its version and requires a new acknowledgement. Resolution is recorded only
when a coherent canonical snapshot proves the condition is absent. Recurrence
creates a new episode ID.

Acknowledgement:

- requires manager permission, last-seen version, operation ID and reason;
- never changes attendance, shift, presence, assignment, room or target facts;
- never suppresses realtime refresh;
- suppresses duplicate notification for the unchanged episode only;
- is retained after automatic resolution; and
- cannot be used as evidence of regulatory approval.

## Administrator experience

### Rooms workspace

The existing `/rooms` workspace gains a **Live operations** mode; `0041` does
not create a disconnected top-level module.

The facility summary shows:

- projection timestamp and connection/freshness state;
- confirmed on-site children;
- open actual-shift staff;
- located staff;
- unlocated staff;
- facility configured-target state; and
- active exception count.

Each room card shows:

- room name;
- confirmed on-site child count;
- configured room capacity;
- confirmed room-present staff count;
- active room operational target when one exists;
- target/capacity/unknown state;
- last canonical refresh; and
- an exact link to the current room roster and active exception.

Exception detail is an inline or full-page workspace section, not a side
drawer hidden under navigation. It explains:

- which configured fact was compared;
- the server-authored arithmetic;
- what is unknown;
- which existing workspace owns the likely source correction;
- whether it has been acknowledged;
- acknowledgement history; and
- why acknowledgement is not resolution.

The acknowledgement dialog is focus trapped, scroll safe under the fixed
header, keyboard accessible and exact-retry locked after an ambiguous result.

### Dashboard and Today

Dashboard and Today receive compact summaries only. They link to the exact
Rooms live-operations state after an authenticated action-target lookup. They
do not duplicate manager commands or cache their own arithmetic.

No positive status is shown while organization, facility, projection or
realtime context is unresolved.

## Expo staff experience

### Clock and room selection

Clock-in displays:

- the planned room when the acknowledged schedule has one;
- the single eligible room when only one exists; or
- a required room selection when multiple eligible rooms exist.

If actual clock-in succeeds without a room, the app remains in the employee
shell but opens a clear **Choose current room** blocker. Clock-out remains
available. The app does not restart the shift or fabricate a room assignment.

### Current room

The staff Room surface shows:

- current room and presence start time;
- confirmed on-site child count;
- confirmed room staff count;
- configured room target when active;
- configured room capacity;
- current stale/unknown/attention state; and
- **Move room** / **End room duty** actions.

Only active assigned destination rooms are selectable. A move explains that
child operations will immediately follow the new room after the server
confirms the command.

### Child-operation gate

Attendance, daily care, medication administration and incident creation require:

- active organization membership and permissions;
- an open actual shift;
- a current room-presence session;
- the presence facility/room matching the target child and attendance day; and
- a fresh canonical access refresh.

Without those facts, controls are disabled with one precise resolution path.
There is no redundant confirmation modal after the gate passes. Clock-out is
never hidden by this gate.

The mobile app does not store a live-board cache as offline-current truth.
When offline it may show the last refresh timestamp and room identity, but
counts and positive state are visibly unavailable until refresh.

## Realtime contract

New organization entity types:

- `staff_room_presence`; and
- `room_operational_exception`.

New event families:

- `staff_room_presence.started`;
- `staff_room_presence.moved`;
- `staff_room_presence.ended`;
- `room_operational_exception.opened`;
- `room_operational_exception.materially_changed`;
- `room_operational_exception.acknowledged`; and
- `room_operational_exception.resolved`.

Payloads contain only event/entity IDs, organization/facility/room IDs where
needed for routing, event type and `requires_action`. They contain no person
identity, count, threshold, child/staff name, medical fact, note or
acknowledgement reason.

Canonical consumers:

- administrator Rooms, Dashboard, Today and staff-rota monitor;
- staff Room, Clock, Attendance, Daily Care, Medication, Incidents and Daily
  Close; and
- the authenticated notification inbox for a matching durable notification.

Those consumers also refresh on existing `attendance_day`, `staff_shift`,
`staff_schedule`, `staff_coverage_target`, `organization_membership`,
`facility`, `room` and room-assignment invalidations.

The client coalesces event bursts and advances its cursor only after every
mounted dependent surface has completed a canonical REST refresh. Access loss
clears room safety and presence state before reconnect. A reset requires a full
canonical refresh, not cursor guessing.

## Notification and route-safety contract

Routine attendance, presence, clock and count changes are silent. A durable
notification is created only when:

- a new actionable exception episode opens; or
- an acknowledged episode materially worsens.

Initial cutover reconciliation is explicitly notification-suppressed.
Resolution and acknowledgement update the inbox through realtime but do not
send a new remote wake-up.

Recipients are current owner/administrator memberships with the manager read
boundary for the affected facility. `0041` does not broadcast a room exception
to all educators. A later role-specific escalation policy may widen recipients
only with an explicit privacy and supervision decision.

Lock-screen copy is fixed and generic:

- title: `Room operations need review`
- body: `Open CareSync to review a current operational signal.`

The durable action is:

```text
action_path        = /rooms
action_entity_type = room_operational_exception
action_entity_id   = <exception UUID>
```

The backend notification allowlist must add that exact path/entity pairing.
The client never treats the entity ID as a URL. On tap it:

1. restores authentication and organization;
2. fetches
   `/api/v1/room-safety/exceptions/{id}/action-target`;
3. verifies organization, facility, visibility and current permission;
4. opens `/rooms` and focuses the returned room/exception internally; or
5. shows a safe unavailable state if the episode resolved or access changed.

No room name, facility name, count or condition code is carried in the remote
payload. Notification deduplication is keyed to the exception episode and
material fingerprint.

## Integration mutation matrix

| Source mutation | Presence consequence | Projection/exception consequence | Realtime | Durable notification |
|---|---|---|---|---|
| Staff clock-in with valid unambiguous room | Create actual shift and room presence atomically | Refresh room/facility facts | `staff_shift`, `staff_room_presence` | Only if a new actionable exception opens |
| Staff clock-in with ambiguous/no eligible room | Create actual shift; no presence | Increment unlocated staff and open/update facility signal | `staff_shift`, `staff_room_presence`, `room_operational_exception` | Manager only for a new/material episode |
| Presence start | Open one room session | Re-evaluate source/destination facility and room | `staff_room_presence`, exception changes | New/material episode only |
| Presence move | End source and start destination at one instant | Re-evaluate both rooms and facility | One moved invalidation plus exception changes | New/material episode only |
| Presence end while shift remains open | End current session | Staff becomes unlocated; re-evaluate room/facility | `staff_room_presence`, exception changes | New/material episode only |
| Staff clock-out | End presence and actual shift atomically | Re-evaluate prior room/facility | `staff_shift`, `staff_room_presence`, exception changes | New/material episode only |
| Child check-in/re-check-in | No presence mutation | Increment confirmed child count in attendance room | `attendance_day`, exception changes | New/material episode only |
| Child checkout | No presence mutation | Decrement confirmed child count | `attendance_day`, exception resolution/change | No routine wake-up |
| Attendance correction/status correction | No presence mutation | Recompute affected room(s) from canonical interval truth | `attendance_day`, exception changes | New/material episode only |
| Coverage target replace/remove | No presence mutation | Re-evaluate target state; removal becomes `not_configured` | `staff_coverage_target`, exception changes | New/material episode only; no alert solely because target is absent |
| Room assignment removal | Block while a current presence depends on it | Impact preview names dependency | Existing assignment invalidation | No notification until committed source state changes |
| Membership suspension/revocation | Atomically end presence as `access_revoked` | Re-evaluate room/facility and clear client authorization | `organization_membership`, `staff_room_presence`, exception changes | Manager exception policy only |
| Room/facility deactivation | Block while current presence or open child attendance depends on it | Existing impact preview gains presence dependency | `room`/`facility` plus exception changes after valid commit | New/material episode only |
| Scheduled-shift room edit/publication | Does not move current actual presence | Future clock derivation changes only | `staff_schedule` | Existing schedule policy only |
| Child enrollment/room move while not on site | No presence mutation | No current child-count change | Existing enrollment/room events | Existing policy only |
| Child placement change while currently on site | Refused or requires a separate future child-movement workflow; never silently moves attendance room | Current live room remains attendance-bound | Existing enrollment/attendance behavior | None in `0041` |
| Canonical projection read | No write | Derives current truth only | None | None |
| Exception acknowledgement | No source-fact mutation | Changes episode acknowledgement only | `room_operational_exception` | No remote wake-up |
| Source facts clear a condition | No manual resolve | Server records resolved event | `room_operational_exception` | No remote wake-up |

Source mutations, their audit events and the required invalidation/exception
transition commit atomically. Optional provider delivery remains outside the
business transaction. Source-integrity problems produce an unknown signal
rather than preventing terminal child checkout or staff clock-out.

## Permission boundary

`0041` reuses existing product permissions rather than silently granting a new
role:

- self presence reads/commands require `shift:clock`,
  `care_roster:read`, active membership and active room assignment;
- the staff self live board additionally requires `child_safety:read`;
- manager live-board and exception reads require `facility:read`,
  `care_roster:read` and `staff:manage_educators`;
- acknowledgement requires `staff:manage_educators`; and
- roster/person drilldown continues to use its existing stricter permissions.

Owners and administrators receive no new authority beyond permissions they
already hold. Educators receive no facility-wide staff list or exception
history. A custom role must possess the exact required permission conjunction;
role-name guessing is forbidden.

The API rechecks active membership and room/facility scope for every request.
Resource lookup never returns a foreign-tenant or unauthorized-room existence
signal.

## RLS and restricted grants

All four new tables:

- enable and force PostgreSQL row-level security;
- scope rows by `organization_id` and the transaction-local authenticated
  organization;
- require the authenticated user's active organization membership;
- use tenant-composite foreign keys;
- revoke all privileges from `PUBLIC`; and
- are inaccessible to unauthenticated/candidate marketplace sessions.

The restricted application role receives only:

- `SELECT` and `INSERT` on presence sessions;
- column-level terminal `UPDATE` on presence sessions;
- `SELECT` and `INSERT` on presence events;
- `SELECT` and `INSERT` plus exact state/fingerprint/acknowledgement column
  updates on exception heads; and
- `SELECT` and `INSERT` on exception events.

It receives no delete, truncate, ownership, trigger-disable, policy-bypass or
general table-update privilege. Sequences, functions and indexes receive only
the minimum grants required by the implemented command path. Migration and
evidence owners remain separate login identities and are not used by the API.

Startup attests:

- exact Alembic head;
- all four tables, required indexes, constraints and triggers;
- `relrowsecurity=true` and `relforcerowsecurity=true`;
- expected owner identities;
- exact runtime grants and absence of `PUBLIC` grants; and
- absence of a broad update/delete path.

An incomplete boundary disables the capability and returns a truthful
capability status; it does not fall back to client inference.

## Cutover and backfill rule

The migration itself inserts no room-presence or exception row.

In particular, it does not:

- convert a planned shift room into actual presence;
- infer presence from a single room assignment;
- backdate a session to an existing shift's clock-in;
- infer child presence from enrollment; or
- create historical exception episodes.

After guarded migration and service restart:

1. every pre-existing open actual shift is honestly `unlocated`;
2. staff must select a current eligible room or clock out;
3. existing completed shifts remain unchanged and receive no presence history;
4. existing child attendance remains authoritative;
5. one explicit release-reconciliation pass computes only current conditions
   at its server timestamp;
6. that pass may create current exception episodes with provenance
   `release_reconciliation`, but it creates no session and sends no remote
   notification; and
7. the feature capability remains unavailable until the reconciliation receipt,
   runtime attestation and canonical projection checks pass.

Cutover requires writer quiescence, an exact pre-migration database backup,
vault backup/restore coverage where the release train requires it, source and
restored row counts/digests, migration on a fresh restored PostgreSQL target,
restricted-role startup, reconciliation receipt and signed-in smoke tests.

Downgrade is for disposable proof only. It must refuse when any `0041` table is
non-empty unless an explicit disposable destructive-test flag is present.
Retained rollback restores the pre-migration backup; it does not drop live
presence/evidence rows in place.

An unresolved pre-cutover mobile care command:

- may recover a previously committed receipt without new presence evaluation;
- may not execute a previously absent write after cutover until current room
  presence matches its original room; and
- is never silently assigned a new operation ID or room.

## Capability contract

The server exposes `live_room_presence_safety_board` only when:

- schema revision and runtime attestation are complete;
- the database is writable;
- initial current-state reconciliation completed;
- required routes are registered;
- the caller has the exact permission/scope boundary; and
- the canonical projection can establish one coherent snapshot.

The admin and staff clients keep the feature hidden or unavailable when the
server does not advertise it. They do not simulate it from existing roster,
schedule or clock endpoints.

## Acceptance matrix

| Gate | Minimum acceptance evidence |
|---|---|
| Architecture boundary | Tests and copy prove no regulatory, qualification, licensing, physical-capacity or supervision claim; no legacy ratio/scheduler import or route is enabled |
| Schema | All four tables, closed enums/checks, tenant-composite FKs, partial uniqueness, immutability triggers and operation bindings match this document |
| Migration | Fresh and populated disposable PostgreSQL 17 `0039 -> 0041 -> 0039 -> 0041`; migration preserves every existing row/count/digest; non-empty downgrade refuses without disposable opt-in |
| Restricted runtime | API starts only as the expected non-superuser `NOBYPASSRLS` role; exact grants pass; owner/superuser or incomplete boundary fails closed |
| RLS and tenancy | Owner, administrator, educator, inactive member, candidate, unauthenticated and crossed-tenant probes for every table/read/command; foreign IDs do not disclose existence |
| Permission/scope | Custom-role conjunctions, assigned/unassigned rooms, inactive room/facility/membership, manager acknowledgement and educator self-only access |
| Start command | Scheduled-room, explicit-room, single-assignment, ambiguous, no-assignment, invalid-room and closed-shift cases |
| Move/end commands | Atomic same-instant move, stale version, same-room move, invalid destination, access revocation, voluntary end and clock-out terminal behavior |
| Exact retry | Exact replay after current state changed; changed-intent operation reuse; foreign actor operation; response-loss retry; immutable receipt/current projection separation |
| Concurrency | Simultaneous starts, start versus clock-out, two destination moves, move versus assignment removal, move versus room closure, suspension versus presence mutation, and deterministic lock order |
| Database guards | Direct DML attempts for duplicate open presence, overlap, reopen, scope rewrite, unmatched operation event, manual exception resolve, event mutation and delete all fail |
| Child arithmetic | Check-in, re-check-in, checkout, absence, multiple intervals, correction, midnight/facility-time behavior, duplicate/crossed data and present child without active room |
| Staff arithmetic | Scheduled versus actual separation, located/unlocated reconciliation, open/closed shifts, inactive assignment, duplicate/crossed data and membership revocation |
| Capacity arithmetic | Below/equal/above configured room capacity, unknown count/configuration and proof that program/facility/licensed/group-size values are not substituted |
| Target arithmetic | Room and facility targets, exact boundary instants, no active window, no profile, non-overlapping windows, 15-minute alignment, DST conversion, and no facility-to-room allocation |
| Unknown/freshness | Every invalid source reason prevents positive state; 60-second stale transition, reconnect, reset, app foreground and manual refresh behavior |
| Exception lifecycle | Open, material change, acknowledgement, unchanged dedupe, worsening re-open-to-attention, automatic resolution and recurrence with a new episode |
| Integration mutations | Every row of the integration mutation matrix has backend tests proving its presence/projection/realtime/notification effect |
| Admin API/parser | Strict schema, arithmetic reconciliation, duplicate/crossed references, unauthorized action target, bounded pagination and private no-store handling |
| Admin UI | Rooms live mode, Dashboard/Today links, full/inline exception detail, exact-retry acknowledgement, no partial green state, responsive layout, fixed-header/modal scrolling and production build |
| Staff API/parser | Current self presence, eligible-room scope, receipt verification, current-room board, crossed-tenant/room rejection and fail-closed capability handling |
| Staff UI | Ambiguous clock-in room choice, current room, move/end, child-operation gate, clock-out escape, protected pending command, offline stale state and process-loss recovery |
| Care queue | Queued command replay after move/access change stays bound to original child/day/room and cannot auto-retarget |
| Realtime | PII-free payloads, event coalescing, refresh-before-cursor, reset, reconnect, organization switch, access loss and mounted-surface barrier across admin and mobile |
| Notifications | Closed recipient set, generic OS copy, episode/material dedupe, cutover suppression, strict `/rooms` + exception entity pairing, authenticated action-target resolution and removed-access behavior |
| Accessibility | Keyboard/focus order, screen-reader labels/live regions, touch targets, text scaling, color-independent states, reduced motion and stale/unknown announcements |
| Performance | Indexed current-presence/open-shift/attendance queries, bounded exception lists, facility-scale load test, burst coalescing and no N+1 roster/person lookup in the count projection |
| Operational release | Exact backup/restore, reconciliation receipt, retained row preservation, capability attestation, signed-in administrator walkthrough and physical Android clock/select/move/care-gate/clock-out walkthrough |
| Regression | Full backend, administrator, staff app and extension suites; Ruff, bytecode, TypeScript, production web build, Expo Doctor and Android export all pass |

## Release claim

Completion of `0041` may claim:

> CareSync records server-confirmed staff room-presence intervals and shows a
> tenant-scoped live operational board comparing confirmed attendance and
> room-present staff with configured room capacity and operational staffing
> targets. Unknown data fails visibly, actions are exact-retry safe, and
> actionable exception episodes are audited and routed through canonical
> realtime/notification boundaries.

It may not claim:

> CareSync certifies Alberta child-to-staff ratios, staff qualifications,
> licensed capacity, group size, supervision adequacy or regulatory
> compliance.

That boundary remains visible in API schemas, UI copy, tests, release notes and
operator evidence.

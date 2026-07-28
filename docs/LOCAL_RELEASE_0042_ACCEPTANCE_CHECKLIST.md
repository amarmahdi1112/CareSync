# CareSync Retained 0042 Acceptance Checklist

Last updated: 2026-07-26

## Classification

Procedure: retained `0039_admissions_decision_spine` to
`0042_billing_policy_recert` acceptance  
Scope: administrator browser plus connected physical Android Staff app  
Status: **acceptance procedure only; not completed release evidence**

This document defines the ordered acceptance work that remains after the
guarded retained migration and restricted-runtime certificate succeed. Empty
checkboxes are instructions, not claims that an action ran or passed. This
document is not a cutover receipt, operator authorization, signed walkthrough
record or `LOCAL_RELEASE_0042_CUTOVER.md`.

Do not record bearer tokens, passwords, realtime tickets, WebSocket URLs with
tickets, private child or staff facts, or unredacted screenshots in acceptance
evidence. Free-text operational reasons become permanent evidence and must use
approved, non-PII wording.

## Release boundary

0041 provides server-confirmed room-presence intervals and factual operational
configured-target evidence. It does not certify regulatory ratios,
qualifications, licensed capacity, group size, supervision adequacy or
regulatory compliance. 0042 changes no room-presence product behavior; it
recertifies the existing billing policy catalog at the checked-in source head.

The database revision and restricted-runtime certificate are prerequisites.
The browser or Android capability marker is not a substitute for exact
`0042_billing_policy_recert` release evidence.

## Canonical release and recovery commands

This checklist does not authorize a release by itself. The canonical
two-phase operator flow is:

```text
scripts/basic-release.sh prepare [--clone-port 55000..60999]

scripts/basic-release.sh commit \
  --receipt /absolute/private/run/candidate-receipt.json \
  --confirm "COMMIT CARESYNC RETAINED 0039 TO 0042"
```

Emergency physical rollback has exactly two accepted evidence shapes.

Finalized rollback requires all three receipts:

```text
scripts/basic-release.sh rollback \
  --receipt /absolute/private/run/candidate-receipt.json \
  --commit-receipt /absolute/private/run/commit-receipt.json \
  --finalization-receipt /absolute/private/run/finalization-receipt.json \
  --confirm "ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039"
```

Interrupted intent-only rollback supplies the candidate receipt and exact
phrase, with no `--commit-receipt` or `--finalization-receipt` flag:

```text
scripts/basic-release.sh rollback \
  --receipt /absolute/private/run/candidate-receipt.json \
  --confirm "ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039"
```

The intent-only form is valid only when the candidate's release run contains
and validates its exact durable commit-attempt intent. Supplying only one
finalized-receipt flag is invalid.

An interrupted prepare is auto-recoverable only from this exact, private,
source-bound nine-line fence:

```text
status=preparing
run_directory=<absolute private direct child of the release-state directory>
release_source_root=<run_directory>/release-source
release_source_manifest=<run_directory>/release-source.manifest.json
release_source_manifest_sha256=<64 lowercase hexadecimal characters>
app_prior_login=<login|nologin>
ingest_prior_login=<login|nologin>
source_revision=0039_admissions_decision_spine
target_revision=0042_billing_policy_recert
```

Recovery must execute under the captured source and verify the bound manifest
before it may reconcile disposable PostgreSQL state or retire the preparing
fence. A prepared fence is never auto-reconciled.

## Hard ordering and stop line

Normal browser writers, Android devices and protected/offline queue replay must
remain quiesced until the organization-wide owner/administrator reconciliation
has completed and its capability postconditions have passed.

This ordering is mandatory because:

- the staff bootstrap deliberately omits the 0041 capability before
  organization reconciliation;
- the clock and child-operation backend paths already use the attested 0041
  foundation after retained startup; and
- an early Android clock-in could therefore create 0041 presence or exception
  rows while the device still presents capability-absent legacy behavior.

- [ ] Confirm the guarded commit and restricted-runtime certificate identify
  exact head `0042_billing_policy_recert`.
- [ ] Keep all ordinary product traffic and physical Android devices closed or
  fenced. Permit only the named acceptance operator's ordered traffic below.
- [ ] Using the cutover's authorized read-only count evidence, certify the
  initial 0041 boundary:

  ```text
  staff_room_presence_sessions       0
  staff_room_presence_events         0
  room_operational_exception_heads   0
  room_operational_exception_events  0
  ```

- [ ] Stop if any new table is non-empty before the explicit reconciliation.
  Do not explain unexpected rows as acceptance traffic after the fact.

## Stage 1 — pre-activation browser checks

Use an organization-wide `owner` or `administrator` with all of:

```text
facility:read
facility:manage
care_roster:read
staff:manage_educators
```

These checks create no 0041 business row. Authentication and realtime setup
may create ordinary session, audit or short-lived `realtime_tickets` rows
outside the four 0041 ledgers.

- [ ] `GET /api/v1/health` returns HTTP `200` with `status="ok"`.
- [ ] Open `/rooms`. The configuration workspace remains available and the
  **Activate live room operations** card appears.
- [ ] `GET /api/v1/room-safety/release-reconciliation/status` returns HTTP
  `200` with exactly this pre-activation relationship:

  ```text
  schema_version              "0041"
  foundation_available        true
  complete                    false
  active_facility_count       N
  completed_facility_count    0
  missing_facility_ids        every N active facility
  facility_set_sha256         64 lowercase hexadecimal characters
  organization_receipt_id     null
  ```

- [ ] Confirm the activation card displays the same `N` active facilities and
  states **No historical presence backfill** and
  **Configured-target evidence only**.
- [ ] `GET /api/v1/room-safety/capability` returns HTTP `503` with
  `detail.code="room_presence_release_reconciliation_required"`.

Stop for any of the following:

- `room_presence_foundation_unavailable`;
- HTTP `403` for the intended organization-wide release leader;
- a missing activation card;
- a status facility count/set that the operator cannot review; or
- capability HTTP `200` before this procedure's explicit reconciliation,
  unless a separately authenticated completed activation is first established.

Do not open Android and do not release normal writers yet.

## Stage 2 — one-time release reconciliation

- [ ] Review the facility count and scope shown on `/rooms`.
- [ ] Select the confirmation:

  > I reviewed this one-time activation scope and understand that CareSync
  > will derive current operational signals without inventing historical room
  > presence.

- [ ] Click **Activate live room operations** once.

The browser sends:

```text
POST /api/v1/room-safety/release-reconciliation
```

with:

```json
{
  "client_operation_id": "<protected UUID>",
  "expected_active_facility_count": "<N>",
  "expected_facility_set_sha256": "<reviewed digest>",
  "expected_facility_ids": ["<every reviewed active facility UUID>"]
}
```

Expected response:

- HTTP `200`;
- `schema_version="0041"`;
- `complete=true`;
- the exact reviewed facility-set digest;
- one non-null organization receipt;
- `facility_receipts.length=N`; and
- normally `replayed=false`.

If the response is uncertain, use the browser's protected retry. It must reuse
the same operation ID and may return `replayed=true`. Never invent a new
operation ID to resolve an uncertain result. A changed facility-set response
requires a fresh GET, a new human review and only then a new protected
operation.

### Exact reconciliation writes from an empty boundary

The command always creates:

- one pre-existing `audit_events` facility receipt for each of the `N` active
  facilities; and
- one pre-existing `audit_events` organization receipt.

For each distinct current condition `K`, it creates:

- one `room_operational_exception_heads` row in state `open`;
- one `room_operational_exception_events` row of type `opened`; and
- one PII-free `room_operational_exception.opened` realtime invalidation.

The possible current conditions are:

- confirmed facility or room staff below a configured operational target;
- an open actual-shift staff member without current room presence;
- a present child without an active room;
- confirmed children above configured room capacity; and
- facility- or room-scoped source integrity unknown.

Therefore, immediately after the first successful reconciliation:

```text
staff_room_presence_sessions       0
staff_room_presence_events         0
room_operational_exception_heads   K
room_operational_exception_events  K
audit_events increase              N + 1
```

If no current condition exists, `K=0` and both exception tables remain empty.
The pass creates no room-presence history, no backdated session, no inferred
presence and no remote notification. An exact replay creates no additional
receipt or 0041 row.

### Capability postconditions

- [ ] Re-read
  `GET /api/v1/room-safety/release-reconciliation/status`.
- [ ] Verify:

  ```text
  complete                    true
  completed_facility_count    N
  missing_facility_ids        []
  organization_receipt_id     non-null UUID
  ```

- [ ] `GET /api/v1/room-safety/capability` now returns HTTP `200`.
- [ ] Strictly verify the marker:

  ```text
  schema_version                         "0041"
  capability                             "live_room_presence_safety_board"
  runtime_available                      true
  online_only                            true
  operational_configured_target_only     true
  regulatory_compliance_certified        false
  self_presence_read_path                /api/v1/staff/self/room-presence
  self_live_board_path                   /api/v1/staff/self/room-safety/live
  start_path                             /api/v1/staff/self/room-presence/start
  move_path                              /api/v1/staff/self/room-presence/move
  end_path                               /api/v1/staff/self/room-presence/end
  manager_live_board_path                /api/v1/room-safety/live
  manager_exceptions_path                /api/v1/room-safety/exceptions
  ```

Keep normal writers and Android fenced until Stage 3 passes.

## Stage 3 — administrator read-only acceptance

Open:

```text
/rooms?view=live&facility_id=<facility UUID>
```

For each active facility, verify the browser issues:

```text
GET /api/v1/room-safety/live?facility_id=<facility UUID>
GET /api/v1/room-safety/exceptions?facility_id=<facility UUID>&state=all&limit=100
```

When an exception exists, this is an additional non-mutating route:

```text
GET /api/v1/room-safety/exceptions/<exception UUID>/action-target
```

- [ ] Every active room appears exactly once.
- [ ] With no leaked post-migration writer, every room initially has zero
  confirmed room-present staff and every retained open actual shift is
  unlocated.
- [ ] For every projection whose source facts are known:

  ```text
  open actual-shift staff
    = located room staff + unlocated on-duty staff

  located room staff
    = sum(room confirmed staff)

  confirmed on-site children
    = sum(room confirmed children) + children without an active room
  ```

- [ ] Unknown source data shows `—`, reason codes and an explicit `unknown`
  state. No partial positive state is displayed.
- [ ] Room and facility state is one of:

  ```text
  attention
  unknown
  not_evaluated
  no_active_configured_target_signal
  ```

- [ ] The UI does not label any state compliant, safe, adequately supervised
  or regulatory.
- [ ] The configured-target-only standing boundary is visible.
- [ ] The exception workspace says acknowledgement records review only and is
  not resolution.
- [ ] `/dashboard` and `/today` bounded summaries link to the exact selected
  facility live Rooms route.

Freshness behavior is part of acceptance:

- [ ] Immediately after canonical load, the board is current only while its
  `generated_at` is under 60 seconds old and realtime is connected.
- [ ] At 60 seconds, or after realtime disconnects, it displays
  **Stale — refresh required** and treats counts as historical evidence only.
- [ ] Manual **Refresh** restores current state only when realtime is also
  connected.
- [ ] A malformed, crossed-scope or partially incoherent response produces no
  live status instead of a partial board.

Do not click **Acknowledge review** during this read-only stage.

## Stage 4 — connected Android read-only baseline

Only after Stage 3 passes, open a current 0041-capable physical Android Staff
build. Use an active staff membership with:

```text
shift:clock
care_roster:read
child_safety:read
```

and active facility/room assignments.

- [ ] Before clock-in, confirm no unresolved protected care, shift or
  room-presence operation is present. Do not clear protected state to make the
  test pass. An existing queue requires a separate exact-operation recovery.
- [ ] `GET /api/v1/staff/self` includes the strict
  `live_room_presence_safety_board` marker.
- [ ] Android obtains current state through:

  ```text
  GET /api/v1/staff/self/room-presence
  GET /api/v1/staff/self/room-safety/live
  ```

- [ ] Verify the applicable baseline:

| Retained state | Expected self-presence projection | Expected staff live board |
|---|---|---|
| No open shift | `current_presence=null`; `eligible_rooms=[]`; `room_presence_required=false`; `decision_reason=no_open_shift` | `current_room=null`; `unavailable_reason=no_open_shift` |
| Pre-existing open shift with eligible rooms | No backfill; `current_presence=null`; `room_presence_required=true`; `decision_reason=room_selection_required` | `unavailable_reason=room_presence_required` |
| Open shift with no eligible room | `current_presence=null`; required `true`; `decision_reason=no_eligible_room` | `unavailable_reason=room_presence_required` |
| Incoherent source | Current and eligible rooms suppressed; required `false`; `decision_reason=source_integrity_unknown` | `unavailable_reason=source_integrity_unknown` |

- [ ] The app shows **Online** and
  **Realtime connected · canonical refetch on events**.
- [ ] No protected-storage warning is present.
- [ ] Presence and board projections become stale after 60 seconds and recover
  only after reconnect plus canonical refresh.
- [ ] Child mutations remain locked unless an open shift and fresh current
  presence match the exact selected facility and room.
- [ ] Clock-out remains available as the terminal escape from missing or
  incoherent room presence, although shift operations still require a server
  connection and are not queued offline.

## Stage 5 — controlled physical Android walkthrough

Keep the administrator live board open beside Android. Use an approved
maintenance window and an account whose movement will not surprise operators.
After activation, new actionable exception episodes and material worsening may
legitimately notify current owners/administrators.

### A. Room-select clock-in

Prefer an unscheduled clock-in for a staff member with at least two eligible
rooms and no open shift.

- [ ] On the **Clock** tab, choose **Clock in unscheduled**.
- [ ] The app opens **Choose the room you are entering** and does not guess.
- [ ] Cancel once. Confirm no clock-in request was sent and no row was created.
- [ ] Open it again and select the reviewed room.

Android sends:

```text
POST /api/v1/staff/self/shifts/clock-in
```

Expected:

- HTTP `201`;
- exact shift operation acknowledgement;
- one version-`1` current presence;
- `decision_reason=current_presence_confirmed`;
- `room_presence_required=false`; and
- source `staff_selected`, `scheduled_room` or `single_assignment` matching the
  actual decision.

A valid unambiguous clock-in atomically inserts one
`staff_room_presence_sessions` row and one
`staff_room_presence_events` row. An ambiguous or no-eligible-room clock-in
creates the shift but no presence row and may open an unlocated exception.

### B. Pre-existing-shift branch

If the selected staff member already has a retained open shift, do not clock in
again.

- [ ] On the **Room** tab, choose one server-advertised eligible room and press
  **Confirm \<room\>**.

Android sends:

```text
POST /api/v1/staff/self/room-presence/start
```

Expected HTTP `201`, a new version-`1` `staff_selected` session starting at the
server command time, and one immutable `started` event. The session must not be
backdated to the retained shift's original clock-in.

### C. Move and child-operation gate

- [ ] Choose another eligible destination.
- [ ] Enter an approved non-PII reason containing 5–500 normalized characters.
- [ ] Press **Move and confirm room**.

Android sends:

```text
POST /api/v1/staff/self/room-presence/move
```

Expected HTTP `200`:

- source session closes at version `2`;
- destination is a distinct version-`1` session;
- source end and destination start share the same server instant; and
- exactly one immutable `moved` event binds both sessions and rooms.

Without submitting a child mutation:

- [ ] Select the former room as the visible child workspace. Attendance,
  daily-care, medication, incident and daily-close mutations remain locked
  with the instruction to move to that child's room.
- [ ] Select the confirmed destination. Controls become eligible only while
  online, realtime-connected, canonically refreshed and under 60 seconds old.
- [ ] Disconnect or background the app. Positive/current controls become
  stale and unavailable.
- [ ] Reconnect and verify canonical refresh restores the gate.

### D. Clock-out

- [ ] On the **Clock** tab, choose **Clock out current shift**.

Android sends:

```text
POST /api/v1/staff/self/shifts/clock-out
```

Expected HTTP `200`:

- the actual shift closes;
- the current presence closes atomically at version `2`;
- one terminal presence event is appended when a current presence existed;
- no new presence session is inserted; and
- the refreshed projection is `no_open_shift`.

### E. Cross-client realtime result

- [ ] Each Android transition emits a PII-free `staff_room_presence`
  invalidation.
- [ ] The mounted administrator board performs canonical REST refresh before
  advancing its realtime cursor.
- [ ] A move decrements the source and increments the destination without a
  transient double-count.
- [ ] Clock-out removes the staff member from both open-shift and located-room
  counts.
- [ ] Any resulting exception opens, changes or resolves from canonical source
  facts rather than a client-side guess.

## First-row and mutation map

| Action | Legitimate 0041 effect |
|---|---|
| Migration, restart, health/status/capability/live GET | None |
| Realtime ticket creation | No 0041 business row; creates only a short-lived ticket outside the four new tables |
| Release reconciliation | Current exception head plus one `opened` event per current condition; no presence; remote notifications suppressed |
| Valid clock-in | Insert one presence session and one immutable presence event |
| Manual presence start | Insert one presence session and one immutable presence event |
| Ambiguous/no-eligible-room clock-in | No presence session/event; may create an unlocated exception head/event |
| Presence move | Close source session, insert destination session, append one `moved` event |
| Voluntary presence end | Close current session and append one `ended` event; shift remains open and unlocated |
| Clock-out | Close current session and append a terminal event when one exists; insert no new session |
| Access suspension/revocation | Close current session and append an access-revoked terminal event |
| Exception acknowledgement | Update an existing head and append one acknowledgement event; never resolves the source condition |
| Attendance, shift, target, room or access mutation | May open, materially change or resolve exception episodes |
| Canonical projection read | No write |

Explicit **End room presence** and **Acknowledge review** are valid but are not
part of the minimum retained smoke. Both create permanent operational evidence,
and a voluntary end may create an unlocated episode and post-activation manager
notification. Perform either only under separate authorization.

## Protected pre-cutover operation rule

An unresolved pre-cutover mobile care operation:

- may recover an already committed receipt without new presence evaluation;
- may not execute a previously absent write after cutover until fresh current
  presence matches its originally bound facility and room; and
- must never receive a replacement operation ID or automatic room retarget.

If Android shows protected pending work, stop this clean walkthrough and
follow the exact-operation recovery path. Do not delete application storage or
discard encrypted state.

## Acceptance failure conditions

Stop and preserve evidence if any of these occurs:

- any 0041 table was non-empty before reconciliation;
- the reviewed facility set changes between status GET and activation POST;
- reconciliation does not return and durably re-read as complete;
- activation produces presence history or a remote notification;
- a qualified staff bootstrap omits or weakens the strict capability marker;
- a retained open shift receives backdated room presence;
- a stale, offline, crossed-room or unknown projection enables child mutation;
- room actions send before protected storage loads successfully;
- an uncertain command is retried with another operation ID or changed intent;
- browser or Android shows a partial positive state after contract failure;
- realtime advances without the mounted canonical refresh completing; or
- clock-out is blocked solely because current room presence is missing or
  incoherent.

## Evidence to capture separately

The eventual signed acceptance record should bind, without secrets:

- candidate, commit and finalization receipt identifiers;
- checked-in source identity and exact database head;
- organization and reviewed active-facility-set digest;
- pre- and post-reconciliation 0041 row counts;
- reconciliation organization/facility receipt IDs;
- administrator identity/role and walkthrough timestamps;
- Android application artifact identity, device model and OS version;
- clock, start/move/clock-out operation IDs and server receipt IDs;
- redacted browser and Android screenshots;
- realtime/freshness observations;
- accessibility, privacy and operator notes; and
- explicit pass/fail disposition plus authorized signatures.

Create that evidence only after the work actually runs. Do not convert this
procedure into completed evidence by checking boxes in source control.

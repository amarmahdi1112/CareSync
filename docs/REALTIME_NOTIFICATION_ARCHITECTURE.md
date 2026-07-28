# Realtime and notification architecture

Last updated: 2026-07-16

## Scope and release boundary

This contract covers every enabled Basic workspace surface in the administrator
portal and both candidate and employed-staff modes of the Expo application. It
does not make the database outbox, a WebSocket frame, an operating-system push,
or a notification ledger row interchangeable. Each has one explicit job:

- a committed domain or audit record is the authoritative business change;
- a `realtime_events` row is a durable, tenant-scoped invalidation signal;
- a WebSocket transports ordered invalidations to an active client;
- a `user_notifications` row is the authenticated user's durable inbox record;
- a delivery job requests an optional, generic wake-up through a registered
  device or browser channel; and
- the destination page reloads canonical authorized REST data before it shows
  the result as current.

Remote delivery is an optional edge. A missing provider, denied permission,
expired token, sleeping browser, disconnected socket, or lost push must never
make a business command fail or make a page permanently stale.

## Non-negotiable invariants

1. **Commit first.** Realtime and delivery records are written in the same
   database transaction as their source change or are derived idempotently from
   its committed outbox record. A provider is never called inside the business
   transaction.
2. **Invalidate, then reload.** A realtime payload identifies the affected
   domain; it is not rendered as canonical entity state. The client reloads the
   authorized REST projection and only then persists the delivered cursor.
3. **Fail closed on access loss.** WebSocket close `4403`, an unauthorized REST
   refresh, organization removal, or assignment removal clears affected local
   state and forces session/access revalidation.
4. **Tenant and user scope are server-owned.** Clients cannot choose a user or
   organization when registering a delivery endpoint. The authenticated
   session supplies ownership. Organization switching creates a new realtime
   ticket and discards the previous organization's page cache.
5. **No sensitive lock-screen content.** Remote/desktop notifications use a
   generic title and body. Child names, medical details, incident details,
   credential contents, attendance state, and hiring terms remain behind
   authentication in the notification ledger and destination API.
6. **Strict navigation.** Notification actions use a finite allowlist of
   internal CareSync routes and validated identifiers. They never accept an
   arbitrary URL, script, or cross-organization destination.
7. **Idempotent endpoints and jobs.** A stable installation/device identity plus
   provider/token rotation cannot create an unbounded number of active
   registrations. Enqueue and dispatch use stable deduplication keys. Invalid
   or unregistered endpoints are revoked without retry storms.
8. **Preferences are enforced server-side.** User category preferences affect
   optional notification creation/delivery, while mandatory security/system
   notices cannot be disabled. Authorization never depends on a preference.
9. **Push is not realtime correctness.** Foreground sockets, app resume, tab
   visibility, manual refresh, and command responses all converge through the
   same canonical reload path. A push is only a prompt or wake-up hint.
10. **Permission is contextual.** Browser and mobile notification permission is
    requested only after a user gesture and after the product explains its
    value. Refusal is respected and does not block normal application use.

## Client convergence lifecycle

For every authenticated client:

1. Restore and validate the session.
2. Fetch canonical page/workspace data and notification summary.
3. Obtain a one-time realtime ticket for the active organization or candidate
   identity.
4. Connect after the last successfully applied cursor.
5. On an event, coalesce related invalidations and refresh the visible page plus
   shared shell counters.
6. Persist the event cursor only after every required refresh succeeds.
7. On `reset_required`, keep the old cursor, reload canonical data, then resume
   from the server's latest available cursor.
8. On reconnect, app foreground, document visibility, or network recovery,
   perform a canonical refresh even when no event was observed.
9. On authorization loss, clear protected state before showing a new access
   boundary.

Event bursts should be debounced/coalesced by domain so a bulk import, room
approval, or attendance wave does not turn into one REST request per row. A
page may optimistically reflect its own successful command response, but the
next invalidation still reconciles it with the server.

## Enabled-surface coverage target

| Surface | Canonical domains refreshed | Notification expectations |
|---|---|---|
| Dashboard | command summary, attendance, rooms, staffing | foreground activity cue; durable items for actionable exceptions |
| Today/daybook | room roster, shift access, care records, attendance | generic wake-up only for assigned actionable work |
| Families | families, guardians, child links | no routine push; refresh on childcare/organization changes |
| Child profile/directory | profile, enrollment, photo metadata, safety context | no routine push; refresh on childcare/room changes |
| Rooms | facilities, programs, rooms, roster and placement approvals | assignment/placement items where user action is required |
| Attendance | roster and current attendance day | operations alerts only where action is required |
| Medication | room medication day and plan/history state | time-sensitive operational item without medical lock-screen content |
| Incidents | room context, incident list/detail/history | role-scoped action item without incident detail on lock screen |
| Staff/access | membership, roles, assignments, invitations | assignment and account/access items |
| Jobs/hiring | listings, applications, interviews, offers, provisioning | hiring workflow items for the correct employer/candidate identity |
| Settings | organization, facilities, programs, rooms, notification preferences | system/account items; delivery-permission state is visible here |
| Candidate app | jobs, applications, interviews, interests, offers, profile/credentials | generic local/remote alert with authenticated deep link |
| Employed staff app | workplace, shift, roster, care, medication, incidents, careers | generic local/remote alert; foreground banner and canonical refresh |

The detailed route/event test matrices live beside each client so they can be
kept synchronized with code:

- `frontend-redesign/docs/REALTIME_COVERAGE_MATRIX.md`
- `CareSync-Staff/docs/MOBILE_REALTIME_NOTIFICATION_COVERAGE.md`

## Delivery state machine

A delivery job progresses independently of its notification ledger row:

`pending|retry -> processing -> receipt_pending -> processing -> sent`

The first provider response is only an accepted Expo ticket. It moves the row
to `receipt_pending`; it is not recorded as delivered. A later receipt moves
the row to `sent`, whose meaning is **provider handoff to FCM/APNs**, not device
display or human reading. Recoverable send/receipt errors use bounded retry
states and next-attempt times. Permanent token/endpoint errors mark the job
`dead` and revoke that registration. Revocation/preferences can instead produce
`cancelled` or `suppressed`. A lease/attempt timestamp allows another worker to
recover abandoned `processing` work without holding a database lock during
provider latency. The worker records only provider-safe identifiers and error
classes; it must not persist secrets or sensitive message bodies in logs.

Local development defaults to provider-disabled operation: ledger, realtime,
registration, enqueueing, deduplication and worker selection remain testable,
while no external notification is transmitted until a provider is explicitly
configured. That default prevents accidental messages during database-backed
local testing. The explicit worker entry point is
`backend/scripts/uv.sh run python scripts/push_worker.py --once` (or
`--poll SECONDS` from the project root); when provider configuration is absent
it exits without claiming work, changing delivery state, or making a network
request.

## Platform behavior

### Shared authenticated delivery API

- `POST /api/v1/notifications/push/subscriptions` idempotently registers or
  rotates the authenticated user's device endpoint by `device_id`.
- `GET /api/v1/notifications/push/subscriptions` returns endpoint metadata but
  never the delivery address or Web Push encryption material.
- `DELETE /api/v1/notifications/push/subscriptions/{id}` and
  `POST /api/v1/notifications/push/subscriptions/revoke-all` wipe delivery
  addresses and cancel pending work.
- `GET /api/v1/notifications/push/deliveries` exposes bounded delivery evidence
  to the owning user without provider secrets.
- `POST /api/v1/notifications/realtime/tickets` issues a one-use ticket for
  `/api/v1/notifications/realtime/ws`. This user-private stream covers inbox
  creation/read state, preference and subscription changes, and delivery state;
  it is separate from the active organization's domain stream.

### Administrator browser

- The authenticated shell owns one realtime lifecycle across route changes.
- In-app banners and the inbox work without browser notification permission.
- Desktop notifications are capability-gated, requested from a button, and use
  generic content. They are best-effort while the portal is open.
- Durable background Web Push is a separate production adapter requiring HTTPS,
  a service worker, VAPID/provider configuration, endpoint revocation and
  deployment acceptance tests.

### Expo staff/candidate application

- Foreground in-app banners and canonical refresh work in Expo Go.
- Remote push registration is optional and cannot block login, onboarding,
  careers, clocking or care workflows.
- Real remote notification testing uses a signed development build with the
  Expo notifications native module and project credentials. The application
  records permission/unavailable states clearly instead of pretending delivery
  is active.
- Notification taps enter through the same allowlisted navigation dispatcher
  whether the app was foregrounded, backgrounded or cold-started.
- The local Android development-client APK has been installed and launched on
  a Pixel through ADB reverse tunnels, validating native-module loading and
  local API/Metro connectivity. The Expo/EAS project is now linked and a signed
  development build completed successfully. Android FCM credentials, provider
  enablement and real remote delivery have not yet been completed end to end.

## Known production hardening work

- Worker discovery currently scans active users; production needs indexed or
  partitioned work selection, per-user failure evidence and metrics.
- Expo receipt calls are one delivery at a time rather than batched.
- Expired tickets, old realtime events and terminal deliveries do not yet have
  an automated retention job.
- Revoking a subscription does not eagerly remove already
  `receipt_pending` receipt work. It cannot send new content, but can cause a
  stale provider receipt lookup.
- Delivery is intentionally at-least-once around worker crashes/token transfer;
  generic PII-free payloads limit the consequence of a duplicate wake-up.
- The marketplace WebSocket still needs the same bounded write/backpressure
  timeout used by the other streams.
- Local startup proves process liveness only. Production requires a supervisor,
  restart policy, readiness checks and alerting for the API and worker.
- Delivery addresses are protected by tenant/user RLS and are omitted from
  list APIs, but are not separately application-encrypted at rest.

## Verification gates

Completion requires automated coverage for tenant/user registration ownership,
token rotation, revocation, preferences, enqueue deduplication, retry/lease
recovery, generic payload content, strict routes, cursor reset, refresh-before-
advance, reconnect/app-resume refresh, organization switching and access loss.
It also requires production builds and physical-device smoke tests for denied
permission, foreground, background, terminated-app tap, expired session,
removed assignment and notification from a different organization.

Provider credentials and actual production delivery remain deployment work, not
a reason to weaken the local contract or claim a notification was delivered
when it was merely queued.

# CareSync admin realtime and notification coverage

## Guarantees

- One organization-scoped WebSocket lives above the router for the signed-in organization. Pages register canonical REST reloads with the central registry; an event cursor is written only after every matching mounted reload succeeds.
- A separate user-private notification WebSocket drives the global inbox and unread badge. Its frames contain safe metadata only; the UI fetches authenticated notification ledger records before advancing its private cursor.
- Organization changes recreate the organization registry and cursor namespace. Ready frames for another organization or private ready frames for another user are rejected.
- Browser focus, visibility return, and network recovery run one coalesced canonical refresh across mounted pages. Notifications also retain a visible-only 60-second poll as a bounded recovery path.
- Browser desktop permission is requested only from the explicit “Enable private desktop alerts” button and only in a supported secure context (HTTPS or localhost). Operating-system title/body text is always generic. Authenticated detail appears only in the portal.
- Foreground updates use an accessible in-app toast. Desktop alerts are emitted only when the document is hidden or unfocused, preventing double alerts.
- Deep links are allow-listed internal routes. Cross-organization items require an active membership and explicit confirmation before the session switches workspaces.

## Enabled route matrix

| Route | Canonical refresh | Realtime entities |
|---|---|---|
| `/onboarding` | Onboarding snapshot, programs, rooms; dirty drafts are preserved with a conflict banner | organization, onboarding, facility, program, room |
| `/dashboard` | Family statistics, room workspace, every active-facility attendance roster | family, child, enrollment, facility, room, attendance |
| `/today` | Room workspace and selected care room-day | daily care, attendance, enrollment, child, room |
| `/families`, `/families/:id` | Directory or mounted family detail | family, child, enrollment |
| `/children`, `/children/:id` | Roster/profile and program placement directory | child, family, enrollment, program, room |
| `/rooms` | Facility/program/room workspace and selected facility roster | organization, facility, program, room, enrollment, child |
| `/attendance` | Selected facility/date roster | attendance, enrollment, child, room, facility |
| `/medications` | Room context, plans, consent, and administration records | medication, attendance, enrollment, child, room |
| `/incidents` | Room context and complete incident list | incident, attendance, enrollment, child, room |
| `/staff` | Members, invitations, roles, assignments, credentials, and current shifts | invitation, membership, user, shift, credential, room |
| `/jobs` | ATS workspace and employer credential notices | job, candidate, application, interview, offer, credential, marketplace interest |
| `/transport-registry` | Exact bounded 0032 staff evidence, decisions, vehicles, and review history | transport registry |
| `/settings` | Organization and facility settings allowed for the current role | organization, onboarding, facility, program, room, user |

Public marketing, login, activation, and password-reset routes do not hold organization live data and therefore do not open realtime connections.

## Notification delivery layers

1. The transactional notification ledger remains the source of truth.
2. The user-private stream sends only an invalidation; the portal reloads list and summary from REST.
3. The inbox and unread badge update in place. New unseen records create a deduplicated, accessible toast.
4. If the user opted in and the portal is backgrounded, the browser creates a generic desktop notification tagged by ledger ID.
5. Backend push preference is separately configurable. Durable service-worker web push is intentionally outside this while-open portal layer; registered mobile delivery uses the backend subscription/delivery pipeline.

## Verification

Focused tests cover tenant/user boundary rejection, same-origin WebSocket construction, replay-reset semantics, cursor-after-refresh ordering, route-matrix completeness, cross-organization redaction, internal-link allow-listing, foreground alert suppression, secure-context gating, and deduplication.

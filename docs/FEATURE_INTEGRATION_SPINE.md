# CareSync feature integration spine

Status: implemented source-of-truth and retained runtime wiring, updated
2026-07-23. The original no-migration tranche was recorded at 0028; the current
retained database is `0039_admissions_decision_spine`.

## Runtime contract

1. A command commits one canonical entity plus its audit/realtime outbox in the backend.
2. Realtime is a quiet invalidation hint, never durable truth. Every matching mounted consumer
   reloads canonical REST and the event cursor advances only after those reloads succeed.
3. Human-attention notifications are separate. They exist only when a person must decide,
   approve, respond, or remediate; routine cross-screen synchronization creates no notification.
4. Notification actions use the closed internal-route registry. The destination is re-read under
   the current identity/organization before the client focuses a record or declares it stale.
5. The executable portal graph lives in
   `frontend-redesign/src/realtime/featureIntegrationManifest.ts`. The dependency tests fail when
   a consequential producer has a mounted consumer that does not subscribe to its entity.
6. The backend/frontend vocabulary lives in `contracts/realtime_entity_contract.json`. Backend
   source analysis rejects unknown or unbounded command entity names, while frontend tests require
   every canonical organization-outbox entity to have at least one mounted canonical consumer.

## Canonical communication matrix

| Canonical entity / event family | Command producers | Mounted admin consumers | Mounted mobile consumers | Human-attention rule and safe next action | State |
| --- | --- | --- | --- | --- | --- |
| `organization`, `organization_onboarding` | Registration, onboarding, Settings | Persistent session shell, Onboarding, Settings, Rooms | Staff bootstrap and candidate bootstrap use canonical session reads | Notify only for a system/security action; `/dashboard` or `/settings` from the closed registry | Covered; an `organization` event quietly refreshes the selected organization record and every organization choice before its cursor commits, while any tenant or authority mismatch fails closed |
| `facility`, `facility_program`, `room` | Onboarding, Settings, Rooms | Dashboard, Admissions, Today, Children, Rooms, Attendance, Medication, Incidents, Staff, Rota, Settings | Staff room, attendance, care, medication, incident, close, clock/rota | Quiet invalidation. A placement warning links to the exact owning child/family/room workflow, not a broadcast alert | Covered in portal manifest; Today now includes `facility_program`, and Child profile now includes `facility` |
| `family` | Families | Dashboard, Admissions, Families, Children | Staff release/safety bootstrap when relevant | Alert only for a concrete enrollment/readiness blocker; safe action is the exact `/families/:id` review | Covered |
| `child` | Children/profile/photo | Dashboard, Admissions, Families, Children, Rooms, Attendance, Today, Medication, Incidents | Staff roster, attendance, care, medication, incident, close | Routine edits are quiet. Readiness work opens exact `/children/:id` or linked family review | Covered |
| `enrollment` | Children enrollment, Rooms placement (including each item in a batch approval) | Dashboard, Admissions, Families, Children, Rooms, Attendance, Today, Medication, Incidents | All roster/care surfaces | Alert only when a person must resolve placement/readiness; action resolves the canonical enrollment before focusing | Covered; a batch emits one canonical `enrollment` event per successful placement and never invents a batch entity |
| `admission_application`, `admission_waitlist`, `admission_offer` | Administrator Admissions decision commands | Admissions pipeline, detail, waitlist, conversion and recovery | None in this bounded release | Submitted/converted attention only; `/admissions/applications/:id` is re-authorized and canonically reloaded before focus | Covered in retained 0039; exact retry, deterministic waitlist, duplicate-reviewed conversion and PII-free invalidation are released, while the derived remediation queue remains separate |
| `authority_person`, `authority_evidence`, `authority_evidence_object`, `release_authorization`, `release_rule`, `consent`, `consent_policy`, `child_authority_head` | Family authority workspace | Family profile/authority panels; owner/admin child profile minimum-necessary summary | Staff release context and capability-gated verified-release flow | No alert for ordinary synchronization. A safety decision stays in the private family workspace; a checkout re-evaluates current authority server-side | Covered in source and retained schema: the generic head invalidation refreshes family, child-summary, and staff release consumers; exact child receipt targets never substitute a nearby record. Retained activation remains absent, so verified release stays safely unavailable |
| `attendance_day`, `attendance_release` | Admin Attendance; staff check-in/out and verified release checkout | Dashboard, Today, Attendance, Medication, Incidents | Staff room, attendance, care, medication, incident, close | Quiet invalidation. Operational errors stay local to the exact idempotent command; no notification spam | Covered |
| `daily_care_record` | Today and staff care daybook | Today and its Daily Close subview | Staff daily care and close | Quiet invalidation | Covered |
| `medication_plan`, `medication_administration` | Admin/staff Medication | Medication; Today Daily Close for administrations | Staff medication and close | Notify only for authorization revoked or plan activation; exact action `/medications?plan=:medication_plan_id` re-reads the authorized plan without trusting room/date metadata | Covered; stale, cross-tenant, malformed, or substituted plan targets fail closed and no fallback plan is selected |
| `incident_record` | Admin/staff Incidents | Incidents; Today Daily Close | Staff incidents and close | Review/return/finalize/external-follow-up only; exact action `/incidents?incident=:incident_id` is canonically resolved | Covered |
| `staff_invitation`, `organization_membership`, `user`, `staff_shift` | Staff & Access, authentication, staff clock | Staff, Rota, Hiring handoff, Settings; assignment-sensitive care views also rebuild scope | Staff room/attendance/clock/rota/workforce; candidate timeline during provisioning | Scope changes notify only the affected staff identity; `/today` reopens the canonical assigned workspace. Auth-version change revokes stale streams/tokens | Covered; target identity is fail-closed on authorization change |
| `staff_schedule`, availability/time off/templates/coverage targets/rotations/open shifts/engagements/substitutes/swaps | Rota manager and staff workforce/exchange commands | Rota and Staff current-clock projection where applicable | Staff clock, rota, workforce, exchange | Notify only for a response/decision. Exact schedule action is `/staff-rota?schedule=:schedule_id`; workforce actions use `/staff-rota?focus=:entity_type&record=:entity_id` and resolve their facility, week, parent, and membership from canonical server state | Covered; exact availability, time-off, rotation, open-shift, engagement, substitute, and swap rows focus in their owning tab, while stale or unauthorized targets fail visibly without selecting a fallback |
| `job`, `candidate`, `application`, `interview`, `offer`, `credential`, `marketplace_interest`, `screening_share` | Employer ATS and candidate marketplace | Jobs & Hiring; Staff after provisioning; Settings/session after membership creation | Candidate jobs, applications, profile/onboarding | Application/interview/offer/credential decisions only; `/jobs?view=applicants&application=:application_id` or candidate timeline, resolved from fresh canonical ATS state | Introduced in retained 0038 and carried unchanged into retained 0039: exact candidate-owned tenant rows use their private stream, while the forced-RLS public-safe catalog outbox durably replays public listing invalidations and last-listing removal to unaffiliated candidates without exposing drafts, organization identity, candidates, applications or free text |
| `transport_registry` | Capability-gated manager/staff registry commands | Driver & Vehicle Registry | Staff transport registry | Evidence/readiness review only; `/transport-registry` / `staff_more`. Never creates child transport authority or dispatch readiness | Covered when the runtime capability is present; schema is retained at 0039, while child-transport and dispatch authority remain false |
| `notification`, `notification_preference`, `notification_delivery`, `push_subscription` | Private notification ledger and delivery worker | Admin inbox/browser presentation | Mobile inbox/OS generic reference | The ledger is the source; OS payload is generic and contains only the notification reference. Opening re-reads the private ledger | Covered; provider delivery remains disabled until explicit deployment configuration |

## Mounted surface coverage

The persistent session shell is manifest-driven for canonical organization identity and workspace
choices. Portal routes are manifest-driven for Dashboard, Admissions, Today/Daily Close, Children list and
profile, Rooms, Attendance, Medication, Incidents, Staff, Rota, Hiring, and Settings. Families uses
the same entity contract across its directory/profile hook plus the separately permission-gated
authority panels. Onboarding already uses the same canonical entity set and retains its explicit
dirty-draft conflict behavior.

Mobile behavior now consumes the executable selector contract in
`CareSync-Staff/src/api/mobileRealtimeSelectors.ts`. An organization event for a projection owned
only by the mounted medication, incident, daily-close, rota, exchange, workforce or transport
surface refreshes that surface and waits for its exact acknowledgement before the cursor commits.
If no matching surface is mounted, the cursor may advance because every one of those surfaces
performs a canonical read when mounted. Shared staff bootstrap, roster, attendance, daily-care,
actual-shift, release-authority and unclassified future entities still rebuild the parent
operational workspace; this is intentional because those facts gate multiple tabs or the
identity/access boundary.

Candidate tenant events for the bounded job/application/interview/offer/interest/share family
reload the career core (public jobs, candidate applications and employer interests) without
re-reading unrelated personal/screening modules. Identity, profile, credential, membership,
unknown and user-private invalidations retain the full career-workspace read. Reset/replay
overflow and foreground resume also remain full canonical rebuilds because their missing entity
set cannot be selected safely. Identity changes, surface unmounts, failed reads and replaced
sockets reject the checkpoint; routine selector refreshes remain notification-free.

## Enforced checks

- `featureIntegrationManifest.test.ts` requires every enabled authenticated portal feature and
  onboarding to exist in the manifest.
- Each route-backed portal manifest entry reuses the exact `realtimeRouteCoverage` array by
  identity, preventing a second documentation-only graph. The always-mounted session shell owns
  one deliberately narrow `organization` selector and is covered by a runtime-wiring test.
- Family-authority migration, detector and contract tests require `child_authority_head` as the
  only canonical database-trigger identity, forbid legacy `release_context`, require a null entity
  ID and reject child/family identity leakage.
- Every declared consequential producer-to-consumer edge must include the canonical entity in the
  consumer selector.
- Attention reasons and action destinations must be paired; quiet synchronization cannot silently
  grow an alert destination.
- `realtimeRegistry.test.ts` proves tenant isolation and requires all canonical refresh promises to
  settle before the cursor can advance.
- Staff `mobileRealtimeSelectors.test.ts` proves representative care, medication, incident, rota,
  workforce, exchange, transport and marketplace selection; ordered batching; failed-read
  no-advance; unmount/identity replacement; and reset-before-checkpoint behavior.
- `test_basic_realtime_entity_contract.py` inventories Basic audit, ATS, and direct organization
  event producers and fails on an unknown literal or a newly introduced unbounded forwarder.
- `test_basic_realtime_command_outbox.py` runs the historical `0028` command-spine migration on a disposable SQLite
  database and proves representative family, child, enrollment, room, attendance/care, ATS, and
  workforce commands reach the transactional organization outbox with the expected bridge source.
- The batch-placement regression proves a failed batch leaves no placement event behind and a
  successful batch emits one `enrollment` event per placement—never `enrollment_batch`.

## Retained closure and next bounded slice

The former P1 durable public-job removal gap is closed by retained
`0038_public_job_catalog_outbox`. Public listing changes and closure of an
organization's last public listing now have a privacy-safe replay path for
unaffiliated candidates; canonical REST remains display authority. Retained
`0039_admissions_decision_spine` adds the three admission entity families and
their administrator consumers without conflating ATS `application`. Product
slice `0040_billing_readiness_batch_planner` is verified in source and retained
live read-only API acceptance without a migration. Its setup consumer treats
billing, family, child, enrollment, facility and facility-program events as
quiet invalidation hints, clears stale preview state and reloads canonical REST.
No notification is added merely for routine catalog or planner
synchronization. Signed-in administrator browser-click acceptance for the setup
surface remains pending.

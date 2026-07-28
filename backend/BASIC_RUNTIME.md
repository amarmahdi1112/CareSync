> [!IMPORTANT]
> **Retained-release commands supersede legacy instructions below (2026-07-26).**
> The remainder of this document is preserved verbatim for product and audit
> context. For the retained `0039_admissions_decision_spine` to
> `0042_billing_policy_recert` release, do not execute any older startup,
> migration, cutover, restore, or rollback command found below. The canonical
> contract is `scripts/BASIC_RELEASE_CLI_CONTRACT.md`. Its current two-phase
> operator flow is:
>
> ```text
> scripts/basic-release.sh prepare [--clone-port 55000..60999]
> scripts/basic-release.sh commit \
>   --receipt /absolute/private/run/candidate-receipt.json \
>   --confirm "COMMIT CARESYNC RETAINED 0039 TO 0042"
> ```
>
> Finalized emergency rollback requires the candidate, commit and finalization
> receipts. Interrupted intent-only rollback supplies only the candidate receipt;
> it omits both finalized-receipt flags and is accepted only when the run contains
> its exact durable commit-attempt intent. Both use the exact confirmation phrase
> `ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039`.
>

# CareSync Basic database identities

CareSync Basic separates schema ownership from request-time data access.

- **Migration identity:** owns the schema in the populated retained Basic
  `caresync` database, runs deliberate Alembic operations, and applies grants.
  It is never configured on the FastAPI process.
- **Runtime identity:** `caresync_basic_app`, created by
  `scripts/bootstrap_basic_runtime_role.sql`. It cannot create databases,
  roles, schemas, or tables and cannot bypass RLS. The retained legacy feature
  surface still requires broad, table-specific `SELECT`, `INSERT` and `UPDATE`
  grants. Table `DELETE` is limited to `marketplace_jobs`,
  `marketplace_profile_photos` and `child_profile_photos`; append-only ledgers
  retain their narrower grants. Do not summarize this role as globally
  insert/select-only or as having no operational deletes.

The staged 0029 authority boundary is deliberately tighter than the legacy
surface. A/A1 grant only the direct person/evidence/head DML their command
services require. A2 adds exact INSERT lanes and narrow revoke/withdraw-column
UPDATE grants for authorization, rule and consent commands; no authority table
permits runtime `DELETE`. B exposes educator release context only through its
hardened projection callable rather than direct privileged reads. D exposes
normal release only through exact restricted writer callables; the ordinary
runtime role receives no general release-snapshot or attendance-table DML.

The retained local database and checked-in launcher now share
`0039_admissions_decision_spine`. Revision `0038_public_job_catalog_outbox` is
the immediately preceding release, while `0036_billing_manual_mode` remains the
manual-billing protocol boundary. The guarded 0039 cutover used the launcher to
quiesce writers, create and verify the complete database/evidence recovery set,
prove the exact 16,445-row disposable restore, and migrate to the reviewed
revision exactly.

Revision 0039 adds six forced-RLS admissions tables. The restricted runtime
receives bounded reads, command-path inserts and exact column-level lifecycle
updates, but no admission-domain `DELETE`, event/conversion update or ownership.
Command-row and deferred bundle guards bind the organization, actor, operation,
versions, event, receipt, audit and realtime provenance. Startup and bootstrap
attest the exact schema, constraints, indexes, policies, grants, triggers,
function definitions, owners and fixed search paths before the capability is
available. Revision 0039 grants no parent/public admissions, automatic room
placement, family-release activation, billing/payment/funding or transport
authority. Use the same guarded launcher for every future retained-database
maintenance operation:

```bash
CARESYNC_BASIC_RESTORE_VERIFY_PORT=55447 \
CARESYNC_BASIC_RESTORE_VERIFY_USER=postgres \
  ../scripts/start-basic.sh
```

Do not run `alembic upgrade head` or `alembic check` directly against the
retained runtime. Run source-head/model-drift gates only against an explicitly
disposable target.
`scripts/start-basic.sh` is pinned to the same checked-in released revision and
performs no Alembic command when the retained database already matches it.
Startup also requires `alembic_version` to contain exactly one nonblank
revision; zero-row, blank or multi-head provenance fails before backup or
migration.
After all backup/restore and repeated writer gates pass, the launcher adds the
protected-target opt-in only to its one exact Alembic subprocess. It never
exports or persists that value.

`scripts/stop-basic.sh` validates managed PID command lines and working
directories. It also discovers the actual Uvicorn listener on port 3002 when a
PID file is stale or missing, accepts only this project's `app.main:app`, waits
for it to exit, and refuses to stop PostgreSQL while any matching API process
or any foreign port-3002 listener remains.

The local migration environment must use the schema-owner identity on the
isolated Basic database at port 5434. Alembic prints a password-free target
summary before online operations. Every Alembic command aimed at protected
local ports 5432, 5433, or 5434 fails closed unless the operator supplies the
exact, command-scoped
`CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true` opt-in. Test environments
cannot override that refusal and must use a disposable port. Do not put the
opt-in in `.env`, shell profiles, service definitions, or shared scripts; pair
it with the backup and target-verification procedure for the one deliberate
command only. Programmatic migration checks should set an explicit disposable
`sqlalchemy.url` instead. Seven focused tests cover this protected-port guard.
FastAPI is started separately with the restricted
`caresync_basic_app` credentials injected by its start process; do not copy the
schema-owner credentials into that process.

For a password-authenticated environment, set the runtime password out of band:

```sql
ALTER ROLE caresync_basic_app PASSWORD '<secret-from-secret-manager>';
```

Configure FastAPI with `DATABASE_USER=caresync_basic_app`; never give it the
migration owner's credentials. The API sets transaction-local
`app.current_user_id` before membership resolution and
`app.current_organization_id` after an active membership is proven. Explicit
organization predicates remain mandatory in application queries; RLS is the
independent second boundary.

The local launcher fixes `CARESYNC_BASIC_APP_USER` to that exact role and
rejects any override before it stops a running service. When local PostgreSQL
requires password authentication, inject the runtime secret only for the
launcher process as `CARESYNC_BASIC_APP_PASSWORD`; the launcher forwards it as
`DATABASE_PASSWORD` without printing it. Peer/trust-authenticated local setups
leave it unset. A direct `uvicorn app.main:app` command instead inherits
`backend/.env`, so that file must never contain the migration owner when used
to start a writable API.

For staged 0029 administrator ORM authority queries, the API sets those GUCs
only after resolving an active owner/administrator membership, and the
privileged-actor helper fails closed when context is absent or malformed. This
protects API-managed administrator queries. B educator reads and D release
writes use their separate hardened projection/writer boundaries. None of this
is a boundary against arbitrary SQL executed with the shared runtime role,
because that role can set custom GUCs. A future commandized membership/role
boundary must remove that production limitation; do not claim the staged
helper alone proves shared-role SQL isolation.

For private/local manual billing, the launcher defaults to manual server mode
and derives the sole active organization only when that selection is
unambiguous. More than one active organization requires
`CARESYNC_BASIC_BILLING_MANUAL_ORGANIZATION_IDS`. This allowlist exposes the
owner activation workflow; it does not create the immutable activation row.
Set `CARESYNC_BASIC_BILLING_MODE=disabled` to keep the workspace unavailable.
Manual mode never enables a processor, money movement, automatic issue,
delivery, refund, tax advice or funding submission.

## Confidential staff-evidence ingest readiness

The 0030 staff-screening schema and its encrypted upload pipeline are
separate capabilities. When 0030 is present, startup checks the private staff
vault, the configured 32-byte encryption key, and one inert scanner probe. New
screening uploads are enabled only when that complete local pipeline is ready.
Existing document history, authenticated content reads, confirmations,
sharing, and employer review remain available when upload is paused. The
public health response exposes only `ready` or `unavailable`; it never returns
vault paths, key diagnostics, scanner paths, document names, or evidence data.

Configure the following only in the server environment:

- `STAFF_SCREENING_VAULT_PATH`: an absolute private path outside this source
  tree and every static/public upload directory. If omitted, CareSync uses the
  private Application Support location documented in `Settings`.
- `STAFF_SCREENING_VAULT_ENCRYPTION_KEY`: URL-safe base64 for exactly 32 random
  bytes. An empty or invalid value keeps upload unavailable.
- `STAFF_SCREENING_VAULT_KEY_ID`: the stable identifier recorded beside every
  ciphertext written by this key.
- `FAMILY_EVIDENCE_SCANNER_PATH`: an optional absolute scanner executable. If
  omitted, the adapter prefers `clamscan`. CareSync invokes it with
  `--alert-exceeds-max=yes`, so a ClamAV resource-limit exhaustion cannot be
  reported as clean. `clamdscan` fails closed until an explicit contract can
  attest the daemon-side `AlertExceedsMax` policy; client configuration is not
  silently trusted.
- `FAMILY_EVIDENCE_SCANNER_TIMEOUT_SECONDS` and
  `FAMILY_EVIDENCE_SCANNER_MAX_DEFINITION_AGE_HOURS`: bounded scan and
  definition-freshness policy.

Do not change the active staff-vault key or its ID as an informal rotation.
The current runtime has one active key, not a historical keyring; a
change can make older ciphertext unreadable. Key custody, historical-key
coverage, rotation/rewrap receipts, crash reconciliation, retention/legal hold,
and signed-in operator proof remain explicit release gates. Pending cutovers at
or after 0030 now require the backup-bound staff/transport bundle, its
independent verification, a no-clobber disposable vault restore and a private
receipt before Alembic may touch the retained database. The encrypted bundle
still excludes the key, so approved offline key custody remains mandatory. The
2026-07-22 synthetic-only real-scanner adapter
proof is recorded in `docs/FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`; it does
not establish the complete encrypted staff-vault pipeline or authorize upload
when the remaining readiness inputs are absent. None of this authorizes child
transport.

Child profile photos are decoded and normalized before storage in the
tenant-RLS `child_profile_photos` table. They are never statically mounted.
Authenticated reads use `GET /api/v1/children/{child_id}/photo`; educator reads
also require a current active enrollment in one of the educator's assigned
rooms. Input defaults to a 6 MiB byte limit, a 25-million-pixel decode limit,
and a 1024-pixel maximum output edge. These can be reduced with
`CHILD_PROFILE_PHOTO_MAX_BYTES`, `CHILD_PROFILE_PHOTO_MAX_PIXELS`, and
`CHILD_PROFILE_PHOTO_MAX_EDGE`.

Room daybooks are stored as a mutable `daily_care_records` projection backed by
append-only `daily_care_record_events`. Care writes lock the attendance day,
its intervals, and then its care records; every care time must remain inside an
actual same-service-date attendance interval. Historical placement comes from
the immutable `attendance_days` snapshot, so moving an enrollment or
deactivating a room does not erase owner/administrator access to prior records.
Educator reads remain limited to today's active assigned rooms, and the room
daybook requires both `care:read` and `child_safety:read`. Daybook, safety-card,
and authenticated child-photo responses use `private, no-store`.

Educator child-state mutations require an open server-recorded shift at the
same facility. Attendance check-in and check-out additionally require a stable
`client_operation_id`; clients must persist and retry the same UUID until a
response is reconciled. Reuse for another action or child returns `409`, while
an exact committed retry returns the original current attendance projection.
Owners and administrators deliberately retain an emergency operational
override so child safety work is not blocked by a missing staff clock event.
Those override mutations still write their normal immutable domain event and
actor-scoped audit event; the exemption is not available to educators.

Realtime cursors mean “last event emitted,” not “refresh successfully applied.”
A client may persist a received cursor only after its local refresh/transaction
succeeds. A `reset_required` frame supplies `resume_from` and
`latest_available_cursor`, sets `cursor_must_not_advance=true`, and requires a
fresh snapshot without advancing the saved cursor on a failed refresh.

Remote push delivery is disabled by default. To enable the Expo provider on a
server, set `PUSH_DELIVERY_ENABLED=true`, `PUSH_PROVIDER=expo`, and a non-empty
server-only `EXPO_PUSH_ACCESS_TOKEN`. `scripts/start-basic.sh` then supervises
the push outbox worker and `scripts/stop-basic.sh` stops it. The worker sends
only generic identifiers and category/severity metadata; notification title,
body, child/family/staff names, and other private data are fetched only after
the signed-in client opens its authenticated notification feed. Expo ticket
acceptance is recorded as `receipt_pending`; a delivery becomes `sent` only
after a successful provider receipt. That status means provider handoff, not
proof that the device displayed the message or that a person read it.

The revision-zero migration refuses to run if legacy product tables exist. The
intended database layout remains:

- original `caresync` on 5432 — untouched;
- legacy rebuild clone on 5433 — retained;
- populated retained Basic `caresync` on 5434 — active runtime target, released
  at `0039_admissions_decision_spine`.

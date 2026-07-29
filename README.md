> [!IMPORTANT]
> **Retained-release commands supersede legacy instructions below (2026-07-26).**
> The remainder of this document is preserved verbatim for product and audit
> context. For the retained `0039_admissions_decision_spine` to
> `0043_org_wide_room_presence` release, do not execute any older startup,
> migration, cutover, restore, or rollback command found below. The canonical
> contract is `scripts/BASIC_RELEASE_CLI_CONTRACT.md`. Its current two-phase
> operator flow is:
>
> ```text
> scripts/basic-release.sh prepare [--clone-port 55000..60999]
> scripts/basic-release.sh commit \
>   --receipt /absolute/private/run/candidate-receipt.json \
>   --confirm "COMMIT CARESYNC RETAINED 0039 TO 0043"
> ```
>
> Finalized emergency rollback requires the candidate, commit and finalization
> receipts. Interrupted intent-only rollback supplies only the candidate receipt;
> it omits both finalized-receipt flags and is accepted only when the run contains
> its exact durable commit-attempt intent. Both use the exact confirmation phrase
> `ROLL BACK CARESYNC RETAINED 0043 TO CAPTURED 0039`.
>

# CareSync Private Rebuild

Private, local-first CareSync product rebuild. Its Basic release starts from a
clean Alembic-owned database and is deliberately separate from the original
private runtime and the retained legacy clone.

Basic runs the new interface on `5174`, FastAPI on `3002`, and PostgreSQL on
`5434`. The original remains on `5173/3001/5432`; the legacy rebuild database
is retained on `5433`. See [`docs/REBUILD_RUNTIME.md`](docs/REBUILD_RUNTIME.md).

The legacy application remains the behavioral reference during migration. Its
SQLite database filename is preserved as `caresync.db`, and the PostgreSQL database
name remains `caresync`.

Scheduler V3 source is preserved for later Analyzer integration, but scheduling
is intentionally hidden and unreachable in the Basic product.

## Current status

The Basic product is implemented: public entry, owner registration, onboarding,
dashboard, families, children and enrollment, facilities/programs/rooms, actual
attendance, and settings. A facility can register Daycare, OSC, or both as
separate licensed service records and assign rooms to the correct service.
Deferred routers are disabled by default. PostgreSQL RLS is enforced under a
restricted runtime role.

The Basic backend now also provides a facility-scoped room roster at
`GET /api/v1/room-rosters?facility_id=...`. New enrollment writes require a
complete active program-and-room placement with capacity; an enrollment move
updates both identifiers together, while explicitly clearing both creates a
reviewable unassigned placement. Family details and the guardian/emergency
contact network are editable atomically through
`PATCH /api/v1/families/{family_id}`, with omitted sections preserved and
explicit null/empty sections removed.

A read-only audit of the isolated Basic database found no program/room,
enrollment, child-activity, onboarding, or cross-tenant relationship invariant
violations. The retained live-local database and checked-in launcher now share
the reviewed release `0039_admissions_decision_spine`. Its guarded promotion
quiesced writers, created and verified the complete database/evidence recovery
set, proved the exact 16,445-row disposable restore, migrated to exactly 0039
and rebuilt restricted grants before the services returned. Releases 0036
through 0038 remain historical evidence; they are not the current retained
state.

Revision 0039 adds a private administrator admissions lifecycle with versioned
intake, deterministic waitlist lanes, program offers, exact retry, duplicate
review and atomic conversion into canonical Family, Child and pending
unassigned Enrollment records. The existing derived intake-remediation queue
remains separate. It adds no parent/public admissions portal, documents or
signatures, outbound email, automatic room placement, billing/payment/funding
behavior or transport authority.

The 0029–0039 train keeps family authority, staff screening, driver/vehicle,
billing, public-job replay and admissions behind truthful runtime and
permission gates. It does not automatically activate verified family release
or billing. Each facility keeps its legacy checkout behavior until an
owner/administrator resolves the readiness queue and performs the irreversible
facility activation. Private manual billing requires a separate immutable
organization-owner activation and records only charges/payments completed
outside CareSync. It has no processor, money movement, automatic issue,
delivery, tax advice, refund or funding submission. The synthetic 0033 sandbox
remains separately restricted to attested disposable high-port databases.

The current promotion evidence is recorded in
[`docs/LOCAL_RELEASE_0039_CUTOVER.md`](docs/LOCAL_RELEASE_0039_CUTOVER.md),
[`docs/REBUILD_RUNTIME.md`](docs/REBUILD_RUNTIME.md) and
[`docs/CUTOVER_BACKUP_RESTORE_RUNBOOK.md`](docs/CUTOVER_BACKUP_RESTORE_RUNBOOK.md).
The 0038 public-job cutover remains frozen as historical evidence in
[`docs/LOCAL_RELEASE_0038_CUTOVER.md`](docs/LOCAL_RELEASE_0038_CUTOVER.md).
Product slice `0040_billing_readiness_batch_planner` is verified in source and
through retained live read-only API acceptance. It adds the administrator
`/billing?view=setup` planner and no-write canonical intent preview, while any
reviewed Apply action reuses the existing protected account, payer, rate and
agreement commands. It introduces no schema migration; the retained Alembic
head remains exactly `0039_admissions_decision_spine`. Signed-in administrator
browser-click acceptance remains pending. See
[`docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md`](docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md)
and
[`docs/PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md`](docs/PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md).
Basic `/invoicing/*` remains unavailable; the supported administrator surface
is `/billing`.

Start it from the repository root:

```bash
./scripts/start-rebuild.sh
```

## Backend development

```bash
cd backend
./scripts/uv.sh sync
./scripts/uv.sh run pytest
./scripts/uv.sh run ruff check .
```

Release 0039 validation recorded 1,997 passing backend tests, 105 explicit
opt-in skips, seven warnings, a green 22-test focused admissions matrix, two
independent green PostgreSQL 17 runs, Ruff and bytecode compilation. Complete
evidence is maintained in `docs/LOCAL_RELEASE_0039_CUTOVER.md`,
`docs/PRODUCT_IMPLEMENTATION_LEDGER.md` and `docs/MVP_READINESS_AUDIT.md`.

API documentation is available at `http://127.0.0.1:3002/docs` while Basic is
running.

The wrapper keeps the disposable Python environment on the Mac's internal drive.
This avoids the `._` metadata files that macOS creates when Python wheels are
installed directly onto the T7 filesystem.

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

# CareSync Basic rebuild runtime

This project is the writable rebuild sandbox. It is intentionally isolated from the original CareSync Private runtime.

| Component | Original | Legacy clone | Basic |
|---|---:|---:|---:|
| Frontend | 5173 | — | 5174 |
| FastAPI | 3001 | compatibility on 3002 | 3002 |
| PostgreSQL | 5432 | 5433 | 5434 |
| Database name | `caresync` | `caresync` | `caresync` |

The source project lives on the T7 drive. PostgreSQL data directories live on
the Mac's internal drive because the T7 filesystem creates AppleDouble `._*`
metadata files that PostgreSQL treats as invalid relation files:

- legacy evidence: `~/Library/Application Support/CareSync Private Rebuild/postgres-data`
- active Basic: `~/Library/Application Support/CareSync Basic/postgres-data`

The initial clone was produced from a consistent PostgreSQL custom-format dump. Verification matched the original for all 40 public tables and these representative row counts:

- 3 organizations
- 7 users
- 109 families
- 202 children
- 578 generated claims
- 153 invoices
- 41,386 scheduled-attendance records
- 1,122 activity-log records

The default port-3002 backend connects only to Basic on 5434 as
`caresync_basic_app`. That role is a non-superuser, cannot bypass PostgreSQL
RLS, and cannot create schema objects. Its DELETE authority is limited to the
explicit marketplace/media projection allowlist documented in
`backend/BASIC_RUNTIME.md`; it has no blanket operational-table DELETE.
Alembic runs separately as the local migration owner.

The isolated retained live-local database and the launcher's
`RELEASED_REVISION` now share `0039_admissions_decision_spine`. The guarded
2026-07-23 cutover moved exactly from `0038_public_job_catalog_outbox` only after
the complete database and evidence-bundle backup/disposable-restore gate
passed, then rebuilt the restricted runtime grants. The earlier guarded
0028-to-0036, 0036-to-0037 and 0037-to-0038 promotions remain recorded
separately.

Revision 0037 changes only immutable billing agreement scope: ordinary records
are unique by organization, account and enrollment; historical
null-enrollment records retain a partial organization/account/child fallback.
The superseded all-row account/child constraint is absent. It does not create a
new billing mode or rewrite a billing fact. Revision 0036 remains the
private/manual protocol boundary. Migrations create no facility or billing
activation. Verified checkout remains legacy until a privileged operator
clears the server-computed readiness queue and explicitly activates one
facility. Manual billing remains command-disabled until an organization owner
completes its separate immutable activation review.

Revision 0038 adds a forced-RLS public-safe job projection and durable catalog
outbox. Unaffiliated candidates can replay public listing changes and the
closure of an organization's last public listing without receiving draft,
organization, candidate, application, interview, offer, credential, or
free-text tenant-private data. It changes no billing or family-release
protocol and creates no activation.

Revision 0039 adds the forced-RLS administrator admissions lifecycle,
deterministic waitlist, offers, exact retry, duplicate review and atomic
conversion into canonical Family, Child and pending unassigned Enrollment.
The six admission tables began and remain empty in retained data. The release
adds no public/parent portal, automatic room placement, billing/payment/funding
behavior or transport authority.

The 0033 synthetic sandbox is unchanged: command writes still require test
mode, exact disposable-target attestation, a tenant allowlist, immutable
synthetic-source attestations and a loopback high port other than
5432/5433/5434. The 0036 private/manual path is distinct. On the local
development server it may record only externally completed charge/payment
facts for an explicitly allowlisted and owner-activated organization. It has no
processor, money movement, automatic issue, external delivery, refund, tax
advice or funding submission. Historical payer/rate/agreement versions and
invoice provenance remain pinned so later reassignment cannot rewrite them.

Hiring now has one mounted Basic boundary: `/api/v1/ats` for the employer and
`/api/v1/marketplace` for the candidate, including the employer marketplace
projection below `/api/v1/ats/marketplace`. The legacy `/api/v1/hiring` and
`/api/v1/candidate/hiring` prefixes are absent from OpenAPI and unused legacy
client adapters are retired.

Migration `0027` adds recurring rotation sources, open shifts and manager
offers, staff-owned substitute opt-in, consent/approval-based whole-shift swaps
and nullable scheduled-shift provenance. It does not change the
API/port/database isolation in this document or merge planned shifts with
actual clock evidence. Runtime rows use terminal lifecycles/tombstones rather
than DELETE, and the immutable workforce ledger stores exact operation
receipts.

## Current 0039 migration evidence

The canonical source-cutover artifact stem is
`caresync-postgres-20260723-052743-592770`. The exact backup, manifest and
database/vault restore receipts are listed in
`docs/LOCAL_RELEASE_0039_CUTOVER.md`.

The source backup and fresh PostgreSQL 17 port-56555 restore contain exactly
16,445 rows across all 135 public tables at
`0038_public_job_catalog_outbox`, including 110 families and 203 children.
Their canonical row digest is
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both evidence bundles restored zero objects. The retained database then
migrated to `0039_admissions_decision_spine` with 141 public tables plus one
view, exactly 16,445 rows, 110 families, 203 children and 197 enrollments. All
six admission tables and both activation tables remain empty.

Final evidence is backend 1,997 passed / 105 skipped / seven warnings,
administrator 125 files / 841 tests, staff app 272, extension 78, focused
backend 22 and two independent green PostgreSQL 17 runs. TypeScript/build,
release-pin, Ruff and bytecode gates passed. The signed-in retained Admissions
workspace loaded every canonical read projection without a visible error or
write. Product slice `0040_billing_readiness_batch_planner` is verified in
source and through retained live read-only API acceptance. It introduces no
schema migration; the retained Alembic head and launcher target remain exactly
`0039_admissions_decision_spine`. Signed-in administrator browser-click
acceptance for the setup planner remains pending.

## Historical 0038 migration evidence

The canonical source-cutover artifact stem is
`caresync-postgres-20260723-022822-921802`. The backup is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.gz`;
its matching manifest is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.manifest.json`,
and its exact database restore receipt is
`~/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.json.gz.receipt.json`.

The source backup and fresh PostgreSQL 17 restore contain exactly 16,335 rows
across all 134 public tables at `0037_billing_agreement_scope`, including 110
families and 203 children. The guarded private evidence recovery requirements
passed. The retained database then migrated to
`0038_public_job_catalog_outbox` with 135 public tables plus one view and the
same 110 families and 203 children. The retained facility-release and manual
billing activation tables both remain empty.

Final source evidence at that checkpoint was 1,979 backend tests passed with 104 explicit opt-in
cases skipped; administrator 808/808; staff app 272/272; extension 78/78; and
the fresh PostgreSQL 17 public-job gate 3/3. The public-job catalog replay
boundary was released and retained. Admissions 0039 subsequently completed the
guarded release recorded above.

## Historical 0037 migration evidence

The canonical source-cutover backup is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-005011-912450.json.gz`;
its matching manifest is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-005011-912450.json.manifest.json`,
and its exact database restore receipt is
`~/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-005011-912450.json.gz.receipt.json`.
The verified family and staff/transport restore receipts are under the sibling
`caresync-postgres-20260723-005011-912450.vaults/` directory.

The source backup and fresh PostgreSQL 17 restore contain exactly 16,309 rows
across all 134 public tables at `0036_billing_manual_mode`, including 110
families and 203 children. The disposable restore matched every table count and
the canonical row digest. Both required evidence bundles restored with private
no-clobber receipts. The retained database then migrated to
`0037_billing_agreement_scope` with 134 public tables plus one view and the same
110 families and 203 children.

Inspection verified `uq_bill_agreement_account_enrollment`, the partial
`uq_bill_agreement_legacy_account_child` index for rows whose enrollment is
null, and absence of `uq_bill_agreement_account_child`. The retained facility
release and manual billing activation tables both remain empty.

Final source evidence is 1,969 backend tests passed with 102 explicit opt-in
cases skipped; administrator 808/808 plus TypeScript and production build;
staff app 260/260 plus TypeScript; and extension 78/78 plus production build.
Required canonical OpenAPI routes are present, legacy hiring prefixes and
retired routes are absent, and the hiring preflight reports zero pending
private invitations, invitation-bound applications and draft offers.

Signed-in Admissions, Billing, Family, Child and Jobs checks passed. Billing
readiness truthfully reported 0 setup-ready records out of 197 active child
records. This checkpoint preceded the released 0038 public-job catalog outbox.

## Historical 0036 migration evidence

The canonical source-cutover backup is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.gz`;
its matching manifest is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.manifest.json`,
and its exact-restore receipt is
`~/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260722-232512-277485.json.gz.receipt.json`.

The source backup and fresh PostgreSQL 17 restore contain exactly 16,260 rows
across 77 tables at `0028_childcare_command_spine`, including 110 families and
203 children. The disposable restore matched every table count and the
canonical row digest and remained at 0028. The retained database then migrated
to `0036_billing_manual_mode` with 134 public tables plus one view, preserving
the same 110 families and 203 children. The 0028 source had neither family nor
staff/transport evidence tables nor corresponding vault bytes, so no evidence
bundle was required for this specific transition.

The retained release and billing activation tables both remain empty. Schema
promotion did not activate verified release or manual billing. Health reported
PostgreSQL connected after restart and the administrator frontend returned
HTTP 200.

Final source evidence is 1,094 backend tests passed with 101 explicit opt-in
cases skipped and seven non-failing dependency warnings; administrator
790/790 plus production build and zero production audit findings; staff app
265/265 plus TypeScript and the recorded Expo SDK 57 Doctor/export evidence;
and extension 78/78 plus TypeScript/build and zero production audit findings.

## Historical 0028 migration evidence

The canonical pre-`0028` release backup is
`~/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260717-120050-877200.json.gz`;
its manifest is in the same directory as
`caresync-postgres-20260717-120050-877200.json.manifest.json`.
The compressed SHA-256 is
`64220acf9e233ef81571305324239b77d9c9cd70df0dfd761ef21d41ae89553d`,
the uncompressed JSON-lines SHA-256 is
`712000703124bdb9e4e7b98ec21955e8003ac0db2718044e1868da541cfae893`, and
the canonical row-only SHA-256 is
`5378a43b7dd7c5bb058dac5790a9ba6a15d60adf81de075e56b715580767c325`.
The v2 manifest records 1,830 rows across all 71 pre-migration tables. It was
verified directly, restored on a fresh disposable PostgreSQL 17 target, and
matched exact table counts and the row-only digest before live Alembic was
allowed to run. The private restore receipt is retained under
`~/Library/Application Support/CareSync Basic/restore-verifications/`.
The project-directory copies are ExFAT mirrors only: T7 cannot represent Unix
`0600` file modes. The canonical internal directory is `0700` and both
artifacts are verified `0600`; future cutovers use it by default.

The prior `0027` release backup remains retained as historical evidence at
`backend/backups/caresync-postgres-20260717-013825.json.gz`. Its
compressed SHA-256 is
`230aa2265e2b8298e43992547256c99ee1bd0b9e010ae805f2d984a0d0f7df00`
and its uncompressed JSON-lines SHA-256 is
`3a37e26517b8f1b6fd9214ea74a02035f7bd8ad6eb598202404d573e726be203`.
It records 1,665 rows across 66 tables.

Fresh PostgreSQL 17 verification passed 38/38 application, RLS and concurrency
checks at the final source; the process-level `0027 -> 0028 -> 0027 -> 0028`
migration gate passed 1/1, including atomic refusal once committed command
history exists. The backup/restore track passed its focused suite and two real
database drills, including exact restoration of the full 71-table `0027`
schema. All disposable PostgreSQL instances were stopped and deleted.

The logical restore gate proves all 1,830 pre-migration rows were preserved.
Public tables increased additively from 71 to 77; the six new command,
reconciliation and budget tables began at zero. Each has RLS enabled and
forced. The runtime role is still `caresync_basic_app`, remains non-superuser
and NOBYPASSRLS, has a pinned `public, pg_catalog` search path, and owns no
database objects.

Live inspection also verified the two source-schedule swap indexes, the unique
origin-occurrence and supersedes indexes, and the new scheduled-shift provenance
columns. The live OpenAPI exposes 31 staff-exchange paths / 35 operations;
unauthenticated manager and educator exchange reads both returned 401.

Final gates recorded 387 passing default backend tests with 41 expected opt-in
database skips, 38/38 isolated PostgreSQL application checks, 1/1 fresh-process
migration gate, maintained-source Ruff green and bytecode compilation green.
The administrator client passed 471 tests across 79 files, TypeScript and an
830-module production build. The staff app passed 138 tests, TypeScript, Expo
Doctor 20/20 and a 740-module Android export on Expo SDK 57 patch releases.

Post-cutover runtime smoke returned 200 for API health and the administrator
portal. An already authenticated client re-established both realtime streams
against the restarted API. Full operator walkthrough of the new child-domain
command UI remains acceptance work; the release claim here is local technical
integrity, not production or regulatory acceptance.

Physical-device/operator, accessibility, privacy and regulatory acceptance
remain separate from this local release evidence.

Run `./scripts/start-rebuild.sh` from the project root to migrate/start Basic,
the API, and the redesign. Run `./scripts/stop-rebuild.sh` to stop only Basic.
The explicit equivalents are `start-basic.sh` and `stop-basic.sh`.

When a non-empty database has a pending schema revision, startup now enters a
fail-closed maintenance gate: it quiesces and verifies API/push writers, creates
a complete same-snapshot backup through an RLS-bypass maintenance identity, and
requires a count-and-digest-exact logical restore on a fresh disposable
PostgreSQL port before Alembic may run. Ports 5432, 5433 and 5434 can never be
restore targets. See [CUTOVER_BACKUP_RESTORE_RUNBOOK.md](CUTOVER_BACKUP_RESTORE_RUNBOOK.md)
for preparation, artifact, secret-handling and teardown details.
The current 0039 retained-cutover inputs and activation boundaries are
summarized above and in
[CUTOVER_BACKUP_RESTORE_RUNBOOK.md](CUTOVER_BACKUP_RESTORE_RUNBOOK.md). The
historical 0038 public-job predecessor remains frozen in
[LOCAL_RELEASE_0038_CUTOVER.md](LOCAL_RELEASE_0038_CUTOVER.md); earlier releases
remain in [LOCAL_RELEASE_0037_CUTOVER.md](LOCAL_RELEASE_0037_CUTOVER.md) and
[LOCAL_RELEASE_0036_CUTOVER.md](LOCAL_RELEASE_0036_CUTOVER.md).

The API binds to loopback by default. For an Expo device on the same trusted
LAN, start with `CARESYNC_BASIC_API_HOST=0.0.0.0 ./scripts/start-rebuild.sh`,
then point the mobile app at the Mac's current LAN address. Return to the
loopback default after device testing.

For the current USB device smoke, the CareSync Staff Android development client
has been built, installed and launched on a connected Pixel. ADB reverse
tunnels expose local Metro `8081` and API `3002` to the device while keeping the
API on loopback. That proves native installation and local app/API connectivity;
it does not prove remote Expo/FCM push delivery.

The linked EAS development build completed as build
`c119edd9-efc6-49a7-8c89-693ee3c859d3`. Its downloaded APK is retained at
`~/Library/Caches/CareSync-Staff/eas-builds/caresync-staff-development-c119edd9.apk`
with SHA-256 `86101a145d3a9d810b32f574da6a7b0d4d9870049d223e65eca1ac874c83fb38`.
It replaces the temporary locally signed build at the next connected-device
install; the signature change requires removing that temporary package first.

Push delivery is fail-closed and provider-disabled by default. The local API
still supports notification ledger, user-private realtime, subscription and
delivery-evidence contracts, but the worker will not claim work or make a
network request unless `push_delivery_enabled`, the `expo` provider and a valid
Expo access token are explicitly configured. The Expo/EAS project is linked and
a signed development build completed successfully; Android FCM credentials and an
end-to-end remote notification smoke remain deployment work. The administrator
portal provides realtime inbox/toasts and browser
notifications while open; durable closed-browser service-worker Web Push is
not part of this runtime yet.

Startup removes only macOS AppleDouble `._*` metadata sidecars from the source
tree before Alembic or Vite runs. Those sidecars can contain NUL bytes and must
never be interpreted as migrations or application source on the external T7.
Alembic's environment also removes `alembic/versions/._*.py` immediately before
direct programmatic migrations, so migration tests and tooling receive the same
protection even when they do not use the startup wrapper.

The retained 5433 clone is not the default. If regression investigation requires
its old API, `start-legacy-backend.sh` switches port 3002 into explicit
compatibility mode; `start-rebuild.sh` returns it to Basic.

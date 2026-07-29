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

# CareSync schema-cutover backup and restore gate

This runbook is the fail-closed contract for every non-empty PostgreSQL schema
upgrade. It applies to the local Basic runtime and is intentionally stricter
than an ordinary application restart.

## What startup now guarantees

Before it creates a backup or invokes Alembic, `scripts/start-basic.sh`:

1. sends `SIGTERM` only to PID-file processes whose command lines identify the
   CareSync API or push worker;
2. stops a CareSync Uvicorn listener on port 3002 and refuses to kill an
   unrelated listener;
3. waits for every signalled process to exit and rejects any remaining
   CareSync API/push-worker process even if its PID file was lost;
4. queries `pg_stat_activity` and refuses to continue while any other client
   session remains connected to the CareSync database; and
5. repeats the database-session check immediately before Alembic.

The frontend is not a database writer and may stay open. It will report the API
as unavailable during this maintenance window.

If the current Alembic revision already equals the launcher's explicitly
pinned `RELEASED_REVISION`, no migration backup/restore drill is required.
Source head may be newer while an unreleased migration is being staged and is
never inferred by the launcher. A new database with no public tables may be
initialized directly to the pinned release. A non-empty public schema without
an `alembic_version` table is rejected.

The checked-in local release target and retained port-5434 database now share
`0039_admissions_decision_spine`. The guarded 0039 cutover used this runbook to
move exactly from `0038_public_job_catalog_outbox`; the 0036 through 0038
cutovers remain historical checkpoints. For every future pending migration, the
launcher detects whether the source backup contains the complete family and
staff/transport evidence-table shapes. A partial shape fails before backup. A
complete shape requires the matching bundle creation, independent
verification, no-clobber disposable vault restore and private receipt between
the database backup and Alembic. A pre-0029/0030 source backup has no such
external evidence rows and therefore skips the absent vault gate only when the
corresponding private vault is empty. Untracked bytes block migration and are
never deleted or silently omitted.

The protected-port Alembic opt-in is command-scoped inside the launcher and is
added only after the backup, exact restore and repeated writer checks pass. It
is never exported to the shell, stored in `.env`, or used by a test process.

## Recorded 2026-07-23 retained 0039 cutover

The current retained cutover uses canonical artifact stem
`caresync-postgres-20260723-052743-592770`. Its exact database backup, manifest,
database restore receipt and both vault restore receipts are listed in
[LOCAL_RELEASE_0039_CUTOVER.md](LOCAL_RELEASE_0039_CUTOVER.md).

The source backup and fresh PostgreSQL 17 restore at port 56555 contain exactly
16,445 rows across all 135 public tables at
`0038_public_job_catalog_outbox`, including 110 families and 203 children. The
source and restore canonical row digest is
`7911ccaad42fa7f94943669a230f461624d3b3f1a1052fbf28d7384de27cd0eb`.
Both evidence-vault restores contained zero objects and produced private
receipts.

The retained migration reached `0039_admissions_decision_spine` with 141
public tables plus one public view and exactly 16,445 rows, preserving 110
families, 203 children and 197 enrollments. All six admission tables are empty.
Facility-release and manual-billing activation counts remain zero.

Final acceptance recorded backend 1,997 passed / 105 skipped / seven warnings,
administrator 125 files / 841 tests, staff app 272, extension 78, focused
backend 22 and two independent green PostgreSQL 17 admission runs. The
signed-in retained Admissions smoke was read-only and left every admission
table empty. Product slice `0040_billing_readiness_batch_planner` is verified
in source and through retained live read-only API acceptance. It introduces no
schema migration, so it did not invoke this cutover gate and the retained head
remains 0039. Any later schema migration must use the gate.

## Historical recorded 2026-07-23 retained 0038 cutover

At that historical checkpoint, the retained cutover used canonical artifact stem
`caresync-postgres-20260723-022822-921802`:

- backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-022822-921802.json.manifest.json`; and
- exact disposable-restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.json.gz.receipt.json`.

The same stem also identifies the family-evidence ZIP and manifest, the
staff/transport-evidence ZIP and manifest, and the private vault restore
receipts under
`/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-022822-921802.vaults/`.

The source backup and fresh PostgreSQL 17 restore contain exactly 16,335 rows
across all 134 public tables at `0037_billing_agreement_scope`, including 110
families and 203 children. The retained migration reached
`0038_public_job_catalog_outbox` with 135 public tables plus one public view,
preserving those family and child counts. The guarded evidence-bundle and
no-clobber restore requirements applied because the source was later than
0029/0030.

The 0038 release added the public-safe durable job-catalog replay boundary. It
does not activate verified release or manual billing:
`facility_release_checkout_activations` and `billing_manual_activations` both
remained at zero rows. Final acceptance recorded 1,979 backend tests passed with
104 explicit opt-in cases skipped, 808 administrator tests, 272 staff-app
tests, 78 extension tests, and the PostgreSQL 17 public-job gate at 3/3.
Admissions 0039 subsequently completed the guarded release recorded above.

## Historical recorded 2026-07-23 retained 0037 cutover

The preceding 0037 checkpoint used artifact stem
`caresync-postgres-20260723-005011-912450`. Its source backup and exact
disposable restore contained 16,309 rows across 134 public tables at
`0036_billing_manual_mode`, including 110 families and 203 children. Both
private evidence bundles restored with no-clobber receipts. The retained
database then reached `0037_billing_agreement_scope` with 134 public tables plus
one public view and the same family/child counts. Both activation tables
remained empty. Its complete historical evidence is frozen in
[LOCAL_RELEASE_0037_CUTOVER.md](LOCAL_RELEASE_0037_CUTOVER.md).

## Historical recorded 2026-07-22 retained 0036 cutover

The completed cutover retained the following canonical evidence:

- backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.manifest.json`; and
- exact disposable-restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260722-232512-277485.json.gz.receipt.json`.

The backup and disposable PostgreSQL 17 restore each contain 16,260 rows across
77 tables at exactly `0028_childcare_command_spine`, including 110 families
and 203 children. Every direct/export/restored table count and the canonical
row digest matched. The retained migration then reached
`0036_billing_manual_mode`, 134 public tables plus one view, while preserving
the same 110 families and 203 children.

Because the exact 0028 source had no family or staff/transport evidence tables
and both corresponding vaults were empty, no evidence bundle was required for
this cutover. That source-specific absence must not be generalized to any
future backup at 0029A1, 0030 or later.

Both owner-controlled activations remain absent after migration:
`facility_release_checkout_activations` has zero rows and
`billing_manual_activations` has zero rows. The cutover is local technical
release evidence; it is not physical-operator, regulatory, accountant,
payment-provider or live third-party acceptance.

## Backup completeness contract

`backend/scripts/backup_database.py` writes the v2 JSON-lines gzip artifact and
its manifest from one PostgreSQL `REPEATABLE READ`, read-only snapshot. Before
reading a row it sets `row_security=off` and requires a superuser or explicit
`BYPASSRLS` maintenance identity. PostgreSQL therefore raises an error rather
than returning a tenant-filtered subset from a `FORCE ROW LEVEL SECURITY`
table.

The runtime role must never be used for backup. Configure a separate local
maintenance identity with `CARESYNC_BASIC_BACKUP_USER`; supply its password only
through `CARESYNC_BASIC_BACKUP_PASSWORD` when peer/trust authentication is not
available. Neither value is printed or written to the artifacts.

By default, startup writes cutover artifacts under
`~/Library/Application Support/CareSync Basic/backups`, not the T7 project
tree. T7 is ExFAT and cannot represent Unix `0600` modes. The internal default
keeps the directory at `0700` and artifacts at `0600`. An explicit
`CARESYNC_BASIC_BACKUP_DIRECTORY` override must point to a filesystem capable
of enforcing those owner-only modes.

For every reflected public table the backup records a direct `count(*)` from
the same snapshot, streams rows in primary-key order, and checks the exported
count against the direct count. The manifest contains:

- compressed-file SHA-256;
- complete uncompressed JSON-lines SHA-256;
- row-only SHA-256 used by restore comparison;
- per-table direct/export counts and total rows; and
- the source Alembic revision.

Artifacts are first written under private partial names, verified by reopening
the gzip and manifest, atomically renamed, and set to mode `0600`. The output
directory is mode `0700`. A failed backup removes partial/final candidates and
blocks migration.

## 0029A1 private evidence-vault consistency set

Revision `0029A1_family_evidence_vault` adds private document bytes that are not
stored in PostgreSQL. A database artifact alone is therefore incomplete for
0029A1 or any later revision. The release evidence must retain all four files as
one consistency set:

- the verified logical database backup;
- its logical-backup manifest;
- the family-evidence ZIP bundle; and
- the family-evidence bundle manifest.

`backend/scripts/family_evidence_vault_bundle.py` never queries a live database.
It first verifies the existing logical backup, derives the exact object and
terminal-assessment inventory from that snapshot, and then measures the private
vault bytes against each snapshot row. The evidence manifest binds the archive
to both the compressed database SHA-256 and the SHA-256 of the database
manifest. Reverification derives the inventory again; a caller cannot supply or
edit an object list independently.

The byte-retention policy is fail closed:

- clean, quarantined, `rejected/invalid_document`, and
  `rejected/malware_detected` objects must all exist and are included;
- a rejected object remains non-downloadable and invalid for evidence, but
  rejection alone is not an implicit purge or permission to create an
  unexplained missing file; and
- any missing referenced byte, size/hash mismatch,
  unexpected assessment transition, unsafe storage reference, symbolic link,
  or non-private mode blocks bundle creation.

Bundle members use only the exact opaque references present in the verified DB
snapshot. Verification rejects duplicates, undeclared members, traversal,
links, compression changes, mode changes, and byte/hash mismatches. Archive and
manifest directories must be `0700`; files must be `0600`. Do not put this
consistency set on T7/ExFAT because that filesystem cannot prove owner-only Unix
modes.

Create and independently verify the companion bundle after the quiescent DB
backup has been created:

```bash
cd backend
./scripts/uv.sh run python scripts/family_evidence_vault_bundle.py create \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --vault-root "$HOME/Library/Application Support/CareSync Basic/private-family-authority-vault" \
  --output-directory /private/backups

./scripts/uv.sh run python scripts/family_evidence_vault_bundle.py verify \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --bundle /private/backups/caresync-postgres-TIMESTAMP.family-evidence.zip \
  --bundle-manifest \
    /private/backups/caresync-postgres-TIMESTAMP.family-evidence.manifest.json
```

Restore proof uses a new, non-existing disposable vault root. It never merges
into or overwrites an existing root. Every restored directory/file is recreated
as `0700`/`0600`, the exact inventory is remeasured, malware-rejected objects
are preserved as non-downloadable custody records, and an optional private
receipt is written without clobbering:

```bash
./scripts/uv.sh run python scripts/family_evidence_vault_bundle.py restore \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --bundle /private/backups/caresync-postgres-TIMESTAMP.family-evidence.zip \
  --bundle-manifest \
    /private/backups/caresync-postgres-TIMESTAMP.family-evidence.manifest.json \
  --destination /private/disposable-restore/private-family-authority-vault \
  --receipt /private/receipts/family-evidence-restore.json
```

### Report-only vault reconciliation

`backend/scripts/family_evidence_vault_reconcile.py` compares a live private
vault with the backup-derived canonical inventory from one verified logical DB
backup and manifest. It traverses descriptor-relative without following links,
remeasures canonical and unexpected regular files, and reports missing,
mismatched, unsafe, unexpected and indeterminate state. It never deletes or
quarantines vault content. `--purge` intentionally fails closed; `--stdout`
must be explicit because the report contains opaque private object keys.

Write the report only into a pre-existing `0700` directory. The report is
created no-clobber as `0600`:

```bash
cd backend
./scripts/uv.sh run python scripts/family_evidence_vault_reconcile.py \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --vault-root "$HOME/Library/Application Support/CareSync Basic/private-family-authority-vault" \
  --output /private/reconciliation/family-evidence-TIMESTAMP.json
```

No finding produced by this version is purge authorization. A future purge
tool must independently require two verified snapshots with an authoritative
`snapshotEstablishedAt`; proof that the same unexpected object was absent from
both and unchanged for at least 30 days; decisive writer/database quiescence;
confirmation of the exact purge-plan digest; and durable per-object receipts
for every attempted deletion. Until all of those gates exist and pass,
rejected, invalid-document and unexpected bytes stay in place.

The launcher invokes this gate whenever a pending-migration source database
contains the complete 0029A1 evidence-table pair. It requires both the database
restore receipt and this evidence-vault restore receipt; neither receipt alone
proves a complete restore. The current pre-0029 retained source has no evidence
tables or references, so its first 0028-to-0036 cutover has no pre-existing
family vault bytes to bundle.

## 0030/0032 encrypted staff/transport vault recovery set

Revision `0030_staff_screening_pathways` and the 0032 transport evidence commands
store encrypted ciphertext outside PostgreSQL in the shared private staff vault.
For a backup at either revision or later, the database backup and manifest are
not a complete recovery set by themselves. Retain these four artifacts together:

- the verified logical database backup;
- its database manifest;
- the deterministic staff/transport evidence ZIP; and
- the staff/transport evidence bundle manifest.

Create and independently verify the bundle only after the logical backup has
been fixed. The command derives its inventory exclusively from that verified
backup; it neither queries a live database nor accepts a caller-supplied object
list:

```bash
cd backend
./scripts/uv.sh run python scripts/staff_transport_vault_bundle.py create \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --vault-root "$HOME/Library/Application Support/CareSync Basic/private-staff-screening-vault" \
  --output-directory /private/backups

./scripts/uv.sh run python scripts/staff_transport_vault_bundle.py verify \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --bundle /private/backups/caresync-postgres-TIMESTAMP.staff-transport-evidence.zip \
  --bundle-manifest \
    /private/backups/caresync-postgres-TIMESTAMP.staff-transport-evidence.manifest.json
```

Creation fails if any referenced ciphertext is missing or mismatched, if the
vault contains any unexpected or indeterminate entry, or if a path, owner, link
count or mode is unsafe. All screening, qualification and vehicle evidence rows
are retained, including historical and terminal rejected/expired/revoked
relationships. The commands do not decrypt or print object references.

Restore only into a path that does not exist. It never merges with or replaces a
vault, and every restored ciphertext is remeasured against the snapshot before
the optional receipt is published:

```bash
./scripts/uv.sh run python scripts/staff_transport_vault_bundle.py restore \
  --backup /private/backups/caresync-postgres-TIMESTAMP.json.gz \
  --manifest /private/backups/caresync-postgres-TIMESTAMP.json.manifest.json \
  --bundle /private/backups/caresync-postgres-TIMESTAMP.staff-transport-evidence.zip \
  --bundle-manifest \
    /private/backups/caresync-postgres-TIMESTAMP.staff-transport-evidence.manifest.json \
  --destination /private/disposable-restore/private-staff-screening-vault \
  --receipt /private/receipts/staff-transport-vault-restore.json
```

The ZIP contains ciphertext, not its encryption key. Separately back up
`$CARESYNC_BASIC_RUNTIME/secrets/staff-screening-vault.key` (or
`$HOME/Library/Application Support/CareSync Basic/secrets/staff-screening-vault.key`
when the runtime override is absent) as a mode-0600 secret under approved
offline custody. Before cutover, compare bundle key-ID counts with the retained
key material and prove every ID is available. Do not rename a key ID or
rotate/rewrap ciphertext informally; the current runtime supports only the
configured active key ID.

The bundle also does not prove transport evidence-ingest connectivity. The
launcher keeps a distinct
`$CARESYNC_BASIC_RUNTIME/secrets/transport-evidence-ingest.password`, while the
database bootstrap owns the `caresync_transport_evidence_ingest` login role.
After migration and grant bootstrap, the launcher reads the stable owner-only
secret, installs or compares only its SCRAM verifier on the exact restricted
role, and emits no credential material. A password-authenticated intake probe
must still pass. Merely creating/normalizing the login role, or merely
forwarding the secret to the API, leaves evidence intake unavailable on a
password-authenticated PostgreSQL server.

The bundle proves exact recovery relative to the specified logical database
artifact and grants no deletion/purge authority. The launcher closes the local
maintenance timing gap by stopping verified application writers, rejecting
remaining database clients, creating the logical backup and vault bundles
before any migration, and repeating writer checks immediately before Alembic.
This is the bounded local cutover contract, not a production storage snapshot
or purge authorization.

### Operator certification and bounded artifact recovery

The 2026-07-22 synthetic-only signed-in A/A1/A2 operator certification passed on a
caller-provisioned empty loopback PostgreSQL database at exact
`0029D_release_checkout_writer`. Its private mode-0600, no-clobber redacted receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-operator-20260722T161501Z.json`;
SHA-256 `c0bdda5c56bc54396b0402330d6b36422e3c86cea8b915da1a61d1c3112d7308`.
That receipt proves the bounded signed-in HTTP, scanner/vault, maker/checker, exact-replay,
generic realtime-delivery and administrative-summary cases only. The harness did not create a
database backup, create a vault bundle, restore either artifact, migrate retained data, activate
a facility, execute a release checkout or authorize cutover.

The separate 2026-07-22 synthetic exact-0029D artifact-recovery consistency gate also passed. It
restored the four already-fixed database/vault artifacts into one caller-created scratch target,
matched 90 table counts and the canonical 61-row digest, restored and reconciled one evidence
object, and retained the database, evidence and joint no-clobber receipts. The joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
Its exact database component is `family-authority-database-restore-20260722T172958Z.json`, SHA-256
`6c2398da23da2c210f626fc883373bb877581355f5ba06428b5dc6be7291f29e`; its evidence component is
`family-authority-evidence-restore-20260722T172958Z.json`, SHA-256
`1e0de5c026599c06499e8f688540cb37e7a9e11e568a28ef0d64da01e07aee4f`. All three are owned
mode-`0600`, single-link files under the same private mode-`0700` receipt directory.

That decision is deliberately `artifactRecoveryConsistencyOnly`. It records
`recoveryConsistencyProven=true`, while source-writer quiescence, authoritative source
completeness, authoritative same-snapshot capture, unexpected source-vault exclusion and target
schema authenticity are all false. It invoked no migration, used no protected port and grants no
cutover, release or purge authority. The next recovery boundary is therefore a writer-frozen,
authoritative-source capture attestation that produces the four artifacts, followed by explicit
cutover orchestration and human release approval. Neither the operator receipt nor either
component restore receipt can substitute for the joint receipt, and none of the three authorizes
retained cutover.

## Disposable restore proof

When a migration is pending on a non-empty database, startup also requires
`CARESYNC_BASIC_RESTORE_VERIFY_PORT`. That port must belong to a fresh local
PostgreSQL cluster with an empty database named `caresync`. Ports 5432, 5433 and
5434 are permanently rejected by the restore tool. The target host must be
loopback and the confirmation value must exactly identify the target.

Example preparation, using a deliberately non-live port:

```bash
VERIFY_DATA="$(mktemp -d /tmp/caresync-restore.XXXXXX)"
/opt/homebrew/opt/postgresql@17/bin/initdb \
  -D "$VERIFY_DATA" -U postgres --auth=trust --no-locale --encoding=UTF8
/opt/homebrew/opt/postgresql@17/bin/pg_ctl \
  -D "$VERIFY_DATA" -l "$VERIFY_DATA/postgres.log" \
  -o "-p 55447 -h 127.0.0.1" start
/opt/homebrew/opt/postgresql@17/bin/createdb \
  -h 127.0.0.1 -p 55447 -U postgres caresync
CARESYNC_BASIC_RESTORE_VERIFY_PORT=55447 \
CARESYNC_BASIC_RESTORE_VERIFY_USER=postgres \
  ./scripts/start-basic.sh
```

`backend/scripts/restore_database.py` verifies the backup first, migrates only
the confirmed empty disposable target to the backed-up revision, restores all
rows with triggers disabled for the restore transaction, resets sequences, and
then opens a new read-only snapshot. The new snapshot must match every table
count and the canonical row-only SHA-256 exactly. Only then is a private restore
receipt written and live-local Alembic allowed to run.

The joint certifier is intentionally stricter than that standalone helper.
`backend/scripts/family_authority_joint_recovery_certification.py` never provisions or migrates a
database. Its caller must create and migrate an owned mode-`0700` direct child of `/tmp` or
`/private/tmp` named `caresync-joint-recovery-target.*`, write the exact private cluster-identity
marker, and keep it running on an unprotected loopback port at
`0029D_release_checkout_writer`. Before destructive restore, the certifier holds its target locks
and proves the exact empty public-table inventory, no extra non-system schema, zero other client
sessions, the expected PostgreSQL data directory and system identifier, and all four raw artifact
hashes. It names every public table explicitly and never uses `TRUNCATE ... CASCADE`.

Stop the disposable cluster after the cutover and retain it only as long as the
release evidence requires:

```bash
/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D "$VERIFY_DATA" stop -m fast
```

Never point restore verification at an original, legacy, live-local, shared,
remote, or otherwise non-disposable database. The restore helper deliberately
has no override for the three protected local ports.

## Direct verification commands

Existing v2 artifacts can be checked without database access:

```bash
cd backend
./scripts/uv.sh run python scripts/backup_database.py --verify \
  /absolute/path/to/backup.json.gz \
  /absolute/path/to/backup.json.manifest.json
```

An explicit restore drill against an already prepared schema uses:

```bash
cd backend
DATABASE_TYPE=postgres \
DATABASE_HOST=127.0.0.1 \
DATABASE_PORT=55447 \
DATABASE_USER=postgres \
DATABASE_NAME=caresync \
CARESYNC_RESTORE_CONFIRM_DISPOSABLE=127.0.0.1:55447/caresync \
./scripts/uv.sh run python scripts/restore_database.py \
  --backup /absolute/path/to/backup.json.gz \
  --manifest /absolute/path/to/backup.json.manifest.json \
  --receipt /private/path/restore-receipt.json
```

Historical v1 backups remain release evidence for their original releases, but
they do not satisfy this cutover gate because they lack same-snapshot direct
counts and a row-only restore digest.

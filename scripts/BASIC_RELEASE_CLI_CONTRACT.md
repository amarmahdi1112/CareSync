# CareSync Basic two-phase release shell contract

This staged shell is deliberately split from ordinary startup:

- `start-basic.sh` never backs up, restores, bootstraps or migrates. Its normal
  mode admits only exact `0042_billing_policy_recert`.
- `basic-release.sh prepare` is non-promoting. It requires exact
  `0039_admissions_decision_spine` and both certified runtime roles initially
  in their healthy `LOGIN` state, quiesces writers, fences the runtime by
  setting both `caresync_basic_app` and
  `caresync_transport_evidence_ingest` to `NOLOGIN`, creates and verifies both
  physical and logical recovery evidence, inventories every physical byte,
  boots a copied physical backup on an independent private high-port
  PostgreSQL rehearsal, seals online and clean-shutdown evidence, restores a
  second fresh high-port clone, migrates and certifies that clone, writes a
  candidate receipt, and leaves the retained database fenced at 0039.
- `basic-release.sh commit` reopens every artifact and requires the exact phrase
  `COMMIT CARESYNC RETAINED 0039 TO 0042` before it migrates retained 0039,
  bootstraps/certifies 0042, verifies the immutable commit receipt, removes the
  fence and starts services.
- `resume-basic-0039.sh` requires the exact phrase
  `RESUME CARESYNC RETAINED 0039 WITH THIS SOURCE`. It can resume only a fully
  prepared candidate whose receipt and current exact-0039 database are
  re-certified as the captured source. It never invokes Alembic. This is a
  one-candidate recovery: once resumed application activity changes source
  business data, that immutable candidate can no longer authorize a later
  restart or commit. Run `prepare` again to capture and certify the new exact
  0039 source before the next resume or promotion.
- `basic-release.sh rollback` is emergency physical recovery after a commit
  has begun. A finalized rollback requires the matching candidate, commit and
  finalization receipts. An interrupted intent-only rollback requires the
  candidate receipt, omits both finalized-receipt flags, and is admitted only
  when that run contains its exact durable commit-attempt intent. Both forms
  require the exact phrase
  `ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039`, reopen every applicable
  artifact, quarantine the changed PGDATA without deletion, promote a
  separately verified same-APFS copy of the rehearsed exact-0039 physical
  backup, and resume it through a rollback-specific bounded runtime window.

Operator entry points:

```text
scripts/basic-release.sh prepare [--clone-port 55000..60999]

scripts/basic-release.sh commit \
  --receipt /absolute/private/run/candidate-receipt.json \
  --confirm "COMMIT CARESYNC RETAINED 0039 TO 0042"

scripts/resume-basic-0039.sh \
  --receipt /absolute/private/run/candidate-receipt.json \
  --confirm "RESUME CARESYNC RETAINED 0039 WITH THIS SOURCE"

scripts/basic-release.sh rollback \
  --receipt /absolute/private/run/candidate-receipt.json \
  --commit-receipt /absolute/private/run/commit-receipt.json \
  --finalization-receipt /absolute/private/run/finalization-receipt.json \
  --confirm "ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039"

scripts/basic-release.sh rollback \
  --receipt /absolute/private/run/candidate-receipt.json \
  --confirm "ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039"
```

The first rollback invocation is the finalized form. The second is the
interrupted intent-only form: do not pass either `--commit-receipt` or
`--finalization-receipt`. Supplying only one finalized-receipt flag is invalid,
and the intent-only form fails closed unless the candidate's release run
contains and validates its exact durable commit-attempt intent.

The shell expects this read-only Python release-contract CLI. Database identity
comes only from the normal `Settings` environment; connection strings and
passwords are never command arguments.

```text
python scripts/basic_release_contract.py certify-clone \
  --restore-receipt RESTORE_RECEIPT \
  --output CLONE_CERTIFICATE

python scripts/basic_release_contract.py inventory-physical-backup \
  --pgdata PHYSICAL_BACKUP_DIRECTORY \
  --output PHYSICAL_BACKUP_INVENTORY

python scripts/basic_release_contract.py verify-physical-backup-inventory \
  --pgdata PHYSICAL_BACKUP_DIRECTORY \
  --inventory PHYSICAL_BACKUP_INVENTORY

python scripts/basic_release_contract.py atomic-rename-no-replace \
  --source OWNER_CONTROLLED_PATH \
  --destination ABSENT_PATH_ON_THE_SAME_PRIVATE_FILESYSTEM

python scripts/basic_release_contract.py observe-physical-rehearsal \
  --physical-backup-manifest PHYSICAL_BACKUP_MANIFEST \
  --physical-backup-inventory PHYSICAL_BACKUP_INVENTORY \
  --retained-identity RETAINED_IDENTITY \
  --observation NEW_REHEARSAL_OBSERVATION

python scripts/basic_release_contract.py certify-physical-rehearsal \
  --observation REHEARSAL_OBSERVATION \
  --rehearsal-pgdata STOPPED_REHEARSAL_PGDATA \
  --physical-backup-manifest PHYSICAL_BACKUP_MANIFEST \
  --physical-backup-inventory PHYSICAL_BACKUP_INVENTORY \
  --retained-identity RETAINED_IDENTITY \
  --receipt NEW_REHEARSAL_RECEIPT

python scripts/basic_release_contract.py verify-physical-rehearsal \
  --observation REHEARSAL_OBSERVATION \
  --physical-backup-manifest PHYSICAL_BACKUP_MANIFEST \
  --physical-backup-inventory PHYSICAL_BACKUP_INVENTORY \
  --retained-identity RETAINED_IDENTITY \
  --receipt REHEARSAL_RECEIPT

python scripts/basic_release_contract.py prepare \
  --clone-certificate CLONE_CERTIFICATE \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --release-payload NEW_RELEASE_PAYLOAD \
  --receipt NEW_CANDIDATE_RECEIPT

python scripts/basic_release_contract.py verify-prepare-receipt \
  --receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...]

python scripts/basic_release_contract.py certify-live \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --receipt NEW_COMMIT_RECEIPT

python scripts/basic_release_contract.py verify-commit-receipt \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --receipt COMMIT_RECEIPT

python scripts/basic_release_contract.py verify-live-commit \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --commit-receipt COMMIT_RECEIPT

python scripts/basic_release_contract.py finalize-live \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --commit-receipt COMMIT_RECEIPT \
  --receipt NEW_FINALIZATION_RECEIPT

python scripts/basic_release_contract.py verify-finalization-receipt \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --commit-receipt COMMIT_RECEIPT \
  --receipt FINALIZATION_RECEIPT

python scripts/basic_release_contract.py certify-resume-0039 \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --authorization NEW_RESUME_AUTHORIZATION

python scripts/basic_release_contract.py verify-resume-authorization \
  --candidate-receipt CANDIDATE_RECEIPT \
  --clone-certificate CLONE_CERTIFICATE \
  --release-payload RELEASE_PAYLOAD \
  --artifact NAME=PATH [--artifact NAME=PATH ...] \
  --authorization RESUME_AUTHORIZATION
```

The required core artifact group is:

```text
backup
backup_manifest
database_restore_receipt
physical_backup_manifest
physical_backup_inventory
physical_rehearsal_observation
physical_rehearsal_receipt
prepared_fence_context
retained_identity
```

The optional family group is all-or-none:

```text
family_vault_bundle
family_vault_manifest
family_vault_restore_receipt
```

The optional staff/transport group is all-or-none:

```text
staff_transport_vault_bundle
staff_transport_vault_manifest
staff_transport_vault_restore_receipt
staff_transport_vault_key
```

`prepare` creates the closed-shape release payload; the shell only supplies a
nonexistent output path. The Python contract never fences roles, migrates,
bootstraps, restores or starts services. Those state changes remain visible and
ordered in the shell. Every successful CLI operation prints:

```text
CARESYNC_RELEASE_CONTRACT_OK SUBCOMMAND RELEASE_OR_CERTIFICATE_ID
```

Fence discharge is also evidence-preserving: after validating that the private
fence directory contains exactly its bound `context` file, the shell atomically
renames the whole directory into the matching release run. It never unlinks the
context first. `EXIT`, `INT` and `TERM` guards re-fence both runtime identities
during every controlled `LOGIN` window; a later retry also reasserts the fence
to recover from untrappable power loss or `SIGKILL`.

An interrupted `prepare` is recoverable without discarding evidence. Before a
fresh release ID is allocated, `prepare` recognizes only an exact private,
source-bound nine-line `status=preparing` fence:

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

The exact paths, source-manifest digest, source/target revisions and prior
writer states must all match. Recovery executes under that captured source and
verifies its manifest before inspecting either possible high-port PostgreSQL
tree (`physical-rehearsal/postgres-data` and `clone/postgres-data`). A live
disposable server is stopped only after the PID file, canonical PostgreSQL
executable, exact PGDATA, high loopback listener, system identifier and
SQL-reported data directory/endpoint all agree; a reused or foreign PID is
never signaled. A proven stale PID is atomically preserved in the run. Partial
offline copies and every other run file remain in place. The retained database
must still be exact 0039 before both writer roles are restored to their
recorded prior states and the whole preparing fence is atomically retired into
that run. A `status=prepared` fence is never auto-reconciled; it remains
commit/resume-only.

All JSON receipts are first completed and fsynced under a unique private
pending name, then published with the platform's atomic no-replace rename.
Interrupted pending files remain as evidence but never poison the final receipt
path. Physical inventory v2 enforces a single-device/no-nested-mount policy,
hashes every data fork (including `pg_wal` and `postgresql.auto.conf`), and
rejects links, ACLs, resource forks, quarantine attributes, special files and
mutable filesystem flags. The OS-managed `com.apple.provenance` marker is the
only ignored extended attribute.

Ports 5432, 5433 and 5434 are permanently excluded from disposable restore
targets. Neither the restore helper nor either release script contains an
Alembic downgrade path.

## Emergency physical rollback

`basic-release.sh rollback` implements the separately gated disaster-recovery
path. Its contract is:

1. Select exactly one evidence shape:
   - finalized rollback: matching candidate, commit and finalization receipts;
   - interrupted intent-only rollback: the matching candidate receipt, no
     `--commit-receipt` or `--finalization-receipt` flag, and the run's exact
     durable commit-attempt intent.

   Both shapes require the exact operator phrase
   `ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039`. Reopen every applicable
   bound artifact before changing live state. A mixed or partial evidence
   shape fails closed.
2. Re-attest the pinned retained PostgreSQL system identifier and canonical
   data directory, quiesce the API, frontend and push worker, fence every known
   application writer role with `NOLOGIN`, and prove that no application
   sessions remain.
3. Run both the complete physical-tree inventory verifier and
   `pg_verifybackup --exit-on-error` against the immutable evidence. Never
   start PostgreSQL directly from, rename, or otherwise mutate that evidence.
4. Require the prepare-time private rehearsal observation and clean-shutdown
   receipt. They prove PostgreSQL 17, exact Alembic 0039, both writer roles
   NOLOGIN, zero other cluster clients, primary/not-in-recovery state,
   loopback/high-port isolation, retained system identity, exact source
   business evidence, and offline `pg_controldata` state `shut down`. Copied
   configuration cannot redirect the first boot: command-line settings pin
   `data_directory`, an isolated config/HBA/ident set, a short private Unix
   socket, disabled SSL/external PID/log collector, and empty preload,
   archive, restore and recovery-end commands before PostgreSQL starts.
5. Reopen the rehearsal receipt, its observation, the complete physical-tree
   inventory, the candidate plus its applicable commit evidence (finalized
   commit/finalization receipts or the exact interrupted commit-attempt
   intent), and the byte-identical retired prepared-fence context immediately
   before promotion.
6. With the retained server stopped and still fenced, atomically rename the
   current `PGDATA` to a timestamped quarantine directory on the same
   filesystem. Never delete or overwrite the quarantine directory.
7. Materialize a new protected partial `PGDATA` from the verified physical
   evidence before promotion, without moving or mutating the evidence itself.
   Re-run the full inventory and `pg_verifybackup`, reject links, external
   tablespaces and special files, prove the same APFS device, then use
   no-clobber renames for quarantine and promotion. Each crash window is
   derived from preserved filesystem state and the private rollback journal.
   An interrupted or invalid partial is atomically moved to a unique evidence
   quarantine and a fresh partial is created; it is never deleted or reused.
   The journal advances monotonically through stopped, copy-verified,
   quarantined, restored and starting phases. A stopped retained-tree receipt
   is sealed before the first rename and verified against the quarantined tree
   on retry. The entire applicable evidence chain is reopened at both atomic
   rename boundaries.
8. Start the restored exact-0039 database while writers remain fenced. Reissue
   and verify a source-compatible 0039 runtime authorization, start the managed
   services, check API and frontend health, and only then restore each writer
   role to its exact pre-fence state and remove the matching rollback fence.
   If power fails after that retirement but before deferred push startup and
   launcher completion, rerunning the same evidence-shape rollback command may
   atomically reactivate only that run's private
   `status=rollback_starting` fence. The candidate, applicable commit evidence,
   authorization, quarantine and partial paths must all match. Services are
   stopped before a down exact-0039 tree is booted; a controlled exit guard
   spans re-entry, and `NOLOGIN` is the first database mutation after
   identity/readiness. The full evidence and byte chain is then reopened
   before startup completion resumes. This is not an ordinary or
   unauthenticated 0039 startup path.
9. Retain the physical evidence, rehearsal receipt and quarantined 0042
   directory until a separate operator-approved retention action.

This recovery path never invokes `alembic downgrade`, never deletes either
cluster, never restores onto a running PostgreSQL directory, and never targets
ports 5432, 5433 or 5434 during rehearsal. The quarantined 0042 cluster and all
release evidence remain until a separate, explicit retention decision.

Both normal startup and release preparation perform local dependency,
runtime-file, vault-root and secret/key checks before they quiesce a healthy
application. Known owner-controlled single-link log/PID files are normalized
to mode 0600; links, foreign owners and hard links fail closed. A controlled
commit/resume/rollback starts the push worker only after receipt finalization
and fence discharge, preventing queued outbox mutations from invalidating
candidate evidence.

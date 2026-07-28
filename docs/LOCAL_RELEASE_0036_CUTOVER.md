# CareSync local release 0036

Last updated: 2026-07-22

## Release state

The checked-in local launcher and the retained PostgreSQL cluster on port 5434
now share the single Alembic head `0036_billing_manual_mode`. The guarded
retained cutover completed on 2026-07-22 from exactly
`0028_childcare_command_spine`; it did not activate a facility or activate
billing.

The 0036 release train promotes these additive source boundaries together:

- 0029 family authority, private family evidence and verified-release
  checkout, with an explicit one-way per-facility activation;
- 0030 staff screening pathways and encrypted evidence history;
- 0031/0032 driver and vehicle records, evidence, independent review and
  exact-retry registry commands, without child dispatch authority;
- 0033 append-only CAD billing facts and reconciliation;
- 0034 owner/administrator transport-registry permission repair;
- 0035 the owner/administrator verified-release activation command; and
- 0036 private/local manual billing, with an immutable organization-owner
  activation record.

Schema availability is not operational approval. Family release stays on the
legacy path until an owner or administrator resolves every readiness item and
performs the exact facility activation. Manual billing stays unavailable for
commands until the organization owner reviews and performs its separate exact
activation. Neither activation is performed by migration or startup.

## Recorded retained-cutover evidence

The launcher froze writers, captured the 0028 source, proved its exact restore
on a fresh PostgreSQL 17 target, migrated the retained database only after that
proof, rebuilt the restricted grants and restarted the loopback API and
administrator frontend.

- The source backup contains 16,260 rows across 77 public tables at revision
  `0028_childcare_command_spine`.
- The exact disposable restore retained all 16,260 rows, including 110
  families and 203 children, and remained at revision 0028.
- The migrated retained database reports revision
  `0036_billing_manual_mode`, 134 public tables plus one public view, 110
  families and 203 children.
- The pre-0029/0030 source had no family or staff/transport evidence tables and
  no corresponding vault bytes, so this cutover correctly required no evidence
  bundle.
- `facility_release_checkout_activations` and
  `billing_manual_activations` both remain empty. Migration and startup did not
  silently authorize either workflow.

The canonical private artifacts are:

- database backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260722-232512-277485.json.manifest.json`; and
- exact-restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260722-232512-277485.json.gz.receipt.json`.

The backup and receipt matched on artifact digest, canonical row digest, every
table count and source revision. The artifact directories are owner-private
mode 0700 and the three files are owner-private mode 0600.

The final integrated source acceptance was 1,094 backend tests passed with 101
explicit opt-in cases skipped and seven non-failing dependency warnings;
administrator 790/790 tests plus production build and zero production audit
findings; staff app 265/265 tests plus TypeScript and the recorded Expo SDK 57
Doctor/export evidence; and extension 78/78 tests plus TypeScript, production
build and zero production audit findings. The API health check reported
PostgreSQL connected and the administrator frontend returned HTTP 200 after
cutover.

## Mandatory maintenance order

For a non-empty database whose revision differs from 0036,
`scripts/start-basic.sh` preserves this order:

1. stop only verified CareSync API and push-worker processes;
2. prove that no application writer or other database client remains;
3. create and re-open-verify a private same-snapshot logical database backup;
4. when the source schema contains family or staff/transport evidence tables,
   create and independently verify the corresponding backup-bound vault
   bundles; when those tables are absent, require the corresponding vault to be
   empty rather than ignoring orphan bytes;
5. restore the database exactly into a fresh, explicitly confirmed disposable
   PostgreSQL target and verify every count plus the canonical row digest;
6. restore each required evidence bundle into a new no-clobber disposable
   vault and require its private receipt;
7. repeat writer and database-session checks;
8. migrate the retained database to exactly
   `0036_billing_manual_mode`;
9. rebuild and audit the restricted runtime grants;
10. bind the stable owner-only transport-ingest credential to its restricted
    database login; and
11. start the push worker, API and frontend only after those gates pass.

The launcher never uses `alembic upgrade head`. Ports 5432, 5433 and 5434 are
permanently forbidden as restore-verification targets. Backup, bundle and
receipt files are no-clobber and must remain on a filesystem that can enforce
directory mode 0700 and file mode 0600.
Only after every preceding gate passes does the launcher attach
`CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true` to the one exact Alembic
subprocess. It is not exported, persisted or applied to tests.

The T7 project volume is ExFAT and is intentionally unsuitable for these
artifacts. In focused verification, ExFAT reported requested mode-0600 test
files as mode 0700; the backup, receipt, secret and vault contracts rejected
them. The same 73 focused contracts passed on the internal permission-capable
filesystem. Do not weaken those checks or point
`CARESYNC_BASIC_BACKUP_DIRECTORY`, `CARESYNC_BASIC_RUNTIME` or a private vault
at T7 merely to save internal space.

The encrypted staff/transport bundle contains ciphertext, not its key. Keep
`$CARESYNC_BASIC_RUNTIME/secrets/staff-screening-vault.key` under separate
approved offline custody and prove that every key ID named by the bundle is
available. The distinct transport-ingest credential is regenerated only when
absent and is rebound after bootstrap without printing plaintext.

## Private manual billing

The local launcher defaults to `CARESYNC_BASIC_BILLING_MODE=manual`. That
server mode does not itself authorize a billing command.

For the current private single-tenant installation, startup may derive the
sole active organization UUID and use it only as the server allowlist. The
owner must still complete the immutable in-product activation review. If there
are no active organizations, the API starts but billing awaits registration
and a restart. If more than one active organization exists, startup refuses
the ambiguous implicit selection.

For a future multi-tenant local installation, provide the intended active
tenant UUIDs explicitly:

```bash
CARESYNC_BASIC_BILLING_MODE=manual \
CARESYNC_BASIC_BILLING_MANUAL_ORGANIZATION_IDS="uuid-one,uuid-two" \
CARESYNC_BASIC_RESTORE_VERIFY_PORT=55447 \
CARESYNC_BASIC_RESTORE_VERIFY_USER=postgres \
  ./scripts/start-basic.sh
```

Every UUID is syntax-checked and must identify an active local organization.
The allowlist is server configuration, not evidence that an owner reviewed or
activated the organization. To keep the billing workspace unavailable, set
`CARESYNC_BASIC_BILLING_MODE=disabled`.

Manual mode records only charges and payment facts completed outside CareSync.
It enables no processor, money movement, automatic invoice issue, external
delivery, tax advice, refund, funding submission or bank settlement. A browser
print/save operation is a local document action, not delivery evidence.

## Inputs required for a future retained cutover or recovery drill

- a fresh loopback PostgreSQL 17 cluster and empty `caresync` database on an
  unprotected high port for exact restore verification;
- the restore target's maintenance user and, if required, password;
- the retained migration/backup identity and any locally required passwords;
- private storage with enforceable 0700/0600 modes for database and vault
  artifacts;
- enough free space on that permission-capable internal filesystem for the
  fresh PostgreSQL cluster, logical backup, bundles and receipts; do not start
  while the internal volume is nearly full;
- custody confirmation for the active staff-vault encryption key; and
- after startup, real owner review of the family-release and manual-billing
  activation screens. Do not pre-create either activation row.

The 2026-07-22 retained cutover met the local technical completion boundary:
the retained head reports 0036, bootstrap and restricted-role startup passed,
health passed, signed-in capability screens showed truthful readiness, and the
new backup/restore receipt was retained. Production, regulatory, accountant,
payment-provider, live extension/provider and physical-operator acceptance
remain separate decisions.

# CareSync Product Slice 0042 Source Release Note

Last updated: 2026-07-23

## Classification

Product slice: `0042_billing_policy_recertification`  
Alembic revision: `0042_billing_policy_recert`  
Status: **verified source integrity repair; retained cutover not performed**  
Checked-in source and launcher target: `0042_billing_policy_recert`  
Retained PostgreSQL 17 head on port 5434: `0039_admissions_decision_spine`

This document records source and disposable PostgreSQL evidence. It is not
`LOCAL_RELEASE_0042_CUTOVER.md`, and no such cutover record exists because the
retained database was not migrated.

## Reason for the revision

The frozen 0033 billing runtime certificate identified one complete,
semantically equivalent PostgreSQL 17 rendering of the 36 billing policies
after dump/restore. The whole catalog was present, RLS remained enabled and
forced, and the other billing tables, functions, triggers, grants and
constraints were intact, but the catalog-expression identity differed from the
canonical source rendering.

Weakening the runtime detector or accepting arbitrary expression drift would
have reduced the security boundary. 0042 instead performs a narrow,
transactional recertification:

- recognize only exact whole-catalog profile A or the independently audited
  dump/restore profile B;
- reject missing, duplicate, mixed, partially changed or unknown profiles
  before replacement;
- require PostgreSQL 17, migration-owned persistent relations and enabled plus
  forced RLS;
- lock the reference and policy tables across preflight, replacement and
  postflight;
- recreate exactly 36 policies from the concise frozen 0033 definitions;
- require exact canonical profile A after replacement; and
- preserve every billing and non-billing row.

SQLite has no PostgreSQL policy catalog, so 0042 is an intentional no-op in
both directions there.

## Downgrade and restore behavior

Downgrade never drops or loosens the recertified policies. It requires exact
profile A and moves only the Alembic marker back to 0041. A drifted profile is
rejected.

PostgreSQL `pg_dump` expands canonical profile A into audited profile B on
restore. The trusted 0042 runtime detector accepts that complete profile only
at installed 0042 ancestry. Replaying 0042 from a disposable 0041 marker
canonicalizes the restored catalog from B back to A. Unknown, mixed or
untrusted-revision catalogs fail closed.

## Disposable proof

The populated disposable clone started with 140 pre-0041 business tables and
16,508 rows. Exact preservation identities were:

- count digest:
  `19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`;
- row digest:
  `ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`;
- backup:
  `/Volumes/T7/.caresync-tmp/0041-proof/populated-0039-pre0041.dump`; and
- backup SHA-256:
  `f6091645ef4744b4b6d9d92761e7a3b27f695ea6ec2940fdd7ceb36e3e17909a`.

Immediately before the dedicated 0042 recertification proof, the populated
0041 source was also captured at:

- `/Volumes/T7/.caresync-tmp/0042-proof/populated-0041-pre0042.dump`; with
- SHA-256
  `55be096d31c90b33cb7f19e625b472defbb60387d4dd56a7fb1fdec0f9a7490c`.

All pre-0041 counts and both digests remained exact through
`0041 -> 0039 -> 0042` and `0042 -> 0041 -> 0042`. The four empty 0041
ledger tables remained empty. Restricted runtime bootstrap and the combined
0041 room-presence plus 0033 billing capability identity passed at the final
0042 source head.

The dedicated fresh PostgreSQL 17 proof passed one complete test covering:

- profile-A migration;
- tamper rejection without moving the revision;
- canonical A postflight;
- data-count preservation;
- restricted-runtime billing certification;
- downgrade refusal on drift;
- dump and restore from A to audited B;
- runtime acceptance of B only at trusted 0042 ancestry;
- replay canonicalization from B to A; and
- downgrade that preserves the secure policy catalog.

## Verification

| Gate | Result |
|---|---|
| Backend complete source sweep | All 135 test files passed |
| Focused backend after 0042 implementation | 45 passed, 1 explicit opt-in case skipped |
| Fresh PostgreSQL 17 recertification/dump-restore proof | 1 passed |
| Source-head runtime grant and backup checks | 39 passed |
| Billing runtime-certificate checks | 8 passed |
| Ruff and launcher shell syntax | Passed |
| Administrator focused regression | 22 files, 193 tests passed |
| Administrator TypeScript and production build | Passed |
| Staff app regression | 297 tests passed |
| Staff TypeScript, Expo Doctor and Android export | Passed; Doctor 20/20, 782 modules |
| Android HBC bundle SHA-256 | `a3667d6da9e033c3a28fec98cf2e9edf4f5ffed51fbeefc0a2bb2c3769aec0fe` |
| Retained 5434 runtime identity | Not exercised at 0042; retained head is still 0039 |
| Retained 5434 migration/cutover | **Not performed** |

## Release boundary

0042 adds no billing product behavior and changes no billing authority. It does
not activate manual billing, issue an invoice, record a payment, allocate
money, create a credit, contact a provider or make a funding decision. It
repairs only the exact policy-catalog certificate needed for the already
bounded billing ledger.

Before retained promotion, the guarded cutover must repeat backup reopen,
same-snapshot restore, complete row/digest comparison, evidence-vault recovery,
0041/0042 migration, restricted-grant rebuild, both capability certificates
and operator acceptance. Until that separate decision, port 5434 remains at
0039 and existing live services must not be restarted through the 0042-pinned
launcher.

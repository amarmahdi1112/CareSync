# CareSync local release 0037

Last updated: 2026-07-23

## Release state

The checked-in local launcher and the retained PostgreSQL 17 cluster on port
5434 share the single Alembic head `0037_billing_agreement_scope`. The guarded
retained cutover completed on 2026-07-23 from exactly
`0036_billing_manual_mode`.

Revision 0037 is a narrow integrity repair. It lets one child receive a new
immutable billing agreement after re-enrollment without weakening the earlier
agreement history:

- enrollment-backed agreements are unique by
  `(organization_id, billing_account_id, enrollment_id)`;
- historical agreements whose `enrollment_id` is null remain unique by the
  partial legacy key `(organization_id, billing_account_id, child_id)`; and
- the superseded all-row
  `uq_bill_agreement_account_child` constraint is absent.

The migration rewrites or deletes no billing fact. Its preflight refuses
ambiguous duplicate enrollment or legacy-null scope, and its downgrade refuses
when legitimate re-enrollment agreements cannot fit the older 0036
one-account/one-child shape.

`0036_billing_manual_mode` remains the protocol boundary for private/manual
billing. Advancing the retained schema to 0037 did not activate that protocol,
issue an invoice, record a payment or change the separate facility-release
boundary. `billing_manual_activations` and
`facility_release_checkout_activations` both remain empty.

## Recorded retained-cutover evidence

The guarded launcher quiesced application writers, captured the exact retained
0036 source, verified the logical database backup and both evidence bundles,
restored all database rows on a fresh PostgreSQL 17 target, and migrated the
retained database only after that proof succeeded. Restricted runtime grants
were then rebuilt before the API and clients were accepted.

- The source backup and disposable restore contain 16,309 rows across all 134
  public source tables at revision `0036_billing_manual_mode`.
- The disposable restore matched every table count and the canonical row
  digest.
- The family-evidence and staff/transport-evidence bundles each produced a
  private no-clobber restore receipt.
- The retained database reports `0037_billing_agreement_scope`, 134 public
  tables plus one public view, 110 families and 203 children.
- The new enrollment-scoped constraint and legacy-null partial index are
  present, and the old account/child constraint is absent.
- The facility-release and manual-billing activation tables each contain zero
  rows.

The canonical private artifacts are:

- database backup:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-005011-912450.json.gz`;
- matching manifest:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/backups/caresync-postgres-20260723-005011-912450.json.manifest.json`;
- exact database restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-005011-912450.json.gz.receipt.json`;
- family-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-005011-912450.vaults/family-evidence.receipt.json`; and
- staff/transport-evidence restore receipt:
  `/Users/amarmuha/Library/Application Support/CareSync Basic/restore-verifications/caresync-postgres-20260723-005011-912450.vaults/staff-transport.receipt.json`.

These artifacts are retained on the internal permission-capable filesystem.
The T7 project volume remains an ExFAT source mirror and is not authoritative
for owner-private 0700 directories or 0600 files.

## Integrated acceptance

The final complete source acceptance passed:

- backend: 1,969 tests, with 102 explicitly opt-in cases skipped;
- administrator: 808/808 tests, TypeScript and production build;
- staff app: 260/260 tests and TypeScript;
- browser extension: 78/78 tests and production build.

The live OpenAPI includes the required canonical ATS and candidate-marketplace
routes and contains zero legacy hiring prefixes. Retired hiring routes are not
mounted. The retained hiring preflight reports zero pending private
invitations, zero invitation-bound applications and zero draft offers; no
legacy record migration was required.

Signed-in live checks passed for Admissions, Billing, Family, Child and Jobs.
The enrollment-to-billing projection truthfully reports 0 setup-ready records
out of 197 active child records; each unresolved record remains an actionable
readiness item rather than being dropped. This is current retained data, not a
claim that billing is activated or that 197 invoices should exist.

## Canonical hiring boundary

The supported hiring surfaces are the employer ATS under `/api/v1/ats` and the
candidate marketplace under `/api/v1/marketplace`, including the employer
marketplace projection under `/api/v1/ats/marketplace`. Both clients use these
same canonical lifecycles and repositories.

The former `/api/v1/hiring` and `/api/v1/candidate/hiring` prefixes are not part
of Basic OpenAPI, and their unused client adapters are retired. This route
consolidation did not delete canonical ATS/marketplace data and did not convert
private invitations into public applications.

## Mandatory maintenance order

For a non-empty retained database whose revision differs from
`0037_billing_agreement_scope`, `scripts/start-basic.sh` must preserve this
order:

1. stop only verified CareSync API and push-worker processes;
2. prove that no application writer or other database client remains;
3. create and re-open-verify one private same-snapshot logical backup;
4. capture and verify every required evidence bundle, or prove the
   corresponding authoritative vault is empty;
5. restore the database exactly into a fresh, explicitly confirmed disposable
   PostgreSQL target and verify every count plus the canonical row digest;
6. restore each required evidence bundle into a new no-clobber disposable
   vault and require its private receipt;
7. repeat writer and database-session checks;
8. migrate the retained database to exactly
   `0037_billing_agreement_scope`;
9. rebuild and audit restricted runtime grants;
10. bind the stable owner-only transport-ingest credential to its restricted
    database login; and
11. start the push worker, API and clients only after every gate passes.

The launcher never uses `alembic upgrade head` against the retained database.
Ports 5432, 5433 and 5434 remain forbidden as restore-verification targets.
Neither migration nor startup may create a facility-release or manual-billing
activation.

## Next bounded slice

Revision `0038_public_job_catalog_outbox` is the next bounded product slice. It
was not part of release 0037 and is now in implementation, not released or
retained. Its purpose is a privacy-safe durable public-job catalog
invalidation/outbox so closure of an organization's final public listing can be
replayed without relying only on app foreground/resume recovery. It must carry
no candidate-private data, preserve the canonical ATS/marketplace boundary and
pass the same exact guarded release process before it may be described as
retained.

Release 0037 is a local technical release, not production, regulatory,
accountant, payment-provider, live-provider or physical-operator acceptance.

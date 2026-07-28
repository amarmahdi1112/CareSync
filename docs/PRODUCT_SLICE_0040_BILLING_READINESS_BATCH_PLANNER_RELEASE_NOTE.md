# CareSync Product Slice 0040 Release Note

Last updated: 2026-07-23

## Classification

Product slice: `0040_billing_readiness_batch_planner`  
Status: **verified source/product slice; signed-in administrator acceptance pending**  
Retained Alembic head: `0039_admissions_decision_spine`  
Schema migration: **none**  
Release-pin change: **none**

This is a product-slice release note, not an Alembic cutover record. The retained
database, launcher target and release pin remain exactly 0039.

## Delivered

0040 adds a dedicated administrator setup planner at
`/billing?view=setup`. It:

- converts enrollment-to-billing readiness into deterministic account/payer,
  rate, agreement, ready and manual-review waves;
- exposes privacy-bounded server paging, filtering and search;
- preserves full affected counts and membership digests while limiting child
  previews and option lists;
- previews one actionable wave without writing;
- normalizes only account open, payer assignment, rate publish and agreement
  establish commands;
- requires current effective windows containing the organization-local plan
  date;
- keeps inactive, ambiguous, unattested or incomplete source scopes in manual
  review;
- allows preview while owner activation is pending but keeps Apply disabled;
- revalidates the exact snapshot before the first command;
- runs one existing canonical command at a time;
- refreshes and re-proves all remaining intents after every exact receipt;
- stops on drift, rejection or uncertainty without hiding completed receipts;
  and
- routes unresolved protected operations to the existing Billing recovery
  surface.

The retained FastAPI OpenAPI document contains:

- `GET /api/v1/billing/readiness/batch-plan`; and
- `POST /api/v1/billing/readiness/batch-plan/preview`.

Retained API health and both routes are live.

## Safety boundary

Plan and preview are read-only. Apply does not create a new write path: it reuses
the existing protected billing preparation, command, receipt and recovery
protocol.

0040 does not:

- activate manual billing;
- issue or deliver invoices;
- record or allocate payments;
- create credits;
- contact a provider;
- move money;
- determine tax or funding eligibility;
- submit claims; or
- change the database schema or release pins.

## Verification

| Gate | Result |
|---|---|
| Focused backend planner | 9 passed |
| Portable billing | 34 passed, 1 skipped |
| Fresh PostgreSQL 17 RLS/no-write | 1 passed |
| Administrator frontend full suite | 128 files, 865 tests passed |
| Administrator production build | Passed; 881 modules transformed |
| Build warnings | Existing chunk-size advisory only |
| Retained API health | Live |
| Batch-plan OpenAPI routes | Both live |
| Signed-in setup-planner walkthrough | Pending |

The PostgreSQL proof establishes restricted-runtime tenant isolation and no
billing-row mutation by plan or preview. The frontend evidence includes strict
response parsing, loading/empty/error states, owner-activation gating, stale
snapshot rejection before first execution, realtime invalidation, delayed
receipt recovery, partial-stop behavior, current-window browser bounds and
bypassed-input rejection.

Retained live read-only acceptance returned schema v1 for organization-local
`2026-07-23` with 111 groups: 102 account/payer and nine manual review.
`apply_available=false` and `manual_activation_required=true` preserved the
absent activation. A one-group preview returned one `account_open` intent,
zero blocks and the supplied operation identifier. Exact post-preview counts
remained zero for every operational billing table and manual activation; the
role backup table remained at three rows. The retained head stayed 0039, API
port 3002 and administrator port 5174 were healthy, and the setup route
returned HTTP 200. This is live API/read-only acceptance, not signed-in
browser-click acceptance.

The separately prepared disposable billing sandbox has backup
`/Volumes/CareSyncTests/caresync-billing-sandbox-backups/caresync-56544-pre0039-20260723-065358.dump`
and SHA-256
`3e198aef786ec7a0bc03d6eb9a2978c3c248024a693cf301d3492789198a44f6`.
It was explicitly migrated from 0033 to 0039, restricted grants were rebuilt,
API port 3302 was healthy with both routes live, manual activation remained
zero, and administrator port 5274 was wired to 3302. It is a disposable test
sandbox, not an 0040 schema migration or retained cutover.

## Acceptance still required

The new source and API boundary are verified. Before recording signed-in
administrator acceptance, an authorized operator must:

1. open `/billing?view=setup` in the retained runtime;
2. verify paging, search, filters and manual-review source links;
3. verify preview while activation is pending and confirm Apply remains
   disabled;
4. if a separately authorized disposable writable billing tenant is used,
   exercise one reviewed setup sequence and exact recovery without touching the
   retained private data; and
5. record accessibility and responsive-layout observations.

No production finance, provider, parent or funding acceptance is implied.

## Architecture

The normative design, API, proof and recovery contract is
[`BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md`](BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md).

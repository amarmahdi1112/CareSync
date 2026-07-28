# CareSync 0040 Billing Readiness Batch Planner Architecture

Last updated: 2026-07-23

## Status and release boundary

`0040_billing_readiness_batch_planner` is a verified source/product slice. It
adds no Alembic revision and creates no table, column, grant, trigger or seed
row. The retained database, launcher target and release pin remain exactly
`0039_admissions_decision_spine`.

The two planner API routes are mounted in the retained FastAPI OpenAPI document
and retained API health is green. Retained read-only API acceptance and
automated backend, PostgreSQL and administrator-frontend evidence are green. A
signed-in administrator browser-click walkthrough of the new
`/billing?view=setup` surface has not yet been recorded and remains a separate
acceptance item. This document therefore does not claim a new live-local schema
release or completed signed-in UI acceptance.

0040 reuses the released billing readiness projection, billing capability
boundary, canonical preparation protocol, append-only commands, exact receipts
and recovery register. It does not activate billing or introduce a second write
path.

## Product purpose

Before an invoice can be reviewed, a child needs a coherent dependency chain:

1. a family billing account and current accountable payer;
2. a current rate for the enrolled facility, program and age scope; and
3. an enrollment-scoped billing agreement pinned to the current rate version.

The existing `/api/v1/billing/readiness` projection identifies the first
missing dependency per active enrollment. 0040 turns that projection into a
deterministic, privacy-bounded work plan. An administrator can review one
dependency wave, preview the exact canonical command intents without writing,
and—only when the existing billing runtime is already writable—apply those
intents sequentially through the canonical billing command boundary.

The planner never manufactures payer, rate, agreement, enrollment or source
authority. Ambiguous or unsafe groups remain manual review.

## Explicit non-goals

0040 does not:

- create or imply a database migration;
- change `RELEASED_REVISION` or any release pin;
- activate private/manual billing for an organization;
- issue, generate or deliver an invoice;
- record, allocate, process or move a payment;
- create a credit, refund, tax receipt or accounting close;
- contact a payment, email, document or government provider;
- infer funding eligibility or submit a funding claim;
- convert legacy invoice data;
- make a ready group billable without the existing capability and permission
  checks; or
- allow a warning acknowledgement to override a blocked or stale command.

## Canonical dependency waves

The planner produces five mutually exclusive wave types:

| Wave | Meaning | Batch action |
|---|---|---|
| `account_payer` | A family needs an account or current payer assignment | `account_open` or `account_payer_assign` |
| `rate_plan` | A facility/program/age scope needs a current rate | `rate_version_publish` |
| `agreement` | One enrollment needs a current enrollment-scoped agreement | `agreement_establish` |
| `ready` | Account, payer, current rate and current agreement align | None |
| `manual_review` | Source authority, scope, cardinality or effective dates cannot be resolved safely | None |

Only the first three waves are actionable. A preview contains one actionable
wave only. Ready and manual-review groups cannot become commands.

Account and payer work is grouped by family because one account/payer decision
can affect multiple children. Rate work is grouped by facility, program and age
scope. Agreement work remains enrollment-specific. The planner preserves the
full affected count and a SHA-256 membership digest while returning at most 25
child summaries per group. Payer and rate option lists are bounded at 50.

Inactive programs, missing synthetic-source attestations in sandbox mode,
missing guardian/rate authority, conflicting scopes, unsafe option
cardinality, empty effective windows and other unresolved conditions become
non-actionable `manual_review` groups with stable block codes and a safe source
action path.

## Read-only plan contract

### `GET /api/v1/billing/readiness/batch-plan`

The plan route requires `billing:read` and the existing billing runtime
availability boundary. It accepts:

- optional `wave`;
- optional readiness `status`;
- optional search text capped at 80 characters;
- `limit` from 1 to 100;
- `offset` from 0 to 10,000; and
- an optional 64-character `snapshot_token` for exact continuation or
  pre-apply revalidation.

The response schema is `billing-readiness-batch-plan-v1`. It contains:

- organization, generation time, organization-local `as_of_date` and realtime
  sequence;
- an immutable snapshot token;
- truthful `apply_available` and `manual_activation_required` flags;
- complete wave counts;
- bounded page metadata; and
- deterministic plan groups with source scope, actionability, block reason,
  affected-membership proof and bounded options.

Filtering and searching happen server-side against the complete group
membership. Search can match a family or child omitted from the 25-row display
preview without disclosing the rest of the group.

## Snapshot and stale-review protection

The snapshot token is a canonical SHA-256 digest of:

- schema version;
- organization and organization-local plan date;
- realtime sequence;
- every deterministic group and option;
- reserved rate codes; and
- the complete membership search index.

The server rebuilds the plan in a read-only projection snapshot. If a caller
supplies a token that no longer matches, the route returns
`billing_readiness_batch_snapshot_advanced` with `restart_required=true`.

The administrator client also rejects:

- an organization mismatch;
- an older accepted realtime sequence;
- an unexpected response key or enum;
- incoherent paging/count/truncation proofs;
- duplicate group or operation identifiers;
- an unsafe local action/execute path; and
- any command type outside the four setup commands.

Immediately before the first write, the client re-requests the plan using the
reviewed snapshot token. No protected command is sent if this exact preflight
fails.

## Read-only preview contract

### `POST /api/v1/billing/readiness/batch-plan/preview`

Preview requires `billing:manage`. Its request contains:

- the exact plan snapshot token;
- one actionable wave; and
- unique group selections with unique client operation identifiers and
  explicit reviewed inputs.

Preview rebuilds the canonical plan, rejects a stale token, validates each
selection against current source authority, and returns
`billing-readiness-batch-preview-v1`. The response is explicitly read-only and
contains:

- ordered immutable intents;
- blocked selections with stable codes and messages;
- command type, target scope and request hash;
- exact request and preparation payloads;
- the existing canonical execution path; and
- affected counts.

Preview does not insert a preparation row, execute a command, activate billing
or mutate source facts.

Rate and agreement windows must contain the plan `as_of_date`. The backend is
authoritative. The administrator form mirrors the rule with date bounds and
defensive validation so a bypassed browser constraint still cannot reach
preview:

- rate start is on or before the plan date and a finite end is on or after it;
- agreement start is within the canonical lower bound and on or before the plan
  date; and
- a finite agreement end is on or after both its start and the plan date, and
  no later than the canonical upper bound.

An existing rate option is disabled when its latest version cannot be revised
into a current rate. Agreement frequency and family amount are derived from the
selected canonical rate; 0040 does not allow the operator to invent a different
frequency or split.

## Apply and exact-recovery protocol

Apply is available only when all of these facts agree:

- the user has `billing:manage`;
- the server capability reports writes available;
- the organization has completed the existing owner-controlled manual
  activation when manual mode requires it;
- both plan and preview report apply available;
- at least one preview intent exists;
- the administrator attests to the exact ordered sequence;
- no protected billing operation or journal error is unresolved; and
- no apply is already running.

The client executes one intent at a time:

1. persist the redacted approved operation proof before preparation;
2. prepare through the existing canonical billing preparation endpoint;
3. require preparation command, target and request hash to match the reviewed
   proof exactly;
4. execute the existing account, payer, rate or agreement command;
5. require the exact operation, command and request-hash receipt;
6. refresh the canonical plan;
7. re-preview every remaining selection under the new snapshot; and
8. compare every remaining immutable intent before sending the next command.

Any drift, blocked remainder, lost write capability, delayed receipt, uncertain
outcome or command rejection stops the sequence. Confirmed prior receipts are
not rolled back or hidden. An uncertain operation retains only its redacted
proof and locks later work until exact reconciliation. The setup surface always
links unresolved operations to the existing Billing overview recovery
workspace.

No invoice, payment, allocation or credit method is imported into the setup
workspace.

## Realtime and cross-feature integration

Realtime remains a quiet invalidation hint. The setup planner reloads canonical
REST and invalidates any preview when relevant facts change. Its billing
consumer covers:

- manual activation, account, rate, agreement, invoice, payment, allocation
  and credit entities;
- family, child and enrollment facts; and
- facility and facility-program lifecycle facts.

Routine planner synchronization does not create a human-attention notification.
The event cursor is not record authority, and a stale preview never survives a
canonical refresh.

## Verification evidence

Recorded 2026-07-23 evidence:

- focused backend planner matrix: **9 passed**;
- portable billing matrix: **34 passed, 1 skipped**;
- fresh PostgreSQL 17 RLS/no-write proof: **1 passed**;
- administrator frontend full suite after final current-window changes:
  **128 files, 865 tests passed**;
- administrator production build: **passed, 881 modules transformed**;
- build advisory: only the pre-existing chunk-size advisory;
- retained API health: **live**;
- retained OpenAPI: both batch-plan routes are **live**; and
- signed-in `/billing?view=setup` administrator acceptance: **pending**.

The PostgreSQL proof uses a fresh restricted runtime context and demonstrates
that plan and preview preserve tenant RLS and create no billing rows. The
planner-focused and portable matrices cover deterministic grouping, privacy
bounds, paging/search, stale tokens, permission separation, invalid options,
source-attestation boundaries, current effective windows and the absence of
planner writes.

Retained live read-only acceptance returned schema v1 for organization-local
`2026-07-23` with 111 groups: 102 account/payer groups and nine manual-review
groups. It truthfully returned `apply_available=false` and
`manual_activation_required=true`. A one-group preview returned one
`account_open` intent, zero blocks and preserved the supplied operation
identifier. Immediately afterward, every operational billing table and manual
activation still contained zero rows; the role backup table remained at three
rows. The retained Alembic head stayed 0039, API port 3002 and administrator
port 5174 were healthy, and the setup route returned HTTP 200. This is live
API/read-only acceptance, not signed-in browser-click acceptance.

A separate disposable billing sandbox was backed up before operator testing at
`/Volumes/CareSyncTests/caresync-billing-sandbox-backups/caresync-56544-pre0039-20260723-065358.dump`
with SHA-256
`3e198aef786ec7a0bc03d6eb9a2978c3c248024a693cf301d3492789198a44f6`.
It was explicitly migrated from 0033 to 0039, its restricted grants were
rebuilt, API port 3302 returned healthy with both planner routes live, manual
activation remained zero, and administrator port 5274 was wired to 3302. This
is disposable test-sandbox preparation, not an 0040 migration, retained
cutover or release pin.

## Authoritative source map

- Planner: `backend/app/basic/billing_readiness_planner.py`
- Schemas: `backend/app/basic/billing_schemas.py`
- Routes and preview normalization: `backend/app/api/basic/billing.py`
- Backend safety matrix:
  `backend/tests/test_basic_billing_readiness_batch_planner.py`
- PostgreSQL proof: `backend/tests/test_basic_postgres_billing_ledger.py`
- Administrator workspace:
  `frontend-redesign/src/features/billing/BillingSetupWorkspace.tsx`
- Strict client contract:
  `frontend-redesign/src/features/billing/billingBatchPlanApi.ts`
- Protected operation boundary:
  `frontend-redesign/src/features/billing/billingOperation.ts`
- Render/integration tests:
  `frontend-redesign/src/features/billing/BillingSetupWorkspace.render.test.ts`
  and
  `frontend-redesign/src/features/billing/BillingSetupWorkspace.integration.test.ts`

The product-slice evidence and acceptance boundary are summarized in
`PRODUCT_SLICE_0040_BILLING_READINESS_BATCH_PLANNER_RELEASE_NOTE.md`.

# API parity inventory

The legacy GraphQL schemas defined 200 root operations: 70 queries and 130 mutations.
The active private application no longer ships an Apollo client or GraphQL operations. The
inventory below is migration history: compatibility routes are not automatically part of the
default Basic API, and legacy invoicing is not the new billing authority.

| Legacy module | Queries | Mutations | Total | FastAPI status |
|---|---:|---:|---:|---|
| Activity log | 3 | 2 | 5 | Scoped REST reads active in dashboard and log screens |
| AI | 3 | 3 | 6 | Child insight and invoice-agent adapters remain compatibility-only; invoice AI is not part of 0033; Basic adds a separate bounded extension name-match companion route |
| Authentication | 7 | 9 | 16 | Login, current user, roles, and permissions in progress |
| Claim generation | 11 | 11 | 22 | V2 simulation and active scheduling-pipeline REST workflow implemented |
| CSV import | 0 | 5 | 5 | Detect, validate, mapped import, and direct import REST workflows implemented |
| Email | 2 | 2 | 4 | Invoice SMTP/test/delivery adapters are compatibility-only; Basic 0033 has no invoice delivery |
| Families and children | 7 | 22 | 29 | Rich reads and organization-scoped CRUD use REST |
| Invoicing | 20 | 41 | 61 | Legacy compatibility router only when advanced routes are explicitly enabled; absent from default Basic OpenAPI |
| Letterheads | 2 | 2 | 4 | Not started |
| Organizations | 4 | 13 | 17 | Current profile and JSON preference REST workflows implemented |
| Pricing | 2 | 2 | 4 | Not started |
| Relationship detection | 1 | 3 | 4 | Family relationship and sibling workflows use REST |
| Scheduler | 4 | 12 | 16 | Certified V3 generation and active review/export REST workflow implemented; V2 deprecated |
| Signatures | 4 | 3 | 7 | Scoped REST reads and guarded creation implemented |
| **Total** | **70** | **130** | **200** | |

## Authentication REST mapping

| GraphQL operation | REST replacement | Status |
|---|---|---|
| `login` | `POST /api/v1/auth/login` | Implemented and tested |
| `me` | `GET /api/v1/auth/me` | Implemented and tested |
| `roles` | `GET /api/v1/auth/roles` | Implemented and mapped to live DB |
| `permissions` | `GET /api/v1/auth/permissions` | Implemented and mapped to live DB |
| Remaining auth operations | Versioned `/api/v1/auth` and `/api/v1/users` routes | Pending write-mode parity |

Basic is writable through its dedicated, tenant-scoped command routes. Each
mutation remains governed by membership, permission, feature capability,
exact-retry and PostgreSQL RLS boundaries; runtime-gated release and billing
commands remain unavailable until their separate owner-controlled activations.

## Canonical hiring REST mapping

The supported Basic hiring API is:

- employer ATS and pipeline commands under `/api/v1/ats`;
- candidate registration, profile, jobs, applications, interviews and offers
  under `/api/v1/marketplace`; and
- the employer-facing marketplace projection under
  `/api/v1/ats/marketplace`.

Employer and candidate commands share the same lifecycle and repository
boundaries. Historical 0037 OpenAPI acceptance found every required canonical route,
zero paths under the legacy `/api/v1/hiring` or
`/api/v1/candidate/hiring` prefixes, and no retired invitation/handoff route.
The corresponding unused legacy client adapters are retired. Retained
preflight found zero pending private invitations, zero invitation-bound
applications and zero draft offers, so canonicalization required no hiring-data
rewrite.

## Claim simulation REST mapping

`POST /api/v1/claims/simulate` accepts camelCase legacy-style JSON or snake_case JSON.
Its deterministic golden fixture matches the compiled TypeScript engine for projected
hours, profiles, attendance days, fairness, optimization iterations, and utilization.

## Scheduler REST mapping

`POST /api/v1/schedules/generate` uses deterministic Scheduler V3 by default. Claims
are normalized explicitly to five-minute ticks, assignments are independently audited,
and the adapter preserves the established entries, statistics, fairness, utilization,
warnings, and audit response shape. Generated entries include the canonical child name
so review and export views do not depend on UUID-to-name reconstruction. V2 remains
available only through `SCHEDULER_ENGINE_VERSION=v2` as a deprecated emergency rollback.

Generation now fails closed on duplicate child IDs/dates, non-finite hours, malformed
or overlapping time blocks, ambiguous overrides, and organization closure dates. The
engine enforces enrollment/exclusion eligibility, conservative partial-slot capacity,
claimed-hour ceilings, canonical deterministic ordering, and post-generation invariants. Results
include an algorithm version, input hash, completion/shortfall statistics, and
collision-safe batch ID. Incomplete V3 results may be inspected as diagnostics but
cannot be persisted or exported. Fairness is measured by claim-fulfillment ratio rather than
raw hours, so children with legitimately different hour targets are compared correctly.

`GET /api/v1/schedules/closures` calculates Alberta's nine statutory holidays for
the requested year, merges configured optional holidays and custom daycare closure
dates, and returns them pre-marked to the scheduling UI. `PATCH` persists the optional
and custom closure policy without changing database names or replacing unrelated
organization preferences. The generation endpoint independently rechecks those
closures, so a stale frontend cannot silently schedule a statutory or configured
daycare closure.

When `persist=true`, schedule generation verifies every child belongs to the current
organization and writes the validated batch to `scheduled_attendance` in one database
transaction. Large batches are chunked without sacrificing all-or-nothing behavior.
The response includes the persisted entry IDs, and deleting a batch uses a dedicated,
organization-scoped transaction.

PDF claim parsing now performs organization-scoped child matching using normalized
first/middle/last-name variants, `LAST, FIRST` handling, conservative fuzzy matching,
and date-of-birth confirmation. Ambiguous identities remain unmatched. Matching is
repeated during save so stale browser results cannot silently store every claim as
unmatched, and saved batches can be safely re-matched.

## Legacy compatibility invoicing mapping

`POST /api/v1/invoicing/billing-runs/preview` performs a read-only family-by-family
preflight for a selected billing period. It resolves effective rates and funding,
reports warnings and existing-period invoices, and exposes the expected parent
portion before drafts are created. Bulk generation validates date chronology and
skips duplicate periods or families without billable children by default. This documents the
explicit advanced compatibility API only. It is absent from default Basic OpenAPI, is not used by
the Basic administrator, and is not an authority for the 0033 ledger.

## Basic billing REST mapping

The default Basic OpenAPI includes the authenticated `/api/v1/billing` router. Its capability probe,
owner-only manual-activation status/command and protected record routes are present in source even
when the runtime capability is unavailable. Reads cover overview, a coherent paginated workspace,
source options, account detail, invoice document preview and
account/invoice/payment/allocation/credit/rate/agreement lists. The command protocol exposes
preparation, actor-private status and finalized-absence recovery. Eight ledger mutations cover
account open, payer assignment, rate-version publication, agreement establishment, invoice issue,
off-platform payment record, allocation and credit.

The `0033_billing_ledger` foundation remains a synthetic test/sandbox boundary. Its PostgreSQL
writes require an attested disposable loopback high-port target, an allowlisted organization and
synthetic-source attestations. SQLite may serve disabled/shadow reads but never commands. Its
record-bearing projections remain labelled `TEST/SYNTHETIC — NOT A REAL INVOICE`.

The checked-in `0036_billing_manual_mode` target adds a separate private/local boundary. It requires
server attestation, an organization allowlist and an explicit immutable owner activation against an
empty organization ledger; no migration or startup action performs that activation. Once activated,
source options resolve the organization's real families, guardians, children, active enrollments
and programs, and every record-bearing projection is labelled
`PRIVATE/MANUAL — OFF-PLATFORM RECORD`.

Both modes use the same eight canonical collections: `accounts`, full historical
`payer_versions`, `rate_plans`, `agreements`, `invoices`, `payments`, `allocations` and `credits`.
An invoice references the exact payer-version and guardian provenance used at record time; changing
the account's current payer cannot rewrite, relabel or invalidate an earlier invoice. The
read-only document endpoint returns a canonical, digest-bound invoice record with immutable line
and payer snapshots plus current allocations, credits and outstanding balance. Browser
Print / Save PDF creates a local copy only: CareSync does not generate or deliver a server PDF,
process or move money, issue automatically, refund funds, provide tax advice, submit funding or
expose a parent billing portal.

Revision `0037_billing_agreement_scope` leaves that 0036 protocol unchanged. It
makes enrollment-backed agreements unique by organization, account and
enrollment, while a partial organization/account/child uniqueness rule applies
only to historical null-enrollment agreements. The superseded all-row
account/child constraint is absent, and no billing fact was rewritten.

The read-only `/api/v1/billing/readiness` and
`/api/v1/billing/families/{family_id}/summary` projections connect Admissions,
Billing, Family and Child without creating financial authority. Family invoices
remain settlement truth; child summaries attribute charges only. Live
acceptance reported 0 setup-ready records out of 197 active child records and
retained a concrete action for every unresolved record.

The launcher, source and retained port-5434 database now share
`0039_admissions_decision_spine` after the recorded exact guarded cutover. This
proves local schema promotion, not an organization's owner-reviewed 0036 manual
activation: `billing_manual_activations` remains empty. Revision 0037's
agreement-scope rules and the 0038 public-catalog replay are preserved
unchanged.

## Basic extension name-matching companion mapping

`POST /api/v1/ai/name-matches` is the bounded local companion used by the
CareSync browser extension. It accepts only bounded candidate names and opaque
identifiers, rejects attendance payloads, and keeps loopback/extension origins
within the explicit adapter boundary. It does not make the live third-party
portal workflow, a model-provider call or portal mutation part of the Basic
administrator API. The extension's live authenticated portal acceptance
remains a separate operator decision.

## Legacy resource REST mapping

`GET /api/v1/resources/{table}` and `GET /api/v1/resources/{table}/{id}` expose all
40 mapped legacy tables with direct or parent-derived organization scoping. Passwords,
SMTP credentials, and large binary/base64 fields are excluded. Generic create, update,
and confirmed-delete routes are implemented but remain locked while
`DATABASE_READ_ONLY=true`; identity and role tables require dedicated workflows.

## Frontend REST mapping

The private React app authenticates and refreshes sessions through REST. The Basic source uses its
dedicated operational endpoints and exposes `/billing` only when the server capability and caller
permission are explicit. Navigation remains preview-labelled for the 0033 sandbox and becomes live
only when the server confirms writable, owner-activated 0036 manual mode. The old `/invoicing/*`
client route renders NotFound. Apollo, GraphQL documents, and the legacy unreachable GraphQL
screens have been removed. The FastAPI service does not expose a GraphQL endpoint.

The administrator Jobs screen uses only the canonical ATS/marketplace API, and
the staff candidate experience uses only the canonical marketplace client.
Release `0038_public_job_catalog_outbox` adds a durable public-safe catalog
stream for unaffiliated candidates. Its payload represents only the minimum
public projection/invalidation identity, never draft status, organization
identity, candidate data, applications, interviews, offers, credentials, or
free-text content. Exact replay and closure of the last public listing no
longer depend solely on app foreground/resume.

Release `0039_admissions_decision_spine` adds private administrator
applications, deterministic waitlist lanes, offers, exact retry, duplicate
review and atomic canonical conversion under `/api/v1/admissions`. The existing
read-only remediation queue remains separate.

Verified source/product slice `0040_billing_readiness_batch_planner` adds
`GET /api/v1/billing/readiness/batch-plan` for `billing:read` and
`POST /api/v1/billing/readiness/batch-plan/preview` for `billing:manage`.
Both routes are live in the retained OpenAPI document. Plan and preview are
read-only; reviewed Apply reuses the existing protected account, payer, rate
and agreement endpoints rather than adding another mutation path. 0040 adds no
schema migration, billing activation, invoice, payment, provider or funding
behavior. Retained live API/read-only acceptance is complete; signed-in
administrator browser-click acceptance remains pending.

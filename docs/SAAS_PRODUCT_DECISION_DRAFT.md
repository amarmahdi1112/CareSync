# CareSync SaaS product decision draft

> Status: discussion draft only. Nothing in this document authorizes a database
> reset, production deployment, payment activation, or collection of customer data.
> Decisions marked `OPEN` must be approved before implementation begins.

## Product thesis

CareSync becomes an Alberta-first, Canada-ready childcare operations platform for
licensed organizations. It combines the existing strengths in claims, attendance,
invoicing, schedule construction, imports, and auditable automation with a true
multi-tenant SaaS foundation.

CareSync is not the Government of Alberta and does not issue licences, determine
funding eligibility, or replace the Childcare Licensing Portal. It prepares,
validates, retains, and exports operational evidence and can provide explicitly
reviewed browser assistance where an official integration is unavailable.

## Proposed launch boundary

| Decision | Proposed default | Status |
|---|---|---|
| Market | Alberta-first branding with Canada-ready architecture | OPEN |
| Initial customer | Licensed facility-based daycare and out-of-school-care operators | OPEN |
| Organization shape | One organization may manage one or many licensed facilities | OPEN |
| Pending applicants | Demo/checklist workspace only; no verified badge or production child data | OPEN |
| Staff portal | Membership foundation now; full staff product after the first commercial foundation | OPEN |
| Parent payment processing | Not in the first release; record invoices/payments first | OPEN |
| Hosting | Canadian region for application data, files, backups, and logs | OPEN |
| Legacy data | Preserve offline as a regression/migration source; new active database starts empty | OPEN |

Family day homes, family day home agencies, stand-alone preschools, parent mobile
apps, payroll, and nationwide regulatory packs are deliberately later expansions.

## Public product surface

The unauthenticated site contains:

- `/` — outcome-led landing page
- `/product` — product overview
- `/alberta` — Alberta-specific operational workflows and boundaries
- `/features/*` — attendance, scheduling, claims, billing, compliance, and reporting
- `/pricing` — transparent Canadian pricing
- `/security` — privacy, hosting, encryption, access, backup, and breach practices
- `/about` and `/contact`
- `/login`, `/register`, `/forgot-password`, and `/accept-invitation`
- legal pages for terms, privacy, subprocessors, acceptable use, and data processing

The visual direction is a futuristic command centre with restrained motion,
excellent contrast, reduced-motion support, fast keyboard navigation, and a calm,
trustworthy public presentation.

## Proposed pricing experiment

All prices are proposed in Canadian dollars, per month, before tax. Payment
processing is disclosed separately.

| Plan | Proposed price | Boundary |
|---|---:|---|
| CareSync Core | $79 per location | Up to 100 active children; registration, families, attendance, invoicing, and core reporting |
| CareSync Alberta Pro | $129 per location | Core plus Alberta claims, V3 scheduling, audits, imports, AI matching, and compliance automation |
| CareSync Network | $249 for 3 locations | Consolidated controls and reporting; $69 per additional location |

Proposed commercial terms:

- 30-day trial without a credit card.
- Two months free for annual billing.
- Unlimited staff and family accounts within fair-use controls.
- No mandatory setup fee.
- A founding-centre offer of Alberta Pro at $79 per month for 12 months.
- A payment failure moves through grace and read-only states; it never deletes
  operational records automatically.

Pricing must be represented as effective-dated catalogue data and entitlements,
not hard-coded feature checks.

## Organization registration journey

Onboarding is resumable, autosaved, and represented by an explicit state machine.

1. **Owner identity**
   - Email verification, password/passkey setup, terms and privacy acceptance.
   - MFA is required before production activation.
2. **Organization identity**
   - Legal and operating name, entity type, business identifiers, registered and
     mailing addresses, billing contact, authorized representative, and privacy
     contact.
3. **Facility lookup**
   - Search Alberta public childcare data by name, location, and program type.
   - Prefill only public registry fields and retain source and retrieval time.
4. **Facility control verification**
   - The registrant confirms the public record and supplies evidence that they are
     authorized to act for the licence holder.
   - Registry presence alone never produces a verified status.
5. **Licensed operations**
   - Program types, rooms, age groups, licensed capacities, operating hours,
     extended/overnight approval, closures, calendars, and emergency contacts.
6. **Funding configuration**
   - Operator-declared agreements for affordability, subsidy, workforce support,
     inclusive childcare, effective dates, and claim-authorized roles.
   - CareSync does not infer eligibility and never stores government credentials.
7. **Privacy and records**
   - Privacy officer, collection purposes, consent configuration, retention classes,
     legal hold, access/correction, export, and deletion policy.
8. **Plan and trial**
   - Plan selection, transparent limits, tax address, and hosted subscription checkout.
9. **Readiness review**
   - Blocking requirements, warnings, verification state, and an operator attestation.
10. **Workspace activation**
    - Provision an empty tenant, establish the owner membership, and offer imports,
      staff invitations, or guided setup.

### Independent lifecycle states

These states must not be collapsed into one `active` flag:

- Onboarding: `draft -> submitted -> needs_review -> complete`
- Organization: `pending -> active -> suspended -> deletion_scheduled -> deleted`
- Facility: `draft -> pending_verification -> active -> inactive`
- Subscription: `trialing -> active -> past_due -> grace -> canceled`
- Workspace access: `setup -> operational -> read_only -> locked`

## Tenant and identity model

The minimum identity hierarchy is:

```text
User identity
  -> Organization membership
      -> Organization-scoped role assignments
          -> Optional facility scopes

Organization (subscriber)
  -> Facility (licensed site)
      -> Program types
          -> Rooms and capacity rules
```

Requirements:

- Users are global identities and may belong to multiple organizations.
- Organization and facility context is explicit in the session and every job.
- Every tenant-owned row has a non-null `organization_id`.
- Facility-owned rows also have a non-null `facility_id` where applicable.
- Composite keys prevent cross-tenant references at the database layer.
- PostgreSQL Row-Level Security is a second isolation boundary behind FastAPI
  authorization.
- Exports, search, background jobs, object storage, AI requests, notifications,
  analytics, and support tooling carry the same tenant boundary.
- Platform support access is separate, time-limited, reason-bound, and audited.

Initial organization roles are Owner, Director/Administrator, Finance, Scheduler,
Educator, and Read-only Auditor. Permission checks, not role-name comparisons,
authorize actions.

## Proposed technical shape

CareSync remains a modular monolith until scale proves a service boundary is needed.

```text
React/TypeScript web
  public marketing shell + onboarding shell + authenticated application shell
                           |
                      versioned REST
                           |
FastAPI modular monolith
  identity | tenancy | onboarding | billing | childcare | attendance
  scheduling | claims | invoicing | documents | audit | notifications
                           |
PostgreSQL + RLS | Canadian object storage | job queue | transactional outbox
```

The public site requires server-rendered, indexable pages. The authenticated product
can remain a highly interactive React application. Styled-components may remain as
the design-system implementation; domain modules and contracts provide the actual
architectural boundaries.

Authentication must provide verified email, invitation acceptance, password reset,
session listing and revocation, rotated refresh sessions, MFA for privileged roles,
rate limiting, and security-event audit. A managed identity provider is preferred if
its Canadian-region, export, incident, and contractual properties satisfy the final
security review.

Stripe (or an approved equivalent) handles CareSync's business subscription. Signed,
deduplicated webhooks—not the checkout return page—control subscription state.
Processing parent tuition is a separate later product requiring its own commercial,
financial, and technical design.

## Privacy and records baseline

The implementation must support:

- Canadian-region data and backup hosting by default.
- Purpose-specific collection notices and consent history.
- Separate optional consent for photos, marketing, and non-essential processing.
- Encryption in transit and at rest.
- Least-privilege access and administrator MFA.
- Immutable access, export, edit, and support-access audit trails.
- Access and correction workflows.
- Record-class retention, legal hold, anonymization, and secure destruction.
- Data export before cancellation deletion.
- Subprocessor inventory and hosting-country disclosure.
- Incident assessment and breach-notification workflow.
- Human approval before official submissions or external disclosures.

Claims and regulatory rules are effective-dated reference data. A software release
must not silently rewrite the historical rule basis of an existing claim or audit.

## Clean-database transition

The approved clean start must not destroy the only useful migration and regression
source.

1. Stop writes to the isolated rebuild only.
2. Create and verify an immutable custom-format dump and table-count manifest.
3. Archive the current cloned database under a clearly legacy name.
4. Create a new empty runtime database from migration revision zero.
5. Keep the required runtime database name `caresync` if desired.
6. Seed only platform permissions, default roles, plan catalogue, Alberta reference
   data, and the minimum platform administration identity.
7. Put demonstration records in a dedicated demo tenant, never in a customer tenant.
8. Register the first real organization through the same onboarding flow customers use.
9. Later import legacy private records through a validated migration adapter.

The original CareSync project, original PostgreSQL instance, and original records
remain untouched.

## Delivery phases and acceptance gates

### Phase 0 — product contract

- Approve the open decisions in this document.
- Approve positioning, pricing experiment, launch customer, and payment boundary.
- Approve data-residency and authentication constraints.

Gate: no unresolved decision can change the primary entity hierarchy or payment flow.

### Phase 1 — SaaS security foundation

- Revision-zero schema, organizations, facilities, memberships, permissions, RLS,
  sessions, invitations, audit, and guarded development reset.
- Automated cross-tenant isolation suite.

Gate: tenant A cannot read, mutate, search, export, reference, or infer tenant B data
through HTTP, jobs, files, logs, or AI workflows.

### Phase 2 — public site and onboarding

- Marketing, pricing, security, registration, email verification, facility lookup,
  verification workflow, resumable setup, and activation.
- Subscription checkout, webhooks, entitlements, trial, grace, and cancellation.

Gate: a new owner can register an organization, add and verify a facility, start a
trial, and reach an empty correctly isolated workspace without administrator database
work.

### Phase 3 — operational vertical slices

- Families and children.
- Enrolments, rooms, capacity, calendars, closures, and attendance.
- V3 scheduling with explainability and certification.
- Claims/imports/name matching and extension integration.
- Invoicing, payments ledger, reports, documents, and audit.

Gate: each slice supports create, read, update, archive, audit, permission checks,
import/export where relevant, empty/loading/error states, and end-to-end browser tests.

### Phase 4 — commercial readiness

- Backup/restore drills, data export/deletion, incident workflow, service health,
  support access, observability, documentation, accessibility, and performance.
- Deliberate Alberta beta and legacy migration rehearsal.

Gate: recovery, privacy, cancellation, and tenant-isolation evidence is retained and
reviewable before real customer data is accepted.

## Explicit non-goals for the first commercial foundation

- No claim of government affiliation, certification, or guaranteed funding outcome.
- No collection of Alberta portal passwords.
- No automatic external submission without human approval.
- No parent-funds marketplace or payroll product.
- No global microservice decomposition.
- No production customer data before facility control and security readiness.
- No deletion of the original private project or database.

## Approval checklist

Implementation may begin only after the product owner accepts or changes:

- [ ] Alberta-first, Canada-ready positioning
- [ ] Facility-based daycare and OSC launch scope
- [ ] Multi-location organization model
- [ ] Proposed pricing and trial
- [ ] Manual control verification assisted by public lookup
- [ ] Canadian-region data requirement
- [ ] Managed-auth preference and administrator MFA
- [ ] CareSync subscriptions first; parent payment processing later
- [ ] Empty active database with an immutable legacy source retained
- [ ] Staff membership foundation now; full staff product later

## Research references

- Alberta facility licensing: <https://www.alberta.ca/licensed-facility-based-programs>
- Alberta childcare lookup: <https://www.alberta.ca/find-childcare>
- Alberta monthly claims: <https://www.alberta.ca/submit-a-monthly-claim>
- Alberta PIPA responsibilities: <https://www.alberta.ca/organization-responsibilities-for-protecting-personal-information>
- KinderLogix pricing: <https://kinderlogix.com/pricing/>
- Storypark Canada pricing: <https://ca.storypark.com/pricing>
- Daily Connect pricing: <https://en.dailyconnect.com/pricing>
- Stripe Canada pricing: <https://stripe.com/en-ca/pricing>
- Stripe Billing pricing: <https://stripe.com/en-ca/billing/pricing>

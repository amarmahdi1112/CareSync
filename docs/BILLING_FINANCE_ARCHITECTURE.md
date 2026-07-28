# CareSync Billing, Funding and Finance Architecture

Last updated: 2026-07-23

## Status

This document is the architecture contract for CareSync's childcare billing,
payments, funding-claim and finance direction. Revision
`0033_billing_ledger` implements the bounded synthetic checkpoint and
`0036_billing_manual_mode` adds a separate, explicitly owner-activated
private/local record of off-platform charge and payment facts. It extends
`ULTIMATE_PRODUCT_CONSTITUTION.md`; it does not authorize a production
migration, processor, money movement, government submission, tax treatment or
release of the existing legacy invoicing routes.

The capability is gated by server mode, tenant allowlist and, for manual mode,
an immutable owner activation. Pre-0033 invoice-like data and screens remain
legacy reference material; no current database row is silently converted into
a charge, payment, government receivable or tax receipt.

The retained Basic database and checked-in launcher now share
`0039_admissions_decision_spine`. The guarded 0036 through 0038 promotions
remain recorded historical checkpoints, and the exact 0039 promotion is
recorded in the runtime and cutover runbooks. None of those promotions activated the
private/manual protocol for an organization. Revision 0038 adds only the
privacy-safe durable public-job replay boundary; 0037 changes agreement
identity only, and `0036_billing_manual_mode` remains the protocol boundary.
Revision 0039 adds the private administrator admissions spine without changing
billing authority. The retained database contains 141 public tables plus one
view with both owner-controlled activation tables still empty. Product slice
`0040_billing_readiness_batch_planner` is now verified in source and through
retained live read-only API acceptance. It adds a deterministic, privacy-bounded
setup planner and no-write preview plus explicitly reviewed reuse of canonical
account, payer, rate and agreement commands. It has no schema migration,
activation, invoice, payment, provider or funding behavior. The retained
Alembic head and release pin remain exactly
`0039_admissions_decision_spine`. Signed-in administrator browser-click
acceptance remains pending; the normative 0040 contract is
`docs/BILLING_READINESS_BATCH_PLANNER_ARCHITECTURE.md`.

This is product engineering, not legal, accounting or program-administration advice. Before a
tenant uses real money or submits a claim, an accountable operator must confirm its current signed
funding agreement and Schedule A, and a qualified Canadian accountant must approve tax, receipt,
chart-of-account and period-close configuration.

### `0033_billing_ledger` foundation

`0033_billing_ledger` is the verified synthetic foundation. It implements a
tenant-scoped append-only CAD receivables foundation: billing accounts and versioned payer
assignment, effective-dated rate-plan and agreement versions, synthetic invoice facts and lines,
manually recorded synthetic payments with explicit external references, immutable allocations and
credits, balanced journal entries, command preparation and terminal receipts, exact retry, and
finalized-absence recovery. The eight exposed commands are account open, payer assignment, rate
version publish, agreement establish, invoice issue, payment record, payment allocation and credit
issue.

Command writes are PostgreSQL-only and require `environment=test`, writable `sandbox` mode, the
exact disposable-target attestation, an explicitly allowlisted organization, immutable synthetic
source attestations and a loopback high port other than 5432, 5433 or 5434. SQLite may exercise
portable schema/service checks and disabled or shadow reads, but it never authorizes 0033 command
writes. Every projected invoice is visibly labelled
`TEST/SYNTHETIC — NOT A REAL INVOICE`.

The source administrator workspace at `/billing` provides permission- and capability-gated
overview, action queue, family accounts, invoice detail and exact-recovery state. Its eight
canonical collections are `accounts`, full historical `payer_versions`, `rate_plans`, `agreements`,
`invoices`, `payments`, `allocations` and `credits`. It assembles every page under one snapshot
token and rejects identity, count, sequence, duplicate, reference or arithmetic drift instead of
rendering a partial financial picture. Each invoice pins the exact account payer-version and
guardian provenance used when it was recorded, so a later payer reassignment changes only future
work and does not invalidate or relabel prior invoices. Basic `/invoicing/*` remains NotFound.

This checkpoint does **not** issue or deliver a real invoice, generate a PDF or statement, contact
a processor, move or settle money, perform a refund or chargeback, determine tax treatment, issue
a tax receipt, determine funding eligibility, prepare or submit a funding claim, close an
accounting period, export accounting data or expose parent self-service. Configured synthetic
funding splits and tax-basis-point arithmetic are fixture calculations, not program eligibility,
tax advice or an accountant-approved treatment.

### `0036_billing_manual_mode` boundary

0036 leaves every 0033 sandbox rule intact and adds one independent,
organization-scoped activation. Only an active owner, with the exact server
attestation and tenant allowlist already present, can affirm the private manual
boundary. The activation is immutable, idempotent for the exact operation and
cannot be inserted by startup or migration. A non-empty synthetic or prior
billing ledger blocks activation rather than relabelling its provenance.

After activation, account, payer, rate, agreement, invoice, payment,
allocation, credit and journal facts use the same append-only invariant checks
but carry private/manual provenance. Source family, child, enrollment and
facility records remain ordinary retained facts; no synthetic attestation is
fabricated for them. The UI distinguishes manual records from the visibly
watermarked sandbox and provides a local print/save rendering of the canonical
invoice record. That rendering is not delivery, a tax receipt, payment
evidence or legal/accounting approval.

## How to read requirements

The following labels deliberately separate external requirements from CareSync design choices:

- **`[OFFICIAL—LAW]`** — a requirement stated in legislation or regulator guidance.
- **`[OFFICIAL—PROGRAM]`** — a requirement stated in current Alberta program material. The
  tenant's signed, effective agreement and Schedule A remain controlling for that tenant.
- **`[OFFICIAL—CRA]`** — Canada Revenue Agency guidance; it is not a CareSync product decision.
- **`[PRODUCT]`** — a CareSync safety, usability or architecture decision.
- **`[OPEN—REVIEW]`** — a question that must be resolved by the named human authority before the
  affected capability can be enabled.

`MUST`, `MUST NOT`, `SHOULD` and `MAY` are normative only for the CareSync product contract unless
the sentence is explicitly labelled as an external requirement.

## Product truth hierarchy

When facts conflict, CareSync must preserve the conflict and apply this order:

1. applicable law and regulation;
2. the tenant's signed agreement, Schedule A and effective amendments;
3. current official program or CRA guidance;
4. accountant-reviewed tenant configuration;
5. facility contracts, fee schedules and policies;
6. CareSync recommendations and forecasts.

CareSync calculates, reconciles, explains, prepares and records. It does not become the licensing,
funding, taxation or accounting authority. A rule-pack result is a recommendation tied to an exact
source version, not a declaration of legal entitlement.

## Bounded scope

### Target architecture scope

The following is the long-term target, not the implemented 0033 boundary. Only the source subset
explicitly documented above is implemented.

- effective-dated childcare fee schedules by facility, program, attendance category and contract;
- family/child/payer billing terms, confidential payer responsibility and optional-service consent;
- explainable invoice drafts, finalized invoices, credits, refunds, write-offs and statements;
- payment intent, provider-token references, settlement, allocation, reversal and reconciliation;
- an immutable tenant double-entry subledger and accountant-reviewed general-ledger mappings;
- Alberta affordability and subsidy claim preparation, evidence, approval, export and reconciliation;
- optional-service and penalty registers required to explain charges and program treatment;
- annual childcare tax-receipt preparation, issue, reissue, supersession and audit history;
- aged receivables, program/facility finance views and funding financial-report workspaces;
- parent self-service for their authorized payer scope; and
- durable notifications, action queues, exports, audit evidence and recovery receipts.

### Explicitly outside the target architecture

- a full general ledger, payroll engine, corporate tax return or replacement for professional
  accounting software;
- holding client trust funds, extending credit, lending, collections-agency activity or determining
  ability to pay;
- autonomous government-portal submission, stored government credentials, screen scraping or
  unattended declarations;
- legal conclusions about funding eligibility, custody, tax deductibility or document validity;
- changing attendance, enrollment, fee contracts or care records to make a claim balance;
- raw card, bank-login, government-login or individual-provider SIN storage in ordinary settings,
  logs, analytics or support tools;
- opaque fee optimization, discriminatory pricing or automatic adverse action based on family
  finances;
- exposing legacy invoice routes merely because a feature flag is enabled; and
- CareSync's own SaaS subscription billing. Platform commerce is a separate ledger, tenant and
  permission boundary described under `SAAS-004`; childcare money must never share balances,
  sequence numbers, processor customers or reports with CareSync subscription revenue.

## External baseline checked on 2026-07-22

These summaries are design inputs, not substitutes for the linked source or a tenant's agreement.

### Alberta affordability and subsidy

- **`[OFFICIAL—PROGRAM]`** Alberta's affordability material states that eligible facility-based
  daycare and family day home parent fees are no more than **$326.25 per month for 100 or more
  registered hours** and **$230 per month for 50 to 99 registered hours**. Programs determine fees
  below 50 registered hours. Preschool funding can reduce the parent fee by up to $100 and the
  stated preschool fee includes supplementary fees. The Alberta contribution is based on the
  program-specific Schedule A fee less the applicable parent fee. See the
  [Alberta affordability grant page](https://www.alberta.ca/affordability-grant) and the
  [June 2026 Affordability Grant Funding Guide](https://open.alberta.ca/dataset/061d9f31-4edd-4a2a-9f0d-09bb23594934/resource/e8292a12-e82a-4720-a473-82ad61211da8/download/ecc-alberta-child-care-affordability-grant-funding-guide-2026-06-v5-1.pdf).
- **`[OFFICIAL—PROGRAM]`** Grade 1 to Grade 6 out-of-school care is not part of the universal
  affordability fee structure; eligible families may instead receive subsidy. Kindergarten and
  mixed-program cases must use the current program rules rather than a generic OSC assumption.
  See [Alberta child care subsidy](https://www.alberta.ca/child-care-subsidy-program).
- **`[OFFICIAL—PROGRAM]`** The current guide distinguishes partial first/last-month registration,
  requires actual attendance reporting, and normally does not fund a full month with no attendance
  unless an approved exception applies.
- **`[PRODUCT]`** CareSync stores the registered-hours classification, actual attendance, contracted
  fee, Schedule A source and calculated family/government portions separately. It never infers one
  from another or edits care evidence to reach a target.

### Optional services, penalties and disclosure

- **`[OFFICIAL—PROGRAM]`** An optional service must be separately and voluntarily selected. The
  current guide prohibits automatic enrollment/opt-out, bundling optional services into the core
  fee and preferential program access based on selection.
- **`[OFFICIAL—PROGRAM]`** The current guide requires disclosure after an agreement begins and
  recurring reporting of optional services, identifies October and April reporting periods, and
  normally requires advance notice before changes. Operators must read the exact current guide and
  agreement for timing and exceptions.
- **`[OFFICIAL—PROGRAM]`** Targeted late-payment, NSF and late-pickup penalties are treated
  separately from supplementary/optional services in the current guide. Excess parent fees and
  unselected or ineligible optional-service amounts may require reimbursement.
- **`[PRODUCT]`** A charge cannot be finalized as an optional service without a current affirmative
  consent version covering the child, payer, service, price and effective period. A penalty needs
  its own published policy version and triggering evidence. Neither is represented by a free-text
  invoice line alone.

### Monthly claims and funding evidence

- **`[OFFICIAL—PROGRAM]`** Alberta monthly claims use registration information and actual monthly
  attendance; separately approved extended hours are entered separately. Claims are submitted
  after the service month and can require later adjustment. See
  [Submit a monthly claim](https://www.alberta.ca/submit-a-monthly-claim) and the
  [June 17, 2026 Child Care Licensing Portal Claims Submission User Guide](https://ccds.blob.core.windows.net/claims/Child%20Care%20Licensing%20Portal%20Claims%20Submission%20User%20Guide.pdf).
- **`[OFFICIAL—PROGRAM]`** The affordability guide describes audit records including registration,
  daily attendance, parent amounts charged and collected (including supplementary fees), and
  educator time/payroll evidence. It states that affordability claim records are retained for six
  years after agreement termination.
- **`[PRODUCT]`** CareSync prepares a bounded claim artifact, validates it, records maker/checker
  approval and produces an export. The accountable user performs the external declaration and
  records the portal submission receipt. CareSync does not claim that an export was submitted.

### Funding financial reports

- **`[OFFICIAL—PROGRAM]`** The April 2026 guide states that a financial report is due within 90 days
  after the agreement or selected fiscal reporting period. It describes a signed statement/report
  at $250,000 or less, a CPA review engagement above $250,000 through $500,000, and a CPA audit
  above $500,000, with program-level supplementary schedules for multi-program operations and
  return of unused funding. See the
  [2026–27 Affordability Grant Financial Reporting Guide](https://open.alberta.ca/dataset/69f8367a-667f-48af-9ac8-53c23bec562c/resource/62989fdb-9c1d-4263-96db-2d2885756a03/download/ecc-financial-reporting-guide-2026-27-affordability-grant-agreement.pdf).
- **`[PRODUCT]`** The report workspace calculates threshold and due-date prompts from a pinned rule
  version, but labels them `review required` until an authorized finance user confirms the signed
  agreement period and current official rule.

### Childcare receipts and tax

- **`[OFFICIAL—CRA]`** CRA asks child-care providers to give a receipt identifying the services and
  says the receipt should be made to the person who paid. CRA's detailed provider guidance lists
  payer, child, amount received, service period, provider identity/address, signature and signed
  date, and recommends a separate receipt for each child. See
  [How to claim child care expenses](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/deductions-credits-expenses/line-21400-child-care-expenses/how-claim.html),
  [Issuing receipts](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/daycare-your-home/issuing-receipts.html), and
  [Income Tax Folio S1-F3-C1](https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-1-individuals/folio-3-family-unit-issues/income-tax-folio-s1-f3-c1-child-care-expense-deduction.html).
- **`[OFFICIAL—CRA]`** CRA's individual-provider guidance calls for the provider's SIN. The reviewed
  public pages do **not** establish a universal rule that every incorporated daycare receipt must
  display a business number.
- **`[OPEN—REVIEW]`** A Canadian accountant must approve the entity identifier, signature method,
  template wording and treatment of split payers before tax-receipt issue is enabled. Individual
  provider SIN handling, if ever applicable, requires a separate restricted secret/evidence design;
  it must not be put in tenant settings or reusable PDF templates.
- **`[OFFICIAL—CRA]`** Child care involving care and supervision of children 14 or younger, normally
  for periods under 24 hours, is generally GST/HST exempt. Treatment is supply-specific: integrated
  transportation/activities can follow the exempt childcare supply, while distinct transportation
  or administration may be taxable. See
  [GST/HST Memorandum 21-1, Child Care Services](https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/21-1/child-care-services.html).
- **`[PRODUCT]`** Every charge code pins an accountant-reviewed tax-treatment version and rationale.
  CareSync's SaaS subscription is not classified as childcare; treating it as an ordinary taxable
  commercial supply is an architecture assumption pending separate platform-tax review.

### Records and privacy

- **`[OFFICIAL—LAW]`** Alberta's Child Care Licensing Regulation requires facility child and staff
  attendance records to be retained for at least two years and permits electronic records. See the
  [Alberta Child Care Licensing Regulation](https://kings-printer.alberta.ca/1266.cfm?display=html&isbncln=9780779856428&leg_type=Regs&page=2008_143.cfm).
- **`[OFFICIAL—CRA]`** CRA generally requires business records for six years after the end of the
  related tax year, requires usable electronic records and audit trails, and normally expects
  records to be kept in Canada unless written permission is obtained. See
  [where and how long to keep records](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html),
  [audit trails for business transactions](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/review-business-systems-keeping-audit-trails-business-transactions.html), and
  [acceptable electronic records](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/acceptable-format-imaging-paper-documents-backing-electronic-files.html).
- **`[OFFICIAL—LAW]`** Alberta PIPA guidance describes reasonable-purpose collection, notice and
  consent, minimization, accuracy, access/correction, safeguards, and destruction or anonymization
  when information is no longer reasonably required. It also requires transparency about service
  providers outside Canada and breach reporting to the OIPC where there is a real risk of
  significant harm. See
  [collecting personal information](https://www.alberta.ca/collecting-personal-information),
  [organization responsibilities](https://www.alberta.ca/organization-responsibilities-for-protecting-personal-information), and
  [OIPC breach notification](https://oipc.ab.ca/breach-notification/).

## Financial-domain separation

The architecture has four related but non-interchangeable domains:

1. **Operational truth** — enrollment, attendance, optional-service consent and care events. These
   systems own their facts; finance can only reference versioned snapshots.
2. **Family accounts receivable** — contracted charges, invoices, payments, credits and receipts.
3. **Government funding** — claim calculation, submission evidence, remittance and adjustment.
4. **Accounting evidence** — immutable journal entries, period controls, reconciliation and export.

No domain writes directly into another domain's tables. A server-authorized command validates a
source snapshot, writes its own aggregate and journal transaction, and records an outbox event.
Realtime events invalidate read models; they never authorize or post money.

## Immutable accounting model

### Money and time

- All posted money is integer minor units with an ISO 4217 currency. No IEEE floating-point value
  may enter a command hash, journal, invoice total, tax calculation or export.
- The bounded release supports CAD only. Multi-currency is a future architecture decision, not a
  hidden string column.
- Rounding occurs once at the documented line or document boundary chosen by the reviewed tax
  configuration. The unrounded input, rule and rounded result remain explainable.
- Instants are UTC and aware. Accounting date, service date and claim month are separate fields
  derived under the facility's IANA timezone, normally `America/Edmonton`.
- Backdating is permissioned and never changes server commit time or history.

### Tenant subledger

Each organization has an isolated append-only double-entry subledger. A journal entry contains:

- organization, facility and optional program dimensions;
- unique entry ID, monotonically assigned tenant book sequence and status;
- effective instant, accounting date, service period and CAD currency;
- canonical source command/aggregate/version and client operation ID;
- source rule/tax/fee-schedule versions and non-PII request digest;
- optional `reversal_of_entry_id` and correction chain;
- balanced debit and credit lines; and
- actor, approval, commit, audit and export provenance.

Every line has one account and may carry family, child, payer, invoice, payment, funding program,
claim period and facility/program dimensions where appropriate. Dimensions are references for
explanation and reporting; they do not weaken tenant isolation.

The minimum tenant chart uses reviewed mappings for:

- accounts receivable;
- cash/processor clearing;
- unapplied customer cash;
- parent childcare fee revenue;
- optional-service revenue;
- penalty/late/NSF revenue;
- government affordability receivable and revenue/contra-revenue mapping;
- subsidy receivable and revenue/contra-revenue mapping;
- refunds payable;
- credit/write-off/bad-debt adjustments; and
- GST/HST payable only for charge codes explicitly classified as taxable.

The product does not prescribe the final debit/credit classification of government funding or
revenue recognition. **`[OPEN—REVIEW]`** The tenant's accountant approves the chart mapping before
posting is enabled.

### Posting rules

1. A draft has no accounting effect.
2. Finalization posts exactly one balanced journal entry in the same database transaction as the
   authoritative aggregate version and command receipt.
3. A finalized entry, invoice, allocation or receipt is never edited or deleted.
4. Corrections use linked reversal and replacement entries or a credit/debit memo. A UI `edit`
   action must disclose this result before confirmation.
5. Invoice, statement, aging and family balance are projections of posted lines and allocations;
   no writable `balance` field is authoritative.
6. A payment is not cash merely because a client started checkout. Provider authorization,
   capture, settlement, reversal and refund remain distinct facts.
7. Government expected funding, submitted claim and cash remittance remain distinct facts.
8. A period close cannot erase or rewrite a late fact. It posts an allowed later-period correction
   or follows the controlled reopen workflow.
9. All journal sequences, PDF/document numbers and exports are tenant scoped and non-reusable.
10. No command may post across organizations or between childcare and CareSync platform books.

## Canonical aggregates and records

Names below are domain contracts; a migration may refine physical names without changing meaning.

- `fee_schedule` — versioned draft/published/retired charge definitions and effective windows.
- `billing_agreement` — family/child/program/payer responsibility, service dates and pinned schedule.
- `optional_service_consent` — affirmative choice, price/version, signer authority and withdrawal.
- `invoice` — immutable finalized document with versioned lines and provenance.
- `credit_memo` / `write_off` / `refund` — separately authorized compensating aggregates.
- `payment` — provider-independent payment lifecycle and token reference, never raw card data.
- `payment_allocation` — immutable allocation or compensating unallocation across open items.
- `funding_rule_pack` — effective-dated official-source facts and formulas, reviewed before activation.
- `claim` — one facility/program/period preparation, approval, export/submission evidence and version.
- `funding_remittance` — imported government statement/payment and claim allocation.
- `tax_receipt` — issued payer/child/year evidence derived from eligible net settled allocations.
- `accounting_period` — open/soft-closed/hard-closed/reopened lifecycle and approval evidence.
- `journal_entry` / `journal_line` — immutable accounting authority.
- `financial_command_receipt` — exact retry and interruption recovery authority.
- `financial_inbox_event` / `financial_outbox_event` — durable external input and internal delivery.
- `reconciliation_case` — durable mismatch, owner, evidence, decision and resolution chain.

All records are tenant bound at schema, foreign-key, query, RLS, command and response-parser layers.
Facility/program scope is enforced where money or reporting is facility/program specific.

## Command boundary

Every mutation is an explicit server-authorized command. Generic CRUD routes and arbitrary PATCH
of financial records are forbidden.

### Configuration and contracts

- `CreateFeeScheduleDraft`
- `PublishFeeScheduleVersion`
- `RetireFeeScheduleVersion`
- `CreateOrReplaceBillingAgreement`
- `RecordOptionalServiceConsent`
- `WithdrawOptionalServiceConsent`
- `PublishChargePolicyVersion`
- `ApproveTaxTreatmentVersion`
- `ActivateFundingRulePack`

### Invoicing and receivables

- `GenerateInvoiceDraft`
- `RecalculateInvoiceDraft`
- `FinalizeInvoice`
- `DiscardInvoiceDraft`
- `IssueCreditMemo`
- `RecordWriteOff`
- `ReverseWriteOff`
- `RecordManualPayment`
- `CreateProviderPaymentIntent`
- `AllocatePayment`
- `ReversePaymentAllocation`
- `RecordRefund`
- `RecordChargebackOrReversal`

Finalized invoices use credit/rebill; only drafts can be discarded. `Void finalized invoice` is
not a command because it disguises accounting history.

### Funding and reports

- `PrepareClaimSnapshot`
- `ValidateClaim`
- `ApproveClaim`
- `ExportClaim`
- `RecordExternalSubmissionReceipt`
- `ImportFundingStatement`
- `ReconcileFundingRemittance`
- `CreateClaimAdjustment`
- `ApproveClaimAdjustment`
- `PrepareFundingFinancialReport`
- `RecordExternalReportReceipt`

Recording an external receipt requires exact external reference/time entered or imported by an
authorized human. It does not submit anything.

### Receipts and periods

- `PrepareTaxReceiptDrafts`
- `IssueTaxReceipt`
- `SupersedeTaxReceipt`
- `OpenAccountingPeriod`
- `SoftCloseAccountingPeriod`
- `HardCloseAccountingPeriod`
- `ReopenAccountingPeriod`
- `PlaceFinancialLegalHold`
- `ReleaseFinancialLegalHold`
- `ExportFinancialAuditBundle`

Each command carries `client_operation_id`, canonical intent, expected aggregate version, tenant,
actor and target. Commands that affect several aggregates acquire locks in deterministic order and
commit atomically. A stale version returns structured `409 stale_financial_resource` and writes
nothing.

## Read models

Read models are rebuildable and never authorize a post:

- finance overview and action queue;
- family account and confidential payer subaccount;
- child service/charge history;
- invoice list/detail and immutable document timeline;
- payment, settlement and allocation views;
- credits, refunds, write-offs and exception review;
- receivables aging and unapplied-cash queue;
- claim workbench, evidence lineage and claim comparison;
- funding expected/submitted/remitted/adjusted reconciliation;
- optional-service consent and biannual disclosure report;
- tax-receipt register and payer delivery state;
- program/facility financial reporting and threshold workbench;
- journal/account export and close checklist; and
- audit, command receipt, notification and reconciliation-case views.

A read projection displays `generated_at`, data-through cursor, organization/facility scope,
currency, rule versions and whether it is stale. Realtime invalidation triggers a canonical REST
refresh. A stale projection may be viewed but not used as the expected version for a financial
command.

## Lifecycle contracts

### Fee schedule

```text
draft --publish--> published --retire--> retired
```

Published versions are immutable and may be future effective. Overlapping active versions for the
same charge scope are rejected. Retirement does not change contracts or invoices already pinned to
that version.

### Invoice

```text
draft --finalize--> open --allocation--> partially_paid --allocation--> paid
  |                    |                         |                       |
  +--discard-----------+--------credit/rebill----+-----------------------+

paid --excess allocation--> overpaid
open / partially_paid / paid / overpaid --credit memo--> credited state derived from balances
```

`paid`, `overpaid` and `credited` are derived settlement states, not mutable lifecycle labels.

### Payment

```text
created -> pending -> authorized -> captured -> settled
              |           |           |          |
              +-> failed  +-> expired +-> reversed/refunded/chargeback
```

Provider states are mapped, never copied blindly. An unknown or contradictory provider event opens
a reconciliation case and does not guess the financial result.

### Claim

```text
draft -> validated -> approved -> exported -> externally_submitted
  ^          |            |                         |
  +--revise--+------------+                         v
                            in_review -> processed -> reconciled
                                             |
                                             v
                                   adjustment_required -> adjusted
```

Every revision preserves prior versions. `exported` is not `externally_submitted`. Only a recorded
external receipt may advance that boundary.

### Tax receipt

```text
draft -> issued -> superseded
```

An issued receipt is never regenerated in place. A correction issues a new numbered version linked
to the superseded document and preserves both artifacts.

### Accounting period

```text
open -> soft_closed -> hard_closed
          |                |
          +-> reopened <---+
```

Reopen requires a reason, step-up authentication and independent approval. The original close and
all intervening entries remain visible.

## Authorization and separation of duties

Permissions are evaluated by the server using active membership, tenant, facility/program scope,
command and current aggregate state. A client route, feature flag or hidden button is not authority.

Minimum permission vocabulary:

- `billing.configure`, `billing.contracts.manage`, `billing.invoices.draft`,
  `billing.invoices.finalize`, `billing.credits.issue`, `billing.writeoffs.approve`;
- `payments.record`, `payments.allocate`, `payments.refund`, `payments.reconcile`;
- `funding.claims.prepare`, `funding.claims.approve`, `funding.claims.export`,
  `funding.submission_receipts.record`, `funding.reconcile`;
- `tax_receipts.prepare`, `tax_receipts.issue`;
- `finance.periods.close`, `finance.periods.reopen`, `finance.audit.export`;
- `finance.read.family`, `finance.read.program`, `finance.read.organization`; and
- `finance.legal_hold.manage`.

Role expectations:

- owner/finance administrator can configure scope but does not bypass maker/checker rules;
- billing clerk can draft invoices and record evidence but cannot publish rates, refund, write off,
  hard-close or approve their own funding claim;
- claims specialist can prepare but cannot self-approve/export a claim they materially changed;
- authorized finance approver can finalize, approve and close within explicit thresholds;
- parent/guardian sees only payer/child scopes derived from effective family authority and payer
  responsibility; another payer's instruments, contact details and confidential balance stay hidden;
- educator sees operational attendance/consent prompts necessary for care but no family balance,
  bank, funding or claim data;
- auditor is read-only and may receive a bounded, watermarked export;
- support access is time-bound, reason-bound, audited and cannot post, approve, export tax identity
  fields or reveal payment instruments.

Independent approval is mandatory for fee-schedule publication, tax-rule activation, configured
high-value credit/refund/write-off thresholds, claim approval/export, hard-close/reopen and legal
hold release. High-risk commands require recent step-up authentication. Thresholds are tenant
policy, not client input.

## Exact retry and recovery contract

Financial interruption must be boring, deterministic and explainable.

### Idempotent command protocol

1. Before any financial mutation, the client sends the exact in-memory command to a read-safe
   preparation endpoint. The server validates it with the same typed model used by the command,
   canonicalizes dates, instants, defaults and identifiers once, and appends an actor/tenant-bound
   preparation fact containing only `client_operation_id`, command type, target and digest. It does
   not retain the payload or a second copy of free text.
2. Only after receiving that authoritative digest does the client durably store the tenant, actor,
   `client_operation_id`, command type, target and digest. Persistent browser recovery records must
   not contain memos, notes, names or the full command. The server locks the tenant/operation lane
   and requires the exact preparation fact before accepting a financial mutation.
3. Same operation plus same intent returns the committed receipt and current canonical projection
   with `replayed=true`; it creates no second journal, audit or outbox event.
4. Reusing an operation ID with changed money, payer, target, period, source version or intent
   returns `409 operation_reused` and writes nothing.
5. One database transaction writes the command receipt, aggregate version, balanced journal,
   audit event and durable outbox event. Partial financial commits are impossible.
6. A transport timeout, disconnect, throttling, 5xx or malformed response is **ambiguous**. The
   client freezes the prepared operation and does not generate a new ID. It may retry the exact
   command while its input remains in volatile memory; after a reload it must reconcile instead of
   reconstructing missing free text or intent.
7. An authenticated, digest-bound receipt-status endpoint resolves committed,
   prepared-not-committed or finalized-absent under the same operation lock. Finalizing absence
   consumes the actor-bound preparation proof and appends a terminal claim; it never trusts a bare
   UUID or requires a persistent browser copy of the original payload. Only that canonical
   terminal-absence response permits reviewed intent to be re-entered under a new ID.

### External side effects

- No processor, email, document-delivery or government call runs inside the database transaction.
- The outbox worker is at-least-once. Each consumer deduplicates on tenant/event ID and records a
  durable delivery receipt.
- Payment-provider webhooks first enter an append-only inbox. Signature, provider account, tenant
  binding, event ID, event time and envelope digest are verified before processing. A unique
  provider event ID is handled once; changed content for a reused ID is quarantined.
- A provider success followed by a CareSync crash is recovered by webhook and provider
  reconciliation. An uncertain provider response remains `pending_external`; CareSync polls or
  reconciles and never assumes success or failure.
- Provider events may arrive late or out of order. The mapper accepts only valid state transitions;
  contradictions create a reconciliation case.
- Statement/CSV imports are content-hashed and import-ID scoped. Re-upload returns the original
  import result; changed content cannot reuse the ID.
- Email/PDF delivery failure does not reverse an issued invoice or receipt. Delivery is retried and
  shown as a separate state.

### Failure matrix

| Failure | Canonical behavior |
|---|---|
| Browser loses response after finalize | Freeze the redacted preparation reference; digest-bound receipt lookup or an exact same-session retry returns the one committed invoice. |
| Two users finalize the same draft | Aggregate/advisory lock and expected version allow one commit; the other receives structured 409. |
| Provider captures but API times out | Keep payment pending; webhook/provider reconciliation records capture once. |
| Duplicate or out-of-order webhook | Inbox dedupe plus transition validator; no duplicate cash or allocation post. |
| Worker crashes after sending | Delivery receipt/dedupe prevents duplicate business effect; harmless delivery may repeat only where provider contract permits. |
| Projection is corrupt or deleted | Rebuild from immutable aggregates, journal and inbox/outbox cursor; compare book sequence and hashes. |
| Import repeated | Same hash returns prior result; mismatch under same import ID is rejected. |
| Refund succeeds externally before local response | Provider event/reconciliation posts one refund; operator cannot retry as a new refund while unresolved. |
| Device is offline | Financial writes remain disabled; cached views show stale/offline status. No offline money queue. |
| Backup restore | Restore database and document artifacts to the same checkpoint, then replay inbox/outbox and reconcile processor/government statements before reopening writes. |

Rebuild never fabricates missing journal lines from invoice totals. A ledger/hash mismatch freezes
affected posting, period close, receipt issue and claim export until reconciled. Recovery objectives,
backup cadence and provider-specific procedures must be recorded in the certification receipt.

## Invoice, payment and adjustment rules

- Each invoice line identifies child, service period, charge code, billing agreement, fee-schedule
  version, source facts, quantity, unit amount, discount, tax treatment and government/family split.
- A family discount or waiver is a versioned policy or explicit approved adjustment, never a direct
  total override.
- Multiple payers have explicit effective responsibility. A payer statement includes only that
  payer's obligation, payments and authorized shared facts.
- Payment allocation cannot exceed settled/captured amount net of prior refunds, reversals and
  allocations. Unallocated money stays in unapplied cash.
- A refund cannot exceed eligible settled money net of prior refunds and chargebacks. It never
  silently deletes the invoice obligation.
- A write-off changes collection/accounting treatment, not service history, government claim facts
  or the amount a payer actually paid.
- Chargeback and NSF events reopen the relevant balance through compensating entries and notify an
  authorized finance queue; they do not trigger automatic child-service suspension.
- Autopay, when introduced, needs payer mandate/consent version, amount-notice policy, cancellation,
  provider token and attempt history. It is not enabled in the first real-money pilot.

## Tax-receipt contract

The annual receipt register is payment based, not invoice based.

1. Eligible amount is derived from settled allocations to childcare service lines for the named
   child and actual payer during the receipt year, net of refunds, reversals and chargebacks.
2. Unpaid invoices, government funding, subsidy remittances, write-offs and non-childcare taxable
   supplies are not silently included.
3. A split payment creates amounts for the actual payers; CareSync does not choose which household
   member may claim a deduction.
4. The document identifies receipt number/version, actual payer, child, eligible amount received,
   service period, provider legal name/address, issue/signed date and accountant-approved entity/
   signature fields.
5. Separate per-child receipt generation is the product default because it aligns with CRA's
   detailed guidance. Any alternate consolidated format requires accountant approval and tests.
6. Receipt issue takes a frozen allocation snapshot and hash. Later refund/correction creates a
   superseding receipt; it never mutates or reuses the original number.
7. Delivery is through authenticated parent access or a separately approved secure channel. Email
   notifications contain no sensitive amount or child information.
8. Drafts display the exact included/excluded allocation lines before maker/checker issue.

The product must say `CareSync-prepared receipt` until the tenant's accountant has approved the
template and the facility has issued it. CareSync never labels a receipt as CRA-approved.

## Funding and claim contract

### Rule packs

Every funding rule pack records program, jurisdiction, effective interval, source URLs, source
document version/date, extracted facts, reviewer, review date, test fixtures and supersession.
Official material is never overwritten. A new guide creates a new version. The tenant separately
records the exact signed agreement/Schedule A facts it is authorized to use.

A stale or missing rule pack may allow draft exploration with a prominent warning; it must block
claim approval/export. Unknown program type, fee tier, partial-month treatment, zero-attendance
exception, extended-hour approval or optional-service treatment is an explicit exception, never a
zero/default value.

### Claim snapshot

One claim version freezes and hashes:

- organization, facility, licensed program and claim month;
- enrollment/registration and registered-hours category;
- daily actual attendance and source event versions;
- approved extended hours and evidence;
- fee agreement, Schedule A and parent fee versions;
- optional/supplementary charge and consent records;
- calculation rule pack and each result/provenance path;
- prior claim/submission/adjustment links; and
- maker/checker identities and declarations.

Changing source data after snapshot creates a visible delta and requires a new claim version or
adjustment. It never edits the approved/submitted snapshot.

### Submission and reconciliation

- `ApproveClaim` requires all blocking exceptions resolved or explicitly identified as
  non-applicable under a rule citation. Warnings cannot override a missing required fact.
- `ExportClaim` creates a hash, manifest, source versions and accountable approver. It does not
  attest external submission.
- `RecordExternalSubmissionReceipt` stores the portal reference, timestamp, submitted artifact
  hash and human actor; government credentials are not retained.
- Imported assessment/remittance statements reconcile expected, claimed, approved and paid amounts
  per child/program/period without overwriting any of them.
- A mismatch creates a durable case with owner, due date, evidence, next safe action and adjustment
  chain.
- Excess/recoverable funding, reimbursements and unused-funding returns use reviewed compensating
  entries and remain distinct from family credits.

## Retention, privacy and residency

Retention is purpose and record-class specific. The configured policy uses the longest applicable
legal, program, tax, contractual or hold period—never the shortest convenient period.

| Record class | External baseline | CareSync policy requirement |
|---|---|---|
| Facility child/staff attendance | Alberta minimum two years | Preserve under the childcare evidence policy and extend when linked to a longer claim, tax or legal hold. |
| Affordability claim records | Current guide: six years after agreement termination | Preserve exact claim snapshots, evidence manifests, submissions, adjustments and remittances for that period or longer applicable hold. |
| Tax/business records | CRA generally six years after related tax year | Preserve journal, invoices, payments, allocations, refunds and issued receipts in readable, auditable form. |
| Drafts and failed imports | No universal single period identified | Define short purpose-bounded retention; purge or anonymize after resolution unless evidence/hold requires preservation. |
| Processor payloads | Contract and dispute dependent | Retain only normalized minimum evidence plus bounded raw webhook envelope; never raw card data. |
| Audit/access records | Risk and accountability dependent | Effective-dated policy with restricted access and sufficient duration to investigate retained financial evidence. |

Additional controls:

- Canadian-region primary storage, backups and document artifacts are the default. A service
  provider outside Canada requires documented country, purpose, contract, risk review and required
  notice before enablement.
- Data is encrypted in transit and at rest; document URLs are time-limited; bank/card details are
  processor tokens with masked display only.
- Finance exports are reason-bound, watermarked, access logged, hash-manifested and expire.
- Search, logs, traces, analytics, push notifications and support tools exclude full bank/card
  details, individual-provider SIN, child health data and document contents.
- PIPA access/correction requests create an audited workflow. Correction never rewrites a posted
  entry; it updates mutable contact facts or creates compensating evidence as appropriate.
- Legal hold suspends destruction for exact subjects/classes and records authority, scope and
  release. Hold is not a reason to broaden user access.
- After all applicable periods/holds expire, direct identifiers and lookup indexes are securely
  destroyed or irreversibly anonymized while retaining only evidence that must legally remain.
  **`[OPEN—REVIEW]`** Counsel/privacy officer must approve how immutable financial evidence is
  minimized at end of life.
- Backup retention follows the same schedule and supports cryptographic destruction; a purge that
  remains indefinitely in backups is not complete.
- Breach detection feeds the privacy incident register and OIPC-assessment workflow without
  automatically making a legal breach determination.

## User experience and information architecture

Finance is a first-class administrator area, not scattered invoice buttons.

```text
Finance
├── Overview & action centre
├── Family accounts
├── Invoices
├── Payments & allocations
├── Credits, refunds & write-offs
├── Funding & claims
├── Reconciliation
├── Tax receipts
├── Reports & accounting export
├── Configuration
└── Audit & recovery
```

### Interaction rules

- Every warning names the affected facility/family/child/period, explains why it matters, identifies
  the responsible role and links directly to the safe resolver.
- No modal or drawer hides the only path to resolve a finance blocker. Major records have stable,
  deep-linkable full pages; contextual dialogs remain viewport-bounded and accessible.
- Family and child profiles show a scoped finance summary and link to the full account; they do not
  duplicate writable balance logic.
- Every amount exposes provenance: contract, schedule, attendance/service facts, rule, journal and
  adjustment chain.
- Actions use precise verbs: `Finalize invoice`, `Issue credit`, `Record external receipt`. Avoid
  ambiguous `Save`, `Fix` or `Mark paid`.
- Destructive-looking corrections preview the actual reversal/replacement entries and resulting
  balances.
- Global search respects finance permission and payer confidentiality. Notifications contain
  generic prose and validated internal destinations; REST reload establishes current truth.
- Parent portal provides authorized statements, invoice detail, payment state, receipts and autopay
  consent/history. It never reveals another payer's private responsibility or instrument.
- Loading, empty, stale, offline, failed, permission-denied and exact-retry states are distinct.
- Dark-ice visual language remains responsive, keyboard operable, WCAG-conscious and reduced-motion
  safe. Animation explains state/progress but never delays or obscures financial confirmation.

## Capability gate

The target architecture uses this tenant capability sequence:

```text
disabled -> shadow -> sandbox -> internal -> pilot -> general
```

- `disabled`: only the authenticated capability probe may report unavailability; no workspace or
  financial projection is exposed and legacy routes stay blocked.
- `shadow`: 0033 permits read-only projection of explicitly synthetic ledger facts and no commands.
  A future reviewed shadow-replay design may compare copied history without treating it as truth.
- `sandbox`: visibly watermarked synthetic families and facts. The 0033 checkpoint has no payment
  processor; a processor sandbox is a later Stage 4 capability.
- `internal`: authorized staff exercise real tenant configuration with no external money/submission.
- `pilot`: one approved facility, bounded real-money/manual-claim scope and daily reconciliation.
- `general`: only after pilot evidence and explicit certification approval.

The 0033 sandbox recognizes `disabled`, `shadow` and `sandbox`. Revision
`0036_billing_manual_mode` adds a deliberately narrower `manual` local mode;
it is not the future processor-backed `internal` or `pilot` state. `Internal`,
`pilot` and `general` remain future architecture states and cannot be selected
by the current settings contract.

`manual` requires a writable loopback PostgreSQL development server, the exact
private-local server attestation, an explicit organization allowlist and one
immutable organization-owner activation. For the private single-tenant
launcher only, the sole active organization may be derived for the server
allowlist; multiple active organizations require explicit UUIDs. Neither
migration, allowlisting nor startup creates the activation. Manual records
represent only charges and payment facts completed outside CareSync and enable
no processor, money movement, automatic issue, delivery, refund, tax advice,
funding submission or settlement.

Promotion is explicit, audited and reversible to a safer mode. A UI flag cannot promote it. A
future production mode must refuse sandbox processor keys/data and sandbox mode must refuse
production keys; 0033 has neither processor mode nor processor credentials.

Before `pilot`, the gate verifies at runtime:

- released schema, forced tenant RLS, least runtime grants and tenant/facility foreign keys;
- initialized chart, CAD currency, fiscal calendar, facility timezone and document numbering;
- accountant-approved charge/tax mappings and receipt template;
- current signed agreement/Schedule A confirmation and reviewed active funding rule pack;
- permissions, maker/checker policy, approval thresholds and step-up authentication;
- command receipts, journal balancing, outbox/inbox, provider reconciliation and alerting;
- processor sandbox/live account separation, webhook secrets and token-only storage;
- backup plus exact database/document restore rehearsal and written recovery objectives;
- Canada-region/data-processing inventory, retention schedule, privacy notices and breach path;
- complete automated gates, signed operator runbook and accountable pilot owner; and
- no unresolved P0 reconciliation, tenancy, security, privacy or accounting finding.

If any required configuration becomes stale or unavailable, new finalization/claim export/receipt
issue fails closed while read and safe recovery remain available.

## Staged implementation and rollout

### Stage 0 — decisions and fixtures

- obtain accountant, privacy and current-agreement decisions listed under open review;
- freeze domain vocabulary, chart mapping, charge codes and source hierarchy;
- build synthetic fixtures covering daycare, preschool, OSC, split payers, partial months, optional
  services, zero attendance, refunds, chargebacks and adjustments; and
- inventory legacy invoice records without changing or trusting them.

### Stage 1 — shadow subledger

- implement tenant ledger, command receipts, locks, audit and inbox/outbox;
- replay synthetic and copied historical cases without issuing documents or moving money;
- prove property invariants, rebuilds and deterministic results; and
- compare legacy outputs as evidence, not as expected truth.

**0033 checkpoint:** a bounded append-only journal, command receipt/recovery boundary and synthetic
source lineage are implemented. Finance-specific external inbox/provider processing and copied
historical replay are not implemented, so Stage 1 is not declared complete.

### Stage 2 — sandbox receivables

- fee schedules, agreements, invoice drafts/finalization, manual payments, allocations, credits and
  tax-receipt drafts;
- parent-facing sandbox statements and secure documents; and
- full UI/accessibility/exact-retry/backup-restore acceptance.

**0033 checkpoint:** direct synthetic invoice recording, manual synthetic payments, allocations,
credits and the administrator workspace are implemented. Draft/recalculation lifecycle,
statements, secure documents and tax-receipt drafts are absent, so Stage 2 is not declared complete.

### Stage 3 — internal/manual pilot

- one facility, one accountable finance team and manual bank/payment evidence;
- no autopay, no stored government credentials and no automated claim submission;
- daily ledger-to-bank/family reconciliation and weekly issue review; and
- reversible cutover with legacy view-only access.

### Stage 4 — payment processor

- tokenized payment intent/capture, webhook inbox, refund and chargeback workflows;
- provider settlement import and reconciliation before increasing volume; and
- incident, key-rotation and provider-outage rehearsals.

### Stage 5 — Alberta funding workbench

- effective-dated rule packs, claim snapshots, maker/checker approval and evidence export;
- human portal submission plus recorded receipt; remittance import/reconciliation and adjustments;
- optional-service reporting and financial-report workspaces; and
- program/accountant review of real pilot output before broader use.

### Stage 6 — parent self-service and automation

- secure delivery, payments, receipt history, reminders and separately consented autopay;
- payer-split privacy acceptance and notification delivery reconciliation; and
- progressive facility rollout with measurable support and exception rates.

### Stage 7 — integrations and platform commerce

- reviewed QuickBooks/Xero/general-ledger export, not silent bidirectional mutation;
- CareSync SaaS subscription billing in its separate platform ledger; and
- only then evaluate approved government interfaces or broader automation.

### 0033 source evidence checkpoint

The focused, non-additive evidence recorded for this synthetic source boundary is:

- PostgreSQL 16 focused billing gate: 6/6 passed;
- fresh disposable PostgreSQL 17 focused billing gate: 6/6 passed after the final
  trigger/detector edits;
- portable SQLite schema/read/service gate: 8/8 passed, with command writes still forbidden;
- administrator portal: 110 test files / 746 tests, TypeScript and production build passed; and
- whole backend: 1048 passed, 100 intentionally opt-in PostgreSQL tests skipped and 7
  deprecation warnings recorded.

Signed-in synthetic browser acceptance passed. The sandbox boundary loaded; an account opened with
Priya as payer version 1; a rate and agreement were created; and a CAD 100.00 invoice was issued for
a fully covered August period. Reassigning the account to Samir as payer version 2 left the invoice
pinned to Priya/version 1. A CAD 40.00 receipt, CAD 20.00 allocation and CAD 10.00 credit produced
CAD 70.00 outstanding and CAD 20.00 unapplied; reports and readiness reconciled while live snapshot
tokens advanced. The walkthrough exposed a July effective-period gap. The invoice review now
requires full inclusive coverage by both the agreement and its pinned rate and disables Review when
coverage is incomplete; that state was visually reverified.
These results are source evidence only. They are not retained-runtime, real-money, document,
processor, accountant, tax, funding, operator, accessibility, regulatory or production evidence.

## Non-negotiable invariants

1. Every posted journal entry balances debits and credits in one currency.
2. Posted values use integer minor units; financial floats are rejected at every boundary.
3. Finalized entries/documents/allocations are immutable; corrections compensate.
4. A command commits aggregate, journal, receipt, audit and outbox together or writes nothing.
5. Exact retry creates at most one business effect; changed intent cannot reuse an operation ID.
6. Tenant isolation is enforced in schema, RLS, service authorization, queries and client parsing.
7. No balance, status or claim total is authoritative merely because a UI or cache displays it.
8. Payment allocation cannot exceed eligible captured/settled funds net of reversals/refunds.
9. Refund cannot exceed eligible settled funds and requires an explicit destination/provenance.
10. Invoice balance is derived from immutable charges, credits and allocations.
11. A tax receipt cannot exceed eligible net settled allocations for its actual payer/child/year.
12. Issued receipt numbers are never reused; corrections supersede.
13. A claim cannot be approved/exported without pinned attendance, registration, fee, rule and
    agreement evidence plus independent human approval.
14. Attendance/enrollment/care facts are never altered by a finance or claim command.
15. Expected funding, submitted amount, approved amount and remittance remain separate.
16. Exported does not mean submitted; submitted does not mean approved; approved does not mean paid.
17. Optional-service charges require affirmative current consent; penalties require policy/evidence.
18. Tax classification requires an effective accountant-reviewed version; unknown fails closed.
19. Closed-period corrections are later entries or controlled reopen, never hidden back-editing.
20. Realtime and notifications invalidate/alert; canonical authorized reads decide truth.
21. No government or bank credential is stored without a separately approved integration design.
22. No retained/held evidence is deleted, and no expired-purpose data is kept without authority.
23. Every export/issued artifact has tenant, actor, timestamp, scope, hash and source-version manifest.
24. Support, educator, parent and cross-payer boundaries never weaken for convenience.
25. CareSync childcare books and CareSync SaaS platform books never commingle.

## Certification checklist

No stage is called complete until applicable items pass and evidence is recorded.

### Schema, accounting and concurrency

- [ ] Migration upgrade/downgrade/re-upgrade passes on disposable PostgreSQL with preserved source
      data and explicit downgrade-loss warning.
- [ ] Forced RLS, least grants, tenant/facility composite keys and restricted runtime identity pass.
- [ ] Journal balance, immutability, sequence, reversal chain and CAD minor-unit property tests pass.
- [ ] Fee, tax and proration fixtures reproduce accountant-approved results exactly.
- [ ] Concurrent finalize, allocate, refund, close, claim-approve and sequence allocation serialize.
- [ ] Every command passes exact retry, changed-intent, stale-version and cross-tenant tests.

### Payments and recovery

- [ ] Provider signature/account/tenant validation and secret rotation pass.
- [ ] Duplicate, late, out-of-order, changed-ID-content and replayed webhook tests pass.
- [ ] Timeout/crash tests cover every point before/after provider and database commit.
- [ ] Settlement, refund, reversal, chargeback and unapplied-cash reconciliation pass.
- [ ] Projection rebuild matches journal book sequence and hashes.
- [ ] Same-checkpoint database/document restore, inbox/outbox replay and external reconciliation pass.
- [ ] Provider outage and uncertain-status runbooks are exercised by an operator.

### Funding, receipts and reporting

- [ ] Current official sources, signed agreement and Schedule A are versioned and reviewed.
- [ ] Daycare/preschool/OSC, registered-hour, partial-month, zero-attendance, extended-hour and
      optional-service fixtures pass with explainable provenance.
- [ ] Claim source change, adjustment, export-versus-submission and remittance mismatch tests pass.
- [ ] Maker/checker and external-receipt recording cannot be self-bypassed.
- [ ] Receipt actual-payer, per-child, net-payment, refund and supersession tests pass.
- [ ] Accountant signs charge/tax/chart/receipt/report configuration; unresolved BN/SIN handling is
      explicitly closed or the affected path remains disabled.

### Privacy, security and operations

- [ ] Retention/destruction/hold matrix is approved by privacy officer and counsel/accountant as
      applicable; claim, CRA and licensing baselines are represented.
- [ ] Canada-region storage/backups and every subprocessor country/purpose are verified.
- [ ] Raw card/bank login/SIN/child-sensitive data absence is proven in logs, traces, analytics,
      push, exports and support surfaces.
- [ ] PIPA access/correction, breach assessment and secure-destruction exercises pass.
- [ ] Permission, separation-of-duty, step-up, parent split-payer, auditor and support-access tests
      pass at API and UI layers.
- [ ] Rate limits, abuse monitoring, audit integrity, alert routing and reconciliation ownership pass.

### Experience and release

- [ ] Desktop/mobile/responsive, keyboard, screen-reader, contrast and reduced-motion acceptance pass.
- [ ] Loading/empty/stale/offline/error/exact-retry/reconciliation states have actionable resolution.
- [ ] PDFs/statements/exports render correctly, have stable numbers/hashes and disclose status.
- [ ] Realtime invalidation and durable notification delivery/reconciliation pass without PII payloads.
- [ ] Legacy routes stay blocked and sandbox/live data and credentials cannot mix.
- [ ] Pilot operator completes invoice-to-payment-to-receipt and claim-to-remittance scenarios.
- [ ] Finance owner, accountant, privacy owner and engineering release owner sign the capability
      receipt; physical/operator acceptance is recorded separately from automated evidence.

The certification receipt records source revision, migration head, schema/hash evidence, rule-pack
versions, processor environment, test commands/results, backup/restore artifacts, known limitations,
approvers, timestamp and enabled tenant/facility/mode. It must state what was **not** proven. A test
suite passing does not certify legal compliance, tax correctness, funding entitlement or government
acceptance.

## Open decisions that block real-money release

1. Accountant-approved childcare chart mapping and government-funding presentation.
2. Corporate-provider receipt identifier/signature requirements and any individual-provider SIN
   handling.
3. Tax treatment for every non-core supply, including standalone transportation, registration,
   late, NSF and administrative charges.
4. Processor choice, Canadian data path, settlement model, fee/refund/chargeback mapping and PCI
   responsibility matrix.
5. Tenant fiscal calendar, close/reopen policy, approval thresholds and numbering policy.
6. Current signed affordability agreement/Schedule A facts, preschool/OSC/Kindergarten edge cases
   and rule-pack accountable reviewer.
7. Parent payment mandate, autopay notice/cancellation and failed-payment policy.
8. Retention end-state for immutable journal identity fields, backups and legal holds.
9. General-ledger export target and whether funding is mapped as revenue, contra-revenue or another
   accountant-approved classification.
10. Separate CareSync SaaS platform billing/tax/merchant architecture.

Until each affected decision is closed, the corresponding capability remains `disabled`, `shadow`
or `sandbox`. Product enthusiasm, imported data or a visible button is not authorization to move
money or represent a claim as submitted.

export type MinorUnits = number & { readonly __minorUnits: unique symbol };
export type BillingUnit =
  | "weekly_period"
  | "biweekly_period"
  | "monthly_period"
  | "service_event";
export type BillingFrequency =
  | "weekly"
  | "biweekly"
  | "monthly"
  | "per_service";
export type BillingPaymentMethod = "cash" | "cheque" | "e_transfer" | "other";
export type BillingProgramType = "daycare" | "out_of_school_care";
export type BillingRuntimeMode = "shadow" | "sandbox" | "manual";
export type BillingProvenanceLabel =
  | "TEST/SYNTHETIC — NOT A REAL INVOICE"
  | "PRIVATE/MANUAL — OFF-PLATFORM RECORD";

export interface BillingProvenance {
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
}

export interface BillingCapability {
  schema_version: "0033";
  organization_id: string;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  runtime_available: boolean;
  billing_mode: "disabled" | BillingRuntimeMode;
  manual_activation_required: boolean;
  manual_activated: boolean;
  writes_available: boolean;
  currency: "CAD";
  organization_timezone: string;
  organization_local_date: string;
  server_time: string;
  processor_enabled: false;
  money_movement_enabled: false;
  automatic_issue_enabled: false;
  tax_advice_enabled: false;
  off_platform_payment_methods: BillingPaymentMethod[];
  reason_code: string | null;
}

export interface BillingManualActivation {
  schema_version: "0036";
  organization_id: string;
  billing_mode: "manual";
  server_attested: boolean;
  organization_allowlisted: boolean;
  activated: boolean;
  activation_policy_version: "private_local_manual_billing_v1" | null;
  activated_by_user_id: string | null;
  activated_at: string | null;
  immutable: true;
  processor_enabled: false;
  money_movement_enabled: false;
  automatic_issue_enabled: false;
  delivery_enabled: false;
  tax_advice_enabled: false;
}

export interface BillingOverview {
  schema_version: "0033";
  organization_id: string;
  currency: "CAD";
  as_of: string;
  account_count: number;
  open_account_count: number;
  issued_invoice_count: number;
  outstanding_minor: MinorUnits;
  settled_payments_minor: MinorUnits;
  unapplied_payments_minor: MinorUnits;
  credits_minor: MinorUnits;
}

export interface BillingAccountSummary {
  organization_id: string;
  id: string;
  family_id: string;
  payer_guardian_id: string;
  latest_payer_version_id: string;
  latest_payer_version_number: number;
  family_name: string;
  account_number: string;
  status: "open";
  currency: "CAD";
  opened_at: string;
  invoiced_minor: MinorUnits;
  allocated_minor: MinorUnits;
  credits_minor: MinorUnits;
  outstanding_minor: MinorUnits;
  unapplied_minor: MinorUnits;
}

export interface BillingAccountPayerVersion {
  organization_id: string;
  id: string;
  billing_account_id: string;
  family_id: string;
  payer_guardian_id: string;
  version_number: number;
  assigned_by_user_id: string;
  assigned_at: string;
}

export interface BillingInvoiceLine {
  organization_id: string;
  id: string;
  agreement_version_id: string;
  child_id: string;
  line_number: number;
  description: string;
  child_name: string;
  rate_plan_name: string;
  billing_unit: BillingUnit;
  service_period_start: string;
  service_period_end: string;
  quantity: number;
  gross_unit_amount_minor: MinorUnits;
  funding_unit_amount_minor: MinorUnits;
  unit_amount_minor: MinorUnits;
  tax_rate_basis_points: number;
  gross_subtotal_minor: MinorUnits;
  funding_minor: MinorUnits;
  subtotal_minor: MinorUnits;
  tax_minor: MinorUnits;
  total_minor: MinorUnits;
}

export type BillingInvoiceStatus =
  | "open"
  | "partially_settled"
  | "settled_paid"
  | "settled_credited"
  | "settled_mixed";
export interface BillingInvoice extends BillingProvenance {
  organization_id: string;
  document_label: BillingProvenanceLabel;
  id: string;
  billing_account_id: string;
  family_id: string;
  billing_account_payer_version_id: string;
  payer_guardian_id: string;
  invoice_number: string;
  lifecycle_status: BillingInvoiceStatus;
  currency: "CAD";
  issue_date: string;
  due_date: string;
  service_period_start: string;
  service_period_end: string;
  family_name: string;
  payer_name: string;
  payer_email: string | null;
  payer_address: string | null;
  gross_subtotal_minor: MinorUnits;
  funding_minor: MinorUnits;
  subtotal_minor: MinorUnits;
  tax_minor: MinorUnits;
  total_minor: MinorUnits;
  allocated_minor: MinorUnits;
  credits_minor: MinorUnits;
  outstanding_minor: MinorUnits;
  issued_at: string;
  lines: BillingInvoiceLine[];
}

export interface BillingInvoiceDocumentOrganization {
  id: string;
  display_name: string;
  legal_name: string | null;
  email: string | null;
  phone: string | null;
}

export interface BillingInvoiceDocumentInvoice {
  organization_id: string;
  id: string;
  billing_account_id: string;
  family_id: string;
  billing_account_payer_version_id: string;
  payer_guardian_id: string;
  invoice_number: string;
  status: "issued";
  currency: "CAD";
  issue_date: string;
  due_date: string;
  service_period_start: string;
  service_period_end: string;
  family_name: string;
  gross_subtotal_minor: MinorUnits;
  funding_minor: MinorUnits;
  subtotal_minor: MinorUnits;
  tax_minor: MinorUnits;
  total_minor: MinorUnits;
  issued_at: string;
  lines: BillingInvoiceLine[];
}

export interface BillingInvoiceDocumentPayerSnapshot {
  payer_version_id: string;
  guardian_id: string;
  name: string;
  email: string | null;
  address: string | null;
}

export interface BillingInvoiceDocumentAllocation {
  id: string;
  payment_id: string;
  amount_minor: MinorUnits;
  allocated_at: string;
}

export interface BillingInvoiceDocumentCredit {
  id: string;
  amount_minor: MinorUnits;
  reason_code: string;
  note: string | null;
  issued_at: string;
}

export interface BillingInvoiceDocumentSettlement {
  currency: "CAD";
  total_minor: MinorUnits;
  allocated_minor: MinorUnits;
  credits_minor: MinorUnits;
  outstanding_minor: MinorUnits;
}

export interface BillingInvoiceDocumentPreview {
  schema_version: "0033";
  document_version: "billing-invoice-preview-v1";
  organization_id: string;
  invoice_id: string;
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  read_only: true;
  download_enabled: false;
  delivery_enabled: false;
  generated_at: string;
  data_through_at: string;
  data_through_realtime_sequence: number;
  organization: BillingInvoiceDocumentOrganization;
  invoice: BillingInvoiceDocumentInvoice;
  payer_snapshot: BillingInvoiceDocumentPayerSnapshot;
  allocations: BillingInvoiceDocumentAllocation[];
  credits: BillingInvoiceDocumentCredit[];
  settlement: BillingInvoiceDocumentSettlement;
  canonical_sha256: string;
}

export type BillingPaymentStatus =
  | "settled"
  | "partially_allocated"
  | "fully_allocated";
export interface BillingPayment extends BillingProvenance {
  organization_id: string;
  id: string;
  billing_account_id: string;
  family_id: string;
  payer_guardian_id: string;
  payer_name: string;
  payer_email: string | null;
  lifecycle_status: BillingPaymentStatus;
  method: BillingPaymentMethod;
  currency: "CAD";
  amount_minor: MinorUnits;
  allocated_minor: MinorUnits;
  unapplied_minor: MinorUnits;
  external_reference: string;
  memo: string | null;
  operator_confirmation_note: string | null;
  received_at: string;
  recorded_at: string;
}

export interface BillingAllocation {
  organization_id: string;
  id: string;
  billing_account_id: string;
  payment_id: string;
  invoice_id: string;
  amount_minor: MinorUnits;
  allocated_by_user_id: string;
  allocated_at: string;
  client_operation_id: string;
  request_hash: string;
}

export interface BillingCredit {
  organization_id: string;
  id: string;
  billing_account_id: string;
  invoice_id: string;
  status: "issued";
  currency: "CAD";
  amount_minor: MinorUnits;
  reason_code: string;
  note: string | null;
  issued_by_user_id: string;
  issued_at: string;
  client_operation_id: string;
  request_hash: string;
}

export interface BillingRatePlanVersion {
  organization_id: string;
  id: string;
  rate_plan_id: string;
  version_number: number;
  status: "published";
  billing_unit: BillingUnit;
  unit_amount_minor: MinorUnits;
  tax_rate_basis_points: number;
  currency: "CAD";
  effective_from: string;
  effective_until: string | null;
  description: string | null;
  published_at: string;
}

export interface BillingRatePlan {
  organization_id: string;
  id: string;
  code: string;
  name: string;
  program_type: BillingProgramType;
  charge_kind: "core_care";
  age_group: string | null;
  facility_id: string | null;
  program_id: string | null;
  created_at: string;
  latest_version: BillingRatePlanVersion;
  versions: BillingRatePlanVersion[];
}

export interface BillingAgreementVersion {
  organization_id: string;
  id: string;
  agreement_id: string;
  rate_plan_version_id: string;
  version_number: number;
  billing_frequency: BillingFrequency;
  family_amount_minor_per_unit: MinorUnits;
  funding_amount_minor_per_unit: MinorUnits;
  effective_from: string;
  effective_until: string | null;
  review_status: "reviewed";
  reviewed_at: string;
}

export interface BillingAgreement {
  organization_id: string;
  id: string;
  billing_account_id: string;
  family_id: string;
  child_id: string;
  child_name: string;
  enrollment_id: string | null;
  facility_id: string | null;
  created_at: string;
  latest_version: BillingAgreementVersion;
  versions: BillingAgreementVersion[];
}

export interface BillingAccountDetail {
  schema_version: "0033";
  organization_id: string;
  currency: "CAD";
  account: BillingAccountSummary;
  payer_versions: BillingAccountPayerVersion[];
  invoices: BillingInvoice[];
  payments: BillingPayment[];
  agreements: BillingAgreement[];
}

export interface BillingPageResult<T> {
  schema_version: "0033";
  organization_id: string;
  currency?: "CAD";
  items: T[];
  total: number;
}

export interface BillingOffsetPageResult<T> extends BillingPageResult<T> {
  limit: number;
  offset: number;
}

export interface BillingCollectionPage {
  offset: number;
  limit: number;
  returned: number;
  total: number;
  has_more: boolean;
  next_offset: number | null;
}

export type BillingWorkspaceCollection =
  | "accounts"
  | "payer_versions"
  | "invoices"
  | "payments"
  | "rate_plans"
  | "agreements"
  | "allocations"
  | "credits";

export type BillingWorkspacePaging = {
  snapshot_token: string;
} & Record<BillingWorkspaceCollection, BillingCollectionPage>;

export interface BillingWorkspacePage {
  schema_version: "0033";
  organization_id: string;
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  complete: boolean;
  canonical_collection_limit: number;
  generated_at: string;
  data_through_realtime_sequence: number;
  paging: BillingWorkspacePaging;
  overview: BillingOverview;
  accounts: BillingPageResult<BillingAccountSummary>;
  payer_versions: BillingPageResult<BillingAccountPayerVersion>;
  invoices: BillingPageResult<BillingInvoice>;
  payments: BillingPageResult<BillingPayment>;
  rate_plans: BillingPageResult<BillingRatePlan>;
  agreements: BillingPageResult<BillingAgreement>;
  allocations: BillingOffsetPageResult<BillingAllocation>;
  credits: BillingOffsetPageResult<BillingCredit>;
}

export interface BillingWorkspaceProjection {
  schema_version: "0033";
  organization_id: string;
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  complete: true;
  canonical_collection_limit: number;
  generated_at: string;
  data_through_realtime_sequence: number;
  snapshot_token: string;
  overview: BillingOverview;
  accounts: BillingPageResult<BillingAccountSummary>;
  payer_versions: BillingPageResult<BillingAccountPayerVersion>;
  invoices: BillingPageResult<BillingInvoice>;
  payments: BillingPageResult<BillingPayment>;
  rate_plans: BillingPageResult<BillingRatePlan>;
  agreements: BillingPageResult<BillingAgreement>;
  allocations: BillingPageResult<BillingAllocation>;
  credits: BillingPageResult<BillingCredit>;
}

export interface BillingGuardianOption {
  organization_id: string;
  id: string;
  family_id: string;
  name: string;
  email: string;
  cell_phone: string;
}
export interface BillingChildOption {
  organization_id: string;
  id: string;
  family_id: string;
  name: string;
  age_group: string | null;
  enrollment_id: string | null;
  facility_id: string | null;
  program_id: string | null;
  program_type: "daycare" | "out_of_school_care" | null;
}
export interface BillingFamilyOption {
  organization_id: string;
  id: string;
  name: string;
  status: "active";
  guardians: BillingGuardianOption[];
  children: BillingChildOption[];
}
export interface BillingProgramOption {
  organization_id: string;
  facility_id: string;
  facility_name: string;
  program_id: string;
  program_name: string;
  program_type: "daycare" | "out_of_school_care";
  minimum_age_months: number | null;
  maximum_age_months: number | null;
}
export interface BillingFamilyOptions {
  schema_version: "0033";
  organization_id: string;
  items: BillingFamilyOption[];
  programs: BillingProgramOption[];
  total: number;
  limit: number;
  offset: number;
}

export type BillingCommandKind =
  | "account.create"
  | "account.payer.assign"
  | "rate_plan.create"
  | "agreement.create"
  | "invoice.issue"
  | "payment.record"
  | "payment.allocate"
  | "credit.create";
export interface BillingCommandReceipt {
  schema_version: "0033";
  organization_id: string;
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  client_operation_id: string;
  request_hash: string;
  command_type:
    | "account_open"
    | "account_payer_assign"
    | "rate_version_publish"
    | "agreement_establish"
    | "invoice_issue"
    | "payment_record"
    | "payment_allocate"
    | "credit_issue";
  result_kind:
    | "billing_account"
    | "billing_rate_plan"
    | "billing_agreement"
    | "billing_invoice"
    | "billing_payment"
    | "billing_allocation"
    | "billing_credit";
  result_id: string;
  committed_at: string;
  exact_retry: boolean;
  action_path: string;
}
export interface BillingCommandPreparation {
  schema_version: "0033";
  organization_id: string;
  billing_mode: BillingRuntimeMode;
  sandbox: boolean;
  provenance_label: BillingProvenanceLabel;
  client_operation_id: string;
  command_type: BillingCommandReceipt["command_type"];
  target_scope: string;
  request_hash: string;
  prepared_at: string;
  exact_retry: boolean;
}

export interface CreateBillingAccountInput {
  family_id: string;
  payer_guardian_id: string;
}
export interface AssignBillingAccountPayerInput {
  account_id: string;
  payer_guardian_id: string;
  expected_latest_payer_version_id: string;
  expected_latest_payer_version_number: number;
}
export interface CreateRatePlanInput {
  rate_plan_id?: string | null;
  expected_latest_version_id?: string | null;
  expected_latest_version_number?: number | null;
  code?: string | null;
  name?: string | null;
  program_type?: BillingProgramType | null;
  charge_kind?: "core_care" | null;
  age_group?: string | null;
  facility_id?: string | null;
  program_id?: string | null;
  billing_unit: BillingUnit;
  unit_amount_minor: MinorUnits;
  tax_rate_basis_points: 0;
  effective_from: string;
  effective_until?: string | null;
  description?: string | null;
}
export interface CreateAgreementInput {
  agreement_id?: string | null;
  expected_latest_version_id?: string | null;
  expected_latest_version_number?: number | null;
  account_id?: string | null;
  child_id?: string | null;
  enrollment_id?: string | null;
  rate_plan_version_id: string;
  billing_frequency: BillingFrequency;
  effective_from: string;
  effective_until?: string | null;
  family_amount_minor_per_unit: MinorUnits;
  funding_amount_minor_per_unit: 0;
  reviewed: true;
}
export interface IssueInvoiceInput {
  account_id: string;
  agreements: Array<{ agreement_id: string; agreement_version_id: string }>;
  service_period_start: string;
  service_period_end: string;
  issue_date: string;
  due_date: string;
}
export interface RecordPaymentInput {
  account_id: string;
  payer_guardian_id: string;
  amount_minor: MinorUnits;
  method: BillingPaymentMethod;
  received_at: string;
  external_reference: string;
  memo?: string | null;
  operator_confirmation_note?: string | null;
}
export interface AllocatePaymentInput {
  payment_id: string;
  invoice_id: string;
  amount_minor: MinorUnits;
  expected_payment_unapplied_minor: MinorUnits;
  expected_invoice_outstanding_minor: MinorUnits;
}
export interface CreateCreditInput {
  invoice_id: string;
  amount_minor: MinorUnits;
  expected_invoice_outstanding_minor: MinorUnits;
  reason_code: string;
  note?: string | null;
}

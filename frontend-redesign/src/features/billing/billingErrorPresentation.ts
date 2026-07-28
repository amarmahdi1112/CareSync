export type BillingErrorRecovery =
  | "edit"
  | "refresh"
  | "review_setup"
  | "request_access"
  | "reconcile"
  | "retry_later";

export interface BillingErrorPresentation {
  code: string | null;
  message: string;
  recovery: BillingErrorRecovery;
}

type Detail = Record<string, unknown>;
type KnownPresentation = (
  detail: Detail,
) => Omit<BillingErrorPresentation, "code">;

const fixed =
  (
    message: string,
    recovery: BillingErrorRecovery,
  ): KnownPresentation =>
  () => ({ message, recovery });

const KNOWN_BILLING_ERRORS: Record<string, KnownPresentation> = {
  billing_ledger_unavailable: fixed(
    "Billing is not available in this workspace. Confirm the protected billing runtime and organization readiness before trying again.",
    "retry_later",
  ),
  billing_sandbox_writes_disabled: fixed(
    "Billing changes are disabled for this workspace. Use an approved disposable billing sandbox or wait for the controlled release.",
    "request_access",
  ),
  billing_manual_activation_required: fixed(
    "Private manual billing is read-only until an organization owner reviews and activates the immutable off-platform boundary.",
    "review_setup",
  ),
  billing_owner_required: fixed(
    "Only an organization owner with billing management access can activate private manual billing.",
    "request_access",
  ),
  billing_manual_mode_disabled: fixed(
    "This server is not configured for private manual billing. No activation was attempted.",
    "request_access",
  ),
  billing_manual_boundary_unavailable: fixed(
    "The private manual billing boundary is unavailable in this runtime. Keep billing read-only and restart the approved local release.",
    "retry_later",
  ),
  billing_manual_server_attestation_required: fixed(
    "The server has not attested that this is the approved private local manual-billing target. Activation remains blocked.",
    "request_access",
  ),
  billing_manual_organization_not_allowlisted: fixed(
    "This organization is not allowlisted for private manual billing. Activation remains blocked.",
    "request_access",
  ),
  billing_manual_activation_requires_empty_ledger: fixed(
    "Private manual billing can only be activated before any billing ledger facts exist. Preserve the current records and complete a reviewed migration instead.",
    "review_setup",
  ),
  billing_manual_activation_conflict: fixed(
    "Manual billing activation changed concurrently. Refresh capability and review the immutable activation record.",
    "refresh",
  ),
  billing_permission_required: fixed(
    "Your current role cannot perform this billing action. Ask an organization owner to grant the specific billing permission.",
    "request_access",
  ),
  billing_account_payer_needs_review: fixed(
    "This family account has no valid current payer. Review the guardian record and publish a current payer assignment before invoicing.",
    "review_setup",
  ),
  billing_agreement_period_already_invoiced: fixed(
    "This agreement and service period already have an invoice. Open the existing invoice instead of issuing a duplicate.",
    "review_setup",
  ),
  billing_agreement_version_stale: fixed(
    "The selected agreement version is no longer the effective version for this period. Refresh and review the exact historical version again.",
    "refresh",
  ),
  billing_agreement_not_effective_for_period: fixed(
    "The reviewed agreement does not cover every day in this service period. Choose a covered period or publish the missing agreement version.",
    "edit",
  ),
  billing_agreement_not_reviewed: fixed(
    "The selected agreement version is not reviewed. Complete agreement review before issuing an invoice.",
    "review_setup",
  ),
  billing_agreement_rate_drift: fixed(
    "The agreement is pinned to a rate that is not effective for this period. Publish a matching agreement revision, then review the invoice again.",
    "review_setup",
  ),
  billing_service_period_frequency_mismatch: fixed(
    "The service dates do not form one complete contracted billing period. Choose the exact weekly, biweekly, monthly, or service-event boundary.",
    "edit",
  ),
  billing_mixed_agreement_frequencies: fixed(
    "The selected agreements use different billing frequencies. Issue separate invoices for each frequency.",
    "edit",
  ),
  billing_invoice_issue_date_must_be_today: (detail) => ({
    message:
      typeof detail.organization_local_date === "string"
        ? `Set the issue date to the organization's current date, ${detail.organization_local_date}, then review the invoice again.`
        : "Refresh the organization clock, set the issue date to organization-local today, and review the invoice again.",
    recovery: "edit",
  }),
  billing_invoice_has_no_family_charge: fixed(
    "This invoice has no family-payable amount. Review the agreement funding split before issuing it.",
    "review_setup",
  ),
  billing_rate_not_effective_for_agreement: fixed(
    "The selected rate does not cover the agreement's full effective window. Choose a compatible rate version or shorten the agreement window.",
    "edit",
  ),
  billing_rate_version_stale: fixed(
    "A newer rate version was published while you were reviewing. Refresh and confirm the current effective rate.",
    "refresh",
  ),
  billing_workspace_snapshot_advanced: fixed(
    "Billing records changed while this workspace was loading. Refresh once to rebuild a coherent snapshot before continuing.",
    "refresh",
  ),
  billing_readiness_batch_snapshot_advanced: fixed(
    "Billing or enrollment records changed during setup review. Restart the dependency plan and preview the exact wave again; no reviewed setup command was sent.",
    "refresh",
  ),
  billing_payment_reference_reused: fixed(
    "That payment reference is already recorded. Open the existing receipt or enter the distinct bank, cheque, or cash reference.",
    "edit",
  ),
  billing_payment_received_at_in_future: fixed(
    "The receipt time is later than the organization clock. Correct the received time before recording the payment.",
    "edit",
  ),
  billing_payment_overallocated: fixed(
    "This payment no longer has enough unapplied value for that allocation. Refresh and allocate only the remaining amount.",
    "refresh",
  ),
  billing_allocation_projection_stale: fixed(
    "The payment or invoice balance changed during review. Refresh both balances before allocating again.",
    "refresh",
  ),
  billing_credit_exceeds_outstanding: fixed(
    "The credit is greater than the invoice's current outstanding balance. Refresh and enter an amount within the remaining balance.",
    "edit",
  ),
  billing_operation_reused: fixed(
    "This protected operation identifier was already used for different details. Reconcile the existing operation before starting another change.",
    "reconcile",
  ),
  billing_operation_already_committed: fixed(
    "This protected billing change is already committed. Reconcile its receipt and refresh; do not submit it again.",
    "reconcile",
  ),
  billing_command_receipt_not_found: fixed(
    "The server cannot yet prove the outcome of this protected billing command. Keep billing locked and reconcile before retrying.",
    "reconcile",
  ),
  billing_operation_reconciliation_conflict: fixed(
    "The protected browser proof and server record disagree. Stop financial changes and complete reconciliation before continuing.",
    "reconcile",
  ),
  organization_timezone_invalid: fixed(
    "The organization's timezone is invalid, so CareSync cannot prove the billing date. Correct the organization timezone before issuing.",
    "review_setup",
  ),
};

function record(value: unknown): Detail | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Detail)
    : null;
}

function errorDetails(caught: unknown): Detail | null {
  const caughtRecord = record(caught);
  const details = record(caughtRecord?.details);
  const payload = details || caughtRecord;
  return record(payload?.detail) || payload;
}

export function billingServerErrorCode(caught: unknown): string | null {
  const code = errorDetails(caught)?.code;
  return typeof code === "string" && code.trim() ? code : null;
}

export function presentBillingError(caught: unknown): BillingErrorPresentation {
  const detail = errorDetails(caught) || {};
  const code =
    typeof detail.code === "string" && detail.code.trim() ? detail.code : null;
  const known = code ? KNOWN_BILLING_ERRORS[code] : undefined;
  if (known) return { code, ...known(detail) };
  if (caught instanceof Error && caught.message.trim())
    return { code, message: caught.message, recovery: "retry_later" };
  return {
    code,
    message: code
      ? `Billing could not complete this request. Refresh and try again; if it repeats, report reference code ${code}.`
      : "Billing could not complete this request. Refresh and try again.",
    recovery: "retry_later",
  };
}

export function billingErrorMessage(caught: unknown): string {
  return presentBillingError(caught).message;
}

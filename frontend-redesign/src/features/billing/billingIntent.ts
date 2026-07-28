import type { BillingCommandKind, BillingCommandReceipt } from "./types";

const COMMAND_TYPES: Record<
  BillingCommandKind,
  BillingCommandReceipt["command_type"]
> = {
  "account.create": "account_open",
  "account.payer.assign": "account_payer_assign",
  "rate_plan.create": "rate_version_publish",
  "agreement.create": "agreement_establish",
  "invoice.issue": "invoice_issue",
  "payment.record": "payment_record",
  "payment.allocate": "payment_allocate",
  "credit.create": "credit_issue",
};

export function billingCommandType(
  commandKind: BillingCommandKind,
): BillingCommandReceipt["command_type"] {
  return COMMAND_TYPES[commandKind];
}

export function billingPreparePayload(
  commandKind: BillingCommandKind,
  operationId: string,
  input: Record<string, unknown>,
): Record<string, unknown> {
  return {
    command_type: billingCommandType(commandKind),
    request_payload: {
      client_operation_id: operationId,
      ...input,
    },
  };
}

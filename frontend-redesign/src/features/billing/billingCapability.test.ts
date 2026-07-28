import { describe, expect, it } from "vitest";
import { billingCapabilityIsLive } from "./billingCapability";
import type { BillingCapability } from "./types";

function capability(
  overrides: Partial<BillingCapability> = {},
): BillingCapability {
  return {
    schema_version: "0033",
    organization_id: "11111111-1111-4111-8111-111111111111",
    billing_mode: "manual",
    sandbox: false,
    provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    runtime_available: true,
    writes_available: true,
    manual_activation_required: false,
    manual_activated: true,
    currency: "CAD",
    organization_timezone: "America/Edmonton",
    organization_local_date: "2026-07-22",
    server_time: "2026-07-22T20:00:00Z",
    processor_enabled: false,
    money_movement_enabled: false,
    automatic_issue_enabled: false,
    tax_advice_enabled: false,
    off_platform_payment_methods: ["cash", "cheque", "e_transfer", "other"],
    reason_code: null,
    ...overrides,
  };
}

describe("billing runtime release status", () => {
  it("is live only for the ready, owner-reviewed private manual boundary", () => {
    expect(billingCapabilityIsLive(capability())).toBe(true);
    expect(
      billingCapabilityIsLive(
        capability({
          manual_activation_required: true,
          manual_activated: false,
          writes_available: false,
        }),
      ),
    ).toBe(false);
    expect(
      billingCapabilityIsLive(
        capability({
          billing_mode: "sandbox",
          sandbox: true,
          provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
          manual_activated: false,
        }),
      ),
    ).toBe(false);
    expect(
      billingCapabilityIsLive(capability({ writes_available: false })),
    ).toBe(false);
    expect(
      billingCapabilityIsLive(capability({ runtime_available: false })),
    ).toBe(false);
  });
});

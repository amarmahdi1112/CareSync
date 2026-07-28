import { describe, expect, it } from "vitest";
import {
  parseBillingBatchPlan,
  parseBillingBatchPreview,
} from "./billingBatchPlanApi";

const organizationId = "11111111-1111-4111-8111-111111111111";
const familyId = "22222222-2222-4222-8222-222222222222";
const childId = "33333333-3333-4333-8333-333333333333";
const enrollmentId = "44444444-4444-4444-8444-444444444444";
const guardianId = "55555555-5555-4555-8555-555555555555";
const operationId = "66666666-6666-4666-8666-666666666666";
const snapshotToken = "a".repeat(64);
const groupId = "b".repeat(64);
const membershipDigest = "c".repeat(64);
const requestHash = "d".repeat(64);

function group(overrides: Record<string, unknown> = {}) {
  return {
    group_id: groupId,
    wave: "account_payer",
    readiness_status: "needs_account",
    reason_codes: ["billing_account_missing"],
    actionable: true,
    block_code: null,
    suggested_command_type: "account_open",
    family_id: familyId,
    family_name: "Example Family",
    billing_account_id: null,
    latest_payer_version_id: null,
    latest_payer_version_number: null,
    facility_id: null,
    facility_name: null,
    program_id: null,
    program_name: null,
    program_type: null,
    age_group: null,
    rate_plan_id: null,
    rate_plan_version_id: null,
    rate_billing_unit: null,
    rate_unit_amount_minor: null,
    rate_effective_from: null,
    rate_effective_until: null,
    agreement_effective_from_min: null,
    agreement_effective_until_max: null,
    agreement_effective_until_required: false,
    affected_count: 26,
    affected_membership_digest: membershipDigest,
    affected_children: [
      {
        family_id: familyId,
        family_name: "Example Family",
        child_id: childId,
        child_name: "Example Child",
        enrollment_id: enrollmentId,
      },
    ],
    affected_children_truncated: true,
    payer_options: [
      {
        guardian_id: guardianId,
        display_name: "Example Guardian",
        is_primary: true,
      },
    ],
    rate_plan_options: [],
    action_path: `/families/${familyId}?section=billing`,
    ...overrides,
  };
}

function ratePlanOption(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    rate_plan_id: operationId,
    code: "DAYCARE",
    name: "Daycare rate",
    age_group: "preschool",
    latest_version_id: enrollmentId,
    latest_version_number: 1,
    latest_billing_unit: "monthly_period",
    latest_unit_amount_minor: 12_500,
    latest_effective_from: "2026-01-01",
    latest_effective_until: null,
    revision_can_resolve_as_of_date: true,
    ...overrides,
  };
}

function plan(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "billing-readiness-batch-plan-v1",
    organization_id: organizationId,
    generated_at: "2026-07-23T12:00:00Z",
    as_of_date: "2026-07-23",
    data_through_realtime_sequence: 42,
    snapshot_token: snapshotToken,
    read_only: true,
    apply_available: false,
    manual_activation_required: true,
    counts: {
      total: 1,
      account_payer: 1,
      rate_plan: 0,
      agreement: 0,
      ready: 0,
      manual_review: 0,
    },
    page: {
      offset: 0,
      limit: 25,
      returned: 1,
      total: 1,
      has_more: false,
      next_offset: null,
    },
    items: [group()],
    ...overrides,
  };
}

function preview(overrides: Record<string, unknown> = {}) {
  const requestPayload = {
    client_operation_id: operationId,
    family_id: familyId,
    payer_guardian_id: guardianId,
  };
  return {
    schema_version: "billing-readiness-batch-preview-v1",
    organization_id: organizationId,
    snapshot_token: snapshotToken,
    wave: "account_payer",
    previewed_at: "2026-07-23T12:01:00Z",
    data_through_realtime_sequence: 42,
    read_only: true,
    apply_available: false,
    manual_activation_required: true,
    requires_sequential_execution: true,
    requires_canonical_refresh_after_each_intent: true,
    intents: [
      {
        sequence: 1,
        group_id: groupId,
        label: "Open account for Example Family",
        command_type: "account_open",
        client_operation_id: operationId,
        target_scope: familyId,
        request_hash: requestHash,
        request_payload: requestPayload,
        prepare_request: {
          command_type: "account_open",
          request_payload: requestPayload,
        },
        execute_path: "/api/v1/billing/accounts",
        affected_count: 26,
      },
    ],
    blocked: [],
    ...overrides,
  };
}

describe("billing readiness batch-plan contract", () => {
  it("accepts a bounded child preview while retaining the full affected proof", () => {
    const parsed = parseBillingBatchPlan(plan(), organizationId);
    expect(parsed.items[0]).toMatchObject({
      group_id: groupId,
      affected_count: 26,
      affected_membership_digest: membershipDigest,
      affected_children_truncated: true,
    });
    expect(parsed.items[0]?.affected_children).toHaveLength(1);
  });

  it("rejects a truncated flag or count that does not reconcile", () => {
    expect(() =>
      parseBillingBatchPlan(
        plan({
          items: [
            group({
              affected_count: 1,
              affected_children_truncated: true,
            }),
          ],
        }),
        organizationId,
      ),
    ).toThrow("affected preview proof");
  });

  it("requires the rate revision availability proof", () => {
    const parsed = parseBillingBatchPlan(
      plan({
        items: [group({ rate_plan_options: [ratePlanOption()] })],
      }),
      organizationId,
    );
    expect(
      parsed.items[0]?.rate_plan_options[0]?.revision_can_resolve_as_of_date,
    ).toBe(true);

    const missing = ratePlanOption();
    delete missing.revision_can_resolve_as_of_date;
    expect(() =>
      parseBillingBatchPlan(
        plan({ items: [group({ rate_plan_options: [missing] })] }),
        organizationId,
      ),
    ).toThrow("rate option");
  });

  it("accepts the immutable read-only preview and strips only the operation id from command input", () => {
    const parsed = parseBillingBatchPreview(
      preview(),
      organizationId,
      snapshotToken,
      "account_payer",
    );
    expect(parsed.intents[0]).toMatchObject({
      command_type: "account_open",
      command_kind: "account.create",
      client_operation_id: operationId,
      request_hash: requestHash,
      affected_count: 26,
      input: {
        family_id: familyId,
        payer_guardian_id: guardianId,
      },
    });
    expect(parsed.intents[0]?.input).not.toHaveProperty("client_operation_id");
  });

  it("accepts valid plan and preview counts beyond arbitrary client caps", () => {
    const largeCount = 1_000_001;
    const parsedPlan = parseBillingBatchPlan(
      plan({
        items: [
          group({
            affected_count: largeCount,
            affected_children_truncated: true,
          }),
        ],
      }),
      organizationId,
    );
    const largeGroup = preview();
    (
      largeGroup.intents as Array<Record<string, unknown>>
    )[0].affected_count = largeCount;
    const parsed = parseBillingBatchPreview(
      largeGroup,
      organizationId,
      snapshotToken,
      "account_payer",
    );
    expect(parsedPlan.items[0]?.affected_count).toBe(largeCount);
    expect(parsed.intents[0]?.affected_count).toBe(largeCount);
  });

  it("fails closed on preview payload drift, an unsafe destination, or a non-setup command", () => {
    const changedPrepare = preview();
    const changedIntent = (
      changedPrepare.intents as Array<Record<string, any>>
    )[0];
    changedIntent.prepare_request = {
      ...changedIntent.prepare_request,
      request_payload: {
        ...changedIntent.prepare_request.request_payload,
        payer_guardian_id: childId,
      },
    };
    expect(() =>
      parseBillingBatchPreview(
        changedPrepare,
        organizationId,
        snapshotToken,
        "account_payer",
      ),
    ).toThrow("prepare proof");

    const unsafePath = preview();
    (unsafePath.intents as Array<Record<string, unknown>>)[0].execute_path =
      "/api/v1/billing/invoices/issue";
    expect(() =>
      parseBillingBatchPreview(
        unsafePath,
        organizationId,
        snapshotToken,
        "account_payer",
      ),
    ).toThrow("command destination");

    const invoice = preview();
    (invoice.intents as Array<Record<string, unknown>>)[0].command_type =
      "invoice_issue";
    expect(() =>
      parseBillingBatchPreview(
        invoice,
        organizationId,
        snapshotToken,
        "account_payer",
      ),
    ).toThrow("preview command");
  });
});

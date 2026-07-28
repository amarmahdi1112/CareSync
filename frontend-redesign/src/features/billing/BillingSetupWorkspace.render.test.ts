import { createElement } from "react";
import {
  act,
  create,
  type ReactTestInstance,
  type ReactTestRenderer,
} from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "styled-components";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { workspaceTheme } from "../../styles/theme";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

const organizationId = "11111111-1111-4111-8111-111111111111";
const actorId = "22222222-2222-4222-8222-222222222222";
const familyId = "33333333-3333-4333-8333-333333333333";
const childId = "44444444-4444-4444-8444-444444444444";
const enrollmentId = "55555555-5555-4555-8555-555555555555";
const guardianId = "66666666-6666-4666-8666-666666666666";
const secondFamilyId = "77777777-7777-4777-8777-777777777777";
const secondChildId = "88888888-8888-4888-8888-888888888888";
const secondGuardianId = "99999999-9999-4999-8999-999999999999";
const groupId = "a".repeat(64);
const secondGroupId = "b".repeat(64);
const snapshotToken = "c".repeat(64);
const operationId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const secondOperationId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const harness = vi.hoisted(() => ({
  session: {
    status: "authenticated",
    user: {
      id: "22222222-2222-4222-8222-222222222222",
      organization_id: "11111111-1111-4111-8111-111111111111",
      membership_status: "active",
      role: {
        key: "administrator",
        permissions: ["billing:read", "billing:manage"],
      },
    },
  } as any,
  capability: {
    phase: "enabled",
    enabled: true,
    live: false,
    error: null,
    retry: vi.fn(),
    capability: {
      runtime_available: true,
      writes_available: false,
      billing_mode: "manual",
      manual_activation_required: true,
      manual_activated: false,
    },
  } as any,
  fetchPlan: vi.fn(),
  previewWave: vi.fn(),
  readPending: vi.fn(),
  readVolatile: vi.fn(),
  clearPending: vi.fn(),
  executeProtected: vi.fn(),
  reconcileCommand: vi.fn(),
  prepareCommand: vi.fn(),
  createAccount: vi.fn(),
  assignAccountPayer: vi.fn(),
  createRatePlan: vi.fn(),
  createAgreement: vi.fn(),
  realtimeRefresh: null as null | (() => Promise<void>),
}));

vi.mock("../../auth/SessionContext", () => ({
  useSession: () => harness.session,
}));

vi.mock("../../realtime/RealtimeContext", () => ({
  useRealtimeRefresh: (options: { refresh: () => Promise<void> }) => {
    harness.realtimeRefresh = options.refresh;
  },
}));

vi.mock("./billingCapability", () => ({
  useBillingCapability: () => harness.capability,
}));

vi.mock("./billingBatchPlanApi", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("./billingBatchPlanApi")>();
  return {
    ...original,
    fetchBillingBatchPlan: harness.fetchPlan,
    previewBillingBatchWave: harness.previewWave,
  };
});

vi.mock("./billingOperation", async (importOriginal) => {
  const original = await importOriginal<typeof import("./billingOperation")>();
  return {
    ...original,
    readPendingBillingOperation: harness.readPending,
    readVolatileBillingOperationInput: harness.readVolatile,
    clearPendingBillingOperation: harness.clearPending,
    executeProtectedBillingCommand: harness.executeProtected,
  };
});

vi.mock("./billingApi", () => ({
  billingApi: {
    reconcileCommand: harness.reconcileCommand,
    prepareCommand: harness.prepareCommand,
    createAccount: harness.createAccount,
    assignAccountPayer: harness.assignAccountPayer,
    createRatePlan: harness.createRatePlan,
    createAgreement: harness.createAgreement,
  },
}));

import BillingSetupWorkspace from "./BillingSetupWorkspace";

function planGroup(
  id = groupId,
  overrides: Record<string, unknown> = {},
) {
  return {
    group_id: id,
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
    affected_count: 1,
    affected_membership_digest: "d".repeat(64),
    affected_children: [
      {
        family_id: familyId,
        family_name: "Example Family",
        child_id: childId,
        child_name: "Example Child",
        enrollment_id: enrollmentId,
      },
    ],
    affected_children_truncated: false,
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

function canonicalPlan(
  items: ReturnType<typeof planGroup>[] = [planGroup()],
  overrides: Record<string, unknown> = {},
) {
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
      total: items.length,
      account_payer: items.length,
      rate_plan: 0,
      agreement: 0,
      ready: 0,
      manual_review: 0,
    },
    page: {
      offset: 0,
      limit: 25,
      returned: items.length,
      total: items.length,
      has_more: false,
      next_offset: null,
    },
    items,
    ...overrides,
  };
}

function intent(
  id = operationId,
  group = groupId,
  family = familyId,
  payer = guardianId,
  sequence = 1,
) {
  return {
    sequence,
    group_id: group,
    label: `Open account ${sequence}`,
    command_type: "account_open",
    command_kind: "account.create",
    client_operation_id: id,
    target_scope: family,
    request_hash: sequence === 1 ? "e".repeat(64) : "f".repeat(64),
    request_payload: {
      client_operation_id: id,
      family_id: family,
      payer_guardian_id: payer,
    },
    input: { family_id: family, payer_guardian_id: payer },
    execute_path: "/api/v1/billing/accounts",
    affected_count: 1,
  };
}

function canonicalPreview(
  intents = [intent()],
  overrides: Record<string, unknown> = {},
) {
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
    intents,
    blocked: [],
    ...overrides,
  };
}

function text(node: ReactTestInstance): string {
  return node.children
    .map((child) => (typeof child === "string" ? child : text(child)))
    .join("");
}

function button(
  renderer: ReactTestRenderer,
  label: string,
): ReactTestInstance {
  const found = renderer.root.findAll(
    (node) => node.type === "button" && text(node).includes(label),
  )[0];
  if (!found) throw new Error(`Button not found: ${label}`);
  return found;
}

async function renderWorkspace(): Promise<ReactTestRenderer> {
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      createElement(
        ThemeProvider,
        { theme: workspaceTheme },
        createElement(
          MemoryRouter,
          { initialEntries: ["/billing?view=setup"] },
          createElement(BillingSetupWorkspace),
        ),
      ),
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer;
}

beforeEach(() => {
  harness.session.user.organization_id = organizationId;
  harness.session.user.id = actorId;
  harness.session.user.role.permissions = ["billing:read", "billing:manage"];
  harness.capability.phase = "enabled";
  harness.capability.capability.runtime_available = true;
  harness.capability.capability.writes_available = false;
  harness.capability.capability.manual_activation_required = true;
  harness.capability.capability.manual_activated = false;
  harness.fetchPlan.mockReset().mockResolvedValue(canonicalPlan());
  harness.previewWave.mockReset().mockResolvedValue(canonicalPreview());
  harness.readPending.mockReset().mockReturnValue(null);
  harness.readVolatile.mockReset().mockReturnValue(null);
  harness.clearPending.mockReset();
  harness.executeProtected.mockReset();
  harness.reconcileCommand.mockReset();
  harness.prepareCommand.mockReset();
  harness.realtimeRefresh = null;
  vi.stubGlobal("crypto", {
    randomUUID: vi
      .fn()
      .mockReturnValueOnce(operationId)
      .mockReturnValue(secondOperationId),
  });
});

describe("BillingSetupWorkspace rendered behavior", () => {
  it("renders loading, empty, and error states without inventing setup success", async () => {
    let resolvePlan!: (value: unknown) => void;
    harness.fetchPlan.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePlan = resolve;
      }),
    );
    const loading = await renderWorkspace();
    expect(text(loading.root)).toContain(
      "Loading a privacy-bounded setup page",
    );
    await act(async () => resolvePlan(canonicalPlan([])));
    expect(text(loading.root)).toContain("No groups match this page");

    harness.fetchPlan.mockReset().mockRejectedValue(new Error("offline"));
    const failed = await renderWorkspace();
    expect(text(failed.root)).toContain("The setup plan could not be loaded");
    expect(text(failed.root)).toContain("offline");
  });

  it("allows read-only preview while owner activation is pending but disables Apply", async () => {
    const renderer = await renderWorkspace();
    const checkbox = renderer.root.find(
      (node) =>
        node.type === "input" &&
        node.props.type === "checkbox" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => checkbox.props.onChange());
    const payer = renderer.root.find(
      (node) =>
        node.type === "select" &&
        String(node.props["aria-label"] || "").startsWith("Payer for"),
    );
    await act(async () =>
      payer.props.onChange({ currentTarget: { value: guardianId } }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(harness.previewWave).toHaveBeenCalledOnce();
    expect(text(renderer.root)).toContain(
      "Read-only preview created. No setup record has been changed.",
    );
    const attest = renderer.root.findAll(
      (node) =>
        node.type === "input" &&
        node.props.type === "checkbox" &&
        !node.props["aria-label"],
    )[0];
    await act(async () =>
      attest.props.onChange({ currentTarget: { checked: true } }),
    );
    expect(button(renderer, "Apply reviewed wave").props.disabled).toBe(true);
    expect(text(renderer.root)).toContain(
      "Owner activation or authoritative billing write readiness is still pending.",
    );
  });

  it("invalidates a stale preview and restarts from canonical records", async () => {
    harness.previewWave.mockRejectedValueOnce(
      new Error("The billing setup snapshot changed."),
    );
    const renderer = await renderWorkspace();
    const checkbox = renderer.root.find(
      (node) =>
        node.type === "input" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => checkbox.props.onChange());
    const payer = renderer.root.find(
      (node) =>
        node.type === "select" &&
        String(node.props["aria-label"] || "").startsWith("Payer for"),
    );
    await act(async () =>
      payer.props.onChange({ currentTarget: { value: guardianId } }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(text(renderer.root)).toContain(
      "The billing setup snapshot changed.",
    );
    expect(harness.fetchPlan.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("revalidates the exact snapshot before the first protected command", async () => {
    harness.capability.capability.writes_available = true;
    harness.capability.capability.manual_activation_required = false;
    harness.capability.capability.manual_activated = true;
    harness.fetchPlan.mockReset().mockResolvedValue(
      canonicalPlan([planGroup()], {
        apply_available: true,
        manual_activation_required: false,
      }),
    );
    harness.previewWave.mockResolvedValue(
      canonicalPreview([intent()], {
        apply_available: true,
        manual_activation_required: false,
      }),
    );
    const renderer = await renderWorkspace();
    const selectGroup = renderer.root.find(
      (node) =>
        node.type === "input" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => selectGroup.props.onChange());
    const payer = renderer.root.find(
      (node) =>
        node.type === "select" &&
        String(node.props["aria-label"] || "").startsWith("Payer for"),
    );
    await act(async () =>
      payer.props.onChange({ currentTarget: { value: guardianId } }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    const attest = renderer.root.findAll(
      (node) =>
        node.type === "input" &&
        node.props.type === "checkbox" &&
        !node.props["aria-label"],
    )[0];
    await act(async () =>
      attest.props.onChange({ currentTarget: { checked: true } }),
    );
    harness.fetchPlan.mockRejectedValueOnce(
      new Error("The billing readiness batch snapshot advanced."),
    );
    await act(async () =>
      button(renderer, "Apply reviewed wave").props.onClick(),
    );
    expect(harness.executeProtected).not.toHaveBeenCalled();
    expect(text(renderer.root)).toContain(
      "0/1 reviewed setup commands have confirmed receipts",
    );
    expect(text(renderer.root)).toContain(
      "billing readiness batch snapshot advanced",
    );
  });

  it("invalidates an approved preview when a relevant realtime fact changes", async () => {
    const renderer = await renderWorkspace();
    const selectGroup = renderer.root.find(
      (node) =>
        node.type === "input" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => selectGroup.props.onChange());
    const payer = renderer.root.find(
      (node) =>
        node.type === "select" &&
        String(node.props["aria-label"] || "").startsWith("Payer for"),
    );
    await act(async () =>
      payer.props.onChange({ currentTarget: { value: guardianId } }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(text(renderer.root)).toContain("Read-only");
    expect(harness.realtimeRefresh).not.toBeNull();
    await act(async () => harness.realtimeRefresh?.());
    expect(text(renderer.root)).toContain(
      "Canonical billing or enrollment facts changed",
    );
    expect(text(renderer.root)).toContain("Preview again");
  });

  it("routes every unresolved protected operation to canonical billing recovery", async () => {
    harness.readPending.mockReturnValue({
      version: 3,
      organization_id: organizationId,
      actor_id: actorId,
      client_operation_id: operationId,
      command_kind: "account.create",
      command_type: "account_open",
      target_scope: familyId,
      request_hash: "e".repeat(64),
      started_at: "2026-07-23T12:01:00Z",
    });
    harness.reconcileCommand.mockResolvedValue("not_found");
    const renderer = await renderWorkspace();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const recovery = renderer.root.find(
      (node) =>
        node.type === "a" && text(node).includes("Open billing recovery"),
    );
    expect(recovery.props.href).toBe("/billing?view=overview");
    expect(text(renderer.root)).toContain(
      "This redacted operation stays locked for explicit recovery",
    );
  });

  it("bounds a rate window to the plan date and rejects a bypassed future start", async () => {
    const rateGroup = planGroup(groupId, {
      wave: "rate_plan",
      readiness_status: "needs_rate",
      reason_codes: ["billing_rate_missing"],
      suggested_command_type: "rate_version_publish",
      family_id: null,
      family_name: null,
      facility_id: secondFamilyId,
      facility_name: "North Centre",
      program_id: secondChildId,
      program_name: "Daycare",
      program_type: "daycare",
      age_group: "preschool",
      affected_membership_digest: "2".repeat(64),
      payer_options: [],
      action_path: `/settings?facility=${secondFamilyId}`,
    });
    harness.fetchPlan.mockReset().mockResolvedValue(
      canonicalPlan([rateGroup], {
        counts: {
          total: 1,
          account_payer: 0,
          rate_plan: 1,
          agreement: 0,
          ready: 0,
          manual_review: 0,
        },
      }),
    );
    const renderer = await renderWorkspace();
    const checkbox = renderer.root.find(
      (node) =>
        node.type === "input" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => checkbox.props.onChange());
    const rateIdentity = renderer.root.findByProps({
      "aria-label": "Rate identity for North Centre · Daycare · preschool",
    });
    await act(async () =>
      rateIdentity.props.onChange({ currentTarget: { value: "new" } }),
    );
    const selects = renderer.root.findAllByType("select");
    const billingUnit = selects.find(
      (node) =>
        node.props["aria-label"] === undefined &&
        node.props.value === "",
    );
    expect(billingUnit).toBeDefined();
    await act(async () =>
      billingUnit?.props.onChange({
        currentTarget: { value: "monthly_period" },
      }),
    );
    const code = renderer.root.findByProps({ maxLength: 40 });
    const name = renderer.root.findByProps({ maxLength: 160 });
    const amount = renderer.root.findByProps({ placeholder: "0.00" });
    await act(async () =>
      code.props.onChange({ currentTarget: { value: "DAYCARE" } }),
    );
    await act(async () =>
      name.props.onChange({ currentTarget: { value: "Daycare rate" } }),
    );
    await act(async () =>
      amount.props.onChange({ currentTarget: { value: "125.00" } }),
    );
    const dates = renderer.root.findAll(
      (node) => node.type === "input" && node.props.type === "date",
    );
    expect(dates[0].props.max).toBe("2026-07-23");
    expect(dates[1].props.min).toBe("2026-07-23");
    await act(async () =>
      dates[0].props.onChange({
        currentTarget: { value: "2026-07-24" },
      }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(harness.previewWave).not.toHaveBeenCalled();
    expect(text(renderer.root)).toContain(
      "must begin no later than the current plan date 2026-07-23",
    );
  });

  it("derives agreement frequency, amount, and effective bounds from the canonical rate", async () => {
    const agreementGroup = planGroup(groupId, {
      wave: "agreement",
      readiness_status: "needs_agreement",
      reason_codes: ["billing_agreement_missing"],
      suggested_command_type: "agreement_establish",
      billing_account_id: secondFamilyId,
      facility_id: secondChildId,
      facility_name: "North Centre",
      program_id: secondGuardianId,
      program_name: "Daycare",
      program_type: "daycare",
      age_group: "preschool",
      rate_plan_id: secondOperationId,
      rate_plan_version_id: operationId,
      rate_billing_unit: "monthly_period",
      rate_unit_amount_minor: 12_500,
      rate_effective_from: "2026-01-01",
      rate_effective_until: "2026-12-31",
      agreement_effective_from_min: "2026-07-01",
      agreement_effective_until_max: "2026-12-31",
      agreement_effective_until_required: true,
      payer_options: [],
      action_path: `/billing?view=rates&account=${secondFamilyId}`,
    });
    harness.fetchPlan.mockReset().mockResolvedValue(
      canonicalPlan([agreementGroup], {
        counts: {
          total: 1,
          account_payer: 0,
          rate_plan: 0,
          agreement: 1,
          ready: 0,
          manual_review: 0,
        },
      }),
    );
    harness.previewWave.mockResolvedValue({
      ...canonicalPreview([]),
      wave: "agreement",
      intents: [],
      blocked: [
        {
          group_id: groupId,
          code: "test_review_block",
          message: "Review stopped for this test.",
        },
      ],
    });
    const renderer = await renderWorkspace();
    const checkbox = renderer.root.find(
      (node) =>
        node.type === "input" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => checkbox.props.onChange());
    const frequency = renderer.root.findByProps({
      "aria-label": "Derived billing frequency for Example Family",
    });
    const amount = renderer.root.findByProps({
      "aria-label": "Derived family amount for Example Family",
    });
    expect(frequency.props.readOnly).toBe(true);
    expect(frequency.props.value).toBe("Monthly");
    expect(amount.props.readOnly).toBe(true);
    expect(amount.props.value).toBe("125.00");
    const dateInputs = renderer.root.findAll(
      (node) => node.type === "input" && node.props.type === "date",
    );
    expect(dateInputs.map((input) => input.props.value)).toEqual([
      "2026-07-01",
      "2026-12-31",
    ]);
    expect(dateInputs[0].props.max).toBe("2026-07-23");
    expect(dateInputs[1].props.min).toBe("2026-07-23");
    await act(async () =>
      dateInputs[0].props.onChange({
        currentTarget: { value: "2026-07-24" },
      }),
    );
    expect(dateInputs[1].props.min).toBe("2026-07-24");
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(harness.previewWave).not.toHaveBeenCalled();
    expect(text(renderer.root)).toContain(
      "cannot start after the current plan date 2026-07-23",
    );
    await act(async () =>
      dateInputs[0].props.onChange({
        currentTarget: { value: "2026-07-01" },
      }),
    );
    await act(async () =>
      dateInputs[1].props.onChange({
        currentTarget: { value: "2026-07-10" },
      }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(harness.previewWave).not.toHaveBeenCalled();
    expect(text(renderer.root)).toContain(
      "must remain effective through the current plan date 2026-07-23",
    );
    await act(async () =>
      dateInputs[1].props.onChange({
        currentTarget: { value: "2026-12-31" },
      }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    expect(harness.previewWave.mock.calls[0][2]).toBe("agreement");
    expect(harness.previewWave.mock.calls[0][3][0]).toMatchObject({
      billing_frequency: "monthly",
      family_amount_minor_per_unit: 12_500,
      effective_from: "2026-07-01",
      effective_until: "2026-12-31",
    });
  });

  it("recovers a delayed exact receipt and refreshes the owning canonical plan", async () => {
    const events: string[] = [];
    const pending = {
      version: 3,
      organization_id: organizationId,
      actor_id: actorId,
      client_operation_id: operationId,
      command_kind: "account.create",
      command_type: "account_open",
      target_scope: familyId,
      request_hash: "e".repeat(64),
      started_at: "2026-07-23T12:01:00Z",
    };
    harness.readPending.mockReturnValue(pending);
    harness.fetchPlan.mockImplementation(async () => {
      events.push("fetch");
      return canonicalPlan();
    });
    harness.reconcileCommand.mockImplementation(async () => {
      events.push("reconcile");
      return {
        ...intent(),
        schema_version: "0033",
        organization_id: organizationId,
        billing_mode: "manual",
        sandbox: false,
        provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
        result_kind: "billing_account",
        result_id: familyId,
        committed_at: "2026-07-23T12:02:00Z",
        exact_retry: false,
        action_path: `/billing?view=accounts`,
      };
    });
    harness.clearPending.mockImplementation(() => {
      events.push("clear");
    });
    const renderer = await renderWorkspace();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(harness.clearPending).toHaveBeenCalledWith(pending);
    const clearIndex = events.indexOf("clear");
    expect(clearIndex).toBeGreaterThanOrEqual(0);
    expect(events.slice(clearIndex + 1)).toContain("fetch");
    expect(text(renderer.root)).toContain("A delayed exact receipt was recovered");
  });

  it("stops a partially completed wave after the first unconfirmed command", async () => {
    const events: string[] = [];
    harness.capability.capability.writes_available = true;
    harness.capability.capability.manual_activation_required = false;
    harness.capability.capability.manual_activated = true;
    const second = planGroup(secondGroupId, {
      family_id: secondFamilyId,
      family_name: "Second Family",
      affected_membership_digest: "1".repeat(64),
      affected_children: [
        {
          family_id: secondFamilyId,
          family_name: "Second Family",
          child_id: secondChildId,
          child_name: "Second Child",
          enrollment_id: null,
        },
      ],
      payer_options: [
        {
          guardian_id: secondGuardianId,
          display_name: "Second Guardian",
          is_primary: true,
        },
      ],
      action_path: `/families/${secondFamilyId}?section=billing`,
    });
    const writablePlan = canonicalPlan([planGroup(), second], {
      apply_available: true,
      manual_activation_required: false,
    });
    harness.fetchPlan.mockReset().mockImplementation(async () => {
      events.push("refresh");
      return writablePlan;
    });
    const secondIntent = intent(
      secondOperationId,
      secondGroupId,
      secondFamilyId,
      secondGuardianId,
      2,
    );
    harness.previewWave.mockImplementation(
      async (
        _organization: string,
        _snapshot: string,
        _wave: string,
        selections: Array<{ group_id: string }>,
      ) => {
        events.push("repreview");
        return canonicalPreview(
          selections.length === 2 ? [intent(), secondIntent] : [secondIntent],
          {
            apply_available: true,
            manual_activation_required: false,
          },
        );
      },
    );
    harness.executeProtected
      .mockImplementationOnce(async () => {
        events.push("execute-1");
        return {
          client_operation_id: operationId,
          request_hash: "e".repeat(64),
          command_type: "account_open",
        };
      })
      .mockImplementationOnce(async () => {
        events.push("execute-2");
        throw new Error("second command rejected");
      });
    const renderer = await renderWorkspace();
    const selectBoxes = renderer.root.findAll(
      (node) =>
        node.type === "input" &&
        node.props.type === "checkbox" &&
        String(node.props["aria-label"] || "").startsWith("Select"),
    );
    await act(async () => selectBoxes[0].props.onChange());
    await act(async () => selectBoxes[1].props.onChange());
    const payers = renderer.root.findAll(
      (node) =>
        node.type === "select" &&
        String(node.props["aria-label"] || "").startsWith("Payer for"),
    );
    await act(async () =>
      payers[0].props.onChange({ currentTarget: { value: guardianId } }),
    );
    await act(async () =>
      payers[1].props.onChange({ currentTarget: { value: secondGuardianId } }),
    );
    await act(async () => button(renderer, "Preview sequence").props.onClick());
    const attest = renderer.root.findAll(
      (node) =>
        node.type === "input" &&
        node.props.type === "checkbox" &&
        !node.props["aria-label"],
    )[0];
    await act(async () =>
      attest.props.onChange({ currentTarget: { checked: true } }),
    );
    events.length = 0;
    await act(async () =>
      button(renderer, "Apply reviewed wave").props.onClick(),
    );
    expect(harness.executeProtected).toHaveBeenCalledTimes(2);
    expect(events.slice(0, 5)).toEqual([
      "refresh",
      "execute-1",
      "refresh",
      "repreview",
      "execute-2",
    ]);
    expect(text(renderer.root)).toContain(
      "1/2 reviewed setup commands have confirmed receipts",
    );
    expect(text(renderer.root)).toContain("second command rejected");
  });
});

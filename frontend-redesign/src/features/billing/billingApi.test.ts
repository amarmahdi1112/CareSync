import { describe, expect, it } from "vitest";
import {
  BillingApiError,
  parseBillingAccountDetail,
  parseBillingCapability,
  parseBillingCommandPreparation,
  parseBillingCommandReceipt,
  parseBillingInvoice,
  parseBillingManualActivation,
  parseBillingWorkspacePage,
  assembleBillingWorkspacePages,
  parseBillingWorkspace,
  parseFamilyBillingOptions,
} from "./billingApi";
import { billingPreparePayload } from "./billingIntent";

const organizationId = "11111111-1111-4111-8111-111111111111";
const familyId = "22222222-2222-4222-8222-222222222222";
const accountId = "33333333-3333-4333-8333-333333333333";
const guardianId = "44444444-4444-4444-8444-444444444444";
const payerVersionId = "55555555-5555-4555-8555-555555555555";
const childId = "66666666-6666-4666-8666-666666666666";
const enrollmentId = "77777777-7777-4777-8777-777777777777";
const facilityId = "88888888-8888-4888-8888-888888888888";
const programId = "99999999-9999-4999-8999-999999999999";
const rateId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const rateVersionId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const agreementId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const agreementVersionId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const invoiceId = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const lineId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const paymentId = "12121212-1212-4212-8212-121212121212";
const operationId = "13131313-1313-4313-8313-131313131313";
const allocationId = "14141414-1414-4414-8414-141414141414";
const creditId = "15151515-1515-4515-8515-151515151515";
const creditOperationId = "16161616-1616-4616-8616-161616161616";
const actorId = "17171717-1717-4717-8717-171717171717";
const allocationId2 = "18181818-1818-4818-8818-181818181818";
const operationId2 = "19191919-1919-4919-8919-191919191919";
const historicalPayerVersionId = "20202020-2020-4020-8020-202020202020";
const successorGuardianId = "21212121-2121-4121-8121-212121212121";
const hash = "a".repeat(64);
const snapshotToken = "b".repeat(64);
const at = "2026-07-22T18:30:00Z";

function invoice() {
  return {
    billing_mode: "sandbox",
    sandbox: true,
    provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    document_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    organization_id: organizationId,
    id: invoiceId,
    billing_account_id: accountId,
    family_id: familyId,
    billing_account_payer_version_id: payerVersionId,
    payer_guardian_id: guardianId,
    invoice_number: "TEST-INV-202607-ABC",
    lifecycle_status: "open",
    currency: "CAD",
    issue_date: "2026-07-22",
    due_date: "2026-08-05",
    service_period_start: "2026-07-01",
    service_period_end: "2026-07-31",
    family_name: "Example family",
    payer_name: "Example Guardian",
    payer_email: "guardian@example.test",
    payer_address: null,
    gross_subtotal_minor: 10_000,
    funding_minor: 0,
    subtotal_minor: 10_000,
    tax_minor: 0,
    total_minor: 10_000,
    allocated_minor: 2_000,
    credits_minor: 1_000,
    outstanding_minor: 7_000,
    issued_at: at,
    lines: [
      {
        organization_id: organizationId,
        id: lineId,
        agreement_version_id: agreementVersionId,
        child_id: childId,
        line_number: 1,
        description: "Monthly care",
        child_name: "Example Child",
        rate_plan_name: "Monthly care",
        billing_unit: "monthly_period",
        service_period_start: "2026-07-01",
        service_period_end: "2026-07-31",
        quantity: 1,
        gross_unit_amount_minor: 10_000,
        funding_unit_amount_minor: 0,
        unit_amount_minor: 10_000,
        tax_rate_basis_points: 0,
        gross_subtotal_minor: 10_000,
        funding_minor: 0,
        subtotal_minor: 10_000,
        tax_minor: 0,
        total_minor: 10_000,
      },
    ],
  };
}

function workspace() {
  const account = {
    organization_id: organizationId,
    id: accountId,
    family_id: familyId,
    payer_guardian_id: guardianId,
    latest_payer_version_id: payerVersionId,
    latest_payer_version_number: 1,
    family_name: "Example family",
    account_number: "TEST-BA-ABC",
    status: "open",
    currency: "CAD",
    opened_at: at,
    invoiced_minor: 10_000,
    allocated_minor: 2_000,
    credits_minor: 1_000,
    outstanding_minor: 7_000,
    unapplied_minor: 1_000,
  };
  const rateVersion = {
    organization_id: organizationId,
    id: rateVersionId,
    rate_plan_id: rateId,
    version_number: 1,
    status: "published",
    billing_unit: "monthly_period",
    unit_amount_minor: 10_000,
    tax_rate_basis_points: 0,
    currency: "CAD",
    effective_from: "2026-01-01",
    effective_until: null,
    description: null,
    published_at: at,
  };
  const agreementVersion = {
    organization_id: organizationId,
    id: agreementVersionId,
    agreement_id: agreementId,
    rate_plan_version_id: rateVersionId,
    version_number: 1,
    billing_frequency: "monthly",
    family_amount_minor_per_unit: 10_000,
    funding_amount_minor_per_unit: 0,
    effective_from: "2026-01-01",
    effective_until: null,
    review_status: "reviewed",
    reviewed_at: at,
  };
  return {
    schema_version: "0033",
    organization_id: organizationId,
    billing_mode: "sandbox",
    sandbox: true,
    provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    complete: true,
    canonical_collection_limit: 500,
    generated_at: at,
    data_through_realtime_sequence: 42,
    overview: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      as_of: at,
      account_count: 1,
      open_account_count: 1,
      issued_invoice_count: 1,
      outstanding_minor: 7_000,
      settled_payments_minor: 3_000,
      unapplied_payments_minor: 1_000,
      credits_minor: 1_000,
    },
    accounts: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [account],
      total: 1,
    },
    payer_versions: {
      schema_version: "0033",
      organization_id: organizationId,
      items: [
        {
          organization_id: organizationId,
          id: payerVersionId,
          billing_account_id: accountId,
          family_id: familyId,
          payer_guardian_id: guardianId,
          version_number: 1,
          assigned_by_user_id: actorId,
          assigned_at: at,
        },
      ],
      total: 1,
    },
    invoices: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [invoice()],
      total: 1,
    },
    payments: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [
        {
          billing_mode: "sandbox",
          sandbox: true,
          provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
          organization_id: organizationId,
          id: paymentId,
          billing_account_id: accountId,
          family_id: familyId,
          payer_guardian_id: guardianId,
          payer_name: "Example Guardian",
          payer_email: "guardian@example.test",
          lifecycle_status: "partially_allocated",
          method: "e_transfer",
          currency: "CAD",
          amount_minor: 3_000,
          allocated_minor: 2_000,
          unapplied_minor: 1_000,
          external_reference: "BANK-ABC",
          memo: null,
          operator_confirmation_note: null,
          received_at: at,
          recorded_at: at,
        },
      ],
      total: 1,
    },
    rate_plans: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [
        {
          organization_id: organizationId,
          id: rateId,
          code: "MONTHLY",
          name: "Monthly care",
          program_type: "daycare",
          charge_kind: "core_care",
          age_group: null,
          facility_id: facilityId,
          program_id: programId,
          created_at: at,
          latest_version: rateVersion,
          versions: [rateVersion],
        },
      ],
      total: 1,
    },
    agreements: {
      schema_version: "0033",
      organization_id: organizationId,
      items: [
        {
          organization_id: organizationId,
          id: agreementId,
          billing_account_id: accountId,
          family_id: familyId,
          child_id: childId,
          child_name: "Example Child",
          enrollment_id: enrollmentId,
          facility_id: facilityId,
          created_at: at,
          latest_version: agreementVersion,
          versions: [agreementVersion],
        },
      ],
      total: 1,
    },
    allocations: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [
        {
          organization_id: organizationId,
          id: allocationId,
          billing_account_id: accountId,
          payment_id: paymentId,
          invoice_id: invoiceId,
          amount_minor: 2_000,
          allocated_by_user_id: actorId,
          allocated_at: at,
          client_operation_id: operationId,
          request_hash: hash,
        },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    },
    credits: {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      items: [
        {
          organization_id: organizationId,
          id: creditId,
          billing_account_id: accountId,
          invoice_id: invoiceId,
          status: "issued",
          currency: "CAD",
          amount_minor: 1_000,
          reason_code: "billing_correction",
          note: "Synthetic correction",
          issued_by_user_id: actorId,
          issued_at: at,
          client_operation_id: creditOperationId,
          request_hash: hash,
        },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    },
    paging: {
      snapshot_token: snapshotToken,
      accounts: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      payer_versions: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      invoices: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      payments: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      rate_plans: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      agreements: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      allocations: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
      credits: {
        offset: 0,
        limit: 500,
        returned: 1,
        total: 1,
        has_more: false,
        next_offset: null,
      },
    },
  };
}

function twoWorkspacePages() {
  const first = structuredClone(workspace());
  first.complete = false;
  first.canonical_collection_limit = 1;
  for (const proof of Object.values(first.paging).filter(
    (value): value is (typeof first.paging)["accounts"] =>
      typeof value === "object",
  ))
    proof.limit = 1;
  first.allocations.items[0].amount_minor = 1_000;
  first.allocations.total = 2;
  first.allocations.limit = 1;
  first.credits.limit = 1;
  first.paging.allocations = {
    offset: 0,
    limit: 1,
    returned: 1,
    total: 2,
    has_more: true,
    next_offset: 1 as never,
  };

  const second = structuredClone(first);
  second.generated_at = "2026-07-22T18:31:00Z";
  second.overview.as_of = "2026-07-22T18:31:00Z";
  const collectionNames = [
    "accounts",
    "payer_versions",
    "invoices",
    "payments",
    "rate_plans",
    "agreements",
    "credits",
  ] as const;
  for (const name of collectionNames) {
    second[name].items = [] as never;
    second.paging[name] = {
      offset: 1,
      limit: 1,
      returned: 0,
      total: 1,
      has_more: false,
      next_offset: null,
    };
  }
  second.allocations.items = [
    {
      ...first.allocations.items[0],
      id: allocationId2,
      amount_minor: 1_000,
      client_operation_id: operationId2,
      request_hash: "c".repeat(64),
    },
  ];
  second.allocations.offset = 1;
  second.credits.offset = 1;
  second.paging.allocations = {
    offset: 1,
    limit: 1,
    returned: 1,
    total: 2,
    has_more: false,
    next_offset: null,
  };
  return [first, second] as const;
}

describe("strict coherent billing projection", () => {
  it("accepts one complete, organization-bound financial snapshot", () => {
    const result = parseBillingWorkspace(workspace(), organizationId);
    expect(result.complete).toBe(true);
    expect(result.data_through_realtime_sequence).toBe(42);
    expect(result.accounts.items[0].latest_payer_version_number).toBe(1);
    expect(result.payer_versions.items[0].id).toBe(payerVersionId);
    expect(result.invoices.items[0].billing_account_payer_version_id).toBe(
      payerVersionId,
    );
    expect(result.invoices.items[0].outstanding_minor).toBe(7_000);
  });

  it("accepts the same coherent ledger under the private manual provenance boundary", () => {
    const manual = workspace();
    manual.billing_mode = "manual";
    manual.sandbox = false;
    manual.provenance_label = "PRIVATE/MANUAL — OFF-PLATFORM RECORD";
    Object.assign(manual.invoices.items[0], {
      billing_mode: "manual",
      sandbox: false,
      provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
      document_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    });
    Object.assign(manual.payments.items[0], {
      billing_mode: "manual",
      sandbox: false,
      provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    });
    const result = parseBillingWorkspace(manual, organizationId);
    expect(result).toMatchObject({
      billing_mode: "manual",
      sandbox: false,
      provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    });
    expect(result.invoices.items[0].document_label).toBe(
      "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    );
  });

  it("rejects incomplete collections and cross-organization records", () => {
    const incomplete = workspace();
    incomplete.accounts.total = 2;
    expect(() => parseBillingWorkspace(incomplete, organizationId)).toThrow(
      /accounts page proof/i,
    );
    const crossed = workspace();
    crossed.invoices.items[0].organization_id =
      "14141414-1414-4414-8414-141414141414";
    expect(() => parseBillingWorkspace(crossed, organizationId)).toThrow(
      /organization boundary/i,
    );
  });

  it("rejects duplicate records, limit drift, and unreconciled overview totals", () => {
    const duplicate = workspace();
    duplicate.accounts.items.push({ ...duplicate.accounts.items[0] });
    duplicate.accounts.total = 2;
    expect(() => parseBillingWorkspace(duplicate, organizationId)).toThrow(
      /unique record proof/i,
    );

    const overLimit = workspace();
    overLimit.canonical_collection_limit = 0;
    expect(() => parseBillingWorkspace(overLimit, organizationId)).toThrow(
      /collection limit/i,
    );

    const drifted = workspace();
    drifted.overview.unapplied_payments_minor = 499;
    expect(() => parseBillingWorkspace(drifted, organizationId)).toThrow(
      /overview reconciliation proof/i,
    );
  });

  it("rejects inconsistent invoice line, header, and settlement arithmetic", () => {
    const badLine = invoice();
    badLine.lines[0].total_minor = 9_999;
    expect(() => parseBillingInvoice(badLine, organizationId)).toThrow(
      /line amount reconciliation/i,
    );
    const badHeader = invoice();
    badHeader.outstanding_minor = 7_001;
    expect(() => parseBillingInvoice(badHeader, organizationId)).toThrow(
      /amount reconciliation/i,
    );
  });

  it("requires exact immutable payer provenance on every invoice", () => {
    const parsed = parseBillingInvoice(invoice(), organizationId);
    expect(parsed.billing_account_payer_version_id).toBe(payerVersionId);
    expect(parsed.payer_guardian_id).toBe(guardianId);

    const missingVersion = invoice();
    delete (missingVersion as Partial<typeof missingVersion>)
      .billing_account_payer_version_id;
    expect(() => parseBillingInvoice(missingVersion, organizationId)).toThrow(
      /invoice payer version id/i,
    );

    const malformedGuardian = invoice();
    malformedGuardian.payer_guardian_id = "not-a-guardian-id";
    expect(() =>
      parseBillingInvoice(malformedGuardian, organizationId),
    ).toThrow(/invoice payer guardian id/i);
  });

  it("requires a durable reference on every settled payment projection", () => {
    const missingReference = workspace();
    missingReference.payments.items[0].external_reference = null as never;
    expect(() =>
      parseBillingWorkspace(missingReference, organizationId),
    ).toThrow(/payment external reference/i);
  });

  it("binds account detail invoices to the complete payer history", () => {
    const source = workspace();
    const detail = {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      account: source.accounts.items[0],
      payer_versions: source.payer_versions.items,
      invoices: source.invoices.items,
      payments: source.payments.items,
      agreements: source.agreements.items,
    };
    expect(
      parseBillingAccountDetail(detail, accountId, organizationId)
        .payer_versions[0].payer_guardian_id,
    ).toBe(guardianId);

    const crossed = structuredClone(detail);
    crossed.invoices[0].payer_guardian_id = successorGuardianId;
    expect(() =>
      parseBillingAccountDetail(crossed, accountId, organizationId),
    ).toThrow(/selected account boundary/i);
  });

  it("rejects cross-account facts and broken immutable version chains", () => {
    const crossedInvoice = workspace();
    crossedInvoice.invoices.items[0].family_id =
      "14141414-1414-4414-8414-141414141414";
    expect(() =>
      parseBillingWorkspace(crossedInvoice, organizationId),
    ).toThrow(/invoice account ownership proof/i);

    const ghostAgreementVersion = workspace();
    ghostAgreementVersion.invoices.items[0].lines[0].agreement_version_id =
      "15151515-1515-4515-8515-151515151515";
    expect(() =>
      parseBillingWorkspace(ghostAgreementVersion, organizationId),
    ).toThrow(/invoice line ownership proof/i);

    const staleLatest = workspace();
    staleLatest.rate_plans.items[0].latest_version = {
      ...staleLatest.rate_plans.items[0].latest_version,
      id: "16161616-1616-4616-8616-161616161616",
    };
    expect(() => parseBillingWorkspace(staleLatest, organizationId)).toThrow(
      /rate plan version chain proof/i,
    );

    const contradictoryLatest = workspace();
    contradictoryLatest.rate_plans.items[0].latest_version = {
      ...contradictoryLatest.rate_plans.items[0].latest_version,
      unit_amount_minor: 10_001,
    };
    expect(() =>
      parseBillingWorkspace(contradictoryLatest, organizationId),
    ).toThrow(/rate plan version chain proof/i);

    const accountDrift = workspace();
    accountDrift.accounts.items[0].unapplied_minor = 999;
    expect(() => parseBillingWorkspace(accountDrift, organizationId)).toThrow(
      /per-account reconciliation proof/i,
    );
  });

  it("proves historical invoice payer ownership without forcing the latest payer", () => {
    const historical = workspace();
    historical.payer_versions.items[0].id = historicalPayerVersionId;
    historical.invoices.items[0].billing_account_payer_version_id =
      historicalPayerVersionId;
    historical.payer_versions.items.push({
      ...historical.payer_versions.items[0],
      id: payerVersionId,
      payer_guardian_id: successorGuardianId,
      version_number: 2,
      assigned_at: "2026-07-22T19:30:00Z",
    });
    historical.payer_versions.total = 2;
    historical.paging.payer_versions.returned = 2;
    historical.paging.payer_versions.total = 2;
    historical.accounts.items[0].payer_guardian_id = successorGuardianId;
    historical.accounts.items[0].latest_payer_version_number = 2;

    const result = parseBillingWorkspace(historical, organizationId);
    expect(result.invoices.items[0].billing_account_payer_version_id).toBe(
      historicalPayerVersionId,
    );
    expect(result.accounts.items[0].latest_payer_version_id).toBe(
      payerVersionId,
    );
  });

  it("rejects payer-version ownership, latest-pointer, and invoice-guardian drift", () => {
    const crossedVersion = workspace();
    crossedVersion.payer_versions.items[0].billing_account_id =
      "23232323-2323-4323-8323-232323232323";
    expect(() => parseBillingWorkspace(crossedVersion, organizationId)).toThrow(
      /payer version ownership proof/i,
    );

    const staleLatest = workspace();
    staleLatest.accounts.items[0].latest_payer_version_number = 2;
    expect(() => parseBillingWorkspace(staleLatest, organizationId)).toThrow(
      /latest payer version proof/i,
    );

    const gappedChain = workspace();
    gappedChain.payer_versions.items[0].version_number = 2;
    gappedChain.accounts.items[0].latest_payer_version_number = 2;
    expect(() => parseBillingWorkspace(gappedChain, organizationId)).toThrow(
      /payer version chain proof/i,
    );

    const guardianDrift = workspace();
    guardianDrift.invoices.items[0].payer_guardian_id = successorGuardianId;
    expect(() => parseBillingWorkspace(guardianDrift, organizationId)).toThrow(
      /invoice account ownership proof/i,
    );
  });
});

describe("adversarial canonical billing paging", () => {
  it("assembles every collection only after all pages prove one snapshot", () => {
    const [first, second] = twoWorkspacePages();
    const result = assembleBillingWorkspacePages(
      [
        parseBillingWorkspacePage(first, organizationId),
        parseBillingWorkspacePage(second, organizationId),
      ],
      organizationId,
    );
    expect(result.complete).toBe(true);
    expect(result.snapshot_token).toBe(snapshotToken);
    expect(result.allocations.items).toHaveLength(2);
    expect(result.allocations.items.map((item) => item.amount_minor)).toEqual([
      1_000, 1_000,
    ]);
  });

  it("rejects token, sequence, count, and overview drift across pages", () => {
    const parsed = () => {
      const [first, second] = twoWorkspacePages();
      return [
        parseBillingWorkspacePage(first, organizationId),
        parseBillingWorkspacePage(second, organizationId),
      ] as const;
    };
    const tokenDrift = parsed();
    tokenDrift[1].paging.snapshot_token = "d".repeat(64);
    expect(() =>
      assembleBillingWorkspacePages(tokenDrift, organizationId),
    ).toThrow(/snapshot drift proof/i);

    const sequenceDrift = parsed();
    sequenceDrift[1].data_through_realtime_sequence += 1;
    expect(() =>
      assembleBillingWorkspacePages(sequenceDrift, organizationId),
    ).toThrow(/snapshot drift proof/i);

    const countDrift = parsed();
    countDrift[1].paging.allocations.total += 1;
    countDrift[1].allocations.total += 1;
    expect(() =>
      assembleBillingWorkspacePages(countDrift, organizationId),
    ).toThrow(/allocations page sequence/i);

    const overviewDrift = parsed();
    overviewDrift[1].overview.outstanding_minor = 7_001 as never;
    expect(() =>
      assembleBillingWorkspacePages(overviewDrift, organizationId),
    ).toThrow(/snapshot drift proof/i);
  });

  it("rejects overlap, duplicates, malformed next offsets, and tenant crossing", () => {
    const [firstRaw, secondRaw] = twoWorkspacePages();
    const malformed = structuredClone(firstRaw);
    malformed.paging.allocations.next_offset = 2 as never;
    expect(() =>
      parseBillingWorkspacePage(malformed, organizationId),
    ).toThrow(/allocations paging proof/i);

    const crossed = structuredClone(firstRaw);
    crossed.allocations.items[0].organization_id =
      "20202020-2020-4020-8020-202020202020";
    expect(() => parseBillingWorkspacePage(crossed, organizationId)).toThrow(
      /organization boundary/i,
    );

    const first = parseBillingWorkspacePage(firstRaw, organizationId);
    const overlap = parseBillingWorkspacePage(secondRaw, organizationId);
    overlap.paging.allocations.offset = 0;
    expect(() =>
      assembleBillingWorkspacePages([first, overlap], organizationId),
    ).toThrow(/allocations page sequence/i);

    const duplicate = parseBillingWorkspacePage(secondRaw, organizationId);
    duplicate.allocations.items[0].id = first.allocations.items[0].id;
    expect(() =>
      assembleBillingWorkspacePages([first, duplicate], organizationId),
    ).toThrow(/duplicate or overlap proof/i);
  });

  it("rejects effect ownership and amount projection drift", () => {
    const crossed = workspace();
    crossed.allocations.items[0].payment_id =
      "21212121-2121-4121-8121-212121212121";
    expect(() => parseBillingWorkspace(crossed, organizationId)).toThrow(
      /allocation ownership proof/i,
    );

    const drifted = workspace();
    drifted.credits.items[0].amount_minor = 999;
    expect(() => parseBillingWorkspace(drifted, organizationId)).toThrow(
      /invoice effect reconciliation proof/i,
    );
  });
});

describe("billing command and source boundaries", () => {
  it("requires authoritative write readiness and rejects impossible capability states", () => {
    const capability = (overrides: Record<string, unknown> = {}) => ({
      schema_version: "0033",
      organization_id: organizationId,
      sandbox: true,
      provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
      runtime_available: true,
      billing_mode: "sandbox",
      manual_activation_required: false,
      manual_activated: false,
      writes_available: true,
      currency: "CAD",
      organization_timezone: "America/Edmonton",
      organization_local_date: "2026-07-22",
      server_time: at,
      processor_enabled: false,
      money_movement_enabled: false,
      automatic_issue_enabled: false,
      tax_advice_enabled: false,
      off_platform_payment_methods: [
        "cash",
        "cheque",
        "e_transfer",
        "other",
      ],
      reason_code: null,
      ...overrides,
    });
    expect(
      parseBillingCapability(capability(), organizationId).writes_available,
    ).toBe(true);
    expect(
      parseBillingCapability(
        capability({ billing_mode: "shadow", writes_available: false }),
        organizationId,
      ).writes_available,
    ).toBe(false);
    expect(() =>
      parseBillingCapability(
        capability({ billing_mode: "shadow", writes_available: true }),
        organizationId,
      ),
    ).toThrow(/write-readiness consistency proof/i);
    expect(() =>
      parseBillingCapability(
        capability({ runtime_available: false, writes_available: true }),
        organizationId,
      ),
    ).toThrow(/write-readiness consistency proof/i);
    const missing: Record<string, unknown> = capability();
    delete missing.writes_available;
    expect(() => parseBillingCapability(missing, organizationId)).toThrow(
      /write-readiness flag/i,
    );
    const manual = parseBillingCapability(
      capability({
        billing_mode: "manual",
        sandbox: false,
        provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
        manual_activation_required: false,
        manual_activated: true,
      }),
      organizationId,
    );
    expect(manual).toMatchObject({
      billing_mode: "manual",
      sandbox: false,
      manual_activated: true,
      writes_available: true,
    });
    expect(() =>
      parseBillingCapability(
        capability({
          billing_mode: "manual",
          sandbox: false,
          provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
          manual_activation_required: true,
          manual_activated: false,
          writes_available: true,
        }),
        organizationId,
      ),
    ).toThrow(/write-readiness consistency proof/i);
  });

  it("parses an immutable owner-reviewed manual activation and rejects boundary drift", () => {
    const raw = {
      schema_version: "0036",
      organization_id: organizationId,
      billing_mode: "manual",
      server_attested: true,
      organization_allowlisted: true,
      activated: true,
      activation_policy_version: "private_local_manual_billing_v1",
      activated_by_user_id: actorId,
      activated_at: at,
      immutable: true,
      processor_enabled: false,
      money_movement_enabled: false,
      automatic_issue_enabled: false,
      delivery_enabled: false,
      tax_advice_enabled: false,
    };
    expect(
      parseBillingManualActivation(raw, organizationId),
    ).toMatchObject({
      activated: true,
      immutable: true,
      money_movement_enabled: false,
      delivery_enabled: false,
    });
    expect(() =>
      parseBillingManualActivation(
        { ...raw, money_movement_enabled: true },
        organizationId,
      ),
    ).toThrow(/money-movement boundary/i);
    expect(() =>
      parseBillingManualActivation(
        {
          ...raw,
          activated: false,
          activation_policy_version: null,
          activated_by_user_id: actorId,
          activated_at: null,
        },
        organizationId,
      ),
    ).toThrow(/lifecycle proof/i);
  });

  it("prepares the exact typed payload without dropping payer concurrency pins", () => {
    const input = {
      account_id: accountId,
      payer_guardian_id: guardianId,
      expected_latest_payer_version_id: payerVersionId,
      expected_latest_payer_version_number: 1,
    };
    expect(
      billingPreparePayload("account.payer.assign", operationId, input),
    ).toEqual({
      command_type: "account_payer_assign",
      request_payload: { client_operation_id: operationId, ...input },
    });
  });

  it("binds server preparation and receipt proofs to the exact operation", () => {
    expect(
      parseBillingCommandPreparation(
        {
          schema_version: "0033",
          organization_id: organizationId,
          billing_mode: "sandbox",
          sandbox: true,
          provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
          client_operation_id: operationId,
          command_type: "payment_record",
          target_scope: accountId,
          request_hash: hash,
          prepared_at: at,
          exact_retry: false,
        },
        organizationId,
        operationId,
        "payment.record",
      ).request_hash,
    ).toBe(hash);
    expect(() =>
      parseBillingCommandReceipt(
        {
          schema_version: "0033",
          organization_id: organizationId,
          billing_mode: "sandbox",
          sandbox: true,
          provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
          client_operation_id: operationId,
          command_type: "payment_record",
          request_hash: "b".repeat(64),
          result_kind: "billing_payment",
          result_id: paymentId,
          committed_at: at,
          exact_retry: true,
          action_path: `/billing?focus=billing_payment&record=${paymentId}`,
        },
        organizationId,
        operationId,
        "payment.record",
        hash,
      ),
    ).toThrow(BillingApiError);
  });

  it("parses canonical payer, child placement, and program choices", () => {
    const result = parseFamilyBillingOptions(
      {
        schema_version: "0033",
        organization_id: organizationId,
        items: [
          {
            organization_id: organizationId,
            id: familyId,
            name: "Example family",
            status: "active",
            guardians: [
              {
                organization_id: organizationId,
                id: guardianId,
                family_id: familyId,
                first_name: "Example",
                last_name: "Guardian",
                email: "guardian@example.test",
                cell_phone: "",
              },
            ],
            children: [
              {
                organization_id: organizationId,
                id: childId,
                family_id: familyId,
                first_name: "Example",
                last_name: "Child",
                age_group: "preschool",
                enrollment_id: enrollmentId,
                facility_id: facilityId,
                program_id: programId,
                program_type: "daycare",
              },
            ],
          },
        ],
        programs: [
          {
            organization_id: organizationId,
            facility_id: facilityId,
            facility_name: "Example centre",
            program_id: programId,
            program_name: "Daycare",
            program_type: "daycare",
            minimum_age_months: 19,
            maximum_age_months: 72,
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      },
      organizationId,
    );
    expect(result.items[0].guardians[0].name).toBe("Example Guardian");
    expect(result.items[0].children[0].program_id).toBe(programId);
    expect(result.programs[0].facility_name).toBe("Example centre");
  });

  it("accepts a guardian with one real name component without inventing a surname", () => {
    const source = {
      schema_version: "0033",
      organization_id: organizationId,
      items: [
        {
          organization_id: organizationId,
          id: familyId,
          name: "Single-name family",
          status: "active",
          guardians: [
            {
              organization_id: organizationId,
              id: guardianId,
              family_id: familyId,
              first_name: "  Hidaya  ",
              last_name: "   ",
              email: "hidaya@example.test",
              cell_phone: "",
            },
          ],
          children: [],
        },
      ],
      programs: [],
      total: 1,
      limit: 100,
      offset: 0,
    };
    const parsed = parseFamilyBillingOptions(source, organizationId);
    expect(parsed.items[0].guardians[0].name).toBe("Hidaya");
  });

  it("rejects a guardian whose complete name is blank", () => {
    const source = {
      schema_version: "0033",
      organization_id: organizationId,
      items: [
        {
          organization_id: organizationId,
          id: familyId,
          name: "Unnamed family",
          status: "active",
          guardians: [
            {
              organization_id: organizationId,
              id: guardianId,
              family_id: familyId,
              first_name: " ",
              last_name: "\t",
              email: "unknown@example.test",
              cell_phone: "",
            },
          ],
          children: [],
        },
      ],
      programs: [],
      total: 1,
      limit: 100,
      offset: 0,
    };
    expect(() => parseFamilyBillingOptions(source, organizationId)).toThrow(
      /guardian name/i,
    );
  });
});

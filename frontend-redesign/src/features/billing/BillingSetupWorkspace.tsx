import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClipboardDocumentCheckIcon,
  ExclamationTriangleIcon,
  LinkIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  QueueListIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import { ACCESS, hasExplicitPermission } from "../../auth/accessModel";
import { useSession } from "../../auth/SessionContext";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  StatusChip,
} from "../../components/ui/Primitives";
import { useRealtimeRefresh } from "../../realtime/RealtimeContext";
import { featureIntegrationManifest } from "../../realtime/featureIntegrationManifest";
import { billingApi } from "./billingApi";
import {
  BILLING_BATCH_ACTIONABLE_WAVES,
  BILLING_BATCH_WAVES,
  fetchBillingBatchPlan,
  previewBillingBatchWave,
  type BillingBatchActionableWave,
  type BillingBatchPlan,
  type BillingBatchPlanGroup,
  type BillingBatchPreview,
  type BillingBatchPreviewIntent,
  type BillingBatchPreviewSelection,
  type BillingBatchWave,
  type BillingBatchWaveFilter,
} from "./billingBatchPlanApi";
import { useBillingCapability } from "./billingCapability";
import { billingErrorMessage } from "./billingErrorPresentation";
import {
  BillingOperationLockedError,
  BillingOperationOutcomeUnknownError,
  clearPendingBillingOperation,
  executeProtectedBillingCommand,
  readPendingBillingOperation,
  readVolatileBillingOperationInput,
  type PendingBillingOperation,
} from "./billingOperation";
import {
  BILLING_READINESS_STATUSES,
  type BillingReadinessStatus,
} from "./billingReadinessApi";
import {
  formatDateTime,
  isDateOnly,
  parseMoneyInput,
  titleCase,
} from "./billingModel";
import type {
  AssignBillingAccountPayerInput,
  BillingCommandReceipt,
  BillingFrequency,
  BillingUnit,
  CreateAgreementInput,
  CreateBillingAccountInput,
  CreateRatePlanInput,
} from "./types";

const PAGE_SIZE = 25;
const MAX_SELECTED_GROUPS = 25;

const Page = styled.section`
  display: grid;
  gap: 16px;
  padding: clamp(16px, 2.2vw, 30px);
  color: ${({ theme }) => theme.color.text};
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  h1 {
    margin: 8px 0 6px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.35rem, 2.3vw, 1.92rem);
    font-weight: 540;
    letter-spacing: -0.04em;
  }
  p {
    max-width: 780px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.76rem;
    line-height: 1.62;
  }
  @media (max-width: 740px) {
    flex-direction: column;
  }
`;

const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  @media (max-width: 740px) {
    justify-content: flex-start;
  }
`;

const BillingNav = styled.nav`
  display: flex;
  gap: 5px;
  padding: 7px;
  overflow-x: auto;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px 6px 14px 6px;
  background: ${({ theme }) => theme.color.surface};
  scrollbar-width: thin;
`;

const BillingNavLink = styled(Link)<{ $active?: boolean }>`
  display: inline-flex;
  min-height: 39px;
  flex: 0 0 auto;
  align-items: center;
  padding: 0 13px;
  border: 1px solid
    ${({ $active, theme }) => ($active ? theme.color.cyan : "transparent")};
  border-radius: 9px 4px 9px 4px;
  color: ${({ $active, theme }) =>
    $active ? theme.color.text : theme.color.textMuted};
  background: ${({ $active, theme }) =>
    $active ? theme.color.control : "transparent"};
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 2px;
  }
`;

const Boundary = styled(GlassPanel)`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  padding: 14px 16px;
  > svg {
    width: 23px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 0 0 4px;
    font-size: 0.82rem;
    font-weight: 620;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.69rem;
    line-height: 1.55;
  }
  @media (max-width: 720px) {
    grid-template-columns: auto minmax(0, 1fr);
    > span {
      grid-column: 1 / -1;
      justify-self: start;
    }
  }
`;

const WaveRail = styled.ol`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  @media (max-width: 920px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;

const WaveCard = styled(GlassPanel)<{ $active?: boolean }>`
  display: grid;
  min-height: 112px;
  align-content: space-between;
  gap: 12px;
  padding: 15px;
  border-color: ${({ $active, theme }) =>
    $active ? theme.color.cyan : theme.color.border};
  button {
    display: grid;
    gap: 7px;
    width: 100%;
    padding: 0;
    border: 0;
    color: inherit;
    background: transparent;
    cursor: pointer;
    text-align: left;
  }
  strong {
    font-size: 0.77rem;
    font-weight: 620;
  }
  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    line-height: 1.45;
  }
  b {
    color: ${({ theme }) => theme.color.cyan};
    font-family: "CareSync Display", sans-serif;
    font-size: 1.26rem;
    font-weight: 520;
  }
`;

const Filters = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(210px, 1fr) minmax(150px, 0.3fr) minmax(
      170px,
      0.35fr
    ) auto;
  align-items: end;
  gap: 10px;
  padding: 12px;
  @media (max-width: 850px) {
    grid-template-columns: 1fr 1fr;
  }
  @media (max-width: 540px) {
    grid-template-columns: 1fr;
  }
`;

const Field = styled.label`
  display: grid;
  gap: 6px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.63rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  span {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  svg {
    width: 15px;
  }
`;

const Control = styled.input`
  width: 100%;
  min-height: 42px;
  padding: 0 11px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px 5px 10px 5px;
  outline: 0;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.control};
  font: inherit;
  font-size: 0.72rem;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 1px;
  }
`;

const Select = styled.select`
  width: 100%;
  min-height: 42px;
  padding: 0 30px 0 11px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px 5px 10px 5px;
  outline: 0;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.control};
  font: inherit;
  font-size: 0.72rem;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 1px;
  }
`;

const ContentGrid = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(310px, 0.42fr);
  align-items: start;
  gap: 13px;
  @media (max-width: 1050px) {
    grid-template-columns: 1fr;
  }
`;

const ListPanel = styled(GlassPanel)`
  min-width: 0;
  overflow: hidden;
`;

const PanelHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1rem;
    font-weight: 540;
    letter-spacing: -0.02em;
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    line-height: 1.5;
  }
`;

const GroupList = styled.ul`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const GroupRow = styled.li`
  display: grid;
  gap: 12px;
  padding: 15px 18px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  & + & {
    border-top: 1px solid ${({ theme }) => theme.color.border};
  }
`;

const GroupTop = styled.div`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 11px;
`;

const GroupCheck = styled.input`
  width: 18px;
  height: 18px;
  margin: 3px 0 0;
  accent-color: ${({ theme }) => theme.color.cyan};
`;

const GroupTitle = styled.div`
  min-width: 0;
  strong {
    display: block;
    overflow: hidden;
    font-size: 0.78rem;
    font-weight: 620;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.67rem;
    line-height: 1.48;
  }
`;

const GroupMeta = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
`;

const GroupLink = styled(Link)`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: ${({ theme }) => theme.color.cyan};
  font-size: 0.65rem;
  font-weight: 600;
  svg {
    width: 14px;
  }
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 2px;
  }
`;

const GroupForm = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surface};
  @media (max-width: 620px) {
    grid-template-columns: 1fr;
  }
`;

const WideField = styled(Field)`
  grid-column: 1 / -1;
`;

const Pagination = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.67rem;
`;

const ReviewPanel = styled(GlassPanel)`
  position: sticky;
  top: calc(${({ theme }) => theme.layout.header} + 12px);
  display: grid;
  gap: 0;
  overflow: hidden;
  @media (max-width: 1050px) {
    position: static;
  }
`;

const ReviewBody = styled.div`
  display: grid;
  gap: 12px;
  padding: 15px;
`;

const ReviewList = styled.ol`
  display: grid;
  gap: 8px;
  max-height: 360px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
`;

const ReviewRow = styled.li`
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 9px;
  padding: 10px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 10px 4px 10px 4px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  > b {
    display: grid;
    width: 24px;
    height: 24px;
    place-items: center;
    border-radius: 8px 3px 8px 3px;
    color: ${({ theme }) => theme.color.ink};
    background: ${({ theme }) => theme.color.cyan};
    font-size: 0.64rem;
  }
  strong {
    display: block;
    font-size: 0.7rem;
    font-weight: 620;
  }
  small {
    display: block;
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.62rem;
    line-height: 1.45;
  }
`;

const Attestation = styled.label`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 9px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.67rem;
  line-height: 1.5;
  input {
    width: 17px;
    height: 17px;
    margin-top: 2px;
    accent-color: ${({ theme }) => theme.color.cyan};
  }
`;

const State = styled(GlassPanel)`
  display: grid;
  min-height: 220px;
  place-items: center;
  padding: 30px;
  text-align: center;
  > div {
    max-width: 620px;
  }
  svg {
    width: 32px;
    margin: 0 auto 10px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 620;
  }
  p {
    margin: 7px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    line-height: 1.55;
  }
  button {
    margin-top: 14px;
  }
`;

const Notice = styled.div<{ $warning?: boolean }>`
  padding: 11px 12px;
  border: 1px solid
    ${({ $warning, theme }) =>
      $warning ? "rgba(242,190,116,.38)" : "rgba(142,216,176,.38)"};
  border-radius: 10px 4px 10px 4px;
  color: ${({ $warning, theme }) =>
    $warning ? theme.color.amber : theme.color.mint};
  background: ${({ $warning }) =>
    $warning ? "rgba(242,190,116,.08)" : "rgba(142,216,176,.08)"};
  font-size: 0.67rem;
  line-height: 1.5;
`;

const InlineActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

interface GroupDraft {
  payerGuardianId: string;
  ratePlanChoice: string;
  code: string;
  name: string;
  billingUnit: "" | BillingUnit;
  amount: string;
  effectiveFrom: string;
  effectiveUntil: string;
  description: string;
}

interface ProgressState {
  completed: number;
  total: number;
  current: string;
}

const EMPTY_DRAFT: GroupDraft = {
  payerGuardianId: "",
  ratePlanChoice: "",
  code: "",
  name: "",
  billingUnit: "",
  amount: "",
  effectiveFrom: "",
  effectiveUntil: "",
  description: "",
};

const WAVE_CONTENT: Record<
  BillingBatchWave,
  { title: string; short: string }
> = {
  account_payer: {
    title: "Family account & payer",
    short: "Establish one accountable family ledger identity.",
  },
  rate_plan: {
    title: "Current care rate",
    short: "Publish reviewed terms for a program and age group.",
  },
  agreement: {
    title: "Enrollment agreement",
    short: "Bind the enrolled child to a reviewed current rate.",
  },
  ready: {
    title: "Setup ready",
    short: "All setup dependencies align; no financial action is created.",
  },
  manual_review: {
    title: "Manual review",
    short: "Resolve ambiguous or missing source authority individually.",
  },
};

const BILLING_NAV: Array<[string, string]> = [
  ["overview", "Overview"],
  ["setup", "Setup planner"],
  ["accounts", "Family accounts"],
  ["invoices", "Invoices"],
  ["payments", "Payments"],
  ["rates", "Rates & agreements"],
  ["reports", "Reports & readiness"],
];

function groupHeading(group: BillingBatchPlanGroup): string {
  if (group.family_name) return group.family_name;
  const careContext = [group.facility_name, group.program_name, group.age_group]
    .filter(Boolean)
    .join(" · ");
  if (careContext) return careContext;
  return group.affected_children[0]?.child_name || "Billing setup group";
}

function groupDescription(group: BillingBatchPlanGroup): string {
  const names = group.affected_children
    .slice(0, 3)
    .map((child) => child.child_name)
    .join(", ");
  const remaining = Math.max(0, group.affected_count - 3);
  return `${names}${remaining > 0 ? ` +${remaining} more` : ""} · ${
    group.affected_count
  } affected ${group.affected_count === 1 ? "child" : "children"}`;
}

function frequencyForUnit(unit: BillingUnit): BillingFrequency {
  return {
    weekly_period: "weekly",
    biweekly_period: "biweekly",
    monthly_period: "monthly",
    service_event: "per_service",
  }[unit] as BillingFrequency;
}

function defaultDraft(
  group: BillingBatchPlanGroup,
  asOfDate: string,
): GroupDraft {
  return {
    ...EMPTY_DRAFT,
    effectiveFrom:
      group.wave === "agreement"
        ? group.agreement_effective_from_min ?? asOfDate
        : asOfDate,
    effectiveUntil:
      group.wave === "agreement" &&
      group.agreement_effective_until_required
        ? group.agreement_effective_until_max ?? ""
        : "",
  };
}

function commandLabel(intent: BillingBatchPreviewIntent): string {
  return {
    account_open: "Open family account",
    account_payer_assign: "Assign current payer",
    rate_version_publish: "Publish rate version",
    agreement_establish: "Establish agreement",
  }[intent.command_type];
}

function canonicalProof(value: unknown): string {
  if (Array.isArray(value))
    return `[${value.map((item) => canonicalProof(item)).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalProof(
            (value as Record<string, unknown>)[key],
          )}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}

function sameIntentProof(
  reviewed: BillingBatchPreviewIntent,
  refreshed: BillingBatchPreviewIntent,
): boolean {
  return (
    reviewed.group_id === refreshed.group_id &&
    reviewed.label === refreshed.label &&
    reviewed.command_type === refreshed.command_type &&
    reviewed.command_kind === refreshed.command_kind &&
    reviewed.client_operation_id === refreshed.client_operation_id &&
    reviewed.target_scope === refreshed.target_scope &&
    reviewed.request_hash === refreshed.request_hash &&
    reviewed.execute_path === refreshed.execute_path &&
    reviewed.affected_count === refreshed.affected_count &&
    canonicalProof(reviewed.request_payload) ===
      canonicalProof(refreshed.request_payload) &&
    canonicalProof(reviewed.input) === canonicalProof(refreshed.input)
  );
}

function statusLabel(status: BillingReadinessStatus): string {
  return titleCase(status.replaceAll("_", " "));
}

function validActionableWave(
  value: BillingBatchWave | null,
): value is BillingBatchActionableWave {
  return (
    value !== null &&
    BILLING_BATCH_ACTIONABLE_WAVES.includes(
      value as BillingBatchActionableWave,
    )
  );
}

function selectedGroupWave(
  plan: BillingBatchPlan | null,
  selected: Set<string>,
): BillingBatchActionableWave | null {
  if (!plan || !selected.size) return null;
  const waves = new Set(
    plan.items
      .filter((group) => selected.has(group.group_id))
      .map((group) => group.wave),
  );
  if (waves.size !== 1) return null;
  const wave = [...waves][0] ?? null;
  return validActionableWave(wave) ? wave : null;
}

function buildSelection(
  group: BillingBatchPlanGroup,
  draft: GroupDraft,
  asOfDate: string,
  operationId: string,
): BillingBatchPreviewSelection {
  const base = {
    group_id: group.group_id,
    client_operation_id: operationId,
  };
  if (group.wave === "account_payer") {
    if (!draft.payerGuardianId)
      throw new Error(`Choose a payer for ${groupHeading(group)}.`);
    if (
      !group.payer_options.some(
        (option) => option.guardian_id === draft.payerGuardianId,
      )
    )
      throw new Error(
        `The selected payer for ${groupHeading(group)} is no longer available.`,
      );
    return { ...base, payer_guardian_id: draft.payerGuardianId };
  }
  if (group.wave === "rate_plan") {
    if (!draft.ratePlanChoice)
      throw new Error(`Choose an existing or new rate for ${groupHeading(group)}.`);
    if (!draft.billingUnit)
      throw new Error(`Choose a billing unit for ${groupHeading(group)}.`);
    const amount = parseMoneyInput(draft.amount, { allowZero: true });
    if (!draft.effectiveFrom || !isDateOnly(draft.effectiveFrom))
      throw new Error(`Choose an effective date for ${groupHeading(group)}.`);
    if (draft.effectiveFrom > asOfDate)
      throw new Error(
        `The rate for ${groupHeading(group)} must begin no later than the current plan date ${asOfDate}.`,
      );
    if (draft.effectiveUntil && !isDateOnly(draft.effectiveUntil))
      throw new Error(`Choose a valid end date for ${groupHeading(group)}.`);
    if (
      draft.effectiveUntil &&
      draft.effectiveUntil < draft.effectiveFrom
    )
      throw new Error(
        `The end date precedes the effective date for ${groupHeading(group)}.`,
      );
    if (draft.effectiveUntil && draft.effectiveUntil < asOfDate)
      throw new Error(
        `The rate for ${groupHeading(group)} must remain effective through the current plan date ${asOfDate}.`,
      );
    const terms = {
      ...base,
      billing_unit: draft.billingUnit,
      unit_amount_minor: Number(amount),
      effective_from: draft.effectiveFrom,
      ...(draft.effectiveUntil
        ? { effective_until: draft.effectiveUntil }
        : {}),
      ...(draft.description.trim()
        ? { description: draft.description.trim() }
        : {}),
    };
    if (draft.ratePlanChoice === "new") {
      if (!draft.code.trim() || !draft.name.trim())
        throw new Error(
          `Enter a code and name for the new rate in ${groupHeading(group)}.`,
        );
      return {
        ...terms,
        code: draft.code.trim(),
        name: draft.name.trim(),
      };
    }
    const selectedRate = group.rate_plan_options.find(
      (option) => option.rate_plan_id === draft.ratePlanChoice,
    );
    if (!selectedRate)
      throw new Error(
        `The selected rate for ${groupHeading(group)} is no longer available.`,
      );
    if (!selectedRate.revision_can_resolve_as_of_date)
      throw new Error(
        `The selected rate cannot be revised into a current rate for ${groupHeading(group)}.`,
      );
    return { ...terms, rate_plan_id: draft.ratePlanChoice };
  }
  if (group.wave === "agreement") {
    if (
      !group.rate_billing_unit ||
      group.rate_unit_amount_minor === null ||
      !group.agreement_effective_from_min
    )
      throw new Error(
        `The canonical rate terms for ${groupHeading(group)} are incomplete.`,
      );
    const billingFrequency = frequencyForUnit(group.rate_billing_unit);
    if (!draft.effectiveFrom || !isDateOnly(draft.effectiveFrom))
      throw new Error(`Choose an effective date for ${groupHeading(group)}.`);
    if (draft.effectiveFrom < group.agreement_effective_from_min)
      throw new Error(
        `The agreement for ${groupHeading(group)} cannot start before ${group.agreement_effective_from_min}.`,
      );
    if (draft.effectiveFrom > asOfDate)
      throw new Error(
        `The agreement for ${groupHeading(group)} cannot start after the current plan date ${asOfDate}.`,
      );
    if (draft.effectiveUntil && !isDateOnly(draft.effectiveUntil))
      throw new Error(`Choose a valid end date for ${groupHeading(group)}.`);
    if (
      draft.effectiveUntil &&
      draft.effectiveUntil < draft.effectiveFrom
    )
      throw new Error(
        `The end date precedes the effective date for ${groupHeading(group)}.`,
      );
    if (draft.effectiveUntil && draft.effectiveUntil < asOfDate)
      throw new Error(
        `The agreement for ${groupHeading(group)} must remain effective through the current plan date ${asOfDate}.`,
      );
    if (
      group.agreement_effective_until_required &&
      !draft.effectiveUntil
    )
      throw new Error(
        `Choose the required agreement end date for ${groupHeading(group)}.`,
      );
    if (
      group.agreement_effective_until_max &&
      (!draft.effectiveUntil ||
        draft.effectiveUntil > group.agreement_effective_until_max)
    )
      throw new Error(
        `The agreement for ${groupHeading(group)} must end by ${group.agreement_effective_until_max}.`,
      );
    return {
      ...base,
      billing_frequency: billingFrequency,
      family_amount_minor_per_unit: group.rate_unit_amount_minor,
      effective_from: draft.effectiveFrom,
      ...(draft.effectiveUntil
        ? { effective_until: draft.effectiveUntil }
        : {}),
    };
  }
  throw new Error("This group requires individual review, not a batch command.");
}

export function billingSetupApplyBlockReason(input: {
  hasPermission: boolean;
  capabilityWritesAvailable: boolean;
  planApplyAvailable: boolean;
  previewApplyAvailable: boolean;
  manualActivationRequired: boolean;
  hasPendingOperation: boolean;
  journalError: string;
  reviewed: boolean;
  previewIntentCount: number;
  busy: boolean;
}): string | null {
  if (!input.hasPermission)
    return "Your role does not include billing setup management.";
  if (
    input.manualActivationRequired ||
    !input.capabilityWritesAvailable ||
    !input.planApplyAvailable ||
    !input.previewApplyAvailable
  )
    return "Owner activation or authoritative billing write readiness is still pending.";
  if (input.hasPendingOperation || input.journalError)
    return "Resolve the protected billing command before applying another setup change.";
  if (!input.previewIntentCount)
    return "Preview at least one actionable setup group first.";
  if (!input.reviewed)
    return "Confirm that you reviewed the exact command sequence.";
  if (input.busy) return "The reviewed sequence is already being processed.";
  return null;
}

export default function BillingSetupWorkspace() {
  const session = useSession();
  const capability = useBillingCapability();
  const organizationId = session.user?.organization_id || "";
  const actorId = session.user?.id || "";
  const canManage = hasExplicitPermission(
    session.user,
    ACCESS.billingManage,
  );
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [plan, setPlan] = useState<BillingBatchPlan | null>(null);
  const [error, setError] = useState("");
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [wave, setWave] = useState<BillingBatchWaveFilter>("all");
  const [status, setStatus] = useState<BillingReadinessStatus | "all">("all");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drafts, setDrafts] = useState<Record<string, GroupDraft>>({});
  const [preview, setPreview] = useState<BillingBatchPreview | null>(null);
  const [previewSelections, setPreviewSelections] = useState<
    BillingBatchPreviewSelection[]
  >([]);
  const [reviewed, setReviewed] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [approvalInvalidated, setApprovalInvalidated] = useState(false);
  const [notice, setNotice] = useState<{
    text: string;
    warning?: boolean;
  } | null>(null);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [pending, setPending] = useState<PendingBillingOperation | null>(null);
  const [pendingLookup, setPendingLookup] = useState<
    "idle" | "checking" | "prepared" | "not_found" | "unavailable"
  >("idle");
  const [journalError, setJournalError] = useState("");
  const requestIdentity = useRef(`${organizationId}:${actorId}`);
  const acceptedSequence = useRef(-1);
  const loadGeneration = useRef(0);

  const invalidateApproval = useCallback((visible = true) => {
    setPreview((current) => {
      if (current && visible) setApprovalInvalidated(true);
      return null;
    });
    setPreviewSelections([]);
    setReviewed(false);
  }, []);

  const loadPlan = useCallback(
    async (options?: {
      offset?: number;
      snapshotToken?: string | null;
      preserveApproval?: boolean;
      signal?: AbortSignal;
    }): Promise<BillingBatchPlan> => {
      if (!organizationId)
        throw new Error("A selected organization is required.");
      const generation = ++loadGeneration.current;
      const identity = `${organizationId}:${actorId}`;
      const nextOffset = options?.offset ?? 0;
      const result = await fetchBillingBatchPlan(
        organizationId,
        {
          wave,
          status: status === "all" ? null : status,
          query,
          limit: PAGE_SIZE,
          offset: nextOffset,
          snapshotToken: options?.snapshotToken ?? null,
        },
        options?.signal,
      );
      if (
        requestIdentity.current !== identity ||
        generation !== loadGeneration.current
      )
        throw new Error(
          "The billing setup identity changed while the plan was loading.",
        );
      if (
        options?.snapshotToken &&
        result.snapshot_token !== options.snapshotToken
      )
        throw new Error(
          "The billing setup snapshot changed between pages. Restart the review.",
        );
      if (
        !options?.snapshotToken &&
        result.data_through_realtime_sequence < acceptedSequence.current
      )
        throw new Error(
          "The server returned an older billing setup checkpoint than the one already accepted.",
        );
      acceptedSequence.current = Math.max(
        acceptedSequence.current,
        result.data_through_realtime_sequence,
      );
      setPlan(result);
      setOffset(result.page.offset);
      setPhase("ready");
      setError("");
      if (!options?.preserveApproval) {
        setSelected(new Set());
        setDrafts({});
        invalidateApproval(false);
        setApprovalInvalidated(false);
      }
      return result;
    },
    [
      actorId,
      invalidateApproval,
      organizationId,
      query,
      status,
      wave,
    ],
  );

  useEffect(() => {
    requestIdentity.current = `${organizationId}:${actorId}`;
    acceptedSequence.current = -1;
    loadGeneration.current += 1;
    setPlan(null);
    setSelected(new Set());
    setDrafts({});
    setPreview(null);
    setPreviewSelections([]);
    setReviewed(false);
    setOffset(0);
    setPhase("loading");
    setError("");
  }, [actorId, organizationId]);

  useEffect(() => {
    if (
      capability.phase !== "enabled" ||
      capability.capability?.runtime_available !== true
    )
      return;
    const controller = new AbortController();
    setPhase("loading");
    void loadPlan({ offset: 0, signal: controller.signal }).catch((caught) => {
      if (!controller.signal.aborted) {
        setError(billingErrorMessage(caught));
        setPhase("error");
      }
    });
    return () => controller.abort();
  }, [capability.phase, capability.capability?.runtime_available, loadPlan]);

  useEffect(() => {
    if (!organizationId || !actorId) return;
    let cancelled = false;
    try {
      const operation = readPendingBillingOperation(organizationId, actorId);
      setPending(operation);
      setJournalError("");
      if (!operation) {
        setPendingLookup("idle");
        return;
      }
      setPendingLookup("checking");
      void billingApi
        .reconcileCommand(
          organizationId,
          operation.client_operation_id,
          operation.command_kind,
          operation.request_hash,
        )
        .then(async (result) => {
          if (cancelled) return;
          if (result === "prepared_not_committed") {
            setPendingLookup("prepared");
            return;
          }
          if (result === "not_found") {
            setPendingLookup("not_found");
            return;
          }
          clearPendingBillingOperation(operation);
          setPending(null);
          setPendingLookup("idle");
          invalidateApproval(false);
          setSelected(new Set());
          setDrafts({});
          setNotice({
            text:
              result === "finalized_absent"
                ? "The server proved the protected operation was not committed. The setup plan was refreshed."
                : "A delayed exact receipt was recovered. The committed setup is now reflected in the canonical plan.",
          });
          await loadPlan({ offset: 0 });
        })
        .catch((caught) => {
          if (!cancelled) {
            setPendingLookup("unavailable");
            setNotice({
              text: `The protected operation remains locked: ${billingErrorMessage(caught)}`,
              warning: true,
            });
          }
        });
    } catch (caught) {
      setPending(null);
      setPendingLookup("unavailable");
      setJournalError(billingErrorMessage(caught));
    }
    return () => {
      cancelled = true;
    };
  }, [actorId, invalidateApproval, loadPlan, organizationId]);

  useRealtimeRefresh({
    scope: "billing-setup-planner",
    organizationId,
    enabled:
      capability.phase === "enabled" &&
      capability.capability?.runtime_available === true,
    entityTypes: featureIntegrationManifest.billing.realtimeEntities,
    refresh: async () => {
      if (applyBusy)
        throw new Error(
          "A billing setup command is in progress; canonical refresh will run after its receipt.",
        );
      invalidateApproval();
      setSelected(new Set());
      setDrafts({});
      setNotice({
        text: "Canonical billing or enrollment facts changed. The earlier review was invalidated and the setup plan was refreshed.",
        warning: true,
      });
      await loadPlan({ offset: 0 });
    },
  });

  const selectedWave = useMemo(
    () => selectedGroupWave(plan, selected),
    [plan, selected],
  );
  const selectedGroups = useMemo(
    () => plan?.items.filter((group) => selected.has(group.group_id)) ?? [],
    [plan, selected],
  );

  const updateDraft = (
    group: BillingBatchPlanGroup,
    field: keyof GroupDraft,
    value: string,
  ) => {
    invalidateApproval();
    setDrafts((current) => ({
      ...current,
      [group.group_id]: {
        ...defaultDraft(group, plan?.as_of_date ?? ""),
        ...current[group.group_id],
        [field]: value,
      },
    }));
  };

  const toggleGroup = (group: BillingBatchPlanGroup) => {
    if (!group.actionable || !validActionableWave(group.wave)) return;
    invalidateApproval();
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(group.group_id)) next.delete(group.group_id);
      else {
        const currentWave = selectedGroupWave(plan, next);
        if (currentWave && currentWave !== group.wave) {
          setNotice({
            text: "Review one dependency wave at a time. Clear the current selection before choosing another wave.",
            warning: true,
          });
          return next;
        }
        if (next.size >= MAX_SELECTED_GROUPS) {
          setNotice({
            text: `Review at most ${MAX_SELECTED_GROUPS} groups in one visible page.`,
            warning: true,
          });
          return next;
        }
        next.add(group.group_id);
        setDrafts((draftsCurrent) => ({
          ...draftsCurrent,
          [group.group_id]: {
            ...defaultDraft(group, plan?.as_of_date ?? ""),
            ...draftsCurrent[group.group_id],
          },
        }));
      }
      return next;
    });
  };

  const changePage = (nextOffset: number) => {
    if (!plan || nextOffset < 0 || nextOffset > 10_000) return;
    setPhase("loading");
    void loadPlan({
      offset: nextOffset,
      snapshotToken: plan.snapshot_token,
    }).catch((caught) => {
      setError(
        `${billingErrorMessage(caught)} Restart the plan before reviewing any setup command.`,
      );
      setPhase("error");
    });
  };

  const submitFilters = (event: FormEvent) => {
    event.preventDefault();
    const nextQuery = queryDraft.trim();
    if (nextQuery.length > 80) {
      setNotice({
        text: "Search is limited to 80 characters.",
        warning: true,
      });
      return;
    }
    setQuery(nextQuery);
    setOffset(0);
  };

  const previewSelection = async () => {
    if (!plan || !selectedWave || !selectedGroups.length) {
      setNotice({
        text: "Select at least one actionable group from one dependency wave.",
        warning: true,
      });
      return;
    }
    setPreviewBusy(true);
    setNotice(null);
    setApprovalInvalidated(false);
    try {
      const selections = selectedGroups.map((group) =>
        buildSelection(
          group,
          drafts[group.group_id] ?? {
            ...defaultDraft(group, plan.as_of_date),
          },
          plan.as_of_date,
          crypto.randomUUID(),
        ),
      );
      const result = await previewBillingBatchWave(
        organizationId,
        plan.snapshot_token,
        selectedWave,
        selections,
      );
      const selectedIds = new Set(selectedGroups.map((group) => group.group_id));
      const outcomeIds = new Set([
        ...result.intents.map((intent) => intent.group_id),
        ...result.blocked.map((block) => block.group_id),
      ]);
      if (
        result.data_through_realtime_sequence !==
          plan.data_through_realtime_sequence ||
        selectedIds.size !== outcomeIds.size ||
        [...selectedIds].some((groupId) => !outcomeIds.has(groupId)) ||
        result.intents.some((intent) => {
          const group = selectedGroups.find(
            (candidate) => candidate.group_id === intent.group_id,
          );
          return !group || group.affected_count !== intent.affected_count;
        })
      )
        throw new Error(
          "The read-only preview did not reconcile to the selected canonical groups.",
        );
      setPreview(result);
      setPreviewSelections(selections);
      setReviewed(false);
      setNotice(
        result.blocked.length
          ? {
              text: `${result.blocked.length} selected ${
                result.blocked.length === 1 ? "group was" : "groups were"
              } blocked and will not be sent. Review the exact remaining sequence.`,
              warning: true,
            }
          : {
              text: "Read-only preview created. No setup record has been changed.",
            },
      );
    } catch (caught) {
      invalidateApproval(false);
      setNotice({ text: billingErrorMessage(caught), warning: true });
      if (
        caught instanceof Error &&
        /snapshot|checkpoint|changed/i.test(caught.message)
      ) {
        setSelected(new Set());
        setDrafts({});
        void loadPlan({ offset: 0 }).catch(() => undefined);
      }
    } finally {
      setPreviewBusy(false);
    }
  };

  const executeIntent = useCallback(
    async (
      intent: BillingBatchPreviewIntent,
    ): Promise<BillingCommandReceipt> => {
      return executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: intent.command_kind,
        input: intent.input,
        approvedProof: {
          client_operation_id: intent.client_operation_id,
          command_type: intent.command_type,
          target_scope: intent.target_scope,
          request_hash: intent.request_hash,
        },
        prepare: async (operationId) => {
          const prepared = await billingApi.prepareCommand(
            organizationId,
            operationId,
            intent.command_kind,
            intent.input,
          );
          if (
            prepared.request_hash !== intent.request_hash ||
            prepared.target_scope !== intent.target_scope ||
            prepared.command_type !== intent.command_type
          )
            throw new Error(
              "The server preparation changed after review. No setup command was sent.",
            );
          return prepared;
        },
        execute: (operationId) => {
          switch (intent.command_kind) {
            case "account.create":
              return billingApi.createAccount(
                organizationId,
                operationId,
                intent.input as unknown as CreateBillingAccountInput,
              );
            case "account.payer.assign": {
              const input =
                intent.input as unknown as AssignBillingAccountPayerInput;
              return billingApi.assignAccountPayer(
                organizationId,
                input.account_id,
                operationId,
                input,
              );
            }
            case "rate_plan.create":
              return billingApi.createRatePlan(
                organizationId,
                operationId,
                intent.input as unknown as CreateRatePlanInput,
              );
            case "agreement.create":
              return billingApi.createAgreement(
                organizationId,
                operationId,
                intent.input as unknown as CreateAgreementInput,
              );
            default:
              throw new Error(
                "The setup planner refused a non-setup financial command.",
              );
          }
        },
      });
    },
    [actorId, organizationId],
  );

  const applyPreview = async () => {
    if (!plan || !preview) return;
    const blockReason = billingSetupApplyBlockReason({
      hasPermission: canManage,
      capabilityWritesAvailable:
        capability.capability?.writes_available === true,
      planApplyAvailable: plan.apply_available,
      previewApplyAvailable: preview.apply_available,
      manualActivationRequired:
        plan.manual_activation_required ||
        preview.manual_activation_required ||
        capability.capability?.manual_activation_required === true,
      hasPendingOperation: pending !== null,
      journalError,
      reviewed,
      previewIntentCount: preview.intents.length,
      busy: applyBusy,
    });
    if (blockReason) {
      setNotice({ text: blockReason, warning: true });
      return;
    }
    setApplyBusy(true);
    setProgress({
      completed: 0,
      total: preview.intents.length,
      current: "Starting reviewed sequence",
    });
    setNotice(null);
    let completed = 0;
    try {
      if (
        previewSelections.length !==
          preview.intents.length + preview.blocked.length ||
        new Set(previewSelections.map((selection) => selection.group_id))
          .size !== previewSelections.length
      )
        throw new Error(
          "The reviewed selection artifact is incomplete. Preview the wave again.",
        );
      const preflight = await loadPlan({
        offset,
        snapshotToken: preview.snapshot_token,
        preserveApproval: true,
      });
      if (
        !preflight.apply_available ||
        preflight.manual_activation_required
      )
        throw new Error(
          "Billing setup is no longer writable. No reviewed command was sent.",
        );
      const selectionsByGroup = new Map(
        previewSelections.map((selection) => [
          selection.group_id,
          selection,
        ]),
      );
      for (const intent of preview.intents) {
        setProgress({
          completed,
          total: preview.intents.length,
          current: intent.label,
        });
        let receipt: BillingCommandReceipt;
        try {
          receipt = await executeIntent(intent);
        } catch (caught) {
          if (
            caught instanceof BillingOperationOutcomeUnknownError ||
            caught instanceof BillingOperationLockedError
          ) {
            setPending(caught.pending);
            setPendingLookup("checking");
          }
          throw caught;
        }
        if (
          receipt.client_operation_id !== intent.client_operation_id ||
          receipt.request_hash !== intent.request_hash ||
          receipt.command_type !== intent.command_type
        )
          throw new Error(
            "The committed receipt did not match the reviewed setup intent.",
          );
        completed += 1;
        setProgress({
          completed,
          total: preview.intents.length,
          current: `Confirmed ${intent.label}`,
        });
        const refreshed = await loadPlan({
          offset,
          preserveApproval: true,
        });
        const remainingIntents = preview.intents.slice(completed);
        if (remainingIntents.length) {
          const remainingSelections = remainingIntents.map((candidate) => {
            const selection = selectionsByGroup.get(candidate.group_id);
            if (!selection)
              throw new Error(
                "The remaining reviewed selection proof is unavailable.",
              );
            return selection;
          });
          const refreshedPreview = await previewBillingBatchWave(
            organizationId,
            refreshed.snapshot_token,
            preview.wave,
            remainingSelections,
          );
          if (
            refreshedPreview.data_through_realtime_sequence !==
              refreshed.data_through_realtime_sequence ||
            !refreshedPreview.apply_available ||
            refreshedPreview.manual_activation_required ||
            refreshedPreview.blocked.length ||
            refreshedPreview.intents.length !== remainingIntents.length ||
            remainingIntents.some(
              (reviewedIntent, index) =>
                !sameIntentProof(
                  reviewedIntent,
                  refreshedPreview.intents[index],
                ),
            )
          )
            throw new Error(
              "The next reviewed setup proof changed after the last receipt. The remaining sequence was stopped before another command was sent.",
            );
        }
      }
      setSelected(new Set());
      setDrafts({});
      setPreview(null);
      setPreviewSelections([]);
      setReviewed(false);
      setApprovalInvalidated(false);
      setNotice({
        text: `All ${completed} reviewed setup ${
          completed === 1 ? "command was" : "commands were"
        } confirmed by exact receipts. No invoice or payment was created.`,
      });
    } catch (caught) {
      setReviewed(false);
      const outcomeUnknown =
        caught instanceof BillingOperationOutcomeUnknownError ||
        caught instanceof BillingOperationLockedError;
      if (!outcomeUnknown) {
        setPreview(null);
        setPreviewSelections([]);
        setApprovalInvalidated(true);
        try {
          await loadPlan({ offset, preserveApproval: true });
        } catch {
          // The original command error remains primary. A manual plan restart
          // is required if this best-effort canonical refresh also fails.
        }
      }
      setNotice({
        text: `${completed}/${preview.intents.length} reviewed setup commands have confirmed receipts. The sequence stopped: ${billingErrorMessage(
          caught,
        )}`,
        warning: true,
      });
    } finally {
      setProgress(null);
      setApplyBusy(false);
    }
  };

  const retryPendingIntent = async () => {
    if (!pending || !preview) return;
    const intent = preview.intents.find(
      (candidate) =>
        candidate.client_operation_id === pending.client_operation_id,
    );
    if (!intent || readVolatileBillingOperationInput(pending) === null) {
      setNotice({
        text: "The private command fields are no longer in memory. Reloading never stores them; reconcile the receipt or restart with a new review after finalizing the earlier outcome.",
        warning: true,
      });
      return;
    }
    setApplyBusy(true);
    try {
      await executeIntent(intent);
      setPending(null);
      setPendingLookup("idle");
      invalidateApproval(false);
      setSelected(new Set());
      setDrafts({});
      await loadPlan({ offset: 0 });
      setNotice({
        text: "The exact pending setup command returned a confirmed receipt. The canonical plan was refreshed.",
      });
    } catch (caught) {
      if (caught instanceof BillingOperationOutcomeUnknownError)
        setPending(caught.pending);
      setNotice({ text: billingErrorMessage(caught), warning: true });
    } finally {
      setApplyBusy(false);
    }
  };

  const capabilityWritesAvailable =
    capability.capability?.writes_available === true;
  const applyBlockReason = billingSetupApplyBlockReason({
    hasPermission: canManage,
    capabilityWritesAvailable,
    planApplyAvailable: plan?.apply_available === true,
    previewApplyAvailable: preview?.apply_available === true,
    manualActivationRequired:
      plan?.manual_activation_required === true ||
      preview?.manual_activation_required === true ||
      capability.capability?.manual_activation_required === true,
    hasPendingOperation: pending !== null,
    journalError,
    reviewed,
    previewIntentCount: preview?.intents.length ?? 0,
    busy: applyBusy,
  });

  if (capability.phase === "checking")
    return (
      <Page>
        <State aria-live="polite">
          <div>
            <ArrowPathIcon />
            <h2>Checking billing setup access</h2>
            <p>
              CareSync is confirming the selected organization and protected
              billing capability.
            </p>
          </div>
        </State>
      </Page>
    );

  if (
    capability.phase !== "enabled" ||
    !capability.capability?.runtime_available
  )
    return (
      <Page>
        <State role="alert">
          <div>
            <LockClosedIcon />
            <h2>Billing setup is unavailable</h2>
            <p>
              The server did not certify read access to the protected billing
              foundation for this organization.
            </p>
          </div>
        </State>
      </Page>
    );

  return (
    <Page>
      <Header>
        <div>
          <Eyebrow>
            <SparklesIcon width={15} /> Billing readiness · dependency planner
          </Eyebrow>
          <h1>Prepare billing in safe waves</h1>
          <p>
            Review account, payer, rate, and enrollment-agreement gaps without
            creating invoices or payments. The directory stays server-paged,
            each preview is read-only, and every approved setup command runs
            through the existing exact-receipt boundary.
          </p>
        </div>
        <HeaderActions>
          {plan && (
            <StatusChip $tone={plan.apply_available ? "success" : "warning"}>
              {plan.apply_available
                ? "Setup commands available"
                : "Review only · activation pending"}
            </StatusChip>
          )}
          <ActionButton
            type="button"
            disabled={phase === "loading" || applyBusy}
            onClick={() => {
              setPhase("loading");
              void loadPlan({ offset: 0 }).catch((caught) => {
                setError(billingErrorMessage(caught));
                setPhase("error");
              });
            }}
          >
            <ArrowPathIcon /> Restart plan
          </ActionButton>
        </HeaderActions>
      </Header>

      <BillingNav aria-label="Billing sections">
        {BILLING_NAV.map(([view, label]) => (
          <BillingNavLink
            key={view}
            to={`/billing?view=${view}`}
            $active={view === "setup"}
            aria-current={view === "setup" ? "page" : undefined}
          >
            {label}
          </BillingNavLink>
        ))}
      </BillingNav>

      <Boundary $accent="cyan">
        <ShieldCheckIcon />
        <div>
          <h2>Setup only — no financial lifecycle actions</h2>
          <p>
            This planner cannot issue invoices, record or allocate payments,
            create credits, activate billing, move money, deliver documents, or
            contact a provider. Preview remains available while owner
            activation is pending; Apply does not.
          </p>
        </div>
        <StatusChip $tone="info">Read-only planning</StatusChip>
      </Boundary>

      {(pending || journalError) && (
        <Boundary $accent="amber" role="alert">
          <LockClosedIcon />
          <div>
            <h2>A protected billing outcome must be reconciled</h2>
            <p>
              {journalError ||
                (pendingLookup === "checking"
                  ? "CareSync is checking for the exact server receipt."
                  : pendingLookup === "prepared"
                    ? "The server has a preparation proof but no committed receipt yet."
                    : pendingLookup === "not_found"
                      ? "The server has no receipt or preparation proof. This redacted operation stays locked for explicit recovery."
                      : "The outcome could not be reconciled. No new setup command can be sent.")}
            </p>
          </div>
          <InlineActions>
            {pending &&
              pendingLookup === "prepared" &&
              preview?.intents.some(
                (intent) =>
                  intent.client_operation_id === pending.client_operation_id,
              ) && (
              <ActionButton
                type="button"
                disabled={applyBusy || !capabilityWritesAvailable}
                onClick={() => void retryPendingIntent()}
              >
                <ArrowPathIcon /> Retry exact command
              </ActionButton>
            )}
            <GroupLink to="/billing?view=overview">
              <ShieldCheckIcon /> Open billing recovery
            </GroupLink>
          </InlineActions>
        </Boundary>
      )}

      {notice && (
        <Notice
          $warning={notice.warning}
          role={notice.warning ? "alert" : "status"}
        >
          {notice.text}
        </Notice>
      )}

      {phase === "error" ? (
        <State role="alert">
          <div>
            <ExclamationTriangleIcon />
            <h2>The setup plan could not be loaded</h2>
            <p>{error}</p>
            <ActionButton
              type="button"
              onClick={() => {
                setPhase("loading");
                void loadPlan({ offset: 0 }).catch((caught) => {
                  setError(billingErrorMessage(caught));
                  setPhase("error");
                });
              }}
            >
              <ArrowPathIcon /> Restart from current records
            </ActionButton>
          </div>
        </State>
      ) : phase === "loading" || !plan ? (
        <State aria-live="polite" aria-busy="true">
          <div>
            <ArrowPathIcon />
            <h2>Loading a privacy-bounded setup page</h2>
            <p>
              CareSync is reading one server-paged group directory. It is not
              loading every family record into the browser.
            </p>
          </div>
        </State>
      ) : (
        <>
          <WaveRail aria-label="Billing setup dependency waves">
            {(
              [
                "account_payer",
                "rate_plan",
                "agreement",
                "ready",
              ] as const
            ).map((itemWave, index) => (
              <WaveCard
                as="li"
                key={itemWave}
                $active={wave === itemWave}
                $accent={
                  itemWave === "ready"
                    ? "cyan"
                    : index === 0
                      ? "amber"
                      : undefined
                }
              >
                <button
                  type="button"
                  onClick={() => {
                    setWave(itemWave);
                    setOffset(0);
                  }}
                  aria-label={`Filter to ${WAVE_CONTENT[itemWave].title}`}
                >
                  <b>{index + 1}</b>
                  <strong>{WAVE_CONTENT[itemWave].title}</strong>
                  <small>{WAVE_CONTENT[itemWave].short}</small>
                </button>
                <StatusChip
                  $tone={itemWave === "ready" ? "success" : "neutral"}
                >
                  {plan.counts[itemWave]}
                </StatusChip>
              </WaveCard>
            ))}
          </WaveRail>

          <Filters as="form" onSubmit={submitFilters}>
            <Field>
              <span>
                <MagnifyingGlassIcon /> Search this protected directory
              </span>
              <Control
                value={queryDraft}
                maxLength={80}
                onChange={(event) => setQueryDraft(event.currentTarget.value)}
                placeholder="Family, child, facility, program…"
                aria-label="Search billing setup groups"
              />
            </Field>
            <Field>
              <span>Dependency wave</span>
              <Select
                value={wave}
                onChange={(event) => {
                  setWave(event.currentTarget.value as BillingBatchWaveFilter);
                  setOffset(0);
                }}
                aria-label="Filter billing setup wave"
              >
                <option value="all">All waves</option>
                {BILLING_BATCH_WAVES.map((item) => (
                  <option key={item} value={item}>
                    {WAVE_CONTENT[item].title}
                  </option>
                ))}
              </Select>
            </Field>
            <Field>
              <span>Readiness status</span>
              <Select
                value={status}
                onChange={(event) => {
                  setStatus(
                    event.currentTarget.value as BillingReadinessStatus | "all",
                  );
                  setOffset(0);
                }}
                aria-label="Filter billing readiness status"
              >
                <option value="all">All statuses</option>
                {BILLING_READINESS_STATUSES.map((item) => (
                  <option key={item} value={item}>
                    {statusLabel(item)}
                  </option>
                ))}
              </Select>
            </Field>
            <ActionButton type="submit">
              <MagnifyingGlassIcon /> Apply filters
            </ActionButton>
          </Filters>

          <ContentGrid>
            <ListPanel as="section" aria-labelledby="setup-groups-title">
              <PanelHeader>
                <div>
                  <h2 id="setup-groups-title">Canonical setup groups</h2>
                  <p>
                    Showing {plan.page.returned} of {plan.page.total} matching
                    groups · snapshot {plan.snapshot_token.slice(0, 10)}… ·
                    event {plan.data_through_realtime_sequence}
                  </p>
                </div>
                <StatusChip $tone={selected.size ? "info" : "neutral"}>
                  {selected.size} selected
                </StatusChip>
              </PanelHeader>

              {plan.items.length === 0 ? (
                <State>
                  <div>
                    <CheckCircleIcon />
                    <h2>No groups match this page</h2>
                    <p>
                      Change the wave, readiness status, or search. No setup
                      command was created.
                    </p>
                  </div>
                </State>
              ) : (
                <GroupList aria-label="Billing setup groups">
                  {plan.items.map((group) => {
                    const checked = selected.has(group.group_id);
                    const currentDraft = {
                      ...defaultDraft(group, plan.as_of_date),
                      ...drafts[group.group_id],
                    };
                    const anotherWaveSelected =
                      selectedWave !== null && selectedWave !== group.wave;
                    return (
                      <GroupRow key={group.group_id}>
                        <GroupTop>
                          {group.actionable ? (
                            <GroupCheck
                              type="checkbox"
                              checked={checked}
                              disabled={anotherWaveSelected || applyBusy}
                              onChange={() => toggleGroup(group)}
                              aria-label={`Select ${groupHeading(group)} for ${WAVE_CONTENT[group.wave].title}`}
                            />
                          ) : (
                            <LockClosedIcon
                              width={18}
                              aria-label="Individual review required"
                            />
                          )}
                          <GroupTitle>
                            <strong>{groupHeading(group)}</strong>
                            <p>{groupDescription(group)}</p>
                            <GroupMeta>
                              <StatusChip
                                $tone={
                                  group.wave === "ready"
                                    ? "success"
                                    : group.actionable
                                      ? "info"
                                      : "warning"
                                }
                              >
                                {WAVE_CONTENT[group.wave].title}
                              </StatusChip>
                              <StatusChip $tone="neutral">
                                {statusLabel(group.readiness_status)}
                              </StatusChip>
                            </GroupMeta>
                            {group.block_code && (
                              <p role="note">
                                Requires individual review:{" "}
                                {titleCase(group.block_code.replaceAll("_", " "))}
                              </p>
                            )}
                          </GroupTitle>
                          <GroupLink to={group.action_path}>
                            <LinkIcon /> Open source
                          </GroupLink>
                        </GroupTop>

                        {checked && group.wave === "account_payer" && (
                          <GroupForm>
                            <WideField>
                              <span>Reviewed payer</span>
                              <Select
                                value={currentDraft.payerGuardianId}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "payerGuardianId",
                                    event.currentTarget.value,
                                  )
                                }
                                aria-label={`Payer for ${groupHeading(group)}`}
                              >
                                <option value="">Choose a guardian…</option>
                                {group.payer_options.map((payer) => (
                                  <option
                                    key={payer.guardian_id}
                                    value={payer.guardian_id}
                                  >
                                    {payer.display_name}
                                    {payer.is_primary ? " · primary" : ""}
                                  </option>
                                ))}
                              </Select>
                            </WideField>
                          </GroupForm>
                        )}

                        {checked && group.wave === "rate_plan" && (
                          <GroupForm>
                            <WideField>
                              <span>Rate identity</span>
                              <Select
                                value={currentDraft.ratePlanChoice}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "ratePlanChoice",
                                    event.currentTarget.value,
                                  )
                                }
                                aria-label={`Rate identity for ${groupHeading(group)}`}
                              >
                                <option value="">Choose a rate…</option>
                                {group.rate_plan_options.map((rate) => (
                                  <option
                                    key={rate.rate_plan_id}
                                    value={rate.rate_plan_id}
                                    disabled={
                                      !rate.revision_can_resolve_as_of_date
                                    }
                                  >
                                    {rate.code} · {rate.name}
                                    {!rate.revision_can_resolve_as_of_date
                                      ? ` · unavailable for ${plan.as_of_date}`
                                      : ""}
                                  </option>
                                ))}
                                <option value="new">Create a new rate</option>
                              </Select>
                            </WideField>
                            {currentDraft.ratePlanChoice === "new" && (
                              <>
                                <Field>
                                  <span>New rate code</span>
                                  <Control
                                    value={currentDraft.code}
                                    maxLength={40}
                                    onChange={(event) =>
                                      updateDraft(
                                        group,
                                        "code",
                                        event.currentTarget.value,
                                      )
                                    }
                                  />
                                </Field>
                                <Field>
                                  <span>New rate name</span>
                                  <Control
                                    value={currentDraft.name}
                                    maxLength={160}
                                    onChange={(event) =>
                                      updateDraft(
                                        group,
                                        "name",
                                        event.currentTarget.value,
                                      )
                                    }
                                  />
                                </Field>
                              </>
                            )}
                            <Field>
                              <span>Billing unit</span>
                              <Select
                                value={currentDraft.billingUnit}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "billingUnit",
                                    event.currentTarget.value,
                                  )
                                }
                              >
                                <option value="">Choose a unit…</option>
                                <option value="weekly_period">Weekly</option>
                                <option value="biweekly_period">Biweekly</option>
                                <option value="monthly_period">Monthly</option>
                                <option value="service_event">
                                  Per service
                                </option>
                              </Select>
                            </Field>
                            <Field>
                              <span>Family amount (CAD)</span>
                              <Control
                                inputMode="decimal"
                                value={currentDraft.amount}
                                placeholder="0.00"
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "amount",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </Field>
                            <Field>
                              <span>
                                Effective from · on or before{" "}
                                {plan.as_of_date}
                              </span>
                              <Control
                                type="date"
                                max={plan.as_of_date}
                                value={currentDraft.effectiveFrom}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "effectiveFrom",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </Field>
                            <Field>
                              <span>
                                Effective until · optional, on or after{" "}
                                {plan.as_of_date}
                              </span>
                              <Control
                                type="date"
                                min={plan.as_of_date}
                                value={currentDraft.effectiveUntil}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "effectiveUntil",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </Field>
                            <WideField>
                              <span>Description (optional)</span>
                              <Control
                                value={currentDraft.description}
                                maxLength={500}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "description",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </WideField>
                          </GroupForm>
                        )}

                        {checked && group.wave === "agreement" && (
                          <GroupForm>
                            <Field>
                              <span>Rate-matched frequency</span>
                              <Control
                                readOnly
                                value={
                                  group.rate_billing_unit
                                    ? titleCase(
                                        frequencyForUnit(
                                          group.rate_billing_unit,
                                        ).replaceAll("_", " "),
                                      )
                                    : "Canonical rate unavailable"
                                }
                                aria-label={`Derived billing frequency for ${groupHeading(group)}`}
                              />
                            </Field>
                            <Field>
                              <span>Rate-matched family amount (CAD)</span>
                              <Control
                                readOnly
                                value={
                                  group.rate_unit_amount_minor === null
                                    ? "Canonical rate unavailable"
                                    : (
                                        group.rate_unit_amount_minor / 100
                                      ).toFixed(2)
                                }
                                aria-label={`Derived family amount for ${groupHeading(group)}`}
                              />
                            </Field>
                            <Field>
                              <span>
                                Effective from · not before{" "}
                                {group.agreement_effective_from_min} · on or
                                before {plan.as_of_date}
                              </span>
                              <Control
                                type="date"
                                min={
                                  group.agreement_effective_from_min ??
                                  undefined
                                }
                                max={plan.as_of_date}
                                value={currentDraft.effectiveFrom}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "effectiveFrom",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </Field>
                            <Field>
                              <span>
                                Effective until{" "}
                                {group.agreement_effective_until_required
                                  ? `· required by ${group.agreement_effective_until_max}`
                                  : "· optional"}
                              </span>
                              <Control
                                type="date"
                                min={
                                  currentDraft.effectiveFrom > plan.as_of_date
                                    ? currentDraft.effectiveFrom
                                    : plan.as_of_date
                                }
                                max={
                                  group.agreement_effective_until_max ??
                                  undefined
                                }
                                value={currentDraft.effectiveUntil}
                                onChange={(event) =>
                                  updateDraft(
                                    group,
                                    "effectiveUntil",
                                    event.currentTarget.value,
                                  )
                                }
                              />
                            </Field>
                          </GroupForm>
                        )}
                      </GroupRow>
                    );
                  })}
                </GroupList>
              )}

              <Pagination>
                <ActionButton
                  type="button"
                  disabled={plan.page.offset === 0}
                  onClick={() =>
                    changePage(Math.max(0, plan.page.offset - plan.page.limit))
                  }
                >
                  <ChevronLeftIcon /> Previous
                </ActionButton>
                <span>
                  {plan.page.total
                    ? `${plan.page.offset + 1}–${
                        plan.page.offset + plan.page.returned
                      } of ${plan.page.total}`
                    : "0 groups"}
                </span>
                <ActionButton
                  type="button"
                  disabled={!plan.page.has_more}
                  onClick={() =>
                    changePage(
                      plan.page.next_offset ??
                        plan.page.offset + plan.page.returned,
                    )
                  }
                >
                  Next <ChevronRightIcon />
                </ActionButton>
              </Pagination>
            </ListPanel>

            <ReviewPanel as="aside" aria-labelledby="setup-review-title">
              <PanelHeader>
                <div>
                  <h2 id="setup-review-title">Review before Apply</h2>
                  <p>
                    One dependency wave, one protected operation at a time.
                  </p>
                </div>
                <ClipboardDocumentCheckIcon width={22} />
              </PanelHeader>
              <ReviewBody>
                {approvalInvalidated && !preview && (
                  <Notice $warning role="alert">
                    The earlier preview was invalidated by a selection, input,
                    filter, page, or canonical-data change. Preview again.
                  </Notice>
                )}
                {!preview ? (
                  <>
                    <p>
                      {selected.size
                        ? `${selected.size} ${
                            selectedWave
                              ? WAVE_CONTENT[selectedWave].title.toLowerCase()
                              : "setup"
                          } ${
                            selected.size === 1 ? "group is" : "groups are"
                          } selected. Preview validates current canonical facts and creates no records.`
                        : "Select actionable groups from one dependency wave. Ready and manual-review groups never become batch commands."}
                    </p>
                    <ActionButton
                      type="button"
                      $variant="primary"
                      disabled={
                        !selected.size ||
                        !selectedWave ||
                        previewBusy ||
                        applyBusy
                      }
                      onClick={() => void previewSelection()}
                    >
                      <QueueListIcon />{" "}
                      {previewBusy ? "Preparing preview…" : "Preview sequence"}
                    </ActionButton>
                  </>
                ) : (
                  <>
                    <StatusChip $tone="info">
                      Read-only · {formatDateTime(preview.previewed_at)}
                    </StatusChip>
                    <ReviewList aria-label="Reviewed billing setup command sequence">
                      {preview.intents.map((intent) => (
                        <ReviewRow key={intent.client_operation_id}>
                          <b>{intent.sequence}</b>
                          <div>
                            <strong>{intent.label}</strong>
                            <small>
                              {commandLabel(intent)} · {intent.affected_count}{" "}
                              affected · proof{" "}
                              {intent.request_hash.slice(0, 10)}…
                            </small>
                          </div>
                        </ReviewRow>
                      ))}
                    </ReviewList>
                    {preview.blocked.map((block) => (
                      <Notice key={block.group_id} $warning role="note">
                        {block.message} ({titleCase(block.code.replaceAll("_", " "))})
                      </Notice>
                    ))}
                    <Attestation>
                      <input
                        type="checkbox"
                        checked={reviewed}
                        disabled={!preview.intents.length || applyBusy}
                        onChange={(event) =>
                          setReviewed(event.currentTarget.checked)
                        }
                      />
                      <span>
                        I reviewed this exact ordered setup sequence and
                        understand it creates or versions account, payer, rate,
                        or agreement records only—never invoices, payments, or
                        billing activation.
                      </span>
                    </Attestation>
                    {progress && (
                      <Notice role="status">
                        {progress.completed}/{progress.total} receipts confirmed
                        · {progress.current}
                      </Notice>
                    )}
                    {applyBlockReason && (
                      <Notice $warning role="note">
                        Apply unavailable: {applyBlockReason}
                      </Notice>
                    )}
                    <InlineActions>
                      <ActionButton
                        type="button"
                        onClick={() => invalidateApproval()}
                        disabled={applyBusy}
                      >
                        <ArrowLeftIcon /> Change review
                      </ActionButton>
                      <ActionButton
                        type="button"
                        $variant="primary"
                        disabled={applyBlockReason !== null}
                        onClick={() => void applyPreview()}
                      >
                        <ShieldCheckIcon />{" "}
                        {applyBusy ? "Applying safely…" : "Apply reviewed wave"}
                      </ActionButton>
                    </InlineActions>
                  </>
                )}
              </ReviewBody>
            </ReviewPanel>
          </ContentGrid>
        </>
      )}
    </Page>
  );
}

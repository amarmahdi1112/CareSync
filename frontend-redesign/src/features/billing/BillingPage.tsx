import {
  ArrowLeftIcon,
  ArrowPathIcon,
  BanknotesIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  ReceiptPercentIcon,
  ScaleIcon,
  ShieldCheckIcon,
  UserGroupIcon,
} from "@heroicons/react/24/outline";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useSearchParams } from "react-router-dom";
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
import {
  BILLING_MANUAL_REVIEW_ATTESTATION,
  billingApi,
  BillingApiError,
} from "./billingApi";
import { useBillingCapability } from "./billingCapability";
import { BillingDialog } from "./BillingDialog";
import { billingErrorMessage } from "./billingErrorPresentation";
import {
  resolveBillingInvoiceDraftAgreements,
  validateBillingInvoiceDraftDates,
} from "./billingInvoiceDraft";
import { BillingInvoicePreviewDialog } from "./BillingInvoiceDocument";
import BillingReadinessPanel from "./BillingReadinessPanel";
import BillingSetupWorkspace from "./BillingSetupWorkspace";
import {
  fetchBillingReadiness,
  type BillingReadinessResponse,
} from "./billingReadinessApi";
import {
  BillingOperationLockedError,
  BillingOperationOutcomeUnknownError,
  billingOperationStorageKey,
  clearPendingBillingOperation,
  executeProtectedBillingCommand,
  readPendingBillingOperation,
  readVolatileBillingOperationInput,
  purgeVolatileBillingOperationInputs,
  withBillingOperationLock,
  type PendingBillingOperation,
} from "./billingOperation";
import {
  filterAccounts,
  formatCadMinor,
  formatDateOnly,
  formatDateTime,
  invoiceOutstanding,
  addDateOnlyDays,
  organizationDateTimeLocal,
  organizationLocalDateTimeToIso,
  billingPeriodForFrequency,
  parseMoneyInput,
  paymentAvailable,
  previewCreditResult,
  previewInvoiceFromAgreements,
  resolveBillingAccountPayer,
  sortAccountsForAction,
  titleCase,
} from "./billingModel";
import type {
  AllocatePaymentInput,
  AssignBillingAccountPayerInput,
  BillingAccountDetail,
  BillingAccountPayerVersion,
  BillingAccountSummary,
  BillingAgreement,
  BillingAllocation,
  BillingCommandKind,
  BillingCommandReceipt,
  BillingCredit,
  BillingFamilyOption,
  BillingInvoice,
  BillingManualActivation,
  BillingOverview,
  BillingPayment,
  BillingProgramOption,
  BillingProvenanceLabel,
  BillingRatePlan,
  CreateAgreementInput,
  CreateBillingAccountInput,
  CreateCreditInput,
  CreateRatePlanInput,
  IssueInvoiceInput,
  RecordPaymentInput,
} from "./types";

type AssignBillingAccountPayerOperationInput =
  AssignBillingAccountPayerInput & { account_id: string };

type TabId =
  | "overview"
  | "setup"
  | "accounts"
  | "invoices"
  | "payments"
  | "rates"
  | "reports";
type DialogKind =
  | "account"
  | "payer"
  | "rate"
  | "agreement"
  | "invoice"
  | "payment"
  | "allocation"
  | "credit";
type BillingDialogTarget =
  | { kind: "payer"; account: BillingAccountSummary }
  | { kind: "rate"; rate: BillingRatePlan }
  | { kind: "agreement"; agreement: BillingAgreement };
interface Snapshot {
  billingMode: "shadow" | "sandbox" | "manual";
  sandbox: boolean;
  generatedAt: string;
  dataThroughRealtimeSequence: number;
  canonicalCollectionLimit: number;
  snapshotToken: string;
  provenanceLabel: BillingProvenanceLabel;
  overview: BillingOverview;
  accounts: BillingAccountSummary[];
  payerVersions: BillingAccountPayerVersion[];
  invoices: BillingInvoice[];
  payments: BillingPayment[];
  allocations: BillingAllocation[];
  credits: BillingCredit[];
  ratePlans: BillingRatePlan[];
  agreements: BillingAgreement[];
  families: BillingFamilyOption[];
  programs: BillingProgramOption[];
}
interface BillingAccountContext extends BillingAccountDetail {
  allocations: BillingAllocation[];
  credits: BillingCredit[];
}
interface Aging {
  current: number;
  days30: number;
  days60: number;
  days90: number;
  older: number;
}
type BillingFocus =
  | "billing_account"
  | "billing_invoice"
  | "billing_payment"
  | "billing_allocation"
  | "billing_credit"
  | "billing_rate_plan"
  | "billing_agreement";
const RECORD_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const FOCUS_TABS: Record<BillingFocus, TabId> = {
  billing_account: "accounts",
  billing_invoice: "invoices",
  billing_credit: "invoices",
  billing_payment: "payments",
  billing_allocation: "payments",
  billing_rate_plan: "rates",
  billing_agreement: "rates",
};

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
`;
const Tabs = styled.nav`
  display: flex;
  gap: 5px;
  padding: 7px;
  overflow: auto;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px 6px 14px 6px;
  background: ${({ theme }) => theme.color.surface};
  scrollbar-width: thin;
`;
const Tab = styled.button<{ $active: boolean }>`
  flex: 0 0 auto;
  min-height: 39px;
  padding: 0 13px;
  border: 1px solid
    ${({ $active, theme }) => ($active ? theme.color.cyan : "transparent")};
  border-radius: 9px 4px 9px 4px;
  color: ${({ $active, theme }) =>
    $active ? theme.color.text : theme.color.textMuted};
  background: ${({ $active, theme }) =>
    $active ? theme.color.control : "transparent"};
  cursor: pointer;
  font-size: 0.7rem;
  font-weight: 600;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 2px;
  }
`;
const Stats = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 900px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;
const Stat = styled(GlassPanel)`
  padding: 15px 16px;
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.63rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin: 7px 0 4px;
    font-size: 1.26rem;
    font-weight: 560;
  }
  small {
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.63rem;
    line-height: 1.4;
  }
`;
const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 800px) {
    grid-template-columns: 1fr;
  }
`;
const Panel = styled(GlassPanel)`
  padding: 16px;
  overflow: visible;
`;
const PanelHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 13px;
  h2 {
    margin: 0 0 4px;
    font-size: 0.86rem;
    font-weight: 620;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    line-height: 1.5;
  }
  @media (max-width: 600px) {
    flex-direction: column;
  }
`;
const WorkList = styled.div`
  display: grid;
  gap: 7px;
`;
const WorkRow = styled.button`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.divider};
  border-radius: 10px 4px 10px 4px;
  color: ${({ theme }) => theme.color.text};
  background: rgba(255, 255, 255, 0.018);
  cursor: pointer;
  text-align: left;
  > svg:first-child {
    width: 19px;
    color: ${({ theme }) => theme.color.amber};
  }
  .copy {
    display: grid;
    gap: 3px;
    strong {
      font-size: 0.72rem;
      font-weight: 610;
    }
    small {
      color: ${({ theme }) => theme.color.textMuted};
      font-size: 0.63rem;
      line-height: 1.45;
    }
  }
  .arrow {
    width: 15px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  &:hover {
    border-color: ${({ theme }) => theme.color.cyan};
  }
  &[data-focused="true"] {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    background: ${({ theme }) => theme.color.control};
  }
  &:disabled {
    cursor: default;
    opacity: 0.78;
  }
`;
const StatusRow = styled.div`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.divider};
  border-radius: 10px 4px 10px 4px;
  color: ${({ theme }) => theme.color.text};
  background: rgba(255, 255, 255, 0.018);
  cursor: default;
  text-align: left;
  > svg:first-child {
    width: 19px;
    color: ${({ theme }) => theme.color.amber};
  }
  .copy {
    display: grid;
    gap: 3px;
    strong {
      font-size: 0.72rem;
      font-weight: 610;
    }
    small {
      color: ${({ theme }) => theme.color.textMuted};
      font-size: 0.63rem;
      line-height: 1.45;
    }
  }
`;
const AgingBar = styled.div`
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 7px;
  margin-top: 13px;
  div {
    padding: 11px 8px;
    border: 1px solid ${({ theme }) => theme.color.divider};
    border-radius: 9px 4px 9px 4px;
    background: rgba(255, 255, 255, 0.015);
    span {
      display: block;
      color: ${({ theme }) => theme.color.textMuted};
      font-size: 0.58rem;
    }
    strong {
      display: block;
      margin-top: 5px;
      font-size: 0.72rem;
      font-weight: 600;
    }
  }
  @media (max-width: 580px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
`;
const Boundary = styled(GlassPanel)`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  > svg {
    width: 23px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 0 0 3px;
    font-size: 0.8rem;
    font-weight: 620;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    line-height: 1.5;
  }
  @media (max-width: 700px) {
    grid-template-columns: auto 1fr;
    > span {
      grid-column: 1/-1;
      justify-self: start;
    }
  }
`;
const Toolbar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  @media (max-width: 650px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Search = styled.label`
  display: flex;
  min-width: min(360px, 100%);
  align-items: center;
  gap: 8px;
  padding: 0 11px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px 5px 10px 5px;
  background: ${({ theme }) => theme.color.control};
  svg {
    width: 17px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  input {
    width: 100%;
    min-height: 40px;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font: inherit;
    font-size: 0.72rem;
  }
`;
const TableWrap = styled(GlassPanel)`
  overflow: auto;
`;
const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
  th,
  td {
    padding: 12px 14px;
    border-bottom: 1px solid ${({ theme }) => theme.color.divider};
    text-align: left;
  }
  th {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.59rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  td {
    font-size: 0.69rem;
  }
  tbody tr:last-child td {
    border-bottom: 0;
  }
  tbody tr[data-focused="true"] {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: -2px;
    background: ${({ theme }) => theme.color.control};
  }
  strong {
    font-weight: 610;
  }
  small {
    display: block;
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.61rem;
  }
  .money {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .action {
    text-align: right;
  }
  @media (max-width: 700px) {
    min-width: 0;
    thead {
      display: none;
    }
    tbody,
    tr,
    td {
      display: block;
    }
    tr {
      padding: 9px;
      border-bottom: 1px solid ${({ theme }) => theme.color.divider};
    }
    td {
      display: grid;
      grid-template-columns: 110px minmax(0, 1fr);
      gap: 10px;
      padding: 7px;
      border: 0;
    }
    td::before {
      content: attr(data-label);
      color: ${({ theme }) => theme.color.textMuted};
      font-size: 0.58rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .money,
    .action {
      text-align: left;
    }
  }
`;
const InlineButtons = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
`;
const SmallButton = styled.button`
  min-height: 32px;
  padding: 0 9px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 8px 4px 8px 4px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  font-size: 0.62rem;
  font-weight: 600;
  &:hover {
    border-color: ${({ theme }) => theme.color.cyan};
    color: ${({ theme }) => theme.color.text};
  }
  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
`;
const State = styled(GlassPanel)`
  display: grid;
  min-height: 310px;
  place-items: center;
  padding: 28px;
  text-align: center;
  div {
    max-width: 550px;
  }
  svg {
    width: 36px;
    margin-bottom: 10px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 0 0 7px;
    font-size: 1rem;
    font-weight: 620;
  }
  p {
    margin: 0 0 14px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    line-height: 1.6;
  }
`;
const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0;
  border: 0;
  color: ${({ theme }) => theme.color.cyan};
  background: transparent;
  cursor: pointer;
  font-size: 0.68rem;
  font-weight: 600;
  svg {
    width: 16px;
  }
`;
const AccountHero = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 15px;
  padding: 17px;
  h2 {
    margin: 7px 0 5px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.2rem;
    font-weight: 560;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
  }
  @media (max-width: 650px) {
    grid-template-columns: 1fr;
  }
`;
const CurrentPayerCard = styled.div<{ $unavailable?: boolean }>`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 11px 12px;
  border: 1px solid
    ${({ $unavailable, theme }) =>
      $unavailable ? "rgba(242,190,116,.38)" : theme.color.divider};
  border-radius: 10px 4px 10px 4px;
  background: rgba(255, 255, 255, 0.018);
  > svg {
    width: 20px;
    color: ${({ $unavailable, theme }) =>
      $unavailable ? theme.color.amber : theme.color.cyan};
  }
  span,
  small {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.61rem;
    line-height: 1.45;
  }
  span {
    margin-bottom: 3px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    font-size: 0.72rem;
    font-weight: 610;
    line-height: 1.45;
  }
  @media (max-width: 520px) {
    grid-template-columns: auto minmax(0, 1fr);
    > span:last-child {
      grid-column: 2;
      justify-self: start;
    }
  }
`;
const Notice = styled.div<{ $warning?: boolean }>`
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 360;
  max-width: min(440px, calc(100vw - 36px));
  padding: 12px 14px;
  border: 1px solid
    ${({ $warning }) =>
      $warning ? "rgba(242,190,116,.4)" : "rgba(142,216,176,.38)"};
  border-radius: 11px 5px 11px 5px;
  color: ${({ $warning, theme }) =>
    $warning ? theme.color.amber : theme.color.mint};
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: ${({ theme }) => theme.shadow.panel};
  font-size: 0.69rem;
  line-height: 1.5;
`;
const Recovery = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-color: rgba(242, 190, 116, 0.38);
  h2 {
    margin: 0 0 4px;
    font-size: 0.8rem;
    color: ${({ theme }) => theme.color.amber};
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    line-height: 1.5;
  }
  @media (max-width: 700px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;
const Fields = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 560px) {
    grid-template-columns: 1fr;
  }
`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => ($wide ? "1/-1" : "auto")};
  gap: 6px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.64rem;
  font-weight: 600;
  input,
  select,
  textarea {
    width: 100%;
    min-height: 42px;
    padding: 9px 10px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px 4px 9px 4px;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.72rem;
  }
  textarea {
    min-height: 84px;
    resize: vertical;
  }
  input:focus,
  select:focus,
  textarea:focus {
    border-color: ${({ theme }) => theme.color.cyan};
  }
`;
const CheckList = styled.div`
  display: grid;
  gap: 7px;
  max-height: 240px;
  overflow: auto;
  label {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 9px;
    padding: 10px;
    border: 1px solid ${({ theme }) => theme.color.divider};
    border-radius: 9px;
    cursor: pointer;
  }
  strong {
    font-size: 0.7rem;
    font-weight: 610;
  }
  small {
    display: block;
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.61rem;
  }
`;
const SummaryBox = styled.div`
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding: 13px;
  border: 1px solid rgba(123, 211, 240, 0.3);
  border-radius: 10px 4px 10px 4px;
  background: rgba(123, 211, 240, 0.045);
  h3 {
    margin: 0;
    font-size: 0.76rem;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    line-height: 1.55;
  }
  ul {
    margin: 0;
    padding-left: 18px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.65rem;
    line-height: 1.65;
  }
`;
const ReviewAcknowledgment = styled.label`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px 4px 10px 4px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  font-size: 0.68rem;
  line-height: 1.55;
  input {
    width: 17px;
    height: 17px;
    margin: 2px 0 0;
    accent-color: ${({ theme }) => theme.color.cyan};
  }
  &:focus-within {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 2px;
  }
`;
const DetailGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin: 14px 0;
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;
const DetailTotals = styled(Stats)`
  margin-top: 14px;
`;
const DetailCard = styled.div`
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.divider};
  border-radius: 9px 4px 9px 4px;
  background: rgba(255, 255, 255, 0.018);
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.58rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 4px;
    font-size: 0.7rem;
    font-weight: 610;
    line-height: 1.45;
  }
`;
const ProvenanceCode = styled.code`
  overflow-wrap: anywhere;
  color: ${({ theme }) => theme.color.textSoft};
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.58rem;
`;
const Empty = styled.div`
  padding: 30px;
  text-align: center;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.7rem;
  line-height: 1.6;
`;

const TAB_LABELS: Array<[TabId, string]> = [
  ["overview", "Overview"],
  ["setup", "Setup planner"],
  ["accounts", "Family accounts"],
  ["invoices", "Invoices"],
  ["payments", "Payments"],
  ["rates", "Rates & agreements"],
  ["reports", "Reports & readiness"],
];
const minorInput = (amount: number) => (amount / 100).toFixed(2);
const statusTone = (
  status: string,
): "success" | "warning" | "info" | "neutral" =>
  ["settled_paid", "fully_allocated", "published", "reviewed"].includes(status)
    ? "success"
    : ["open", "partially_settled", "partially_allocated"].includes(status)
      ? "warning"
      : ["settled_credited", "settled_mixed", "settled"].includes(status)
        ? "info"
        : "neutral";

function deriveAging(invoices: BillingInvoice[], today: string): Aging {
  const result: Aging = {
    current: 0,
    days30: 0,
    days60: 0,
    days90: 0,
    older: 0,
  };
  const now = Date.parse(`${today}T00:00:00Z`);
  invoices.filter(invoiceOutstanding).forEach((invoice) => {
    const days = Math.max(
      0,
      Math.floor(
        (now - Date.parse(`${invoice.due_date}T00:00:00Z`)) / 86_400_000,
      ),
    );
    if (days === 0) result.current += invoice.outstanding_minor;
    else if (days <= 30) result.days30 += invoice.outstanding_minor;
    else if (days <= 60) result.days60 += invoice.outstanding_minor;
    else if (days <= 90) result.days90 += invoice.outstanding_minor;
    else result.older += invoice.outstanding_minor;
  });
  return result;
}

function EmptyRow({
  colSpan,
  children,
}: {
  colSpan: number;
  children: string;
}) {
  return (
    <tr>
      <td colSpan={colSpan}>
        <Empty>{children}</Empty>
      </td>
    </tr>
  );
}

function CurrentAccountPayer({
  account,
  families,
  payerVersions,
  detail = false,
}: {
  account: BillingAccountSummary;
  families: readonly BillingFamilyOption[];
  payerVersions: readonly BillingAccountPayerVersion[];
  detail?: boolean;
}) {
  const resolved = resolveBillingAccountPayer(
    account,
    families,
    payerVersions,
  );
  const assignmentVersion =
    resolved.assignment?.version_number ?? account.latest_payer_version_number;
  const name =
    resolved.status === "resolved"
      ? resolved.guardian.name
      : "Current payer identity unavailable";
  const contact =
    resolved.status === "resolved"
      ? [resolved.guardian.email, resolved.guardian.cell_phone]
          .map((value) => value.trim())
          .filter(Boolean)
          .join(" · ") || "No email or phone on file"
      : "Guardian source is unavailable in this coherent workspace";
  const assignment = `Assignment v${assignmentVersion}`;
  if (!detail)
    return (
      <>
        <strong>{name}</strong>
        <small>
          {contact} · {assignment}
        </small>
      </>
    );
  return (
    <CurrentPayerCard
      $unavailable={resolved.status === "unavailable"}
      data-payer-resolution={resolved.status}
    >
      <UserGroupIcon />
      <div>
        <span>Current payer</span>
        <strong>{name}</strong>
        <small>{contact}</small>
      </div>
      <StatusChip $tone={resolved.status === "resolved" ? "info" : "warning"}>
        {assignment}
      </StatusChip>
    </CurrentPayerCard>
  );
}

function ManualBillingActivationBoundary({
  organizationId,
  activated,
  ownerCanActivate,
  onCapabilityRefresh,
}: {
  organizationId: string;
  activated: boolean;
  ownerCanActivate: boolean;
  onCapabilityRefresh: () => void;
}) {
  const [status, setStatus] = useState<BillingManualActivation | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "error">(
    ownerCanActivate ? "loading" : "idle",
  );
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadStatus = useCallback(
    async (signal?: AbortSignal) => {
      if (!ownerCanActivate || !organizationId) return;
      setPhase("loading");
      try {
        const next = await billingApi.manualActivation(organizationId, signal);
        setStatus(next);
        setError("");
        setPhase("ready");
        if (next.activated !== activated) onCapabilityRefresh();
      } catch (caught) {
        if (signal?.aborted) return;
        setStatus(null);
        setError(billingErrorMessage(caught));
        setPhase("error");
      }
    },
    [activated, onCapabilityRefresh, organizationId, ownerCanActivate],
  );

  useEffect(() => {
    if (!ownerCanActivate) {
      setStatus(null);
      setPhase("idle");
      setError("");
      return;
    }
    const controller = new AbortController();
    void loadStatus(controller.signal);
    return () => controller.abort();
  }, [loadStatus, ownerCanActivate]);

  const activate = async () => {
    if (
      !reviewed ||
      !status ||
      !status.server_attested ||
      !status.organization_allowlisted ||
      status.activated
    )
      return;
    setBusy(true);
    setError("");
    try {
      const next = await billingApi.activateManualBilling(organizationId);
      if (!next.activated)
        throw new BillingApiError(
          "The server did not confirm private manual billing activation.",
          409,
        );
      setStatus(next);
      setDialogOpen(false);
      setReviewed(false);
      setPhase("ready");
      onCapabilityRefresh();
    } catch (caught) {
      setError(billingErrorMessage(caught));
      setPhase("error");
    } finally {
      setBusy(false);
    }
  };

  const confirmed = activated || status?.activated === true;
  if (confirmed)
    return (
      <Boundary $accent="cyan">
        <ShieldCheckIcon />
        <div>
          <h2>Private manual billing is active</h2>
          <p>
            CareSync records reviewed invoices, credits, and off-platform
            payment facts for this organization. Activation is immutable. No
            processor, bank movement, automatic issue, delivery, refund, or tax
            advice is represented.
          </p>
        </div>
        <StatusChip $tone="success">Manual · active</StatusChip>
      </Boundary>
    );

  return (
    <>
      <Boundary $accent="amber">
        <LockClosedIcon />
        <div>
          <h2>Private manual billing needs owner activation</h2>
          <p>
            The ledger remains read-only until an owner reviews and permanently
            activates the local off-platform boundary. Activation does not
            connect a processor, move money, send invoices, automate issue, or
            provide tax advice.
            {error ? ` ${error}` : ""}
          </p>
        </div>
        {ownerCanActivate ? (
          <ActionButton
            type="button"
            disabled={
              phase === "loading" ||
              (phase === "ready" &&
                (!status?.server_attested ||
                  !status.organization_allowlisted))
            }
            onClick={() => {
              if (phase === "error") {
                void loadStatus();
                return;
              }
              setDialogOpen(true);
            }}
          >
            {phase === "loading" ? (
              <>
                <ArrowPathIcon /> Checking boundary
              </>
            ) : phase === "error" ? (
              <>
                <ArrowPathIcon /> Retry boundary check
              </>
            ) : (
              <>
                <ShieldCheckIcon /> Review activation
              </>
            )}
          </ActionButton>
        ) : (
          <StatusChip $tone="warning">Owner action required</StatusChip>
        )}
      </Boundary>
      {dialogOpen && status && (
        <BillingDialog
          title="Activate private manual billing?"
          description="This is an immutable organization-level decision. It cannot be reversed from CareSync."
          busy={busy}
          onClose={() => {
            if (busy) return;
            setDialogOpen(false);
            setReviewed(false);
          }}
          footer={
            <>
              <ActionButton
                type="button"
                disabled={busy}
                onClick={() => {
                  setDialogOpen(false);
                  setReviewed(false);
                }}
              >
                Keep read-only
              </ActionButton>
              <ActionButton
                type="button"
                $variant="primary"
                disabled={
                  busy ||
                  !reviewed ||
                  !status.server_attested ||
                  !status.organization_allowlisted
                }
                onClick={() => void activate()}
              >
                <ShieldCheckIcon /> Activate manual billing
              </ActionButton>
            </>
          }
        >
          <SummaryBox>
            <h3>Exact owner attestation</h3>
            <p>“{BILLING_MANUAL_REVIEW_ATTESTATION}”</p>
            <ul>
              <li>Activation is permanent and requires an empty ledger.</li>
              <li>Payments are recorded only after they happen elsewhere.</li>
              <li>
                Browser printing creates a local copy; CareSync does not deliver
                it.
              </li>
              <li>
                No processor, money movement, automatic issue, refund, or tax
                advice is enabled.
              </li>
            </ul>
          </SummaryBox>
          <ReviewAcknowledgment>
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(event) => setReviewed(event.currentTarget.checked)}
            />
            <span>
              I personally reviewed the exact attestation and understand this
              irreversible private, off-platform record boundary.
            </span>
          </ReviewAcknowledgment>
        </BillingDialog>
      )}
    </>
  );
}

export function BillingLedgerWorkspace() {
  const session = useSession();
  const capability = useBillingCapability();
  const organizationId = session.user?.organization_id || "";
  const actorId = session.user?.id || "";
  const billingWritable =
    capability.capability?.runtime_available === true &&
    (capability.capability.billing_mode === "sandbox" ||
      (capability.capability.billing_mode === "manual" &&
        capability.capability.manual_activated === true)) &&
    capability.capability.writes_available === true;
  const canManage =
    billingWritable &&
    hasExplicitPermission(session.user, ACCESS.billingManage);
  const canIssue =
    billingWritable && hasExplicitPermission(session.user, ACCESS.billingIssue);
  const canPayments =
    billingWritable &&
    hasExplicitPermission(session.user, ACCESS.billingPayments);
  const canAdjust =
    billingWritable &&
    hasExplicitPermission(session.user, ACCESS.billingAdjust);
  const canRecover =
    billingWritable &&
    hasExplicitPermission(session.user, ACCESS.billingRecover);
  const ownerCanActivate =
    session.user?.role?.key === "owner" &&
    hasExplicitPermission(session.user, ACCESS.billingManage);
  const [params, setParams] = useSearchParams();
  const rawFocus = params.get("focus") as BillingFocus | null;
  const focus = rawFocus && rawFocus in FOCUS_TABS ? rawFocus : null;
  const rawRecordId = params.get("record");
  const focusedRecordId =
    rawRecordId && RECORD_ID.test(rawRecordId) ? rawRecordId : null;
  const rawTab = params.get("view") as TabId | null;
  const tab: TabId = TAB_LABELS.some(([id]) => id === rawTab)
    ? rawTab!
    : focus
      ? FOCUS_TABS[focus]
      : "overview";
  const selectedAccountId =
    params.get("account") ||
    (focus === "billing_account" ? focusedRecordId : null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [readiness, setReadiness] = useState<BillingReadinessResponse | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [accountSearch, setAccountSearch] = useState("");
  const [invoiceSearch, setInvoiceSearch] = useState("");
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [dialogTarget, setDialogTarget] = useState<BillingDialogTarget | null>(
    null,
  );
  const [invoiceDetailId, setInvoiceDetailId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    message: string;
    warning?: boolean;
  } | null>(null);
  const [pending, setPending] = useState<PendingBillingOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshState, setRefreshState] = useState<
    "current" | "refreshing" | "stale"
  >("refreshing");
  const [sourceProgress, setSourceProgress] = useState("");
  const [pendingLookup, setPendingLookup] = useState<
    "idle" | "checking" | "not_found" | "unavailable"
  >("idle");
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [journalRevision, setJournalRevision] = useState(0);
  const workspaceLoadRef = useRef<Promise<number | undefined> | null>(null);
  const acceptedWorkspaceSequenceRef = useRef(-1);
  const workspaceIdentityRef = useRef(`${organizationId}:${actorId}`);

  useEffect(() => {
    workspaceIdentityRef.current = `${organizationId}:${actorId}`;
    acceptedWorkspaceSequenceRef.current = -1;
    workspaceLoadRef.current = null;
    setSnapshot(null);
    setReadiness(null);
    setPhase("loading");
    setRefreshState("refreshing");
    setError("");
    setSourceProgress("");
    setInvoiceDetailId(null);
  }, [actorId, organizationId]);

  useEffect(
    () => () => purgeVolatileBillingOperationInputs(organizationId, actorId),
    [actorId, organizationId],
  );
  useEffect(() => {
    if (!organizationId || !actorId) return;
    const key = billingOperationStorageKey(organizationId, actorId);
    const changed = (event: StorageEvent) => {
      if (event.storageArea === window.localStorage && event.key === key)
        setJournalRevision((current) => current + 1);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [actorId, organizationId]);

  const loadWorkspace = useCallback(
    (signal?: AbortSignal): Promise<number | undefined> => {
      if (
        !organizationId ||
        capability.phase !== "enabled" ||
        capability.capability?.runtime_available !== true
      )
        return Promise.resolve(undefined);
      if (workspaceLoadRef.current) return workspaceLoadRef.current;
      const requestIdentity = `${organizationId}:${actorId}`;
      const request = (async () => {
        const [workspace, families, enrollmentReadiness] = await Promise.all([
          billingApi.workspace(organizationId, signal),
          billingApi.familyOptions(organizationId, signal, (loaded, total) =>
            setSourceProgress(
              total
                ? `Loading billing choices ${loaded}/${total}…`
                : "Loading billing choices…",
              ),
          ),
          fetchBillingReadiness(organizationId, signal),
        ]);
        if (workspaceIdentityRef.current !== requestIdentity)
          throw new BillingApiError(
            "The billing identity changed while records were loading.",
          );
        if (
          workspace.data_through_realtime_sequence <
          acceptedWorkspaceSequenceRef.current
        )
          throw new BillingApiError(
            "The server returned an older billing checkpoint than the one already accepted.",
          );
        if (
          capability.capability?.billing_mode === "manual" &&
          capability.capability.manual_activated === true &&
          workspace.billing_mode !== "manual"
        )
          throw new BillingApiError(
            "The billing capability is active, but the canonical workspace has not reached the private manual boundary yet. Refresh before relying on financial records.",
            409,
          );
        if (
          enrollmentReadiness.data_through_realtime_sequence !==
          workspace.data_through_realtime_sequence
        )
          throw new BillingApiError(
            "Enrollment readiness and the billing ledger were loaded from different realtime checkpoints. Refresh before making a financial decision.",
            409,
          );
        acceptedWorkspaceSequenceRef.current =
          workspace.data_through_realtime_sequence;
        setReadiness(enrollmentReadiness);
        setSnapshot({
          billingMode: workspace.billing_mode,
          sandbox: workspace.sandbox,
          generatedAt: workspace.generated_at,
          dataThroughRealtimeSequence:
            workspace.data_through_realtime_sequence,
          canonicalCollectionLimit: workspace.canonical_collection_limit,
          snapshotToken: workspace.snapshot_token,
          provenanceLabel: workspace.provenance_label,
          overview: workspace.overview,
          accounts: workspace.accounts.items,
          payerVersions: workspace.payer_versions.items,
          invoices: workspace.invoices.items,
          payments: workspace.payments.items,
          allocations: workspace.allocations.items,
          credits: workspace.credits.items,
          ratePlans: workspace.rate_plans.items,
          agreements: workspace.agreements.items,
          families: families.items,
          programs: families.programs,
        });
        setPhase("ready");
        setRefreshState("current");
        setSourceProgress("");
        setError("");
        return workspace.data_through_realtime_sequence;
      })();
      workspaceLoadRef.current = request;
      const release = () => {
        if (workspaceLoadRef.current === request)
          workspaceLoadRef.current = null;
      };
      void request.then(release, release);
      return request;
    },
    [
      actorId,
      capability.capability?.billing_mode,
      capability.capability?.manual_activated,
      capability.phase,
      organizationId,
    ],
  );

  useEffect(() => {
    if (capability.phase !== "enabled") return;
    const controller = new AbortController();
    setPhase("loading");
    void loadWorkspace(controller.signal).catch((caught) => {
      if (!controller.signal.aborted) {
        setError(billingErrorMessage(caught));
        setPhase("error");
      }
    });
    return () => controller.abort();
  }, [capability.phase, loadWorkspace]);
  const accountDetail = useMemo<BillingAccountContext | null>(() => {
    if (!snapshot || !selectedAccountId) return null;
    const account = snapshot.accounts.find(
      (candidate) => candidate.id === selectedAccountId,
    );
    if (!account) return null;
    return {
      schema_version: "0033",
      organization_id: organizationId,
      currency: "CAD",
      account,
      payer_versions: snapshot.payerVersions.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
      invoices: snapshot.invoices.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
      payments: snapshot.payments.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
      agreements: snapshot.agreements.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
      allocations: snapshot.allocations.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
      credits: snapshot.credits.filter(
        (candidate) => candidate.billing_account_id === account.id,
      ),
    };
  }, [organizationId, selectedAccountId, snapshot]);
  const focusedRecordResolved = useMemo(() => {
    if (!snapshot || !focus || !focusedRecordId) return false;
    const ids: Partial<Record<BillingFocus, readonly string[]>> = {
      billing_account: snapshot.accounts.map((item) => item.id),
      billing_invoice: snapshot.invoices.map((item) => item.id),
      billing_payment: snapshot.payments.map((item) => item.id),
      billing_allocation: snapshot.allocations.map((item) => item.id),
      billing_credit: snapshot.credits.map((item) => item.id),
      billing_rate_plan: snapshot.ratePlans.map((item) => item.id),
      billing_agreement: snapshot.agreements.map((item) => item.id),
    };
    return ids[focus]?.includes(focusedRecordId) === true;
  }, [focus, focusedRecordId, snapshot]);
  const invoiceDetail = useMemo(
    () =>
      snapshot?.invoices.find((invoice) => invoice.id === invoiceDetailId) ||
      null,
    [invoiceDetailId, snapshot],
  );
  const effectDetail = useMemo(() => {
    if (!snapshot || !focus || !focusedRecordId) return null;
    if (focus === "billing_allocation")
      return {
        kind: "allocation" as const,
        record:
          snapshot.allocations.find((item) => item.id === focusedRecordId) ||
          null,
      };
    if (focus === "billing_credit")
      return {
        kind: "credit" as const,
        record:
          snapshot.credits.find((item) => item.id === focusedRecordId) || null,
      };
    return null;
  }, [focus, focusedRecordId, snapshot]);
  useEffect(() => {
    if (
      phase === "ready" &&
      focus === "billing_invoice" &&
      focusedRecordId &&
      focusedRecordResolved
    )
      setInvoiceDetailId(focusedRecordId);
  }, [focus, focusedRecordId, focusedRecordResolved, phase]);
  useEffect(() => {
    if (phase !== "ready" || !focusedRecordId || !focusedRecordResolved)
      return;
    const frame = window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>(
          `[data-billing-record="${focusedRecordId}"]`,
        )
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusedRecordId, focusedRecordResolved, phase, tab]);
  const [journalError, setJournalError] = useState("");
  useEffect(() => {
    if (!organizationId || !actorId) return;
    try {
      const operation = readPendingBillingOperation(organizationId, actorId);
      setPending(operation);
      setJournalError("");
      if (operation) {
        setPendingLookup("checking");
        void billingApi
          .reconcileCommand(
            organizationId,
            operation.client_operation_id,
            operation.command_kind,
            operation.request_hash,
          )
          .then(async (result) => {
            if (result === "prepared_not_committed") {
              setPendingLookup("not_found");
              setNotice({
                message:
                  "No committed receipt exists at this check. Retry the exact command, or explicitly finalize its absence before unlocking new work.",
                warning: true,
              });
              return;
            }
            if (result === "not_found") {
              setPendingLookup("unavailable");
              setNotice({
                message:
                  "The server has neither a receipt nor a preparation proof for this redacted operation. It remains locked for support review and cannot be finalized from this screen.",
                warning: true,
              });
              return;
            }
            clearPendingBillingOperation(operation);
            setPending(null);
            setPendingLookup("idle");
            setNotice({
              message:
                result === "finalized_absent"
                  ? "The server durably confirmed that the protected operation was not committed. New commands are unlocked."
                  : "The server confirmed the protected command receipt. Canonical records are refreshing.",
            });
            try {
              setRefreshState("refreshing");
              await loadWorkspace();
            } catch (caught) {
              setRefreshState("stale");
              setNotice({
                message: `The protected outcome is terminal and new commands are unlocked, but the current view is stale: ${billingErrorMessage(caught)} Refresh only.`,
                warning: true,
              });
            }
          })
          .catch((caught) => {
            setPendingLookup("unavailable");
            setNotice({
              message: `Protected command remains locked: ${billingErrorMessage(caught)}`,
              warning: true,
            });
          });
      } else setPendingLookup("idle");
    } catch (caught) {
      setPending(null);
      setJournalError(billingErrorMessage(caught));
    }
  }, [actorId, journalRevision, loadWorkspace, organizationId]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);
  useRealtimeRefresh({
    scope: "billing",
    organizationId,
    enabled:
      capability.phase === "enabled" &&
      capability.capability?.runtime_available === true,
    entityTypes: featureIntegrationManifest.billing.realtimeEntities,
    refresh: async (event) => {
      setRefreshState("refreshing");
      try {
        const throughSequence = await loadWorkspace();
        if (
          typeof throughSequence === "number" &&
          event.cursor > throughSequence
        )
          throw new BillingApiError(
            "A newer billing event exists beyond the loaded coherent snapshot. Refresh again before making a financial decision.",
          );
      } catch (caught) {
        setRefreshState("stale");
        setNotice({
          message: `A committed change arrived, but the current view could not refresh: ${billingErrorMessage(caught)}`,
          warning: true,
        });
        throw caught;
      }
    },
  });

  const navigate = (next: TabId, account?: string) => {
    const query = new URLSearchParams();
    query.set("view", next);
    if (account) query.set("account", account);
    setParams(query);
  };
  const commandWriteAllowed = (kind: BillingCommandKind): boolean => {
    switch (kind) {
      case "account.create":
      case "account.payer.assign":
      case "rate_plan.create":
      case "agreement.create":
        return canManage;
      case "invoice.issue":
        return canIssue;
      case "payment.record":
      case "payment.allocate":
        return canPayments;
      case "credit.create":
        return canAdjust;
    }
  };
  const executePending = useCallback(
    (
      operation: PendingBillingOperation,
      input: Record<string, unknown>,
      operationId: string,
    ): Promise<BillingCommandReceipt> => {
      switch (operation.command_kind) {
        case "account.create":
          return billingApi.createAccount(
            organizationId,
            operationId,
            input as unknown as CreateBillingAccountInput,
          );
        case "account.payer.assign": {
          const payerInput =
            input as unknown as AssignBillingAccountPayerOperationInput;
          return billingApi.assignAccountPayer(
            organizationId,
            payerInput.account_id,
            operationId,
            {
              account_id: payerInput.account_id,
              payer_guardian_id: payerInput.payer_guardian_id,
              expected_latest_payer_version_id:
                payerInput.expected_latest_payer_version_id,
              expected_latest_payer_version_number:
                payerInput.expected_latest_payer_version_number,
            },
          );
        }
        case "rate_plan.create":
          return billingApi.createRatePlan(
            organizationId,
            operationId,
            input as unknown as CreateRatePlanInput,
          );
        case "agreement.create":
          return billingApi.createAgreement(
            organizationId,
            operationId,
            input as unknown as CreateAgreementInput,
          );
        case "invoice.issue":
          return billingApi.issueInvoice(
            organizationId,
            operationId,
            input as unknown as IssueInvoiceInput,
          );
        case "payment.record":
          return billingApi.recordPayment(
            organizationId,
            operationId,
            input as unknown as RecordPaymentInput,
          );
        case "payment.allocate":
          return billingApi.allocatePayment(
            organizationId,
            operationId,
            input as unknown as AllocatePaymentInput,
          );
        case "credit.create":
          return billingApi.createCredit(
            organizationId,
            operationId,
            input as unknown as CreateCreditInput,
          );
      }
    },
    [organizationId],
  );
  const runCommand = async <T extends Record<string, unknown>>(
    kind: BillingCommandKind,
    input: T,
    execute: (operationId: string) => Promise<BillingCommandReceipt>,
  ) => {
    if (!commandWriteAllowed(kind)) {
      setNotice({
        message:
          "This financial change is disabled because the server did not certify both write readiness and the required finance permission.",
        warning: true,
      });
      return;
    }
    setBusy(true);
    let receipt: BillingCommandReceipt;
    try {
      receipt = await executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: kind,
        input,
        prepare: (operationId) =>
          billingApi.prepareCommand(organizationId, operationId, kind, input),
        execute,
      });
      setPending(null);
      setDialog(null);
      setDialogTarget(null);
      setNotice({
        message: `${titleCase(receipt.command_type)} committed${receipt.exact_retry ? " by exact safe replay" : ""}.`,
      });
      try {
        const destination = new URL(
          receipt.action_path,
          window.location.origin,
        );
        const receiptFocus = destination.searchParams.get(
          "focus",
        ) as BillingFocus | null;
        const receiptRecord = destination.searchParams.get("record");
        if (
          destination.origin === window.location.origin &&
          destination.pathname.endsWith("/billing") &&
          receiptFocus &&
          receiptFocus in FOCUS_TABS &&
          receiptRecord &&
          RECORD_ID.test(receiptRecord)
        )
          setParams({ focus: receiptFocus, record: receiptRecord });
      } catch {
        // The committed receipt remains terminal; an invalid destination is ignored.
      }
    } catch (caught) {
      if (
        caught instanceof BillingOperationOutcomeUnknownError ||
        caught instanceof BillingOperationLockedError
      ) {
        setPending(caught.pending);
        setDialog(null);
        setDialogTarget(null);
        setNotice({ message: caught.message, warning: true });
      } else if (caught instanceof BillingApiError && caught.status === 409) {
        setDialog(null);
        setDialogTarget(null);
        setNotice({
          message:
            "The command was not committed because canonical versions changed. Records are refreshing; reopen the command and review the new versions.",
          warning: true,
        });
        try {
          setRefreshState("refreshing");
          await loadWorkspace();
        } catch (refreshError) {
          setRefreshState("stale");
          setNotice({
            message: `The command was not committed, and canonical records could not refresh: ${billingErrorMessage(refreshError)}`,
            warning: true,
          });
        }
      } else
        setNotice({ message: billingErrorMessage(caught), warning: true });
      setBusy(false);
      return;
    }
    try {
      setRefreshState("refreshing");
      await loadWorkspace();
    } catch (caught) {
      setRefreshState("stale");
      setNotice({
        message: `${titleCase(receipt.command_type)} is committed. The current view is stale because refresh failed: ${billingErrorMessage(caught)} Use refresh only; do not create a new operation.`,
        warning: true,
      });
    } finally {
      setBusy(false);
    }
  };
  const retryPending = async () => {
    if (!pending) return;
    if (!commandWriteAllowed(pending.command_kind)) {
      setNotice({
        message:
          "The protected command remains locked, but exact retry is disabled until the server certifies this billing boundary as writable.",
        warning: true,
      });
      return;
    }
    const input = readVolatileBillingOperationInput(pending);
    if (!input) {
      setNotice({
        message:
          "This browser reload intentionally discarded the command fields. Check server status or finalize the prepared no-commit proof; private form values were not stored.",
        warning: true,
      });
      return;
    }
    await runCommand(pending.command_kind, input, (operationId) =>
      executePending(pending, input, operationId),
    );
  };
  const finalizePendingAbsence = async () => {
    if (!pending) return;
    if (!canRecover) {
      setNotice({
        message:
          "Absence finalization is disabled until the server certifies billing writes and the actor has the recovery permission.",
        warning: true,
      });
      return;
    }
    setBusy(true);
    let finalized = false;
    try {
      await withBillingOperationLock({
        organizationId,
        actorId,
        run: async () => {
          const current = readPendingBillingOperation(organizationId, actorId);
          if (
            !current ||
            current.client_operation_id !== pending.client_operation_id
          )
            throw new Error(
              "The protected operation changed in another tab. Refresh before continuing.",
            );
          await billingApi.finalizeCommandAbsence(organizationId, pending);
          clearPendingBillingOperation(pending);
        },
      });
      setPending(null);
      setPendingLookup("idle");
      setFinalizeOpen(false);
      setNotice({
        message:
          "The server durably finalized this operation as absent. New billing commands are unlocked.",
      });
      finalized = true;
    } catch (caught) {
      setNotice({
        message: `Absence was not finalized: ${billingErrorMessage(caught)}`,
        warning: true,
      });
    }
    if (finalized) {
      try {
        setRefreshState("refreshing");
        await loadWorkspace();
      } catch (caught) {
        setRefreshState("stale");
        setNotice({
          message: `The absence claim is committed and new commands are unlocked, but records are stale: ${billingErrorMessage(caught)} Refresh only.`,
          warning: true,
        });
      }
    }
    setBusy(false);
  };
  const dialogWriteAllowed = (kind: DialogKind): boolean => {
    const kindPermission: Record<DialogKind, boolean> = {
      account: canManage,
      payer: canManage,
      rate: canManage,
      agreement: canManage,
      invoice: canIssue,
      payment: canPayments,
      allocation: canPayments,
      credit: canAdjust,
    };
    return kindPermission[kind];
  };
  const openDialog = (
    kind: DialogKind,
    target: BillingDialogTarget | null = null,
  ) => {
    if (!dialogWriteAllowed(kind)) {
      setNotice({
        message:
          "This financial change is read-only because authoritative billing write readiness or the required permission is unavailable.",
        warning: true,
      });
      return;
    }
    setDialogTarget(target);
    setDialog(kind);
  };
  const closeDialog = () => {
    setDialog(null);
    setDialogTarget(null);
  };
  const openAgreement = () => openDialog("agreement");

  if (capability.phase === "checking")
    return (
      <Page>
        <State $accent="cyan">
          <div>
            <ArrowPathIcon />
            <h2>Checking the protected billing ledger</h2>
            <p>
              CareSync is confirming the organization, role, and deployed
              billing capability before requesting financial records.
            </p>
          </div>
        </State>
      </Page>
    );
  if (capability.phase === "error")
    return (
      <Page>
        <State $accent="amber">
          <div>
            <ExclamationTriangleIcon />
            <h2>Billing capability check failed</h2>
            <p>
              {capability.error ||
                "CareSync could not verify the protected billing capability."} The
              organization has not been treated as intentionally disabled, and no
              financial records or commands were requested.
            </p>
            <ActionButton type="button" onClick={capability.retry}>
              <ArrowPathIcon /> Retry capability check
            </ActionButton>
          </div>
        </State>
      </Page>
    );
  if (
    capability.phase === "disabled" ||
    !capability.capability?.runtime_available
  )
    return (
      <Page>
        <State $accent="amber">
          <div>
            <LockClosedIcon />
            <h2>Billing is unavailable</h2>
            <p>
              This workspace fails closed unless an active owner or
              administrator has billing access and the server confirms the
              ledger capability. Server mode:{" "}
              {capability.capability?.billing_mode
                ? titleCase(capability.capability.billing_mode)
                : "Unavailable"}
              .
            </p>
          </div>
        </State>
      </Page>
    );
  if (phase === "loading")
    return (
      <Page>
        <State $accent="cyan">
          <div>
            <ArrowPathIcon />
            <h2>Loading canonical billing records</h2>
            <p>
              {sourceProgress ||
                "Assembling accounts, agreements, invoices, payments, allocations, credits, rates, and current projections under one snapshot proof."}
            </p>
          </div>
        </State>
      </Page>
    );
  if (phase === "error" || !snapshot || !capability.capability)
    return (
      <Page>
        <State $accent="amber">
          <div>
            <ExclamationTriangleIcon />
            <h2>The billing workspace could not open</h2>
            <p>{error}</p>
            <ActionButton
              type="button"
              onClick={() => {
                setPhase("loading");
                void loadWorkspace().catch((caught) => {
                  setError(billingErrorMessage(caught));
                  setPhase("error");
                });
              }}
            >
              <ArrowPathIcon /> Try again
            </ActionButton>
          </div>
        </State>
      </Page>
    );

  const activeCapability = capability.capability;
  const writeUnavailableExplanation = activeCapability.writes_available
    ? null
    : activeCapability.billing_mode === "shadow"
      ? "The server is deliberately running this ledger in shadow mode. Canonical records are viewable, but every finance mutation, exact command retry, and absence-finalization recovery remains disabled."
      : activeCapability.billing_mode === "sandbox"
        ? "Canonical sandbox records are viewable, but the server did not certify every write condition: a writable PostgreSQL database, active Basic routes, tenant allowlisting, and a disposable-target attestation. Every finance mutation and recovery command remains disabled."
        : activeCapability.manual_activation_required
          ? "Private manual billing has not been activated by an owner. Real family and enrollment choices may be reviewed, but every finance mutation and recovery command remains disabled until the immutable off-platform boundary is accepted."
          : "Private manual billing is activated, but the server did not certify the writable PostgreSQL and organization boundary. Canonical records remain viewable; every finance mutation and recovery command is disabled.";
  const pendingInputAvailable = pending
    ? readVolatileBillingOperationInput(pending) !== null
    : false;
  const commandProjectionReady = refreshState === "current";
  const filteredAccounts = filterAccounts(
    sortAccountsForAction(snapshot.accounts),
    accountSearch,
  );
  const aging = deriveAging(
    snapshot.invoices,
    activeCapability.organization_local_date,
  );
  const overdue = snapshot.invoices.filter(
    (item) =>
      invoiceOutstanding(item) &&
      item.due_date < activeCapability.organization_local_date,
  );
  const unapplied = snapshot.payments.filter(paymentAvailable);
  const accountsWithoutAgreements = snapshot.accounts.filter(
    (account) =>
      !snapshot.agreements.some(
        (agreement) => agreement.billing_account_id === account.id,
      ),
  );
  return (
    <Page>
      <Header>
        <div>
          <Eyebrow>
            <BanknotesIcon width={15} /> Billing & finance · CAD ledger
          </Eyebrow>
          <h1>Receivables without guesswork</h1>
          <p>
            Reviewed care agreements become immutable invoices; off-platform
            payments are recorded and allocated with exact, retry-safe
            operations. Every view reloads from canonical organization-scoped
            records.
          </p>
        </div>
        <HeaderActions>
          <StatusChip $tone={refreshState === "stale" ? "warning" : "info"}>
            {titleCase(activeCapability.billing_mode)} ·{" "}
            {refreshState === "stale"
              ? "records stale"
              : refreshState === "refreshing"
                ? "refreshing records"
                : `coherent through event ${snapshot.dataThroughRealtimeSequence} · ${formatDateTime(snapshot.generatedAt)}`}
          </StatusChip>
          <ActionButton
            type="button"
            onClick={() => {
              setRefreshState("refreshing");
              void loadWorkspace().catch((caught) => {
                setRefreshState("stale");
                setNotice({
                  message: billingErrorMessage(caught),
                  warning: true,
                });
              });
            }}
          >
            <ArrowPathIcon /> Refresh
          </ActionButton>
        </HeaderActions>
      </Header>
      {activeCapability.billing_mode === "manual" && (
        <ManualBillingActivationBoundary
          organizationId={organizationId}
          activated={activeCapability.manual_activated}
          ownerCanActivate={ownerCanActivate}
          onCapabilityRefresh={capability.retry}
        />
      )}
      <Boundary $accent="amber">
        <ExclamationTriangleIcon />
        <div>
          <h2>
            {activeCapability.billing_mode === "sandbox"
              ? "Synthetic sandbox — not real invoices or payments"
              : activeCapability.billing_mode === "manual"
                ? activeCapability.manual_activated
                  ? "Private manual records — off-platform billing only"
                  : "Private manual ledger — activation pending"
                : "Read-only shadow ledger — financial commands disabled"}
          </h2>
          <p>
            {activeCapability.billing_mode === "manual"
              ? "This private ledger records invoices and payments that are reviewed or completed off-platform. Browser printing is local only: CareSync does not deliver documents, process payments, move money, issue automatically, refund funds, or provide tax advice. "
              : "This 0033 foundation does not process or move real money. PDF delivery, email, processor, refund, bank movement, tax, and production export capabilities are unavailable. "}
            Canonical history was assembled across every server page under
            snapshot proof {snapshot.snapshotToken.slice(0, 12)}…; each request
            is bounded to {snapshot.canonicalCollectionLimit} records and the
            entire workspace fails closed on any page drift, overlap, or gap.
          </p>
        </div>
        <StatusChip $tone="warning">
          {titleCase(activeCapability.billing_mode)}
        </StatusChip>
      </Boundary>
      {writeUnavailableExplanation && (
        <Boundary $accent="amber">
          <LockClosedIcon />
          <div>
            <h2>Canonical billing is viewable, but financial writes are unavailable</h2>
            <p>{writeUnavailableExplanation}</p>
          </div>
          <StatusChip $tone="warning">
            {activeCapability.billing_mode === "shadow"
              ? "Shadow · read only"
              : activeCapability.billing_mode === "manual" &&
                  activeCapability.manual_activation_required
                ? "Owner activation required"
                : "Write target not certified"}
          </StatusChip>
        </Boundary>
      )}
      {pending && (
        <Recovery $accent="amber">
          <div>
            <h2>One command has an unconfirmed outcome</h2>
            <p>
              {titleCase(pending.command_kind)} · redacted operation{" "}
              {pending.client_operation_id}. All other financial changes are
              locked in this browser profile. Only the server-issued hash and
              routing proof are stored here—never payer notes, memo text, or
              form payloads.
            </p>
          </div>
          <InlineButtons>
            {pendingLookup === "not_found" && canRecover && (
              <ActionButton
                type="button"
                disabled={busy}
                onClick={() => setFinalizeOpen(true)}
              >
                Finalize no commit
              </ActionButton>
            )}
            {pendingInputAvailable && (
              <ActionButton
                type="button"
                $variant="primary"
                disabled={busy || !commandWriteAllowed(pending.command_kind)}
                onClick={() => void retryPending()}
              >
                <ArrowPathIcon /> Retry this-session command
              </ActionButton>
            )}
          </InlineButtons>
        </Recovery>
      )}
      {journalError && (
        <Recovery $accent="amber">
          <div>
            <h2>Protected command recovery needs attention</h2>
            <p>
              {journalError} No new financial command can be sent from this
              browser profile.
            </p>
          </div>
          <StatusChip $tone="warning">Locked</StatusChip>
        </Recovery>
      )}
      <Boundary $accent="cyan">
        <ShieldCheckIcon />
        <div>
          <h2>Manual ledger boundary</h2>
          <p>
            No card processor, money movement, automatic invoice issue, refunds,
            email delivery, or tax advice is active. Tax remains 0 until a
            qualified configuration is approved.
          </p>
        </div>
        <StatusChip $tone="info">
          Private ledger · {titleCase(activeCapability.billing_mode)} mode · off-platform
        </StatusChip>
      </Boundary>
      <Tabs aria-label="Billing sections">
        {TAB_LABELS.map(([id, label]) => (
          <Tab
            key={id}
            type="button"
            $active={tab === id}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => navigate(id)}
          >
            {label}
          </Tab>
        ))}
      </Tabs>
      {focus && focusedRecordId && !focusedRecordResolved && (
        <Boundary $accent="amber">
          <ExclamationTriangleIcon />
          <div>
            <h2>{titleCase(focus)} reference is unavailable</h2>
            <p>
              CareSync cannot prove record {focusedRecordId} exists in the
              loaded canonical workspace. Refresh the ledger and review the
              related account before relying on this link. No unproven ledger
              effect is displayed.
            </p>
          </div>
        </Boundary>
      )}
      {tab === "overview" && (
        <OverviewTab
          snapshot={snapshot}
          aging={aging}
          overdue={overdue}
          unapplied={unapplied}
          missing={accountsWithoutAgreements}
          onNavigate={navigate}
        />
      )}
      {tab === "accounts" && (
        <AccountsTab
          accounts={filteredAccounts}
          families={snapshot.families}
          payerVersions={snapshot.payerVersions}
          search={accountSearch}
          onSearch={setAccountSearch}
          detail={selectedAccountId ? accountDetail : null}
          onNavigate={navigate}
          canCreate={
            canManage &&
            commandProjectionReady &&
            !pending &&
            !journalError &&
            snapshot.families.some(
              (family) =>
                !snapshot.accounts.some(
                  (account) => account.family_id === family.id,
                ) && family.guardians.length,
            )
          }
          canManage={
            canManage && commandProjectionReady && !pending && !journalError
          }
          canRecord={
            canPayments && commandProjectionReady && !pending && !journalError
          }
          onCreate={() => openDialog("account")}
          onPayer={(account) => openDialog("payer", { kind: "payer", account })}
          onPayment={() => openDialog("payment")}
          onOpenEffect={(effectFocus, recordId) =>
            setParams({ focus: effectFocus, record: recordId })
          }
        />
      )}
      {tab === "invoices" && (
        <InvoicesTab
          invoices={snapshot.invoices}
          payerVersions={snapshot.payerVersions}
          focusedRecordId={focus === "billing_invoice" ? focusedRecordId : null}
          search={invoiceSearch}
          onSearch={setInvoiceSearch}
          canIssue={
            canIssue &&
            commandProjectionReady &&
            !pending &&
            !journalError &&
            snapshot.agreements.length > 0
          }
          canAdjust={
            canAdjust && commandProjectionReady && !pending && !journalError
          }
          onIssue={() => openDialog("invoice")}
          onCredit={() => openDialog("credit")}
          onOpenInvoice={(invoice) => {
            setInvoiceDetailId(invoice.id);
            setParams({ focus: "billing_invoice", record: invoice.id });
          }}
        />
      )}
      {tab === "payments" && (
        <PaymentsTab
          payments={snapshot.payments}
          allocations={snapshot.allocations}
          invoices={snapshot.invoices}
          focusedRecordId={focus === "billing_payment" ? focusedRecordId : null}
          accounts={snapshot.accounts}
          canRecord={
            canPayments && commandProjectionReady && !pending && !journalError
          }
          onRecord={() => openDialog("payment")}
          onAllocate={() => openDialog("allocation")}
          onOpenAllocation={(recordId) =>
            setParams({ focus: "billing_allocation", record: recordId })
          }
        />
      )}
      {tab === "rates" && (
        <RatesTab
          rates={snapshot.ratePlans}
          agreements={snapshot.agreements}
          accounts={snapshot.accounts}
          programs={snapshot.programs}
          focusedRecordId={focusedRecordId}
          focus={focus}
          canManage={
            canManage && commandProjectionReady && !pending && !journalError
          }
          onRate={() => openDialog("rate")}
          onAgreement={openAgreement}
          onReviseRate={(rate) => openDialog("rate", { kind: "rate", rate })}
          onReviseAgreement={(agreement) =>
            openDialog("agreement", { kind: "agreement", agreement })
          }
        />
      )}
      {tab === "reports" && readiness && <ReportsTab snapshot={snapshot} aging={aging} readiness={readiness} />}
      {dialog && (
        <CommandDialog
          key={`${dialog}:${
            dialogTarget?.kind === "payer"
              ? dialogTarget.account.id
              : dialogTarget?.kind === "rate"
                ? dialogTarget.rate.id
                : dialogTarget?.kind === "agreement"
                  ? dialogTarget.agreement.id
                  : "new"
          }`}
          kind={dialog}
          target={dialogTarget}
          snapshot={snapshot}
          busy={busy}
          writeAllowed={dialogWriteAllowed(dialog)}
          onClose={() => !busy && closeDialog()}
          onRun={runCommand}
        />
      )}
      {invoiceDetail && (
        <InvoiceDetailDialog
          invoice={invoiceDetail}
          snapshot={snapshot}
          onOpenEffect={(effectFocus, recordId) => {
            setInvoiceDetailId(null);
            setParams({ focus: effectFocus, record: recordId });
          }}
          onClose={() => {
            setInvoiceDetailId(null);
            if (focus === "billing_invoice") navigate("invoices");
          }}
        />
      )}
      {effectDetail?.kind === "allocation" && effectDetail.record && (
        <BillingEffectDetailDialog
          kind="allocation"
          record={effectDetail.record}
          snapshot={snapshot}
          onOpenRecord={(nextFocus, recordId) =>
            setParams({ focus: nextFocus, record: recordId })
          }
          onClose={() => navigate(FOCUS_TABS[focus!])}
        />
      )}
      {effectDetail?.kind === "credit" && effectDetail.record && (
        <BillingEffectDetailDialog
          kind="credit"
          record={effectDetail.record}
          snapshot={snapshot}
          onOpenRecord={(nextFocus, recordId) =>
            setParams({ focus: nextFocus, record: recordId })
          }
          onClose={() => navigate(FOCUS_TABS[focus!])}
        />
      )}
      {finalizeOpen && pending && (
        <BillingDialog
          title="Finalize operation as not committed?"
          description="This writes a durable server-side absence claim for this exact actor and operation. The same UUID can never be posted afterward."
          busy={busy}
          onClose={() => !busy && setFinalizeOpen(false)}
          footer={
            <>
              <ActionButton
                type="button"
                disabled={busy}
                onClick={() => setFinalizeOpen(false)}
              >
                Keep locked
              </ActionButton>
              <ActionButton
                type="button"
                $variant="danger"
                disabled={busy || !canRecover}
                onClick={() => void finalizePendingAbsence()}
              >
                Finalize absence
              </ActionButton>
            </>
          }
        >
          <SummaryBox>
            <h3>Permanent recovery decision</h3>
            <p>
              Continue only because the actor-bound lookup returned no committed
              receipt. A server-detected commit rejects this decision and
              preserves the lock.
            </p>
            <ul>
              <li>{titleCase(pending.command_kind)}</li>
              <li>Operation {pending.client_operation_id}</li>
              <li>
                Browser-profile recovery remains intact until server acceptance
              </li>
            </ul>
          </SummaryBox>
        </BillingDialog>
      )}
      {notice && (
        <Notice role="status" $warning={notice.warning}>
          {notice.message}
        </Notice>
      )}
    </Page>
  );
}

function OverviewTab({
  snapshot,
  aging,
  overdue,
  unapplied,
  missing,
  onNavigate,
}: {
  snapshot: Snapshot;
  aging: Aging;
  overdue: BillingInvoice[];
  unapplied: BillingPayment[];
  missing: BillingAccountSummary[];
  onNavigate: (tab: TabId, account?: string) => void;
}) {
  const [showAllActions, setShowAllActions] = useState(false);
  const work: Array<{
    id: string;
    title: string;
    detail: string;
    tab: TabId;
    account?: string;
  }> = [
    ...overdue.map((item) => {
      const payerVersion = snapshot.payerVersions.find(
        (version) => version.id === item.billing_account_payer_version_id,
      );
      return {
        id: item.id,
        title: `${item.family_name} invoice is overdue`,
        detail: `${item.invoice_number} · payer snapshot ${item.payer_name} · assignment v${payerVersion?.version_number ?? "?"} · ${formatCadMinor(item.outstanding_minor)} due ${formatDateOnly(item.due_date)}`,
        tab: "accounts" as TabId,
        account: item.billing_account_id,
      };
    }),
    ...unapplied.map((item) => ({
      id: item.id,
      title: "Payment needs allocation",
      detail: `${formatCadMinor(item.unapplied_minor)} remains unapplied · ${titleCase(item.method)}`,
      tab: "payments" as TabId,
    })),
    ...missing.map((item) => ({
      id: item.id,
      title: `${item.family_name} needs an agreement`,
      detail: `${item.account_number} has no reviewed care agreement`,
      tab: "rates" as TabId,
    })),
  ];
  const visibleWork = showAllActions ? work : work.slice(0, 12);
  return (
    <>
      <Stats>
        <Stat $accent="plasma">
          <span>Outstanding</span>
          <strong>{formatCadMinor(snapshot.overview.outstanding_minor)}</strong>
          <small>Issued family responsibility</small>
        </Stat>
        <Stat $accent="cyan">
          <span>Payments recorded</span>
          <strong>
            {formatCadMinor(snapshot.overview.settled_payments_minor)}
          </strong>
          <small>Off-platform receipts</small>
        </Stat>
        <Stat $accent="amber">
          <span>Unapplied</span>
          <strong>
            {formatCadMinor(snapshot.overview.unapplied_payments_minor)}
          </strong>
          <small>Needs invoice allocation</small>
        </Stat>
        <Stat>
          <span>Accounts</span>
          <strong>{snapshot.overview.open_account_count}</strong>
          <small>
            {snapshot.overview.issued_invoice_count} issued invoices
          </small>
        </Stat>
      </Stats>
      <Grid>
        <Panel>
          <PanelHeader>
            <div>
              <h2>Action queue</h2>
              <p>Exceptions assembled from current canonical records.</p>
            </div>
            <StatusChip $tone={work.length ? "warning" : "success"}>
              {work.length} item{work.length === 1 ? "" : "s"}
            </StatusChip>
          </PanelHeader>
          {work.length ? (
            <WorkList>
              {visibleWork.map((item) => (
                <WorkRow
                  key={`${item.title}-${item.id}`}
                  type="button"
                  onClick={() => onNavigate(item.tab, item.account)}
                >
                  <ExclamationTriangleIcon />
                  <span className="copy">
                    <strong>{item.title}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <ChevronRightIcon className="arrow" />
                </WorkRow>
              ))}
              {work.length > 12 && (
                <ActionButton
                  type="button"
                  aria-expanded={showAllActions}
                  onClick={() => setShowAllActions((current) => !current)}
                >
                  {showAllActions
                    ? "Show first 12 actions"
                    : `View all ${work.length} actions`}
                </ActionButton>
              )}
            </WorkList>
          ) : (
            <Empty>
              No current receivable or allocation exception was detected in the
              loaded canonical window.
            </Empty>
          )}
        </Panel>
        <Panel>
          <PanelHeader>
            <div>
              <h2>Receivable aging</h2>
              <p>
                Derived locally from immutable invoice due dates and current
                outstanding balances.
              </p>
            </div>
          </PanelHeader>
          <AgingBar>
            {[
              ["Current", aging.current],
              ["1–30 days", aging.days30],
              ["31–60 days", aging.days60],
              ["61–90 days", aging.days90],
              ["91+ days", aging.older],
            ].map(([label, amount]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <strong>{formatCadMinor(Number(amount))}</strong>
              </div>
            ))}
          </AgingBar>
        </Panel>
      </Grid>
    </>
  );
}

function AccountsTab({
  accounts,
  families,
  payerVersions,
  search,
  onSearch,
  detail,
  onNavigate,
  canCreate,
  canManage,
  canRecord,
  onCreate,
  onPayer,
  onPayment,
  onOpenEffect,
}: {
  accounts: BillingAccountSummary[];
  families: BillingFamilyOption[];
  payerVersions: BillingAccountPayerVersion[];
  search: string;
  onSearch: (value: string) => void;
  detail: BillingAccountContext | null;
  onNavigate: (tab: TabId, account?: string) => void;
  canCreate: boolean;
  canManage: boolean;
  canRecord: boolean;
  onCreate: () => void;
  onPayer: (account: BillingAccountSummary) => void;
  onPayment: () => void;
  onOpenEffect: (
    focus: "billing_allocation" | "billing_credit",
    recordId: string,
  ) => void;
}) {
  if (detail) {
    const rows = [
      ...detail.invoices.map((item) => ({
        id: item.id,
        at: item.issued_at,
        kind: "Invoice issued",
        ref: item.invoice_number,
        payer: item.payer_name,
        debit: item.total_minor,
        credit: 0,
        detail: `${item.lines.length} agreement line${item.lines.length === 1 ? "" : "s"} · ${titleCase(item.lifecycle_status)}`,
      })),
      ...detail.payments.map((item) => ({
        id: item.id,
        at: item.received_at,
        kind: "Payment recorded",
        ref: item.external_reference,
        payer: item.payer_name,
        debit: 0,
        credit: item.amount_minor,
        detail: `${formatCadMinor(item.allocated_minor)} allocated · ${formatCadMinor(item.unapplied_minor)} unapplied`,
      })),
      ...detail.allocations.map((item) => {
        const payment = detail.payments.find(
          (candidate) => candidate.id === item.payment_id,
        );
        const invoice = detail.invoices.find(
          (candidate) => candidate.id === item.invoice_id,
        );
        return {
          id: item.id,
          at: item.allocated_at,
          kind: "Payment allocated",
          ref: invoice?.invoice_number || item.invoice_id,
          payer: payment?.payer_name || "Recorded payer unavailable",
          debit: 0,
          credit: 0,
          detail: `${formatCadMinor(item.amount_minor)} applied · actor ${item.allocated_by_user_id} · operation ${item.client_operation_id} · hash ${item.request_hash.slice(0, 12)}…`,
          focus: "billing_allocation" as const,
        };
      }),
      ...detail.credits.map((item) => {
        const invoice = detail.invoices.find(
          (candidate) => candidate.id === item.invoice_id,
        );
        return {
          id: item.id,
          at: item.issued_at,
          kind: "Credit issued",
          ref: invoice?.invoice_number || item.invoice_id,
          payer: invoice?.payer_name || "Invoice payer unavailable",
          debit: 0,
          credit: item.amount_minor,
          detail: `${titleCase(item.reason_code)} · actor ${item.issued_by_user_id} · operation ${item.client_operation_id} · hash ${item.request_hash.slice(0, 12)}…`,
          focus: "billing_credit" as const,
        };
      }),
    ].sort((a, b) => b.at.localeCompare(a.at));
    return (
      <>
        <BackButton type="button" onClick={() => onNavigate("accounts")}>
          <ArrowLeftIcon /> Back to family accounts
        </BackButton>
        <AccountHero $accent="plasma">
          <div>
            <Eyebrow>{detail.account.account_number}</Eyebrow>
            <h2>{detail.account.family_name}</h2>
            <p>
              Opened {formatDateTime(detail.account.opened_at)} · immutable
              invoice and receipt activity
            </p>
            <CurrentAccountPayer
              account={detail.account}
              families={families}
              payerVersions={payerVersions}
              detail
            />
          </div>
          <InlineButtons>
            <StatusChip $tone="success">Open</StatusChip>
            <ActionButton
              type="button"
              disabled={!canManage}
              onClick={() => onPayer(detail.account)}
            >
              Change payer
            </ActionButton>
            <ActionButton
              type="button"
              disabled={!canRecord}
              onClick={onPayment}
            >
              <PlusIcon /> Record payment
            </ActionButton>
          </InlineButtons>
        </AccountHero>
        <Stats>
          <Stat>
            <span>Invoiced</span>
            <strong>{formatCadMinor(detail.account.invoiced_minor)}</strong>
          </Stat>
          <Stat>
            <span>Allocated</span>
            <strong>{formatCadMinor(detail.account.allocated_minor)}</strong>
          </Stat>
          <Stat>
            <span>Credits</span>
            <strong>{formatCadMinor(detail.account.credits_minor)}</strong>
          </Stat>
          <Stat $accent="amber">
            <span>Outstanding</span>
            <strong>{formatCadMinor(detail.account.outstanding_minor)}</strong>
            <small>
              {formatCadMinor(detail.account.unapplied_minor)} unapplied
            </small>
          </Stat>
        </Stats>
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <th>Posted</th>
                <th>Activity</th>
                <th>Reference</th>
                <th>Payer</th>
                <th className="money">Debit</th>
                <th className="money">Credit</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => (
                  <tr key={`${row.kind}-${row.id}`}>
                    <td data-label="Posted">{formatDateTime(row.at)}</td>
                    <td data-label="Entry">
                      <strong>{row.kind}</strong>
                      <small>{row.detail}</small>
                    </td>
                    <td data-label="Reference">
                      {"focus" in row && row.focus ? (
                        <SmallButton
                          type="button"
                          onClick={() => onOpenEffect(row.focus, row.id)}
                          aria-label={`Open ${row.kind.toLowerCase()} ${row.id}`}
                        >
                          {row.ref}
                        </SmallButton>
                      ) : (
                        row.ref
                      )}
                    </td>
                    <td data-label="Payer">{row.payer}</td>
                    <td data-label="Debit" className="money">
                      {row.debit ? formatCadMinor(row.debit) : "—"}
                    </td>
                    <td data-label="Credit" className="money">
                      {row.credit ? formatCadMinor(row.credit) : "—"}
                    </td>
                  </tr>
                ))
              ) : (
                <EmptyRow colSpan={6}>
                  No invoice or receipt activity is available.
                </EmptyRow>
              )}
            </tbody>
          </Table>
        </TableWrap>
      </>
    );
  }
  return (
    <>
      <Toolbar>
        <Search>
          <MagnifyingGlassIcon />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search family or account number"
            aria-label="Search family billing accounts"
          />
        </Search>
        <ActionButton
          type="button"
          $variant="primary"
          disabled={!canCreate}
          onClick={onCreate}
        >
          <PlusIcon /> Open family account
        </ActionButton>
      </Toolbar>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Family account</th>
              <th>Current payer</th>
              <th>Status</th>
              <th className="money">Outstanding</th>
              <th className="money">Unapplied</th>
              <th className="action">Action</th>
            </tr>
          </thead>
          <tbody>
            {accounts.length ? (
              accounts.map((account) => (
                <tr key={account.id}>
                  <td data-label="Family">
                    <strong>{account.family_name}</strong>
                    <small>{account.account_number}</small>
                  </td>
                  <td data-label="Current payer">
                    <CurrentAccountPayer
                      account={account}
                      families={families}
                      payerVersions={payerVersions}
                    />
                  </td>
                  <td data-label="Status">
                    <StatusChip $tone="success">Open</StatusChip>
                  </td>
                  <td data-label="Outstanding" className="money">
                    {formatCadMinor(account.outstanding_minor)}
                  </td>
                  <td data-label="Unapplied" className="money">
                    {formatCadMinor(account.unapplied_minor)}
                  </td>
                  <td data-label="Action" className="action">
                    <SmallButton
                      type="button"
                      onClick={() => onNavigate("accounts", account.id)}
                    >
                      Open account
                    </SmallButton>
                  </td>
                </tr>
              ))
            ) : (
              <EmptyRow colSpan={6}>
                No family billing account matches this view.
              </EmptyRow>
            )}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}

function InvoicesTab({
  invoices,
  payerVersions,
  focusedRecordId,
  search,
  onSearch,
  canIssue,
  canAdjust,
  onIssue,
  onCredit,
  onOpenInvoice,
}: {
  invoices: BillingInvoice[];
  payerVersions: BillingAccountPayerVersion[];
  focusedRecordId: string | null;
  search: string;
  onSearch: (value: string) => void;
  canIssue: boolean;
  canAdjust: boolean;
  onIssue: () => void;
  onCredit: () => void;
  onOpenInvoice: (invoice: BillingInvoice) => void;
}) {
  const query = search.trim().toLowerCase();
  const filtered = invoices.filter(
    (item) =>
      !query ||
      [item.family_name, item.invoice_number, item.payer_name].some((value) =>
        value.toLowerCase().includes(query),
      ),
  );
  return (
    <>
      <Toolbar>
        <Search>
          <MagnifyingGlassIcon />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search invoice, family, or payer"
            aria-label="Search invoices"
          />
        </Search>
        <InlineButtons>
          {canAdjust && (
            <ActionButton type="button" onClick={onCredit}>
              Issue credit
            </ActionButton>
          )}
          <ActionButton
            type="button"
            $variant="primary"
            disabled={!canIssue}
            onClick={onIssue}
          >
            <DocumentTextIcon /> Issue from agreements
          </ActionButton>
        </InlineButtons>
      </Toolbar>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Invoice</th>
              <th>Service period</th>
              <th>Status</th>
              <th className="money">Total</th>
              <th className="money">Outstanding</th>
              <th className="action">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length ? (
              filtered.map((item) => {
                const payerVersion = payerVersions.find(
                  (version) =>
                    version.id === item.billing_account_payer_version_id,
                );
                return (
                  <tr
                    key={item.id}
                    data-focused={item.id === focusedRecordId}
                    data-billing-record={item.id}
                  >
                  <td data-label="Invoice">
                    <strong>{item.invoice_number}</strong>
                    <small>
                      {item.family_name} · {item.payer_name}
                      <br />
                      Immutable payer assignment v
                      {payerVersion?.version_number ?? "?"}
                    </small>
                  </td>
                  <td data-label="Period">
                    {formatDateOnly(item.service_period_start)} –{" "}
                    {formatDateOnly(item.service_period_end)}
                    <small>Due {formatDateOnly(item.due_date)}</small>
                  </td>
                  <td data-label="Status">
                    <StatusChip $tone={statusTone(item.lifecycle_status)}>
                      {titleCase(item.lifecycle_status)}
                    </StatusChip>
                  </td>
                  <td data-label="Total" className="money">
                    {formatCadMinor(item.total_minor)}
                  </td>
                  <td data-label="Outstanding" className="money">
                    {formatCadMinor(item.outstanding_minor)}
                  </td>
                  <td data-label="Action" className="action">
                    <SmallButton
                      type="button"
                      onClick={() => onOpenInvoice(item)}
                      aria-label={`Open invoice ${item.invoice_number}`}
                    >
                      Open invoice
                    </SmallButton>
                  </td>
                  </tr>
                );
              })
            ) : (
              <EmptyRow colSpan={6}>No invoices match this view.</EmptyRow>
            )}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}

function PaymentsTab({
  payments,
  allocations,
  invoices,
  focusedRecordId,
  accounts,
  canRecord,
  onRecord,
  onAllocate,
  onOpenAllocation,
}: {
  payments: BillingPayment[];
  allocations: BillingAllocation[];
  invoices: BillingInvoice[];
  focusedRecordId: string | null;
  accounts: BillingAccountSummary[];
  canRecord: boolean;
  onRecord: () => void;
  onAllocate: () => void;
  onOpenAllocation: (recordId: string) => void;
}) {
  const family = (id: string) =>
    accounts.find((item) => item.id === id)?.family_name || "Family account";
  return (
    <>
      <Toolbar>
        <div>
          <strong>Payment activity</strong>
        </div>
        <InlineButtons>
          <ActionButton
            type="button"
            disabled={!canRecord || !payments.some(paymentAvailable)}
            onClick={onAllocate}
          >
            Allocate payment
          </ActionButton>
          <ActionButton
            type="button"
            $variant="primary"
            disabled={!canRecord || !accounts.length}
            onClick={onRecord}
          >
            <PlusIcon /> Record payment
          </ActionButton>
        </InlineButtons>
      </Toolbar>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Received</th>
              <th>Family</th>
              <th>Actual payer</th>
              <th>Method</th>
              <th>Status</th>
              <th className="money">Amount</th>
              <th className="money">Unapplied</th>
              <th>Allocation effects</th>
            </tr>
          </thead>
          <tbody>
            {payments.length ? (
              payments.map((item) => {
                const effects = allocations.filter(
                  (allocation) => allocation.payment_id === item.id,
                );
                return (
                  <tr
                    key={item.id}
                    data-focused={item.id === focusedRecordId}
                    data-billing-record={item.id}
                  >
                  <td data-label="Received">
                    {formatDateTime(item.received_at)}
                    <small>
                      {item.external_reference}
                    </small>
                  </td>
                  <td data-label="Family">{family(item.billing_account_id)}</td>
                  <td data-label="Actual payer">{item.payer_name}</td>
                  <td data-label="Method">{titleCase(item.method)}</td>
                  <td data-label="Status">
                    <StatusChip $tone={statusTone(item.lifecycle_status)}>
                      {titleCase(item.lifecycle_status)}
                    </StatusChip>
                  </td>
                  <td data-label="Amount" className="money">
                    {formatCadMinor(item.amount_minor)}
                  </td>
                  <td data-label="Unapplied" className="money">
                    {formatCadMinor(item.unapplied_minor)}
                  </td>
                  <td data-label="Allocation effects">
                    {effects.length ? (
                      <InlineButtons>
                        {effects.map((effect) => {
                          const invoice = invoices.find(
                            (candidate) => candidate.id === effect.invoice_id,
                          );
                          return (
                            <SmallButton
                              key={effect.id}
                              type="button"
                              onClick={() => onOpenAllocation(effect.id)}
                              aria-label={`Open allocation ${effect.id}`}
                            >
                              {formatCadMinor(effect.amount_minor)} →{" "}
                              {invoice?.invoice_number || "invoice"}
                            </SmallButton>
                          );
                        })}
                      </InlineButtons>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
                );
              })
            ) : (
              <EmptyRow colSpan={8}>No payments have been recorded.</EmptyRow>
            )}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}

function RatesTab({
  rates,
  agreements,
  accounts,
  programs,
  focusedRecordId,
  focus,
  canManage,
  onRate,
  onAgreement,
  onReviseRate,
  onReviseAgreement,
}: {
  rates: BillingRatePlan[];
  agreements: BillingAgreement[];
  accounts: BillingAccountSummary[];
  programs: BillingProgramOption[];
  focusedRecordId: string | null;
  focus: BillingFocus | null;
  canManage: boolean;
  onRate: () => void;
  onAgreement: () => void;
  onReviseRate: (rate: BillingRatePlan) => void;
  onReviseAgreement: (agreement: BillingAgreement) => void;
}) {
  const family = (id: string) =>
    accounts.find((item) => item.id === id)?.family_name || "Family account";
  const programScope = (rate: BillingRatePlan) => {
    const program = programs.find(
      (item) => item.program_id === rate.program_id,
    );
    return program
      ? `${program.facility_name} · ${program.program_name}`
      : "Program scope unavailable";
  };
  return (
    <Grid>
      <Panel>
        <PanelHeader>
          <div>
            <h2>Published rate plans</h2>
            <p>Effective-dated versions; prior prices are never overwritten.</p>
          </div>
          <ActionButton type="button" disabled={!canManage} onClick={onRate}>
            <PlusIcon /> New rate plan
          </ActionButton>
        </PanelHeader>
        <WorkList>
          {rates.length ? (
            rates.map((item) => (
              <WorkRow
                key={item.id}
                type="button"
                disabled={!canManage}
                onClick={() => onReviseRate(item)}
                aria-label={`Publish a new version of ${item.name}`}
                data-focused={
                  focus === "billing_rate_plan" && item.id === focusedRecordId
                }
                data-billing-record={item.id}
              >
                <ReceiptPercentIcon />
                <span className="copy">
                  <strong>
                    {item.name} · {item.code}
                  </strong>
                  <small>
                    {programScope(item)} · {titleCase(item.program_type)} ·{" "}
                    {formatCadMinor(item.latest_version.unit_amount_minor)} /{" "}
                    {item.latest_version.billing_unit} · from{" "}
                    {formatDateOnly(item.latest_version.effective_from)}
                  </small>
                </span>
                <StatusChip $tone="success">
                  {canManage ? "Revise" : "Version"} v
                  {item.latest_version.version_number}
                </StatusChip>
              </WorkRow>
            ))
          ) : (
            <Empty>No published rate plans yet.</Empty>
          )}
        </WorkList>
      </Panel>
      <Panel>
        <PanelHeader>
          <div>
            <h2>Reviewed care agreements</h2>
            <p>
              Child-specific family and funding responsibility pinned to a rate
              version.
            </p>
          </div>
          <ActionButton
            type="button"
            disabled={!canManage || !rates.length || !accounts.length}
            onClick={onAgreement}
          >
            <PlusIcon /> New agreement
          </ActionButton>
        </PanelHeader>
        <WorkList>
          {agreements.length ? (
            agreements.map((item) => (
              <WorkRow
                key={item.id}
                type="button"
                disabled={!canManage}
                onClick={() => onReviseAgreement(item)}
                aria-label={`Publish a new agreement version for ${item.child_name}`}
                data-focused={
                  focus === "billing_agreement" && item.id === focusedRecordId
                }
                data-billing-record={item.id}
              >
                <ClipboardDocumentCheckIcon />
                <span className="copy">
                  <strong>
                    {item.child_name} · {family(item.billing_account_id)}
                  </strong>
                  <small>
                    {titleCase(item.latest_version.billing_frequency)} · family{" "}
                    {formatCadMinor(
                      item.latest_version.family_amount_minor_per_unit,
                    )}{" "}
                    · funding rule gated · v{item.latest_version.version_number}
                  </small>
                </span>
                <StatusChip $tone="success">
                  {canManage ? "Revise" : "Reviewed"}
                </StatusChip>
              </WorkRow>
            ))
          ) : (
            <Empty>No reviewed agreements yet.</Empty>
          )}
        </WorkList>
      </Panel>
    </Grid>
  );
}

function ReportsTab({
  snapshot,
  aging,
  readiness,
}: {
  snapshot: Snapshot;
  aging: Aging;
  readiness: BillingReadinessResponse;
}) {
  const invoiceTotal = snapshot.invoices.reduce(
    (sum, item) => sum + item.total_minor,
    0,
  );
  const allocated = snapshot.invoices.reduce(
    (sum, item) => sum + item.allocated_minor,
    0,
  );
  return (
    <>
      <BillingReadinessPanel status="live" data={readiness} maximumItems={12} />
      <Stats>
        <Stat>
          <span>Invoices issued</span>
          <strong>{formatCadMinor(invoiceTotal)}</strong>
          <small>{snapshot.invoices.length} immutable documents</small>
        </Stat>
        <Stat>
          <span>Allocated receipts</span>
          <strong>{formatCadMinor(allocated)}</strong>
          <small>Matched to invoices</small>
        </Stat>
        <Stat>
          <span>Unapplied receipts</span>
          <strong>
            {formatCadMinor(snapshot.overview.unapplied_payments_minor)}
          </strong>
          <small>Requires explicit allocation</small>
        </Stat>
        <Stat>
          <span>Credits</span>
          <strong>{formatCadMinor(snapshot.overview.credits_minor)}</strong>
          <small>Owner-controlled adjustments</small>
        </Stat>
      </Stats>
      <Grid>
        <Panel>
          <PanelHeader>
            <div>
              <h2>Operational readiness</h2>
              <p>What this first financial foundation can safely do.</p>
            </div>
          </PanelHeader>
          <WorkList>
            {[
              ["Account activity", snapshot.accounts.length > 0],
              ["Reviewed rate agreements", snapshot.agreements.length > 0],
              ["Immutable invoice issue", snapshot.invoices.length > 0],
              ["Off-platform receipt ledger", snapshot.payments.length > 0],
            ].map(([label, ready]) => (
              <StatusRow key={String(label)}>
                <CheckCircleIcon />
                <span className="copy">
                  <strong>{label}</strong>
                  <small>
                    {ready
                      ? "Canonical records are present in the loaded window."
                      : "Ready to configure; no canonical records yet."}
                  </small>
                </span>
                <StatusChip $tone={ready ? "success" : "neutral"}>
                  {ready ? "Active" : "Empty"}
                </StatusChip>
              </StatusRow>
            ))}
          </WorkList>
        </Panel>
        <Panel>
          <PanelHeader>
            <div>
              <h2>Governance roadmap</h2>
              <p>
                These controls remain intentionally unavailable until their own
                audited foundation exists.
              </p>
            </div>
          </PanelHeader>
          <WorkList>
            {[
              "Payment processor and stored payment methods",
              "Automatic invoice runs and delivery",
              "Refunds and bank movement",
              "Tax configuration and accountant review",
              "Exports, statements, subsidy reconciliation",
            ].map((label) => (
              <StatusRow key={label}>
                <LockClosedIcon />
                <span className="copy">
                  <strong>{label}</strong>
                  <small>
                    Not represented as active capability or financial advice.
                  </small>
                </span>
                <StatusChip $tone="neutral">Roadmap</StatusChip>
              </StatusRow>
            ))}
          </WorkList>
          <AgingBar>
            {[
              ["Current", aging.current],
              ["1–30", aging.days30],
              ["31–60", aging.days60],
              ["61–90", aging.days90],
              ["91+", aging.older],
            ].map(([label, amount]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <strong>{formatCadMinor(Number(amount))}</strong>
              </div>
            ))}
          </AgingBar>
        </Panel>
      </Grid>
    </>
  );
}

type BillingEffectDetailProps = {
  snapshot: Snapshot;
  onOpenRecord: (focus: BillingFocus, recordId: string) => void;
  onClose: () => void;
} & (
  | { kind: "allocation"; record: BillingAllocation }
  | { kind: "credit"; record: BillingCredit }
);

function BillingEffectDetailDialog(props: BillingEffectDetailProps) {
  const { snapshot, onOpenRecord, onClose } = props;
  const invoice = snapshot.invoices.find(
    (candidate) => candidate.id === props.record.invoice_id,
  );
  const account = snapshot.accounts.find(
    (candidate) => candidate.id === props.record.billing_account_id,
  );
  const payment =
    props.kind === "allocation"
      ? snapshot.payments.find(
          (candidate) => candidate.id === props.record.payment_id,
        )
      : null;
  const actorId =
    props.kind === "allocation"
      ? props.record.allocated_by_user_id
      : props.record.issued_by_user_id;
  const recordedAt =
    props.kind === "allocation"
      ? props.record.allocated_at
      : props.record.issued_at;
  const label = props.kind === "allocation" ? "Allocation" : "Credit";
  return (
    <BillingDialog
      title={`${label} effect`}
      description={`Immutable ${snapshot.sandbox ? "synthetic" : "private manual"} ledger effect from the fully assembled canonical snapshot.`}
      onClose={onClose}
      footer={
        <ActionButton type="button" $variant="primary" onClick={onClose}>
          Close {label.toLowerCase()}
        </ActionButton>
      }
    >
      <Boundary $accent="amber">
        <ShieldCheckIcon />
        <div>
          <h2>{snapshot.provenanceLabel}</h2>
          <p>
            This record does not move money. Its amount and provenance are
            displayed exactly as returned by the canonical ledger.
          </p>
        </div>
        <StatusChip $tone="info">Immutable effect</StatusChip>
      </Boundary>
      <DetailGrid>
        <DetailCard>
          <span>Family account</span>
          <strong>
            {account?.family_name || "Family unavailable"} ·{" "}
            {account?.account_number || props.record.billing_account_id}
          </strong>
        </DetailCard>
        <DetailCard>
          <span>Amount</span>
          <strong>{formatCadMinor(props.record.amount_minor)}</strong>
        </DetailCard>
        <DetailCard>
          <span>Recorded</span>
          <strong>{formatDateTime(recordedAt)}</strong>
        </DetailCard>
        <DetailCard>
          <span>Actor</span>
          <strong>{actorId}</strong>
        </DetailCard>
      </DetailGrid>
      {props.kind === "credit" && (
        <SummaryBox>
          <h3>Credit reason</h3>
          <p>
            {titleCase(props.record.reason_code)}
            {props.record.note ? ` · ${props.record.note}` : " · no note"}
          </p>
        </SummaryBox>
      )}
      <SummaryBox>
        <h3>Linked canonical context</h3>
        <p>
          Invoice {invoice?.invoice_number || props.record.invoice_id}
          {payment
            ? ` · payment ${payment.external_reference} from ${payment.payer_name}`
            : ""}
          . These destinations are reconstructed from organization-bound
          records rather than accepted from arbitrary URLs.
        </p>
        <InlineButtons>
          {invoice && (
            <SmallButton
              type="button"
              onClick={() => onOpenRecord("billing_invoice", invoice.id)}
            >
              Open invoice
            </SmallButton>
          )}
          {payment && (
            <SmallButton
              type="button"
              onClick={() => onOpenRecord("billing_payment", payment.id)}
            >
              Open payment
            </SmallButton>
          )}
          {account && (
            <SmallButton
              type="button"
              onClick={() => onOpenRecord("billing_account", account.id)}
            >
              Open family account
            </SmallButton>
          )}
        </InlineButtons>
      </SummaryBox>
      <SummaryBox>
        <h3>Command provenance</h3>
        <p>
          Effect <ProvenanceCode>{props.record.id}</ProvenanceCode>
          <br />
          Client operation{" "}
          <ProvenanceCode>{props.record.client_operation_id}</ProvenanceCode>
          <br />
          Request hash{" "}
          <ProvenanceCode>{props.record.request_hash}</ProvenanceCode>
        </p>
      </SummaryBox>
    </BillingDialog>
  );
}

function InvoiceDetailDialog({
  invoice,
  snapshot,
  onOpenEffect,
  onClose,
}: {
  invoice: BillingInvoice;
  snapshot: Snapshot;
  onOpenEffect: (
    focus: "billing_allocation" | "billing_credit",
    recordId: string,
  ) => void;
  onClose: () => void;
}) {
  const account = snapshot.accounts.find(
    (candidate) => candidate.id === invoice.billing_account_id,
  );
  const payerGuardian = snapshot.families
    .find((family) => family.id === invoice.family_id)
    ?.guardians.find((guardian) => guardian.id === invoice.payer_guardian_id);
  const payerVersion = snapshot.payerVersions.find(
    (version) => version.id === invoice.billing_account_payer_version_id,
  );
  const lineProvenance = (line: BillingInvoice["lines"][number]) => {
    const agreement = snapshot.agreements.find((candidate) =>
      candidate.versions.some(
        (version) => version.id === line.agreement_version_id,
      ),
    );
    const agreementVersion = agreement?.versions.find(
      (version) => version.id === line.agreement_version_id,
    );
    const ratePlan = snapshot.ratePlans.find((candidate) =>
      candidate.versions.some(
        (version) => version.id === agreementVersion?.rate_plan_version_id,
      ),
    );
    return {
      agreement,
      agreementVersion,
      ratePlan,
      rateVersion: ratePlan?.versions.find(
        (version) => version.id === agreementVersion?.rate_plan_version_id,
      ),
    };
  };
  const allocations = snapshot.allocations.filter(
    (item) => item.invoice_id === invoice.id,
  );
  const credits = snapshot.credits.filter(
    (item) => item.invoice_id === invoice.id,
  );
  const [documentPreviewOpen, setDocumentPreviewOpen] = useState(false);
  if (documentPreviewOpen)
    return (
      <BillingInvoicePreviewDialog
        organizationId={invoice.organization_id}
        invoiceId={invoice.id}
        invoiceNumber={invoice.invoice_number}
        provenanceLabel={invoice.document_label}
        onClose={() => setDocumentPreviewOpen(false)}
      />
    );
  return (
    <BillingDialog
      title={`Invoice ${invoice.invoice_number}`}
      description={`Immutable ${snapshot.sandbox ? "synthetic" : "private manual"} invoice detail reconstructed from the loaded coherent canonical workspace.`}
      onClose={onClose}
      footer={
        <>
          <ActionButton
            type="button"
            onClick={() => setDocumentPreviewOpen(true)}
          >
            <DocumentTextIcon aria-hidden="true" />
            Preview document
          </ActionButton>
          <ActionButton type="button" $variant="primary" onClick={onClose}>
            Close invoice
          </ActionButton>
        </>
      }
    >
      <Boundary $accent="amber">
        <DocumentTextIcon />
        <div>
          <h2>{snapshot.provenanceLabel}</h2>
          <p>
            No delivery is represented. This view explains the immutable{" "}
            {snapshot.sandbox ? "sandbox" : "private manual"} record and its
            current allocation and credit projection. Browser printing creates
            a local copy only.
          </p>
        </div>
        <StatusChip $tone={statusTone(invoice.lifecycle_status)}>
          {titleCase(invoice.lifecycle_status)}
        </StatusChip>
      </Boundary>
      <DetailGrid>
        <DetailCard>
          <span>Family account</span>
          <strong>
            {invoice.family_name} · {account?.account_number || "Account unavailable"}
          </strong>
        </DetailCard>
        <DetailCard>
          <span>Invoice payer snapshot</span>
          <strong>
            {invoice.payer_name}
            {invoice.payer_email ? ` · ${invoice.payer_email}` : ""}
          </strong>
        </DetailCard>
        <DetailCard>
          <span>Linked payer identity</span>
          <strong>{payerGuardian?.name || invoice.payer_name}</strong>
          <small>
            Assignment v{payerVersion?.version_number ?? "?"} · recorded {" "}
            {payerVersion
              ? formatDateTime(payerVersion.assigned_at)
              : "source time unavailable"}
          </small>
        </DetailCard>
        <DetailCard>
          <span>Service period</span>
          <strong>
            {formatDateOnly(invoice.service_period_start)} –{" "}
            {formatDateOnly(invoice.service_period_end)}
          </strong>
        </DetailCard>
        <DetailCard>
          <span>Issue and due dates</span>
          <strong>
            Issued {formatDateOnly(invoice.issue_date)} · due{" "}
            {formatDateOnly(invoice.due_date)}
          </strong>
        </DetailCard>
      </DetailGrid>
      <SummaryBox>
        <h3>Immutable payer provenance</h3>
        <p>
          The displayed payer text is the invoice-time snapshot. These source
          identifiers preserve which account assignment and guardian the
          {snapshot.sandbox ? " sandbox" : " private manual"} record used; they
          do not represent delivery, collection, or movement of money.
        </p>
        <ProvenanceCode>
          account {invoice.billing_account_id}
          <br />
          payer version {invoice.billing_account_payer_version_id}
          <br />
          guardian {invoice.payer_guardian_id}
          {payerVersion && (
            <>
              <br />
              assigned by {payerVersion.assigned_by_user_id}
            </>
          )}
        </ProvenanceCode>
      </SummaryBox>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Child & service</th>
              <th>Contract provenance</th>
              <th className="money">Gross</th>
              <th className="money">Funding</th>
              <th className="money">Family</th>
              <th className="money">Tax</th>
              <th className="money">Total</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.map((line) => {
              const provenance = lineProvenance(line);
              return (
                <tr key={line.id}>
                  <td data-label="Child & service">
                    <strong>{line.child_name}</strong>
                    <small>
                      {line.description} · {titleCase(line.billing_unit)} · qty{" "}
                      {line.quantity}
                      <br />
                      {formatDateOnly(line.service_period_start)} –{" "}
                      {formatDateOnly(line.service_period_end)}
                    </small>
                  </td>
                  <td data-label="Contract provenance">
                    <strong>
                      {provenance.ratePlan?.name || line.rate_plan_name}
                    </strong>
                    <small>
                      Agreement v
                      {provenance.agreementVersion?.version_number || "?"} · rate
                      v{provenance.rateVersion?.version_number || "?"}
                    </small>
                    <ProvenanceCode>
                      agreement {line.agreement_version_id}
                      <br />
                      rate {provenance.rateVersion?.id || "unavailable"}
                    </ProvenanceCode>
                  </td>
                  <td data-label="Gross" className="money">
                    {formatCadMinor(line.gross_subtotal_minor)}
                  </td>
                  <td data-label="Funding" className="money">
                    {formatCadMinor(line.funding_minor)}
                  </td>
                  <td data-label="Family" className="money">
                    {formatCadMinor(line.subtotal_minor)}
                  </td>
                  <td data-label="Tax" className="money">
                    {formatCadMinor(line.tax_minor)}
                  </td>
                  <td data-label="Total" className="money">
                    {formatCadMinor(line.total_minor)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrap>
      <SummaryBox>
        <h3>Canonical settlement effects</h3>
        <p>
          Allocations and credits are immutable ledger effects. Open a
          server-proven record to inspect its complete actor, timestamp,
          operation, and request-hash provenance.
        </p>
        {allocations.length || credits.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <th>Effect</th>
                  <th>Recorded</th>
                  <th>Actor & operation proof</th>
                  <th className="money">Amount</th>
                  <th className="action">Detail</th>
                </tr>
              </thead>
              <tbody>
                {allocations.map((effect) => (
                  <tr key={effect.id} data-billing-record={effect.id}>
                    <td data-label="Effect">
                      <strong>Payment allocation</strong>
                      <small>Payment {effect.payment_id}</small>
                    </td>
                    <td data-label="Recorded">
                      {formatDateTime(effect.allocated_at)}
                    </td>
                    <td data-label="Provenance">
                      <ProvenanceCode>
                        actor {effect.allocated_by_user_id}
                        <br />
                        operation {effect.client_operation_id}
                        <br />
                        hash {effect.request_hash}
                      </ProvenanceCode>
                    </td>
                    <td data-label="Amount" className="money">
                      {formatCadMinor(effect.amount_minor)}
                    </td>
                    <td data-label="Detail" className="action">
                      <SmallButton
                        type="button"
                        onClick={() =>
                          onOpenEffect("billing_allocation", effect.id)
                        }
                      >
                        Open allocation
                      </SmallButton>
                    </td>
                  </tr>
                ))}
                {credits.map((effect) => (
                  <tr key={effect.id} data-billing-record={effect.id}>
                    <td data-label="Effect">
                      <strong>Credit issued</strong>
                      <small>{titleCase(effect.reason_code)}</small>
                    </td>
                    <td data-label="Recorded">
                      {formatDateTime(effect.issued_at)}
                    </td>
                    <td data-label="Provenance">
                      <ProvenanceCode>
                        actor {effect.issued_by_user_id}
                        <br />
                        operation {effect.client_operation_id}
                        <br />
                        hash {effect.request_hash}
                      </ProvenanceCode>
                    </td>
                    <td data-label="Amount" className="money">
                      {formatCadMinor(effect.amount_minor)}
                    </td>
                    <td data-label="Detail" className="action">
                      <SmallButton
                        type="button"
                        onClick={() => onOpenEffect("billing_credit", effect.id)}
                      >
                        Open credit
                      </SmallButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <Empty>No settlement effects have been recorded for this invoice.</Empty>
        )}
      </SummaryBox>
      <DetailTotals>
        <Stat>
          <span>Gross contracted</span>
          <strong>{formatCadMinor(invoice.gross_subtotal_minor)}</strong>
          <small>{formatCadMinor(invoice.funding_minor)} funding projection</small>
        </Stat>
        <Stat>
          <span>Family invoice total</span>
          <strong>{formatCadMinor(invoice.total_minor)}</strong>
          <small>{formatCadMinor(invoice.tax_minor)} tax</small>
        </Stat>
        <Stat>
          <span>Allocated</span>
          <strong>{formatCadMinor(invoice.allocated_minor)}</strong>
          <small>{formatCadMinor(invoice.credits_minor)} credits</small>
        </Stat>
        <Stat $accent="amber">
          <span>Outstanding</span>
          <strong>{formatCadMinor(invoice.outstanding_minor)}</strong>
          <small>Derived from immutable effects</small>
        </Stat>
      </DetailTotals>
        <SummaryBox>
          <h3>Canonical record identity</h3>
          <p>
            Invoice <ProvenanceCode>{invoice.id}</ProvenanceCode> · account{" "}
            <ProvenanceCode>{invoice.billing_account_id}</ProvenanceCode>. Line,
            agreement, rate, service, payer, and amount snapshots are displayed
            above; the server remains authoritative.
          </p>
        </SummaryBox>
    </BillingDialog>
  );
}

function CommandDialog({
  kind,
  target,
  snapshot,
  busy,
  writeAllowed,
  onClose,
  onRun,
}: {
  kind: DialogKind;
  target: BillingDialogTarget | null;
  snapshot: Snapshot;
  busy: boolean;
  writeAllowed: boolean;
  onClose: () => void;
  onRun: <T extends Record<string, unknown>>(
    kind: BillingCommandKind,
    input: T,
    execute: (operationId: string) => Promise<BillingCommandReceipt>,
  ) => Promise<void>;
}) {
  const billingCapability = useBillingCapability().capability;
  const today = billingCapability?.organization_local_date || "";
  const rateRevision = target?.kind === "rate" ? target.rate : null;
  const agreementRevision =
    target?.kind === "agreement" ? target.agreement : null;
  const payerRevision = target?.kind === "payer" ? target.account : null;
  const agreementRate = agreementRevision
    ? snapshot.ratePlans.find((plan) =>
        plan.versions.some(
          (version) =>
            version.id ===
            agreementRevision.latest_version.rate_plan_version_id,
        ),
      )
    : null;
  const [form, setForm] = useState<Record<string, string>>(() => ({
    issue_date: today,
    due_date: today,
    service_period_start: "",
    service_period_end: "",
    effective_from:
      (rateRevision || agreementRevision) && today
        ? addDateOnlyDays(today, 1)
        : today,
    received_at: billingCapability
      ? organizationDateTimeLocal(
          billingCapability.server_time,
          billingCapability.organization_timezone,
        )
      : "",
    method: "e_transfer",
    billing_unit: rateRevision?.latest_version.billing_unit || "monthly_period",
    amount: rateRevision
      ? minorInput(rateRevision.latest_version.unit_amount_minor)
      : "",
    description: rateRevision?.latest_version.description || "",
    account_id:
      payerRevision?.id || agreementRevision?.billing_account_id || "",
    payer_guardian_id: payerRevision?.payer_guardian_id || "",
    child_id: agreementRevision?.child_id || "",
    rate_plan_id: agreementRate?.id || "",
    program_type: "daycare",
    reason_code: "billing_correction",
  }));
  const [agreements, setAgreements] = useState<string[]>([]);
  const [reviewed, setReviewed] = useState(false);
  const [formError, setFormError] = useState("");
  const set = (key: string, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (kind === "invoice") setReviewed(false);
    setFormError("");
  };
  const family = snapshot.families.find((item) => item.id === form.family_id);
  const selectedAccount = snapshot.accounts.find(
    (item) => item.id === form.account_id,
  );
  const sourceFamily = snapshot.families.find(
    (item) => item.id === selectedAccount?.family_id,
  );
  const childOptions = sourceFamily?.children || [];
  const selectedChild = childOptions.find((item) => item.id === form.child_id);
  const matchingPlans =
    selectedChild?.program_type &&
    selectedChild.facility_id &&
    selectedChild.program_id
      ? snapshot.ratePlans.filter(
          (plan) =>
            plan.program_type === selectedChild.program_type &&
            plan.facility_id === selectedChild.facility_id &&
            plan.program_id === selectedChild.program_id &&
            (!plan.age_group || plan.age_group === selectedChild.age_group),
        )
      : [];
  const accountAgreements = snapshot.agreements.filter(
    (item) => item.billing_account_id === form.account_id,
  );
  const selectedAgreements = accountAgreements.filter((item) =>
    agreements.includes(item.id),
  );
  const selectedFrequency =
    selectedAgreements[0]?.latest_version.billing_frequency;
  const setInvoicePeriod = (
    frequency: BillingAgreement["latest_version"]["billing_frequency"],
    anchor: string,
  ) => {
    const period = billingPeriodForFrequency(frequency, anchor);
    set("service_period_start", period.start);
    set("service_period_end", period.end);
  };
  const rateForAgreement = (agreement: BillingAgreement) =>
    snapshot.ratePlans.find((plan) =>
      plan.versions.some(
        (version) =>
          version.id === agreement.latest_version.rate_plan_version_id,
      ),
    );
  const scopeForRate = (rate: BillingRatePlan | undefined) => {
    const program = snapshot.programs.find(
      (item) => item.program_id === rate?.program_id,
    );
    return program
      ? `${program.facility_name} · ${program.program_name}`
      : "Program scope unavailable";
  };
  const scopeForAgreement = (agreement: BillingAgreement) => {
    return scopeForRate(rateForAgreement(agreement));
  };
  const availablePayments = snapshot.payments.filter(paymentAvailable);
  const payment = availablePayments.find((item) => item.id === form.payment_id);
  const invoiceChoices = snapshot.invoices.filter(
    (item) =>
      invoiceOutstanding(item) &&
      (!payment || item.billing_account_id === payment.billing_account_id),
  );
  const selectedInvoice = snapshot.invoices.find(
    (item) => item.id === form.invoice_id,
  );
  let invoicePreview: ReturnType<typeof previewInvoiceFromAgreements> | null =
    null;
  let resolvedInvoiceAgreements: ReturnType<
    typeof resolveBillingInvoiceDraftAgreements
  > = [];
  let invoicePreviewError = "";
  if (agreements.length) {
    try {
      if (selectedAgreements.length !== agreements.length)
        throw new Error(
          "A selected agreement is no longer present in the coherent workspace. Refresh before review.",
        );
      validateBillingInvoiceDraftDates({
        issueDate: form.issue_date,
        dueDate: form.due_date,
        organizationLocalToday: today,
      });
      resolvedInvoiceAgreements = resolveBillingInvoiceDraftAgreements(
        selectedAgreements,
        snapshot.ratePlans,
        {
          start: form.service_period_start,
          end: form.service_period_end,
        },
      );
      invoicePreview = previewInvoiceFromAgreements(
        resolvedInvoiceAgreements.map(({ agreement, agreementVersion }) => ({
          ...agreement,
          latest_version: agreementVersion,
        })),
        snapshot.ratePlans,
        {
          start: form.service_period_start,
          end: form.service_period_end,
        },
      );
    } catch (caught) {
      invoicePreviewError = billingErrorMessage(caught);
    }
  }
  const invoiceReviewBlocked =
    kind === "invoice" && agreements.length > 0 && !invoicePreview;
  let creditPreviewAmount: ReturnType<typeof parseMoneyInput> | null = null;
  let creditResultingBalance: ReturnType<typeof previewCreditResult> | null =
    null;
  let creditPreviewError = "";
  if (selectedInvoice && form.amount?.trim()) {
    try {
      creditPreviewAmount = parseMoneyInput(form.amount, {
        maximumMinor: selectedInvoice.outstanding_minor,
      });
      creditResultingBalance = previewCreditResult(
        selectedInvoice,
        creditPreviewAmount,
      );
    } catch (caught) {
      creditPreviewError = billingErrorMessage(caught);
    }
  }
  const titles: Record<DialogKind, [string, string]> = {
    account: [
      "Open family billing account",
      "Select the family and a current payer. Identifiers are chosen from canonical billing source records.",
    ],
    payer: [
      "Assign current account payer",
      "Choose who should be responsible for future charges on this family account. Existing invoices keep the payer recorded when they were issued.",
    ],
    rate: [
      "Publish rate plan",
      "Create one effective-dated childcare period price. Tax is fixed at zero in this foundation.",
    ],
    agreement: [
      "Establish reviewed agreement",
      "Pin an enrolled child to a compatible program rate. Funding remains locked until a verified rule pack exists.",
    ],
    invoice: [
      "Issue invoice from agreements",
      "Select reviewed agreements and their exact contracted period. The server derives each one-unit line and amount.",
    ],
    payment: [
      "Record operator-confirmed off-platform receipt",
      "Identify the actual payer and record money already received outside CareSync; no money moves here.",
    ],
    allocation: [
      "Allocate payment",
      "Apply an available receipt to an outstanding invoice in the same account.",
    ],
    credit: [
      "Issue account credit",
      "Owner-only append-only adjustment; original invoice facts remain unchanged.",
    ],
  };
  const dialogTitle = rateRevision
    ? `Publish ${rateRevision.name} version ${rateRevision.latest_version.version_number + 1}`
    : agreementRevision
      ? `Review ${agreementRevision.child_name} agreement version ${agreementRevision.latest_version.version_number + 1}`
      : titles[kind][0];
  const dialogDescription = rateRevision
    ? "Keep the care identity fixed and publish a future-effective price version. Earlier invoices and agreements remain pinned to their original versions."
    : agreementRevision
      ? "Publish a future-effective reviewed version against the exact current agreement and rate projections."
      : titles[kind][1];
  const organizationId = useSession().user?.organization_id || "";
  const submitWithApi = async (event: FormEvent) => {
    const wrapped = async <T extends Record<string, unknown>>(
      command: BillingCommandKind,
      input: T,
    ) =>
      onRun(command, input, (operationId) => {
        switch (command) {
          case "account.create":
            return billingApi.createAccount(
              organizationId,
              operationId,
              input as unknown as CreateBillingAccountInput,
            );
          case "account.payer.assign": {
            const payerInput =
              input as unknown as AssignBillingAccountPayerOperationInput;
            return billingApi.assignAccountPayer(
              organizationId,
              payerInput.account_id,
              operationId,
              {
                account_id: payerInput.account_id,
                payer_guardian_id: payerInput.payer_guardian_id,
                expected_latest_payer_version_id:
                  payerInput.expected_latest_payer_version_id,
                expected_latest_payer_version_number:
                  payerInput.expected_latest_payer_version_number,
              },
            );
          }
          case "rate_plan.create":
            return billingApi.createRatePlan(
              organizationId,
              operationId,
              input as unknown as CreateRatePlanInput,
            );
          case "agreement.create":
            return billingApi.createAgreement(
              organizationId,
              operationId,
              input as unknown as CreateAgreementInput,
            );
          case "invoice.issue":
            return billingApi.issueInvoice(
              organizationId,
              operationId,
              input as unknown as IssueInvoiceInput,
            );
          case "payment.record":
            return billingApi.recordPayment(
              organizationId,
              operationId,
              input as unknown as RecordPaymentInput,
            );
          case "payment.allocate":
            return billingApi.allocatePayment(
              organizationId,
              operationId,
              input as unknown as AllocatePaymentInput,
            );
          case "credit.create":
            return billingApi.createCredit(
              organizationId,
              operationId,
              input as unknown as CreateCreditInput,
            );
        }
      });
    try {
      // Re-run the same validation with a local dispatcher by temporarily routing the calls below.
      event.preventDefault();
      setFormError("");
      if (!writeAllowed)
        throw new Error(
          "This financial command is read-only because authoritative write readiness or the required permission is unavailable.",
        );
      const dispatch = wrapped;
      if (kind === "account") {
        if (!form.family_id || !form.payer_guardian_id)
          throw new Error("Choose a family and primary payer.");
        await dispatch("account.create", {
          family_id: form.family_id,
          payer_guardian_id: form.payer_guardian_id,
        });
      } else if (kind === "payer") {
        if (!payerRevision || !form.payer_guardian_id)
          throw new Error(
            "Choose a current guardian as the new account payer.",
          );
        if (form.payer_guardian_id === payerRevision.payer_guardian_id)
          throw new Error(
            "Choose a different guardian before publishing a payer assignment.",
          );
        await dispatch("account.payer.assign", {
          account_id: payerRevision.id,
          payer_guardian_id: form.payer_guardian_id,
          expected_latest_payer_version_id:
            payerRevision.latest_payer_version_id,
          expected_latest_payer_version_number:
            payerRevision.latest_payer_version_number,
        });
      } else if (kind === "rate") {
        const amount = parseMoneyInput(form.amount || "");
        const sourceProgram = snapshot.programs.find(
          (item) => item.program_id === form.program_id,
        );
        if (!rateRevision && (!form.code?.trim() || !form.name?.trim()))
          throw new Error("Enter a rate code and name.");
        if (!rateRevision && !sourceProgram)
          throw new Error("Choose a canonical active facility program.");
        if (rateRevision && form.effective_from <= today)
          throw new Error(
            "A rate revision must start after the current organization date.",
          );
        await dispatch("rate_plan.create", {
          rate_plan_id: rateRevision?.id || null,
          expected_latest_version_id: rateRevision?.latest_version.id || null,
          expected_latest_version_number:
            rateRevision?.latest_version.version_number || null,
          ...(rateRevision
            ? {
                code: null,
                name: null,
                program_type: null,
                charge_kind: null,
                age_group: null,
                facility_id: null,
                program_id: null,
              }
            : {}),
          ...(!rateRevision && sourceProgram
            ? {
                code: form.code.trim(),
                name: form.name.trim(),
                program_type: sourceProgram.program_type,
                charge_kind: "core_care" as const,
                age_group: form.age_group?.trim() || null,
                facility_id: sourceProgram.facility_id,
                program_id: sourceProgram.program_id,
              }
            : {}),
          billing_unit: form.billing_unit,
          unit_amount_minor: amount,
          tax_rate_basis_points: 0,
          effective_from: form.effective_from,
          effective_until: null,
          description: form.description?.trim() || null,
        });
      } else if (kind === "agreement") {
        const plan = matchingPlans.find(
          (item) => item.id === form.rate_plan_id,
        );
        const child = selectedChild;
        if (!plan || !child || !form.account_id || !child.enrollment_id)
          throw new Error(
            "Choose an account, enrolled child, and compatible program rate.",
          );
        if (agreementRevision && form.effective_from <= today)
          throw new Error(
            "An agreement revision must start after the current organization date.",
          );
        const frequency =
          plan.latest_version.billing_unit === "weekly_period"
            ? "weekly"
            : plan.latest_version.billing_unit === "biweekly_period"
              ? "biweekly"
              : plan.latest_version.billing_unit === "monthly_period"
                ? "monthly"
                : "per_service";
        await dispatch("agreement.create", {
          agreement_id: agreementRevision?.id || null,
          expected_latest_version_id:
            agreementRevision?.latest_version.id || null,
          expected_latest_version_number:
            agreementRevision?.latest_version.version_number || null,
          account_id: form.account_id,
          child_id: child.id,
          enrollment_id: child.enrollment_id,
          rate_plan_version_id: plan.latest_version.id,
          billing_frequency: frequency,
          effective_from: form.effective_from,
          effective_until: null,
          family_amount_minor_per_unit: plan.latest_version.unit_amount_minor,
          funding_amount_minor_per_unit: 0,
          reviewed: true,
        });
      } else if (kind === "invoice") {
        if (!form.account_id || !agreements.length)
          throw new Error(
            "Choose an account and at least one reviewed agreement.",
          );
        validateBillingInvoiceDraftDates({
          issueDate: form.issue_date,
          dueDate: form.due_date,
          organizationLocalToday: today,
        });
        if (!invoicePreview)
          throw new Error(
            invoicePreviewError ||
              "The invoice amount preview is unavailable. Refresh before review.",
          );
        if (resolvedInvoiceAgreements.length !== agreements.length)
          throw new Error(
            "The selected historical agreement versions could not be proven. Refresh before review.",
          );
        if (!reviewed) {
          setReviewed(true);
          return;
        }
        await dispatch("invoice.issue", {
          account_id: form.account_id,
          agreements: resolvedInvoiceAgreements.map(
            (resolution) => resolution.selection,
          ),
          service_period_start: form.service_period_start,
          service_period_end: form.service_period_end,
          issue_date: form.issue_date,
          due_date: form.due_date,
        });
      } else if (kind === "payment") {
        if (!billingCapability)
          throw new Error("The organization billing clock is unavailable.");
        if (!form.account_id) throw new Error("Choose a family account.");
        if (!form.payer_guardian_id)
          throw new Error(
            "Choose the guardian who actually made this payment.",
          );
        if (!form.external_reference?.trim())
          throw new Error(
            "Every payment requires a unique receipt or transaction reference.",
          );
        if (
          ["cash", "other"].includes(form.method) &&
          (form.operator_confirmation_note?.trim().length || 0) < 3
        )
          throw new Error(
            "Cash and other receipts require a meaningful operator memo.",
          );
        await dispatch("payment.record", {
          account_id: form.account_id,
          payer_guardian_id: form.payer_guardian_id,
          amount_minor: parseMoneyInput(form.amount || ""),
          method: form.method,
          received_at: organizationLocalDateTimeToIso(
            form.received_at,
            billingCapability.organization_timezone,
          ),
          external_reference: form.external_reference.trim().toUpperCase(),
          memo: form.memo?.trim() || null,
          operator_confirmation_note:
            form.operator_confirmation_note?.trim() || null,
        });
      } else if (kind === "allocation") {
        if (!payment || !selectedInvoice)
          throw new Error("Choose an available payment and matching invoice.");
        await dispatch("payment.allocate", {
          payment_id: payment.id,
          invoice_id: selectedInvoice.id,
          amount_minor: parseMoneyInput(form.amount || "", {
            maximumMinor: Math.min(
              payment.unapplied_minor,
              selectedInvoice.outstanding_minor,
            ),
          }),
          expected_payment_unapplied_minor: payment.unapplied_minor,
          expected_invoice_outstanding_minor: selectedInvoice.outstanding_minor,
        });
      } else {
        if (!selectedInvoice) throw new Error("Choose an outstanding invoice.");
        await dispatch("credit.create", {
          invoice_id: selectedInvoice.id,
          amount_minor: parseMoneyInput(form.amount || "", {
            maximumMinor: selectedInvoice.outstanding_minor,
          }),
          expected_invoice_outstanding_minor: selectedInvoice.outstanding_minor,
          reason_code: form.reason_code,
          note: form.note?.trim() || null,
        });
      }
    } catch (caught) {
      setFormError(billingErrorMessage(caught));
    }
  };
  return (
    <BillingDialog
      title={dialogTitle}
      description={dialogDescription}
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <ActionButton type="button" onClick={onClose} disabled={busy}>
            Cancel
          </ActionButton>
          <ActionButton
            type="submit"
            form="billing-command-form"
            $variant="primary"
            disabled={busy || !writeAllowed || invoiceReviewBlocked}
          >
            {busy
              ? "Committing…"
              : kind === "invoice" && !reviewed
                ? "Review invoice"
                : kind === "invoice"
                  ? "Confirm & issue"
                  : "Confirm"}
          </ActionButton>
        </>
      }
    >
      <form
        id="billing-command-form"
        onSubmit={(event) => void submitWithApi(event)}
      >
        <Fields>
          {kind === "account" && (
            <>
              <Field $wide>
                Family
                <select
                  value={form.family_id || ""}
                  onChange={(event) => {
                    set("family_id", event.target.value);
                    set("payer_guardian_id", "");
                  }}
                >
                  <option value="">Choose a family</option>
                  {snapshot.families
                    .filter(
                      (item) =>
                        item.status === "active" &&
                        !snapshot.accounts.some(
                          (account) => account.family_id === item.id,
                        ),
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field $wide>
                Payer
                <select
                  value={form.payer_guardian_id || ""}
                  onChange={(event) =>
                    set("payer_guardian_id", event.target.value)
                  }
                  disabled={!family}
                >
                  <option value="">Choose a current guardian</option>
                  {family?.guardians.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                      {item.email ? ` · ${item.email}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
            </>
          )}
          {kind === "payer" && payerRevision && (
            <>
              <Field $wide>
                Family account
                <input
                  value={`${payerRevision.family_name} · ${payerRevision.account_number}`}
                  disabled
                />
              </Field>
              <Field $wide>
                New current payer
                <select
                  value={form.payer_guardian_id || ""}
                  onChange={(event) =>
                    set("payer_guardian_id", event.target.value)
                  }
                >
                  <option value="">Choose a current guardian</option>
                  {snapshot.families
                    .find((item) => item.id === payerRevision.family_id)
                    ?.guardians.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                        {item.email ? ` · ${item.email}` : ""}
                        {item.id === payerRevision.payer_guardian_id
                          ? " · current payer"
                          : ""}
                      </option>
                    ))}
                </select>
              </Field>
              <Field $wide>
                <SummaryBox>
                  <h3>Your review is protected</h3>
                  <p>
                    You are reviewing the guardian currently responsible for
                    future charges. CareSync keeps earlier assignments in the
                    account history. If someone else updates the payer before
                    you save, CareSync will ask you to refresh instead of
                    overwriting their work.
                  </p>
                </SummaryBox>
              </Field>
            </>
          )}
          {kind === "rate" && (
            <>
              {rateRevision ? (
                <Field $wide>
                  <SummaryBox>
                    <h3>Immutable care identity</h3>
                    <p>
                      {rateRevision.code} · {rateRevision.name} ·{" "}
                      {scopeForRate(rateRevision)} ·{" "}
                      {titleCase(rateRevision.program_type)}
                      {rateRevision.age_group
                        ? ` · ${rateRevision.age_group}`
                        : ""}
                    </p>
                    <p>
                      Current v{rateRevision.latest_version.version_number}:{" "}
                      {formatCadMinor(
                        rateRevision.latest_version.unit_amount_minor,
                      )}{" "}
                      / {titleCase(rateRevision.latest_version.billing_unit)}.
                    </p>
                  </SummaryBox>
                </Field>
              ) : (
                <>
                  <Field>
                    Code
                    <input
                      value={form.code || ""}
                      maxLength={40}
                      onChange={(event) => set("code", event.target.value)}
                      placeholder="DAYCARE-MONTHLY"
                    />
                  </Field>
                  <Field>
                    Name
                    <input
                      value={form.name || ""}
                      maxLength={160}
                      onChange={(event) => set("name", event.target.value)}
                      placeholder="Monthly daycare care"
                    />
                  </Field>
                  <Field>
                    Facility program
                    <select
                      value={form.program_id || ""}
                      onChange={(event) =>
                        set("program_id", event.target.value)
                      }
                    >
                      <option value="">Choose an active program</option>
                      {snapshot.programs.map((item) => (
                        <option key={item.program_id} value={item.program_id}>
                          {item.facility_name} · {item.program_name} ·{" "}
                          {titleCase(item.program_type)}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field>
                    Age group (optional)
                    <input
                      value={form.age_group || ""}
                      maxLength={100}
                      onChange={(event) => set("age_group", event.target.value)}
                    />
                  </Field>
                </>
              )}
              <Field>
                Billing unit
                <select
                  value={form.billing_unit}
                  onChange={(event) => set("billing_unit", event.target.value)}
                >
                  <option value="weekly_period">
                    Weekly contracted period
                  </option>
                  <option value="biweekly_period">
                    Biweekly contracted period
                  </option>
                  <option value="monthly_period">
                    Monthly contracted period
                  </option>
                  <option value="service_event">One service event</option>
                </select>
              </Field>
              <Field>
                CAD amount
                <input
                  inputMode="decimal"
                  value={form.amount || ""}
                  onChange={(event) => set("amount", event.target.value)}
                  placeholder="0.00"
                />
              </Field>
              <Field>
                Effective from
                <input
                  type="date"
                  value={form.effective_from}
                  onChange={(event) =>
                    set("effective_from", event.target.value)
                  }
                />
              </Field>
              <Field>
                Tax
                <input value="0.00% — gated" disabled />
              </Field>
              <Field $wide>
                Description (optional)
                <textarea
                  value={form.description || ""}
                  maxLength={500}
                  onChange={(event) => set("description", event.target.value)}
                />
              </Field>
            </>
          )}
          {kind === "agreement" && (
            <>
              {agreementRevision && (
                <Field $wide>
                  <SummaryBox>
                    <h3>Exact agreement revision</h3>
                    <p>
                      {agreementRevision.child_name} · current agreement v
                      {agreementRevision.latest_version.version_number} (
                      {agreementRevision.latest_version.id}). The family account
                      and child identity remain fixed.
                    </p>
                  </SummaryBox>
                </Field>
              )}
              <Field $wide>
                Family account
                <select
                  value={form.account_id || ""}
                  onChange={(event) => {
                    set("account_id", event.target.value);
                    set("child_id", "");
                    set("rate_plan_id", "");
                  }}
                  disabled={Boolean(agreementRevision)}
                >
                  <option value="">Choose an account</option>
                  {snapshot.accounts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.family_name} · {item.account_number}
                    </option>
                  ))}
                </select>
              </Field>
              <Field $wide>
                Child
                <select
                  value={form.child_id || ""}
                  onChange={(event) => {
                    set("child_id", event.target.value);
                    set("rate_plan_id", "");
                  }}
                  disabled={!form.account_id || Boolean(agreementRevision)}
                >
                  <option value="">Choose an active child</option>
                  {childOptions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                      {item.enrollment_id
                        ? ""
                        : " · program context unavailable"}
                    </option>
                  ))}
                </select>
              </Field>
              <Field $wide>
                Published rate
                <select
                  value={form.rate_plan_id || ""}
                  onChange={(event) => set("rate_plan_id", event.target.value)}
                  disabled={
                    !selectedChild?.program_type ||
                    !selectedChild.facility_id ||
                    !selectedChild.program_id
                  }
                >
                  <option value="">
                    {selectedChild &&
                    (!selectedChild.program_type ||
                      !selectedChild.facility_id ||
                      !selectedChild.program_id)
                      ? "Program context unavailable — placement must be completed"
                      : "Choose a compatible rate plan"}
                  </option>
                  {matchingPlans.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ·{" "}
                      {formatCadMinor(item.latest_version.unit_amount_minor)} /{" "}
                      {item.latest_version.billing_unit}
                    </option>
                  ))}
                </select>
              </Field>
              <Field>
                Billing frequency
                <input
                  value={
                    form.rate_plan_id
                      ? titleCase(
                          matchingPlans.find(
                            (item) => item.id === form.rate_plan_id,
                          )?.latest_version.billing_unit || "",
                        )
                      : "Choose a compatible rate"
                  }
                  disabled
                />
              </Field>
              <Field>
                Effective from
                <input
                  type="date"
                  value={form.effective_from}
                  onChange={(event) =>
                    set("effective_from", event.target.value)
                  }
                />
              </Field>
              <Field>
                Family portion per unit
                <input
                  value={
                    form.rate_plan_id
                      ? formatCadMinor(
                          matchingPlans.find(
                            (item) => item.id === form.rate_plan_id,
                          )?.latest_version.unit_amount_minor || 0,
                        )
                      : "Choose a compatible rate"
                  }
                  disabled
                />
              </Field>
              <Field>
                Funding rule
                <input value="$0.00 — verified rule pack pending" disabled />
              </Field>
            </>
          )}
          {kind === "invoice" && (
            <>
              <Field $wide>
                Family account
                <select
                  value={form.account_id || ""}
                  onChange={(event) => {
                    set("account_id", event.target.value);
                    setAgreements([]);
                    set("service_period_start", "");
                    set("service_period_end", "");
                  }}
                >
                  <option value="">Choose an account</option>
                  {snapshot.accounts
                    .filter((account) =>
                      snapshot.agreements.some(
                        (item) => item.billing_account_id === account.id,
                      ),
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.family_name} · {item.account_number}
                      </option>
                    ))}
                </select>
              </Field>
              <Field>
                {selectedFrequency === "monthly"
                  ? "Contract month"
                  : "Period start"}
                <input
                  type={selectedFrequency === "monthly" ? "month" : "date"}
                  value={
                    selectedFrequency === "monthly"
                      ? form.service_period_start.slice(0, 7)
                      : form.service_period_start
                  }
                  disabled={!selectedFrequency}
                  onChange={(event) => {
                    if (!selectedFrequency) return;
                    setInvoicePeriod(
                      selectedFrequency,
                      selectedFrequency === "monthly"
                        ? `${event.target.value}-01`
                        : event.target.value,
                    );
                  }}
                />
              </Field>
              <Field>
                Inclusive period end
                <input type="date" value={form.service_period_end} disabled />
              </Field>
              <Field>
                Issue date
                <input
                  type="date"
                  value={form.issue_date}
                  onChange={(event) => set("issue_date", event.target.value)}
                />
              </Field>
              <Field>
                Due date
                <input
                  type="date"
                  value={form.due_date}
                  onChange={(event) => set("due_date", event.target.value)}
                />
              </Field>
              <Field $wide>
                Reviewed agreements
                <CheckList>
                  {accountAgreements.length ? (
                    accountAgreements.map((item) => (
                      <label key={item.id}>
                        <input
                          type="checkbox"
                          checked={agreements.includes(item.id)}
                          disabled={Boolean(
                            selectedFrequency &&
                              !agreements.includes(item.id) &&
                              item.latest_version.billing_frequency !==
                                selectedFrequency,
                          )}
                          onChange={(event) => {
                            setReviewed(false);
                            const next = event.target.checked
                              ? [...agreements, item.id]
                              : agreements.filter((id) => id !== item.id);
                            setAgreements(next);
                            const first = accountAgreements.find(
                              (agreement) => agreement.id === next[0],
                            );
                            if (first)
                              setInvoicePeriod(
                                first.latest_version.billing_frequency,
                                form.service_period_start || today,
                              );
                            else {
                              set("service_period_start", "");
                              set("service_period_end", "");
                            }
                          }}
                        />
                        <span>
                          <strong>{item.child_name}</strong>
                          <small>
                            {scopeForAgreement(item)} · agreement v
                            {item.latest_version.version_number} · version{" "}
                            {item.latest_version.id}
                            <br />
                            {titleCase(item.latest_version.billing_frequency)} ·
                            family{" "}
                            {formatCadMinor(
                              item.latest_version.family_amount_minor_per_unit,
                            )}{" "}
                            per unit · funding rule gated
                          </small>
                        </span>
                      </label>
                    ))
                  ) : (
                    <Empty>Choose an account to see its agreements.</Empty>
                  )}
                </CheckList>
              </Field>
              {invoicePreview && (
                <Field $wide>
                  <SummaryBox>
                    <h3>Coherent snapshot amount preview</h3>
                    <p>
                      This review is derived only from the loaded agreement and
                      rate versions. The server revalidates every source,
                      effective version, enrollment, period, and amount before
                      it can issue the immutable{" "}
                      {snapshot.sandbox ? "synthetic" : "private manual"} invoice.
                    </p>
                    <ul>
                      {invoicePreview.lines.map((line) => (
                        <li key={line.agreementVersionId}>
                          {line.childName} · {line.ratePlanName} · family{" "}
                          {formatCadMinor(line.familyMinor)} + tax{" "}
                          {formatCadMinor(line.taxMinor)} ={" "}
                          {formatCadMinor(line.totalMinor)} · agreement{" "}
                          {line.agreementVersionId} · rate {line.ratePlanVersionId}
                        </li>
                      ))}
                      <li>
                        Gross {formatCadMinor(invoicePreview.grossMinor)} · funding{" "}
                        {formatCadMinor(invoicePreview.fundingMinor)} · family{" "}
                        {formatCadMinor(invoicePreview.familyMinor)} · tax{" "}
                        {formatCadMinor(invoicePreview.taxMinor)}
                      </li>
                      <li>
                        <strong>
                          Preview total {formatCadMinor(invoicePreview.totalMinor)}
                        </strong>
                      </li>
                    </ul>
                  </SummaryBox>
                </Field>
              )}
              {invoicePreviewError && (
                <Field $wide>
                  <SummaryBox role="alert">
                    <h3>Invoice review is unavailable</h3>
                    <p>{invoicePreviewError}</p>
                    <p>
                      Review and issue are blocked until every selected
                      agreement and its pinned rate version cover the full
                      service period.
                    </p>
                  </SummaryBox>
                </Field>
              )}
              {reviewed && (
                <Field $wide>
                  <SummaryBox>
                    <h3>Final confirmation</h3>
                    <p>
                      CareSync will issue one immutable line for each selected
                      reviewed agreement at quantity one. The server owns
                      eligibility checks, effective-version pinning, and all
                      monetary calculations.
                    </p>
                    <ul>
                      <li>
                        {selectedAgreements.length} reviewed agreement
                        {selectedAgreements.length === 1 ? "" : "s"}
                      </li>
                      <li>
                        Service: {formatDateOnly(form.service_period_start)} –{" "}
                        {formatDateOnly(form.service_period_end)}
                      </li>
                      <li>
                        Issue {formatDateOnly(form.issue_date)} · due{" "}
                        {formatDateOnly(form.due_date)}
                      </li>
                      <li>
                        Snapshot preview total{" "}
                        {invoicePreview
                          ? formatCadMinor(invoicePreview.totalMinor)
                          : "unavailable"}
                      </li>
                      <li>
                        No client-entered amount, tax decision, or automatic
                        delivery
                      </li>
                    </ul>
                  </SummaryBox>
                </Field>
              )}
            </>
          )}
          {kind === "payment" && (
            <>
              <Field $wide>
                Family account
                <select
                  value={form.account_id || ""}
                  onChange={(event) => {
                    set("account_id", event.target.value);
                    set("payer_guardian_id", "");
                  }}
                >
                  <option value="">Choose an account</option>
                  {snapshot.accounts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.family_name} · {item.account_number}
                    </option>
                  ))}
                </select>
              </Field>
              <Field $wide>
                Actual payer
                <select
                  value={form.payer_guardian_id || ""}
                  onChange={(event) =>
                    set("payer_guardian_id", event.target.value)
                  }
                  disabled={!sourceFamily}
                >
                  <option value="">Choose the guardian who paid</option>
                  {sourceFamily?.guardians.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                      {item.email ? ` · ${item.email}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Field>
                Amount received
                <input
                  inputMode="decimal"
                  value={form.amount || ""}
                  onChange={(event) => set("amount", event.target.value)}
                  placeholder="0.00"
                />
              </Field>
              <Field>
                Method
                <select
                  value={form.method}
                  onChange={(event) => set("method", event.target.value)}
                >
                  <option value="cash">Cash</option>
                  <option value="cheque">Cheque</option>
                  <option value="e_transfer">E-transfer</option>
                  <option value="other">Other</option>
                </select>
              </Field>
              <Field>
                Received at
                <input
                  type="datetime-local"
                  value={form.received_at}
                  onChange={(event) => set("received_at", event.target.value)}
                />
              </Field>
              <Field>
                Receipt / transaction reference (required)
                <input
                  value={form.external_reference || ""}
                  maxLength={120}
                  onChange={(event) =>
                    set("external_reference", event.target.value)
                  }
                  placeholder="For example CASH-2026-0001 or bank confirmation"
                  required
                />
              </Field>
              <Field $wide>
                Operator confirmation{" "}
                {["cash", "other"].includes(form.method)
                  ? "(required)"
                  : "(optional)"}
                <textarea
                  value={form.operator_confirmation_note || ""}
                  maxLength={500}
                  onChange={(event) =>
                    set("operator_confirmation_note", event.target.value)
                  }
                  placeholder="Who confirmed receipt and what evidence was checked?"
                />
              </Field>
              <Field $wide>
                Internal memo (optional)
                <textarea
                  value={form.memo || ""}
                  maxLength={500}
                  onChange={(event) => set("memo", event.target.value)}
                />
              </Field>
            </>
          )}
          {kind === "allocation" && (
            <>
              <Field $wide>
                Available payment
                <select
                  value={form.payment_id || ""}
                  onChange={(event) => {
                    set("payment_id", event.target.value);
                    set("invoice_id", "");
                  }}
                >
                  <option value="">Choose a payment</option>
                  {availablePayments.map((item) => (
                    <option key={item.id} value={item.id}>
                      {formatDateTime(item.received_at)} ·{" "}
                      {formatCadMinor(item.unapplied_minor)} available
                    </option>
                  ))}
                </select>
              </Field>
              <Field $wide>
                Outstanding invoice
                <select
                  value={form.invoice_id || ""}
                  onChange={(event) => set("invoice_id", event.target.value)}
                  disabled={!payment}
                >
                  <option value="">
                    Choose an invoice in the same account
                  </option>
                  {invoiceChoices.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.invoice_number} · {item.family_name} ·{" "}
                      {formatCadMinor(item.outstanding_minor)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field $wide>
                Amount to allocate
                <input
                  inputMode="decimal"
                  value={form.amount || ""}
                  onChange={(event) => set("amount", event.target.value)}
                  placeholder="0.00"
                />
              </Field>
            </>
          )}
          {kind === "credit" && (
            <>
              <Field $wide>
                Outstanding invoice
                <select
                  value={form.invoice_id || ""}
                  onChange={(event) => set("invoice_id", event.target.value)}
                >
                  <option value="">Choose an invoice</option>
                  {snapshot.invoices.filter(invoiceOutstanding).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.invoice_number} · {item.family_name} ·{" "}
                      {formatCadMinor(item.outstanding_minor)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field>
                Credit amount
                <input
                  inputMode="decimal"
                  value={form.amount || ""}
                  onChange={(event) => set("amount", event.target.value)}
                  placeholder="0.00"
                />
              </Field>
              <Field>
                Reason
                <select
                  value={form.reason_code}
                  onChange={(event) => set("reason_code", event.target.value)}
                >
                  <option value="billing_correction">Billing correction</option>
                  <option value="service_adjustment">Service adjustment</option>
                  <option value="approved_waiver">Approved waiver</option>
                </select>
              </Field>
              <Field $wide>
                Audit note (optional)
                <textarea
                  value={form.note || ""}
                  maxLength={500}
                  onChange={(event) => set("note", event.target.value)}
                />
              </Field>
              {selectedInvoice && (
                <Field $wide>
                  <SummaryBox role={creditPreviewError ? "alert" : undefined}>
                    <h3>Resulting invoice balance preview</h3>
                    <p>
                      {selectedInvoice.invoice_number} currently has{" "}
                      {formatCadMinor(selectedInvoice.outstanding_minor)}
                      outstanding. This append-only credit does not alter the
                      original invoice or payment evidence.
                    </p>
                    <ul>
                      <li>
                        Proposed credit:{" "}
                        {creditPreviewAmount == null
                          ? "enter a valid amount"
                          : formatCadMinor(creditPreviewAmount)}
                      </li>
                      <li>
                        Resulting outstanding:{" "}
                        {creditResultingBalance == null
                          ? "not yet available"
                          : formatCadMinor(creditResultingBalance)}
                      </li>
                    </ul>
                    <p>
                      {creditPreviewError ||
                        "The server revalidates the exact current outstanding balance before committing the credit."}
                    </p>
                  </SummaryBox>
                </Field>
              )}
            </>
          )}
        </Fields>
        {formError && (
          <SummaryBox role="alert">
            <h3>Review this command</h3>
            <p>{formError}</p>
          </SummaryBox>
        )}
      </form>
    </BillingDialog>
  );
}

export function BillingWorkspace() {
  const [params] = useSearchParams();
  return params.get("view") === "setup" ? (
    <BillingSetupWorkspace />
  ) : (
    <BillingLedgerWorkspace />
  );
}

export default BillingWorkspace;

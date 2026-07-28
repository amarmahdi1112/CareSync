import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowPathIcon,
  BriefcaseIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  DocumentCheckIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  ShieldCheckIcon,
  UsersIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { useSession } from "../../auth/SessionContext";
import { hasPermission } from "../../auth/accessModel";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import {
  candidateTransitions,
  hiringApi,
  jobTransitions,
  type Candidate,
  type CandidateStage,
  type HiringWorkspace,
  type InterviewRecord,
  type ListingInput,
  type OfferInput,
  type ScreeningSchemaVersion,
  type AtsServiceWindow,
  type ServiceWeekday,
  type StructuredRoleTerms,
} from "./hiringApi";
import { useRealtimeRefresh, useRealtimeState } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import { zonedDateTimeToIso } from './zonedDateTime';
import { offerDisplayStatus } from './offerPresentation';
import {
  latestScreeningDecision,
  screeningApi,
  type EmployerScreeningProjection,
  type ScreeningDecision,
  type ScreeningRequirement,
  type SharedScreeningDocument,
  type ViewedScreeningSource,
} from './screeningApi';
import { adminProvisioningPolicy } from './provisioningPolicy';
import { clearNotificationTarget, resolveNotificationTarget } from '../notifications/notificationTarget';
import {
  marketplaceApi,
  type CredentialNotification,
  type DiscoverableCandidate,
} from "./marketplaceApi";
import { fetchHiringRealtimeSnapshot } from './hiringRealtime';

const Page = styled.div`
  display: grid;
  min-width: 0;
  gap: 22px;
  padding-bottom: 42px;
  > section {
    min-width: 0;
  }
`;
const Header = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  h1 {
    margin: 8px 0 6px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.7rem, 3vw, 2.5rem);
    font-weight: 600;
    letter-spacing: -0.05em;
  }
  p {
    max-width: 70ch;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.82rem;
    line-height: 1.7;
  }
  @media (max-width: 740px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;
const Metrics = styled.section`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 900px) {
    grid-template-columns: repeat(2, 1fr);
  }
  @media (max-width: 460px) {
    grid-template-columns: 1fr;
  }
`;
const Metric = styled(GlassPanel)`
  padding: 16px 18px;
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.7rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 7px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.65rem;
    font-weight: 600;
  }
`;
const Tabs = styled.nav`
  display: flex;
  gap: 4px;
  overflow: auto;
  padding: 5px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 6px 12px 6px;
  background: ${({ theme }) => theme.color.surface};
`;
const Tab = styled.button<{ $active: boolean }>`
  display: flex;
  min-width: max-content;
  min-height: 42px;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  border: 1px solid
    ${({ $active, theme }) => ($active ? theme.color.borderStrong : "transparent")};
  border-radius: 9px 4px 9px 4px;
  color: ${({ $active, theme }) => ($active ? theme.color.text : theme.color.textMuted)};
  background: ${({ $active, theme }) => ($active ? theme.color.surfaceStrong : "transparent")};
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  svg {
    width: 17px;
  }
`;
const SectionHead = styled.div`
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.15rem;
    font-weight: 600;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.76rem;
  }
`;
const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 1100px) {
    grid-template-columns: repeat(2, 1fr);
  }
  @media (max-width: 680px) {
    grid-template-columns: 1fr;
  }
`;
const ListingCard = styled(GlassPanel)`
  display: grid;
  gap: 16px;
  padding: 18px;
  h3 {
    margin: 0;
    font-size: 0.96rem;
    font-weight: 600;
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
    line-height: 1.55;
  }
  .top,
  .bottom {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }
  .bottom {
    align-items: center;
    padding-top: 4px;
    border-top: 1px solid ${({ theme }) => theme.color.border};
  }
  .count {
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.74rem;
  }
`;
const Select = styled.select`
  min-height: 40px;
  padding: 0 30px 0 10px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 8px 4px 8px 4px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.control};
  font: inherit;
  font-size: 0.75rem;
`;
const Board = styled.div`
  display: grid;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  grid-auto-flow: column;
  grid-auto-columns: minmax(252px, 1fr);
  grid-template-rows: minmax(230px, auto);
  gap: 10px;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
  padding: 1px 1px 12px;
  scroll-snap-type: inline proximity;
  scrollbar-gutter: stable;
  @media (max-width: 640px) {
    grid-auto-columns: minmax(244px, 86vw);
  }
`;
const Column = styled(GlassPanel)`
  min-width: 0;
  align-self: stretch;
  padding: 12px;
  scroll-snap-align: start;
`;
const ColumnHead = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 2px 3px 10px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  strong {
    font-size: 0.76rem;
    text-transform: capitalize;
  }
  span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
`;
const CandidateCard = styled.article<{ $focused?: boolean }>`
  display: grid;
  min-width: 0;
  gap: 9px;
  padding: 11px;
  border: 1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.border};
  border-radius: 9px 4px 9px 4px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: ${({ $focused, theme }) => $focused ? `0 0 0 3px color-mix(in srgb, ${theme.color.cyan} 18%, transparent)` : 'none'};
  & + & {
    margin-top: 8px;
  }
  strong,
  small {
    display: block;
    min-width: 0;
  }
  strong {
    font-size: 0.78rem;
  }
  small {
    margin-top: 3px;
    overflow: hidden;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.7rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    display: flex;
    min-width: 0;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-start;
    gap: 6px;
  }
  .actions > select {
    width: 100%;
    min-width: 0;
  }
`;
const OfferTable = styled(GlassPanel)`
  overflow-x: auto;
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    padding: 14px 16px;
    border-bottom: 1px solid ${({ theme }) => theme.color.border};
    text-align: left;
    font-size: 0.75rem;
  }
  th {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  tr:last-child td {
    border-bottom: 0;
  }
  .person strong,
  .person small {
    display: block;
  }
  .person small {
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
  }
`;
const State = styled(GlassPanel)`
  padding: 48px 22px;
  text-align: center;
  svg {
    width: 40px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 12px 0 5px;
    font-size: 1rem;
  }
  p {
    max-width: 58ch;
    margin: 0 auto 16px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.78rem;
    line-height: 1.6;
  }
`;
const Notice = styled.div<{ $error?: boolean }>`
  display: flex;
  gap: 9px;
  padding: 12px 14px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.borderStrong)};
  border-radius: 9px 4px 9px 4px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.textSoft)};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.77rem;
  svg {
    width: 18px;
  }
`;
const ProvisioningDialogNotice = styled(Notice)`
  grid-column: 1/-1;
`;
const ProvisioningActionBoundary = styled.div`
  display: grid;
  gap: 6px;
  max-width: 48ch;
  > p {
    margin: 0;
    color: ${({ theme }) => theme.color.amber};
    font-size: 0.69rem;
    line-height: 1.5;
    white-space: normal;
  }
`;
const PrivateLink = styled(GlassPanel)`
  display: grid;
  gap: 10px;
  padding: 16px 18px;
  h2 {
    margin: 0;
    font-size: 0.88rem;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.74rem;
    line-height: 1.55;
  }
  code {
    display: block;
    padding: 11px;
    overflow-wrap: anywhere;
    border: 1px solid ${({ theme }) => theme.color.border};
    border-radius: 8px 4px 8px 4px;
    color: ${({ theme }) => theme.color.cyan};
    background: ${({ theme }) => theme.color.control};
    font-size: 0.7rem;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
`;
const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 600;
  display: grid;
  place-items: center;
  padding: 16px;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
`;
const Dialog = styled(GlassPanel)`
  width: min(620px, 100%);
  max-height: 88vh;
  overflow: auto;
  padding: 22px;
`;
const DialogHead = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
  h2 {
    margin: 6px 0 4px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.25rem;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;
const Form = styled.form`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  @media (max-width: 540px) {
    grid-template-columns: 1fr;
  }
`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => ($wide ? "1/-1" : "auto")};
  gap: 7px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.73rem;
  font-weight: 600;
  input,
  textarea,
  select {
    width: 100%;
    min-height: 44px;
    padding: 10px 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 8px 4px 8px 4px;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    &:focus {
      border-color: ${({ theme }) => theme.color.cyan};
    }
  }
  textarea {
    min-height: 92px;
    resize: vertical;
  }
`;
const FormActions = styled.div`
  display: flex;
  grid-column: 1/-1;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 5px;
`;
const ReviewGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  @media (max-width: 560px) {
    grid-template-columns: 1fr;
  }
`;
const ReviewCard = styled.div`
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 9px 4px 9px 4px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  h3 {
    margin: 0 0 9px;
    font-size: 0.78rem;
  }
  p {
    margin: 3px 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.73rem;
    line-height: 1.55;
  }
  strong {
    color: ${({ theme }) => theme.color.textSoft};
    font-weight: 600;
  }
`;
const ScreeningSection = styled.section`
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  > h3 { margin: 0; font-size: 0.95rem; }
  > p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: 0.74rem; }
`;
const ScreeningShareCard = styled.div`
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 10px 4px 10px 4px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  h4 { margin: 0; font-size: 0.8rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: 0.72rem; line-height: 1.5; }
`;
const IdentityReconciliationAlert = styled.div`
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.amber};
  border-radius: 9px 4px 9px 4px;
  color: ${({ theme }) => theme.color.textSoft};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, ${({ theme }) => theme.color.amber});
  > svg { width: 20px; color: ${({ theme }) => theme.color.amber}; }
  strong { display: block; color: ${({ theme }) => theme.color.amber}; font-size: 0.76rem; }
  p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textSoft}; }
`;
const ProtectedViewer = styled.div`
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 8px;
  background: ${({ theme }) => theme.color.canvas};
  .viewer-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; }
  img, iframe { width: 100%; height: min(62vh, 680px); border: 0; object-fit: contain; background: #fff; }
`;
const EvidenceTrail = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 9px;
`;
const Confirmation = styled.div`
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 9px 4px 9px 4px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: 0.76rem;
  }
  .row span {
    color: ${({ theme }) => theme.color.textMuted};
  }
`;
const ConfirmChoice = styled.label`
  display: flex;
  grid-column: 1/-1;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 9px 4px 9px 4px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.74rem;
  line-height: 1.55;
  input {
    margin-top: 3px;
    accent-color: ${({ theme }) => theme.color.cyan};
  }
`;
const WindowEditor = styled.div`
  display: grid;
  grid-column: 1/-1;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 9px 4px 9px 4px;
  .window { display: grid; gap: 9px; padding: 10px; background: ${({ theme }) => theme.color.surfaceStrong}; }
  .days { display: flex; flex-wrap: wrap; gap: 5px; }
  .days button { min-height: 32px; padding: 0 9px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 999px; color: ${({ theme }) => theme.color.textMuted}; background: ${({ theme }) => theme.color.control}; }
  .days button[aria-pressed="true"] { border-color: ${({ theme }) => theme.color.cyan}; color: ${({ theme }) => theme.color.text}; }
  .times { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .times input { min-height: 42px; padding: 0 10px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 8px 4px; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; }
`;
const DiscoverControls = styled(GlassPanel)`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px;
  margin-bottom: 12px;
  label {
    display: flex;
    min-height: 44px;
    flex: 1;
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 8px 4px 8px 4px;
    background: ${({ theme }) => theme.color.control};
  }
  svg {
    width: 18px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  input {
    width: 100%;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font: inherit;
  }
  @media (max-width: 600px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const PipelineControls = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 0.55fr) auto;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 11px;
  label {
    display: flex;
    min-width: 0;
    min-height: 44px;
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 8px 4px 8px 4px;
    background: ${({ theme }) => theme.color.control};
  }
  svg { width: 18px; flex: 0 0 auto; color: ${({ theme }) => theme.color.textMuted}; }
  input, select {
    width: 100%;
    min-width: 0;
    min-height: 42px;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font: inherit;
    font-size: .75rem;
  }
  @media (max-width: 720px) { grid-template-columns: 1fr; }
`;

type View = "listings" | "applicants" | "discover" | "offers" | "handoff";
const views: readonly View[] = ["listings", "applicants", "discover", "offers", "handoff"];
const isView = (value: string | null): value is View => Boolean(value && views.includes(value as View));
type Modal =
  | { kind: "listing" }
  | { kind: "offer"; candidate: Candidate }
  | null;
const stages: CandidateStage[] = [
  "invited",
  "applied",
  "screening",
  "interview",
  "offer",
  "accepted",
  "hired",
];
const statusTone = (
  status: string,
): "success" | "warning" | "info" | "neutral" =>
  ["open", "accepted", "hired"].includes(status)
    ? "success"
    : ["draft", "sent", "offer"].includes(status)
      ? "warning"
      : status === "interview"
        ? "info"
        : "neutral";
const employerTransitions = (candidate: Candidate) =>
  candidateTransitions(candidate.stage).filter(
    (target) =>
      !(target === "interview" && candidate.source !== "private_invitation"),
  );

export function ProvisioningAction({
  pathway,
  certificationVerificationStatus,
  screeningSchemaVersion,
  busy,
  defaultLabel,
  onStart,
}: {
  pathway: Candidate['pathway'];
  certificationVerificationStatus: Candidate['certification_verification_status'];
  screeningSchemaVersion: ScreeningSchemaVersion;
  busy: boolean;
  defaultLabel: string;
  onStart: () => void;
}) {
  const policy = adminProvisioningPolicy(
    screeningSchemaVersion,
    pathway,
    certificationVerificationStatus,
  );
  return (
    <ProvisioningActionBoundary>
      <ActionButton
        $variant="primary"
        type="button"
        disabled={busy || !policy.canProvisionEducator}
        onClick={policy.canProvisionEducator ? onStart : undefined}
      >
        {policy.canProvisionEducator ? <ShieldCheckIcon /> : <LockClosedIcon />}
        {policy.actionLabel || defaultLabel}
      </ActionButton>
      {policy.guidance ? <p>{policy.guidance}</p> : null}
    </ProvisioningActionBoundary>
  );
}

export default function JobsPage() {
  const session = useSession();
  const organizationId = session.organization?.id || "";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const canManage = hasPermission(session.user, "ats:manage");
  const canHire = hasPermission(session.user, "ats:hire");
  const [workspace, setWorkspace] = useState<HiringWorkspace | null>(null);
  const screeningEnabled = workspace?.screening_schema_version === "0030";
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [view, setViewState] = useState<View>(() => {
    const requested = searchParams.get("view");
    return isView(requested) ? requested : "listings";
  });
  const setView = (next: View) => {
    setViewState(next);
    if (next !== 'applicants') setFocusedApplicationId(null);
    setSearchParams((current) => {
      const params = new URLSearchParams(current);
      if (next === "listings") params.delete("view");
      else params.set("view", next);
      return params;
    }, { replace: true });
  };
  const [modal, setModal] = useState<Modal>(null);
  const [busy, setBusy] = useState("");
  const [focusedApplicationId, setFocusedApplicationId] = useState<string | null>(null);
  const offerOperationIds = useRef(new Map<string, string>());
  useEffect(() => { workspace?.offers.forEach((group) => group.versions.forEach((offer) => { if (offer.client_operation_id && offerOperationIds.current.get(offer.application_id) === offer.client_operation_id) offerOperationIds.current.delete(offer.application_id); })); }, [workspace]);
  const streamState = useRealtimeState();
  const [reviewCandidate, setReviewCandidate] = useState<Candidate | null>(
    null,
  );
  const [handoffCandidate, setHandoffCandidate] = useState<{
    candidate: Candidate;
    operationId: string;
  } | null>(null);
  const [handoffResult, setHandoffResult] = useState<{
    name: string;
    membershipCreated: boolean;
    membershipId: string;
    transportAuthorityWithheld: boolean;
  } | null>(null);
  const [discoverable, setDiscoverable] = useState<DiscoverableCandidate[]>([]);
  const [discoverPhase, setDiscoverPhase] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [discoverError, setDiscoverError] = useState("");
  const discoverRequestSequence = useRef(0);
  const [city, setCity] = useState("");
  const [cityQuery, setCityQuery] = useState("");
  const [requestedProfiles, setRequestedProfiles] = useState<Set<string>>(
    () => new Set(),
  );
  const [credentialNotifications, setCredentialNotifications] = useState<
    CredentialNotification[]
  >([]);
  const [credentialNotificationError, setCredentialNotificationError] = useState("");
  const [interestProfile, setInterestProfile] =
    useState<DiscoverableCandidate | null>(null);
  const [interviewCandidate, setInterviewCandidate] =
    useState<Candidate | null>(null);
  const [proposalReview, setProposalReview] = useState<{
    candidate: Candidate;
    interview: InterviewRecord;
  } | null>(null);
  const [applicantQuery, setApplicantQuery] = useState("");
  const [applicantListing, setApplicantListing] = useState("all");
  useEffect(() => {
    const requested = searchParams.get("view");
    if (isView(requested) && requested !== view) setViewState(requested);
    if (!requested && view !== "listings") setViewState("listings");
  }, [searchParams, view]);
  useEffect(() => {
    const applicationId = searchParams.get('application');
    if (!applicationId || !workspace || phase !== 'ready') return;
    const candidate = workspace.candidates.find((item) => item.id === applicationId);
    const resolution = resolveNotificationTarget(
      applicationId,
      workspace.candidates
        .filter((item) => !['rejected', 'withdrawn'].includes(item.stage))
        .map((item) => item.id),
    );
    const targetCandidate = resolution.status === 'available' ? candidate : undefined;
    setViewState('applicants'); setApplicantQuery(''); setApplicantListing('all');
    setFocusedApplicationId(targetCandidate ? applicationId : null);
    setNotice(targetCandidate
      ? `Opened ${targetCandidate.first_name} ${targetCandidate.last_name}'s application from the notification.`
      : resolution.status === 'invalid'
        ? 'The notification contained an invalid application target. Current applicants are shown instead.'
        : 'That application is no longer available in the active pipeline. Current applicants are shown instead.');
    setSearchParams((current) => {
      const params = clearNotificationTarget(current, 'application');
      params.set('view', 'applicants');
      return params;
    }, { replace: true });
    if (!targetCandidate) return;
    const frame = requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(`[data-application-id="${CSS.escape(applicationId)}"]`);
      card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      card?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [phase, searchParams, setSearchParams, workspace]);
  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setPhase("loading");
    setError("");
    hiringApi
      .workspace(organizationId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setWorkspace(data);
          setPhase("ready");
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Hiring could not be loaded.",
          );
          setPhase("error");
        }
      });
    return () => controller.abort();
  }, [organizationId, revision]);
  useEffect(() => {
    if (!organizationId) return;
    let active = true;
    marketplaceApi
      .credentialNotifications()
      .then((rows) => {
        if (active) {
          setCredentialNotifications(rows);
          setCredentialNotificationError("");
        }
      })
      .catch((caught) => {
        if (active) setCredentialNotificationError(caught instanceof Error ? caught.message : "Credential updates could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [organizationId, revision]);
  const refreshHiringWorkspace = useCallback(async () => {
    const refreshDiscovery = canManage && view === 'discover';
    const discoverySequence = refreshDiscovery ? ++discoverRequestSequence.current : 0;
    try {
      const snapshot = await fetchHiringRealtimeSnapshot(
        organizationId,
        refreshDiscovery ? cityQuery : null,
      );
      setWorkspace(snapshot.workspace); setCredentialNotifications(snapshot.credentialNotifications); setCredentialNotificationError(''); setPhase('ready'); setError('');
      if (
        snapshot.discoverable
        && discoverySequence === discoverRequestSequence.current
      ) {
        setDiscoverable(snapshot.discoverable); setDiscoverPhase('ready'); setDiscoverError('');
      }
    } catch (caught) {
      if (refreshDiscovery && discoverySequence === discoverRequestSequence.current) {
        setDiscoverable([]);
        setDiscoverError(caught instanceof Error ? caught.message : 'Candidate discovery could not be refreshed.');
        setDiscoverPhase('error');
      }
      throw caught;
    }
  }, [canManage, cityQuery, organizationId, view]);
  useRealtimeRefresh({ scope: 'hiring', organizationId, enabled: Boolean(organizationId), eventPrefixes: ['job.', 'candidate.', 'application.', 'interview.', 'offer.', 'marketplace.', 'hire.', 'screening.'], entityTypes: featureIntegrationManifest.hiring.realtimeEntities, refresh: refreshHiringWorkspace });
  useEffect(() => {
    if (view !== "discover" || !canManage) return;
    const controller = new AbortController();
    const sequence = ++discoverRequestSequence.current;
    setDiscoverPhase("loading");
    setDiscoverError("");
    marketplaceApi
      .searchCandidates(cityQuery, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted && sequence === discoverRequestSequence.current) {
          setDiscoverable(items);
          setDiscoverPhase("ready");
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted && sequence === discoverRequestSequence.current) {
          setDiscoverError(
            caught instanceof Error
              ? caught.message
              : "Candidate search could not be loaded.",
          );
          setDiscoverPhase("error");
        }
      });
    return () => controller.abort();
  }, [canManage, cityQuery, view]);
  const refresh = (message: string) => {
    setNotice(message);
    setRevision((value) => value + 1);
  };
  const offers = useMemo(
    () =>
      new Map(
        (workspace?.offers || []).map((item) => [
          item.candidate_id,
          [...item.versions].sort((a, b) => b.version - a.version),
        ]),
      ),
    [workspace],
  );
  const activeCandidates =
    workspace?.candidates.filter(
      (item) => !["rejected", "withdrawn"].includes(item.stage),
    ) || [];
  const visibleCandidates = activeCandidates.filter((candidate) => {
    const query = applicantQuery.trim().toLowerCase();
    const listing = workspace?.listings.find((item) => item.id === candidate.listing_id);
    const matchesQuery = !query || `${candidate.first_name} ${candidate.last_name} ${candidate.email} ${listing?.title || ""}`.toLowerCase().includes(query);
    return matchesQuery && (applicantListing === "all" || candidate.listing_id === applicantListing);
  });
  const hasOpenInterview = (applicationId: string) =>
    workspace?.interviews.some(
      (item) =>
        item.application_id === applicationId &&
        ["requested", "confirmed", "candidate_proposed"].includes(item.status),
    ) || false;
  const candidateProposal = (applicationId: string) =>
    workspace?.interviews.find(
      (item) =>
        item.application_id === applicationId &&
        item.status === "candidate_proposed",
    );
  const mutate = async (
    key: string,
    action: () => Promise<unknown>,
    message: string,
  ) => {
    setBusy(key);
    setError("");
    try {
      await action();
      refresh(message);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The change could not be saved.",
      );
    } finally {
      setBusy("");
    }
  };

  if (phase === "loading")
    return (
      <Page>
        <State $accent="cyan" aria-busy="true">
          <ArrowPathIcon />
          <h2>Preparing the hiring workspace.</h2>
          <p>
            CareSync is loading listings, consented applicants, interviews, and
            offer history.
          </p>
        </State>
      </Page>
    );
  if (phase === "error" || !workspace)
    return (
      <Page>
        <State $accent="amber">
          <ExclamationTriangleIcon />
          <h2>The hiring workspace could not be loaded.</h2>
          <p>{error}</p>
          <ActionButton onClick={() => setRevision((value) => value + 1)}>
            <ArrowPathIcon /> Try again
          </ActionButton>
        </State>
      </Page>
    );
  const openListings = workspace.listings.filter(
    (item) => item.status === "open",
  );
  const latestOffers = activeCandidates
    .map((candidate) => ({ candidate, offer: offers.get(candidate.id)?.[0] }))
    .filter((item) => item.offer);
  const offerCandidates = activeCandidates.filter((item) =>
    ["interview", "offer", "accepted", "hired"].includes(item.stage),
  );
  const activeInterviewApplicationIds = new Set(
    activeCandidates
      .filter((candidate) =>
        ["applied", "screening", "interview"].includes(candidate.stage),
      )
      .map((candidate) => candidate.id),
  );
  const activeInterviewCount = workspace.interviews.filter(
    (interview) =>
      ["requested", "confirmed", "candidate_proposed"].includes(
        interview.status,
      ) && activeInterviewApplicationIds.has(interview.application_id),
  ).length;
  return (
    <Page>
      <Header>
        <div>
          <Eyebrow>
            <LockClosedIcon width={14} /> Employer marketplace · consent first
          </Eyebrow>
          <h1>Jobs & hiring.</h1>
          <p>
            Review incoming applicants, discover opt-in talent, request
            interviews, and move qualified candidates toward versioned offers
            and safe provisioning.
          </p>
        </div>
        <HeaderActions>
          <StatusChip
            $tone={
              streamState === "connected"
                ? "success"
                : streamState === "reconnecting"
                  ? "warning"
                  : "neutral"
            }
          >
            {streamState === "connected"
              ? "Connected"
              : streamState === "reconnecting" || streamState === "connecting"
                ? "Reconnecting"
                : "Manual"}
          </StatusChip>
          <ActionButton
            type="button"
            onClick={() => setRevision((value) => value + 1)}
          >
            <ArrowPathIcon /> Refresh
          </ActionButton>
          {canManage && (
            <ActionButton
              $variant="primary"
              onClick={() => setModal({ kind: "listing" })}
            >
              <PlusIcon /> New listing
            </ActionButton>
          )}
        </HeaderActions>
      </Header>
      {notice && (
        <Notice role="status">
          <CheckCircleIcon />
          {notice}
        </Notice>
      )}
      {error && (
        <Notice $error role="alert">
          <ExclamationTriangleIcon />
          {error}
        </Notice>
      )}
      {credentialNotificationError && (
        <Notice $error role="alert">
          <ExclamationTriangleIcon />
          <span>Hiring data is available, but credential-update notifications are not current. {credentialNotificationError}</span>
        </Notice>
      )}
      {credentialNotifications
        .filter((item) => !item.read_at)
        .map((item) => (
          <PrivateLink key={item.id} $accent="plasma" role="status">
            <h2>Credential updated · {item.candidate_name}</h2>
            <p>
              {item.previous_certificate_type
                ? `${item.previous_certificate_type} → `
                : ""}
              {item.certificate_type} · submitted{" "}
              {new Date(item.created_at).toLocaleString()}. Review the candidate
              evidence before relying on the new level.
            </p>
            <div className="actions">
              <ActionButton
                type="button"
                $variant="primary"
                onClick={() =>
                  void mutate(
                    item.id,
                    () => marketplaceApi.readCredentialNotification(item.id),
                    "Credential notification marked reviewed.",
                  ).then(() =>
                    setCredentialNotifications((rows) =>
                      rows.map((row) =>
                        row.id === item.id
                          ? { ...row, read_at: new Date().toISOString() }
                          : row,
                      ),
                    ),
                  )
                }
              >
                <DocumentCheckIcon /> Mark reviewed
              </ActionButton>
            </div>
          </PrivateLink>
        ))}
      {handoffResult && (
        <PrivateLink
          $accent={handoffResult.membershipCreated ? "cyan" : "amber"}
          role="status"
        >
          <h2>
            {handoffResult.membershipCreated
              ? "Educator membership provisioned"
              : "Existing educator membership linked"}
          </h2>
          <p>
            {handoffResult.membershipCreated
              ? `A new educator membership was created for ${handoffResult.name} with zero assigned rooms.`
              : `No new membership was created for ${handoffResult.name}; an existing active educator membership was reused and provisioning added no rooms. Review any pre-existing assignments.`}{" "}
            {handoffResult.transportAuthorityWithheld
              ? 'Transport authority was not granted. '
              : ''}
            Continue to Staff & access for deliberate facility and room review.
          </p>
          <div className="actions">
            <ActionButton
              type="button"
              $variant="primary"
              onClick={() => navigate("/staff")}
            >
              <ChevronRightIcon /> Continue to Staff & access
            </ActionButton>
            <ActionButton type="button" onClick={() => setHandoffResult(null)}>
              Dismiss
            </ActionButton>
          </div>
        </PrivateLink>
      )}
      <Metrics>
        <Metric $accent="cyan">
          <span>Open listings</span>
          <strong>{openListings.length}</strong>
        </Metric>
        <Metric $accent="plasma">
          <span>Incoming public</span>
          <strong>
            {
              activeCandidates.filter(
                (item) => item.source === "marketplace_application",
              ).length
            }
          </strong>
        </Metric>
        <Metric $accent="amber">
          <span>Active interviews</span>
          <strong>{activeInterviewCount}</strong>
        </Metric>
        <Metric $accent="cyan">
          <span>Offers awaiting</span>
          <strong>
            {
              latestOffers.filter((item) => item.offer && offerDisplayStatus(item.offer) === "sent")
                .length
            }
          </strong>
        </Metric>
      </Metrics>
      <Tabs aria-label="Hiring workspace views">
        {(
          [
            ["listings", BriefcaseIcon, "Listings"],
            ["applicants", UsersIcon, "Applicants"],
            ["discover", MagnifyingGlassIcon, "Discover talent"],
            ["offers", CheckCircleIcon, "Offer review"],
            ["handoff", ChevronRightIcon, "Provisioning"],
          ] as const
        )
          .filter(([id]) => id !== "discover" || canManage)
          .map(([id, Icon, label]) => (
            <Tab
              key={id}
              $active={view === id}
              aria-current={view === id ? "page" : undefined}
              onClick={() => setView(id)}
            >
              <Icon />
              {label}
            </Tab>
          ))}
      </Tabs>
      {view === "listings" && (
        <section>
          <SectionHead>
            <div>
              <h2>Job listings</h2>
              <p>
                Open roles publish to the candidate marketplace. Candidates apply
                from their own account, while employer outreach starts from the
                consent-based talent directory.
              </p>
            </div>
          </SectionHead>
          {workspace.listings.length ? (
            <Cards>
              {workspace.listings.map((listing) => (
                <ListingCard
                  key={listing.id}
                  $accent={listing.status === "open" ? "cyan" : "plasma"}
                >
                  <div className="top">
                    <div>
                      <h3>{listing.title}</h3>
                      <p>
                        {listing.location} ·{" "}
                        {listing.employment_type.replaceAll("_", " ")}
                      </p>
                    </div>
                    <StatusChip $tone={statusTone(listing.status)}>
                      {listing.status}
                    </StatusChip>
                  </div>
                  <p>{listing.summary}</p>
                  <div className="bottom">
                    <span className="count">
                      {listing.applicant_count} applicant
                      {listing.applicant_count === 1 ? "" : "s"}
                    </span>
                    {canManage && jobTransitions(listing.status).length > 0 && (
                      <Select
                        aria-label={`Change status for ${listing.title}`}
                        defaultValue=""
                        disabled={busy === listing.id}
                        onChange={(event) =>
                          void mutate(
                            listing.id,
                            () =>
                              hiringApi.setListingStatus(
                                listing,
                                event.target.value as never,
                              ),
                            "Listing status updated.",
                          )
                        }
                      >
                        <option value="" disabled>
                          Change status…
                        </option>
                        {jobTransitions(listing.status).map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </Select>
                    )}
                  </div>
                </ListingCard>
              ))}
            </Cards>
          ) : (
            <State>
              <BriefcaseIcon />
              <h2>No listings yet.</h2>
              <p>
                Create the first role when you are ready to start recruiting.
              </p>
            </State>
          )}
        </section>
      )}
      {view === "applicants" && (
        <section>
          <SectionHead>
            <div>
              <h2>Applicant pipeline</h2>
              <p>
                Public applications enter directly. Employer interest creates no
                tenant candidate until the person accepts.
              </p>
            </div>
          </SectionHead>
          <PipelineControls $accent="plasma" aria-label="Applicant filters">
            <label>
              <MagnifyingGlassIcon />
              <input
                type="search"
                value={applicantQuery}
                onChange={(event) => setApplicantQuery(event.target.value)}
                placeholder="Search candidate, email, or role"
                aria-label="Search applicants"
              />
            </label>
            <label>
              <BriefcaseIcon />
              <select value={applicantListing} onChange={(event) => setApplicantListing(event.target.value)} aria-label="Filter applicants by listing">
                <option value="all">All listings</option>
                {workspace.listings.map((listing) => <option key={listing.id} value={listing.id}>{listing.title}</option>)}
              </select>
            </label>
            {(applicantQuery || applicantListing !== "all") && <ActionButton type="button" onClick={() => { setApplicantQuery(""); setApplicantListing("all"); }}>Clear filters</ActionButton>}
          </PipelineControls>
          <Board>
            {stages.map((stage) => {
              const candidates = visibleCandidates.filter(
                (item) => item.stage === stage,
              );
              return (
                <Column
                  key={stage}
                  $accent={
                    stage === "offer"
                      ? "amber"
                      : stage === "hired"
                        ? "cyan"
                        : "plasma"
                  }
                >
                  <ColumnHead>
                    <strong>{stage}</strong>
                    <span>{candidates.length}</span>
                  </ColumnHead>
                  {candidates.map((candidate) => {
                    const proposal = candidateProposal(candidate.id);
                    const latestOffer = offers.get(candidate.id)?.[0];
                    const latestInterview = workspace.interviews.filter((item) => item.application_id === candidate.id).sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
                    return (
                      <CandidateCard
                        key={candidate.id}
                        data-application-id={candidate.id}
                        $focused={focusedApplicationId === candidate.id}
                        tabIndex={focusedApplicationId === candidate.id ? -1 : undefined}
                      >
                        <div>
                          <strong>
                            {candidate.first_name} {candidate.last_name}
                          </strong>
                          <small>{candidate.email}</small>
                        </div>
                        <small>
                          {
                            workspace.listings.find(
                              (item) => item.id === candidate.listing_id,
                            )?.title
                          }
                        </small>
                        <ActionButton
                          type="button"
                          onClick={() => setReviewCandidate(candidate)}
                        >
                          <DocumentCheckIcon /> Review profile
                        </ActionButton>
                        {canManage &&
                          candidate.candidate_consent_status === "accepted" &&
                          ["applied", "screening"].includes(candidate.stage) &&
                          !hasOpenInterview(candidate.id) && (
                            <ActionButton
                              type="button"
                              onClick={() => setInterviewCandidate(candidate)}
                            >
                              <EnvelopeIcon /> Request interview
                            </ActionButton>
                          )}
                        {canManage &&
                          candidate.candidate_consent_status === "accepted" &&
                          candidate.stage === "interview" &&
                          !latestOffer && (
                            <ActionButton
                              $variant="primary"
                              type="button"
                              onClick={() =>
                                setModal({ kind: "offer", candidate })
                              }
                            >
                              <EnvelopeIcon /> Create offer
                            </ActionButton>
                          )}
                        {latestOffer && (
                          <ActionButton
                            type="button"
                            onClick={() => setView("offers")}
                          >
                            <CheckCircleIcon />{" "}
                            {latestOffer.status === "draft"
                              ? "Review & send offer"
                              : `Offer ${offerDisplayStatus(latestOffer)}`}
                          </ActionButton>
                        )}
                        {canHire &&
                          candidate.stage === "accepted" &&
                          latestOffer?.status === "accepted" && (
                            <ProvisioningAction
                              pathway={candidate.pathway}
                              certificationVerificationStatus={candidate.certification_verification_status}
                              screeningSchemaVersion={workspace.screening_schema_version}
                              busy={busy === candidate.id}
                              defaultLabel="Hire & provision"
                              onStart={() =>
                                setHandoffCandidate({
                                  candidate,
                                  operationId: crypto.randomUUID(),
                                })
                              }
                            />
                          )}
                        {proposal ? (
                          <>
                            <StatusChip $tone="warning">
                              new time proposed
                            </StatusChip>
                            <small>
                              {proposal.candidate_proposed_at
                                ? new Date(
                                    proposal.candidate_proposed_at,
                                  ).toLocaleString()
                                : "Candidate proposed another time"}
                            </small>
                            <ActionButton
                              $variant="primary"
                              type="button"
                              onClick={() =>
                                setProposalReview({
                                  candidate,
                                  interview: proposal,
                                })
                              }
                            >
                              Review proposed time
                            </ActionButton>
                          </>
                        ) : ["applied", "screening", "interview"].includes(
                            candidate.stage,
                          ) && hasOpenInterview(candidate.id) ? (
                          <>
                            <StatusChip $tone="warning">
                              interview {latestInterview?.status || 'pending'}
                            </StatusChip>
                            {latestInterview && <small>{new Date(latestInterview.scheduled_at).toLocaleString([], { timeZone: latestInterview.timezone })} · {latestInterview.timezone} · {latestInterview.location_or_link}</small>}
                          </>
                        ) : null}
                        <div className="actions">
                          <StatusChip
                            $tone={
                              candidate.source === "marketplace_application"
                                ? "success"
                                : candidate.source === "employer_interest"
                                  ? "warning"
                                  : "info"
                            }
                          >
                            {candidate.source === "marketplace_application"
                              ? "public applicant"
                              : candidate.source === "employer_interest"
                                ? "interest accepted"
                                : "private invite"}
                          </StatusChip>
                          <StatusChip
                            $tone={
                              candidate.candidate_consent_status === "accepted"
                                ? "success"
                                : "warning"
                            }
                          >
                            consent {candidate.candidate_consent_status}
                          </StatusChip>
                          {canManage &&
                            candidate.candidate_consent_status === "accepted" &&
                            employerTransitions(candidate).length > 0 && (
                              <Select
                                aria-label={`Move ${candidate.first_name}`}
                                defaultValue=""
                                disabled={busy === candidate.id}
                                onChange={(event) =>
                                  void mutate(
                                    candidate.id,
                                    () =>
                                      hiringApi.moveCandidate(
                                        candidate,
                                        event.target.value as CandidateStage,
                                      ),
                                    `${candidate.first_name} moved to ${event.target.value}.`,
                                  )
                                }
                              >
                                <option value="" disabled>
                                  Move to…
                                </option>
                                {employerTransitions(candidate).map(
                                  (option) => (
                                    <option key={option}>{option}</option>
                                  ),
                                )}
                              </Select>
                            )}
                        </div>
                      </CandidateCard>
                    );
                  })}
                </Column>
              );
            })}
          </Board>
          {!visibleCandidates.length && (
            <State>
              <UsersIcon />
              <h2>{activeCandidates.length ? "No applicants match these filters." : "No applicants yet."}</h2>
              <p>
                {activeCandidates.length
                  ? "Clear the search or listing filter to return to the full pipeline."
                  : "Public applicants and accepted employer interests will appear here automatically."}
              </p>
              {activeCandidates.length > 0 && <ActionButton type="button" onClick={() => { setApplicantQuery(""); setApplicantListing("all"); }}>Clear filters</ActionButton>}
            </State>
          )}
        </section>
      )}
      {view === "discover" && (
        <section>
          <SectionHead>
            <div>
              <h2>Discover opt-in talent</h2>
              <p>
                Search shows only profiles that candidates made discoverable.
                Interest reveals no private contact details and creates no
                tenant application until accepted.
              </p>
            </div>
          </SectionHead>
          <DiscoverControls
            as="form"
            onSubmit={(event) => {
              event.preventDefault();
              setCityQuery(city.trim());
            }}
          >
            <label>
              <MagnifyingGlassIcon />
              <input
                value={city}
                onChange={(event) => setCity(event.target.value)}
                placeholder="Filter by city"
                aria-label="Candidate city"
              />
            </label>
            <ActionButton type="submit">Search</ActionButton>
          </DiscoverControls>
          {discoverPhase === "loading" && (
            <State $accent="cyan" aria-busy="true">
              <ArrowPathIcon />
              <h2>Searching discoverable profiles.</h2>
              <p>Only current opt-in marketplace summaries are requested.</p>
            </State>
          )}
          {discoverPhase === "error" && (
            <State $accent="amber">
              <ExclamationTriangleIcon />
              <h2>Talent search could not be loaded.</h2>
              <p>{discoverError}</p>
              <ActionButton onClick={() => setCityQuery(`${city.trim()} `)}>
                <ArrowPathIcon /> Try again
              </ActionButton>
            </State>
          )}
          {discoverPhase === "ready" &&
            (discoverable.length ? (
              <Cards>
                {discoverable.map((profile) => (
                  <ListingCard
                    key={profile.user_id}
                    $accent={
                      profile.candidate_type === "student" ? "cyan" : "plasma"
                    }
                  >
                    <div className="top">
                      <div>
                        <h3>{profile.headline}</h3>
                        <p>
                          {profile.city} · {profile.experience_count} work
                          histor
                          {profile.experience_count === 1
                            ? "y entry"
                            : "y entries"}
                        </p>
                      </div>
                      <StatusChip
                        $tone={
                          profile.candidate_type === "student"
                            ? "info"
                            : "success"
                        }
                      >
                        {profile.candidate_type === "student"
                          ? "student"
                          : "certified educator"}
                      </StatusChip>
                    </div>
                    <DiscoverProfileEvidence profile={profile} />
                    <p>
                      Private contact and detailed history remain hidden until
                      candidate consent creates an application.
                    </p>
                    <ActionButton
                      $variant="primary"
                      onClick={() => setInterestProfile(profile)}
                      disabled={
                        !openListings.length ||
                        requestedProfiles.has(profile.user_id)
                      }
                    >
                      <EnvelopeIcon />{" "}
                      {requestedProfiles.has(profile.user_id)
                        ? "Interest requested"
                        : "Express interest"}
                    </ActionButton>
                  </ListingCard>
                ))}
              </Cards>
            ) : (
              <State>
                <MagnifyingGlassIcon />
                <h2>No discoverable candidates found.</h2>
                <p>
                  Try another city or return later. Non-discoverable profiles
                  are never included.
                </p>
              </State>
            ))}
        </section>
      )}
      {view === "offers" && (
        <section>
          <SectionHead>
            <div>
              <h2>Versioned offer review</h2>
              <p>
                Offers unlock only after candidate consent and a confirmed
                interview stage. Every revision is retained.
              </p>
            </div>
          </SectionHead>
          {offerCandidates.length ? <OfferTable $accent="amber">
            <table>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Latest version</th>
                  <th>Terms</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {offerCandidates.map((candidate) => {
                    const latest = offers.get(candidate.id)?.[0];
                    const displayedStatus = latest ? offerDisplayStatus(latest) : 'none';
                    return (
                      <tr key={candidate.id}>
                        <td className="person">
                          <strong>
                            {candidate.first_name} {candidate.last_name}
                          </strong>
                          <small>
                            {
                              workspace.listings.find(
                                (item) => item.id === candidate.listing_id,
                              )?.title
                            }
                          </small>
                        </td>
                        <td>{latest ? `v${latest.version}` : "Not drafted"}</td>
                        <td>
                          {latest
                            ? `${latest.compensation || "Compensation not specified"} · ${latest.start_date || "Start date flexible"}${latest.expires_at ? ` · expires ${new Date(latest.expires_at).toLocaleString()}` : ""}`
                            : "—"}
                        </td>
                        <td>
                          <StatusChip
                            $tone={statusTone(displayedStatus)}
                          >
                            {displayedStatus}
                          </StatusChip>
                        </td>
                        <td>
                          {canManage &&
                            candidate.candidate_consent_status === "accepted" &&
                            ["interview", "offer"].includes(
                              candidate.stage,
                            ) && (
                              <HeaderActions>
                                <ActionButton
                                  onClick={() =>
                                    setModal({ kind: "offer", candidate })
                                  }
                                >
                                  <EnvelopeIcon />
                                  {latest?.status === "draft"
                                    ? "Replace & send"
                                    : latest
                                      ? "Revise & send"
                                      : "Create & send"}
                                </ActionButton>
                                {latest?.status === "sent" && (
                                  <ActionButton
                                    $variant="danger"
                                    disabled={busy === latest.id}
                                    onClick={() => {
                                      if (!window.confirm(`Withdraw offer v${latest.version}? The candidate will no longer be able to accept it.`)) return;
                                      const reason = window.prompt("Reason for withdrawal (required)", "Offer withdrawn by employer");
                                      if (!reason?.trim() || reason.trim().length < 3) { setError("Withdrawal requires a reason of at least 3 characters."); return; }
                                      void mutate(latest.id, () => hiringApi.withdrawOffer(latest.id, reason.trim()), `Offer v${latest.version} withdrawn.`);
                                    }}
                                  >
                                    <XMarkIcon /> Withdraw
                                  </ActionButton>
                                )}
                              </HeaderActions>
                            )}
                          {canHire && candidate.stage === "accepted" && latest?.status === "accepted" && (
                            <ProvisioningAction
                              pathway={candidate.pathway}
                              certificationVerificationStatus={candidate.certification_verification_status}
                              screeningSchemaVersion={workspace.screening_schema_version}
                              busy={busy === candidate.id}
                              defaultLabel="Hire & provision"
                              onStart={() => setHandoffCandidate({ candidate, operationId: crypto.randomUUID() })}
                            />
                          )}
                          {candidate.stage === "hired" && <StatusChip $tone="success">Provisioned</StatusChip>}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </OfferTable> : <State>
            <CheckCircleIcon />
            <h2>No candidates are ready for an offer.</h2>
            <p>Complete candidate consent and the interview workflow first. Eligible candidates will appear here without a manual refresh when realtime updates are connected.</p>
            <ActionButton type="button" onClick={() => setView("applicants")}><UsersIcon /> Return to applicants</ActionButton>
          </State>}
        </section>
      )}
      {view === "handoff" && (
        <section>
          <SectionHead>
            <div>
              <h2>Safe staff provisioning</h2>
              <p>
                {screeningEnabled
                  ? 'Eligible educator pathways require an employer-accepted, current ECE certification review. Provisioning creates only an Educator membership, adds no rooms, and grants no transport authority.'
                  : 'An accepted offer can provision only an Educator membership and provisioning adds no rooms. The server response is validated before success is shown.'}
              </p>
            </div>
          </SectionHead>
          <Cards>
            {latestOffers
              .filter(({ offer }) => offer?.status === "accepted")
              .map(({ candidate, offer }) => (
                <ListingCard key={candidate.id} $accent="cyan">
                  <div className="top">
                    <div>
                      <h3>
                        {candidate.first_name} {candidate.last_name}
                      </h3>
                      <p>
                        {offer?.position_title} · starts{" "}
                        {offer?.start_date || "as agreed"}
                      </p>
                    </div>
                    <StatusChip $tone="success">accepted</StatusChip>
                  </div>
                  <p>
                    {workspace.screening_schema_version === '0030' && candidate.pathway === 'driver'
                      ? 'Driver-only access requires a future least-privilege role. No Educator or transport access can be provisioned here.'
                      : workspace.screening_schema_version === '0030' && candidate.pathway === 'student_educator'
                        ? 'A dedicated supervised trainee/student role is not available yet. No generic Educator membership can be provisioned here.'
                      : workspace.screening_schema_version === '0030' && candidate.pathway === 'educator_driver'
                        ? 'Provisioning baseline: employer-accepted current ECE certification review, Educator role only, and no new room assignments. Transport authority is not granted.'
                        : workspace.screening_schema_version === '0030' && candidate.pathway === 'educator'
                          ? 'Provisioning baseline: employer-accepted current ECE certification review, Educator role, and no new room assignments.'
                        : 'Provisioning baseline: Educator role and no new room assignments. Review certification and work history before confirming.'}
                  </p>
                  <HeaderActions>
                    <ActionButton onClick={() => setReviewCandidate(candidate)}>
                      <DocumentCheckIcon /> Review evidence
                    </ActionButton>
                    {canHire && (
                      <ProvisioningAction
                        pathway={candidate.pathway}
                        certificationVerificationStatus={candidate.certification_verification_status}
                        screeningSchemaVersion={workspace.screening_schema_version}
                        busy={busy === candidate.id}
                        defaultLabel="Confirm provisioning"
                        onStart={() =>
                          setHandoffCandidate({
                            candidate,
                            operationId: crypto.randomUUID(),
                          })
                        }
                      />
                    )}
                  </HeaderActions>
                </ListingCard>
              ))}
          </Cards>
          {!latestOffers.some(({ offer }) => offer?.status === "accepted") && (
            <State>
              <CheckCircleIcon />
              <h2>No accepted offers awaiting provisioning.</h2>
              <p>
                Accepted candidates will appear here with their reviewed offer
                version.
              </p>
            </State>
          )}
        </section>
      )}
      {modal && (
        <HiringDialog
          modal={modal}
          listings={workspace.listings}
          timezone={session.organization?.timezone || 'America/Edmonton'}
          screeningEnabled={screeningEnabled}
          busy={Boolean(busy)}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            setBusy("dialog");
            setError("");
            try {
              if (modal.kind === "listing")
                await hiringApi.createListing(
                  payload as unknown as ListingInput,
                  workspace.screening_schema_version,
                );
              else {
                const operationId = offerOperationIds.current.get(modal.candidate.id) || crypto.randomUUID();
                offerOperationIds.current.set(modal.candidate.id, operationId);
                await hiringApi.createAndSendOffer(
                  modal.candidate.id,
                  {
                    ...(payload as unknown as Omit<
                      OfferInput,
                      "expected_application_version"
                    >),
                    expected_application_version: modal.candidate.version,
                    client_operation_id: operationId,
                  },
                  workspace.screening_schema_version,
                );
                offerOperationIds.current.delete(modal.candidate.id);
                setView("offers");
              }
              setModal(null);
              refresh(
                modal.kind === "listing"
                  ? "Draft listing created."
                  : "Offer created and sent to the candidate.",
              );
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "The record could not be saved.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
      {reviewCandidate && (
        <CandidateReviewDialog
          candidate={reviewCandidate}
          canReview={canManage}
          screeningEnabled={screeningEnabled}
          busy={busy === reviewCandidate.candidate_id}
          onClose={() => setReviewCandidate(null)}
          onReview={async (status, reason) => {
            setBusy(reviewCandidate.candidate_id);
            setError("");
            try {
              await hiringApi.reviewCertification(
                reviewCandidate.candidate_id,
                status,
                reason,
              );
              setReviewCandidate(null);
              refresh(`Certification review marked ${status}.`);
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "The certification review could not be saved.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
      {handoffCandidate && (
        <HandoffDialog
          candidate={handoffCandidate.candidate}
          screeningSchemaVersion={workspace.screening_schema_version}
          busy={busy === handoffCandidate.candidate.id}
          onClose={() => setHandoffCandidate(null)}
          onConfirm={async () => {
            const { candidate, operationId } = handoffCandidate;
            const policy = adminProvisioningPolicy(
              workspace.screening_schema_version,
              candidate.pathway,
              candidate.certification_verification_status,
            );
            if (!policy.canProvisionEducator) {
              setHandoffCandidate(null);
              setError(policy.guidance || 'This pathway cannot use educator provisioning.');
              return;
            }
            setBusy(candidate.id);
            setError("");
            try {
              const result = await hiringApi.provisionCandidate(
                candidate,
                operationId,
                organizationId,
              );
              setHandoffResult({
                name: `${candidate.first_name} ${candidate.last_name}`,
                membershipCreated: result.membership_created,
                membershipId: result.membership_id,
                transportAuthorityWithheld:
                  workspace.screening_schema_version === '0030' &&
                  candidate.pathway === 'educator_driver',
              });
              setHandoffCandidate(null);
              refresh(
                result.membership_created
                  ? `Educator membership provisioned with no room access.${candidate.pathway === 'educator_driver' && workspace.screening_schema_version === '0030' ? ' Transport authority was not granted.' : ''}`
                  : `Existing educator membership linked; no new membership was created.${candidate.pathway === 'educator_driver' && workspace.screening_schema_version === '0030' ? ' Transport authority was not granted.' : ''}`,
              );
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "Safe staff provisioning could not be completed.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
      {interestProfile && (
        <InterestDialog
          profile={interestProfile}
          listings={openListings}
          busy={busy === interestProfile.user_id}
          onClose={() => setInterestProfile(null)}
          onSubmit={async (jobId, message) => {
            setBusy(interestProfile.user_id);
            setError("");
            try {
              await marketplaceApi.expressInterest(
                interestProfile.user_id,
                jobId,
                message,
              );
              setRequestedProfiles((current) =>
                new Set(current).add(interestProfile.user_id),
              );
              setInterestProfile(null);
              setNotice(
                "Interest request sent. No candidate or application exists until the person accepts.",
              );
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "Interest could not be requested.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
      {interviewCandidate && (
        <InterviewDialog
          candidate={interviewCandidate}
          timezone={session.organization?.timezone || 'America/Edmonton'}
          busy={busy === interviewCandidate.id}
          onClose={() => setInterviewCandidate(null)}
          onSubmit={async (scheduledAt, location) => {
            setBusy(interviewCandidate.id);
            setError("");
            try {
              await marketplaceApi.requestInterview(
                interviewCandidate.id,
                scheduledAt,
                location,
                session.organization?.timezone || 'America/Edmonton',
              );
              const name = interviewCandidate.first_name;
              setInterviewCandidate(null);
              refresh(
                `Interview requested from ${name}. The pipeline advances only if the candidate confirms.`,
              );
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "The interview could not be requested.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
      {proposalReview && (
        <ProposalReviewDialog
          candidate={proposalReview.candidate}
          interview={proposalReview.interview}
          timezone={session.organization?.timezone || proposalReview.interview.timezone}
          busy={busy === proposalReview.interview.id}
          onClose={() => setProposalReview(null)}
          onSubmit={async (decision, scheduledAt, location) => {
            const current = proposalReview;
            setBusy(current.interview.id);
            setError("");
            try {
              await marketplaceApi.decideInterviewProposal(
                current.interview.id,
                decision,
                scheduledAt,
                location,
                session.organization?.timezone || current.interview.timezone,
              );
              setProposalReview(null);
              refresh(
                decision === "accepted"
                  ? `Interview time accepted for ${current.candidate.first_name}.`
                  : decision === "countered"
                    ? `A new interview time was sent to ${current.candidate.first_name}.`
                    : `The proposed time was declined.`,
              );
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "The interview proposal could not be updated.",
              );
            } finally {
              setBusy("");
            }
          }}
        />
      )}
    </Page>
  );
}

function CandidateReviewDialog({
  candidate,
  canReview,
  screeningEnabled,
  busy,
  onClose,
  onReview,
}: {
  candidate: Candidate;
  canReview: boolean;
  screeningEnabled: boolean;
  busy: boolean;
  onClose: () => void;
  onReview: (
    status: "pending" | "verified" | "rejected",
    reason: string,
  ) => Promise<void>;
}) {
  const [reviewStatus, setReviewStatus] = useState<
    "pending" | "verified" | "rejected"
  >(
    candidate.certification_verification_status === "unverified"
      ? "pending"
      : candidate.certification_verification_status,
  );
  const [reviewReason, setReviewReason] = useState(
    candidate.certification_review_note ||
      "Certification evidence reviewed in the employer workspace.",
  );
  return (
    <Overlay
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <Dialog
        role="dialog"
        aria-modal="true"
        aria-labelledby="candidate-review-title"
      >
        <DialogHead>
          <div>
            <Eyebrow>
              <DocumentCheckIcon width={14} /> Evidence review
            </Eyebrow>
            <h2 id="candidate-review-title">
              {candidate.first_name} {candidate.last_name}
            </h2>
            <p>
              {candidate.candidate_type === "student"
                ? "Student education is distinct from certification evidence and verification."
                : "Extraction, candidate confirmation, and employer verification are separate evidence states. OCR is never verification."}
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close candidate review"
            onClick={onClose}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <ReviewGrid>
          <ReviewCard>
            <h3>Candidate profile</h3>
            {candidate.candidate_type && (
              <EvidenceTrail>
                <StatusChip
                  $tone={
                    candidate.candidate_type === "student" ? "info" : "success"
                  }
                >
                  {candidate.candidate_type === "student"
                    ? "student"
                    : "certified educator"}
                </StatusChip>
              </EvidenceTrail>
            )}
            <p>
              <strong>Email</strong>
              <br />
              {candidate.email}
            </p>
            <p>
              <strong>Phone</strong>
              <br />
              {candidate.candidate_consent_status === "accepted"
                ? candidate.phone || "Not provided"
                : "Available after candidate contact consent"}
            </p>
            <p>
              <strong>Onboarding</strong>
              <br />
              <StatusChip
                $tone={
                  candidate.onboarding_status === "complete"
                    ? "success"
                    : candidate.onboarding_status === "submitted"
                      ? "info"
                      : "warning"
                }
              >
                {candidate.onboarding_status.replaceAll("_", " ")}
              </StatusChip>
            </p>
            <p>
              Onboarding progress is informational here and does not block this
              application or employer pipeline actions.
            </p>
          </ReviewCard>
          <ReviewCard>
            <h3>Identity & references</h3>
            <StatusChip $tone="warning">unverified</StatusChip>
            <p>
              {screeningEnabled
                ? "Identity and reference checks remain separate. Application-scoped police and vulnerable-sector evidence is reviewed below."
                : "No identity, reference, or background-check verification is represented by the ATS profile. Complete required checks before room assignment."}
            </p>
          </ReviewCard>
          {candidate.pathway === "driver" ? (
            <ReviewCard>
              <h3>Driver pathway</h3>
              <StatusChip $tone="info">candidate declared</StatusChip>
              <p>
                A driver-only candidate is not required to supply ECE certification.
                Their declaration is not operational driver approval.
              </p>
              <p>
                <strong>Licence</strong><br />
                {candidate.driver_declaration?.licence_jurisdiction || 'Not provided'} · class{' '}
                {candidate.driver_declaration?.licence_class || 'not provided'}
              </p>
              <p>
                <strong>Vehicle access</strong><br />
                {candidate.driver_declaration?.vehicle_access.replaceAll('_', ' ') || 'Not provided'}
              </p>
            </ReviewCard>
          ) : candidate.candidate_type === "student" ? (
            <ReviewCard>
              <h3>Education & training</h3>
              <StatusChip $tone="info">student</StatusChip>
              <p>
                <strong>Institution</strong>
                <br />
                {candidate.institution || "Not provided"}
              </p>
              <p>
                <strong>Program</strong>
                <br />
                {candidate.program || "Not provided"}
              </p>
              <p>
                <strong>Expected graduation</strong>
                <br />
                {candidate.expected_graduation_date || "Not provided"}
              </p>
              <p>
                This student record does not represent certification evidence or
                an unverified certified educator.
              </p>
            </ReviewCard>
          ) : (
            <ReviewCard>
              <h3>Certification</h3>
              <EvidenceState
                provenance={candidate.certification_provenance}
                candidateConfirmedAt={
                  candidate.certification_candidate_confirmed_at
                }
                employerStatus={candidate.certification_verification_status}
              />
              <p>
                <strong>Type</strong>
                <br />
                {candidate.certification_type || "Not provided"}
              </p>
              <p>
                <strong>Number</strong>
                <br />
                {candidate.certification_number || "Not provided"}
              </p>
              <p>
                <strong>Expiry</strong>
                <br />
                {candidate.certification_expiry_date || "Not provided"}
              </p>
              {candidate.certification_candidate_confirmed_at && (
                <p>
                  Candidate confirmed{" "}
                  {new Date(
                    candidate.certification_candidate_confirmed_at,
                  ).toLocaleString()}
                </p>
              )}
              {candidate.certification_verified_at && (
                <p>
                  Employer verified{" "}
                  {new Date(
                    candidate.certification_verified_at,
                  ).toLocaleString()}
                </p>
              )}
              {candidate.certification_review_note && (
                <p>
                  <strong>Employer review note</strong>
                  <br />
                  {candidate.certification_review_note}
                </p>
              )}
            </ReviewCard>
          )}
          <ReviewCard>
            <h3>Work history</h3>
            <EvidenceState
              provenance={candidate.work_history_provenance}
              candidateConfirmedAt={
                candidate.work_history_candidate_confirmed_at
              }
            />
            <p>
              Work history has no employer-verification status in this record.
            </p>
            {candidate.work_history_candidate_confirmed_at && (
              <p>
                Candidate confirmed{" "}
                {new Date(
                  candidate.work_history_candidate_confirmed_at,
                ).toLocaleString()}
              </p>
            )}
            {candidate.work_history.length ? (
              candidate.work_history.map((item, index) => (
                <p key={`${item.employer}-${index}`}>
                  <strong>{item.employer}</strong>
                  {typeof item.position === "string" && (
                    <>
                      <br />
                      {item.position}
                    </>
                  )}
                  {typeof item.start_date === "string" && (
                    <>
                      {" "}
                      · {item.start_date}
                      {typeof item.end_date === "string"
                        ? `–${item.end_date}`
                        : "–present"}
                    </>
                  )}
                </p>
              ))
            ) : (
              <p>No work history provided.</p>
            )}
            {candidate.notes && (
              <p>
                <strong>Recruiting notes</strong>
                <br />
                {candidate.notes}
              </p>
            )}
          </ReviewCard>
        </ReviewGrid>
        {screeningEnabled ? (
          <ScreeningReviewPanel
            applicationId={candidate.id}
            canReview={canReview}
          />
        ) : null}
        {canReview && candidate.candidate_type !== "student" && candidate.pathway !== "driver" && (
          <Form
            onSubmit={(event) => {
              event.preventDefault();
              if (reviewReason.trim())
                void onReview(reviewStatus, reviewReason.trim());
            }}
          >
            <Field>
              <span>Certification decision</span>
              <select
                value={reviewStatus}
                onChange={(event) =>
                  setReviewStatus(event.target.value as typeof reviewStatus)
                }
              >
                <option value="pending">Pending</option>
                <option
                  value="verified"
                  disabled={!candidate.certification_number}
                >
                  Verified
                </option>
                <option value="rejected">Rejected</option>
              </select>
            </Field>
            <Field>
              <span>Review reason</span>
              <input
                value={reviewReason}
                onChange={(event) => setReviewReason(event.target.value)}
                minLength={3}
                required
              />
            </Field>
            <FormActions>
              <ActionButton type="button" onClick={onClose} disabled={busy}>
                Close
              </ActionButton>
              <ActionButton
                type="submit"
                $variant="primary"
                disabled={busy || reviewReason.trim().length < 3}
              >
                {busy ? "Saving…" : "Save certification review"}
              </ActionButton>
            </FormActions>
          </Form>
        )}
        {(!canReview || candidate.candidate_type === "student" || candidate.pathway === "driver") && (
          <FormActions>
            <ActionButton type="button" onClick={onClose}>
              Close review
            </ActionButton>
          </FormActions>
        )}
      </Dialog>
    </Overlay>
  );
}

function ScreeningReviewPanel({
  applicationId,
  canReview,
}: {
  applicationId: string;
  canReview: boolean;
}) {
  const [projection, setProjection] = useState<EmployerScreeningProjection | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [viewedShares, setViewedShares] = useState<Set<string>>(() => new Set());
  const [viewer, setViewer] = useState<
    (ViewedScreeningSource & { objectUrl: string }) | null
  >(null);
  const viewController = useRef<AbortController | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    const next = await screeningApi.application(applicationId, signal);
    setProjection(next);
    setPhase('ready');
    setError('');
  }, [applicationId]);

  useEffect(() => {
    const controller = new AbortController();
    setPhase('loading');
    void load(controller.signal).catch((caught) => {
      if (controller.signal.aborted) return;
      setPhase('error');
      setError(
        caught instanceof Error
          ? caught.message
          : 'Application screening could not be loaded.',
      );
    });
    return () => controller.abort();
  }, [load]);

  useEffect(
    () => () => {
      viewController.current?.abort();
    },
    [],
  );
  useEffect(
    () => () => {
      if (viewer) URL.revokeObjectURL(viewer.objectUrl);
    },
    [viewer],
  );
  useEffect(() => {
    const clearWhenHidden = () => {
      if (document.visibilityState !== 'hidden') return;
      viewController.current?.abort();
      setViewer(null);
      setViewedShares(new Set());
    };
    document.addEventListener('visibilitychange', clearWhenHidden);
    return () => document.removeEventListener('visibilitychange', clearWhenHidden);
  }, []);

  const viewSource = async (share: SharedScreeningDocument) => {
    viewController.current?.abort();
    const controller = new AbortController();
    viewController.current = controller;
    setBusy(`view:${share.id}`);
    setError('');
    try {
      const source = await screeningApi.viewExactSource(
        applicationId,
        share,
        controller.signal,
      );
      if (
        source.share_id !== share.id ||
        source.document_version_id !== share.shared_version.id
      )
        throw new Error('The viewed source did not match the exact shared version.');
      setViewer({ ...source, objectUrl: URL.createObjectURL(source.blob) });
      setViewedShares((current) => new Set(current).add(share.id));
    } catch (caught) {
      if (!controller.signal.aborted)
        setError(
          caught instanceof Error
            ? caught.message
            : 'The exact shared source could not be viewed.',
        );
    } finally {
      if (viewController.current === controller) viewController.current = null;
      setBusy('');
    }
  };

  const recordReview = async (
    share: SharedScreeningDocument,
    requirement: ScreeningRequirement,
    decision: ScreeningDecision,
    reasonCode: string,
    note: string | null,
  ) => {
    if (!viewedShares.has(share.id)) return;
    const key = `review:${share.id}:${requirement}`;
    setBusy(key);
    setError('');
    try {
      await screeningApi.review(applicationId, share.id, {
        requirement_class: requirement,
        decision,
        reason_code: reasonCode,
        note,
      });
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The screening review could not be recorded.',
      );
    } finally {
      setBusy('');
    }
  };

  return (
    <ScreeningSection aria-label="Application screening">
      <h3>Application screening</h3>
      <p>
        This section is separate from ECE certification. Decisions apply only to this
        application, exact share, and requirement.
      </p>
      {phase === 'loading' ? <p>Loading confidential screening…</p> : null}
      {error ? <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice> : null}
      {projection?.snapshot ? (
        <ReviewCard>
          <h3>{projection.snapshot.pathway.replaceAll('_', ' ')}</h3>
          <p>
            Candidate-provided declaration · profile version{' '}
            {projection.snapshot.screening_profile_version} · role terms version{' '}
            {projection.snapshot.job_terms_version}. It does not establish
            operational driver approval.
          </p>
          {projection.snapshot.driver_declaration.willing_to_drive ? (
            <p>
              Licence {projection.snapshot.driver_declaration.licence_jurisdiction || 'not provided'} ·
              class {projection.snapshot.driver_declaration.licence_class || 'not provided'} ·{' '}
              {projection.snapshot.driver_declaration.vehicle_access.replaceAll('_', ' ')}
            </p>
          ) : null}
        </ReviewCard>
      ) : null}
      {projection?.shares.map((share) => (
        <ScreeningShareCard key={share.id}>
          <h4>
            Exact shared version {share.shared_version.version_number} ·{' '}
            {share.shared_version.declared_coverage
              .map((requirement) => requirement.replaceAll('_', ' '))
              .join(' + ')}
          </h4>
          <p>
            Candidate confirmed{' '}
            {new Date(share.shared_version.candidate_confirmed_at).toLocaleString()} ·
            shared {new Date(share.shared_at).toLocaleString()}
          </p>
          <p>
            Subject: {share.shared_version.subject_name || 'Not transcribed'} · issue{' '}
            {share.shared_version.issue_date || 'not provided'} · expiry{' '}
            {share.shared_version.expiry_date || 'not provided'}
          </p>
          <ScreeningIdentityWarning
            subjectName={share.shared_version.subject_name}
            accountNameSnapshot={share.shared_version.account_name_snapshot}
            subjectNameMatch={share.shared_version.subject_name_match}
            mismatchResolution={share.shared_version.mismatch_resolution}
          />
          <ActionButton
            type="button"
            disabled={Boolean(busy)}
            onClick={() => void viewSource(share)}
          >
            <DocumentCheckIcon />
            {busy === `view:${share.id}` ? 'Opening exact source…' : 'View exact shared source'}
          </ActionButton>
          {viewer?.share_id === share.id ? (
            <ProtectedViewer role="dialog" aria-label="Protected screening source viewer">
              <div className="viewer-head">
                <strong>Exact version {share.shared_version.version_number}</strong>
                <ActionButton type="button" onClick={() => setViewer(null)}>Close source</ActionButton>
              </div>
              {viewer.media_type === 'application/pdf' ? (
                <iframe title="Exact shared screening PDF" src={viewer.objectUrl} />
              ) : (
                <img alt="Exact shared screening source" src={viewer.objectUrl} />
              )}
            </ProtectedViewer>
          ) : null}
          {share.shared_version.declared_coverage.map((requirement) => (
            <ScreeningRequirementReview
              key={requirement}
              requirement={requirement}
              latest={latestScreeningDecision(share, requirement)}
              viewed={viewedShares.has(share.id)}
              canReview={canReview}
              busy={busy === `review:${share.id}:${requirement}`}
              onSubmit={(decision, reasonCode, note) =>
                recordReview(share, requirement, decision, reasonCode, note)
              }
            />
          ))}
        </ScreeningShareCard>
      ))}
      {phase === 'ready' && !projection?.shares.length ? (
        <ReviewCard>
          <h3>No screening evidence shared</h3>
          <p>The candidate controls application-specific disclosure and may share or revoke it.</p>
        </ReviewCard>
      ) : null}
    </ScreeningSection>
  );
}

export function ScreeningIdentityWarning({
  subjectName,
  accountNameSnapshot,
  subjectNameMatch,
  mismatchResolution,
}: {
  subjectName: string;
  accountNameSnapshot: string;
  subjectNameMatch: boolean;
  mismatchResolution: SharedScreeningDocument['shared_version']['mismatch_resolution'];
}) {
  if (subjectNameMatch || mismatchResolution !== 'candidate_attests_same_person')
    return null;
  return (
    <IdentityReconciliationAlert role="alert" aria-label="Screening identity reconciliation warning">
      <ExclamationTriangleIcon />
      <div>
        <strong>Name mismatch requires employer review</strong>
        <p>
          The exact shared source names {subjectName}, while the candidate account
          name captured at confirmation was {accountNameSnapshot}. The candidate
          attested that both names refer to the same person; this is not employer
          identity verification. Inspect the exact source before deciding.
        </p>
      </div>
    </IdentityReconciliationAlert>
  );
}

function ScreeningRequirementReview({
  requirement,
  latest,
  viewed,
  canReview,
  busy,
  onSubmit,
}: {
  requirement: ScreeningRequirement;
  latest: ReturnType<typeof latestScreeningDecision>;
  viewed: boolean;
  canReview: boolean;
  busy: boolean;
  onSubmit: (
    decision: ScreeningDecision,
    reasonCode: string,
    note: string | null,
  ) => Promise<void>;
}) {
  const [decision, setDecision] = useState<ScreeningDecision>('accepted');
  const [reasonCode, setReasonCode] = useState('current_and_applicable');
  const [note, setNote] = useState('');
  const reasons = decision === 'accepted'
    ? [{ value: 'current_and_applicable', label: 'Current and applicable' }]
    : [
        { value: 'expired', label: 'Expired / recheck required' },
        { value: 'identity_mismatch', label: 'Identity mismatch' },
        { value: 'insufficient_coverage', label: 'Requirement not covered' },
        { value: 'unreadable', label: 'Source unreadable' },
        { value: 'other', label: 'Other documented reason' },
      ];
  return (
    <ReviewCard>
      <h3>{requirement.replaceAll('_', ' ')}</h3>
      {latest ? (
        <EvidenceTrail>
          <StatusChip $tone={latest.decision === 'accepted' ? 'success' : 'warning'}>
            {latest.decision} · {latest.reason_code.replaceAll('_', ' ')} · sequence {latest.review_sequence}
          </StatusChip>
        </EvidenceTrail>
      ) : <p>No employer decision recorded.</p>}
      {!viewed ? <p>Open the exact shared source in this session before recording a decision.</p> : null}
      {canReview ? (
        <Form onSubmit={(event) => {
          event.preventDefault();
          if (viewed && (reasonCode !== 'other' || note.trim()))
            void onSubmit(decision, reasonCode, note.trim() || null);
        }}>
          <Field>
            <span>Decision</span>
            <select value={decision} onChange={(event) => {
              const next = event.target.value as ScreeningDecision;
              setDecision(next);
              setReasonCode(next === 'accepted' ? 'current_and_applicable' : 'expired');
            }}>
              <option value="accepted">Accept this requirement</option>
              <option value="rejected">Reject / request replacement</option>
            </select>
          </Field>
          <Field>
            <span>Reason</span>
            <select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
              {reasons.map((reason) => <option key={reason.value} value={reason.value}>{reason.label}</option>)}
            </select>
          </Field>
          <Field $wide>
            <span>Internal review note (optional; required for Other)</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} />
          </Field>
          <FormActions>
            <ActionButton
              type="submit"
              $variant="primary"
              disabled={!viewed || busy || (reasonCode === 'other' && !note.trim())}
            >
              {busy ? 'Saving…' : 'Record requirement decision'}
            </ActionButton>
          </FormActions>
        </Form>
      ) : null}
    </ReviewCard>
  );
}

function EvidenceState({
  provenance,
  candidateConfirmedAt,
  employerStatus,
}: {
  provenance: Candidate["certification_provenance"];
  candidateConfirmedAt: string | null;
  employerStatus?: Candidate["certification_verification_status"];
}) {
  return (
    <EvidenceTrail aria-label="Evidence status">
      <StatusChip
        $tone={
          provenance === "local_ocr"
            ? "warning"
            : provenance === "manual"
              ? "info"
              : "neutral"
        }
      >
        {provenance === "local_ocr"
          ? "OCR-extracted source"
          : provenance === "manual"
            ? "candidate-entered source"
            : "source not recorded"}
      </StatusChip>
      <StatusChip $tone={candidateConfirmedAt ? "info" : "warning"}>
        {candidateConfirmedAt
          ? "candidate-confirmed"
          : "not candidate-confirmed"}
      </StatusChip>
      <StatusChip $tone={employerStatus === "verified" ? "success" : "warning"}>
        {employerStatus ? `employer ${employerStatus}` : "employer unverified"}
      </StatusChip>
    </EvidenceTrail>
  );
}

function DiscoverProfileEvidence({
  profile,
}: {
  profile: DiscoverableCandidate;
}) {
  if (profile.candidate_type === "student")
    return (
      <div>
        <p>
          <strong>Institution</strong>
          <br />
          {profile.institution || "Not provided"}
        </p>
        <p>
          <strong>Program</strong>
          <br />
          {profile.program || "Not provided"}
        </p>
        <p>
          <strong>Expected graduation</strong>
          <br />
          {profile.expected_graduation_date || "Not provided"}
        </p>
        <p>
          This is a student profile, not a certified educator with an unverified
          certificate.
        </p>
      </div>
    );
  return (
    <div>
      <EvidenceState
        provenance={profile.certification_provenance}
        candidateConfirmedAt={profile.certification_candidate_confirmed_at}
        employerStatus={profile.certification_verification_status}
      />
      <p>
        <strong>Certification</strong>
        <br />
        {profile.certification_type || "Not provided"}
      </p>
      <p>
        OCR extraction identifies the source only; employer verification is
        shown separately.
      </p>
    </div>
  );
}

function HandoffDialog({
  candidate,
  screeningSchemaVersion,
  busy,
  onClose,
  onConfirm,
}: {
  candidate: Candidate;
  screeningSchemaVersion: ScreeningSchemaVersion;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const policy = adminProvisioningPolicy(
    screeningSchemaVersion,
    candidate.pathway,
    candidate.certification_verification_status,
  );
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (confirmed && policy.canProvisionEducator) void onConfirm();
  };
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog role="dialog" aria-modal="true" aria-labelledby="handoff-title">
        <DialogHead>
          <div>
            <Eyebrow>
              <ShieldCheckIcon width={14} /> Least-privilege handoff
            </Eyebrow>
            <h2 id="handoff-title">
              Confirm {candidate.first_name} for onboarding
            </h2>
            <p>
              This records readiness. Provisioning exists only if the server
              explicitly confirms it.
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close handoff confirmation"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <Form onSubmit={submit}>
          {policy.guidance ? (
            <ProvisioningDialogNotice role={policy.canProvisionEducator ? 'status' : 'alert'}>
              {policy.canProvisionEducator ? <ShieldCheckIcon /> : <LockClosedIcon />}
              <span>{policy.guidance}</span>
            </ProvisioningDialogNotice>
          ) : null}
          <Field $wide>
            <span>Access baseline</span>
            <Confirmation>
              <div className="row">
                <span>Requested role</span>
                <strong>{policy.canProvisionEducator ? 'Educator' : 'Not available'}</strong>
              </div>
              <div className="row">
                <span>Facility assignments added</span>
                <strong>None</strong>
              </div>
              <div className="row">
                <span>Room assignments added</span>
                <strong>None</strong>
              </div>
              {screeningSchemaVersion === '0030' &&
              (candidate.pathway === 'educator' || candidate.pathway === 'educator_driver') ? (
                <div className="row">
                  <span>ECE certification review</span>
                  <strong>
                    {candidate.certification_verification_status === 'verified'
                      ? 'Employer accepted'
                      : 'Required — not recorded'}
                  </strong>
                </div>
              ) : null}
              {screeningSchemaVersion === '0030' &&
              (candidate.pathway === 'driver' || candidate.pathway === 'educator_driver') ? (
                <div className="row">
                  <span>Transport authority granted</span>
                  <strong>None</strong>
                </div>
              ) : null}
              <div className="row">
                <span>Accepted offer</span>
                <strong>Required</strong>
              </div>
            </Confirmation>
          </Field>
          <ConfirmChoice>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              disabled={!policy.canProvisionEducator}
              required
            />
            <span>
              I reviewed the accepted offer and available candidate evidence. I
              understand this creates or reuses only an active Educator
              membership and adds no room assignments; any existing assignments
              still require Staff & access review.
              {screeningSchemaVersion === '0030' &&
              (candidate.pathway === 'educator' || candidate.pathway === 'educator_driver')
                ? ' The application must record an employer-accepted, current ECE certification review; candidate confirmation or OCR extraction alone is not sufficient.'
                : ''}
              {screeningSchemaVersion === '0030' && candidate.pathway === 'educator_driver'
                ? ' Transport authority is not granted by this action.'
                : ''}
            </span>
          </ConfirmChoice>
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            <ActionButton
              type="submit"
              $variant="primary"
              disabled={busy || !confirmed || !policy.canProvisionEducator}
            >
              {busy ? "Provisioning…" : policy.actionLabel || "Provision educator safely"}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

function InterestDialog({
  profile,
  listings,
  busy,
  onClose,
  onSubmit,
}: {
  profile: DiscoverableCandidate;
  listings: HiringWorkspace["listings"];
  busy: boolean;
  onClose: () => void;
  onSubmit: (jobId: string, message: string) => Promise<void>;
}) {
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog role="dialog" aria-modal="true" aria-labelledby="interest-title">
        <DialogHead>
          <div>
            <Eyebrow>
              <LockClosedIcon width={14} /> Consent boundary
            </Eyebrow>
            <h2 id="interest-title">Express interest</h2>
            <p>
              {profile.headline} · {profile.city}. This request does not create
              an applicant record or reveal contact details.
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close interest request"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <Form
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void onSubmit(
              String(data.get("job_id")),
              String(data.get("message") || ""),
            );
          }}
        >
          <Field $wide>
            <span>Open role</span>
            <select name="job_id" required autoFocus>
              {listings.map((listing) => (
                <option key={listing.id} value={listing.id}>
                  {listing.title} · {listing.location}
                </option>
              ))}
            </select>
          </Field>
          <Field $wide>
            <span>Interest message (optional)</span>
            <textarea
              name="message"
              maxLength={3000}
              placeholder="Introduce the role without requesting private information."
            />
          </Field>
          <ConfirmChoice>
            <input type="checkbox" required />
            <span>
              I understand the candidate must accept before CareSync creates a
              tenant application or reveals application profile details.
            </span>
          </ConfirmChoice>
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            <ActionButton type="submit" $variant="primary" disabled={busy}>
              {busy ? "Sending…" : "Send interest request"}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

function InterviewDialog({
  candidate,
  timezone,
  busy,
  onClose,
  onSubmit,
}: {
  candidate: Candidate;
  timezone: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (scheduledAt: string, location: string) => Promise<void>;
}) {
  const [localError, setLocalError] = useState('');
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog role="dialog" aria-modal="true" aria-labelledby="interview-title">
        <DialogHead>
          <div>
            <Eyebrow>
              <EnvelopeIcon width={14} /> Candidate confirmation required
            </Eyebrow>
            <h2 id="interview-title">
              Request an interview with {candidate.first_name}
            </h2>
            <p>
              The application remains in screening until the candidate confirms
              this request.
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close interview request"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <Form
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const local = String(data.get("scheduled_at"));
            try { setLocalError(''); void onSubmit(zonedDateTimeToIso(local, timezone), String(data.get("location_or_link"))); }
            catch (caught) { setLocalError(caught instanceof Error ? caught.message : 'The interview time is invalid.'); }
          }}
        >
          {localError && <Notice $error role="alert"><ExclamationTriangleIcon /> {localError}</Notice>}
          <Field>
            <span>Date and time · {timezone}</span>
            <input
              name="scheduled_at"
              type="datetime-local"
              required
              autoFocus
            />
          </Field>
          <Field>
            <span>Location or meeting link</span>
            <input name="location_or_link" required maxLength={500} />
          </Field>
          <ConfirmChoice>
            <input type="checkbox" required />
            <span>
              I understand this is a request, not a confirmed interview, and no
              offer is available until the application reaches the interview
              stage.
            </span>
          </ConfirmChoice>
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            <ActionButton type="submit" $variant="primary" disabled={busy}>
              {busy ? "Requesting…" : "Request interview"}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

function ProposalReviewDialog({
  candidate,
  interview,
  timezone,
  busy,
  onClose,
  onSubmit,
}: {
  candidate: Candidate;
  interview: InterviewRecord;
  timezone: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (
    decision: "accepted" | "declined" | "countered",
    scheduledAt?: string,
    location?: string,
  ) => Promise<void>;
}) {
  const [decision, setDecision] = useState<
    "accepted" | "declined" | "countered"
  >("accepted");
  const [localError, setLocalError] = useState('');
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog role="dialog" aria-modal="true" aria-labelledby="proposal-title">
        <DialogHead>
          <div>
            <Eyebrow>
              <ArrowPathIcon width={14} /> Interview negotiation
            </Eyebrow>
            <h2 id="proposal-title">
              Review {candidate.first_name}’s proposed time
            </h2>
            <p>
              {interview.candidate_proposed_at
                ? new Date(interview.candidate_proposed_at).toLocaleString()
                : "No proposed time returned"}
              {interview.candidate_proposal_note
                ? ` · ${interview.candidate_proposal_note}`
                : ""}
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close proposal review"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <Form
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const local = String(data.get("scheduled_at") || "");
            try { setLocalError(''); void onSubmit(
              decision,
              decision === "countered"
                ? zonedDateTimeToIso(local, timezone)
                : undefined,
              decision === "countered"
                ? String(data.get("location_or_link") || "")
                : undefined,
            ); } catch (caught) { setLocalError(caught instanceof Error ? caught.message : 'The proposed interview time is invalid.'); }
          }}
        >
          {localError && <Notice $error role="alert"><ExclamationTriangleIcon /> {localError}</Notice>}
          <Field $wide>
            <span>Response</span>
            <select
              value={decision}
              onChange={(event) =>
                setDecision(event.target.value as typeof decision)
              }
            >
              <option value="accepted">Accept candidate’s time</option>
              <option value="countered">Suggest another time</option>
              <option value="declined">Decline without another time</option>
            </select>
          </Field>
          {decision === "countered" && (
            <>
              <Field>
                <span>New date and time · {timezone}</span>
                <input name="scheduled_at" type="datetime-local" required />
              </Field>
              <Field>
                <span>Location or meeting link</span>
                <input
                  name="location_or_link"
                  defaultValue={interview.location_or_link}
                  required
                  maxLength={500}
                />
              </Field>
            </>
          )}
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            <ActionButton type="submit" $variant="primary" disabled={busy}>
              {busy ? "Saving…" : "Send response"}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

function HiringDialog({
  modal,
  listings,
  timezone,
  screeningEnabled,
  busy,
  onClose,
  onSubmit,
}: {
  modal: Exclude<Modal, null>;
  listings: HiringWorkspace["listings"];
  timezone: string;
  screeningEnabled: boolean;
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [localError, setLocalError] = useState('');
  const latestTitle =
    modal.kind === "offer"
      ? listings.find((item) => item.id === modal.candidate.listing_id)
          ?.title || ""
      : "";
  const latestListing = modal.kind === "offer"
    ? listings.find((item) => item.id === modal.candidate.listing_id)
    : undefined;
  const [serviceWindows, setServiceWindows] = useState<AtsServiceWindow[]>(
    () => screeningEnabled
      ? latestListing?.structured_terms.service_windows.map((window) => ({ ...window, days: [...window.days] })) ?? []
      : [],
  );
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const raw = Object.fromEntries(data.entries());
    try {
    const positionShape = screeningEnabled
      ? String(raw.position_shape || latestListing?.structured_terms.position_shape || "educator_only")
      : "educator_only";
    const structuredTerms: Record<string, unknown> = !screeningEnabled
      ? {}
      : positionShape === "educator_only" ? {
      position_shape: "educator_only",
      driving_requirement: "not_applicable",
      vehicle_expectation: "none",
      required_licence_jurisdiction: null,
      required_licence_jurisdiction_other: null,
      required_licence_class: null,
      minimum_driving_experience_months: 0,
      service_area: null,
      service_windows: [],
      mileage_policy: null,
      driving_time_paid: false,
      screening_conditions: String(raw.screening_conditions || "")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    } : {
      position_shape: positionShape,
      driving_requirement: String(raw.driving_requirement || latestListing?.structured_terms.driving_requirement || "required"),
      vehicle_expectation: String(raw.vehicle_expectation || latestListing?.structured_terms.vehicle_expectation || "organization_vehicle"),
      required_licence_jurisdiction: raw.required_licence_jurisdiction || "CA-AB",
      required_licence_jurisdiction_other: raw.required_licence_jurisdiction === "OTHER" ? raw.required_licence_jurisdiction_other || null : null,
      required_licence_class: raw.required_licence_class || "5",
      minimum_driving_experience_months: raw.minimum_driving_experience_months
        ? Number(raw.minimum_driving_experience_months)
        : 0,
      service_area: raw.service_area || null,
      service_windows: serviceWindows,
      mileage_policy: raw.mileage_policy || null,
      driving_time_paid: raw.driving_time_paid === "yes",
      screening_conditions: String(raw.screening_conditions || "")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    };
    if (screeningEnabled && positionShape !== "educator_only") {
      const drivingTerms = structuredTerms as unknown as StructuredRoleTerms;
      if (drivingTerms.required_licence_jurisdiction === "OTHER" && !drivingTerms.required_licence_jurisdiction_other)
        throw new Error("Describe the required licence jurisdiction.");
      if (drivingTerms.service_windows.some((window) => !window.days.length || window.start_time === window.end_time))
        throw new Error("Every service window needs at least one day and different start/end times.");
      if (["personal_vehicle", "either"].includes(drivingTerms.vehicle_expectation) && !drivingTerms.mileage_policy)
        throw new Error("Personal-vehicle roles need a mileage or expense policy.");
    }
    const payload =
      modal.kind === "listing"
        ? {
            ...structuredTerms,
            title: raw.title,
            location: raw.location || undefined,
            employment_type: raw.employment_type,
            description: raw.description,
            requirements: String(raw.requirements || "")
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean),
          }
        : {
              ...structuredTerms,
              position_title: raw.position_title,
              compensation: raw.compensation || undefined,
              start_date: raw.start_date || undefined,
              terms: raw.terms,
              expires_at: raw.expires_at ? zonedDateTimeToIso(String(raw.expires_at), timezone) : undefined,
            };
    setLocalError(''); void onSubmit(payload);
    } catch (caught) { setLocalError(caught instanceof Error ? caught.message : 'The local date and time could not be interpreted.'); }
  };
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog role="dialog" aria-modal="true">
        <DialogHead>
          <div>
            <Eyebrow>
              {modal.kind === "listing"
                ? "New opportunity"
                : "Versioned terms"}
            </Eyebrow>
            <h2>
              {modal.kind === "listing"
                ? "Create a job listing"
                : `Offer for ${modal.candidate.first_name}`}
            </h2>
            <p>
              {modal.kind === "offer"
                ? "Saving creates a new immutable version for review."
                : "Required fields are kept intentionally focused."}
            </p>
          </div>
          <IconButton
            type="button"
            aria-label="Close dialog"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <Form onSubmit={submit}>
          {localError && <Notice $error role="alert"><ExclamationTriangleIcon /> {localError}</Notice>}
          {modal.kind === "listing" && (
            <>
              <Field>
                <span>Role title</span>
                <input name="title" required autoFocus />
              </Field>
              <Field>
                <span>Location</span>
                <input name="location" />
              </Field>
              <Field $wide>
                <span>Employment type</span>
                <select name="employment_type">
                  <option value="full_time">Full time</option>
                  <option value="part_time">Part time</option>
                  <option value="casual">Casual</option>
                  <option value="temporary">Temporary</option>
                </select>
              </Field>
              {screeningEnabled && (<>
              <Field>
                <span>Position shape</span>
                <select name="position_shape" defaultValue="educator_only">
                  <option value="educator_only">Educator only</option>
                  <option value="driver_only">Driver only</option>
                  <option value="educator_driver">Educator + driver</option>
                </select>
              </Field>
              <Field>
                <span>Driving duty</span>
                <select name="driving_requirement" defaultValue="required">
                  <option value="not_applicable">Not applicable</option>
                  <option value="preferred">Preferred</option>
                  <option value="required">Required</option>
                </select>
              </Field>
              <Field>
                <span>Vehicle expectation</span>
                <select name="vehicle_expectation" defaultValue="organization_vehicle">
                  <option value="none">No vehicle expectation</option>
                  <option value="organization_vehicle">Organization vehicle</option>
                  <option value="personal_vehicle">Personal vehicle</option>
                  <option value="either">Organization or personal vehicle</option>
                </select>
              </Field>
              <Field>
                <span>Required licence jurisdiction</span>
                <select name="required_licence_jurisdiction" defaultValue="CA-AB">
                  <option value="CA-AB">Alberta</option>
                  <option value="CA-BC">British Columbia</option>
                  <option value="CA-SK">Saskatchewan</option>
                  <option value="CA-MB">Manitoba</option>
                  <option value="CA-ON">Ontario</option>
                  <option value="OTHER">Other jurisdiction</option>
                </select>
              </Field>
              <Field>
                <span>Other jurisdiction (only when selected)</span>
                <input name="required_licence_jurisdiction_other" />
              </Field>
              <Field>
                <span>Required licence class</span>
                <select name="required_licence_class" defaultValue="5">
                  <option value="1">Class 1</option>
                  <option value="2">Class 2</option>
                  <option value="3">Class 3</option>
                  <option value="4">Class 4</option>
                  <option value="5">Class 5</option>
                  <option value="5 GDL">Class 5 GDL</option>
                  <option value="6">Class 6</option>
                  <option value="7">Class 7</option>
                </select>
              </Field>
              <Field>
                <span>Minimum driving experience (months)</span>
                <input name="minimum_driving_experience_months" type="number" min="0" max="1200" defaultValue="0" />
              </Field>
              <Field>
                <span>Is driving time paid?</span>
                <select name="driving_time_paid" defaultValue="no">
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </Field>
              <Field $wide>
                <span>Service area</span>
                <input name="service_area" placeholder="City/area only — never child addresses" />
              </Field>
              <ServiceWindowEditor value={serviceWindows} onChange={setServiceWindows} timezone={timezone} />
              <Field $wide>
                <span>Mileage / expense policy</span>
                <textarea name="mileage_policy" />
              </Field>
              <Field $wide>
                <span>Pre-start screening conditions (one per line)</span>
                <textarea name="screening_conditions" defaultValue={"Employer review of shared criminal-record / vulnerable-sector evidence"} />
              </Field>
              </>)}
              <Field $wide>
                <span>Description</span>
                <textarea name="description" required />
              </Field>
              <Field $wide>
                <span>Requirements (one per line)</span>
                <textarea name="requirements" />
              </Field>
            </>
          )}
          {modal.kind === "offer" && (
            <>
              <Field $wide>
                <span>Position</span>
                <input
                  name="position_title"
                  defaultValue={latestTitle}
                  required
                  autoFocus
                />
              </Field>
              <Field>
                <span>Compensation</span>
                <input name="compensation" placeholder="$24.50/hour" />
              </Field>
              <Field>
                <span>Start date</span>
                <input name="start_date" type="date" />
              </Field>
              <Field>
                <span>Accept by · {timezone}</span>
                <input name="expires_at" type="datetime-local" />
              </Field>
              {screeningEnabled && (<>
              <Field>
                <span>Position shape</span>
                <select name="position_shape" defaultValue={latestListing?.structured_terms.position_shape || "educator_only"}>
                  <option value="educator_only">Educator only</option>
                  <option value="driver_only">Driver only</option>
                  <option value="educator_driver">Educator + driver</option>
                </select>
              </Field>
              <Field>
                <span>Driving duty</span>
                <select name="driving_requirement" defaultValue={latestListing?.structured_terms.driving_requirement || "not_applicable"}>
                  <option value="not_applicable">Not applicable</option>
                  <option value="preferred">Preferred</option>
                  <option value="required">Required</option>
                </select>
              </Field>
              <Field>
                <span>Vehicle expectation</span>
                <select name="vehicle_expectation" defaultValue={latestListing?.structured_terms.vehicle_expectation || "none"}>
                  <option value="none">No vehicle expectation</option>
                  <option value="organization_vehicle">Organization vehicle</option>
                  <option value="personal_vehicle">Personal vehicle</option>
                  <option value="either">Organization or personal vehicle</option>
                </select>
              </Field>
              <Field>
                <span>Required licence jurisdiction</span>
                <select name="required_licence_jurisdiction" defaultValue={latestListing?.structured_terms.required_licence_jurisdiction || "CA-AB"}>
                  <option value="CA-AB">Alberta</option>
                  <option value="CA-BC">British Columbia</option>
                  <option value="CA-SK">Saskatchewan</option>
                  <option value="CA-MB">Manitoba</option>
                  <option value="CA-ON">Ontario</option>
                  <option value="OTHER">Other jurisdiction</option>
                </select>
              </Field>
              <Field>
                <span>Other jurisdiction (only when selected)</span>
                <input name="required_licence_jurisdiction_other" defaultValue={latestListing?.structured_terms.required_licence_jurisdiction_other || ""} />
              </Field>
              <Field>
                <span>Required licence class</span>
                <select name="required_licence_class" defaultValue={latestListing?.structured_terms.required_licence_class || "5"}>
                  <option value="1">Class 1</option>
                  <option value="2">Class 2</option>
                  <option value="3">Class 3</option>
                  <option value="4">Class 4</option>
                  <option value="5">Class 5</option>
                  <option value="5 GDL">Class 5 GDL</option>
                  <option value="6">Class 6</option>
                  <option value="7">Class 7</option>
                </select>
              </Field>
              <Field>
                <span>Minimum driving experience (months)</span>
                <input name="minimum_driving_experience_months" type="number" min="0" max="1200" defaultValue={latestListing?.structured_terms.minimum_driving_experience_months ?? 0} />
              </Field>
              <Field>
                <span>Is driving time paid?</span>
                <select name="driving_time_paid" defaultValue={latestListing?.structured_terms.driving_time_paid ? "yes" : "no"}>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </Field>
              <Field $wide>
                <span>Service area</span>
                <input name="service_area" defaultValue={latestListing?.structured_terms.service_area || ""} />
              </Field>
              <ServiceWindowEditor value={serviceWindows} onChange={setServiceWindows} timezone={timezone} />
              <Field $wide>
                <span>Mileage / expense policy</span>
                <textarea name="mileage_policy" defaultValue={latestListing?.structured_terms.mileage_policy || ""} />
              </Field>
              <Field $wide>
                <span>Pre-start screening conditions (one per line)</span>
                <textarea name="screening_conditions" defaultValue={latestListing?.structured_terms.screening_conditions.join("\n") || ""} />
              </Field>
              </>)}
              <Field $wide>
                <span>Offer terms</span>
                <textarea
                  name="terms"
                  placeholder="Schedule, conditions, and review terms"
                  required
                />
              </Field>
            </>
          )}
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            <ActionButton
              type="submit"
              $variant="primary"
              disabled={busy}
            >
              {busy
                ? "Saving…"
                : modal.kind === "offer"
                    ? "Create & send offer"
                    : "Save"}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

const serviceWeekdays: Array<{ value: ServiceWeekday; label: string }> = [
  { value: 'monday', label: 'Mon' },
  { value: 'tuesday', label: 'Tue' },
  { value: 'wednesday', label: 'Wed' },
  { value: 'thursday', label: 'Thu' },
  { value: 'friday', label: 'Fri' },
  { value: 'saturday', label: 'Sat' },
  { value: 'sunday', label: 'Sun' },
];

function ServiceWindowEditor({
  value,
  onChange,
  timezone,
}: {
  value: AtsServiceWindow[];
  onChange: (next: AtsServiceWindow[]) => void;
  timezone: string;
}) {
  const update = (index: number, next: AtsServiceWindow) =>
    onChange(value.map((item, position) => (position === index ? next : item)));
  return (
    <WindowEditor>
      <strong>Typical service windows</strong>
      <small>Choose weekdays and exact local times · {timezone}</small>
      {value.map((window, index) => (
        <div className="window" key={`${index}-${window.start_time}`}>
          <div className="days">
            {serviceWeekdays.map((day) => {
              const selected = window.days.includes(day.value);
              return (
                <button
                  type="button"
                  key={day.value}
                  aria-pressed={selected}
                  onClick={() =>
                    update(index, {
                      ...window,
                      days: selected
                        ? window.days.filter((item) => item !== day.value)
                        : [...window.days, day.value],
                    })
                  }
                >
                  {day.label}
                </button>
              );
            })}
          </div>
          <div className="times">
            <input
              aria-label="Service window start time"
              type="time"
              value={window.start_time.slice(0, 5)}
              onChange={(event) =>
                update(index, { ...window, start_time: `${event.target.value}:00` })
              }
            />
            <input
              aria-label="Service window end time"
              type="time"
              value={window.end_time.slice(0, 5)}
              onChange={(event) =>
                update(index, { ...window, end_time: `${event.target.value}:00` })
              }
            />
          </div>
          <ActionButton
            type="button"
            $variant="danger"
            onClick={() => onChange(value.filter((_item, position) => position !== index))}
          >
            Remove window
          </ActionButton>
        </div>
      ))}
      <ActionButton
        type="button"
        onClick={() =>
          onChange([
            ...value,
            {
              days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
              start_time: '07:00:00',
              end_time: '09:00:00',
              timezone,
            },
          ])
        }
      >
        <PlusIcon /> Add service window
      </ActionButton>
    </WindowEditor>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowDownIcon,
  ArrowPathIcon,
  ArrowUpIcon,
  BuildingOffice2Icon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ClipboardDocumentCheckIcon,
  ClockIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  MapPinIcon,
  PencilSquareIcon,
  PhoneIcon,
  PlusIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserIcon,
  UsersIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import { isCommandRejectedBeforeCommit } from '../../api/childcareCommand';
import {
  ChildcareCommandRecoveredCommitError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
} from '../../childcare-commands/ChildcareCommandRecoveryContext';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  acceptAdmissionOffer,
  correctAdmissionApplication,
  createAdmissionOffer,
  fetchAdmissionApplication,
  fetchAdmissionConversionCandidates,
  fetchAdmissionLaneDirectory,
  reopenAdmissionReview,
  runAdmissionCommand,
  runAdmissionOfferCommand,
  updateAdmissionApplication,
  waitlistAdmissionApplication,
  type AdmissionActionName,
  type AdmissionConversionCandidateReview,
  type AdmissionConversionResolution,
  type AdmissionCreateInput,
  type AdmissionDetail,
  type AdmissionLaneFacility,
  type AdmissionLaneProgram,
  type AdmissionStatus,
} from './admissionsDecisionApi';

type ConfirmableAction =
  | 'submit'
  | 'start_review'
  | 'enter_waitlist'
  | 'issue_offer'
  | 'reopen_review'
  | 'decline'
  | 'withdraw'
  | 'withdraw_offer'
  | 'decline_offer';

type FactsEditKind = 'update' | 'correct';
type BusyAction = ConfirmableAction | FactsEditKind | 'accept_and_convert';

interface ActionDraft {
  kind: ConfirmableAction;
  applicationVersion: number;
  facilityId: string;
  programId: string;
  startDate: string;
  respondByDate: string;
  reasonCode: string;
  confirmed: boolean;
}

interface PreferenceDraft {
  key: string;
  facilityId: string;
  programId: string;
  desiredStartDate: string;
}

interface FactsDraft {
  kind: FactsEditKind;
  applicationVersion: number;
  childFirstName: string;
  childLastName: string;
  dateOfBirth: string;
  contactFirstName: string;
  contactLastName: string;
  relationship: string;
  email: string;
  telephone: string;
  internalNote: string;
  preferences: PreferenceDraft[];
  confirmed: boolean;
}

interface DirectoryState {
  phase: 'loading' | 'ready' | 'error';
  facilities: AdmissionLaneFacility[];
  message: string;
}

interface ProgramState {
  phase: 'idle' | 'loading' | 'ready' | 'error';
  programs: AdmissionLaneProgram[];
  message: string;
}

type ProgramDirectory = Record<string, ProgramState>;

interface ConversionDraft {
  review: AdmissionConversionCandidateReview;
  mode: AdmissionConversionResolution['resolution_mode'];
  familyId: string;
  childId: string;
  confirmedDistinct: boolean;
  distinctReason: string;
  confirmed: boolean;
}

const enter = keyframes`
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
`;

const spin = keyframes`to { transform: rotate(360deg); }`;

const Page = styled.div`
  display: grid;
  gap: 16px;
  animation: ${enter} 360ms ${({ theme }) => theme.motion.ease} both;
`;

const BackLink = styled(Link)`
  display: inline-flex;
  width: fit-content;
  min-height: 42px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  font-size: .76rem;
  font-weight: 600;
  transition: border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; transform: translateX(-2px); }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 2px; }
  svg { width: 17px; }
`;

const Hero = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, .6fr);
  gap: 26px;
  padding: clamp(20px, 3vw, 30px);
  background:
    radial-gradient(circle at 8% 8%, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 11%, transparent), transparent 30%),
    radial-gradient(circle at 90% 0%, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 10%, transparent), transparent 32%),
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};
  @media (max-width: 820px) { grid-template-columns: 1fr; }
`;

const HeroCopy = styled.div`
  min-width: 0;
  h1 {
    margin: 12px 0 8px;
    overflow-wrap: anywhere;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(1.75rem, 4vw, 2.8rem);
    font-weight: 520;
    letter-spacing: -.052em;
    line-height: 1.02;
  }
  > p { max-width: 760px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .8rem; line-height: 1.65; }
`;

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
`;

const VersionCard = styled.div`
  align-self: stretch;
  display: grid;
  align-content: center;
  gap: 12px;
  padding: 17px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 15px 6px 15px 6px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
  strong { font-family: 'CareSync Display', sans-serif; font-size: 1.55rem; font-weight: 520; }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.55; }
`;

const Notice = styled.div<{ $error?: boolean; $warning?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 13px 15px;
  border: 1px solid ${({ $error, $warning, theme }) => $error ? theme.color.coral : $warning ? theme.color.amber : theme.color.mint};
  border-radius: 13px 5px 13px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $error, $warning, theme }) => `color-mix(in srgb, ${$error ? theme.color.coral : $warning ? theme.color.amber : theme.color.mint} 8%, ${theme.color.surfaceStrong})`};
  font-size: .74rem;
  line-height: 1.55;
  svg { width: 18px; flex: 0 0 auto; color: ${({ $error, $warning, theme }) => $error ? theme.color.coral : $warning ? theme.color.amber : theme.color.mint}; }
`;

const Layout = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(300px, .65fr);
  gap: 14px;
  align-items: start;
  @media (max-width: 980px) { grid-template-columns: 1fr; }
`;

const Column = styled.div`display: grid; gap: 14px; min-width: 0;`;

const Section = styled(GlassPanel)`padding: 18px;`;

const SectionHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.06rem; font-weight: 540; letter-spacing: -.025em; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.55; }
  > svg { width: 21px; flex: 0 0 auto; color: ${({ theme }) => theme.color.cyan}; }
`;

const FactGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin: 0;
  div { min-width: 0; padding: 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; }
  dt { color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; }
  dd { margin: 5px 0 0; overflow-wrap: anywhere; color: ${({ theme }) => theme.color.textSoft}; font-size: .76rem; line-height: 1.5; }
  @media (max-width: 560px) { grid-template-columns: 1fr; }
`;

const PreferenceList = styled.ol`
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const Preference = styled.li`
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px 5px 13px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  > span {
    display: grid;
    width: 34px;
    height: 34px;
    place-items: center;
    border: 1px solid ${({ theme }) => theme.color.cyan};
    border-radius: 10px 4px 10px 4px;
    color: ${({ theme }) => theme.color.cyan};
    font-size: .72rem;
    font-weight: 700;
  }
  strong { display: block; font-size: .78rem; font-weight: 600; }
  small { display: block; margin-top: 4px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.45; }
  time { color: ${({ theme }) => theme.color.textSoft}; font-size: .7rem; white-space: nowrap; }
  @media (max-width: 580px) { grid-template-columns: 38px 1fr; time { grid-column: 2; } }
`;

const Timeline = styled.ol`
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const TimelineItem = styled.li`
  position: relative;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 68px;
  padding-bottom: 15px;
  &::before { position: absolute; top: 24px; bottom: 0; left: 9px; width: 1px; content: ''; background: ${({ theme }) => theme.color.borderStrong}; }
  &:last-child::before { display: none; }
  > svg { position: relative; z-index: 1; width: 19px; padding: 3px; border-radius: 50%; color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.surface}; }
  strong { display: block; font-size: .76rem; font-weight: 600; }
  p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.5; }
  time { color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; white-space: nowrap; }
  @media (max-width: 560px) { grid-template-columns: 26px 1fr; time { grid-column: 2; } }
`;

const ActionGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

const ActionForm = styled.form`
  display: grid;
  gap: 13px;
  margin-top: 14px;
  padding: 15px;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 14px 6px 14px 6px;
  background: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 6%, ${({ theme }) => theme.color.surfaceStrong});
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .98rem; font-weight: 540; }
  > p { margin: -6px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .71rem; line-height: 1.55; }
`;

const FormGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 620px) { grid-template-columns: 1fr; }
`;

const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => $wide ? '1 / -1' : 'auto'};
  gap: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .67rem;
  font-weight: 650;
  letter-spacing: .06em;
  text-transform: uppercase;
  input, select, textarea {
    width: 100%;
    min-height: 43px;
    padding: 0 11px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px 5px 11px 5px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: .75rem;
    letter-spacing: normal;
    text-transform: none;
  }
  textarea { min-height: 96px; padding-block: 10px; resize: vertical; line-height: 1.5; }
  input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 13%, transparent); }
  input:disabled, select:disabled, textarea:disabled { opacity: .6; }
`;

const FactsEditorSection = styled(GlassPanel)`
  display: grid;
  gap: 18px;
  padding: clamp(18px, 3vw, 26px);
  border-color: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 45%, ${({ theme }) => theme.color.border});
  background:
    linear-gradient(135deg, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 6%, transparent), transparent 62%),
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};
`;

const EditorHeading = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  h2 { margin: 6px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: 1.25rem; font-weight: 540; letter-spacing: -.03em; }
  p { max-width: 760px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.58; }
  @media (max-width: 680px) { flex-direction: column; }
`;

const EditorGroup = styled.fieldset`
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 15px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px 6px 14px 6px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  legend {
    padding: 0 7px;
    color: ${({ theme }) => theme.color.textSoft};
    font-family: 'CareSync Display', sans-serif;
    font-size: .92rem;
    font-weight: 540;
  }
`;

const PreferenceEditorList = styled.div`display: grid; gap: 10px;`;

const PreferenceEditor = styled.div`
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px 5px 13px 5px;
  background: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 3%, ${({ theme }) => theme.color.surface});
  > strong {
    display: grid;
    width: 36px;
    height: 36px;
    place-items: center;
    border: 1px solid ${({ theme }) => theme.color.cyan};
    border-radius: 11px 4px 11px 4px;
    color: ${({ theme }) => theme.color.cyan};
    font-size: .72rem;
  }
  > button { margin-top: 23px; }
  @media (max-width: 700px) {
    grid-template-columns: 36px 1fr;
    > button { grid-column: 2; width: fit-content; margin-top: 0; }
  }
`;

const PreferenceFields = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 820px) { grid-template-columns: 1fr; }
`;

const PreferenceActions = styled.div`
  display: grid;
  gap: 6px;
  margin-top: 23px;
  button { min-width: 42px; padding-inline: 10px; }
  @media (max-width: 700px) { grid-column: 2; grid-template-columns: repeat(3, auto); width: fit-content; margin-top: 0; }
`;

const EditorToolbar = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; }
`;

const Confirmation = styled.label`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .71rem;
  line-height: 1.5;
  input { width: 17px; height: 17px; accent-color: ${({ theme }) => theme.color.cyan}; }
`;

const FormActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
`;

const StatusBlock = styled.div`
  display: grid;
  gap: 9px;
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px 5px 13px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  h3 { margin: 0; font-size: .79rem; font-weight: 600; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.55; overflow-wrap: anywhere; }
`;

const EntityLink = styled(Link)`
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 6px;
  color: ${({ theme }) => theme.color.cyan};
  font-size: .71rem;
  font-weight: 600;
  &:hover { text-decoration: underline; }
`;

const Empty = styled.div`
  padding: 16px;
  border: 1px dashed ${({ theme }) => theme.color.controlBorder};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .72rem;
  line-height: 1.6;
  text-align: center;
`;

const State = styled(GlassPanel)`
  display: grid;
  min-height: 440px;
  place-items: center;
  padding: 34px;
  text-align: center;
  div { max-width: 560px; }
  svg { width: 42px; margin: 0 auto 14px; color: ${({ theme }) => theme.color.cyan}; }
  h1 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.42rem; font-weight: 540; }
  p { margin: 0 0 18px; color: ${({ theme }) => theme.color.textMuted}; font-size: .76rem; line-height: 1.7; }
`;

const Spinning = styled(ArrowPathIcon)`animation: ${spin} 900ms linear infinite;`;

const ACTION_COPY: Record<ConfirmableAction, { label: string; title: string; description: string; confirmation: string }> = {
  submit: {
    label: 'Submit application',
    title: 'Submit this draft?',
    description: 'The initial intake snapshot becomes part of the immutable decision history.',
    confirmation: 'I reviewed the child, contact, and ranked program preferences before submission.',
  },
  start_review: {
    label: 'Start review',
    title: 'Begin application review?',
    description: 'This moves the submitted application into the decision workspace.',
    confirmation: 'I am ready to review this application against current program facts.',
  },
  enter_waitlist: {
    label: 'Enter waitlist',
    title: 'Place this application on a waitlist?',
    description: 'Choose the active facility, program, and requested date. Position remains deterministic and is not an entitlement.',
    confirmation: 'I understand this records queue priority and does not promise a space.',
  },
  issue_offer: {
    label: 'Issue offer',
    title: 'Issue a program offer?',
    description: 'The offer names a facility, program, and proposed start date. Room placement and financial terms remain separate.',
    confirmation: 'I verified the offered facility, program, and dates against current operational facts.',
  },
  reopen_review: {
    label: 'Reopen review',
    title: 'Remove this application from the active waitlist?',
    description: 'The queue entry closes and the application returns to review without erasing its history.',
    confirmation: 'I understand the current waitlist position will no longer remain active.',
  },
  decline: {
    label: 'Decline application',
    title: 'Decline this application?',
    description: 'Declined is terminal in this release. A later reapplication must be a new record.',
    confirmation: 'I reviewed the decision and understand this application becomes terminal.',
  },
  withdraw: {
    label: 'Record withdrawal',
    title: 'Record an off-platform family withdrawal?',
    description: 'Withdrawn is terminal and preserves the application history.',
    confirmation: 'I have a valid off-platform withdrawal request to record.',
  },
  withdraw_offer: {
    label: 'Withdraw offer',
    title: 'Withdraw this open offer?',
    description: 'The offer is retracted. A prior waitlist entry may return to its preserved queue priority.',
    confirmation: 'I reviewed the operational reason for retracting this offer.',
  },
  decline_offer: {
    label: 'Record offer decline',
    title: 'Record the family’s off-platform offer decline?',
    description: 'The application and offer become declined. This does not send a message to the family.',
    confirmation: 'I have a valid off-platform decline response to record.',
  },
};

const REASON_OPTIONS: Partial<Record<ConfirmableAction, Array<{ value: string; label: string }>>> = {
  reopen_review: [
    { value: 'capacity_reassessment', label: 'Capacity reassessment' },
    { value: 'program_review', label: 'Program review' },
    { value: 'family_request', label: 'Family request' },
  ],
  decline: [
    { value: 'capacity_unavailable', label: 'Capacity unavailable' },
    { value: 'program_unavailable', label: 'Program unavailable' },
    { value: 'eligibility_review', label: 'Eligibility review' },
    { value: 'other', label: 'Other reviewed reason' },
  ],
  withdraw: [
    { value: 'family_requested', label: 'Family requested withdrawal' },
    { value: 'duplicate_application', label: 'Duplicate application' },
    { value: 'other', label: 'Other recorded request' },
  ],
  withdraw_offer: [
    { value: 'placement_unavailable', label: 'Placement unavailable' },
    { value: 'offer_correction_required', label: 'Offer correction required' },
    { value: 'other', label: 'Other reviewed reason' },
  ],
  decline_offer: [
    { value: 'family_declined', label: 'Family declined' },
    { value: 'start_date_declined', label: 'Proposed start date declined' },
    { value: 'other', label: 'Other recorded response' },
  ],
};

const ACTION_PERMISSION: Readonly<Record<ConfirmableAction, 'manage' | 'decide'>> = {
  submit: 'manage',
  start_review: 'decide',
  enter_waitlist: 'decide',
  issue_offer: 'decide',
  reopen_review: 'decide',
  decline: 'decide',
  withdraw: 'manage',
  withdraw_offer: 'decide',
  decline_offer: 'manage',
};

const RELATIONSHIPS = [
  'Mother',
  'Father',
  'Parent',
  'Guardian',
  'Foster parent',
  'Grandparent',
  'Other',
] as const;

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value: string | null): string {
  if (!value) return 'Not recorded';
  const candidate = value.includes('T') ? value : `${value}T12:00:00`;
  const date = new Date(candidate);
  return Number.isNaN(date.getTime())
    ? 'Not recorded'
    : date.toLocaleDateString('en-CA', { day: 'numeric', month: 'short', year: 'numeric' });
}

function dateTimeLabel(value: string | null): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Not recorded'
    : date.toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
}

function statusTone(status: AdmissionStatus): 'success' | 'warning' | 'info' | 'neutral' {
  if (status === 'accepted') return 'success';
  if (status === 'declined' || status === 'withdrawn') return 'neutral';
  if (status === 'waitlisted' || status === 'offered') return 'warning';
  return 'info';
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'The admission request could not be completed.';
}

function canRunAction(action: ConfirmableAction, canManage: boolean, canDecide: boolean): boolean {
  return ACTION_PERMISSION[action] === 'decide' ? canDecide : canManage;
}

function reasonRequired(action: ConfirmableAction): boolean {
  return Boolean(REASON_OPTIONS[action]?.length);
}

function chooseLaneDefaults(application: AdmissionDetail, facilities: readonly AdmissionLaneFacility[]) {
  const preferredLane = application.waitlist
    ?? application.offer
    ?? application.preferences[0]
    ?? null;
  const requestedFacilityId = preferredLane?.facility_id ?? '';
  const facilityId = facilities.some((facility) => facility.id === requestedFacilityId)
    ? requestedFacilityId
    : facilities[0]?.id ?? '';
  const requestedProgramId = preferredLane?.facility_id === facilityId ? preferredLane.program_id : '';
  const matchingPreference = application.preferences.find((preference) => (
    preference.facility_id === facilityId && (!requestedProgramId || preference.program_id === requestedProgramId)
  ));
  return {
    facilityId,
    programId: requestedProgramId,
    startDate: application.offer?.proposed_start_date
      ?? application.waitlist?.requested_start_date
      ?? matchingPreference?.requested_start_date
      ?? application.preferences[0]?.requested_start_date
      ?? '',
    respondByDate: application.offer?.respond_by_date ?? '',
  };
}

function createFactsDraft(application: AdmissionDetail, kind: FactsEditKind): FactsDraft {
  return {
    kind,
    applicationVersion: application.version,
    childFirstName: application.child.first_name,
    childLastName: application.child.last_name,
    dateOfBirth: application.child.date_of_birth,
    contactFirstName: application.contact.first_name,
    contactLastName: application.contact.last_name,
    relationship: application.contact.relationship,
    email: application.contact.email ?? '',
    telephone: application.contact.telephone ?? '',
    internalNote: application.internal_note ?? '',
    preferences: application.preferences.map((preference) => ({
      key: preference.id,
      facilityId: preference.facility_id,
      programId: preference.program_id,
      desiredStartDate: preference.requested_start_date,
    })),
    confirmed: false,
  };
}

function factsInput(draft: FactsDraft): AdmissionCreateInput {
  return {
    child: {
      first_name: draft.childFirstName.trim(),
      last_name: draft.childLastName.trim(),
      date_of_birth: draft.dateOfBirth,
    },
    primary_contact: {
      first_name: draft.contactFirstName.trim(),
      last_name: draft.contactLastName.trim(),
      relationship: draft.relationship.trim(),
      email: draft.email.trim() || null,
      telephone: draft.telephone.trim() || null,
    },
    preferences: draft.preferences.map((preference, index) => ({
      rank: index + 1,
      facility_id: preference.facilityId,
      program_id: preference.programId,
      desired_start_date: preference.desiredStartDate,
    })),
    internal_note: draft.internalNote.trim() || null,
  };
}

export default function AdmissionApplicationPage() {
  const { applicationId = '' } = useParams();
  const session = useSession();
  const commandRecovery = useChildcareCommandRecovery();
  const organizationId = session.status === 'authenticated'
    && session.user?.organization_id
    && session.user.organization_id === session.organization?.id
    && !session.organizationUnavailable
    ? session.user.organization_id
    : '';
  const canManage = hasPermission(session.user, ACCESS.admissionsManage);
  const canDecide = hasPermission(session.user, ACCESS.admissionsDecide);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [application, setApplication] = useState<AdmissionDetail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeWarning, setNoticeWarning] = useState(false);
  const [activeAction, setActiveAction] = useState<ActionDraft | null>(null);
  const [factsEditor, setFactsEditor] = useState<FactsDraft | null>(null);
  const [conversionDraft, setConversionDraft] = useState<ConversionDraft | null>(null);
  const [conversionLoading, setConversionLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction | null>(null);
  const [pendingOperationId, setPendingOperationId] = useState<string | null>(null);
  const [directory, setDirectory] = useState<DirectoryState>({
    phase: 'loading',
    facilities: [],
    message: '',
  });
  const [programs, setPrograms] = useState<ProgramState>({
    phase: 'idle',
    programs: [],
    message: '',
  });
  const [preferencePrograms, setPreferencePrograms] = useState<ProgramDirectory>({});
  const activeIdentity = useRef({ organizationId, applicationId });
  const requestGeneration = useRef(0);
  const actionFocus = useRef<HTMLDivElement>(null);
  activeIdentity.current = { organizationId, applicationId };

  const loadApplication = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId || !applicationId) {
      throw new Error('The authenticated organization boundary could not be confirmed for this application.');
    }
    const generation = ++requestGeneration.current;
    const detail = await fetchAdmissionApplication(organizationId, applicationId, signal);
    if (
      !signal?.aborted
      && requestGeneration.current === generation
      && activeIdentity.current.organizationId === organizationId
      && activeIdentity.current.applicationId === applicationId
    ) {
      setApplication(detail);
      setPhase('ready');
      setError('');
    }
    return detail;
  }, [applicationId, organizationId]);

  useRealtimeRefresh({
    scope: 'admission-application-profile',
    organizationId,
    enabled: Boolean(organizationId && applicationId),
    entityTypes: featureIntegrationManifest.admissions.realtimeEntities,
    refresh: async () => { await loadApplication(); },
  });

  useEffect(() => {
    requestGeneration.current += 1;
    setActiveAction(null);
    setFactsEditor(null);
    setConversionDraft(null);
    setConversionLoading(false);
    setPreferencePrograms({});
    setBusyAction(null);
    setPendingOperationId(null);
    setNotice('');
    setNoticeWarning(false);
    setApplication(null);
    if (!organizationId || !applicationId) {
      setError('The authenticated organization boundary could not be confirmed for this application.');
      setPhase('error');
      return;
    }
    const controller = new AbortController();
    setPhase('loading');
    setError('');
    loadApplication(controller.signal).catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      setApplication(null);
      setError(errorMessage(caught));
      setPhase('error');
    });
    return () => controller.abort();
  }, [applicationId, loadApplication, organizationId]);

  useEffect(() => {
    if (!organizationId) {
      setDirectory({ phase: 'error', facilities: [], message: 'A confirmed organization is required.' });
      return;
    }
    const controller = new AbortController();
    setDirectory({ phase: 'loading', facilities: [], message: '' });
    const expectedIdentity = `${organizationId}:${applicationId}`;
    fetchAdmissionLaneDirectory(organizationId, controller.signal)
      .then((laneDirectory) => {
        if (
          !controller.signal.aborted
          && `${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` === expectedIdentity
        ) setDirectory({ phase: 'ready', facilities: laneDirectory.facilities, message: '' });
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setDirectory({ phase: 'error', facilities: [], message: errorMessage(caught) });
      });
    return () => controller.abort();
  }, [applicationId, organizationId]);

  useEffect(() => {
    const facilityId = activeAction?.kind === 'enter_waitlist' || activeAction?.kind === 'issue_offer'
      ? activeAction.facilityId
      : '';
    if (!organizationId || !facilityId || directory.phase !== 'ready') {
      setPrograms({ phase: facilityId ? 'loading' : 'idle', programs: [], message: '' });
      return;
    }
    const availablePrograms = directory.facilities.find((facility) => facility.id === facilityId)?.programs ?? [];
    setPrograms({ phase: 'ready', programs: availablePrograms, message: '' });
    setActiveAction((current) => {
      if (!current || current.facilityId !== facilityId || !['enter_waitlist', 'issue_offer'].includes(current.kind)) return current;
      const programId = availablePrograms.some((program) => program.id === current.programId)
        ? current.programId
        : availablePrograms[0]?.id ?? '';
      return programId === current.programId ? current : { ...current, programId };
    });
  }, [activeAction?.facilityId, activeAction?.kind, directory.facilities, directory.phase, organizationId]);

  const preferenceFacilityKey = useMemo(
    () => factsEditor?.preferences.map((preference) => preference.facilityId).filter(Boolean).join('|') ?? '',
    [factsEditor?.preferences],
  );

  useEffect(() => {
    if (!factsEditor || !organizationId || directory.phase !== 'ready') {
      if (!factsEditor) setPreferencePrograms({});
      return;
    }
    const facilityIds = [...new Set(factsEditor.preferences.map((preference) => preference.facilityId).filter(Boolean))];
    if (!facilityIds.length) return;
    const next: ProgramDirectory = {};
    facilityIds.forEach((facilityId) => {
      next[facilityId] = {
        phase: 'ready',
        programs: directory.facilities.find((facility) => facility.id === facilityId)?.programs ?? [],
        message: '',
      };
    });
    setPreferencePrograms(next);
    setFactsEditor((current) => {
      if (!current) return current;
      let changed = false;
      const preferences = current.preferences.map((preference) => {
        const availablePrograms = next[preference.facilityId]?.programs ?? [];
        if (!preference.facilityId || availablePrograms.some((program) => program.id === preference.programId)) {
          return preference;
        }
        changed = true;
        return { ...preference, programId: availablePrograms[0]?.id ?? '' };
      });
      return changed ? { ...current, preferences } : current;
    });
  }, [directory.facilities, directory.phase, factsEditor?.kind, organizationId, preferenceFacilityKey]);

  const allowedActions = useMemo(
    () => new Set(application?.allowed_actions ?? []),
    [application?.allowed_actions],
  );
  const mutationLocked = childcareMutationControlDisabled(
    commandRecovery.laneBlocked,
    Boolean(busyAction),
    conversionLoading,
  );

  const executeProtected = useCallback(async (
    operationId: string,
    metadata: {
      commandType:
        | 'admission.application.update'
        | 'admission.application.submit'
        | 'admission.application.review.start'
        | 'admission.application.decline'
        | 'admission.application.withdraw'
        | 'admission.application.correct'
        | 'admission.waitlist.enter'
        | 'admission.waitlist.reopen_review'
        | 'admission.offer.issue'
        | 'admission.offer.withdraw'
        | 'admission.offer.decline'
        | 'admission.offer.accept_and_convert';
      targetType: 'admission_application' | 'admission_waitlist' | 'admission_offer';
      expectedTargetId: string | null;
      expectedActionOwnerId: string | null;
    },
    send: (journalOperationId: string) => Promise<AdmissionDetail>,
  ): Promise<AdmissionDetail | null> => {
    const expectedIdentity = `${organizationId}:${applicationId}`;
    setPendingOperationId(operationId);
    try {
      const result = await commandRecovery.execute({
        clientOperationId: operationId,
        ...metadata,
      }, send);
      if (`${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` !== expectedIdentity) return null;
      setPendingOperationId(null);
      return result;
    } catch (caught) {
      if (`${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` !== expectedIdentity) return null;
      if (
        childcareCommandWasNotPrepared(caught, operationId)
        || isCommandRejectedBeforeCommit(caught)
      ) setPendingOperationId(null);
      if (caught instanceof ChildcareCommandRecoveredCommitError) {
        setPendingOperationId(null);
        setActiveAction(null);
        setFactsEditor(null);
        setConversionDraft(null);
        await loadApplication().catch(() => undefined);
        setNotice('CareSync confirmed that the interrupted admissions command was saved and refreshed the canonical profile.');
        setNoticeWarning(false);
        requestAnimationFrame(() => actionFocus.current?.focus());
        return null;
      }
      throw caught;
    }
  }, [applicationId, commandRecovery, loadApplication, organizationId]);

  useEffect(() => {
    if (
      busyAction
      || conversionLoading
      || !pendingOperationId
      || commandRecovery.lastResolved?.clientOperationId !== pendingOperationId
    ) return;
    setPendingOperationId(null);
    setActiveAction(null);
    setFactsEditor(null);
    setConversionDraft(null);
    setNotice('The previously unresolved admissions command was confirmed saved.');
    setNoticeWarning(false);
    void loadApplication().catch(() => {
      setNoticeWarning(true);
      setNotice('The admissions commit was found, but the private profile still needs a canonical refresh.');
    });
    requestAnimationFrame(() => actionFocus.current?.focus());
  }, [busyAction, commandRecovery.lastResolved, conversionLoading, loadApplication, pendingOperationId]);

  useEffect(() => {
    if (!childcareFinalAbsenceAcknowledged(
      pendingOperationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    setPendingOperationId(null);
    setError('The server proved this admissions command was not saved. Review the current profile and choose the action again to create a new operation.');
    requestAnimationFrame(() => actionFocus.current?.focus());
  }, [commandRecovery.lastFinalAbsenceAcknowledgedOperationId, pendingOperationId]);

  const openAction = (kind: ConfirmableAction) => {
    if (!application || mutationLocked || !allowedActions.has(kind as AdmissionActionName)) return;
    const defaults = chooseLaneDefaults(application, directory.facilities);
    const reasonCode = REASON_OPTIONS[kind]?.[0]?.value ?? '';
    setError('');
    setNotice('');
    setNoticeWarning(false);
    setFactsEditor(null);
    setActiveAction({
      kind,
      applicationVersion: application.version,
      ...defaults,
      reasonCode,
      confirmed: false,
    });
  };

  const openFactsEditor = (kind: FactsEditKind) => {
    if (!application || mutationLocked || !allowedActions.has(kind)) return;
    if ((kind === 'update' && !canManage) || (kind === 'correct' && !canDecide)) {
      setError('Your current role is not allowed to change these application facts.');
      return;
    }
    setError('');
    setNotice('');
    setNoticeWarning(false);
    setActiveAction(null);
    setPreferencePrograms({});
    setFactsEditor(createFactsDraft(application, kind));
  };

  const runFactsCommand = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!application || !factsEditor || mutationLocked) return;
    if (application.version !== factsEditor.applicationVersion) {
      setError(`This profile advanced from version ${factsEditor.applicationVersion} to version ${application.version} while the editor was open. Review the canonical facts and reopen the editor.`);
      return;
    }
    const permitted = factsEditor.kind === 'update' ? canManage : canDecide;
    if (!permitted || !allowedActions.has(factsEditor.kind)) {
      setError('Your current role or the current application state does not allow this facts command.');
      return;
    }
    if (!factsEditor.confirmed) {
      setError('Confirm the full facts replacement before continuing.');
      return;
    }
    const requiredText = [
      factsEditor.childFirstName,
      factsEditor.childLastName,
      factsEditor.dateOfBirth,
      factsEditor.contactFirstName,
      factsEditor.contactLastName,
      factsEditor.relationship,
    ];
    if (requiredText.some((value) => !value.trim())) {
      setError('Complete the child and primary-contact fields.');
      return;
    }
    if (!factsEditor.email.trim() && !factsEditor.telephone.trim()) {
      setError('Record at least one contact method: email or telephone.');
      return;
    }
    const telephone = factsEditor.telephone.trim();
    if (telephone && (telephone.length > 30 || telephone.replace(/\D/g, '').length < 7)) {
      setError('Telephone numbers must contain at least seven digits and no more than 30 characters.');
      return;
    }
    if (factsEditor.preferences.length < 1 || factsEditor.preferences.length > 5) {
      setError('Keep between one and five ranked preferences.');
      return;
    }
    if (factsEditor.preferences.some((preference) => (
      !preference.facilityId || !preference.programId || !preference.desiredStartDate
    ))) {
      setError('Complete the facility, program, and requested start date for every preference.');
      return;
    }
    const lanes = factsEditor.preferences.map((preference) => `${preference.facilityId}:${preference.programId}`);
    if (new Set(lanes).size !== lanes.length) {
      setError('Each ranked facility/program lane must be unique.');
      return;
    }

    const commandApplication = application;
    const command = factsEditor;
    const operationId = crypto.randomUUID();
    setBusyAction(command.kind);
    setError('');
    setNotice('');
    setNoticeWarning(false);
    try {
      const input = factsInput(command);
      const result = await executeProtected(operationId, {
        commandType: command.kind === 'update'
          ? 'admission.application.update'
          : 'admission.application.correct',
        targetType: 'admission_application',
        expectedTargetId: commandApplication.id,
        expectedActionOwnerId: null,
      }, (journalOperationId) => command.kind === 'update'
        ? updateAdmissionApplication(organizationId, commandApplication, journalOperationId, input)
        : correctAdmissionApplication(organizationId, commandApplication, journalOperationId, input));
      if (!result) return;
      setApplication(result);
      setFactsEditor(null);
      setPreferencePrograms({});
      setNotice(result.replayed
        ? 'The server returned the previously committed result for this exact facts operation. No duplicate transition was created.'
        : `${command.kind === 'update' ? 'Draft facts updated' : 'Submitted facts corrected'} at application version ${result.version}.`);
      try {
        await loadApplication();
      } catch (refreshError: unknown) {
        setNoticeWarning(true);
        setNotice(`The facts command committed, but the canonical profile refresh needs attention: ${errorMessage(refreshError)}`);
      }
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setBusyAction(null);
    }
  };

  const runCommand = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!application || !activeAction || mutationLocked) return;
    if (application.version !== activeAction.applicationVersion) {
      setError(`This profile advanced from version ${activeAction.applicationVersion} to version ${application.version} while the confirmation was open. Review the canonical state and choose the action again.`);
      return;
    }
    if (!canRunAction(activeAction.kind, canManage, canDecide)) {
      setError('Your current role is not allowed to run this admissions command.');
      return;
    }
    if (!activeAction.confirmed) {
      setError('Confirm the decision before continuing.');
      return;
    }
    if (
      (activeAction.kind === 'enter_waitlist' || activeAction.kind === 'issue_offer')
      && (!activeAction.facilityId || !activeAction.programId || !activeAction.startDate)
    ) {
      setError('Choose an active facility, program, and start date.');
      return;
    }
    if (
      activeAction.kind === 'issue_offer'
      && application.status === 'waitlisted'
      && (
        !application.waitlist
        || activeAction.facilityId !== application.waitlist.facility_id
        || activeAction.programId !== application.waitlist.program_id
      )
    ) {
      setError('An offer from the waitlist must stay in the current queue lane. Reopen review before choosing a different facility or program.');
      return;
    }
    if (
      activeAction.kind === 'issue_offer'
      && activeAction.respondByDate
      && activeAction.respondByDate > activeAction.startDate
    ) {
      setError('The response deadline cannot be after the proposed start date.');
      return;
    }
    if (reasonRequired(activeAction.kind) && !activeAction.reasonCode) {
      setError('Choose a bounded reason for this decision.');
      return;
    }

    const commandApplication = application;
    const command = activeAction;
    const operationId = crypto.randomUUID();
    setBusyAction(command.kind);
    setError('');
    setNotice('');
    setNoticeWarning(false);
    try {
      let result: AdmissionDetail | null;
      if (command.kind === 'submit') {
        result = await executeProtected(operationId, {
          commandType: 'admission.application.submit',
          targetType: 'admission_application',
          expectedTargetId: commandApplication.id,
          expectedActionOwnerId: null,
        }, (journalOperationId) => runAdmissionCommand(organizationId, commandApplication, 'submit', journalOperationId));
      } else if (command.kind === 'start_review') {
        result = await executeProtected(operationId, {
          commandType: 'admission.application.review.start',
          targetType: 'admission_application',
          expectedTargetId: commandApplication.id,
          expectedActionOwnerId: null,
        }, (journalOperationId) => runAdmissionCommand(organizationId, commandApplication, 'review/start', journalOperationId));
      } else if (command.kind === 'decline') {
        result = await executeProtected(operationId, {
          commandType: 'admission.application.decline',
          targetType: 'admission_application',
          expectedTargetId: commandApplication.id,
          expectedActionOwnerId: null,
        }, (journalOperationId) => runAdmissionCommand(organizationId, commandApplication, 'decline', journalOperationId, command.reasonCode));
      } else if (command.kind === 'withdraw') {
        result = await executeProtected(operationId, {
          commandType: 'admission.application.withdraw',
          targetType: 'admission_application',
          expectedTargetId: commandApplication.id,
          expectedActionOwnerId: null,
        }, (journalOperationId) => runAdmissionCommand(organizationId, commandApplication, 'withdraw', journalOperationId, command.reasonCode));
      } else if (command.kind === 'enter_waitlist') {
        result = await executeProtected(operationId, {
          commandType: 'admission.waitlist.enter',
          targetType: 'admission_waitlist',
          expectedTargetId: null,
          expectedActionOwnerId: commandApplication.id,
        }, (journalOperationId) => waitlistAdmissionApplication(organizationId, commandApplication, journalOperationId, {
          facility_id: command.facilityId,
          program_id: command.programId,
          desired_start_date: command.startDate,
        }));
      } else if (command.kind === 'reopen_review') {
        result = await executeProtected(operationId, {
          commandType: 'admission.waitlist.reopen_review',
          targetType: 'admission_waitlist',
          expectedTargetId: commandApplication.waitlist?.id ?? null,
          expectedActionOwnerId: commandApplication.id,
        }, (journalOperationId) => reopenAdmissionReview(organizationId, commandApplication, journalOperationId, command.reasonCode));
      } else if (command.kind === 'issue_offer') {
        result = await executeProtected(operationId, {
          commandType: 'admission.offer.issue',
          targetType: 'admission_offer',
          expectedTargetId: null,
          expectedActionOwnerId: commandApplication.id,
        }, (journalOperationId) => createAdmissionOffer(organizationId, commandApplication, journalOperationId, {
          facility_id: command.facilityId,
          program_id: command.programId,
          proposed_start_date: command.startDate,
          respond_by_date: command.respondByDate || null,
        }));
      } else if (command.kind === 'withdraw_offer') {
        result = await executeProtected(operationId, {
          commandType: 'admission.offer.withdraw',
          targetType: 'admission_offer',
          expectedTargetId: commandApplication.offer?.id ?? null,
          expectedActionOwnerId: commandApplication.id,
        }, (journalOperationId) => runAdmissionOfferCommand(organizationId, commandApplication, 'withdraw', journalOperationId, command.reasonCode));
      } else {
        result = await executeProtected(operationId, {
          commandType: 'admission.offer.decline',
          targetType: 'admission_offer',
          expectedTargetId: commandApplication.offer?.id ?? null,
          expectedActionOwnerId: commandApplication.id,
        }, (journalOperationId) => runAdmissionOfferCommand(organizationId, commandApplication, 'decline', journalOperationId, command.reasonCode));
      }

      if (!result) return;
      setApplication(result);
      setActiveAction(null);
      setNotice(result.replayed
        ? 'The server returned the previously committed result for this exact operation. No duplicate transition was created.'
        : `${ACTION_COPY[command.kind].label} committed at application version ${result.version}.`);

      try {
        await loadApplication();
      } catch (refreshError: unknown) {
        setNoticeWarning(true);
        setNotice(`The command committed, but the canonical profile refresh needs attention: ${errorMessage(refreshError)}`);
      }
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setBusyAction(null);
    }
  };

  const openConversionReview = async () => {
    if (
      !application
      || !application.offer
      || application.offer.status !== 'open'
      || !allowedActions.has('accept_and_convert')
      || !canDecide
      || mutationLocked
    ) return;
    const reviewedApplication = application;
    const expectedIdentity = `${organizationId}:${applicationId}`;
    setConversionLoading(true);
    setError('');
    setNotice('');
    setActiveAction(null);
    setFactsEditor(null);
    try {
      const review = await fetchAdmissionConversionCandidates(
        organizationId,
        reviewedApplication,
      );
      if (
        `${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` !== expectedIdentity
      ) return;
      const reusableChild = review.children.find((candidate) => candidate.is_active && !candidate.has_open_enrollment);
      const reusableFamily = review.families.find((candidate) => candidate.status === 'active');
      setConversionDraft({
        review,
        mode: reusableChild
          ? 'reuse_child'
          : reusableFamily
            ? 'reuse_family_create_child'
            : 'create_family_and_child',
        familyId: reusableChild?.family_id ?? reusableFamily?.id ?? '',
        childId: reusableChild?.id ?? '',
        confirmedDistinct: false,
        distinctReason: '',
        confirmed: false,
      });
      requestAnimationFrame(() => actionFocus.current?.focus());
    } catch (caught) {
      if (`${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` === expectedIdentity) {
        setError(errorMessage(caught));
      }
    } finally {
      if (`${activeIdentity.current.organizationId}:${activeIdentity.current.applicationId}` === expectedIdentity) {
        setConversionLoading(false);
      }
    }
  };

  const acceptConversion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !application
      || !application.offer
      || !conversionDraft
      || !canDecide
      || mutationLocked
    ) return;
    if (
      application.id !== conversionDraft.review.application_id
      || application.version !== conversionDraft.review.application_version
      || application.offer.id !== conversionDraft.review.offer_id
      || application.offer.version !== conversionDraft.review.offer_version
    ) {
      setError('The application or offer changed after duplicate review. Refresh the review before accepting.');
      return;
    }
    if (!conversionDraft.confirmed) {
      setError('Confirm the reviewed conversion effect before accepting the offer.');
      return;
    }

    let resolution: AdmissionConversionResolution;
    if (conversionDraft.mode === 'create_family_and_child') {
      const hasCandidates = Boolean(
        conversionDraft.review.families.length || conversionDraft.review.children.length,
      );
      if (hasCandidates && (!conversionDraft.confirmedDistinct || !conversionDraft.distinctReason.trim())) {
        setError('Review every possible match and record why this is a distinct person before creating new canonical records.');
        return;
      }
      resolution = {
        resolution_mode: 'create_family_and_child',
        confirmed_distinct_person: hasCandidates,
        distinct_person_reason: hasCandidates ? conversionDraft.distinctReason.trim() : null,
      };
    } else if (conversionDraft.mode === 'reuse_family_create_child') {
      const family = conversionDraft.review.families.find((candidate) => (
        candidate.id === conversionDraft.familyId && candidate.status === 'active'
      ));
      if (!family) {
        setError('Choose a currently active reviewed family.');
        return;
      }
      resolution = {
        resolution_mode: 'reuse_family_create_child',
        family_id: family.id,
        expected_family_version: family.version,
      };
    } else {
      const child = conversionDraft.review.children.find((candidate) => (
        candidate.id === conversionDraft.childId
        && candidate.family_id === conversionDraft.familyId
        && candidate.is_active
        && !candidate.has_open_enrollment
      ));
      const family = conversionDraft.review.families.find((candidate) => (
        candidate.id === conversionDraft.familyId && candidate.status === 'active'
      ));
      if (!child || !family) {
        setError('Choose a currently active reviewed child and family without an open enrollment.');
        return;
      }
      resolution = {
        resolution_mode: 'reuse_child',
        family_id: family.id,
        expected_family_version: family.version,
        child_id: child.id,
        expected_child_version: child.version,
      };
    }

    const commandApplication = application;
    const commandOffer = application.offer;
    const operationId = crypto.randomUUID();
    setBusyAction('accept_and_convert');
    setError('');
    try {
      const result = await executeProtected(operationId, {
        commandType: 'admission.offer.accept_and_convert',
        targetType: 'admission_offer',
        expectedTargetId: commandOffer.id,
        expectedActionOwnerId: commandApplication.id,
      }, (journalOperationId) => acceptAdmissionOffer(
        organizationId,
        commandApplication,
        conversionDraft.review,
        journalOperationId,
        resolution,
      ));
      if (!result) return;
      setApplication(result);
      setConversionDraft(null);
      setNotice(result.replayed
        ? 'The exact acceptance was already committed; CareSync returned the canonical conversion.'
        : 'Offer accepted. Family, Child, and pending unassigned Enrollment committed atomically.');
      setNoticeWarning(false);
      await loadApplication().catch((caught) => {
        setNoticeWarning(true);
        setNotice(`Acceptance committed, but the canonical profile refresh needs attention: ${errorMessage(caught)}`);
      });
      requestAnimationFrame(() => actionFocus.current?.focus());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusyAction(null);
    }
  };

  if (phase === 'loading') {
    return <State aria-live="polite"><div><Spinning /><h1>Loading the private application profile…</h1><p>CareSync is rebuilding the current application, offer, waitlist, and immutable timeline from canonical records.</p></div></State>;
  }

  if (phase === 'error' || !application) {
    return <Page>
      <BackLink to="/admissions"><ArrowLeftIcon /> Admissions workspace</BackLink>
      <State role="alert"><div><ExclamationTriangleIcon /><h1>Application profile unavailable.</h1><p>{error || 'This application could not be loaded.'}</p><ActionButton type="button" onClick={() => { setPhase('loading'); void loadApplication().catch((caught: unknown) => { setError(errorMessage(caught)); setPhase('error'); }); }}><ArrowPathIcon /> Try again</ActionButton></div></State>
    </Page>;
  }

  const fullName = `${application.child.first_name} ${application.child.last_name}`;
  const openOffer = application.offer?.status === 'open';
  const confirmableActions = ([
    'submit',
    'start_review',
    'enter_waitlist',
    'issue_offer',
    'reopen_review',
    'decline',
    'withdraw',
    'withdraw_offer',
    'decline_offer',
  ] satisfies ConfirmableAction[]).filter((action) => allowedActions.has(action as AdmissionActionName));
  const factsActions = (['update', 'correct'] satisfies FactsEditKind[]).filter((action) => allowedActions.has(action));
  const laneAction = activeAction?.kind === 'enter_waitlist' || activeAction?.kind === 'issue_offer';
  const actionCopy = activeAction ? ACTION_COPY[activeAction.kind] : null;
  const actionReasonOptions = activeAction ? REASON_OPTIONS[activeAction.kind] ?? [] : [];
  const relationshipChoices = factsEditor && !RELATIONSHIPS.some((relationship) => relationship === factsEditor.relationship)
    ? [factsEditor.relationship, ...RELATIONSHIPS]
    : [...RELATIONSHIPS];

  return <Page>
    <BackLink to="/admissions"><ArrowLeftIcon /> Admissions workspace</BackLink>

    <Hero $accent="cyan">
      <HeroCopy>
        <Eyebrow><ClipboardDocumentCheckIcon width={14} /> Admission application · {application.reference}</Eyebrow>
        <h1>{fullName}</h1>
        <p>A private, versioned intake and decision profile. Application facts, queue status, offers, conversion, and timeline remain separate canonical records.</p>
        <Chips>
          <StatusChip $tone={statusTone(application.status)}>{titleCase(application.status)}</StatusChip>
          <StatusChip $tone="info">Version {application.version}</StatusChip>
          {application.offer && <StatusChip $tone={application.offer.status === 'open' ? 'warning' : 'neutral'}>Offer · {titleCase(application.offer.status)}</StatusChip>}
          {application.waitlist && <StatusChip $tone={application.waitlist.status === 'active' ? 'warning' : 'neutral'}>Waitlist · {titleCase(application.waitlist.status)}</StatusChip>}
        </Chips>
      </HeroCopy>
      <VersionCard>
        <span>Committed state</span>
        <strong>v{application.committed_versions.application}</strong>
        <small>Waitlist {application.committed_versions.waitlist ? `v${application.committed_versions.waitlist}` : '—'} · Offer {application.committed_versions.offer ? `v${application.committed_versions.offer}` : '—'}</small>
        <small>Updated {dateTimeLabel(application.updated_at)}</small>
      </VersionCard>
    </Hero>

    {notice && <Notice $warning={noticeWarning} role="status"><CheckCircleIcon /> {notice}</Notice>}
    {error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}

    {factsEditor && <FactsEditorSection as="form" onSubmit={runFactsCommand} $accent="cyan">
      <EditorHeading>
        <div>
          <Eyebrow><PencilSquareIcon width={14} /> {factsEditor.kind === 'update' ? 'Draft facts editor' : 'Submitted facts correction'}</Eyebrow>
          <h2>{factsEditor.kind === 'update' ? 'Update this draft’s complete intake snapshot.' : 'Correct the complete submitted intake snapshot.'}</h2>
          <p>{factsEditor.kind === 'update'
            ? 'The application remains a draft. Every child, contact, and ranked preference value below replaces the current draft facts together.'
            : 'This versioned correction returns the application to review and closes any active waitlist entry with the server-authored facts_changed reason. An open offer must be withdrawn first.'}</p>
        </div>
        <StatusChip $tone={factsEditor.kind === 'correct' ? 'warning' : 'info'}>
          {factsEditor.kind === 'correct' ? 'Decision permission' : 'Manage permission'} · base v{factsEditor.applicationVersion}
        </StatusChip>
      </EditorHeading>

      <EditorGroup disabled={mutationLocked}>
        <legend>Child facts</legend>
        <FormGrid>
          <Field>
            First name
            <input
              required
              maxLength={100}
              autoComplete="off"
              value={factsEditor.childFirstName}
              onChange={(event) => setFactsEditor({ ...factsEditor, childFirstName: event.target.value, confirmed: false })}
            />
          </Field>
          <Field>
            Last name
            <input
              required
              maxLength={100}
              autoComplete="off"
              value={factsEditor.childLastName}
              onChange={(event) => setFactsEditor({ ...factsEditor, childLastName: event.target.value, confirmed: false })}
            />
          </Field>
          <Field>
            Date of birth
            <input
              required
              type="date"
              max={new Date().toISOString().slice(0, 10)}
              value={factsEditor.dateOfBirth}
              onChange={(event) => setFactsEditor({ ...factsEditor, dateOfBirth: event.target.value, confirmed: false })}
            />
          </Field>
        </FormGrid>
      </EditorGroup>

      <EditorGroup disabled={mutationLocked}>
        <legend>Primary contact</legend>
        <FormGrid>
          <Field>
            First name
            <input
              required
              maxLength={100}
              autoComplete="off"
              value={factsEditor.contactFirstName}
              onChange={(event) => setFactsEditor({ ...factsEditor, contactFirstName: event.target.value, confirmed: false })}
            />
          </Field>
          <Field>
            Last name
            <input
              required
              maxLength={100}
              autoComplete="off"
              value={factsEditor.contactLastName}
              onChange={(event) => setFactsEditor({ ...factsEditor, contactLastName: event.target.value, confirmed: false })}
            />
          </Field>
          <Field>
            Relationship
            <select
              required
              value={factsEditor.relationship}
              onChange={(event) => setFactsEditor({ ...factsEditor, relationship: event.target.value, confirmed: false })}
            >
              {relationshipChoices.map((relationship) => <option key={relationship} value={relationship}>{relationship}</option>)}
            </select>
          </Field>
          <Field>
            Email
            <input
              type="email"
              maxLength={320}
              autoComplete="off"
              placeholder="Email or telephone is required"
              value={factsEditor.email}
              onChange={(event) => setFactsEditor({ ...factsEditor, email: event.target.value, confirmed: false })}
            />
          </Field>
          <Field>
            Telephone
            <input
              type="tel"
              minLength={7}
              maxLength={30}
              autoComplete="off"
              placeholder="Email or telephone is required"
              value={factsEditor.telephone}
              onChange={(event) => setFactsEditor({ ...factsEditor, telephone: event.target.value, confirmed: false })}
            />
          </Field>
          <Field $wide>
            Internal note (optional)
            <textarea
              maxLength={2000}
              value={factsEditor.internalNote}
              onChange={(event) => setFactsEditor({ ...factsEditor, internalNote: event.target.value, confirmed: false })}
            />
          </Field>
        </FormGrid>
      </EditorGroup>

      <EditorGroup disabled={mutationLocked}>
        <legend>Ranked program preferences</legend>
        <EditorToolbar>
          <p>One to five unique facility/program lanes. Their displayed order becomes contiguous rank 1–5.</p>
          <ActionButton
            type="button"
            disabled={factsEditor.preferences.length >= 5 || directory.phase !== 'ready'}
            onClick={() => {
              const facilityId = directory.facilities[0]?.id ?? '';
              setFactsEditor({
                ...factsEditor,
                preferences: [...factsEditor.preferences, {
                  key: crypto.randomUUID(),
                  facilityId,
                  programId: '',
                  desiredStartDate: application.preferences[0]?.requested_start_date ?? '',
                }],
                confirmed: false,
              });
            }}
          >
            <PlusIcon /> Add preference
          </ActionButton>
        </EditorToolbar>
        {directory.message && <Notice $error role="alert"><ExclamationTriangleIcon /> {directory.message}</Notice>}
        <PreferenceEditorList>
          {factsEditor.preferences.map((preference, index) => {
            const programState = preferencePrograms[preference.facilityId] ?? {
              phase: preference.facilityId ? 'loading' : 'idle',
              programs: [],
              message: '',
            };
            return <PreferenceEditor key={preference.key}>
              <strong>{index + 1}</strong>
              <PreferenceFields>
                <Field>
                  Facility
                  <select
                    required
                    disabled={directory.phase !== 'ready'}
                    value={preference.facilityId}
                    onChange={(event) => {
                      const facilityId = event.target.value;
                      setFactsEditor({
                        ...factsEditor,
                        preferences: factsEditor.preferences.map((item) => item.key === preference.key
                          ? { ...item, facilityId, programId: '' }
                          : item),
                        confirmed: false,
                      });
                    }}
                  >
                    <option value="">{directory.phase === 'loading' ? 'Loading facilities…' : 'Choose a facility'}</option>
                    {directory.facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
                  </select>
                </Field>
                <Field>
                  Program
                  <select
                    required
                    disabled={programState.phase !== 'ready'}
                    value={preference.programId}
                    onChange={(event) => setFactsEditor({
                      ...factsEditor,
                      preferences: factsEditor.preferences.map((item) => item.key === preference.key
                        ? { ...item, programId: event.target.value }
                        : item),
                      confirmed: false,
                    })}
                  >
                    <option value="">{programState.phase === 'loading' ? 'Loading programs…' : 'Choose a program'}</option>
                    {programState.programs.map((program) => <option key={program.id} value={program.id}>{program.name}{program.program_type ? ` · ${titleCase(program.program_type)}` : ''}</option>)}
                  </select>
                  {programState.message && <span role="alert">{programState.message}</span>}
                </Field>
                <Field>
                  Requested start date
                  <input
                    required
                    type="date"
                    value={preference.desiredStartDate}
                    onChange={(event) => setFactsEditor({
                      ...factsEditor,
                      preferences: factsEditor.preferences.map((item) => item.key === preference.key
                        ? { ...item, desiredStartDate: event.target.value }
                        : item),
                      confirmed: false,
                    })}
                  />
                </Field>
              </PreferenceFields>
              <PreferenceActions>
                <ActionButton
                  type="button"
                  aria-label={`Move preference ${index + 1} up`}
                  disabled={index === 0}
                  onClick={() => {
                    const reordered = [...factsEditor.preferences];
                    [reordered[index - 1], reordered[index]] = [reordered[index]!, reordered[index - 1]!];
                    setFactsEditor({ ...factsEditor, preferences: reordered, confirmed: false });
                  }}
                >
                  <ArrowUpIcon />
                </ActionButton>
                <ActionButton
                  type="button"
                  aria-label={`Move preference ${index + 1} down`}
                  disabled={index === factsEditor.preferences.length - 1}
                  onClick={() => {
                    const reordered = [...factsEditor.preferences];
                    [reordered[index], reordered[index + 1]] = [reordered[index + 1]!, reordered[index]!];
                    setFactsEditor({ ...factsEditor, preferences: reordered, confirmed: false });
                  }}
                >
                  <ArrowDownIcon />
                </ActionButton>
                <ActionButton
                  type="button"
                  $variant="danger"
                  aria-label={`Remove preference ${index + 1}`}
                  disabled={factsEditor.preferences.length <= 1}
                  onClick={() => setFactsEditor({
                    ...factsEditor,
                    preferences: factsEditor.preferences.filter((item) => item.key !== preference.key),
                    confirmed: false,
                  })}
                >
                  <TrashIcon />
                </ActionButton>
              </PreferenceActions>
            </PreferenceEditor>;
          })}
        </PreferenceEditorList>
      </EditorGroup>

      <Confirmation>
        <input
          required
          type="checkbox"
          disabled={mutationLocked}
          checked={factsEditor.confirmed}
          onChange={(event) => setFactsEditor({ ...factsEditor, confirmed: event.target.checked })}
        />
        <span>{factsEditor.kind === 'update'
          ? 'I reviewed the complete replacement and understand this command writes one new draft version.'
          : 'I reviewed the complete replacement and understand this correction returns the application to review and closes any active waitlist entry.'}</span>
      </Confirmation>

      <FormActions>
        <ActionButton
          type="button"
          disabled={mutationLocked}
          onClick={() => { setFactsEditor(null); setPreferencePrograms({}); setError(''); }}
        >
          Keep current facts
        </ActionButton>
        <ActionButton type="submit" $variant="primary" disabled={mutationLocked || !factsEditor.confirmed}>
          {busyAction === factsEditor.kind
            ? <><Spinning /> Saving version…</>
            : <><CheckCircleIcon /> Confirm full {factsEditor.kind === 'update' ? 'draft update' : 'facts correction'}</>}
        </ActionButton>
      </FormActions>
    </FactsEditorSection>}

    <Layout>
      <Column>
        <Section $accent="plasma">
          <SectionHeader>
            <div><h2>Child and primary contact</h2><p>Minimum intake facts only. These are not yet canonical Family or Child identities.</p></div>
            <IdentificationIcon />
          </SectionHeader>
          <FactGrid>
            <div><dt>Child</dt><dd>{fullName}</dd></div>
            <div><dt>Date of birth</dt><dd>{dateLabel(application.child.date_of_birth)}</dd></div>
            <div><dt>Primary contact</dt><dd>{application.contact.first_name} {application.contact.last_name}</dd></div>
            <div><dt>Relationship</dt><dd>{application.contact.relationship}</dd></div>
            <div><dt>Email</dt><dd>{application.contact.email || 'Not recorded'}</dd></div>
            <div><dt>Telephone</dt><dd>{application.contact.telephone || 'Not recorded'}</dd></div>
            <div><dt>Internal note</dt><dd>{application.internal_note || 'No internal note'}</dd></div>
            <div><dt>Source</dt><dd>{titleCase(application.source)}</dd></div>
          </FactGrid>
        </Section>

        <Section $accent="cyan">
          <SectionHeader>
            <div><h2>Ranked preferences</h2><p>Requested lanes are snapshots, not promises of capacity, eligibility, or room placement.</p></div>
            <MapPinIcon />
          </SectionHeader>
          {application.preferences.length ? <PreferenceList>
            {application.preferences.map((preference) => <Preference key={preference.id}>
              <span>{preference.rank}</span>
              <div>
                <strong>{preference.program_name}</strong>
                <small>{preference.facility_name} · preference snapshot v{preference.application_version}</small>
              </div>
              <time dateTime={preference.requested_start_date}>{dateLabel(preference.requested_start_date)}</time>
            </Preference>)}
          </PreferenceList> : <Empty>No ranked program preferences were returned.</Empty>}
        </Section>

        <Section>
          <SectionHeader>
            <div>
              <h2>Immutable transition timeline</h2>
              <p>{application.timeline_total > application.timeline.length
                ? `Showing the most recent ${application.timeline.length} of ${application.timeline_total} preserved lifecycle transitions.`
                : `Showing all ${application.timeline_total} preserved lifecycle ${application.timeline_total === 1 ? 'transition' : 'transitions'}, with application version and bounded reason.`}</p>
            </div>
            <ClockIcon />
          </SectionHeader>
          {application.timeline.length ? <Timeline>
            {application.timeline.map((item) => <TimelineItem key={item.id}>
              <CheckCircleIcon />
              <div>
                <strong>{titleCase(item.command)}</strong>
                <p>{item.from_status ? `${titleCase(item.from_status)} → ` : ''}{titleCase(item.to_status)} · application v{item.application_version}{item.reason_code ? ` · ${titleCase(item.reason_code)}` : ''}</p>
              </div>
              <time dateTime={item.occurred_at}>{dateTimeLabel(item.occurred_at)}</time>
            </TimelineItem>)}
          </Timeline> : <Empty>No timeline events were returned.</Empty>}
        </Section>
      </Column>

      <Column>
        <Section ref={actionFocus} tabIndex={-1} $accent="cyan">
          <SectionHeader>
            <div><h2>Next valid action</h2><p>Only transitions returned by the server for version {application.version} are shown.</p></div>
            <ShieldCheckIcon />
          </SectionHeader>
          {factsActions.length || confirmableActions.length ? <ActionGrid>
            {factsActions.map((action) => {
              const permitted = action === 'update' ? canManage : canDecide;
              return <ActionButton
                key={action}
                type="button"
                $variant={action === 'correct' ? 'primary' : 'quiet'}
                disabled={mutationLocked || Boolean(activeAction) || Boolean(factsEditor) || Boolean(conversionDraft) || !permitted}
                title={permitted
                  ? action === 'update'
                    ? 'Replace the complete facts on this draft.'
                    : 'Correct the complete submitted facts and return the application to review.'
                  : 'Your role does not have the required admissions permission.'}
                onClick={() => openFactsEditor(action)}
              >
                {busyAction === action ? <Spinning /> : <PencilSquareIcon />}
                {action === 'update' ? 'Edit draft facts' : 'Correct submitted facts'}
              </ActionButton>;
            })}
            {confirmableActions.map((action) => {
              const permitted = canRunAction(action, canManage, canDecide);
              return <ActionButton
                key={action}
                type="button"
                $variant={action === 'decline' || action === 'withdraw' || action === 'withdraw_offer' || action === 'decline_offer' ? 'danger' : action === 'submit' || action === 'issue_offer' ? 'primary' : 'quiet'}
                disabled={mutationLocked || Boolean(activeAction) || Boolean(factsEditor) || Boolean(conversionDraft) || !permitted}
                title={permitted ? ACTION_COPY[action].description : 'Your role does not have the required admissions permission.'}
                onClick={() => openAction(action)}
              >
                {busyAction === action ? <Spinning /> : <ClipboardDocumentCheckIcon />}
                {ACTION_COPY[action].label}
              </ActionButton>;
            })}
          </ActionGrid> : <Empty>This application has no lifecycle command available in its current state.</Empty>}

          {!application.conversion && allowedActions.has('accept_and_convert') && !conversionDraft && <StatusBlock>
            <h3>Review duplicates before acceptance</h3>
            <p>Acceptance creates or reuses canonical people and commits one pending, unassigned Enrollment. Room placement remains a separate approval.</p>
            <ActionButton
              type="button"
              $variant="primary"
              disabled={mutationLocked || !canDecide}
              onClick={() => void openConversionReview()}
            >
              {conversionLoading ? <Spinning /> : <ShieldCheckIcon />} Review and accept offer
            </ActionButton>
          </StatusBlock>}

          {conversionDraft && <ActionForm onSubmit={acceptConversion}>
            <h3>Resolve reviewed people and accept</h3>
            <p>The signed duplicate review is bound to application v{conversionDraft.review.application_version} and offer v{conversionDraft.review.offer_version}. Changing canonical records invalidates it.</p>
            <FormGrid>
              <Field $wide>
                Resolution
                <select
                  value={conversionDraft.mode}
                  disabled={mutationLocked}
                  onChange={(event) => setConversionDraft({
                    ...conversionDraft,
                    mode: event.target.value as ConversionDraft['mode'],
                    familyId: '',
                    childId: '',
                    confirmedDistinct: false,
                    distinctReason: '',
                    confirmed: false,
                  })}
                >
                  <option value="create_family_and_child">Create a new Family and Child</option>
                  {conversionDraft.review.families.some((candidate) => candidate.status === 'active') && <option value="reuse_family_create_child">Reuse an active Family; create Child</option>}
                  {conversionDraft.review.children.some((candidate) => candidate.is_active && !candidate.has_open_enrollment) && <option value="reuse_child">Reuse an active Family and Child</option>}
                </select>
              </Field>

              {conversionDraft.mode !== 'create_family_and_child' && <Field $wide>
                Reviewed family
                <select
                  required
                  disabled={mutationLocked}
                  value={conversionDraft.familyId}
                  onChange={(event) => setConversionDraft({
                    ...conversionDraft,
                    familyId: event.target.value,
                    childId: '',
                    confirmed: false,
                  })}
                >
                  <option value="">Choose an active reviewed family</option>
                  {conversionDraft.review.families.filter((candidate) => candidate.status === 'active').map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.display_label} · v{candidate.version}</option>)}
                </select>
              </Field>}

              {conversionDraft.mode === 'reuse_child' && <Field $wide>
                Reviewed child
                <select
                  required
                  disabled={mutationLocked || !conversionDraft.familyId}
                  value={conversionDraft.childId}
                  onChange={(event) => setConversionDraft({
                    ...conversionDraft,
                    childId: event.target.value,
                    confirmed: false,
                  })}
                >
                  <option value="">Choose an eligible reviewed child</option>
                  {conversionDraft.review.children.filter((candidate) => (
                    candidate.family_id === conversionDraft.familyId
                    && candidate.is_active
                    && !candidate.has_open_enrollment
                  )).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.display_label} · v{candidate.version}</option>)}
                </select>
              </Field>}
            </FormGrid>

            {conversionDraft.mode === 'create_family_and_child' && Boolean(conversionDraft.review.families.length || conversionDraft.review.children.length) && <>
              <Notice $warning role="note"><ExclamationTriangleIcon /> Possible canonical matches exist. Review each label and match signal before creating distinct records.</Notice>
              {conversionDraft.review.families.map((candidate) => <StatusBlock key={candidate.id}>
                <h3>{candidate.display_label}</h3>
                <p>Family · {titleCase(candidate.status)} · v{candidate.version} · {candidate.match_reasons.map(titleCase).join(', ')}</p>
              </StatusBlock>)}
              {conversionDraft.review.children.map((candidate) => <StatusBlock key={candidate.id}>
                <h3>{candidate.display_label}</h3>
                <p>Child · v{candidate.version} · {candidate.has_open_enrollment ? 'has an open enrollment' : 'no open enrollment'} · {candidate.match_reasons.map(titleCase).join(', ')}</p>
              </StatusBlock>)}
              <Confirmation>
                <input
                  type="checkbox"
                  required
                  disabled={mutationLocked}
                  checked={conversionDraft.confirmedDistinct}
                  onChange={(event) => setConversionDraft({
                    ...conversionDraft,
                    confirmedDistinct: event.target.checked,
                    confirmed: false,
                  })}
                />
                <span>I reviewed every returned candidate and confirm this application represents a distinct person.</span>
              </Confirmation>
              <Field $wide>
                Distinct-person reason
                <textarea
                  required
                  maxLength={500}
                  disabled={mutationLocked}
                  value={conversionDraft.distinctReason}
                  onChange={(event) => setConversionDraft({
                    ...conversionDraft,
                    distinctReason: event.target.value,
                    confirmed: false,
                  })}
                />
              </Field>
            </>}

            <Confirmation>
              <input
                type="checkbox"
                required
                disabled={mutationLocked}
                checked={conversionDraft.confirmed}
                onChange={(event) => setConversionDraft({ ...conversionDraft, confirmed: event.target.checked })}
              />
              <span>I reviewed the match evidence and understand this atomically accepts the offer, links canonical people, and creates a pending unassigned Enrollment. It does not assign a room.</span>
            </Confirmation>
            <FormActions>
              <ActionButton type="button" disabled={mutationLocked} onClick={() => setConversionDraft(null)}>Cancel review</ActionButton>
              <ActionButton type="submit" $variant="primary" disabled={mutationLocked || !conversionDraft.confirmed}>
                {busyAction === 'accept_and_convert' ? <><Spinning /> Accepting atomically…</> : <><ShieldCheckIcon /> Accept and convert</>}
              </ActionButton>
            </FormActions>
          </ActionForm>}

          {activeAction && actionCopy && <ActionForm onSubmit={runCommand}>
            <h3>{actionCopy.title}</h3>
            <p>{actionCopy.description}</p>
            {laneAction && <FormGrid>
              <Field $wide>
                Facility
                <select
                  required
                  disabled={mutationLocked || directory.phase !== 'ready' || (activeAction.kind === 'issue_offer' && application.status === 'waitlisted')}
                  value={activeAction.facilityId}
                  onChange={(event) => setActiveAction({ ...activeAction, facilityId: event.target.value, programId: '' })}
                >
                  <option value="">{directory.phase === 'loading' ? 'Loading active facilities…' : 'Choose a facility'}</option>
                  {directory.facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
                </select>
              </Field>
              <Field $wide>
                Program
                <select
                  required
                  disabled={mutationLocked || programs.phase !== 'ready' || (activeAction.kind === 'issue_offer' && application.status === 'waitlisted')}
                  value={activeAction.programId}
                  onChange={(event) => setActiveAction({ ...activeAction, programId: event.target.value })}
                >
                  <option value="">{programs.phase === 'loading' ? 'Loading active programs…' : 'Choose a program'}</option>
                  {programs.programs.map((program) => <option key={program.id} value={program.id}>{program.name}{program.program_type ? ` · ${titleCase(program.program_type)}` : ''}</option>)}
                </select>
              </Field>
              <Field>
                {activeAction.kind === 'issue_offer' ? 'Proposed start date' : 'Requested start date'}
                <input
                  required
                  type="date"
                  disabled={mutationLocked}
                  value={activeAction.startDate}
                  onChange={(event) => setActiveAction({ ...activeAction, startDate: event.target.value })}
                />
              </Field>
              {activeAction.kind === 'issue_offer' && <Field>
                Respond by (optional)
                <input
                  type="date"
                  min={new Date().toISOString().slice(0, 10)}
                  max={activeAction.startDate || undefined}
                  disabled={mutationLocked}
                  value={activeAction.respondByDate}
                  onChange={(event) => setActiveAction({ ...activeAction, respondByDate: event.target.value })}
                />
              </Field>}
            </FormGrid>}

            {directory.message && laneAction && <Notice $error role="alert"><ExclamationTriangleIcon /> {directory.message}</Notice>}
            {programs.message && laneAction && <Notice $error role="alert"><ExclamationTriangleIcon /> {programs.message}</Notice>}

            {actionReasonOptions.length > 0 && <Field $wide>
              Decision reason
              <select
                required
                disabled={mutationLocked}
                value={activeAction.reasonCode}
                onChange={(event) => setActiveAction({ ...activeAction, reasonCode: event.target.value })}
              >
                {actionReasonOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </Field>}

            <Confirmation>
              <input
                required
                type="checkbox"
                disabled={mutationLocked}
                checked={activeAction.confirmed}
                onChange={(event) => setActiveAction({ ...activeAction, confirmed: event.target.checked })}
              />
              <span>{actionCopy.confirmation}</span>
            </Confirmation>

            <FormActions>
              <ActionButton type="button" disabled={mutationLocked} onClick={() => { setActiveAction(null); setError(''); }}>Cancel</ActionButton>
              <ActionButton
                type="submit"
                $variant={activeAction.kind === 'decline' || activeAction.kind === 'withdraw' || activeAction.kind === 'withdraw_offer' || activeAction.kind === 'decline_offer' ? 'danger' : 'primary'}
                disabled={mutationLocked || !activeAction.confirmed}
              >
                {busyAction ? <><Spinning /> Recording…</> : `Confirm · ${actionCopy.label}`}
              </ActionButton>
            </FormActions>
          </ActionForm>}
        </Section>

        <Section>
          <SectionHeader>
            <div><h2>Waitlist record</h2><p>Priority is computed within one facility/program lane.</p></div>
            <UsersIcon />
          </SectionHeader>
          {application.waitlist ? <StatusBlock>
            <StatusChip $tone={application.waitlist.status === 'active' ? 'warning' : 'neutral'}>{titleCase(application.waitlist.status)}</StatusChip>
            <h3>{application.waitlist.position === null ? 'Closed queue history' : `Position ${application.waitlist.position}`} · {application.waitlist.program_name}</h3>
            <p>{application.waitlist.facility_name} · requested {dateLabel(application.waitlist.requested_start_date)}</p>
            <p>Priority recorded {dateTimeLabel(application.waitlist.priority_at)} · waitlist v{application.waitlist.version}</p>
            {application.waitlist.closure_reason && <p>Closure reason: {titleCase(application.waitlist.closure_reason)}</p>}
          </StatusBlock> : <Empty>No waitlist record exists for this application.</Empty>}
        </Section>

        <Section>
          <SectionHeader>
            <div><h2>Offer record</h2><p>An offer contains no room assignment, fee, subsidy, or transportation promise.</p></div>
            <BuildingOffice2Icon />
          </SectionHeader>
          {application.offer ? <StatusBlock>
            <StatusChip $tone={openOffer ? 'warning' : application.offer.status === 'accepted' ? 'success' : 'neutral'}>{titleCase(application.offer.status)}</StatusChip>
            <h3>{application.offer.program_name}</h3>
            <p>{application.offer.facility_name} · starts {dateLabel(application.offer.proposed_start_date)}</p>
            <p>Respond by {dateLabel(application.offer.respond_by_date)} · offer v{application.offer.version}</p>
            <p>Issued {dateTimeLabel(application.offer.issued_at)} from {titleCase(application.offer.prior_application_status)}.</p>
          </StatusBlock> : <Empty>No offer has been issued.</Empty>}
        </Section>

        <Section>
          <SectionHeader>
            <div><h2>Canonical conversion</h2><p>Acceptance is complete only when the linked operational records commit atomically.</p></div>
            <ShieldCheckIcon />
          </SectionHeader>
          {application.conversion ? <StatusBlock>
            <StatusChip $tone="success">Converted</StatusChip>
            <h3>{titleCase(application.conversion.resolution_mode)}</h3>
            <p>Committed {dateTimeLabel(application.conversion.converted_at)}</p>
            <EntityLink to={`/families/${application.conversion.family_id}`}><UsersIcon width={15} /> Open family profile</EntityLink>
            <EntityLink to={`/children/${application.conversion.child_id}`}><UserIcon width={15} /> Open child profile</EntityLink>
            <p>Enrollment {application.conversion.enrollment_id} remains a distinct placement record.</p>
          </StatusBlock> : <Empty>No Family, Child, or Enrollment conversion has committed.</Empty>}
        </Section>

        <Section>
          <SectionHeader>
            <div><h2>Record facts</h2><p>Private application metadata and lifecycle timestamps.</p></div>
            <CalendarDaysIcon />
          </SectionHeader>
          <FactGrid>
            <div><dt>Reference</dt><dd>{application.reference}</dd></div>
            <div><dt>Application ID</dt><dd>{application.id}</dd></div>
            <div><dt>Created</dt><dd>{dateTimeLabel(application.created_at)}</dd></div>
            <div><dt>Submitted</dt><dd>{dateTimeLabel(application.submitted_at)}</dd></div>
            <div><dt>Review started</dt><dd>{dateTimeLabel(application.review_started_at)}</dd></div>
            <div><dt>Terminal</dt><dd>{dateTimeLabel(application.terminal_at)}</dd></div>
          </FactGrid>
        </Section>

        <Section>
          <SectionHeader>
            <div><h2>Contact shortcuts</h2><p>Use only for authorized operational follow-up.</p></div>
            <EnvelopeIcon />
          </SectionHeader>
          <StatusBlock>
            <p><EnvelopeIcon width={14} /> {application.contact.email || 'No email recorded'}</p>
            <p><PhoneIcon width={14} /> {application.contact.telephone || 'No telephone recorded'}</p>
            <p><XCircleIcon width={14} /> This release does not send automated parent messages from admissions decisions.</p>
          </StatusBlock>
        </Section>
      </Column>
    </Layout>
  </Page>;
}

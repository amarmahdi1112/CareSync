import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClipboardDocumentCheckIcon,
  ExclamationTriangleIcon,
  ListBulletIcon,
  PlusIcon,
  QueueListIcon,
  SparklesIcon,
  UserPlusIcon,
  XMarkIcon,
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
  ADMISSION_STATUSES,
  createAdmissionApplication,
  fetchAdmissionApplications,
  fetchAdmissionLaneDirectory,
  fetchAdmissionWaitlist,
  fetchAdmissionWorkspace,
  type AdmissionApplicationsPage,
  type AdmissionCreateInput,
  type AdmissionLaneDirectory,
  type AdmissionStatus,
  type AdmissionWaitlistPage,
  type AdmissionWorkspace,
} from './admissionsDecisionApi';

const spin = keyframes`to { transform: rotate(360deg); }`;

const Shell = styled.section`
  display: grid;
  gap: 13px;
`;

const CommandBar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 17px;
  @media (max-width: 720px) { align-items: stretch; flex-direction: column; }
`;

const Tabs = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
`;

const Tab = styled.button<{ $active: boolean }>`
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  color: ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textSoft};
  background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.cyan} 10%, ${theme.color.control})` : theme.color.control};
  cursor: pointer;
  font-size: .74rem;
  font-weight: 600;
  svg { width: 16px; }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 2px; }
`;

const TabPanel = styled.div`
  display: grid;
  gap: 13px;
  min-width: 0;
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 3px; }
`;

const Summary = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .7rem;
  @media (max-width: 720px) { justify-content: flex-start; }
`;

const Pipeline = styled.div`
  display: grid;
  grid-template-columns: repeat(8, minmax(210px, 1fr));
  gap: 10px;
  overflow-x: auto;
  padding: 3px 2px 10px;
  scrollbar-color: ${({ theme }) => theme.color.controlBorder} transparent;
`;

const Lane = styled(GlassPanel)`
  display: grid;
  min-height: 290px;
  grid-template-rows: auto minmax(0, 1fr);
`;

const LaneHeader = styled.header`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  h3 { margin: 0; font-size: .75rem; font-weight: 650; text-transform: capitalize; }
  strong { min-width: 26px; color: ${({ theme }) => theme.color.cyan}; font-family: 'CareSync Display', sans-serif; font-size: 1.08rem; font-weight: 520; text-align: right; }
`;

const LaneBody = styled.div`
  display: grid;
  align-content: start;
  gap: 8px;
  padding: 10px;
`;

const ApplicationLink = styled(Link)`
  display: grid;
  gap: 7px;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  transition: border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; transform: translateY(-1px); }
  strong { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: .76rem; font-weight: 620; }
  strong svg { width: 15px; color: ${({ theme }) => theme.color.cyan}; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; line-height: 1.45; }
`;

const EmptyLane = styled.div`
  display: grid;
  min-height: 92px;
  place-items: center;
  padding: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .67rem;
  line-height: 1.45;
  text-align: center;
`;

const Panel = styled(GlassPanel)`
  overflow: hidden;
`;

const PanelHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 17px 19px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.03rem; font-weight: 540; letter-spacing: -.025em; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
`;

const Waitlist = styled.ol`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const WaitlistRow = styled.li`
  display: grid;
  grid-template-columns: 70px minmax(170px, 1fr) minmax(220px, 1.2fr) 130px auto;
  align-items: center;
  gap: 14px;
  padding: 15px 19px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.surfaceStrong};
  &:hover { background: ${({ theme }) => theme.color.surfaceHover}; }
  strong { font-size: .78rem; font-weight: 620; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.45; }
  @media (max-width: 850px) { grid-template-columns: 60px 1fr auto; > :nth-child(3), > :nth-child(4) { grid-column: 2; } > :last-child { grid-column: 3; grid-row: 1 / span 3; } }
`;

const Position = styled.strong`
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 14px 5px 14px 5px;
  color: ${({ theme }) => theme.color.cyan};
  background: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 8%, transparent);
`;

const State = styled.div`
  display: grid;
  min-height: 190px;
  place-items: center;
  padding: 28px;
  color: ${({ theme }) => theme.color.textMuted};
  text-align: center;
  div { max-width: 560px; }
  svg { width: 32px; margin: 0 auto 11px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0 0 7px; color: ${({ theme }) => theme.color.text}; font-size: .95rem; font-weight: 590; }
  p { margin: 0; font-size: .72rem; line-height: 1.55; }
  button { margin-top: 14px; }
`;

const Spinning = styled(ArrowPathIcon)`animation: ${spin} 850ms linear infinite;`;

const Form = styled.form`
  display: grid;
  gap: 16px;
  padding: 18px 19px;
`;

const FormSection = styled.fieldset`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  border: 0;
  legend { grid-column: 1 / -1; margin-bottom: 11px; color: ${({ theme }) => theme.color.cyan}; font-size: .69rem; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
  @media (max-width: 650px) { grid-template-columns: 1fr; }
`;

const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => $wide ? '1 / -1' : 'auto'};
  gap: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .68rem;
  font-weight: 600;
  letter-spacing: .05em;
  text-transform: uppercase;
  input, select, textarea {
    width: 100%;
    min-height: 43px;
    padding: 9px 11px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px 5px 11px 5px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: .76rem;
    letter-spacing: 0;
    text-transform: none;
  }
  textarea { min-height: 88px; resize: vertical; }
  input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 12%, transparent); }
`;

const Preference = styled.div`
  display: grid;
  grid-template-columns: minmax(170px, 1fr) minmax(170px, 1fr) 150px auto;
  align-items: end;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px 6px 14px 6px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  @media (max-width: 820px) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

const FormActions = styled.footer`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 9px;
  padding-top: 2px;
  span { flex: 1; min-width: 220px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; }
`;

const ErrorNotice = styled.div`
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.coral} 45%, ${({ theme }) => theme.color.border});
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.coral};
  background: color-mix(in srgb, ${({ theme }) => theme.color.coral} 7%, ${({ theme }) => theme.color.surfaceStrong});
  font-size: .72rem;
  line-height: 1.5;
`;

const DirectoryControls = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px;
  padding: 14px 19px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
`;

const SearchField = styled.label`
  display: grid;
  min-width: min(320px, 100%);
  flex: 1;
  gap: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .67rem;
  font-weight: 650;
  letter-spacing: .06em;
  text-transform: uppercase;
  input {
    width: 100%;
    min-height: 43px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px 5px 11px 5px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font-size: .76rem;
    text-transform: none;
  }
  input:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 12%, transparent); }
`;

const DirectoryList = styled.ol`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const DirectoryRow = styled.li`
  display: grid;
  grid-template-columns: minmax(150px, .75fr) minmax(190px, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 14px 19px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.surfaceStrong};
  strong { font-size: .76rem; font-weight: 620; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.45; }
  @media (max-width: 560px) {
    grid-template-columns: minmax(0, 1fr) auto;
    > :nth-child(2) { grid-column: 1; }
    > :last-child { grid-column: 2; grid-row: 1 / span 2; }
  }
`;

const PageControls = styled.footer`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 13px 19px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .69rem;
  > div { display: flex; gap: 8px; }
`;

type View = 'pipeline' | 'waitlist' | 'new';
type LoadState = {
  organizationId: string;
  status: 'loading' | 'live' | 'error';
  workspace: AdmissionWorkspace | null;
  waitlist: AdmissionWaitlistPage | null;
  applications: AdmissionApplicationsPage | null;
  laneDirectory: AdmissionLaneDirectory | null;
  message?: string;
};

type PreferenceDraft = {
  key: string;
  facilityId: string;
  programId: string;
  desiredStartDate: string;
};

const statusLabel = (value: string): string => value.replaceAll('_', ' ');
const formatDate = (value: string): string => new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium' }).format(new Date(`${value}T12:00:00`));
const formatTime = (value: string): string => new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
const localKey = (): string => crypto.randomUUID();
const emptyPreference = (): PreferenceDraft => ({ key: localKey(), facilityId: '', programId: '', desiredStartDate: '' });
const APPLICATION_PAGE_SIZE = 25;
const WAITLIST_PAGE_SIZE = 100;

function organizationIdOf(session: ReturnType<typeof useSession>): string {
  return session.status === 'authenticated'
    && session.user?.organization_id
    && session.user.organization_id === session.organization?.id
    && !session.organizationUnavailable
    ? session.user.organization_id
    : '';
}

export default function AdmissionsDecisionWorkspace() {
  const session = useSession();
  const organizationId = organizationIdOf(session);
  const canManage = hasPermission(session.user, ACCESS.admissionsManage);
  const commandRecovery = useChildcareCommandRecovery();
  const navigate = useNavigate();
  const [view, setView] = useState<View>('pipeline');
  const [selectedStatus, setSelectedStatus] = useState<AdmissionStatus | ''>('');
  const [searchDraft, setSearchDraft] = useState('');
  const [search, setSearch] = useState('');
  const [applicationOffset, setApplicationOffset] = useState(0);
  const [waitlistOffset, setWaitlistOffset] = useState(0);
  const [state, setState] = useState<LoadState>({
    organizationId: '',
    status: 'loading',
    workspace: null,
    waitlist: null,
    applications: null,
    laneDirectory: null,
  });
  const [preferences, setPreferences] = useState<PreferenceDraft[]>(() => [emptyPreference()]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [pendingOperationId, setPendingOperationId] = useState<string | null>(null);
  const activeOrganizationId = useRef(organizationId);
  const requestGeneration = useRef(0);
  const tabRefs = useRef<Partial<Record<View, HTMLButtonElement | null>>>({});
  activeOrganizationId.current = organizationId;

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId) return;
    const generation = ++requestGeneration.current;
    try {
      const [workspace, waitlist, applications, laneDirectory] = await Promise.all([
        fetchAdmissionWorkspace(organizationId, signal),
        fetchAdmissionWaitlist(organizationId, {
          limit: WAITLIST_PAGE_SIZE,
          offset: waitlistOffset,
        }, signal),
        fetchAdmissionApplications(organizationId, {
          status: selectedStatus || undefined,
          search: search || undefined,
          limit: APPLICATION_PAGE_SIZE,
          offset: applicationOffset,
        }, signal),
        fetchAdmissionLaneDirectory(organizationId, signal),
      ]);
      if (
        !signal?.aborted
        && requestGeneration.current === generation
        && activeOrganizationId.current === organizationId
      ) {
        setState({
          organizationId,
          status: 'live',
          workspace,
          waitlist,
          applications,
          laneDirectory,
        });
      }
    } catch (caught) {
      if (
        !signal?.aborted
        && requestGeneration.current === generation
        && activeOrganizationId.current === organizationId
      ) {
        setState((current) => ({
          organizationId,
          status: current.organizationId === organizationId && current.workspace ? 'live' : 'error',
          workspace: current.organizationId === organizationId ? current.workspace : null,
          waitlist: current.organizationId === organizationId ? current.waitlist : null,
          applications: current.organizationId === organizationId ? current.applications : null,
          laneDirectory: current.organizationId === organizationId ? current.laneDirectory : null,
          message: caught instanceof Error ? caught.message : 'The admissions decision workspace is unavailable.',
        }));
      }
      throw caught;
    }
  }, [applicationOffset, organizationId, search, selectedStatus, waitlistOffset]);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setState((current) => current.organizationId === organizationId
      ? { ...current, status: 'loading', message: undefined }
      : {
          organizationId,
          status: 'loading',
          workspace: null,
          waitlist: null,
          applications: null,
          laneDirectory: null,
        });
    void load(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [load, organizationId]);

  useEffect(() => {
    setPreferences([emptyPreference()]);
    setSubmitError('');
    setView('pipeline');
    setSelectedStatus('');
    setSearchDraft('');
    setSearch('');
    setApplicationOffset(0);
    setWaitlistOffset(0);
    setPendingOperationId(null);
  }, [organizationId]);

  useEffect(() => {
    if (!canManage && view === 'new') setView('pipeline');
  }, [canManage, view]);

  useEffect(() => {
    if (state.organizationId !== organizationId || !state.applications) return;
    const { items, limit, offset, total } = state.applications;
    if (items.length || offset === 0) return;
    setApplicationOffset(total === 0 ? 0 : Math.floor((total - 1) / limit) * limit);
  }, [organizationId, state.applications, state.organizationId]);

  useEffect(() => {
    if (state.organizationId !== organizationId || !state.waitlist) return;
    const { items, limit, offset, total } = state.waitlist;
    if (items.length || offset === 0) return;
    setWaitlistOffset(total === 0 ? 0 : Math.floor((total - 1) / limit) * limit);
  }, [organizationId, state.organizationId, state.waitlist]);

  const refreshCanonical = useCallback(async () => {
    await load();
  }, [load]);

  useRealtimeRefresh({
    scope: 'admissions-decision-workspace',
    organizationId,
    enabled: Boolean(organizationId),
    entityTypes: featureIntegrationManifest.admissions.realtimeEntities,
    refresh: refreshCanonical,
  });

  const resetRetry = () => {
    if (!commandRecovery.laneBlocked) setPendingOperationId(null);
    if (submitError) setSubmitError('');
  };

  const updatePreference = (key: string, patch: Partial<PreferenceDraft>) => {
    resetRetry();
    setPreferences((current) => current.map((item) => item.key === key ? { ...item, ...patch } : item));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!organizationId || submitting || commandRecovery.laneBlocked) return;
    const form = new FormData(event.currentTarget);
    const validPreferences = preferences.map((item, index) => ({
      rank: index + 1,
      facility_id: item.facilityId,
      program_id: item.programId,
      desired_start_date: item.desiredStartDate,
    }));
    if (validPreferences.some((item) => !item.facility_id || !item.program_id || !item.desired_start_date)) {
      setSubmitError('Choose a facility, program, and requested start date for every preference.');
      return;
    }
    const lanes = validPreferences.map((item) => `${item.facility_id}:${item.program_id}`);
    if (new Set(lanes).size !== lanes.length) {
      setSubmitError('Each ranked facility/program lane must be unique.');
      return;
    }
    const text = (name: string) => String(form.get(name) || '').trim();
    if (!text('email') && !text('telephone')) {
      setSubmitError('Record at least one contact method: email or telephone.');
      return;
    }
    const telephone = text('telephone');
    if (telephone && (telephone.length > 30 || telephone.replace(/\D/g, '').length < 7)) {
      setSubmitError('Telephone numbers must contain at least seven digits and no more than 30 characters.');
      return;
    }
    const payload: AdmissionCreateInput = {
      child: { first_name: text('child_first_name'), last_name: text('child_last_name'), date_of_birth: text('date_of_birth') },
      primary_contact: {
        first_name: text('contact_first_name'),
        last_name: text('contact_last_name'),
        relationship: text('relationship'),
        email: text('email') || null,
        telephone: telephone || null,
      },
      preferences: validPreferences,
      internal_note: text('internal_note') || null,
    };
    const operationId = pendingOperationId || crypto.randomUUID();
    const expectedOrganizationId = organizationId;
    setPendingOperationId(operationId);
    setSubmitting(true);
    setSubmitError('');
    try {
      const created = await commandRecovery.execute({
        clientOperationId: operationId,
        commandType: 'admission.application.create',
        targetType: 'admission_application',
        expectedTargetId: null,
        expectedActionOwnerId: null,
      }, (journalOperationId) => createAdmissionApplication(
        expectedOrganizationId,
        journalOperationId,
        payload,
      ));
      if (activeOrganizationId.current !== expectedOrganizationId) return;
      setPendingOperationId(null);
      await refreshCanonical().catch(() => undefined);
      navigate(`/admissions/applications/${encodeURIComponent(created.id)}`);
    } catch (caught) {
      if (activeOrganizationId.current !== expectedOrganizationId) return;
      if (
        childcareCommandWasNotPrepared(caught, operationId)
        || isCommandRejectedBeforeCommit(caught)
      ) setPendingOperationId(null);
      if (caught instanceof ChildcareCommandRecoveredCommitError) {
        setPendingOperationId(null);
        await refreshCanonical().catch(() => undefined);
        navigate(caught.resolution.actionRoute);
        return;
      }
      setSubmitError(caught instanceof Error ? caught.message : 'The application was not confirmed. Retry keeps the same protected operation.');
    } finally {
      if (activeOrganizationId.current === expectedOrganizationId) setSubmitting(false);
    }
  };

  useEffect(() => {
    if (
      submitting
      || !pendingOperationId
      || commandRecovery.lastResolved?.clientOperationId !== pendingOperationId
    ) return;
    setPendingOperationId(null);
    setSubmitError('');
    void refreshCanonical().catch(() => undefined);
    navigate(commandRecovery.lastResolved.actionRoute);
  }, [commandRecovery.lastResolved, navigate, pendingOperationId, refreshCanonical, submitting]);

  useEffect(() => {
    if (!childcareFinalAbsenceAcknowledged(
      pendingOperationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    setPendingOperationId(null);
    setSubmitError('The server proved this draft was not created. Review the retained form and choose Create draft again to use a new operation.');
  }, [commandRecovery.lastFinalAbsenceAcknowledgedOperationId, pendingOperationId]);

  const scopedState: LoadState = state.organizationId === organizationId
    ? state
    : {
        organizationId,
        status: 'loading',
        workspace: null,
        waitlist: null,
        applications: null,
        laneDirectory: null,
      };
  const facilities = scopedState.laneDirectory?.facilities ?? [];
  const mutationLocked = childcareMutationControlDisabled(
    commandRecovery.laneBlocked,
    submitting,
  );

  const total = useMemo(
    () => scopedState.workspace
      ? ADMISSION_STATUSES.reduce((sum, item) => sum + scopedState.workspace!.counts[item], 0)
      : 0,
    [scopedState.workspace],
  );
  const visibleTabs = useMemo<View[]>(
    () => canManage ? ['pipeline', 'waitlist', 'new'] : ['pipeline', 'waitlist'],
    [canManage],
  );
  const selectTabFromKeyboard = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    currentView: View,
  ) => {
    const currentIndex = visibleTabs.indexOf(currentView);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % visibleTabs.length;
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + visibleTabs.length) % visibleTabs.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = visibleTabs.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextView = visibleTabs[nextIndex];
    setView(nextView);
    tabRefs.current[nextView]?.focus();
  };
  const tabProps = (tabView: View) => ({
    id: `admissions-tab-${tabView}`,
    'aria-controls': `admissions-panel-${tabView}`,
    'aria-selected': view === tabView,
    tabIndex: view === tabView ? 0 : -1,
    $active: view === tabView,
    ref: (element: HTMLButtonElement | null) => {
      tabRefs.current[tabView] = element;
    },
    onClick: () => setView(tabView),
    onKeyDown: (event: ReactKeyboardEvent<HTMLButtonElement>) => selectTabFromKeyboard(event, tabView),
  });

  if (!organizationId) return <Panel $accent="amber"><State role="alert"><div><ExclamationTriangleIcon /><h3>The admissions boundary is not ready</h3><p>CareSync will not load private application records until the signed-in identity and selected organization agree.</p></div></State></Panel>;

  return <Shell aria-label="Admissions decision workspace">
    <CommandBar $accent="cyan">
      <Tabs role="tablist" aria-label="Admissions workspace views">
        <Tab type="button" role="tab" {...tabProps('pipeline')}><ListBulletIcon /> Pipeline</Tab>
        <Tab type="button" role="tab" {...tabProps('waitlist')}><QueueListIcon /> Waitlist</Tab>
        {canManage && <Tab type="button" role="tab" {...tabProps('new')}><UserPlusIcon /> New application</Tab>}
      </Tabs>
      <Summary>
        <span>{scopedState.workspace ? `${total} applications · ${scopedState.workspace.waitlist_lane_count} waiting` : 'Loading canonical register'}</span>
        <ActionButton type="button" disabled={scopedState.status === 'loading'} onClick={() => void refreshCanonical().catch(() => undefined)}>{scopedState.status === 'loading' ? <Spinning /> : <ArrowPathIcon />} Refresh</ActionButton>
      </Summary>
    </CommandBar>

    {scopedState.message && <ErrorNotice role={scopedState.workspace ? 'status' : 'alert'}>{scopedState.workspace ? `The last confirmed register remains visible. ${scopedState.message}` : scopedState.message}</ErrorNotice>}

    {view === 'pipeline' && <TabPanel
      id="admissions-panel-pipeline"
      role="tabpanel"
      aria-labelledby="admissions-tab-pipeline"
      tabIndex={0}
    >{scopedState.status === 'loading' && !scopedState.workspace
      ? <Panel><State><div><Spinning /><h3>Loading the admissions register</h3><p>No locally invented application stages are shown while the canonical workspace loads.</p></div></State></Panel>
      : !scopedState.workspace
        ? <Panel><State role="alert"><div><ExclamationTriangleIcon /><h3>The decision register is unavailable</h3><p>{scopedState.message}</p><ActionButton type="button" onClick={() => void refreshCanonical().catch(() => undefined)}><ArrowPathIcon /> Retry</ActionButton></div></State></Panel>
        : <>
          <Pipeline aria-label="Admission application pipeline">
          {ADMISSION_STATUSES.map((laneStatus) => {
            const lane = scopedState.workspace!.lanes.find((item) => item.status === laneStatus);
            return <Lane key={laneStatus} $accent={laneStatus === 'offered' ? 'amber' : laneStatus === 'accepted' ? 'cyan' : 'plasma'}>
              <LaneHeader><h3>{statusLabel(laneStatus)}</h3><strong>{lane?.count ?? 0}</strong></LaneHeader>
              <LaneBody>
                {lane?.applications.length
                  ? lane.applications.map((application) => <ApplicationLink key={application.id} to={`/admissions/applications/${encodeURIComponent(application.id)}`}>
                    <strong>{application.reference}<ChevronRightIcon /></strong>
                    <span>{application.preference_count} {application.preference_count === 1 ? 'preference' : 'preferences'} · v{application.version}</span>
                    <span>Updated {formatTime(application.updated_at)}</span>
                  </ApplicationLink>)
                  : <EmptyLane>No application currently occupies this lane.</EmptyLane>}
                {(lane?.count || 0) > (lane?.applications.length || 0) && <EmptyLane>{(lane?.count || 0) - (lane?.applications.length || 0)} more in the canonical register</EmptyLane>}
              </LaneBody>
            </Lane>;
          })}
          </Pipeline>
          <Panel $accent="cyan" aria-label="Reachable admission application directory">
            <PanelHeader>
              <div><h2>Application register</h2><p>Every record remains reachable through server pagination. Search is restricted to the non-PII application reference.</p></div>
              <StatusChip $tone="info">{scopedState.applications?.total ?? 0} records</StatusChip>
            </PanelHeader>
            <DirectoryControls as="form" onSubmit={(event) => {
              event.preventDefault();
              setApplicationOffset(0);
              setSearch(searchDraft.trim());
            }}>
              <Field>
                Lifecycle lane
                <select value={selectedStatus} onChange={(event) => {
                  setSelectedStatus(event.target.value as AdmissionStatus | '');
                  setApplicationOffset(0);
                }}>
                  <option value="">Every lane</option>
                  {ADMISSION_STATUSES.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
                </select>
              </Field>
              <SearchField>
                Application reference
                <input
                  aria-label="Search by application reference"
                  maxLength={16}
                  pattern="[A-Za-z0-9-]+"
                  placeholder="ADM-…"
                  value={searchDraft}
                  onChange={(event) => setSearchDraft(event.target.value)}
                />
              </SearchField>
              <ActionButton type="submit"><ListBulletIcon /> Search</ActionButton>
              {(selectedStatus || search) && <ActionButton type="button" onClick={() => {
                setSelectedStatus('');
                setSearchDraft('');
                setSearch('');
                setApplicationOffset(0);
              }}>Clear</ActionButton>}
            </DirectoryControls>
            {!scopedState.applications?.items.length
              ? <State><div><CheckCircleIcon /><h3>No applications match</h3><p>Change the lifecycle lane or non-PII reference filter.</p></div></State>
              : <DirectoryList>
                {scopedState.applications.items.map((application) => <DirectoryRow key={application.id}>
                  <strong>{application.reference}</strong>
                  <span>{statusLabel(application.status)} · {application.preference_count} {application.preference_count === 1 ? 'preference' : 'preferences'} · updated {formatTime(application.updated_at)}</span>
                  <ActionButton as={Link} to={`/admissions/applications/${encodeURIComponent(application.id)}`}>Review <ChevronRightIcon /></ActionButton>
                </DirectoryRow>)}
              </DirectoryList>}
            {scopedState.applications && <PageControls>
              <span>Showing {scopedState.applications.total ? scopedState.applications.offset + 1 : 0}–{scopedState.applications.offset + scopedState.applications.items.length} of {scopedState.applications.total}</span>
              <div>
                <ActionButton type="button" disabled={scopedState.applications.offset === 0} onClick={() => setApplicationOffset((value) => Math.max(0, value - APPLICATION_PAGE_SIZE))}>Previous</ActionButton>
                <ActionButton type="button" disabled={scopedState.applications.offset + scopedState.applications.items.length >= scopedState.applications.total} onClick={() => setApplicationOffset((value) => value + APPLICATION_PAGE_SIZE)}>Next</ActionButton>
              </div>
            </PageControls>}
          </Panel>
        </>}
    </TabPanel>}

    {view === 'waitlist' && <TabPanel
      id="admissions-panel-waitlist"
      role="tabpanel"
      aria-labelledby="admissions-tab-waitlist"
      tabIndex={0}
    >
      <Panel $accent="amber">
        <PanelHeader><div><h2>Deterministic waitlist</h2><p>Position is server-owned and ordered by priority time, then immutable entry identity. Names and contact details stay inside the private application profile.</p></div><StatusChip $tone="info">{scopedState.waitlist?.total ?? 0} active records</StatusChip></PanelHeader>
        {scopedState.status === 'loading' && !scopedState.waitlist ? <State><div><Spinning /><h3>Loading waitlist</h3></div></State>
          : !scopedState.waitlist?.items.length ? <State><div><CheckCircleIcon /><h3>No waitlist entries</h3><p>The canonical waitlist has no records matching this organization.</p></div></State>
            : <>
              <Waitlist>
              {scopedState.waitlist.items.map((item) => <WaitlistRow key={item.entry_id}>
                <Position aria-label={`Position ${item.position}`}>{item.position}</Position>
                <strong>{item.application_reference}</strong>
                <span>{facilities.find((facility) => facility.id === item.facility_id)?.name ?? 'Current facility'} · {facilities.find((facility) => facility.id === item.facility_id)?.programs.find((program) => program.id === item.program_id)?.name ?? 'Current program'}<br />Requested {formatDate(item.desired_start_date)} · priority {formatTime(item.priority_at)}</span>
                <StatusChip $tone={item.status === 'active' ? 'info' : 'neutral'}>{statusLabel(item.status)}</StatusChip>
                <ActionButton as={Link} to={`/admissions/applications/${encodeURIComponent(item.application_id)}`}>Review <ChevronRightIcon /></ActionButton>
              </WaitlistRow>)}
              </Waitlist>
              <PageControls>
                <span>Showing {scopedState.waitlist.offset + 1}–{scopedState.waitlist.offset + scopedState.waitlist.items.length} of {scopedState.waitlist.total}</span>
                <div>
                  <ActionButton type="button" disabled={scopedState.waitlist.offset === 0} onClick={() => setWaitlistOffset((value) => Math.max(0, value - WAITLIST_PAGE_SIZE))}>Previous</ActionButton>
                  <ActionButton type="button" disabled={scopedState.waitlist.offset + scopedState.waitlist.items.length >= scopedState.waitlist.total} onClick={() => setWaitlistOffset((value) => value + WAITLIST_PAGE_SIZE)}>Next</ActionButton>
                </div>
              </PageControls>
            </>}
      </Panel>
    </TabPanel>}

    {view === 'new' && canManage && <TabPanel
      id="admissions-panel-new"
      role="tabpanel"
      aria-labelledby="admissions-tab-new"
      tabIndex={0}
    >
      <Panel $accent="cyan">
        <PanelHeader><div><Eyebrow><SparklesIcon width={14} /> Protected draft intake</Eyebrow><h2>Create an admission application</h2><p>This creates a versioned draft only. Submission and every later decision happen explicitly from the application profile.</p></div><ActionButton type="button" onClick={() => setView('pipeline')}><XMarkIcon /> Close</ActionButton></PanelHeader>
        <Form key={organizationId} onSubmit={submit} onChange={resetRetry}>
        <FormSection disabled={mutationLocked}>
          <legend>Child</legend>
          <Field>First name<input name="child_first_name" required maxLength={100} autoComplete="off" /></Field>
          <Field>Last name<input name="child_last_name" required maxLength={100} autoComplete="off" /></Field>
          <Field>Date of birth<input name="date_of_birth" type="date" required max={new Date().toISOString().slice(0, 10)} /></Field>
        </FormSection>
        <FormSection disabled={mutationLocked}>
          <legend>Primary family contact</legend>
          <Field>First name<input name="contact_first_name" required maxLength={100} autoComplete="given-name" /></Field>
          <Field>Last name<input name="contact_last_name" required maxLength={100} autoComplete="family-name" /></Field>
          <Field>Relationship<select name="relationship" required defaultValue=""><option value="" disabled>Choose relationship</option><option>Mother</option><option>Father</option><option>Parent</option><option>Legal guardian</option><option>Foster parent</option><option>Grandparent</option><option>Other caregiver</option></select></Field>
          <Field>Email<input name="email" type="email" maxLength={320} autoComplete="email" /></Field>
          <Field>Telephone<input name="telephone" type="tel" minLength={7} maxLength={30} autoComplete="tel" /></Field>
        </FormSection>
        <FormSection disabled={mutationLocked}>
          <legend>Placement preferences</legend>
          <div style={{ gridColumn: '1 / -1', display: 'grid', gap: 9 }}>
            {preferences.map((preference, index) => <Preference key={preference.key}>
              <Field>#{index + 1} facility<select required value={preference.facilityId} onChange={(event) => updatePreference(preference.key, { facilityId: event.target.value, programId: '' })}><option value="">Choose facility</option>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</select></Field>
              <Field>Program<select required disabled={!preference.facilityId || mutationLocked} value={preference.programId} onChange={(event) => updatePreference(preference.key, { programId: event.target.value })}><option value="">Choose program</option>{(facilities.find((facility) => facility.id === preference.facilityId)?.programs ?? []).map((program) => <option key={program.id} value={program.id}>{program.name} · {statusLabel(program.program_type)}</option>)}</select></Field>
              <Field>Requested start<input type="date" required value={preference.desiredStartDate} onChange={(event) => updatePreference(preference.key, { desiredStartDate: event.target.value })} /></Field>
              <ActionButton type="button" $variant="danger" disabled={preferences.length === 1} aria-label={`Remove preference ${index + 1}`} onClick={() => { resetRetry(); setPreferences((current) => current.filter((item) => item.key !== preference.key)); }}><XMarkIcon /></ActionButton>
            </Preference>)}
            <ActionButton type="button" disabled={preferences.length >= 5} onClick={() => { resetRetry(); setPreferences((current) => [...current, emptyPreference()]); }}><PlusIcon /> Add another preference</ActionButton>
          </div>
          <Field $wide>Internal note<textarea name="internal_note" maxLength={2000} placeholder="Private admissions context; never shown in pipeline or waitlist summaries." /></Field>
        </FormSection>
        {submitError && <ErrorNotice role="alert">{submitError}</ErrorNotice>}
        <FormActions>
          <span>{pendingOperationId ? 'The exact operation is retained until its saved outcome is resolved.' : 'The server owns reference numbers, versions, lifecycle status, and timeline evidence.'}</span>
          <ActionButton type="button" disabled={mutationLocked} onClick={() => setView('pipeline')}>Cancel</ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={mutationLocked || !facilities.length}>{submitting ? <Spinning /> : <ClipboardDocumentCheckIcon />} Create draft</ActionButton>
        </FormActions>
        </Form>
      </Panel>
    </TabPanel>}
  </Shell>;
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClipboardDocumentCheckIcon,
  ExclamationTriangleIcon,
  FunnelIcon,
  HomeModernIcon,
  LockClosedIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, hasExplicitPermission, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import type { ResourceState } from '../../hooks/useCommandData';
import { fetchEnrollmentFacilities, type EnrollmentFacilityOption } from '../children/childrenApi';
import BillingReadinessPanel from '../billing/BillingReadinessPanel';
import {
  fetchBillingReadiness,
  type BillingReadinessResponse,
} from '../billing/billingReadinessApi';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  ADMISSION_INTAKE_STAGES,
  fetchAdmissionIntakeQueue,
  type AdmissionIntakeQuery,
  type AdmissionIntakeQueue,
  type AdmissionIntakeStage,
} from './admissionsApi';
import {
  admissionCaseWho,
  admissionQueueWindow,
  admissionStageLabel,
  formatIntakeTimestamp,
  INTAKE_STAGE_PRESENTATION,
  lastAdmissionPageOffset,
  refreshAdmissionSources,
} from './admissionsModel';
import AdmissionsDecisionWorkspace from './AdmissionsDecisionWorkspace';

const PAGE_SIZE = 25;

const enter = keyframes`from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; }`;
const spin = keyframes`to { transform: rotate(360deg); }`;

const Page = styled.div`
  display: grid;
  gap: 18px;
  animation: ${enter} 420ms ${({ theme }) => theme.motion.ease} both;
`;

const Header = styled.header`
  display: flex;
  min-height: 92px;
  align-items: flex-end;
  justify-content: space-between;
  gap: 22px;
  h1 { margin: 9px 0 6px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 3vw, 2.45rem); font-weight: 500; letter-spacing: -.045em; line-height: 1.08; }
  p { max-width: 760px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .82rem; line-height: 1.65; }
  @media (max-width: 780px) { align-items: flex-start; flex-direction: column; }
`;

const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  @media (max-width: 780px) { justify-content: flex-start; }
`;

const ActionLink = styled(Link)<{ $primary?: boolean }>`
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 13px;
  border: 1px solid ${({ $primary, theme }) => $primary ? theme.color.cyan : theme.color.controlBorder};
  border-radius: 12px 5px 12px 5px;
  color: ${({ $primary, theme }) => $primary ? theme.color.ink : theme.color.text};
  background: ${({ $primary, theme }) => $primary ? theme.effect.primaryGradient : theme.color.surfaceStrong};
  box-shadow: ${({ $primary, theme }) => $primary ? theme.effect.primaryShadow : 'none'};
  font-size: .75rem;
  font-weight: 600;
  transition: transform ${({ theme }) => theme.motion.fast} ease, border-color ${({ theme }) => theme.motion.fast} ease;
  &:hover { transform: translateY(-1px); border-color: ${({ theme }) => theme.color.cyan}; }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 2px; }
  svg { width: 17px; }
`;

const TruthNotice = styled(GlassPanel)`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 13px;
  padding: 16px 18px;
  border-color: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 42%, ${({ theme }) => theme.color.border});
  background: linear-gradient(120deg, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 7%, transparent), transparent 62%), ${({ theme }) => theme.color.surfaceStrong};
  > svg { width: 22px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; font-size: .8rem; font-weight: 600; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .74rem; line-height: 1.58; }
`;

const MetricGrid = styled.section`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const Metric = styled(GlassPanel)<{ $tone: 'plasma' | 'cyan' | 'amber' }>`
  min-height: 116px;
  padding: 17px 19px;
  header { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  svg { width: 19px; color: ${({ $tone, theme }) => $tone === 'amber' ? theme.color.amber : $tone === 'cyan' ? theme.color.cyan : theme.color.plasmaBright}; }
  strong { display: block; margin-top: 17px; font-family: 'CareSync Display', sans-serif; font-size: 1.85rem; font-weight: 520; line-height: 1; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const Section = styled(GlassPanel)`overflow: hidden;`;
const SectionHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.08rem; font-weight: 540; letter-spacing: -.025em; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .74rem; line-height: 1.55; }
`;

const Lanes = styled.div`
  display: grid;
  grid-template-columns: repeat(6, minmax(128px, 1fr));
  overflow-x: auto;
  @media (max-width: 1000px) { grid-template-columns: repeat(3, minmax(180px, 1fr)); }
  @media (max-width: 600px) { grid-template-columns: 1fr 1fr; }
`;

const Lane = styled.button<{ $active: boolean; $attention: boolean }>`
  min-width: 0;
  min-height: 128px;
  padding: 16px;
  border: 0;
  border-right: 1px solid ${({ theme }) => theme.color.border};
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.text};
  background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.cyan} 11%, ${theme.color.surfaceStrong})` : theme.color.surfaceStrong};
  cursor: pointer;
  text-align: left;
  transition: background ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { background: ${({ theme }) => theme.color.surfaceHover}; transform: translateY(-1px); }
  &:focus-visible { position: relative; z-index: 1; outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: -3px; }
  span { display: block; color: ${({ $attention, theme }) => $attention ? theme.color.amber : theme.color.textMuted}; font-size: .67rem; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; }
  strong { display: block; margin: 12px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: 1.55rem; font-weight: 520; }
  small { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.42; }
`;

const Filters = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
`;

const Field = styled.label`
  display: grid;
  min-width: 220px;
  gap: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .69rem;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  select { min-height: 43px; padding: 0 34px 0 12px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; outline: none; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font-size: .75rem; text-transform: none; }
  select:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 14%, transparent); }
  @media (max-width: 560px) { width: 100%; min-width: 0; }
`;

const FilterNote = styled.p`
  flex: 1;
  min-width: 220px;
  margin: 0;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .7rem;
  line-height: 1.5;
`;

const QueueList = styled.ol`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const QueueItem = styled.li`
  display: grid;
  grid-template-columns: minmax(180px, .72fr) minmax(260px, 1.25fr) minmax(180px, .65fr);
  gap: 18px;
  padding: 18px 20px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.surfaceStrong};
  &:hover { background: ${({ theme }) => theme.color.surfaceHover}; }
  @media (max-width: 900px) { grid-template-columns: 1fr 1.3fr; > div:last-child { grid-column: 1 / -1; } }
  @media (max-width: 620px) { grid-template-columns: 1fr; > div:last-child { grid-column: auto; } }
`;

const Cell = styled.div`
  min-width: 0;
  h3 { margin: 8px 0 4px; font-size: .82rem; font-weight: 620; line-height: 1.35; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.52; }
  small { display: block; margin-top: 8px; color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; }
`;

const Reasons = styled.ul`
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
  li { padding-left: 11px; border-left: 2px solid ${({ theme }) => theme.color.amber}; }
  strong { display: block; font-size: .76rem; font-weight: 600; }
  span { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.48; }
`;

const Next = styled.div`
  display: grid;
  align-content: center;
  justify-items: start;
  gap: 8px;
  > span { color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
`;

const State = styled.div`
  display: grid;
  min-height: 220px;
  place-items: center;
  padding: 32px 20px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  text-align: center;
  div { max-width: 560px; }
  svg { width: 34px; margin: 0 auto 12px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0 0 7px; color: ${({ theme }) => theme.color.text}; font-family: 'CareSync Display', sans-serif; font-size: 1.12rem; font-weight: 540; }
  p { margin: 0; font-size: .74rem; line-height: 1.6; }
  button { margin-top: 16px; }
`;

const Spinning = styled(ArrowPathIcon)`animation: ${spin} 900ms linear infinite;`;

const QueueFooter = styled.footer`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 20px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .7rem;
  div { display: flex; gap: 8px; }
  @media (max-width: 560px) { align-items: stretch; flex-direction: column; }
`;

const RemediationHeading = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-top: 5px;
  h2 { margin: 7px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: 1.18rem; font-weight: 540; letter-spacing: -.03em; }
  p { max-width: 760px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.55; }
`;

type QueueState = {
  status: 'idle' | 'loading' | 'live' | 'empty' | 'error';
  data: AdmissionIntakeQueue | null;
  message?: string;
};

type FacilityState = {
  status: 'loading' | 'live' | 'error';
  data: EnrollmentFacilityOption[];
  message?: string;
};

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'The intake review could not be loaded.';
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function AdmissionsPage() {
  const session = useSession();
  const organizationId = session.status === 'authenticated'
    && session.user?.organization_id
    && session.user.organization_id === session.organization?.id
    && !session.organizationUnavailable
    ? session.user.organization_id
    : '';
  const canViewBilling = Boolean(
    (session.user?.role?.key === 'owner' || session.user?.role?.key === 'administrator')
    && hasExplicitPermission(session.user, ACCESS.billingRead),
  );
  const canViewLegacyRemediation = hasPermission(session.user, ACCESS.childcareRead);
  const [stageFilter, setStageFilter] = useState<AdmissionIntakeStage | ''>('');
  const [facilityId, setFacilityId] = useState('');
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState<QueueState>({ status: 'idle', data: null });
  const [facilities, setFacilities] = useState<FacilityState>({ status: 'loading', data: [] });
  const [billingReadiness, setBillingReadiness] = useState<ResourceState<BillingReadinessResponse>>({ status: 'idle', data: null });
  const previousOrganizationId = useRef(organizationId);
  const requestKey = `${organizationId}:${stageFilter || 'all'}:${facilityId || 'all'}:${offset}`;
  const activeRequestKey = useRef(requestKey);
  const activeOrganizationId = useRef(organizationId);
  const activeFacilityId = useRef(facilityId);
  activeRequestKey.current = requestKey;
  activeOrganizationId.current = organizationId;
  activeFacilityId.current = facilityId;
  const query = useMemo<AdmissionIntakeQuery>(() => ({
    stage: stageFilter || undefined,
    facilityId: facilityId || undefined,
    limit: PAGE_SIZE,
    offset,
  }), [facilityId, offset, stageFilter]);

  const loadQueue = useCallback(async (signal?: AbortSignal) => {
    if (!canViewLegacyRemediation || !organizationId) return;
    const key = requestKey;
    let data = await fetchAdmissionIntakeQueue(organizationId, query, signal);
    if (!signal?.aborted && data.offset > 0 && data.items.length === 0) {
      const correctedOffset = lastAdmissionPageOffset(data.total, data.limit);
      data = await fetchAdmissionIntakeQueue(organizationId, { ...query, offset: correctedOffset }, signal);
      if (!signal?.aborted && activeRequestKey.current === key) setOffset(correctedOffset);
    }
    if (!signal?.aborted && activeRequestKey.current === key) {
      setQueue({ status: data.total ? 'live' : 'empty', data });
    }
  }, [canViewLegacyRemediation, organizationId, query, requestKey]);

  useEffect(() => {
    if (previousOrganizationId.current === organizationId) return;
    previousOrganizationId.current = organizationId;
    setStageFilter('');
    setFacilityId('');
    setOffset(0);
  }, [organizationId]);

  const loadFacilities = useCallback(async (signal?: AbortSignal) => {
    if (!canViewLegacyRemediation || !organizationId) return;
    const expectedOrganizationId = organizationId;
    const data = await fetchEnrollmentFacilities(organizationId, signal, true);
    if (!signal?.aborted && activeOrganizationId.current === expectedOrganizationId) {
      setFacilities({ status: 'live', data });
      if (activeFacilityId.current && !data.some((facility) => facility.id === activeFacilityId.current)) {
        setFacilityId('');
        setOffset(0);
      }
    }
  }, [canViewLegacyRemediation, organizationId]);

  const loadBillingReadiness = useCallback(async (signal?: AbortSignal) => {
    if (!canViewBilling || !organizationId) return;
    const expectedOrganizationId = organizationId;
    const data = await fetchBillingReadiness(organizationId, signal);
    if (!signal?.aborted && activeOrganizationId.current === expectedOrganizationId) {
      setBillingReadiness({ status: data.counts.total ? 'live' : 'empty', data });
    }
  }, [canViewBilling, organizationId]);

  useEffect(() => {
    if (!canViewLegacyRemediation || !organizationId) {
      setQueue({ status: 'idle', data: null });
      return;
    }
    const controller = new AbortController();
    setQueue({ status: 'loading', data: null });
    loadQueue(controller.signal).catch((caught) => {
      if (!controller.signal.aborted && activeRequestKey.current === requestKey) setQueue({ status: 'error', data: null, message: errorMessage(caught) });
    });
    return () => controller.abort();
  }, [canViewLegacyRemediation, loadQueue, organizationId, requestKey]);

  useEffect(() => {
    if (!canViewLegacyRemediation || !organizationId) {
      setFacilities({ status: 'loading', data: [] });
      return;
    }
    const controller = new AbortController();
    setFacilities({ status: 'loading', data: [] });
    loadFacilities(controller.signal)
      .catch((caught) => { if (!controller.signal.aborted) setFacilities({ status: 'error', data: [], message: errorMessage(caught) }); });
    return () => controller.abort();
  }, [canViewLegacyRemediation, loadFacilities, organizationId]);

  useEffect(() => {
    if (!canViewBilling || !organizationId) {
      setBillingReadiness({ status: 'idle', data: null });
      return;
    }
    const controller = new AbortController();
    setBillingReadiness({ status: 'loading', data: null });
    loadBillingReadiness(controller.signal).catch((caught) => {
      if (!controller.signal.aborted) {
        setBillingReadiness({ status: 'error', data: null, message: errorMessage(caught) });
      }
    });
    return () => controller.abort();
  }, [canViewBilling, loadBillingReadiness, organizationId]);

  const refreshCanonical = useCallback(async () => {
    const [outcome, billingOutcome] = await Promise.all([
      canViewLegacyRemediation
        ? refreshAdmissionSources(() => loadQueue(), () => loadFacilities())
        : Promise.resolve({ queueError: null, facilityError: null }),
      canViewBilling
        ? loadBillingReadiness().then(() => null).catch((caught: unknown) => caught)
        : Promise.resolve(null),
    ]);
    if (outcome.queueError) {
      if (activeRequestKey.current === requestKey) setQueue((current) => current.data
        ? { ...current, message: `Refresh needs attention: ${errorMessage(outcome.queueError)}` }
        : { status: 'error', data: null, message: errorMessage(outcome.queueError) });
    } else setQueue((current) => current.data ? { ...current, message: undefined } : current);
    if (outcome.facilityError) {
      if (activeOrganizationId.current === organizationId) setFacilities((current) => current.data.length
        ? { ...current, message: `Facility refresh needs attention: ${errorMessage(outcome.facilityError)}` }
        : { status: 'error', data: [], message: errorMessage(outcome.facilityError) });
    } else setFacilities((current) => current.status === 'live' ? { ...current, message: undefined } : current);
    if (billingOutcome) {
      setBillingReadiness((current) => ({
        status: 'error',
        data: current.data,
        message: `Billing readiness refresh needs attention: ${errorMessage(billingOutcome)}`,
      }));
    }
    if (outcome.queueError || outcome.facilityError || billingOutcome) {
      throw (outcome.queueError || outcome.facilityError || billingOutcome);
    }
  }, [canViewBilling, canViewLegacyRemediation, loadBillingReadiness, loadFacilities, loadQueue, organizationId, requestKey]);

  useRealtimeRefresh({
    scope: 'admissions',
    organizationId,
    enabled: Boolean(organizationId),
    entityTypes: featureIntegrationManifest.admissions.realtimeEntities,
    refresh: refreshCanonical,
  });

  const data = queue.data;
  const window = data ? admissionQueueWindow(data) : null;
  const clearFilters = () => { setStageFilter(''); setFacilityId(''); setOffset(0); };
  const chooseStage = (value: AdmissionIntakeStage) => { setStageFilter((current) => current === value ? '' : value); setOffset(0); };

  return <Page>
    <Header>
      <div>
        <Eyebrow><ClipboardDocumentCheckIcon width={14} /> Command · admissions and intake</Eyebrow>
        <h1>From first inquiry to a safe enrollment.</h1>
        <p>Run the application pipeline, deterministic waitlist, offers, and conversion from versioned records—then resolve any older family or placement records that still need attention.</p>
      </div>
      <HeaderActions>
        <ActionLink to="/families"><UserGroupIcon /> Family directory</ActionLink>
        <ActionLink to="/children"><UsersIcon /> Child directory</ActionLink>
      </HeaderActions>
    </Header>

    <AdmissionsDecisionWorkspace />

    {canViewLegacyRemediation ? <>
    <RemediationHeading>
      <div><Eyebrow><HomeModernIcon width={14} /> Existing-record remediation</Eyebrow><h2>Resolve legacy family and placement signals</h2><p>This separate projection finds already-created family, child, enrollment, and room records that need a canonical correction. It does not invent an admissions decision.</p></div>
    </RemediationHeading>

    <TruthNotice $accent="cyan" role="note">
      <ShieldCheckIcon aria-hidden="true" />
      <div><strong>Read-only, record-derived remediation.</strong><p>{data?.notice || 'This section is not the application pipeline, waitlist, admissions decision, document-readiness check, or regulatory certification. A case disappearing means only that its current record signals are no longer returned.'}</p></div>
    </TruthNotice>

    {!organizationId ? <Section $accent="amber"><State role="alert"><div><LockClosedIcon /><h3>The admissions boundary is not ready</h3><p>CareSync will not request intake records until the authenticated identity and selected organization agree.</p></div></State></Section> : <>
      {canViewBilling && <BillingReadinessPanel status={billingReadiness.status} data={billingReadiness.data} message={billingReadiness.message} maximumItems={8} />}
      <MetricGrid aria-label="Filtered intake record counts">
        <Metric $accent="plasma" $tone="plasma"><header><span>Record attention</span><ClipboardDocumentCheckIcon /></header><strong>{data?.counts.total ?? '—'}</strong><p>Current family cases after the selected filters</p></Metric>
        <Metric $accent="amber" $tone="amber"><header><span>Critical conflicts</span><ExclamationTriangleIcon /></header><strong>{data?.counts.critical ?? '—'}</strong><p>Contradictory records that visually outrank contact attention</p></Metric>
        <Metric $accent="cyan" $tone="cyan"><header><span>Warning signals</span><ShieldCheckIcon /></header><strong>{data?.counts.warning ?? '—'}</strong><p>Current record attention, not compliance failures</p></Metric>
      </MetricGrid>

      <Section $accent="plasma" aria-labelledby="intake-lanes-title">
        <SectionHeader><div><h2 id="intake-lanes-title">Record-derived attention lanes</h2><p>These are current projections, not saved application stages. Choose a lane to filter the queue.</p></div>{stageFilter && <ActionButton type="button" onClick={() => { setStageFilter(''); setOffset(0); }}>Show every lane</ActionButton>}</SectionHeader>
        <Lanes>
          {ADMISSION_INTAKE_STAGES.map((stage) => <Lane key={stage} type="button" $active={stageFilter === stage} $attention={Boolean(data?.counts.by_stage[stage])} aria-pressed={stageFilter === stage} onClick={() => chooseStage(stage)}>
            <span>{admissionStageLabel(stage)}</span><strong>{data?.counts.by_stage[stage] ?? '—'}</strong><small>{INTAKE_STAGE_PRESENTATION[stage].short}</small>
          </Lane>)}
        </Lanes>
      </Section>

      <Section $accent="cyan" aria-labelledby="intake-queue-title" aria-busy={queue.status === 'loading'}>
        <SectionHeader><div><h2 id="intake-queue-title">Current intake review</h2><p>{data && window ? `Showing ${window.start}–${window.end} of ${data.total} current family cases · generated ${formatIntakeTimestamp(data.generated_at)}` : 'Loading the canonical organization projection.'}</p></div><StatusChip $tone={queue.status === 'error' || queue.message ? 'warning' : queue.status === 'loading' ? 'info' : 'success'}>{queue.status === 'loading' ? 'Refreshing' : queue.status === 'error' ? 'Unavailable' : queue.message ? 'Refresh attention' : 'Read-only projection'}</StatusChip></SectionHeader>
        <Filters aria-label="Intake review filters">
          <Field>Attention lane<select value={stageFilter} onChange={(event) => { setStageFilter(event.target.value as AdmissionIntakeStage | ''); setOffset(0); }}><option value="">All current lanes</option>{ADMISSION_INTAKE_STAGES.map((stage) => <option key={stage} value={stage}>{admissionStageLabel(stage)} · {INTAKE_STAGE_PRESENTATION[stage].short}</option>)}</select></Field>
          <Field>Facility<select value={facilityId} disabled={facilities.status !== 'live'} onChange={(event) => { setFacilityId(event.target.value); setOffset(0); }}><option value="">All facilities</option>{facilities.data.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}{facility.status !== 'active' ? ` · ${titleCase(facility.status)}` : ''}</option>)}</select></Field>
          {(stageFilter || facilityId) && <ActionButton type="button" onClick={clearFilters}><FunnelIcon /> Clear filters</ActionButton>}
          <FilterNote>{facilities.status === 'error' ? `Facility choices are unavailable; the unfiltered queue remains usable. ${facilities.message || ''}` : facilities.message || 'Filters are evaluated by the server before counts and pagination. Text search stays in the canonical family and child directories.'}</FilterNote>
        </Filters>

        {queue.message && data && <TruthNotice $accent="amber" role="status"><ExclamationTriangleIcon /><div><strong>The last good projection remains visible.</strong><p>{queue.message}</p></div></TruthNotice>}
        {queue.status === 'loading' ? <State><div><Spinning /><h3>Refreshing intake records</h3><p>No sample or locally inferred family cases are shown while the server projection loads.</p></div></State>
          : queue.status === 'error' ? <State role="alert"><div><ExclamationTriangleIcon /><h3>The intake review is unavailable</h3><p>{queue.message}</p><ActionButton type="button" onClick={() => void refreshCanonical().catch(() => undefined)}><ArrowPathIcon /> Retry canonical request</ActionButton></div></State>
            : !data || data.total === 0 ? <State><div><CheckCircleIcon /><h3>No current signals match</h3><p>This means only that the selected record-derived queue is empty. It does not certify an admission, finished intake, or regulatory result.</p>{(stageFilter || facilityId) && <ActionButton type="button" onClick={clearFilters}>Clear filters</ActionButton>}</div></State>
              : <>
                <QueueList aria-label="Families requiring intake record attention">
                  {data.items.map((item) => <QueueItem key={item.key}>
                    <Cell><StatusChip $tone={item.severity === 'critical' ? 'warning' : 'info'}>{item.severity === 'critical' ? 'Critical conflict' : admissionStageLabel(item.stage)}</StatusChip><h3>{admissionCaseWho(item)}</h3><p>Family status: {titleCase(item.family_status)} · {item.reasons.length} current {item.reasons.length === 1 ? 'signal' : 'signals'}</p><small>Updated {formatIntakeTimestamp(item.updated_at)}</small></Cell>
                    <Cell><Reasons>{item.reasons.map((reason) => <li key={`${reason.code}:${reason.entity_type}:${reason.entity_id}`}><strong>{reason.title}</strong><span>{reason.instruction}</span></li>)}</Reasons></Cell>
                    <Next><span>Next canonical action</span><ActionLink $primary to={item.primary_action.path}>{item.primary_action.label} <ChevronRightIcon /></ActionLink><ActionLink to={`/families/${encodeURIComponent(item.family_id)}`}>Open family profile</ActionLink></Next>
                  </QueueItem>)}
                </QueueList>
                {window && <QueueFooter><span>Page {window.page} of {window.pageCount}</span><div><ActionButton type="button" disabled={!window.canPrevious} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}><ChevronLeftIcon /> Previous</ActionButton><ActionButton type="button" disabled={!window.canNext} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Next <ChevronRightIcon /></ActionButton></div></QueueFooter>}
              </>}
      </Section>

      <TruthNotice $accent="plasma" role="note"><HomeModernIcon aria-hidden="true" /><div><strong>Canonical work stays where it belongs.</strong><p>Family and child edits, enrollment setup, and room-placement approval still re-fetch their own current record and preserve existing permission, version, and exact-command controls.</p></div></TruthNotice>
    </>}
    </> : <TruthNotice $accent="plasma" role="note"><LockClosedIcon aria-hidden="true" /><div><strong>Existing-record remediation is permission-bound.</strong><p>The admissions pipeline remains available, but legacy Family, Child, Enrollment, room, and billing projections require childcare:read.</p></div></TruthNotice>}
  </Page>;
}

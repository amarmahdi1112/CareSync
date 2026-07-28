import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  MapPinIcon,
  PencilSquareIcon,
  PhoneIcon,
  PlusIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UserIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, canAdministerFamilyAuthority, hasExplicitPermission, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import type { ResourceState } from '../../hooks/useCommandData';
import ChildAvatar from '../children/ChildAvatar';
import FamilyFinanceCard from '../billing/FamilyFinanceCard';
import {
  fetchFamilyFinanceSummary,
  type FamilyFinanceSummaryResponse,
} from '../billing/billingReadinessApi';
import FamilyDrawer from './FamilyDrawer';
import FamilyAuthorityWorkspace from './FamilyAuthorityWorkspace';
import { familyStatusReviewChildName, resolveFamilyIntakeStatusFocus, resolveFamilyStatusReview } from './familyStatusReview';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import { FamiliesApiError, fetchFamilyDetail } from './familiesApi';
import type { FamilyDetailRecord } from './types';

const reveal = keyframes`
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
`;

const Page = styled.div`
  display: grid;
  gap: 18px;
  animation: ${reveal} 320ms ${({ theme }) => theme.motion.ease} both;
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
  font-size: .78rem;
  font-weight: 600;
  transition: border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; transform: translateX(-2px); }
  svg { width: 17px; }
`;

const Hero = styled(GlassPanel)`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 22px;
  padding: clamp(20px, 3vw, 30px);
  background:
    radial-gradient(circle at 8% 16%, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 14%, transparent), transparent 28%),
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};

  @media (max-width: 760px) { grid-template-columns: auto 1fr; }
  @media (max-width: 540px) { grid-template-columns: 1fr; }
`;

const FamilyMark = styled.div`
  position: relative;
  display: grid;
  width: clamp(84px, 11vw, 112px);
  aspect-ratio: 1;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.plasmaBright};
  border-radius: 30px 10px 30px 10px;
  color: ${({ theme }) => theme.color.plasmaBright};
  background: linear-gradient(145deg, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 19%, ${({ theme }) => theme.color.surfaceStrong}), ${({ theme }) => theme.color.surfaceStrong});
  box-shadow: ${({ theme }) => theme.shadow.glow};
  &::after { position: absolute; inset: 8px; border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.cyan} 20%, transparent); border-radius: 23px 7px 23px 7px; content: ''; }
  svg { width: 44%; }
`;

const HeroCopy = styled.div`
  min-width: 0;
  h1 { margin: 10px 0 7px; overflow-wrap: anywhere; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 4vw, 3rem); font-weight: 520; letter-spacing: -.055em; line-height: 1; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .8rem; line-height: 1.65; }
`;

const HeroMeta = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
`;

const HeroActions = styled.div`
  display: grid;
  justify-items: stretch;
  gap: 9px;
  @media (max-width: 760px) { grid-column: 1 / -1; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 540px) { grid-template-columns: 1fr; }
`;

const ActionLink = styled(Link)<{ $primary?: boolean }>`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid ${({ $primary, theme }) => $primary ? theme.color.plasmaBright : theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  color: ${({ $primary, theme }) => $primary ? theme.color.ink : theme.color.text};
  background: ${({ $primary, theme }) => $primary ? theme.effect.primaryGradient : theme.color.control};
  box-shadow: ${({ $primary, theme }) => $primary ? theme.effect.primaryShadow : 'none'};
  font-size: .8rem;
  font-weight: 600;
  svg { width: 18px; }
`;

const Metrics = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 880px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 480px) { grid-template-columns: 1fr; }
`;

const Metric = styled(GlassPanel)`
  padding: 16px;
  span { display: flex; align-items: center; gap: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  span svg { width: 17px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; margin-top: 12px; font-family: 'CareSync Display', sans-serif; font-size: 1.75rem; font-weight: 520; letter-spacing: -.05em; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const Layout = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, .75fr);
  gap: 14px;
  align-items: start;
  @media (max-width: 980px) { grid-template-columns: 1fr; }
`;

const Column = styled.div`display: grid; gap: 14px;`;

const Section = styled(GlassPanel)`
  padding: 19px;
`;

const SectionHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.08rem; font-weight: 550; letter-spacing: -.03em; }
  p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.5; }
  > svg { width: 21px; color: ${({ theme }) => theme.color.cyan}; }
`;

const RecordList = styled.div`display: grid; gap: 9px;`;

const Person = styled.div`
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px 5px 13px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  > svg { width: 20px; margin: 0 auto; color: ${({ theme }) => theme.color.plasmaBright}; }
  strong { display: block; font-size: .8rem; font-weight: 600; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .71rem; line-height: 1.5; }
  @media (max-width: 520px) { grid-template-columns: 36px minmax(0, 1fr); > span { grid-column: 2; width: fit-content; } }
`;

const ContactActions = styled.div`
  display: flex;
  gap: 6px;
  a { display: grid; width: 36px; height: 36px; place-items: center; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 10px 4px 10px 4px; color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.control}; }
  svg { width: 16px; }
`;

const ChildLink = styled(Link)`
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px 6px 14px 6px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  transition: border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; transform: translateX(2px); }
  strong { display: block; font-size: .82rem; font-weight: 600; }
  small { display: block; margin-top: 4px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
  > svg { width: 18px; color: ${({ theme }) => theme.color.cyan}; transform: rotate(180deg); }
`;

const ConsentGrid = styled.div`
  display: grid;
  gap: 8px;
  div { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 11px 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 11px 5px 11px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; }
  svg { width: 17px; color: ${({ theme }) => theme.color.mint}; }
`;

const Notes = styled.p`
  margin: 0;
  white-space: pre-wrap;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .77rem;
  line-height: 1.72;
`;

const Empty = styled.div`
  padding: 18px;
  border: 1px dashed ${({ theme }) => theme.color.controlBorder};
  border-radius: 13px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .75rem;
  line-height: 1.6;
  text-align: center;
`;

const State = styled(GlassPanel)`
  display: grid;
  min-height: 440px;
  place-items: center;
  padding: 34px;
  text-align: center;
  div { max-width: 520px; }
  svg { width: 42px; margin: 0 auto 14px; color: ${({ theme }) => theme.color.cyan}; }
  h1 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.45rem; font-weight: 550; }
  p { margin: 0 0 18px; color: ${({ theme }) => theme.color.textMuted}; font-size: .77rem; line-height: 1.7; }
`;

const Notice = styled.div`
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 13px;
  border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.mint} 46%, ${({ theme }) => theme.color.border});
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: color-mix(in srgb, ${({ theme }) => theme.color.mint} 8%, ${({ theme }) => theme.color.surfaceStrong});
  font-size: .75rem;
  svg { width: 17px; color: ${({ theme }) => theme.color.mint}; }
`;

const ReviewCallout = styled(GlassPanel)<{ $resolved?: boolean }>`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 14px;
  padding: 18px;
  border-color: ${({ $resolved, theme }) => $resolved ? theme.color.mint : theme.color.amber};
  background:
    linear-gradient(120deg, color-mix(in srgb, ${({ $resolved, theme }) => $resolved ? theme.color.mint : theme.color.amber} 10%, transparent), transparent 55%),
    ${({ theme }) => theme.color.surface};
  > svg { width: 24px; color: ${({ $resolved, theme }) => $resolved ? theme.color.mint : theme.color.amber}; }
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; font-weight: 560; letter-spacing: -.025em; }
  p { margin: 6px 0 0; color: ${({ theme }) => theme.color.textSoft}; font-size: .76rem; line-height: 1.62; }
`;

const ReviewSteps = styled.ol`
  display: grid;
  gap: 6px;
  margin: 13px 0 0;
  padding-left: 19px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .73rem;
  line-height: 1.55;
  strong { color: ${({ theme }) => theme.color.text}; font-weight: 600; }
`;

const ReviewActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  > span { color: ${({ theme }) => theme.color.amber}; font-size: .72rem; line-height: 1.5; }
`;

const ReviewIdentifier = styled.small`
  display: block;
  margin-top: 9px;
  color: ${({ theme }) => theme.color.textMuted};
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .64rem;
  overflow-wrap: anywhere;
`;

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleDateString('en-CA', { day: 'numeric', month: 'short', year: 'numeric' });
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

export default function FamilyProfilePage() {
  const { familyId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = useSession();
  const organizationId = session.user?.organization_id || null;
  const canManage = hasPermission(session.user, ACCESS.childcareManage);
  const canManageAuthority = canAdministerFamilyAuthority(session.user);
  const canViewBilling = Boolean(
    (session.user?.role?.key === 'owner' || session.user?.role?.key === 'administrator')
    && hasExplicitPermission(session.user, ACCESS.billingRead),
  );
  const [detail, setDetail] = useState<FamilyDetailRecord | null>(null);
  const [finance, setFinance] = useState<ResourceState<FamilyFinanceSummaryResponse>>({ status: 'idle', data: null });
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');

  const loadProfile = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId || !familyId || (session.organization?.id && session.organization.id !== organizationId)) throw new Error('The authenticated organization boundary could not be confirmed for this family.');
    const record = await fetchFamilyDetail(familyId, organizationId, signal);
    if (!signal?.aborted) { setDetail(record); setPhase('ready'); setError(''); }
  }, [familyId, organizationId, session.organization?.id]);

  const loadFinance = useCallback(async (signal?: AbortSignal) => {
    if (!canViewBilling || !organizationId || !familyId) return;
    const record = await fetchFamilyFinanceSummary(organizationId, familyId, signal);
    if (!signal?.aborted) setFinance({ status: 'live', data: record });
  }, [canViewBilling, familyId, organizationId]);

  useRealtimeRefresh({ scope: 'family-profile', organizationId: organizationId || '', enabled: Boolean(familyId), entityTypes: featureIntegrationManifest.families.realtimeEntities, refresh: async () => loadProfile() });
  useRealtimeRefresh({ scope: 'family-profile-finance', organizationId: organizationId || '', enabled: Boolean(familyId && canViewBilling), entityTypes: featureIntegrationManifest.families.realtimeEntities, refresh: async () => loadFinance() });

  useEffect(() => {
    if (!organizationId || !familyId || (session.organization?.id && session.organization.id !== organizationId)) {
      setPhase('error');
      setError('The authenticated organization boundary could not be confirmed for this family.');
      return;
    }
    const controller = new AbortController();
    setPhase('loading');
    setError('');
    loadProfile(controller.signal)
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setDetail(null);
        setError(caught instanceof FamiliesApiError ? caught.message : caught instanceof Error ? caught.message : 'The family profile could not be loaded.');
        setPhase('error');
      });
    return () => controller.abort();
  }, [familyId, loadProfile, organizationId, revision, session.organization?.id]);

  useEffect(() => {
    if (!canViewBilling || !organizationId || !familyId) {
      setFinance({ status: 'idle', data: null });
      return;
    }
    const controller = new AbortController();
    setFinance({ status: 'loading', data: null });
    loadFinance(controller.signal).catch((caught: unknown) => {
      if (!controller.signal.aborted) {
        setFinance({
          status: 'error',
          data: null,
          message: caught instanceof Error ? caught.message : 'Family finance is unavailable.',
        });
      }
    });
    return () => controller.abort();
  }, [canViewBilling, familyId, loadFinance, organizationId, revision]);

  const activeChildren = useMemo(() => detail?.children.filter((child) => child.is_active).length || 0, [detail]);
  const pickupPeople = useMemo(() => detail
    ? [...detail.guardians, ...detail.emergency_contacts].filter((person) => person.authorized_pickup).length
    : 0, [detail]);
  const statusReview = useMemo(
    () => detail && resolveFamilyIntakeStatusFocus(searchParams, detail) === 'none' ? resolveFamilyStatusReview(searchParams, detail) : null,
    [detail, searchParams],
  );
  const intakeStatusFocus = useMemo(
    () => detail ? resolveFamilyIntakeStatusFocus(searchParams, detail) : 'none',
    [detail, searchParams],
  );

  const dismissStatusReview = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('focus');
    next.delete('child_id');
    next.delete('enrollment_id');
    setSearchParams(next, { replace: true });
  };

  if (phase !== 'ready' || !detail) {
    return <Page><BackLink to="/families"><ArrowLeftIcon /> Back to families</BackLink><State $accent={phase === 'error' ? 'amber' : 'cyan'}><div>{phase === 'loading' ? <ArrowPathIcon /> : <ExclamationTriangleIcon />}<h1>{phase === 'loading' ? 'Loading the family profile' : 'This family profile could not open'}</h1><p>{phase === 'loading' ? 'CareSync is loading the household, care network, children, and legacy profile markers.' : error}</p>{phase === 'error' && <ActionButton type="button" onClick={() => setRevision((value) => value + 1)}><ArrowPathIcon /> Try again</ActionButton>}</div></State></Page>;
  }

  return <Page>
    <BackLink to="/families"><ArrowLeftIcon /> Back to families</BackLink>
    {notice && <Notice role="status"><CheckCircleIcon /> {notice}</Notice>}
    {intakeStatusFocus === 'available' && <ReviewCallout $accent="amber" role="alert" aria-labelledby="family-intake-status-title">
      <ExclamationTriangleIcon aria-hidden="true" />
      <div>
        <h2 id="family-intake-status-title">Review {detail.name}'s family status</h2>
        <p>This family is currently {titleCase(detail.status)}. That is an operational record status, not an admissions decision or certification.</p>
        <ReviewSteps>
          <li><strong>Who:</strong> {detail.name}.</li>
          <li><strong>What:</strong> the record-derived intake queue requested a manual family-status review.</li>
          <li><strong>Next action:</strong> inspect the current family and related child records, then make the appropriate operator decision in the existing editor.</li>
        </ReviewSteps>
        <ReviewActions>
          {canManage && <ActionButton type="button" $variant="primary" onClick={() => setEditing(true)}><PencilSquareIcon /> Review family status</ActionButton>}
          {!canManage && <span>Ask an owner or administrator with childcare-management access to review this status.</span>}
          <ActionButton type="button" onClick={dismissStatusReview}>Clear intake focus</ActionButton>
        </ReviewActions>
      </div>
    </ReviewCallout>}
    {(intakeStatusFocus === 'invalid' || intakeStatusFocus === 'stale') && <ReviewCallout $accent="amber" role="alert">
      <ExclamationTriangleIcon aria-hidden="true" />
      <div><h2>This intake focus is no longer current</h2><p>The canonical family record no longer matches this narrow review link. Return to Admissions & intake for the latest server-derived action.</p><ReviewActions><ActionLink to="/admissions">Open Admissions & intake</ActionLink><ActionButton type="button" onClick={dismissStatusReview}>Clear this focus</ActionButton></ReviewActions></div>
    </ReviewCallout>}
    {statusReview?.status === 'available' && (() => {
      const childName = familyStatusReviewChildName(statusReview.child);
      const resolved = detail.status === 'active';
      return <ReviewCallout $accent={resolved ? 'cyan' : 'amber'} $resolved={resolved} role={resolved ? 'status' : 'alert'} aria-labelledby="family-status-review-title">
        {resolved ? <CheckCircleIcon aria-hidden="true" /> : <ExclamationTriangleIcon aria-hidden="true" />}
        <div>
          <h2 id="family-status-review-title">{resolved ? `${childName}'s family-status blocker is resolved` : `Resolve ${childName}'s enrollment blocker`}</h2>
          <p>{resolved
            ? `${detail.name} is Active now. The dashboard readiness signal will clear after its canonical refresh.`
            : `${detail.name} is ${titleCase(detail.status)} while ${childName} has an open enrollment. CareSync requires the linked family to be Active before that enrollment can be treated as operational.`}</p>
          {!resolved && <ReviewSteps>
            <li><strong>Who:</strong> {childName}, linked to {detail.name}.</li>
            <li><strong>What:</strong> the family status—not the child's saved room—is blocking the enrollment.</li>
            <li><strong>Action:</strong> review the current family and child records, then choose whether Active accurately reflects the operator's decision. If care should not continue, open the child record and end the enrollment instead.</li>
          </ReviewSteps>}
          <ReviewIdentifier>Exact enrollment: {statusReview.enrollmentId}</ReviewIdentifier>
          <ReviewActions>
            {!resolved && canManage && <ActionButton type="button" $variant="primary" onClick={() => setEditing(true)}><PencilSquareIcon /> Edit family status</ActionButton>}
            {!resolved && !canManage && <span>Ask an owner or administrator with childcare-management access to change this status.</span>}
            <ActionLink to={`/children/${encodeURIComponent(statusReview.child.id)}`}><UsersIcon /> Open {statusReview.child.first_name}'s enrollment</ActionLink>
            <ActionButton type="button" onClick={dismissStatusReview}>{resolved ? 'Done' : 'Dismiss focus'}</ActionButton>
          </ReviewActions>
        </div>
      </ReviewCallout>;
    })()}
    {(statusReview?.status === 'invalid' || statusReview?.status === 'stale') && <ReviewCallout $accent="amber" role="alert">
      <ExclamationTriangleIcon aria-hidden="true" />
      <div><h2>This family review link is no longer current</h2><p>Return to Record readiness for the latest organization-scoped action. CareSync will not guess which child or enrollment you intended.</p><ReviewActions><ActionLink to="/dashboard">Open Record readiness</ActionLink><ActionButton type="button" onClick={dismissStatusReview}>Clear this focus</ActionButton></ReviewActions></div>
    </ReviewCallout>}
    <Hero $accent="plasma">
      <FamilyMark><UserGroupIcon /></FamilyMark>
      <HeroCopy>
        <Eyebrow><IdentificationIcon width={14} /> Complete family profile</Eyebrow>
        <h1>{detail.name}</h1>
        <p>{detail.file_number ? `Internal file ${detail.file_number}` : 'No internal file number'} · Registered {dateLabel(detail.created_at)}</p>
        <HeroMeta><StatusChip $tone={detail.status === 'active' ? 'success' : detail.status === 'pending' ? 'warning' : 'neutral'}>{titleCase(detail.status)}</StatusChip><StatusChip $tone="info">{detail.children.length} linked {detail.children.length === 1 ? 'child' : 'children'}</StatusChip></HeroMeta>
      </HeroCopy>
      <HeroActions>
        {canManage && <ActionButton type="button" $variant="primary" onClick={() => setEditing(true)}><PencilSquareIcon /> Edit family</ActionButton>}
        {canManage && <ActionLink to={`/children?family=${encodeURIComponent(detail.id)}`}><PlusIcon /> Add child</ActionLink>}
      </HeroActions>
    </Hero>

    <Metrics aria-label="Family profile summary">
      <Metric $accent="plasma"><span><UsersIcon /> Children</span><strong>{detail.children.length}</strong><small>{activeChildren} active records</small></Metric>
      <Metric $accent="cyan"><span><UserGroupIcon /> Guardians</span><strong>{detail.guardians.length}</strong><small>Linked household contacts</small></Metric>
      <Metric $accent="cyan"><span><PhoneIcon /> Emergency</span><strong>{detail.emergency_contacts.length}</strong><small>Emergency contacts</small></Metric>
      <Metric $accent="plasma"><span><ShieldCheckIcon /> Legacy pickup</span><strong>{pickupPeople}</strong><small>Affirmative legacy markers</small></Metric>
    </Metrics>

    {canManageAuthority && organizationId && <FamilyAuthorityWorkspace family={detail} organizationId={organizationId} />}
    {canViewBilling && <FamilyFinanceCard status={finance.status} data={finance.data} message={finance.message} />}

    <Layout>
      <Column>
        <Section $accent="plasma">
          <SectionHeader><div><h2>Children</h2><p>Each child opens as a complete, addressable profile.</p></div><UsersIcon /></SectionHeader>
          <RecordList>{detail.children.length ? detail.children.map((child) => <ChildLink key={child.id} to={`/children/${encodeURIComponent(child.id)}`}><ChildAvatar firstName={child.first_name} lastName={child.last_name} photoUrl={child.profile_photo_url} photoUpdatedAt={child.profile_photo_updated_at} size={48} /><div><strong>{child.first_name} {child.middle_name ? `${child.middle_name} ` : ''}{child.last_name}</strong><small>{child.age_group || 'Age group not recorded'} · {child.is_active ? 'Active record' : 'Archived record'}</small></div><ArrowLeftIcon /></ChildLink>) : <Empty>No children are linked to this family yet.</Empty>}</RecordList>
        </Section>

        <Section $accent="cyan">
          <SectionHeader><div><h2>Guardians</h2><p>Household contacts; pickup values are legacy markers, not verified authority.</p></div><UserGroupIcon /></SectionHeader>
          <RecordList>{detail.guardians.length ? detail.guardians.map((guardian) => <Person key={guardian.id}><UserIcon /><div><strong>{guardian.first_name} {guardian.last_name}</strong><small>{guardian.relationship || titleCase(guardian.guardian_type)}{guardian.address ? ` · ${guardian.address}${guardian.city ? `, ${guardian.city}` : ''}` : ''}</small></div><ContactActions>{guardian.cell_phone && <a href={`tel:${guardian.cell_phone}`} aria-label={`Call ${guardian.first_name}`}><PhoneIcon /></a>}{guardian.email && <a href={`mailto:${guardian.email}`} aria-label={`Email ${guardian.first_name}`}><EnvelopeIcon /></a>}</ContactActions></Person>) : <Empty>No guardians are recorded for this family.</Empty>}</RecordList>
        </Section>

        <Section $accent="plasma">
          <SectionHeader><div><h2>Emergency contacts</h2><p>People to contact when guardians cannot be reached.</p></div><PhoneIcon /></SectionHeader>
          <RecordList>{detail.emergency_contacts.length ? detail.emergency_contacts.map((contact) => <Person key={contact.id}><ShieldCheckIcon /><div><strong>{contact.first_name} {contact.last_name}</strong><small>{contact.relationship} · {contact.authorized_pickup ? 'Legacy pickup marker: yes' : 'No affirmative pickup marker recorded'}</small></div><ContactActions>{contact.cell_phone && <a href={`tel:${contact.cell_phone}`} aria-label={`Call ${contact.first_name}`}><PhoneIcon /></a>}</ContactActions></Person>) : <Empty>No emergency contacts are recorded.</Empty>}</RecordList>
        </Section>
      </Column>

      <Column>
        <Section $accent="cyan">
          <SectionHeader><div><h2>Legacy profile markers</h2><p>Imported yes/no markers only—not consent evidence or denial. Review versioned consent and release authority in the protected workspace above.</p></div><CheckCircleIcon /></SectionHeader>
          <ConsentGrid>
            <div><span>Photo</span><StatusChip $tone={detail.photo_consent ? 'info' : 'neutral'}>{detail.photo_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
            <div><span>Field trip</span><StatusChip $tone={detail.field_trip_consent ? 'info' : 'neutral'}>{detail.field_trip_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
            <div><span>Emergency medical</span><StatusChip $tone={detail.emergency_medical_consent ? 'info' : 'neutral'}>{detail.emergency_medical_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
          </ConsentGrid>
        </Section>

        <Section $accent="plasma">
          <SectionHeader><div><h2>Family notes</h2><p>Household-level context.</p></div><IdentificationIcon /></SectionHeader>
          <Notes>{detail.additional_notes || 'No family notes have been recorded.'}</Notes>
        </Section>

        <Section $accent="cyan">
          <SectionHeader><div><h2>Record details</h2><p>Stable database identity and history.</p></div><CalendarDaysIcon /></SectionHeader>
          <ConsentGrid>
            <div><span>Created</span><strong>{dateLabel(detail.created_at)}</strong></div>
            <div><span>Last updated</span><strong>{dateLabel(detail.updated_at)}</strong></div>
            <div><span>File number</span><strong>{detail.file_number || 'Not recorded'}</strong></div>
          </ConsentGrid>
        </Section>

        {detail.guardians.some((guardian) => guardian.address) && <Section $accent="plasma"><SectionHeader><div><h2>Household location</h2><p>Address from the primary saved guardian.</p></div><MapPinIcon /></SectionHeader><Notes>{(() => { const guardian = detail.guardians.find((item) => item.address); return [guardian?.address, guardian?.city, guardian?.postal_code].filter(Boolean).join(', '); })()}</Notes></Section>}
      </Column>
    </Layout>

    {editing && organizationId && <FamilyDrawer request={{ mode: 'edit', familyId: detail.id }} organizationId={organizationId} onClose={() => setEditing(false)} onSaved={(message) => { setEditing(false); setNotice(message); setRevision((value) => value + 1); }} />}
  </Page>;
}

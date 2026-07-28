import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CalendarDaysIcon,
  CameraIcon,
  CheckCircleIcon,
  ClockIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  HeartIcon,
  HomeModernIcon,
  IdentificationIcon,
  MapPinIcon,
  PencilSquareIcon,
  PhoneIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserGroupIcon,
  UserIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, canAdministerFamilyAuthority, hasExplicitPermission, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import type { ResourceState } from '../../hooks/useCommandData';
import ChildFinanceCard from '../billing/ChildFinanceCard';
import FamilyFinanceCard from '../billing/FamilyFinanceCard';
import {
  fetchFamilyFinanceSummary,
  type FamilyFinanceSummaryResponse,
} from '../billing/billingReadinessApi';
import ChildEditor from './ChildEditor';
import ChildAuthoritySummaryPanel from './ChildAuthoritySummaryPanel';
import EnrollmentEditor from './EnrollmentEditor';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  ChildrenApiError,
  deleteChildPhoto,
  fetchChildPhoto,
  fetchChildProfile,
  uploadChildPhoto,
  type ApiChildProfile,
} from './childrenApi';
import { childListIdentityFromProfile } from './childrenModel';
import { parseChildAuthorityRouteFocus } from './childAuthorityFocus';

const MAX_PHOTO_BYTES = 6 * 1024 * 1024;
const ACCEPTED_PHOTO_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

const appear = keyframes`
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
`;

const pulse = keyframes`
  0%, 100% { opacity: .38; }
  50% { opacity: .8; }
`;

const Page = styled.div`
  display: grid;
  gap: 18px;
  animation: ${appear} 320ms ${({ theme }) => theme.motion.ease} both;
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
  grid-template-columns: minmax(190px, 230px) minmax(0, 1fr);
  gap: clamp(22px, 4vw, 38px);
  padding: clamp(20px, 3vw, 32px);
  background:
    radial-gradient(circle at 9% 14%, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 13%, transparent), transparent 28%),
    radial-gradient(circle at 74% 4%, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 10%, transparent), transparent 34%),
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const PhotoColumn = styled.div`display: grid; align-content: start; gap: 10px;`;

const PhotoSurface = styled.div`
  position: relative;
  display: grid;
  width: 100%;
  max-width: 230px;
  aspect-ratio: 4 / 5;
  place-items: center;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 32px 10px 32px 10px;
  color: ${({ theme }) => theme.color.cyan};
  background:
    linear-gradient(145deg, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 12%, ${({ theme }) => theme.color.surfaceStrong}), color-mix(in srgb, ${({ theme }) => theme.color.plasma} 10%, ${({ theme }) => theme.color.surfaceStrong}));
  box-shadow: ${({ theme }) => theme.shadow.cyan};
  &::after { position: absolute; inset: 9px; border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 18%, transparent); border-radius: 25px 7px 25px 7px; content: ''; pointer-events: none; }
  img { width: 100%; height: 100%; object-fit: cover; }
  > strong { font-family: 'CareSync Display', sans-serif; font-size: clamp(2rem, 6vw, 3.5rem); font-weight: 520; letter-spacing: -.04em; }
  @media (max-width: 760px) { max-width: 190px; }
`;

const PhotoLoading = styled.div`
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  animation: ${pulse} 1.2s ease-in-out infinite;
  svg { width: 34px; }
`;

const PhotoActions = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  max-width: 230px;
  input { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
`;

const PhotoHint = styled.p`
  max-width: 230px;
  margin: 0;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .68rem;
  line-height: 1.55;
`;

const HeroContent = styled.div`display: grid; min-width: 0; align-content: space-between; gap: 24px;`;

const HeroHeading = styled.div`
  h1 { margin: 11px 0 7px; overflow-wrap: anywhere; font-family: 'CareSync Display', sans-serif; font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 520; letter-spacing: -.06em; line-height: .98; }
  > p { max-width: 740px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .82rem; line-height: 1.65; }
`;

const Chips = styled.div`display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px;`;

const HeroActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
`;

const FamilyLink = styled(Link)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 13px;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 15px 6px 15px 6px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  transition: border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.plasmaBright}; transform: translateY(-1px); }
  > div { display: flex; min-width: 0; align-items: center; gap: 11px; }
  > div > svg { width: 24px; flex: 0 0 auto; color: ${({ theme }) => theme.color.plasmaBright}; }
  strong { display: block; font-size: .82rem; font-weight: 600; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; }
  > svg { width: 17px; color: ${({ theme }) => theme.color.cyan}; transform: rotate(180deg); }
`;

const Metrics = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 900px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 480px) { grid-template-columns: 1fr; }
`;

const Metric = styled(GlassPanel)`
  padding: 16px;
  span { display: flex; align-items: center; gap: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  svg { width: 17px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; margin-top: 11px; font-family: 'CareSync Display', sans-serif; font-size: 1.35rem; font-weight: 530; letter-spacing: -.035em; line-height: 1.2; }
  small { display: block; margin-top: 4px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.45; }
`;

const Layout = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(310px, .8fr);
  gap: 14px;
  align-items: start;
  @media (max-width: 1020px) { grid-template-columns: 1fr; }
`;

const FinanceGrid = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(300px, .8fr);
  gap: 14px;
  align-items: stretch;
  @media (max-width: 980px) { grid-template-columns: 1fr; }
`;

const Column = styled.div`display: grid; gap: 14px;`;
const Section = styled(GlassPanel)`padding: 19px;`;

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

const FactGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin: 0;
  div { padding: 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; }
  dt { color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; }
  dd { margin: 5px 0 0; color: ${({ theme }) => theme.color.textSoft}; font-size: .77rem; line-height: 1.55; overflow-wrap: anywhere; }
  @media (max-width: 560px) { grid-template-columns: 1fr; }
`;

const EnrollmentList = styled.div`display: grid; gap: 9px;`;

const EnrollmentCard = styled.div<{ $current?: boolean }>`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 13px;
  border: 1px solid ${({ $current, theme }) => $current ? theme.color.cyan : theme.color.border};
  border-radius: 14px 6px 14px 6px;
  background: ${({ $current, theme }) => $current ? `color-mix(in srgb, ${theme.color.cyan} 7%, ${theme.color.surfaceStrong})` : theme.color.surfaceStrong};
  > svg { width: 23px; color: ${({ $current, theme }) => $current ? theme.color.cyan : theme.color.textMuted}; }
  strong { display: block; font-size: .8rem; font-weight: 600; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.5; }
  @media (max-width: 560px) { grid-template-columns: auto 1fr; > span { grid-column: 2; width: fit-content; } }
`;

const PersonList = styled.div`display: grid; gap: 8px;`;

const Person = styled.div`
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  > svg { width: 19px; margin: 0 auto; color: ${({ theme }) => theme.color.plasmaBright}; }
  strong { display: block; font-size: .78rem; font-weight: 600; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.45; }
  > div:last-child { display: flex; gap: 5px; }
  a { display: grid; width: 34px; height: 34px; place-items: center; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 9px 4px 9px 4px; color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.control}; }
  a svg { width: 15px; }
`;

const ConsentList = styled.div`
  display: grid;
  gap: 8px;
  div { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 11px 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 11px 5px 11px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; color: ${({ theme }) => theme.color.textSoft}; font-size: .74rem; }
  svg { width: 17px; color: ${({ theme }) => theme.color.mint}; }
`;

const Alert = styled.div<{ $warning?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 13px;
  border: 1px solid ${({ $warning, theme }) => $warning ? theme.color.amber : theme.color.mint};
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $warning, theme }) => `color-mix(in srgb, ${$warning ? theme.color.amber : theme.color.mint} 8%, ${theme.color.surfaceStrong})`};
  font-size: .73rem;
  line-height: 1.55;
  svg { width: 17px; flex: 0 0 auto; color: ${({ $warning, theme }) => $warning ? theme.color.amber : theme.color.mint}; }
`;

const Empty = styled.div`
  padding: 17px;
  border: 1px dashed ${({ theme }) => theme.color.controlBorder};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .74rem;
  line-height: 1.6;
  text-align: center;
`;

const Confirm = styled.div`
  display: grid;
  gap: 10px;
  max-width: 230px;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.amber};
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: color-mix(in srgb, ${({ theme }) => theme.color.amber} 8%, ${({ theme }) => theme.color.surfaceStrong});
  font-size: .7rem;
  line-height: 1.5;
  div { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
`;

const State = styled(GlassPanel)`
  display: grid;
  min-height: 440px;
  place-items: center;
  padding: 34px;
  text-align: center;
  div { max-width: 540px; }
  svg { width: 43px; margin: 0 auto 14px; color: ${({ theme }) => theme.color.cyan}; }
  h1 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.45rem; font-weight: 550; }
  p { margin: 0 0 18px; color: ${({ theme }) => theme.color.textMuted}; font-size: .77rem; line-height: 1.7; }
`;

function dateLabel(value: string | null): string {
  if (!value) return 'Not recorded';
  const raw = value.includes('T') ? value : `${value}T12:00:00`;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleDateString('en-CA', { day: 'numeric', month: 'short', year: 'numeric' });
}

function titleCase(value: string | null): string {
  return value ? value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase()) : 'Not recorded';
}

function childInitials(profile: ApiChildProfile): string {
  return `${profile.first_name.charAt(0)}${profile.last_name.charAt(0)}`.toUpperCase();
}

function ageLabel(dateOfBirth: string): string {
  const birth = new Date(`${dateOfBirth}T12:00:00`);
  if (Number.isNaN(birth.getTime())) return 'Age unavailable';
  const now = new Date();
  let months = (now.getFullYear() - birth.getFullYear()) * 12 + now.getMonth() - birth.getMonth();
  if (now.getDate() < birth.getDate()) months -= 1;
  if (months < 24) return `${Math.max(0, months)} months old`;
  const years = Math.floor(months / 12);
  const remainder = months % 12;
  return `${years} ${years === 1 ? 'year' : 'years'}${remainder ? `, ${remainder} mo` : ''}`;
}

function errorText(caught: unknown): string {
  if (caught instanceof ChildrenApiError) return caught.message;
  return caught instanceof Error ? caught.message : 'The child profile request could not be completed.';
}

export default function ChildProfilePage() {
  const { childId = '' } = useParams();
  const location = useLocation();
  const session = useSession();
  const organizationId = session.user?.organization_id || null;
  const canManage = hasPermission(session.user, ACCESS.childcareManage);
  const canViewAuthority = canAdministerFamilyAuthority(session.user);
  const canViewBilling = Boolean(
    (session.user?.role?.key === 'owner' || session.user?.role?.key === 'administrator')
    && hasExplicitPermission(session.user, ACCESS.billingRead),
  );
  const authorityRouteFocus = useMemo(
    () => parseChildAuthorityRouteFocus(location.search),
    [location.search],
  );
  const fileInput = useRef<HTMLInputElement>(null);
  const [profile, setProfile] = useState<ApiChildProfile | null>(null);
  const [familyFinance, setFamilyFinance] = useState<ResourceState<FamilyFinanceSummaryResponse>>({ status: 'idle', data: null });
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [editing, setEditing] = useState(false);
  const [managingEnrollment, setManagingEnrollment] = useState(false);
  const [notice, setNotice] = useState('');

  const loadProfile = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId || !childId || (session.organization?.id && session.organization.id !== organizationId)) throw new Error('The authenticated organization boundary could not be confirmed for this child.');
    const record = await fetchChildProfile(childId, organizationId, signal);
    if (!signal?.aborted) { setProfile(record); setPhase('ready'); setError(''); }
  }, [childId, organizationId, session.organization?.id]);

  const loadFamilyFinance = useCallback(async (signal?: AbortSignal) => {
    const familyId = profile?.family.id;
    if (!canViewBilling || !organizationId || !familyId) return;
    const record = await fetchFamilyFinanceSummary(organizationId, familyId, signal);
    if (!signal?.aborted) setFamilyFinance({ status: 'live', data: record });
  }, [canViewBilling, organizationId, profile?.family.id]);

  useRealtimeRefresh({ scope: 'child-profile', organizationId: organizationId || '', enabled: Boolean(childId), entityTypes: featureIntegrationManifest.children.realtimeEntities, refresh: async () => loadProfile() });
  useRealtimeRefresh({ scope: 'child-profile-finance', organizationId: organizationId || '', enabled: Boolean(childId && canViewBilling && profile?.family.id), entityTypes: featureIntegrationManifest.children.realtimeEntities, refresh: async () => loadFamilyFinance() });

  useEffect(() => {
    if (!organizationId || !childId || (session.organization?.id && session.organization.id !== organizationId)) {
      setPhase('error');
      setError('The authenticated organization boundary could not be confirmed for this child.');
      return;
    }
    const controller = new AbortController();
    setPhase('loading');
    setError('');
    loadProfile(controller.signal)
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setProfile(null);
        setError(errorText(caught));
        setPhase('error');
      });
    return () => controller.abort();
  }, [childId, loadProfile, organizationId, revision, session.organization?.id]);

  useEffect(() => {
    if (!canViewBilling || !organizationId || !profile?.family.id) {
      setFamilyFinance({ status: 'idle', data: null });
      return;
    }
    const controller = new AbortController();
    setFamilyFinance({ status: 'loading', data: null });
    loadFamilyFinance(controller.signal).catch((caught: unknown) => {
      if (!controller.signal.aborted) {
        setFamilyFinance({
          status: 'error',
          data: null,
          message: caught instanceof Error ? caught.message : 'Family finance is unavailable.',
        });
      }
    });
    return () => controller.abort();
  }, [canViewBilling, loadFamilyFinance, organizationId, profile?.family.id, revision]);

  useEffect(() => {
    setPhotoError('');
    if (!profile?.profile_photo_url) {
      setPhotoUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
      setPhotoLoading(false);
      return;
    }
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPhotoUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setPhotoLoading(true);
    fetchChildPhoto(profile.profile_photo_url, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setPhotoUrl((current) => {
          if (current) URL.revokeObjectURL(current);
          return objectUrl;
        });
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setPhotoError(errorText(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPhotoLoading(false);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [profile?.profile_photo_url, profile?.profile_photo_updated_at]);

  const editorChild = useMemo(() => {
    if (!profile) return null;
    return childListIdentityFromProfile(profile);
  }, [profile]);

  const choosePhoto = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !profile) return;
    setPhotoError('');
    setNotice('');
    if (!ACCEPTED_PHOTO_TYPES.has(file.type)) {
      setPhotoError('Choose a JPEG, PNG, or WebP image.');
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setPhotoError('Choose an image no larger than 6 MiB.');
      return;
    }
    const controller = new AbortController();
    setPhotoBusy(true);
    try {
      await uploadChildPhoto(profile.id, file, controller.signal);
      setConfirmRemove(false);
      setNotice(`${profile.first_name}’s profile photo was updated.`);
      setRevision((value) => value + 1);
    } catch (caught) {
      setPhotoError(errorText(caught));
    } finally {
      setPhotoBusy(false);
    }
  };

  const removePhoto = async () => {
    if (!profile) return;
    const controller = new AbortController();
    setPhotoBusy(true);
    setPhotoError('');
    try {
      await deleteChildPhoto(profile.id, controller.signal);
      setConfirmRemove(false);
      setNotice(`${profile.first_name}’s profile photo was removed.`);
      setPhotoUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
      setRevision((value) => value + 1);
    } catch (caught) {
      setPhotoError(errorText(caught));
    } finally {
      setPhotoBusy(false);
    }
  };

  if (phase !== 'ready' || !profile) {
    return <Page><BackLink to="/children"><ArrowLeftIcon /> Back to children</BackLink><State $accent={phase === 'error' ? 'amber' : 'cyan'}><div>{phase === 'loading' ? <ArrowPathIcon /> : <ExclamationTriangleIcon />}<h1>{phase === 'loading' ? 'Loading the child profile' : 'This child profile could not open'}</h1><p>{phase === 'loading' ? 'CareSync is loading identity, family contacts, health details, and enrollment history.' : error}</p>{phase === 'error' && <ActionButton type="button" onClick={() => setRevision((value) => value + 1)}><ArrowPathIcon /> Try again</ActionButton>}</div></State></Page>;
  }

  const current = profile.current_enrollment;
  const activeGuardians = profile.family.guardians;
  const childFinance = familyFinance.data?.children.find((child) => child.child_id === profile.id) || null;

  return <Page>
    <BackLink to="/children"><ArrowLeftIcon /> Back to children</BackLink>
    {notice && <Alert role="status"><CheckCircleIcon /> {notice}</Alert>}
    <Hero $accent="cyan">
      <PhotoColumn>
        <PhotoSurface role="img" aria-label={`${profile.first_name} ${profile.last_name} profile photo`}>
          {photoUrl ? <img src={photoUrl} alt={`${profile.first_name} ${profile.last_name}`} /> : <strong>{childInitials(profile)}</strong>}
          {photoLoading && <PhotoLoading><CameraIcon /></PhotoLoading>}
        </PhotoSurface>
        {canManage && <PhotoActions>
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" onChange={choosePhoto} aria-label="Choose child profile photo" />
          <ActionButton type="button" onClick={() => fileInput.current?.click()} disabled={photoBusy}><CameraIcon /> {photoBusy ? 'Working…' : photoUrl ? 'Replace' : 'Add photo'}</ActionButton>
          {photoUrl && <ActionButton type="button" $variant="danger" aria-label="Remove profile photo" onClick={() => setConfirmRemove(true)} disabled={photoBusy}><TrashIcon /></ActionButton>}
        </PhotoActions>}
        {confirmRemove && <Confirm><span>Remove this profile photo? The child record stays unchanged.</span><div><ActionButton type="button" onClick={() => setConfirmRemove(false)} disabled={photoBusy}>Keep</ActionButton><ActionButton type="button" $variant="danger" onClick={removePhoto} disabled={photoBusy}>Remove</ActionButton></div></Confirm>}
        {photoError && <Alert $warning role="alert"><ExclamationTriangleIcon /> {photoError}</Alert>}
        <PhotoHint>JPEG, PNG, or WebP · up to 6 MiB. Images are securely normalized by CareSync.</PhotoHint>
      </PhotoColumn>

      <HeroContent>
        <HeroHeading>
          <Eyebrow><IdentificationIcon width={14} /> Complete child profile</Eyebrow>
          <h1>{profile.first_name} {profile.middle_name ? `${profile.middle_name} ` : ''}{profile.last_name}</h1>
          <p>Born {dateLabel(profile.date_of_birth)} · {ageLabel(profile.date_of_birth)} · {profile.age_group || 'No saved age band'}</p>
          <Chips><StatusChip $tone={profile.is_active ? 'success' : 'neutral'}>{profile.is_active ? 'Active child' : 'Archived child'}</StatusChip><StatusChip $tone={current ? 'info' : 'warning'}>{current ? `${current.program_name || titleCase(current.program_type)} · ${current.room_name || 'Room not assigned'}` : 'No current enrollment'}</StatusChip></Chips>
        </HeroHeading>
        <FamilyLink to={`/families/${encodeURIComponent(profile.family.id)}`}><div><UserGroupIcon /><div><strong>{profile.family.name}</strong><small>{profile.family.file_number ? `Family file ${profile.family.file_number}` : 'Open complete family profile'}</small></div></div><ArrowLeftIcon /></FamilyLink>
        <HeroActions>{canManage && <ActionButton type="button" $variant="primary" onClick={() => setEditing(true)}><PencilSquareIcon /> Edit child</ActionButton>}{canManage && <ActionButton type="button" onClick={() => setManagingEnrollment(true)}><MapPinIcon /> Manage enrollment</ActionButton>}</HeroActions>
      </HeroContent>
    </Hero>

    <Metrics aria-label="Child profile summary">
      <Metric $accent="cyan"><span><HomeModernIcon /> Current room</span><strong>{current?.room_name || 'Unassigned'}</strong><small>{current?.facility_name || 'No current facility'}</small></Metric>
      <Metric $accent="plasma"><span><UserGroupIcon /> Family</span><strong>{profile.family.name}</strong><small>{activeGuardians.length} saved {activeGuardians.length === 1 ? 'guardian' : 'guardians'}</small></Metric>
      <Metric $accent="cyan"><span><HeartIcon /> Health</span><strong>{profile.allergies ? 'Allergy note' : 'No allergy note'}</strong><small>{profile.immunization_up_to_date === true ? 'Immunization up to date' : profile.immunization_up_to_date === false ? 'Immunization needs review' : 'Immunization not recorded'}</small></Metric>
      <Metric $accent="plasma"><span><CalendarDaysIcon /> Enrollment history</span><strong>{profile.enrollments.length}</strong><small>{current ? `Current since ${dateLabel(current.start_date)}` : 'No open enrollment'}</small></Metric>
    </Metrics>

    {canViewAuthority && organizationId && <ChildAuthoritySummaryPanel childId={profile.id} familyId={profile.family.id} organizationId={organizationId} routeFocus={authorityRouteFocus} />}
    {canViewBilling && <FinanceGrid>
      <FamilyFinanceCard status={familyFinance.status} data={familyFinance.data} message={familyFinance.message} />
      <ChildFinanceCard status={familyFinance.status} data={childFinance} message={familyFinance.message} />
    </FinanceGrid>}

    <Layout>
      <Column>
        <Section $accent="cyan">
          <SectionHeader><div><h2>Identity & care details</h2><p>Core record information used across CareSync.</p></div><IdentificationIcon /></SectionHeader>
          <FactGrid>
            <div><dt>Date of birth</dt><dd>{dateLabel(profile.date_of_birth)}</dd></div>
            <div><dt>Gender</dt><dd>{profile.gender || 'Not recorded'}</dd></div>
            <div><dt>Age band</dt><dd>{profile.age_group || 'Not recorded'}</dd></div>
            <div><dt>Record status</dt><dd>{profile.is_active ? 'Active' : 'Archived'}</dd></div>
            <div><dt>Created</dt><dd>{dateLabel(profile.created_at)}</dd></div>
            <div><dt>Last updated</dt><dd>{dateLabel(profile.updated_at)}</dd></div>
          </FactGrid>
        </Section>

        <Section $accent="plasma">
          <SectionHeader><div><h2>Enrollment journey</h2><p>Current placement and historical care records.</p></div><MapPinIcon /></SectionHeader>
          <EnrollmentList>{profile.enrollments.length ? profile.enrollments.map((enrollment) => <EnrollmentCard key={enrollment.id} $current={profile.current_enrollment?.id === enrollment.id}><HomeModernIcon /><div><strong>{enrollment.program_name || titleCase(enrollment.program_type)} · {enrollment.room_name || 'No room assigned'}</strong><small>{enrollment.facility_name} · {dateLabel(enrollment.start_date)} to {enrollment.end_date ? dateLabel(enrollment.end_date) : 'present'}</small></div><StatusChip $tone={profile.current_enrollment?.id === enrollment.id ? 'success' : 'neutral'}>{profile.current_enrollment?.id === enrollment.id ? 'Current' : titleCase(enrollment.status)}</StatusChip></EnrollmentCard>) : <Empty>No enrollment history has been recorded.</Empty>}</EnrollmentList>
        </Section>

        <Section $accent="cyan">
          <SectionHeader><div><h2>Health & medical record</h2><p>Operational care details for authorized staff.</p></div><HeartIcon /></SectionHeader>
          <FactGrid>
            <div><dt>Allergies</dt><dd>{profile.allergies || 'None recorded'}</dd></div>
            <div><dt>Medical conditions</dt><dd>{profile.medical_conditions || 'None recorded'}</dd></div>
            <div><dt>Medications</dt><dd>{profile.medications || 'None recorded'}</dd></div>
            <div><dt>Immunization</dt><dd>{profile.immunization_up_to_date === true ? 'Up to date' : profile.immunization_up_to_date === false ? 'Not up to date' : 'Not recorded'}</dd></div>
            <div><dt>Doctor</dt><dd>{profile.doctor_name || 'Not recorded'}</dd></div>
            <div><dt>Doctor phone</dt><dd>{profile.doctor_phone ? <a href={`tel:${profile.doctor_phone}`}>{profile.doctor_phone}</a> : 'Not recorded'}</dd></div>
            <div><dt>Health care number</dt><dd>{profile.health_care_number || 'Not recorded'}</dd></div>
          </FactGrid>
        </Section>
      </Column>

      <Column>
        <Section $accent="plasma">
          <SectionHeader><div><h2>Guardians</h2><p>Primary family contacts.</p></div><UserGroupIcon /></SectionHeader>
          <PersonList>{activeGuardians.length ? activeGuardians.map((guardian) => <Person key={guardian.id}><UserIcon /><div><strong>{guardian.first_name} {guardian.last_name}</strong><small>{guardian.relationship || titleCase(guardian.guardian_type)} · {guardian.authorized_pickup ? 'Legacy pickup marker: yes' : 'No affirmative pickup marker recorded'} · not verified authority</small></div><div>{guardian.cell_phone && <a href={`tel:${guardian.cell_phone}`} aria-label={`Call ${guardian.first_name}`}><PhoneIcon /></a>}{guardian.email && <a href={`mailto:${guardian.email}`} aria-label={`Email ${guardian.first_name}`}><EnvelopeIcon /></a>}</div></Person>) : <Empty>No guardians are recorded.</Empty>}</PersonList>
        </Section>

        <Section $accent="cyan">
          <SectionHeader><div><h2>Emergency contacts</h2><p>Additional people in the care network.</p></div><ShieldCheckIcon /></SectionHeader>
          <PersonList>{profile.family.emergency_contacts.length ? profile.family.emergency_contacts.map((contact) => <Person key={contact.id}><ShieldCheckIcon /><div><strong>{contact.first_name} {contact.last_name}</strong><small>{contact.relationship} · {contact.authorized_pickup ? 'Legacy pickup marker: yes' : 'No affirmative pickup marker recorded'} · verified release authority is reviewed separately</small></div><div>{contact.cell_phone && <a href={`tel:${contact.cell_phone}`} aria-label={`Call ${contact.first_name}`}><PhoneIcon /></a>}</div></Person>) : <Empty>No emergency contacts are recorded.</Empty>}</PersonList>
        </Section>

        <Section $accent="plasma">
          <SectionHeader><div><h2>Legacy family profile markers</h2><p>Imported yes/no markers only—not consent evidence or denial. Protected authority records remain the source of truth.</p></div><CheckCircleIcon /></SectionHeader>
          <ConsentList>
            <div><span>Photo</span><StatusChip $tone={profile.family.photo_consent ? 'info' : 'neutral'}>{profile.family.photo_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
            <div><span>Field trip</span><StatusChip $tone={profile.family.field_trip_consent ? 'info' : 'neutral'}>{profile.family.field_trip_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
            <div><span>Emergency medical</span><StatusChip $tone={profile.family.emergency_medical_consent ? 'info' : 'neutral'}>{profile.family.emergency_medical_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</StatusChip></div>
          </ConsentList>
        </Section>

        <Section $accent="cyan">
          <SectionHeader><div><h2>Family notes</h2><p>Household context linked to this child.</p></div><ClockIcon /></SectionHeader>
          <Empty>{profile.family.additional_notes || 'No family notes have been recorded.'}</Empty>
        </Section>
      </Column>
    </Layout>

    {editing && editorChild && organizationId && <ChildEditor request={{ mode: 'edit', child: editorChild }} organizationId={organizationId} onClose={() => setEditing(false)} onSaved={(message) => { setEditing(false); setNotice(message); setRevision((value) => value + 1); }} onManageEnrollment={() => { setEditing(false); setManagingEnrollment(true); }} />}
    {managingEnrollment && editorChild && organizationId && <EnrollmentEditor child={editorChild} organizationId={organizationId} onClose={() => setManagingEnrollment(false)} onSaved={(message) => { setManagingEnrollment(false); setNotice(message); setRevision((value) => value + 1); }} />}
  </Page>;
}

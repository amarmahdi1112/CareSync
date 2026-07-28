import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowPathIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  ClockIcon,
  IdentificationIcon,
  KeyIcon,
  LockClosedIcon,
  MapPinIcon,
  ShieldCheckIcon,
  UserCircleIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { useSession } from '../../auth/SessionContext';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  daycareVerificationPresentation,
  emailVerificationPresentation,
  type VerificationPresentation,
} from '../../models/verification';
import {
  CANADIAN_PROVINCE_OPTIONS,
  CANADIAN_TIMEZONE_OPTIONS,
  includesDomainValue,
  normalizeCanadianProvince,
} from '../../models/domainOptions';
import {
  SettingsApiError,
  settingsApi,
  type FacilitySettingsRecord,
  type OrganizationSettingsRecord,
  type ReleaseCheckoutActivationStatus,
} from './settingsApi';
import type { DeactivationImpact } from '../../models/deactivationImpact';
import {
  facilityPatch,
  organizationPatch,
  validateFacilityDraft,
  validateOrganizationDraft,
  validatePasswordDraft,
  validateProfileDraft,
  type FacilityDraft,
  type OrganizationDraft,
  type PasswordDraft,
  type ProfileDraft,
} from './settingsValidation';
import { reconcileEditableDraft } from './settingsRealtime';

type SettingsTab = 'organization' | 'facility' | 'profile' | 'security';
type RemoteChangeSection = 'organization' | 'facility' | 'profile';
const SETTINGS_TABS: readonly SettingsTab[] = ['organization', 'facility', 'profile', 'security'];
const isSettingsTab = (value: string | null): value is SettingsTab => Boolean(value && SETTINGS_TABS.includes(value as SettingsTab));
type LoadState = 'idle' | 'loading' | 'ready' | 'error';

const enter = keyframes`from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); }`;
const Page = styled.div`display: grid; gap: 24px; animation: ${enter} 250ms ${({ theme }) => theme.motion.ease} both;`;
const Header = styled.header`
  display: flex; align-items: flex-end; justify-content: space-between; gap: 22px;
  h1 { margin: 10px 0 7px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 3.2vw, 2.8rem); font-weight: 520; letter-spacing: -.035em; line-height: 1.05; }
  p { max-width: 750px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .875rem; line-height: 1.65; }
  @media (max-width: 760px) { align-items: flex-start; flex-direction: column; }
`;
const HeaderSignal = styled.div`display: grid; min-width: 220px; justify-items: end; gap: 7px; small { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; text-align: right; } @media (max-width: 760px) { min-width: 0; justify-items: start; small { text-align: left; } }`;
const VerificationMark = styled.div`
  display: grid; max-width: 310px; justify-items: end; gap: 7px; text-align: right;
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.5; }
  @media (max-width: 700px) { justify-items: start; text-align: left; }
`;
const Layout = styled.div`display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 18px; @media (max-width: 900px) { grid-template-columns: 1fr; }`;
const Tabs = styled(GlassPanel)`
  align-self: start; padding: 10px;
  @media (min-width: 901px) { position: sticky; top: 96px; }
  @media (max-width: 900px) { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
  @media (max-width: 600px) { grid-template-columns: repeat(3, minmax(0, 1fr)); }
`;
const TabButton = styled.button<{ $active: boolean }>`
  display: grid; width: 100%; min-height: 52px; grid-template-columns: 34px 1fr; align-items: center; gap: 10px; padding: 12px; border: 1px solid ${({ $active, theme }) => $active ? theme.color.borderStrong : 'transparent'}; border-radius: 10px 14px 10px 10px; color: ${({ $active, theme }) => $active ? theme.color.text : theme.color.textMuted}; background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.plasma})` : 'transparent'}; cursor: pointer; text-align: left; transition: color ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease}, background ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease}, border-color ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};
  &:hover { color: ${({ theme }) => theme.color.text}; background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 86%, ${theme.color.plasma})` : theme.color.surfaceHover}; }
  svg { width: 20px; margin: auto; color: ${({ $active, theme }) => $active ? theme.color.plasmaBright : 'currentColor'}; } strong { display: block; font-size: .8125rem; font-weight: 600; } small { display: block; margin-top: 2px; font-size: .72rem; color: ${({ theme }) => theme.color.textMuted}; }
  @media (max-width: 900px) { grid-template-columns: 1fr; justify-items: center; text-align: center; small { display: none; } }
`;
const Panel = styled(GlassPanel)`padding: clamp(20px, 3vw, 34px);`;
const PanelHeader = styled.div`
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px;
  h2 { margin: 5px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.3rem, 2.4vw, 1.8rem); font-weight: 540; letter-spacing: -.035em; }
  p { max-width: 620px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; line-height: 1.65; }
`;
const Form = styled.form`display: grid; gap: 22px;`;
const Section = styled.fieldset`
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; margin: 0; padding: 20px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: ${({ theme }) => theme.radius.md}; background: ${({ theme }) => theme.color.surfaceStrong};
  legend { padding: 0 8px; color: ${({ theme }) => theme.color.cyan}; font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  @media (max-width: 700px) { grid-template-columns: 1fr; padding: 16px; }
`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid; grid-column: ${({ $wide }) => $wide ? '1 / -1' : 'auto'}; gap: 7px;
  span { color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; font-weight: 600; }
  input, select { width: 100%; min-height: 46px; padding: 0 13px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .8125rem; }
  input:focus, select:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent); }
  input:disabled, select:disabled { opacity: .62; cursor: not-allowed; }
`;
const FormActions = styled.div`display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px;`;
const ActivationPanel = styled.section`
  display: grid; gap: 16px; padding: 20px; border: 1px solid ${({ theme }) => theme.color.borderStrong}; border-radius: ${({ theme }) => theme.radius.md};
  background: linear-gradient(145deg, color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 90%, ${({ theme }) => theme.color.cyan}), ${({ theme }) => theme.color.surfaceStrong});
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; font-weight: 540; letter-spacing: -.02em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .79rem; line-height: 1.6; }
`;
const ActivationHeader = styled.div`
  display: flex; align-items: flex-start; justify-content: space-between; gap: 14px;
  > div { display: grid; gap: 5px; }
  @media (max-width: 600px) { flex-direction: column; }
`;
const ReadinessGrid = styled.div`
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px;
  div { display: grid; gap: 3px; padding: 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 10px; background: ${({ theme }) => theme.color.control}; }
  strong { font-size: 1.05rem; font-weight: 580; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.4; }
  @media (max-width: 600px) { grid-template-columns: 1fr; }
`;
const PrerequisiteList = styled.div`
  display: grid; gap: 7px;
  div { display: flex; align-items: center; gap: 8px; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; line-height: 1.45; }
  svg { width: 17px; flex: 0 0 auto; }
  [data-ready='true'] svg { color: ${({ theme }) => theme.color.mint}; }
  [data-ready='false'] svg { color: ${({ theme }) => theme.color.amber}; }
`;
const ActivationChecklist = styled.div`
  display: grid; gap: 9px; padding: 14px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 10px; background: ${({ theme }) => theme.color.control};
  label { display: grid; grid-template-columns: 18px 1fr; align-items: start; gap: 9px; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; line-height: 1.5; }
  input[type='checkbox'] { width: 16px; height: 16px; margin: 2px 0 0; accent-color: ${({ theme }) => theme.color.cyan}; }
`;
const ConfirmationField = styled.label`
  display: grid; gap: 7px;
  span { color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; font-weight: 600; }
  input { width: 100%; min-height: 44px; padding: 0 13px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .78rem; }
  input:focus { border-color: ${({ theme }) => theme.color.amber}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.amber} 18%, transparent); }
`;
const Notice = styled.div<{ $error?: boolean; $remote?: boolean }>`
  display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border: 1px solid ${({ $error, $remote, theme }) => $error ? theme.color.coral : $remote ? theme.color.amber : theme.color.mint}; border-radius: 10px 14px 10px 10px; color: ${({ $error, $remote, theme }) => $error ? theme.color.coral : $remote ? theme.color.amber : theme.color.mint}; background: ${({ $error, $remote, theme }) => $error ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.coral})` : $remote ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.amber})` : `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.mint})`}; font-size: .8125rem; line-height: 1.55;
  svg { width: 18px; flex: 0 0 auto; }
`;
const Gate = styled(GlassPanel)`display: grid; min-height: 360px; place-items: center; padding: 30px; text-align: center; svg { width: 46px; margin: 0 auto 14px; color: ${({ theme }) => theme.color.plasmaBright}; } h2 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.7rem; } p { max-width: 520px; margin: 0 auto 18px; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; line-height: 1.65; }`;
const LoginLink = styled(Link)`display: inline-flex; min-height: 44px; align-items: center; padding: 0 15px; border: 1px solid ${({ theme }) => theme.color.plasma}; border-radius: 10px 14px 10px 10px; color: ${({ theme }) => theme.color.text}; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 86%, ${({ theme }) => theme.color.plasma}); font-size: .75rem; font-weight: 600;`;

const EMPTY_ORGANIZATION: OrganizationDraft = { name: '', legal_name: '', email: '', phone: '', timezone: 'America/Edmonton' };
const EMPTY_FACILITY: FacilityDraft = { name: '', license_number: '', email: '', phone: '', street_address: '', city: '', province: 'Alberta', postal_code: '', timezone: 'America/Edmonton', licensed_capacity: '0', opening_time: '', closing_time: '', status: 'active' };

const text = (value: string | null | undefined) => value || '';
const organizationDraftFrom = (value: OrganizationSettingsRecord): OrganizationDraft => ({ name: value.name, legal_name: text(value.legal_name), email: text(value.email), phone: text(value.phone), timezone: value.timezone });
const facilityDraftFrom = (value: FacilitySettingsRecord): FacilityDraft => ({
  name: value.name, license_number: text(value.license_number), email: text(value.email), phone: text(value.phone), street_address: text(value.street_address), city: text(value.city), province: normalizeCanadianProvince(value.province), postal_code: text(value.postal_code), timezone: value.timezone, licensed_capacity: String(value.licensed_capacity), opening_time: text(value.opening_time).slice(0, 5), closing_time: text(value.closing_time).slice(0, 5), status: value.status,
});

const verificationMark = (presentation: VerificationPresentation) => (
  <VerificationMark>
    <StatusChip $tone={presentation.tone}>{presentation.label}</StatusChip>
    <small>{presentation.note}</small>
  </VerificationMark>
);

export default function SettingsPage() {
  const session = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const organizationReady = session.status === 'authenticated' && Boolean(session.user?.organization_id) && session.user?.organization_id === session.organization?.id && !session.organizationUnavailable;
  const canManageTenantSettings = hasPermission(session.user, ACCESS.organizationManage) || hasPermission(session.user, ACCESS.settingsManage);
  const canManageOrganization = canManageTenantSettings;
  const canManageFacility = canManageTenantSettings;
  const canControlReleaseActivation = session.user?.role.key === 'owner' || session.user?.role.key === 'administrator';
  const [tab, setTabState] = useState<SettingsTab>(() => {
    const requested = searchParams.get('section');
    return isSettingsTab(requested) ? requested : canManageOrganization ? 'organization' : canManageFacility ? 'facility' : 'profile';
  });
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [organization, setOrganization] = useState<OrganizationSettingsRecord | null>(null);
  const [organizationDraft, setOrganizationDraft] = useState<OrganizationDraft>(EMPTY_ORGANIZATION);
  const [facilities, setFacilities] = useState<FacilitySettingsRecord[]>([]);
  const [facilityId, setFacilityId] = useState('');
  const [facilityDraft, setFacilityDraft] = useState<FacilityDraft>(EMPTY_FACILITY);
  const [profile, setProfile] = useState<ProfileDraft>({ first_name: '', last_name: '', email: '' });
  const [password, setPassword] = useState<PasswordDraft>({ current: '', next: '', confirm: '' });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);
  const [remoteChanges, setRemoteChanges] = useState<Set<RemoteChangeSection>>(() => new Set());
  const [facilityImpact, setFacilityImpact] = useState<DeactivationImpact | null>(null);
  const [facilityConfirmation, setFacilityConfirmation] = useState('');
  const [facilityDeactivationReason, setFacilityDeactivationReason] = useState('');
  const [releaseActivation, setReleaseActivation] = useState<ReleaseCheckoutActivationStatus | null>(null);
  const [activationChecks, setActivationChecks] = useState({
    authority: false,
    verification: false,
    legacyClosure: false,
    irreversible: false,
  });
  const [activationConfirmation, setActivationConfirmation] = useState('');
  const [activationSubmitting, setActivationSubmitting] = useState(false);

  const organizationBaseline = useRef<OrganizationDraft | null>(null);
  const facilityBaselines = useRef(new Map<string, FacilityDraft>());
  const profileBaseline = useRef<ProfileDraft | null>(null);
  const refreshSequence = useRef(0);
  const appliedRefreshSequence = useRef(0);
  const latestDrafts = useRef({ organizationDraft, facilityId, facilityDraft, profile });
  latestDrafts.current = { organizationDraft, facilityId, facilityDraft, profile };

  const clearRemoteChange = useCallback((section: RemoteChangeSection) => {
    setRemoteChanges((current) => {
      if (!current.has(section)) return current;
      const next = new Set(current); next.delete(section); return next;
    });
  }, []);

  const organizationId = session.user?.organization_id || '';
  const refreshSettings = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId) return;
    const sequence = ++refreshSequence.current;
    const [nextOrganization, nextFacilities, nextProfile] = await Promise.all([
      canManageOrganization ? settingsApi.organization(signal) : Promise.resolve(null),
      canManageFacility ? settingsApi.facilities(signal) : Promise.resolve([]),
      settingsApi.profile(signal),
    ]);
    if ((nextOrganization && nextOrganization.id !== organizationId) || nextFacilities.some((item) => item.organization_id !== organizationId) || nextProfile.organization_id !== organizationId) throw new Error('Organization boundary mismatch. Settings stayed locked.');
    if (sequence < appliedRefreshSequence.current) return;
    appliedRefreshSequence.current = sequence;

    const current = latestDrafts.current;
    const nextOrganizationDraft = nextOrganization ? organizationDraftFrom(nextOrganization) : null;
    const organizationResult = nextOrganizationDraft
      ? reconcileEditableDraft(current.organizationDraft, organizationBaseline.current, nextOrganizationDraft)
      : null;

    const nextFacilityId = nextFacilities.some((item) => item.id === current.facilityId) ? current.facilityId : nextFacilities[0]?.id || '';
    const nextFacility = nextFacilities.find((item) => item.id === nextFacilityId) || null;
    const nextFacilityDraft = nextFacility ? facilityDraftFrom(nextFacility) : EMPTY_FACILITY;
    const facilityResult = reconcileEditableDraft(
      nextFacilityId === current.facilityId ? current.facilityDraft : nextFacilityDraft,
      nextFacilityId === current.facilityId ? facilityBaselines.current.get(nextFacilityId) || null : null,
      nextFacilityDraft,
    );
    const nextProfileDraft = { first_name: nextProfile.first_name, last_name: nextProfile.last_name, email: nextProfile.email };
    const profileResult = reconcileEditableDraft(current.profile, profileBaseline.current, nextProfileDraft);
    const nextReleaseActivation = canControlReleaseActivation && nextFacilityId
      ? await settingsApi.releaseCheckoutActivationStatus(nextFacilityId, organizationId, signal)
      : null;

    organizationBaseline.current = nextOrganizationDraft;
    facilityBaselines.current = new Map(nextFacilities.map((item) => [item.id, facilityDraftFrom(item)]));
    profileBaseline.current = nextProfileDraft;
    latestDrafts.current = {
      organizationDraft: organizationResult?.draft || current.organizationDraft,
      facilityId: nextFacilityId,
      facilityDraft: facilityResult.draft,
      profile: profileResult.draft,
    };
    setOrganization(nextOrganization);
    if (organizationResult) setOrganizationDraft(organizationResult.draft);
    setFacilities(nextFacilities); setFacilityId(nextFacilityId); setFacilityDraft(facilityResult.draft); setProfile(profileResult.draft);
    setReleaseActivation(nextReleaseActivation);
    setRemoteChanges((existing) => {
      const updated = new Set(existing);
      const reconcileNotice = (section: RemoteChangeSection, result: { dirty: boolean; remoteChangedWhileDirty: boolean } | null) => {
        if (result?.remoteChangedWhileDirty) updated.add(section);
        else if (!result?.dirty) updated.delete(section);
      };
      reconcileNotice('organization', organizationResult);
      reconcileNotice('facility', nextFacility ? facilityResult : null);
      reconcileNotice('profile', profileResult);
      return updated;
    });
    setLoadState('ready');
  }, [canControlReleaseActivation, canManageFacility, canManageOrganization, organizationId]);
  useRealtimeRefresh({ scope: 'settings', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.settings.realtimeEntities, refresh: async () => refreshSettings() });

  const selectedFacility = facilities.find((item) => item.id === facilityId) || null;
  const organizationVerification = organization
    ? daycareVerificationPresentation(organization, 'Organization')
    : null;
  const facilityVerification = selectedFacility
    ? daycareVerificationPresentation(selectedFacility, 'Facility')
    : null;
  const emailVerification = session.user
    ? emailVerificationPresentation(session.user)
    : null;

  useEffect(() => {
    const organizationId = session.user?.organization_id;
    if (!organizationReady || !organizationId) { setLoadState('idle'); setOrganization(null); setFacilities([]); setReleaseActivation(null); organizationBaseline.current = null; facilityBaselines.current = new Map(); profileBaseline.current = null; setRemoteChanges(new Set()); return; }
    const controller = new AbortController();
    setLoadState('loading'); setNotice(null);
    void refreshSettings(controller.signal)
      .catch((error: unknown) => { if (!controller.signal.aborted) { setNotice({ message: error instanceof Error ? error.message : 'Settings could not be loaded.', error: true }); setLoadState('error'); } });
    return () => controller.abort();
  }, [organizationReady, refreshSettings, session.user?.organization_id]);

  const tabs = useMemo(() => [
    ...(canManageOrganization ? [{ id: 'organization' as const, label: 'Organization', description: 'Business identity', icon: BuildingOffice2Icon }] : []),
    ...(canManageFacility ? [{ id: 'facility' as const, label: 'Facility', description: 'Licensed location', icon: MapPinIcon }] : []),
    { id: 'profile' as const, label: 'My profile', description: 'Your identity', icon: UserCircleIcon },
    { id: 'security' as const, label: 'Security', description: 'Password', icon: KeyIcon },
  ], [canManageFacility, canManageOrganization]);

  const setTab = (next: SettingsTab) => {
    setTabState(next);
    setSearchParams((current) => {
      const params = new URLSearchParams(current);
      if (next === tabs[0]?.id) params.delete('section');
      else params.set('section', next);
      return params;
    }, { replace: true });
  };

  useEffect(() => {
    const requested = searchParams.get('section');
    if (isSettingsTab(requested) && tabs.some((item) => item.id === requested) && requested !== tab) setTabState(requested);
    else if (!tabs.some((item) => item.id === tab)) setTabState(tabs[0].id);
  }, [searchParams, tab, tabs]);

  const resetFacilityDeactivation = () => { setFacilityImpact(null); setFacilityConfirmation(''); setFacilityDeactivationReason(''); };
  const resetReleaseActivationReview = () => {
    setActivationChecks({ authority: false, verification: false, legacyClosure: false, irreversible: false });
    setActivationConfirmation('');
  };
  const resetOrganizationDraft = () => { if (organizationBaseline.current) { latestDrafts.current.organizationDraft = organizationBaseline.current; setOrganizationDraft(organizationBaseline.current); } clearRemoteChange('organization'); };
  const resetFacilityDraft = () => { const baseline = facilityBaselines.current.get(facilityId); if (baseline) { latestDrafts.current.facilityDraft = baseline; setFacilityDraft(baseline); } resetFacilityDeactivation(); clearRemoteChange('facility'); };
  const resetProfileDraft = () => { if (profileBaseline.current) { latestDrafts.current.profile = profileBaseline.current; setProfile(profileBaseline.current); } clearRemoteChange('profile'); };
  const chooseFacility = (id: string) => {
    setFacilityId(id); latestDrafts.current.facilityId = id;
    const baseline = facilityBaselines.current.get(id);
    if (baseline) { latestDrafts.current.facilityDraft = baseline; setFacilityDraft(baseline); }
    setReleaseActivation(null); resetReleaseActivationReview(); resetFacilityDeactivation(); clearRemoteChange('facility'); setNotice(null);
    void refreshSettings().catch((error: unknown) => setNotice({ message: error instanceof Error ? error.message : 'Facility controls could not be refreshed.', error: true }));
  };
  const permissionGuard = (allowed: boolean, message: string) => { if (allowed) return true; setNotice({ message, error: true }); return false; };

  const saveOrganization = async (event: FormEvent) => {
    event.preventDefault(); if (!permissionGuard(canManageOrganization, 'Your role cannot change organization settings.')) return;
    const errors = validateOrganizationDraft(organizationDraft); if (errors.length) { setNotice({ message: errors.join(' '), error: true }); return; }
    setSaving(true); setNotice(null);
    try { const saved = await settingsApi.updateOrganization(organizationPatch(organizationDraft), session.organization!.id); const savedDraft = organizationDraftFrom(saved); organizationBaseline.current = savedDraft; latestDrafts.current.organizationDraft = savedDraft; setOrganization(saved); setOrganizationDraft(savedDraft); clearRemoteChange('organization'); setNotice({ message: 'Organization settings saved.', error: false }); void session.refreshOrganizationFacts().catch(() => undefined); }
    catch (error) { setNotice({ message: error instanceof Error ? error.message : 'Organization settings could not be saved.', error: true }); }
    finally { setSaving(false); }
  };

  const saveFacility = async (event: FormEvent) => {
    event.preventDefault(); if (!permissionGuard(canManageFacility, 'Your role cannot change facility settings.') || !facilityId) return;
    const errors = validateFacilityDraft(facilityDraft); if (errors.length) { setNotice({ message: errors.join(' '), error: true }); return; }
    const isDeactivation = selectedFacility?.status === 'active' && facilityDraft.status === 'inactive';
    setSaving(true); setNotice(null);
    try {
      if (isDeactivation && !facilityImpact) {
        const impact = await settingsApi.facilityDeactivationImpact(facilityId, session.organization!.id);
        setFacilityImpact(impact);
        setNotice({ message: impact.can_deactivate ? 'Review the impact and confirm this facility deactivation.' : 'This facility cannot be deactivated until every blocker is resolved.', error: !impact.can_deactivate });
        return;
      }
      if (isDeactivation && facilityImpact) {
        if (!facilityImpact.can_deactivate) throw new Error('Resolve every deactivation blocker before trying again.');
        if (facilityConfirmation !== facilityImpact.confirmation_text) throw new Error(`Type “${facilityImpact.confirmation_text}” exactly to confirm.`);
        if (facilityDeactivationReason.trim().length < 3) throw new Error('Enter a deactivation reason of at least 3 characters.');
      }
      const payload = facilityPatch(facilityDraft);
      if (isDeactivation && facilityImpact) {
        payload.deactivation_confirmation = facilityConfirmation;
        payload.deactivation_reason = facilityDeactivationReason.trim();
      }
      const saved = await settingsApi.updateFacility(facilityId, payload, session.organization!.id);
      const savedDraft = facilityDraftFrom(saved); facilityBaselines.current.set(saved.id, savedDraft); latestDrafts.current.facilityDraft = savedDraft;
      setFacilities((items) => items.map((item) => item.id === saved.id ? saved : item)); setFacilityDraft(savedDraft); resetFacilityDeactivation(); clearRemoteChange('facility'); setNotice({ message: 'Facility settings saved.', error: false });
    }
    catch (error) { setNotice({ message: error instanceof Error ? error.message : 'Facility settings could not be saved.', error: true }); }
    finally { setSaving(false); }
  };

  const activateVerifiedRelease = async () => {
    if (!releaseActivation || !facilityId || !session.organization || !canControlReleaseActivation) {
      setNotice({ message: 'The exact facility activation context is not available.', error: true });
      return;
    }
    const reviewed = Object.values(activationChecks).every(Boolean);
    if (!reviewed || activationConfirmation !== releaseActivation.confirmation_text) {
      setNotice({ message: `Review every item and type “${releaseActivation.confirmation_text}” exactly.`, error: true });
      return;
    }
    if (!releaseActivation.can_activate) {
      setNotice({ message: 'Resolve every release-checkout prerequisite before activation.', error: true });
      return;
    }
    const operationKey = `caresync-release-activation:${session.organization.id}:${facilityId}`;
    let operationId = localStorage.getItem(operationKey);
    if (!operationId) {
      operationId = crypto.randomUUID();
      localStorage.setItem(operationKey, operationId);
    }
    setActivationSubmitting(true); setNotice(null);
    try {
      const result = await settingsApi.activateReleaseCheckout(facilityId, {
        schema_version: 'release-checkout-activation-command-v1',
        organization_id: session.organization.id,
        facility_id: facilityId,
        client_operation_id: operationId,
        activation_policy_version: 'normal_verified_release_v1',
        authority_records_reviewed: true,
        verification_workflow_reviewed: true,
        legacy_checkout_closure_understood: true,
        irreversible_activation_understood: true,
        confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT',
      }, session.organization.id);
      localStorage.removeItem(operationKey);
      setReleaseActivation(result.status);
      resetReleaseActivationReview();
      setNotice({ message: result.replayed ? 'Verified release activation was reconciled from its committed receipt.' : 'Verified release checkout is now permanently active for this facility.', error: false });
    } catch (error) {
      if (error instanceof SettingsApiError && error.status > 0 && error.status < 500) localStorage.removeItem(operationKey);
      setNotice({ message: error instanceof Error ? error.message : 'Verified release checkout could not be activated.', error: true });
      if (error instanceof SettingsApiError && error.status === 409) void refreshSettings().catch(() => undefined);
    } finally {
      setActivationSubmitting(false);
    }
  };


  const saveProfile = async (event: FormEvent) => {
    event.preventDefault(); const errors = validateProfileDraft(profile); if (errors.length) { setNotice({ message: errors.join(' '), error: true }); return; }
    setSaving(true); setNotice(null);
    try { const saved = await settingsApi.updateProfile({ first_name: profile.first_name.trim(), last_name: profile.last_name.trim(), email: profile.email.trim() }, session.organization!.id); const savedDraft = { first_name: saved.first_name, last_name: saved.last_name, email: saved.email }; profileBaseline.current = savedDraft; latestDrafts.current.profile = savedDraft; setProfile(savedDraft); clearRemoteChange('profile'); setNotice({ message: 'Your profile was saved.', error: false }); session.retry(); }
    catch (error) { setNotice({ message: error instanceof Error ? error.message : 'Profile could not be saved.', error: true }); }
    finally { setSaving(false); }
  };

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    const errors = validatePasswordDraft(password); if (errors.length) { setNotice({ message: errors.join(' '), error: true }); return; }
    setSaving(true); setNotice(null);
    try { await settingsApi.changePassword({ current_password: password.current, new_password: password.next }); setPassword({ current: '', next: '', confirm: '' }); session.logout(); }
    catch (error) { setNotice({ message: error instanceof Error ? error.message : 'Password could not be changed.', error: true }); }
    finally { setSaving(false); }
  };

  let content;
  if (session.status === 'anonymous') content = <Gate $accent="plasma"><div><LockClosedIcon /><h2>Sign in to open settings.</h2><p>Organization and account settings are available only inside an authenticated session.</p><LoginLink to="/login">Open secure login</LoginLink></div></Gate>;
  else if (session.status === 'checking' || loadState === 'loading' || (session.status === 'authenticated' && !session.organization && !session.organizationUnavailable)) content = <Gate $accent="cyan" aria-busy="true"><div><ArrowPathIcon /><h2>Confirming the organization context.</h2><p>Settings stay locked until the signed-in identity and loaded organization agree.</p></div></Gate>;
  else if (!organizationReady || loadState === 'error') content = <Gate $accent="amber"><div><ShieldCheckIcon /><h2>Settings are safely locked.</h2><p>{notice?.message || 'The identity and organization context could not be confirmed.'}</p><ActionButton onClick={session.retry}><ArrowPathIcon /> Retry context check</ActionButton></div></Gate>;
  else content = <Layout><Tabs $accent="plasma" aria-label="Settings sections">{tabs.map((item) => <TabButton key={item.id} type="button" $active={tab === item.id} aria-pressed={tab === item.id} onClick={() => { setTab(item.id); setNotice(null); }}><item.icon /><span><strong>{item.label}</strong><small>{item.description}</small></span></TabButton>)}</Tabs><Panel $accent={tab === 'security' ? 'amber' : 'cyan'}>
    {remoteChanges.size > 0 && <Notice $remote role="status"><ArrowPathIcon /><span>Saved {Array.from(remoteChanges).join(', ')} settings changed elsewhere while you were editing. Your unsaved values were preserved. Save to replace the newer values, or use Reset unsaved to load them.</span></Notice>}
    {notice && <Notice $error={notice.error} role={notice.error ? 'alert' : 'status'}>{notice.error ? <ShieldCheckIcon /> : <CheckCircleIcon />}<span>{notice.message}</span></Notice>}
    {tab === 'organization' && <Form onSubmit={saveOrganization}><PanelHeader><div><Eyebrow><BuildingOffice2Icon width={14} /> Organization</Eyebrow><h2>Business identity.</h2><p>Core organization contact details and the one canonical organization timezone. Verification is read only and separate from operating status.</p></div>{organizationVerification ? verificationMark(organizationVerification) : <StatusChip $tone="neutral">Verification unavailable</StatusChip>}</PanelHeader><Section disabled={!canManageOrganization}><legend>Identity & contact</legend><Field><span>Organization name</span><input required value={organizationDraft.name} onChange={(e) => setOrganizationDraft((v) => ({ ...v, name: e.target.value }))} /></Field><Field><span>Legal name</span><input value={organizationDraft.legal_name} onChange={(e) => setOrganizationDraft((v) => ({ ...v, legal_name: e.target.value }))} /></Field><Field><span>Email</span><input type="email" value={organizationDraft.email} onChange={(e) => setOrganizationDraft((v) => ({ ...v, email: e.target.value }))} /></Field><Field><span>Phone</span><input type="tel" value={organizationDraft.phone} onChange={(e) => setOrganizationDraft((v) => ({ ...v, phone: e.target.value }))} /></Field><Field $wide><span>Timezone</span><select required value={organizationDraft.timezone} onChange={(e) => setOrganizationDraft((v) => ({ ...v, timezone: e.target.value }))}>{organizationDraft.timezone && !includesDomainValue(CANADIAN_TIMEZONE_OPTIONS, organizationDraft.timezone) && <option value={organizationDraft.timezone}>Current saved timezone · {organizationDraft.timezone}</option>}{CANADIAN_TIMEZONE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field></Section><FormActions><ActionButton type="button" onClick={resetOrganizationDraft}>Reset unsaved</ActionButton><ActionButton type="submit" $variant="primary" disabled={saving || !canManageOrganization}>{saving ? 'Saving…' : 'Save organization'}</ActionButton></FormActions></Form>}
    {tab === 'facility' && (facilities.length ? (
      <Form onSubmit={saveFacility}>
        <PanelHeader>
          <div><Eyebrow><MapPinIcon width={14} /> Facility</Eyebrow><h2>Licensed location.</h2><p>Contact, address, capacity, hours, and operating status. The verification badge is informational and read only.</p></div>
          {facilityVerification ? verificationMark(facilityVerification) : <StatusChip $tone="neutral">Verification unavailable</StatusChip>}
        </PanelHeader>
        <Section>
          <legend>Choose facility</legend>
          <Field $wide><span>Facility</span><select value={facilityId} onChange={(event) => chooseFacility(event.target.value)}>{facilities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        </Section>
        <Section disabled={!canManageFacility}>
          <legend>Identity & contact</legend>
          <Field><span>Facility name</span><input required value={facilityDraft.name} onChange={(event) => setFacilityDraft((value) => ({ ...value, name: event.target.value }))} /></Field>
          <Field><span>License number</span><input value={facilityDraft.license_number} onChange={(event) => setFacilityDraft((value) => ({ ...value, license_number: event.target.value }))} /></Field>
          <Field><span>Email</span><input type="email" value={facilityDraft.email} onChange={(event) => setFacilityDraft((value) => ({ ...value, email: event.target.value }))} /></Field>
          <Field><span>Phone</span><input type="tel" value={facilityDraft.phone} onChange={(event) => setFacilityDraft((value) => ({ ...value, phone: event.target.value }))} /></Field>
        </Section>
        <Section disabled={!canManageFacility}>
          <legend>Location & operations</legend>
          <Field $wide><span>Street address</span><input value={facilityDraft.street_address} onChange={(event) => setFacilityDraft((value) => ({ ...value, street_address: event.target.value }))} /></Field>
          <Field><span>City</span><input value={facilityDraft.city} onChange={(event) => setFacilityDraft((value) => ({ ...value, city: event.target.value }))} /></Field>
          <Field><span>Province or territory</span><select required value={facilityDraft.province} onChange={(event) => setFacilityDraft((value) => ({ ...value, province: event.target.value }))}>{facilityDraft.province && !includesDomainValue(CANADIAN_PROVINCE_OPTIONS, facilityDraft.province) && <option value={facilityDraft.province}>Current saved value · {facilityDraft.province}</option>}{CANADIAN_PROVINCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
          <Field><span>Postal code</span><input value={facilityDraft.postal_code} onChange={(event) => setFacilityDraft((value) => ({ ...value, postal_code: event.target.value }))} /></Field>
          <Field><span>Licensed capacity</span><input required type="number" min="0" step="1" value={facilityDraft.licensed_capacity} onChange={(event) => setFacilityDraft((value) => ({ ...value, licensed_capacity: event.target.value }))} /></Field>
          <Field><span>Operating status</span><select value={facilityDraft.status} onChange={(event) => { setFacilityDraft((value) => ({ ...value, status: event.target.value })); resetFacilityDeactivation(); }}><option value="active">Active</option><option value="inactive">Inactive</option></select></Field>
          <Field><span>Opening time</span><input type="time" value={facilityDraft.opening_time} onChange={(event) => setFacilityDraft((value) => ({ ...value, opening_time: event.target.value }))} /></Field>
          <Field><span>Closing time</span><input type="time" value={facilityDraft.closing_time} onChange={(event) => setFacilityDraft((value) => ({ ...value, closing_time: event.target.value }))} /></Field>
          <Field $wide><span>Timezone</span><select required value={facilityDraft.timezone} onChange={(event) => setFacilityDraft((value) => ({ ...value, timezone: event.target.value }))}>{facilityDraft.timezone && !includesDomainValue(CANADIAN_TIMEZONE_OPTIONS, facilityDraft.timezone) && <option value={facilityDraft.timezone}>Current saved timezone · {facilityDraft.timezone}</option>}{CANADIAN_TIMEZONE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
        </Section>
        {canControlReleaseActivation && <ActivationPanel aria-labelledby="release-activation-heading">
          <ActivationHeader>
            <div>
              <Eyebrow><ShieldCheckIcon width={14} /> Child release boundary</Eyebrow>
              <h3 id="release-activation-heading">Verified release checkout.</h3>
              <p>This is an irreversible facility cutover. Nothing is activated automatically: an owner or administrator must resolve every prerequisite, review the workflow and confirm once.</p>
            </div>
            <StatusChip $tone={releaseActivation?.activated ? 'success' : releaseActivation?.can_activate ? 'warning' : 'neutral'}>
              {releaseActivation?.activated ? 'Permanently active' : releaseActivation?.can_activate ? 'Ready for review' : releaseActivation ? 'Prerequisites open' : 'Loading status'}
            </StatusChip>
          </ActivationHeader>
          {releaseActivation && <>
            <ReadinessGrid>
              <div><strong>{releaseActivation.open_enrollment_children}</strong><span>Active or paused enrolled children</span></div>
              <div><strong>{releaseActivation.release_ready_children}</strong><span>Children with a current supported release authorization</span></div>
              <div><strong>{releaseActivation.children_needing_authority_review}</strong><span>Children requiring authority review before cutover</span></div>
            </ReadinessGrid>
            <PrerequisiteList aria-label="Verified release activation prerequisites">
              {releaseActivation.prerequisites.map((item) => <div key={item.code} data-ready={item.satisfied}>{item.satisfied ? <CheckCircleIcon /> : <ClockIcon />}<span>{item.label}</span></div>)}
            </PrerequisiteList>
            {releaseActivation.activated ? (
              <Notice><LockClosedIcon /><span>Legacy attendance-only checkout is closed for this facility. There is intentionally no deactivate or override control.</span></Notice>
            ) : releaseActivation.can_activate ? (
              <>
                <ActivationChecklist>
                  <label><input type="checkbox" checked={activationChecks.authority} onChange={(event) => setActivationChecks((value) => ({ ...value, authority: event.target.checked }))} /><span>I reviewed the child authority records and the readiness count above.</span></label>
                  <label><input type="checkbox" checked={activationChecks.verification} onChange={(event) => setActivationChecks((value) => ({ ...value, verification: event.target.checked }))} /><span>I reviewed the supported recipient verification workflow with facility operators.</span></label>
                  <label><input type="checkbox" checked={activationChecks.legacyClosure} onChange={(event) => setActivationChecks((value) => ({ ...value, legacyClosure: event.target.checked }))} /><span>I understand the old attendance-only checkout closes immediately after activation.</span></label>
                  <label><input type="checkbox" checked={activationChecks.irreversible} onChange={(event) => setActivationChecks((value) => ({ ...value, irreversible: event.target.checked }))} /><span>I understand this activation is immutable and has no deactivate or software override.</span></label>
                </ActivationChecklist>
                <ConfirmationField><span>Type {releaseActivation.confirmation_text} exactly</span><input value={activationConfirmation} onChange={(event) => setActivationConfirmation(event.target.value)} autoComplete="off" spellCheck={false} /></ConfirmationField>
                <FormActions><ActionButton type="button" onClick={resetReleaseActivationReview}>Reset review</ActionButton><ActionButton type="button" $variant="primary" disabled={activationSubmitting || !Object.values(activationChecks).every(Boolean) || activationConfirmation !== releaseActivation.confirmation_text} onClick={() => void activateVerifiedRelease()}>{activationSubmitting ? 'Activating…' : 'Activate verified release'}</ActionButton></FormActions>
              </>
            ) : (
              <Notice $remote><ClockIcon /><span>Activation stays unavailable until every prerequisite is green. Complete authority records from the child or family profiles, then return here and refresh.</span></Notice>
            )}
          </>}
        </ActivationPanel>}
        {facilityImpact && selectedFacility?.status === 'active' && facilityDraft.status === 'inactive' && <Section>
          <legend>Deactivation impact</legend>
          <Field $wide><span>Operational records affected</span><div>{facilityImpact.active_programs} active programs · {facilityImpact.active_rooms} active rooms · {facilityImpact.open_enrollments} open enrollments · {facilityImpact.open_attendance_intervals} open attendance intervals · {facilityImpact.active_staff_assignments} active staff assignments · {facilityImpact.open_staff_shifts} open staff shifts</div></Field>
          {facilityImpact.blockers.length > 0 && <Field $wide><span>Blockers</span><div role="alert">{facilityImpact.blockers.map((item) => <div key={item}>• {item}</div>)}</div></Field>}
          {facilityImpact.warnings.length > 0 && <Field $wide><span>Warnings to acknowledge</span><div>{facilityImpact.warnings.map((item) => <div key={item}>• {item}</div>)}</div></Field>}
          <Field $wide><span>Type {facilityImpact.confirmation_text} exactly</span><input disabled={!facilityImpact.can_deactivate} value={facilityConfirmation} onChange={(event) => setFacilityConfirmation(event.target.value)} autoComplete="off" /></Field>
          <Field $wide><span>Reason for deactivation</span><input disabled={!facilityImpact.can_deactivate} value={facilityDeactivationReason} onChange={(event) => setFacilityDeactivationReason(event.target.value)} placeholder="Required for the audit record" /></Field>
        </Section>}
        <FormActions><ActionButton type="button" onClick={resetFacilityDraft}>Reset unsaved</ActionButton><ActionButton type="submit" $variant="primary" disabled={saving || !canManageFacility || Boolean(facilityImpact && !facilityImpact.can_deactivate)}>{saving ? 'Saving…' : facilityImpact ? 'Confirm deactivation' : 'Save facility'}</ActionButton></FormActions>
      </Form>
    ) : <div><PanelHeader><div><Eyebrow><MapPinIcon width={14} /> Facility</Eyebrow><h2>No facility configured.</h2><p>Complete organization onboarding to create the first licensed location.</p></div></PanelHeader></div>)}
    {tab === 'profile' && <Form onSubmit={saveProfile}><PanelHeader><div><Eyebrow><IdentificationIcon width={14} /> My profile</Eyebrow><h2>Your CareSync identity.</h2><p>Your name and email identify actions performed in CareSync. Email verification is read only here.</p></div>{emailVerification ? verificationMark(emailVerification) : <StatusChip $tone="neutral">Email status unavailable</StatusChip>}</PanelHeader><Section><legend>Personal details</legend><Field><span>First name</span><input required autoComplete="given-name" value={profile.first_name} onChange={(e) => setProfile((v) => ({ ...v, first_name: e.target.value }))} /></Field><Field><span>Last name</span><input required autoComplete="family-name" value={profile.last_name} onChange={(e) => setProfile((v) => ({ ...v, last_name: e.target.value }))} /></Field><Field $wide><span>Email address</span><input required type="email" autoComplete="email" value={profile.email} onChange={(e) => setProfile((v) => ({ ...v, email: e.target.value }))} /></Field></Section><FormActions><ActionButton type="button" onClick={resetProfileDraft}>Reset unsaved</ActionButton><ActionButton type="submit" $variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</ActionButton></FormActions></Form>}
    {tab === 'security' && <Form onSubmit={changePassword}><PanelHeader><div><Eyebrow><KeyIcon width={14} /> Account security</Eyebrow><h2>Change your password.</h2><p>This self-service control is available to every active staff member. A current password is required.</p></div><StatusChip $tone="info">Self-service</StatusChip></PanelHeader><Section><legend>Password confirmation</legend><Field $wide><span>Current password</span><input required type="password" autoComplete="current-password" value={password.current} onChange={(e) => setPassword((v) => ({ ...v, current: e.target.value }))} /></Field><Field><span>New password</span><input required minLength={10} type="password" autoComplete="new-password" value={password.next} onChange={(e) => setPassword((v) => ({ ...v, next: e.target.value }))} /></Field><Field><span>Confirm new password</span><input required minLength={10} type="password" autoComplete="new-password" value={password.confirm} onChange={(e) => setPassword((v) => ({ ...v, confirm: e.target.value }))} /></Field></Section><Notice><ClockIcon /><span>Changing your password ends this session immediately. Sign in again with the new password.</span></Notice><FormActions><ActionButton type="submit" $variant="primary" disabled={saving}>{saving ? 'Changing…' : 'Change password'}</ActionButton></FormActions></Form>}
  </Panel></Layout>;

  return <Page><Header><div><Eyebrow><ShieldCheckIcon width={14} /> Account controls</Eyebrow><h1>Settings, clearly scoped.</h1><p>Manage your profile and password; organization controls appear only when your permissions allow them.</p></div><HeaderSignal><StatusChip $tone={organizationReady ? 'success' : 'warning'}>{organizationReady ? 'Organization context confirmed' : 'Writes safely blocked'}</StatusChip><small>{session.organization?.name || 'Secure context required'}</small></HeaderSignal></Header>{content}</Page>;
}

import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  ClipboardDocumentCheckIcon,
  HomeModernIcon,
  IdentificationIcon,
  LockClosedIcon,
  MapPinIcon,
  PlusIcon,
  ShieldCheckIcon,
  SparklesIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { CareSyncMark } from '../../components/brand/CareSyncMark';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useSession } from '../../auth/SessionContext';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  CANADIAN_PROVINCE_OPTIONS,
  CANADIAN_TIMEZONE_OPTIONS,
  ROOM_AGE_GROUP_OPTIONS,
  includesDomainValue,
} from '../../models/domainOptions';
import { PROGRAM_TYPES, PROGRAM_TYPE_LABELS, formatProgramType, type ProgramType } from '../../models/programTypes';
import { onboardingApi } from './onboardingApi';
import {
  draftFromResponse,
  createEmptyRoomDraft,
  EMPTY_ONBOARDING_DRAFT,
  reconcileCareStructure,
  recoverCareStructureIds,
  STEP_ORDER,
  validateFacility,
  validateOrganization,
  validateRooms,
  type DraftErrors,
} from './onboardingModel';
import type { OnboardingDraft, OnboardingResponse, OnboardingStep } from './types';

const stepMeta: Array<{ id: OnboardingStep; label: string; short: string; icon: typeof IdentificationIcon }> = [
  { id: 'organization', label: 'Organization', short: 'Operating identity', icon: IdentificationIcon },
  { id: 'facility', label: 'First facility', short: 'Licensed location', icon: BuildingOffice2Icon },
  { id: 'rooms', label: 'Program & room', short: 'Care structure', icon: HomeModernIcon },
  { id: 'review', label: 'Review', short: 'Activate Basic', icon: ClipboardDocumentCheckIcon },
];

const Page = styled.main`
  min-height: 100vh;
  padding: 18px;
  background: ${({ theme }) => theme.color.canvas};
  @media (max-width: 700px) { padding: 10px; }
`;

const Shell = styled.div`
  display: grid;
  min-height: calc(100vh - 36px);
  grid-template-columns: 310px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 22px 22px 8px 22px;
  background: ${({ theme }) => theme.color.surface};
  box-shadow: ${({ theme }) => theme.shadow.panel};
  @media (max-width: 920px) { grid-template-columns: 1fr; }
`;

const Rail = styled.aside`
  position: relative;
  display: flex;
  min-height: 100%;
  flex-direction: column;
  padding: 28px 22px;
  overflow: hidden;
  border-right: 1px solid ${({ theme }) => theme.color.border};
  background: radial-gradient(circle at 20% 15%, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 6%, transparent), transparent 34%), ${({ theme }) => theme.color.canvasElevated};
  &::after { position:absolute; right:-150px; bottom:8%; width:320px; height:320px; content:''; border:1px dashed color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 70%, ${({ theme }) => theme.color.cyan}); border-radius:50%; opacity:.48; }
  @media (max-width: 920px) { min-height:auto; border-right:0; border-bottom:1px solid ${({ theme }) => theme.color.border}; }
`;

const Brand = styled.div`
  position: relative;
  z-index: 1;
  display:flex;
  align-items:center;
  gap:12px;
  strong { display:block; font-family:'CareSync Display',sans-serif; font-size:1.05rem; }
  span { display:block; color:${({ theme }) => theme.color.textMuted}; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; }
`;

const RailIntro = styled.div`
  position:relative; z-index:1; margin:38px 0 24px;
  h1 { margin:12px 0 9px; font-family:'CareSync Display',sans-serif; font-size:1.75rem; font-weight:520; letter-spacing:-.055em; line-height:1.05; }
  p { margin:0; color:${({ theme }) => theme.color.textMuted}; font-size:.8125rem; line-height:1.65; }
  @media(max-width:920px){margin:25px 0 18px; h1{font-size:1.45rem;}}
`;

const Steps = styled.nav`
  position:relative; z-index:1; display:grid; gap:7px;
  @media(max-width:920px){grid-template-columns:repeat(4,1fr);}
  @media(max-width:650px){grid-template-columns:1fr 1fr;}
`;

const StepButton = styled.button<{ $active: boolean; $complete: boolean }>`
  display:grid;
  grid-template-columns:38px 1fr auto;
  align-items:center;
  gap:11px;
  min-height:58px;
  padding:9px 11px;
  border:1px solid ${({ $active, theme }) => $active ? theme.color.borderStrong : 'transparent'};
  border-radius:13px 13px 5px 13px;
  color:${({ $active, theme }) => $active ? theme.color.text : theme.color.textSoft};
  text-align:left;
  background:${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 86%, ${theme.color.plasma})` : 'transparent'};
  cursor:pointer;
  &:disabled{cursor:not-allowed;opacity:.5;}
  > svg:first-child{width:20px;margin:auto;color:${({ $complete, theme }) => $complete ? theme.color.mint : theme.color.cyan};}
  strong{display:block;font-size:.8125rem;} small{display:block;margin-top:2px;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;}
  > svg:last-child{width:16px;color:${({ theme }) => theme.color.mint};}
  @media(max-width:920px){grid-template-columns:28px 1fr; > svg:last-child{display:none;} small{display:none;}}
`;

const RailBottom = styled.div`
  position:relative; z-index:1; display:grid; gap:8px; margin-top:auto; padding-top:28px;
  span{color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.5;}
  button{width:100%;}
  @media(max-width:920px){display:none;}
`;

const Workspace = styled.section`display:grid; grid-template-rows:auto 1fr; min-width:0;`;

const Topbar = styled.header`
  display:flex;
  min-height:72px;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  padding:13px 26px;
  border-bottom:1px solid ${({ theme }) => theme.color.border};
  div:first-child{min-width:0;} strong{display:block;font-size:.8125rem;} small{display:block;overflow:hidden;margin-top:2px;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;text-overflow:ellipsis;white-space:nowrap;}
  @media(max-width:600px){padding:12px 16px; > span{display:none;}}
`;

const Content = styled.div`display:grid; align-content:start; width:min(980px,100%); margin:0 auto; padding:clamp(24px,5vw,60px);`;

const PanelHeader = styled.div`
  display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:28px;
  h2{margin:12px 0 8px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.65rem,3vw,2.25rem);font-weight:500;letter-spacing:-.04em;line-height:1.08;}
  p{max-width:660px;margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.875rem;line-height:1.65;}
  @media(max-width:650px){display:block; > span{margin-top:14px;}}
`;

const Form = styled.form`display:grid; gap:18px;`;
const Section = styled(GlassPanel)`display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:clamp(20px,4vw,30px); @media(max-width:650px){grid-template-columns:1fr;}`;
const SectionTitle = styled.div`grid-column:1/-1; margin-bottom:2px; h3{margin:0 0 4px;font-size:.875rem;} p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.55;}`;

const LicenseChoices = styled.div`
  display:grid; grid-column:1/-1; grid-template-columns:1fr 1fr; gap:11px;
  @media(max-width:650px){grid-template-columns:1fr;}
`;
const LicenseChoice = styled.label<{ $selected: boolean }>`
  display:grid; grid-template-columns:20px 1fr; gap:10px; min-height:76px; align-items:start; padding:15px;
  border:1px solid ${({ $selected, theme }) => $selected ? theme.color.borderStrong : theme.color.border}; border-radius:13px 13px 5px 13px;
  background:${({ $selected, theme }) => $selected ? `color-mix(in srgb, ${theme.color.surfaceStrong} 86%, ${theme.color.plasma})` : theme.color.surfaceStrong};
  cursor:pointer; transition:border-color .16s ease, background .16s ease;
  input{width:17px;height:17px;margin:1px 0 0;accent-color:${({ theme }) => theme.color.plasma};}
  strong{display:block;color:${({ theme }) => theme.color.text};font-size:.8125rem;}
  small{display:block;margin-top:5px;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.5;}
  &:hover{border-color:${({ theme }) => theme.color.borderStrong};}
`;
const ProgramConfiguration = styled.div`
  display:grid; grid-column:1/-1; grid-template-columns:1fr 1fr; gap:16px; padding:18px;
  border:1px solid ${({ theme }) => theme.color.border}; border-radius:14px; background:${({ theme }) => theme.color.surfaceStrong};
  @media(max-width:650px){grid-template-columns:1fr;}
`;
const ProgramHeading = styled.div`
  display:flex; grid-column:1/-1; align-items:center; justify-content:space-between; gap:12px;
  strong{font-size:.8125rem;} span{color:${({ theme }) => theme.color.mint};font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;}
`;
const AddRoomRow = styled.div`
  display:flex; grid-column:1/-1; align-items:center; justify-content:space-between; gap:12px;
  p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.5;}
`;

const Field = styled.div<{ $wide?: boolean }>`
  display:grid; gap:7px; ${({ $wide }) => $wide && 'grid-column:1/-1;'}
  label{color:${({ theme }) => theme.color.textSoft};font-size:.75rem;font-weight:600;letter-spacing:.02em;}
  input,select{width:100%;min-height:47px;padding:0 12px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:11px;outline:0;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font-size:.8125rem;}
  input:focus,select:focus{border-color:${({ theme }) => theme.color.cyan};box-shadow:0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent);}
  input[aria-invalid='true']{border-color:${({ theme }) => theme.color.coral};}
  small{color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.5;}
`;

const FieldError = styled.span`color:${({ theme }) => theme.color.coral};font-size:.75rem;line-height:1.4;`;
const FormActions = styled.div`
  display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:4px;
  >div{display:flex;gap:9px;}
  @media(max-width:560px){align-items:stretch;flex-direction:column-reverse; >div{display:grid;grid-template-columns:1fr 1fr;} button{width:100%;}}
`;

const Notice = styled.div<{ $error?: boolean }>`
  display:flex; align-items:flex-start; gap:9px; padding:12px 14px; border:1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.mint}; border-radius:12px 12px 4px 12px; color:${({ $error, theme }) => $error ? theme.color.coral : theme.color.mint}; background:${({ $error, theme }) => $error ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.coral})` : `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.mint})`}; font-size:.8125rem; line-height:1.55;
  svg{width:18px;flex:0 0 auto;}
`;

const Gate = styled(GlassPanel)`
  display:grid; min-height:430px; place-items:center; padding:40px; text-align:center;
  div{display:grid;max-width:500px;gap:14px;} svg{width:54px;margin:0 auto;color:${({ theme }) => theme.color.cyan};} h2{margin:0;font-family:'CareSync Display',sans-serif;font-size:2rem;letter-spacing:-.04em;} p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.8125rem;line-height:1.65;} button{width:100%;}
`;

const ReviewGrid = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:12px;@media(max-width:700px){grid-template-columns:1fr;}`;
const ReviewCard = styled(GlassPanel)`padding:22px; h3{display:flex;align-items:center;gap:9px;margin:0 0 16px;font-size:.8125rem;} h3 svg{width:19px;color:${({ theme }) => theme.color.cyan};} dl{display:grid;gap:10px;margin:0;} div{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid ${({ theme }) => theme.color.divider};padding-bottom:8px;} dt{color:${({ theme }) => theme.color.textMuted};font-size:.72rem;} dd{margin:0;text-align:right;color:${({ theme }) => theme.color.textSoft};font-size:.8125rem;}`;
const Completion = styled(GlassPanel)`display:grid;gap:16px;padding:clamp(28px,6vw,55px);text-align:center;>svg{width:62px;margin:0 auto;color:${({ theme }) => theme.color.mint};}h2{margin:0;font-family:'CareSync Display',sans-serif;font-size:2.4rem;letter-spacing:-.045em;}p{max-width:560px;margin:0 auto;color:${({ theme }) => theme.color.textMuted};font-size:.875rem;line-height:1.65;}button{width:min(340px,100%);margin:0 auto;}`;

function optional(value: string): string | null { return value.trim() || null; }
function integerOrNull(value: string): number | null { return value.trim() ? Number(value) : null; }

function ErrorFor({ errors, name }: { errors: DraftErrors; name: string }) {
  return errors[name] ? <FieldError id={`${name}-error`} role="alert">{errors[name]}</FieldError> : null;
}

function ReviewValue({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children || 'Not provided'}</dd></div>;
}

export default function OnboardingPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [remote, setRemote] = useState<OnboardingResponse | null>(null);
  const [draft, setDraft] = useState<OnboardingDraft>(EMPTY_ONBOARDING_DRAFT);
  const [step, setStep] = useState<OnboardingStep>('organization');
  const [completed, setCompleted] = useState<OnboardingStep[]>([]);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = useRef(false);
  const organizationId = session.user?.organization_id || '';

  useRealtimeRefresh({
    scope: 'onboarding', organizationId, enabled: session.status === 'authenticated',
    entityTypes: featureIntegrationManifest.onboarding.realtimeEntities,
    refresh: async () => {
      const response = await onboardingApi.get();
      let nextDraft = draftFromResponse(response);
      const facility = response.facilities[0];
      if (facility) {
        const [programs, rooms] = await Promise.all([onboardingApi.programs(facility.id), onboardingApi.rooms(facility.id)]);
        nextDraft = reconcileCareStructure(nextDraft, programs, rooms);
      }
      setRemote(response);
      setCompleted(response.completed_steps.filter((item): item is OnboardingStep => STEP_ORDER.includes(item)));
      if (dirty.current) setNotice({ message: 'Organization setup changed in another session. Your unsaved fields were preserved; save or reload before continuing.', error: true });
      else { setDraft(nextDraft); setStep(STEP_ORDER.includes(response.current_step as OnboardingStep) ? response.current_step as OnboardingStep : 'organization'); }
      setLoadState('ready');
    },
  });

  useEffect(() => {
    if (session.status !== 'authenticated') return;
    const controller = new AbortController();
    setLoadState('loading');
    onboardingApi.get(controller.signal).then(async (response) => {
      if (controller.signal.aborted) return;
      let nextDraft = draftFromResponse(response);
      const facility = response.facilities[0];
      if (facility) {
        const [programs, rooms] = await Promise.all([
          onboardingApi.programs(facility.id, controller.signal),
          onboardingApi.rooms(facility.id, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        nextDraft = reconcileCareStructure(nextDraft, programs, rooms);
      }
      setRemote(response);
      setDraft(nextDraft);
      dirty.current = false;
      setCompleted(response.completed_steps.filter((item): item is OnboardingStep => STEP_ORDER.includes(item)));
      setStep(STEP_ORDER.includes(response.current_step as OnboardingStep) ? response.current_step as OnboardingStep : 'organization');
      setLoadState('ready');
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) {
        setNotice({ message: caught instanceof Error ? caught.message : 'Onboarding could not be loaded.', error: true });
        setLoadState('error');
      }
    });
    return () => controller.abort();
  }, [session.status]);

  const currentIndex = STEP_ORDER.indexOf(step);
  const progress = useMemo(() => remote?.status === 'complete' ? 100 : Math.round((currentIndex / (STEP_ORDER.length - 1)) * 100), [currentIndex, remote?.status]);

  const updateOrganization = (field: keyof OnboardingDraft['organization'], value: string) => { dirty.current = true; setDraft((current) => ({ ...current, organization: { ...current.organization, [field]: value } })); };
  const updateFacility = (field: keyof OnboardingDraft['facility'], value: string) => { dirty.current = true; setDraft((current) => ({ ...current, facility: { ...current.facility, [field]: value } })); };
  const updateProgram = (type: ProgramType, field: keyof OnboardingDraft['programs'][ProgramType], value: string) => { dirty.current = true; setDraft((current) => ({
    ...current,
    programs: { ...current.programs, [type]: { ...current.programs[type], [field]: value } },
  })); };
  const updateRoom = (draftKey: string, field: keyof OnboardingDraft['rooms'][number], value: string) => { dirty.current = true; setDraft((current) => ({
    ...current,
    rooms: current.rooms.map((room) => room.draftKey === draftKey ? { ...room, [field]: value } : room),
  })); };

  const addRoom = () => {
    dirty.current = true;
    const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setDraft((current) => ({
      ...current,
      rooms: [...current.rooms, {
        ...createEmptyRoomDraft(`room-${suffix}`),
        programType: current.selectedProgramTypes[0] || '',
      }],
    }));
  };

  const removeRoom = (draftKey: string) => { dirty.current = true; setDraft((current) => {
    const room = current.rooms.find((candidate) => candidate.draftKey === draftKey);
    if (!room || current.rooms.length === 1) return current;
    return {
      ...current,
      rooms: current.rooms.filter((candidate) => candidate.draftKey !== draftKey),
      archivedRoomIds: room.id
        ? [...new Set([...current.archivedRoomIds, room.id])]
        : current.archivedRoomIds,
    };
  }); };

  const toggleProgramType = (type: ProgramType) => { dirty.current = true; setDraft((current) => {
    const selected = current.selectedProgramTypes.includes(type)
      ? current.selectedProgramTypes.filter((item) => item !== type)
      : PROGRAM_TYPES.filter((item) => [...current.selectedProgramTypes, type].includes(item));
    const rooms = current.rooms.map((room) => ({
      ...room,
      programType: room.programType && selected.includes(room.programType) ? room.programType : selected[0] || '',
    }));
    return { ...current, selectedProgramTypes: selected, rooms };
  }); };

  const finishStep = async (finished: OnboardingStep, next: OnboardingStep, nextDraft = draft) => {
    const nextCompleted = [...new Set([...completed, finished])] as OnboardingStep[];
    const response = await onboardingApi.save({ current_step: next, completed_steps: nextCompleted, draft: nextDraft as unknown as Record<string, unknown> });
    dirty.current = false; setRemote(response); setCompleted(nextCompleted); setStep(next); setNotice({ message: 'Progress saved. You can safely return later.', error: false });
  };

  const saveOrganization = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateOrganization(draft.organization); setErrors(nextErrors); setNotice(null);
    if (Object.keys(nextErrors).length) return;
    setBusy(true);
    try {
      await onboardingApi.updateOrganization({ name: draft.organization.name.trim(), legal_name: optional(draft.organization.legalName), email: optional(draft.organization.email), phone: optional(draft.organization.phone), timezone: draft.organization.timezone });
      await finishStep('organization', 'facility');
    } catch (caught) { setNotice({ message: caught instanceof Error ? caught.message : 'Organization details could not be saved.', error: true }); }
    finally { setBusy(false); }
  };

  const saveFacility = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateFacility(draft.facility); setErrors(nextErrors); setNotice(null);
    if (Object.keys(nextErrors).length) return;
    setBusy(true);
    try {
      const payload = { name: draft.facility.name.trim(), license_number: optional(draft.facility.licenseNumber), email: optional(draft.facility.email), phone: optional(draft.facility.phone), street_address: draft.facility.streetAddress.trim(), city: draft.facility.city.trim(), province: draft.facility.province.trim(), postal_code: draft.facility.postalCode.trim().toUpperCase(), timezone: draft.facility.timezone, licensed_capacity: Number(draft.facility.licensedCapacity), opening_time: draft.facility.openingTime || null, closing_time: draft.facility.closingTime || null, status: 'active' };
      const facility = draft.facility.id ? await onboardingApi.updateFacility(draft.facility.id, payload) : await onboardingApi.createFacility(payload);
      const nextDraft = { ...draft, facility: { ...draft.facility, id: facility.id } };
      setDraft(nextDraft);
      await finishStep('facility', 'rooms', nextDraft);
    } catch (caught) { setNotice({ message: caught instanceof Error ? caught.message : 'Facility details could not be saved.', error: true }); }
    finally { setBusy(false); }
  };

  const saveRooms = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateRooms(draft); setErrors(nextErrors); setNotice(null);
    if (Object.keys(nextErrors).length || !draft.facility.id) {
      if (!draft.facility.id) setNotice({ message: 'Save the facility before creating its programs and rooms.', error: true });
      return;
    }
    setBusy(true);
    try {
      const [existingPrograms, existingRooms] = await Promise.all([
        onboardingApi.programs(draft.facility.id),
        onboardingApi.rooms(draft.facility.id),
      ]);
      let workingDraft = recoverCareStructureIds(draft, existingPrograms, existingRooms);
      if (workingDraft !== draft) setDraft(workingDraft);
      const checkpointDraft = async (nextDraft: OnboardingDraft) => {
        setDraft(nextDraft);
        const checkpoint = await onboardingApi.save({ current_step: 'rooms', completed_steps: completed, draft: nextDraft as unknown as Record<string, unknown> });
        setRemote(checkpoint);
      };
      for (const type of workingDraft.selectedProgramTypes) {
        const programDraft = workingDraft.programs[type];
        const programValues = { name: programDraft.name.trim(), program_type: type, capacity: Number(programDraft.capacity), minimum_age_months: integerOrNull(programDraft.minimumAgeMonths), maximum_age_months: integerOrNull(programDraft.maximumAgeMonths), is_active: true };
        const program = programDraft.id
          ? await onboardingApi.updateProgram(programDraft.id, programValues)
          : await onboardingApi.createProgram({ facility_id: draft.facility.id, ...programValues });
        workingDraft = {
          ...workingDraft,
          programs: { ...workingDraft.programs, [type]: { ...programDraft, id: program.id } },
        };
        await checkpointDraft(workingDraft);
      }
      for (const roomDraft of workingDraft.rooms) {
        const assignedType = roomDraft.programType;
        const programId = assignedType ? workingDraft.programs[assignedType].id : null;
        if (!programId) throw new Error(`Choose a saved program for ${roomDraft.name || 'each room'}.`);
        const roomValues = { program_id: programId, name: roomDraft.name.trim(), capacity: Number(roomDraft.capacity), age_group: optional(roomDraft.ageGroup), is_active: true };
        const room = roomDraft.id
          ? await onboardingApi.updateRoom(roomDraft.id, roomValues)
          : await onboardingApi.createRoom({ facility_id: draft.facility.id, ...roomValues });
        workingDraft = {
          ...workingDraft,
          rooms: workingDraft.rooms.map((candidate) => candidate.draftKey === roomDraft.draftKey ? { ...candidate, id: room.id } : candidate),
        };
        await checkpointDraft(workingDraft);
      }
      for (const roomId of workingDraft.archivedRoomIds) {
        if (workingDraft.rooms.some((room) => room.id === roomId)) continue;
        await onboardingApi.updateRoom(roomId, { is_active: false });
        workingDraft = { ...workingDraft, archivedRoomIds: workingDraft.archivedRoomIds.filter((id) => id !== roomId) };
        await checkpointDraft(workingDraft);
      }
      await finishStep('rooms', 'review', workingDraft);
    } catch (caught) { setNotice({ message: caught instanceof Error ? caught.message : 'The programs and rooms could not be fully saved.', error: true }); }
    finally { setBusy(false); }
  };

  const activate = async () => {
    setBusy(true); setNotice(null);
    try {
      const response = await onboardingApi.complete();
      dirty.current = false; setRemote(response); setCompleted([...STEP_ORDER]);
      session.retry();
    } catch (caught) { setNotice({ message: caught instanceof Error ? caught.message : 'The workspace did not pass activation checks.', error: true }); }
    finally { setBusy(false); }
  };

  const selectStep = (next: OnboardingStep) => {
    if (STEP_ORDER.indexOf(next) <= currentIndex || completed.includes(next)) { setErrors({}); setNotice(null); setStep(next); }
  };

  let content: ReactNode;
  if (session.status === 'anonymous') {
    content = <Gate $accent="amber"><div><LockClosedIcon /><h2>Owner sign-in required.</h2><p>Onboarding changes organization and facility records, so it never opens without a verified owner session.</p><ActionButton $variant="primary" onClick={() => navigate('/login')}>Sign in <ArrowRightIcon /></ActionButton></div></Gate>;
  } else if (loadState === 'loading' || session.status === 'checking') {
    content = <Gate $accent="cyan" aria-busy="true"><div><ArrowPathIcon /><h2>Restoring your setup.</h2><p>CareSync is loading the saved onboarding state and any facility, program, or room already created.</p></div></Gate>;
  } else if (loadState === 'error') {
    content = <Gate $accent="amber"><div><ShieldCheckIcon /><h2>Setup stayed safely locked.</h2><p>{notice?.message || 'CareSync could not restore onboarding.'}</p><ActionButton $variant="primary" onClick={() => window.location.reload()}><ArrowPathIcon /> Retry setup</ActionButton></div></Gate>;
  } else if (remote?.status === 'complete') {
    content = <Completion $accent="cyan"><CheckCircleIcon /><StatusChip $tone="success">Basic workspace active</StatusChip><h2>Your operating foundation is ready.</h2><p>The organization, first facility, licensed programs, and configured rooms passed activation checks. You can now begin the Basic operating path with real records.</p><ActionButton $variant="primary" onClick={() => navigate('/dashboard', { replace: true })}>Open dashboard <ArrowRightIcon /></ActionButton></Completion>;
  } else if (step === 'organization') {
    content = <>
      <PanelHeader><div><Eyebrow><IdentificationIcon width={14} /> Step 1 of 4</Eyebrow><h2>Identify the organization.</h2><p>Start with the legal and operating identity that owns this CareSync workspace. Facility details come next.</p></div><StatusChip $tone="info">Autosaved by step</StatusChip></PanelHeader>
      {notice && <Notice $error={notice.error} role={notice.error ? 'alert' : 'status'}>{notice.error ? <ShieldCheckIcon /> : <CheckCircleIcon />}{notice.message}</Notice>}
      <Form onSubmit={saveOrganization} noValidate>
        <Section $accent="plasma">
          <SectionTitle><h3>Organization identity</h3><p>The operating name appears throughout the workspace.</p></SectionTitle>
          <Field><label htmlFor="organization-name">Operating name *</label><input id="organization-name" value={draft.organization.name} onChange={(event) => updateOrganization('name', event.target.value)} aria-invalid={Boolean(errors['organization.name'])} /><ErrorFor errors={errors} name="organization.name" /></Field>
          <Field><label htmlFor="organization-legal">Legal name</label><input id="organization-legal" value={draft.organization.legalName} onChange={(event) => updateOrganization('legalName', event.target.value)} /></Field>
          <Field><label htmlFor="organization-email">Organization email</label><input id="organization-email" type="email" value={draft.organization.email} onChange={(event) => updateOrganization('email', event.target.value)} aria-invalid={Boolean(errors['organization.email'])} /><ErrorFor errors={errors} name="organization.email" /></Field>
          <Field><label htmlFor="organization-phone">Organization phone</label><input id="organization-phone" type="tel" value={draft.organization.phone} onChange={(event) => updateOrganization('phone', event.target.value)} /></Field>
          <Field $wide><label htmlFor="organization-timezone">Timezone *</label><select id="organization-timezone" value={draft.organization.timezone} onChange={(event) => updateOrganization('timezone', event.target.value)}>{draft.organization.timezone && !includesDomainValue(CANADIAN_TIMEZONE_OPTIONS, draft.organization.timezone) && <option value={draft.organization.timezone}>Current saved timezone · {draft.organization.timezone}</option>}{CANADIAN_TIMEZONE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
        </Section>
        <FormActions><span /><div><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? 'Saving…' : 'Save & continue'} <ArrowRightIcon /></ActionButton></div></FormActions>
      </Form>
    </>;
  } else if (step === 'facility') {
    content = <>
      <PanelHeader><div><Eyebrow><MapPinIcon width={14} /> Step 2 of 4</Eyebrow><h2>Describe the first facility.</h2><p>This is the licensed location where rooms, enrollment, and actual attendance will belong.</p></div><StatusChip $tone="warning">One facility required</StatusChip></PanelHeader>
      {notice && <Notice $error={notice.error}>{notice.error ? <ShieldCheckIcon /> : <CheckCircleIcon />}{notice.message}</Notice>}
      <Form onSubmit={saveFacility} noValidate>
        <Section $accent="cyan">
          <SectionTitle><h3>Facility identity and location</h3><p>Required location fields establish a useful operating record; licence number can be added when available.</p></SectionTitle>
          <Field><label htmlFor="facility-name">Facility name *</label><input id="facility-name" value={draft.facility.name} onChange={(event) => updateFacility('name', event.target.value)} aria-invalid={Boolean(errors['facility.name'])} /><ErrorFor errors={errors} name="facility.name" /></Field>
          <Field><label htmlFor="facility-license">Alberta licence number</label><input id="facility-license" value={draft.facility.licenseNumber} onChange={(event) => updateFacility('licenseNumber', event.target.value)} /></Field>
          <Field $wide><label htmlFor="facility-address">Street address *</label><input id="facility-address" value={draft.facility.streetAddress} onChange={(event) => updateFacility('streetAddress', event.target.value)} aria-invalid={Boolean(errors['facility.streetAddress'])} /><ErrorFor errors={errors} name="facility.streetAddress" /></Field>
          <Field><label htmlFor="facility-city">City *</label><input id="facility-city" value={draft.facility.city} onChange={(event) => updateFacility('city', event.target.value)} aria-invalid={Boolean(errors['facility.city'])} /><ErrorFor errors={errors} name="facility.city" /></Field>
          <Field><label htmlFor="facility-province">Province or territory *</label><select id="facility-province" value={draft.facility.province} onChange={(event) => updateFacility('province', event.target.value)} aria-invalid={Boolean(errors['facility.province'])}>{draft.facility.province && !includesDomainValue(CANADIAN_PROVINCE_OPTIONS, draft.facility.province) && <option value={draft.facility.province}>Current saved value · {draft.facility.province}</option>}{CANADIAN_PROVINCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><ErrorFor errors={errors} name="facility.province" /></Field>
          <Field><label htmlFor="facility-postal">Postal code *</label><input id="facility-postal" value={draft.facility.postalCode} onChange={(event) => updateFacility('postalCode', event.target.value)} placeholder="T2P 1J9" aria-invalid={Boolean(errors['facility.postalCode'])} /><ErrorFor errors={errors} name="facility.postalCode" /></Field>
          <Field><label htmlFor="facility-capacity">Licensed capacity *</label><input id="facility-capacity" type="number" min="1" step="1" value={draft.facility.licensedCapacity} onChange={(event) => updateFacility('licensedCapacity', event.target.value)} aria-invalid={Boolean(errors['facility.licensedCapacity'])} /><ErrorFor errors={errors} name="facility.licensedCapacity" /></Field>
        </Section>
        <Section $accent="plasma">
          <SectionTitle><h3>Contact and operating hours</h3><p>Facility contact can differ from organization contact.</p></SectionTitle>
          <Field><label htmlFor="facility-email">Facility email</label><input id="facility-email" type="email" value={draft.facility.email} onChange={(event) => updateFacility('email', event.target.value)} aria-invalid={Boolean(errors['facility.email'])} /><ErrorFor errors={errors} name="facility.email" /></Field>
          <Field><label htmlFor="facility-phone">Facility phone</label><input id="facility-phone" type="tel" value={draft.facility.phone} onChange={(event) => updateFacility('phone', event.target.value)} /></Field>
          <Field><label htmlFor="facility-open">Opening time *</label><input id="facility-open" type="time" value={draft.facility.openingTime} onChange={(event) => updateFacility('openingTime', event.target.value)} /></Field>
          <Field><label htmlFor="facility-close">Closing time *</label><input id="facility-close" type="time" value={draft.facility.closingTime} onChange={(event) => updateFacility('closingTime', event.target.value)} aria-invalid={Boolean(errors['facility.closingTime'])} /><ErrorFor errors={errors} name="facility.closingTime" /></Field>
          <Field $wide><label htmlFor="facility-timezone">Timezone *</label><select id="facility-timezone" value={draft.facility.timezone} onChange={(event) => updateFacility('timezone', event.target.value)}>{draft.facility.timezone && !includesDomainValue(CANADIAN_TIMEZONE_OPTIONS, draft.facility.timezone) && <option value={draft.facility.timezone}>Current saved timezone · {draft.facility.timezone}</option>}{CANADIAN_TIMEZONE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
        </Section>
        <FormActions><ActionButton type="button" onClick={() => setStep('organization')}><ArrowLeftIcon /> Back</ActionButton><div><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? 'Saving facility…' : 'Save & continue'} <ArrowRightIcon /></ActionButton></div></FormActions>
      </Form>
    </>;
  } else if (step === 'rooms') {
    content = <>
      <PanelHeader>
        <div>
          <Eyebrow><HomeModernIcon width={14} /> Step 3 of 4</Eyebrow>
          <h2>Define licensed care.</h2>
          <p>Select every licensed service this facility offers. A facility can operate Daycare, OSC, or both, with a separate name, capacity, and age range for each.</p>
        </div>
        <StatusChip $tone="warning">At least one service required</StatusChip>
      </PanelHeader>
      {notice && <Notice $error={notice.error}>{notice.error ? <ShieldCheckIcon /> : <CheckCircleIcon />}{notice.message}</Notice>}
      <Form onSubmit={saveRooms} noValidate>
        <Section $accent="plasma">
          <SectionTitle>
            <h3>Licensed services</h3>
            <p>Choose one or both. OSC is tracked separately from Daycare so capacities, rooms, and enrollment stay accurate.</p>
          </SectionTitle>
          <LicenseChoices>
            {PROGRAM_TYPES.map((type) => {
              const selected = draft.selectedProgramTypes.includes(type);
              const alreadySaved = Boolean(draft.programs[type].id);
              return <LicenseChoice key={type} $selected={selected}>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={alreadySaved && selected}
                  onChange={() => toggleProgramType(type)}
                  aria-describedby={`${type}-service-description`}
                />
                <span>
                  <strong>{PROGRAM_TYPE_LABELS[type]}</strong>
                  <small id={`${type}-service-description`}>
                    {type === 'daycare' ? 'Licensed daytime child care offered at this facility.' : 'Licensed care offered outside regular school hours and during school breaks.'}
                    {alreadySaved && selected ? ' Saved services remain selected during setup.' : ''}
                  </small>
                </span>
              </LicenseChoice>;
            })}
          </LicenseChoices>
          <ErrorFor errors={errors} name="selectedProgramTypes" />
          {draft.selectedProgramTypes.map((type) => {
            const program = draft.programs[type];
            const prefix = `programs.${type}`;
            return <ProgramConfiguration key={type}>
              <ProgramHeading><strong>{PROGRAM_TYPE_LABELS[type]} details</strong><span>Licensed service</span></ProgramHeading>
              <Field>
                <label htmlFor={`${type}-program-name`}>Program name *</label>
                <input id={`${type}-program-name`} value={program.name} onChange={(event) => updateProgram(type, 'name', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.name`])} />
                <small>A friendly operating label; the licensed type remains {PROGRAM_TYPE_LABELS[type]}.</small>
                <ErrorFor errors={errors} name={`${prefix}.name`} />
              </Field>
              <Field>
                <label htmlFor={`${type}-program-capacity`}>Program capacity *</label>
                <input id={`${type}-program-capacity`} type="number" min="1" step="1" value={program.capacity} onChange={(event) => updateProgram(type, 'capacity', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.capacity`])} />
                <ErrorFor errors={errors} name={`${prefix}.capacity`} />
              </Field>
              <Field>
                <label htmlFor={`${type}-program-min-age`}>Minimum age in months</label>
                <input id={`${type}-program-min-age`} type="number" min="0" step="1" value={program.minimumAgeMonths} onChange={(event) => updateProgram(type, 'minimumAgeMonths', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.minimumAgeMonths`])} />
                <ErrorFor errors={errors} name={`${prefix}.minimumAgeMonths`} />
              </Field>
              <Field>
                <label htmlFor={`${type}-program-max-age`}>Maximum age in months</label>
                <input id={`${type}-program-max-age`} type="number" min="0" step="1" value={program.maximumAgeMonths} onChange={(event) => updateProgram(type, 'maximumAgeMonths', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.maximumAgeMonths`])} />
                <ErrorFor errors={errors} name={`${prefix}.maximumAgeMonths`} />
              </Field>
            </ProgramConfiguration>;
          })}
        </Section>
        <Section $accent="cyan">
          <SectionTitle><h3>Care rooms</h3><p>Add every room this facility operates now. There is no artificial room limit, and every room is assigned to its licensed Daycare or OSC program.</p></SectionTitle>
          <ErrorFor errors={errors} name="rooms" />
          {draft.rooms.map((room, index) => {
            const prefix = `rooms.${room.draftKey}`;
            return <ProgramConfiguration key={room.draftKey}>
              <ProgramHeading>
                <strong>Room {index + 1}{room.name.trim() ? ` · ${room.name.trim()}` : ''}</strong>
                <ActionButton type="button" onClick={() => removeRoom(room.draftKey)} disabled={busy || draft.rooms.length === 1} title={draft.rooms.length === 1 ? 'At least one room is required.' : room.id ? 'Remove and archive this saved room when setup is saved.' : 'Remove this room.'}><TrashIcon /> Remove</ActionButton>
              </ProgramHeading>
              <Field $wide>
                <label htmlFor={`${room.draftKey}-program`}>Belongs to program *</label>
                <select id={`${room.draftKey}-program`} value={room.programType} onChange={(event) => updateRoom(room.draftKey, 'programType', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.programType`])}>
                  <option value="">Select a program</option>
                  {draft.selectedProgramTypes.map((type) => <option key={type} value={type}>{draft.programs[type].name || PROGRAM_TYPE_LABELS[type]} · {PROGRAM_TYPE_LABELS[type]}</option>)}
                </select>
                <ErrorFor errors={errors} name={`${prefix}.programType`} />
              </Field>
              <Field><label htmlFor={`${room.draftKey}-name`}>Room name *</label><input id={`${room.draftKey}-name`} value={room.name} onChange={(event) => updateRoom(room.draftKey, 'name', event.target.value)} placeholder="Infant room" aria-invalid={Boolean(errors[`${prefix}.name`])} /><ErrorFor errors={errors} name={`${prefix}.name`} /></Field>
              <Field><label htmlFor={`${room.draftKey}-capacity`}>Room capacity *</label><input id={`${room.draftKey}-capacity`} type="number" min="1" step="1" value={room.capacity} onChange={(event) => updateRoom(room.draftKey, 'capacity', event.target.value)} aria-invalid={Boolean(errors[`${prefix}.capacity`])} /><ErrorFor errors={errors} name={`${prefix}.capacity`} /></Field>
              <Field $wide><label htmlFor={`${room.draftKey}-age-group`}>Age group</label><select id={`${room.draftKey}-age-group`} value={room.ageGroup} onChange={(event) => updateRoom(room.draftKey, 'ageGroup', event.target.value)}><option value="">Mixed / not specified</option>{room.ageGroup && !includesDomainValue(ROOM_AGE_GROUP_OPTIONS, room.ageGroup) && <option value={room.ageGroup}>Current saved value · {room.ageGroup}</option>}{ROOM_AGE_GROUP_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
            </ProgramConfiguration>;
          })}
          <AddRoomRow><p>Rooms are saved one at a time with a recovery checkpoint, so an interrupted request can safely resume.</p><ActionButton type="button" onClick={addRoom} disabled={busy}><PlusIcon /> Add room</ActionButton></AddRoomRow>
        </Section>
        <FormActions><ActionButton type="button" onClick={() => setStep('facility')}><ArrowLeftIcon /> Back</ActionButton><div><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? 'Saving care structure…' : 'Save & review'} <ArrowRightIcon /></ActionButton></div></FormActions>
      </Form>
    </>;
  } else {
    content = <><PanelHeader><div><Eyebrow><ClipboardDocumentCheckIcon width={14} /> Step 4 of 4</Eyebrow><h2>Review the Basic foundation.</h2><p>Activation validates the organization, an active facility, its licensed programs, and every configured room. No family or child records are created by onboarding.</p></div><StatusChip $tone="success">Ready for validation</StatusChip></PanelHeader>{notice && <Notice $error={notice.error}>{notice.error ? <ShieldCheckIcon /> : <CheckCircleIcon />}{notice.message}</Notice>}<ReviewGrid><ReviewCard $accent="plasma"><h3><IdentificationIcon /> Organization</h3><dl><ReviewValue label="Operating name">{draft.organization.name}</ReviewValue><ReviewValue label="Legal name">{draft.organization.legalName}</ReviewValue><ReviewValue label="Email">{draft.organization.email}</ReviewValue><ReviewValue label="Timezone">{draft.organization.timezone}</ReviewValue></dl></ReviewCard><ReviewCard $accent="cyan"><h3><BuildingOffice2Icon /> Facility</h3><dl><ReviewValue label="Name">{draft.facility.name}</ReviewValue><ReviewValue label="Location">{[draft.facility.streetAddress, draft.facility.city, draft.facility.province].filter(Boolean).join(', ')}</ReviewValue><ReviewValue label="Licensed capacity">{draft.facility.licensedCapacity}</ReviewValue><ReviewValue label="Hours">{draft.facility.openingTime}–{draft.facility.closingTime}</ReviewValue></dl></ReviewCard><ReviewCard $accent="plasma"><h3><SparklesIcon /> Licensed programs</h3><dl>{draft.selectedProgramTypes.map((type) => <ReviewValue key={type} label={formatProgramType(type)}>{draft.programs[type].name} · {draft.programs[type].capacity} places</ReviewValue>)}</dl></ReviewCard>{draft.rooms.map((room, index) => <ReviewCard key={room.draftKey} $accent="cyan"><h3><HomeModernIcon /> Room {index + 1}</h3><dl><ReviewValue label="Name">{room.name}</ReviewValue><ReviewValue label="Program">{room.programType ? `${draft.programs[room.programType].name} · ${formatProgramType(room.programType)}` : ''}</ReviewValue><ReviewValue label="Capacity">{room.capacity}</ReviewValue><ReviewValue label="Age group">{room.ageGroup}</ReviewValue></dl></ReviewCard>)}</ReviewGrid><Notice><ShieldCheckIcon />Activation opens only the verified Basic workspace. Every later product module stays hidden until it receives its own tested release boundary.</Notice><FormActions><ActionButton type="button" onClick={() => setStep('rooms')}><ArrowLeftIcon /> Back</ActionButton><div><ActionButton type="button" $variant="primary" onClick={activate} disabled={busy}>{busy ? 'Validating…' : 'Activate Basic workspace'} <CheckCircleIcon /></ActionButton></div></FormActions></>;
  }

  return <Page><Shell><Rail><Brand><CareSyncMark size={43} /><div><strong>CareSync</strong><span>Basic setup</span></div></Brand><RailIntro><Eyebrow><SparklesIcon width={14} /> Guided activation</Eyebrow><h1>Set the operating boundary.</h1><p>Each completed step is saved to your organization so setup can resume safely.</p></RailIntro><Steps aria-label="Onboarding progress">{stepMeta.map((item, index) => { const isComplete = completed.includes(item.id) || remote?.status === 'complete'; const accessible = index <= currentIndex || isComplete; return <StepButton key={item.id} type="button" $active={step === item.id} $complete={isComplete} disabled={!accessible || busy} onClick={() => selectStep(item.id)}><item.icon /><span><strong>{item.label}</strong><small>{item.short}</small></span>{isComplete && <CheckCircleIcon />}</StepButton>; })}</Steps><RailBottom><span>{progress}% of the guided setup reached</span><ActionButton type="button" onClick={session.logout}>Sign out</ActionButton></RailBottom></Rail><Workspace><Topbar><div><strong>{session.organization?.name || remote?.organization.name || 'Organization setup'}</strong><small>{session.user?.email || 'Authenticated owner session required'}</small></div><StatusChip $tone={remote?.status === 'complete' ? 'success' : 'info'}>{remote?.status === 'complete' ? 'Active' : 'Setup in progress'}</StatusChip></Topbar><Content>{content}</Content></Workspace></Shell></Page>;
}

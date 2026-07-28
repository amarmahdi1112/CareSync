import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import {
  AcademicCapIcon,
  ArrowPathIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClipboardDocumentListIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  FaceSmileIcon,
  FunnelIcon,
  HandRaisedIcon,
  MagnifyingGlassIcon,
  MoonIcon,
  PencilSquareIcon,
  ShieldExclamationIcon,
  SparklesIcon,
  TrashIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, hasAnyPermission, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import { Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import { serviceDateValue } from '../../hooks/useCommandData';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import type { ProgramType } from '../../models/programTypes';
import ChildAvatar from '../children/ChildAvatar';
import { fetchRoomWorkspace, type RoomRecord, type RoomWorkspace } from '../rooms/roomsApi';
import RoomSafetyCompactSummary from '../rooms/RoomSafetyCompactSummary';
import {
  correctCareRecord,
  createCareRecord,
  fetchCareRoomDay,
  finishSleepRecord,
  voidCareRecord,
  type CareDayChild,
  type CareRecord,
  type CareRoomDay,
  type CareType,
} from './careApi';
import {
  activeRecords,
  attendanceLabel,
  attendanceTone,
  canCorrectCareRecord,
  careActionsForRoom,
  careDayCounts,
  canPresentCurrentSafety,
  careRecordDetail,
  careRecordTitle,
  childNameParts,
  formatCareTime,
  openSleep,
  safetyFlagCount,
} from './careModel';
import {
  CareCorrectionDialog,
  CareEntryDialog,
  CareHistoryDialog,
  CareVoidDialog,
  SafetyCardDialog,
  SleepFinishDialog,
  type CareCorrectionDraft,
  type CareEntryDraft,
} from './CareDialogs';
import DailyClosePreview from './DailyClosePreview';
import { fetchRoomDailyClosePreview } from './dailyCloseApi';
import {
  canOpenDailyClosePreview,
  createDailyCloseRequestGate,
  dailyCloseBoundaryKey,
  nextTodayView,
  settleQuietDailyCloseFailure,
  type DailyCloseResourceState,
  type TodayView,
} from './todayViewModel';

const arrive = keyframes`from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); }`;
const breathe = keyframes`0%,100% { opacity: .45; } 50% { opacity: 1; }`;

const Page = styled.div`display: grid; gap: 18px; min-width: 0;`;
const Header = styled.header`
  display: flex; align-items: end; justify-content: space-between; gap: 22px;
  h1 { margin: 9px 0 6px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.65rem, 3.5vw, 2.5rem); font-weight: 530; letter-spacing: -.055em; }
  p { max-width: 700px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .79rem; line-height: 1.65; }
  @media (max-width: 760px) { align-items: flex-start; flex-direction: column; }
`;
const LiveMark = styled.div`
  display: flex; align-items: center; gap: 10px; min-width: max-content; padding: 9px 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; color: ${({ theme }) => theme.color.textSoft}; background: ${({ theme }) => theme.color.surface}; font-size: .7rem;
  i { width: 7px; height: 7px; border-radius: 50%; background: ${({ theme }) => theme.color.mint}; box-shadow: 0 0 8px ${({ theme }) => theme.color.mint}; animation: ${breathe} 2s ease-in-out infinite; }
  @media (prefers-reduced-motion: reduce) { i { animation: none; } }
`;
const Scope = styled(GlassPanel)`display: grid; grid-template-columns: repeat(3, minmax(150px, 1fr)) auto; align-items: end; gap: 11px; padding: 14px; @media (max-width: 860px) { grid-template-columns: repeat(2,minmax(0,1fr)); } @media (max-width: 520px) { grid-template-columns: 1fr; }`;
const Field = styled.label`
  display: grid; gap: 6px; min-width: 0;
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; }
  select, input { width: 100%; min-height: 44px; padding: 0 11px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .76rem; }
  select:focus, input:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 15%, transparent); }
  input:disabled { cursor: not-allowed; opacity: .7; }
`;
const RefreshButton = styled(IconButton)`@media (max-width: 520px) { width: 100%; }`;
const ViewTabs = styled.div`display:flex;flex-wrap:wrap;gap:7px;padding:6px;border:1px solid ${({ theme }) => theme.color.border};border-radius:12px 5px 12px 5px;background:${({ theme }) => theme.color.surface};width:max-content;max-width:100%;`;
const ViewTab = styled.button<{ $active?: boolean }>`display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 13px;border:1px solid ${({ $active, theme }) => $active ? theme.color.cyan : 'transparent'};border-radius:10px 4px 10px 4px;color:${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textSoft};background:${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.cyan})` : 'transparent'};cursor:pointer;font:inherit;font-size:.7rem;font-weight:620;svg{width:16px;}&:disabled{cursor:not-allowed;opacity:.5;}@media(max-width:440px){flex:1;}`;
const ViewPermissionNote = styled.p`margin:-9px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.67rem;line-height:1.5;`;
const ViewPanel = styled.div`display:grid;gap:18px;min-width:0;`;
const MetricGrid = styled.div`display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 10px; @media (max-width: 1040px) { grid-template-columns: repeat(3,minmax(0,1fr)); } @media (max-width: 560px) { grid-template-columns: repeat(2,minmax(0,1fr)); }`;
const Metric = styled(GlassPanel)`padding: 13px 14px; animation: ${arrive} 260ms ease both; span { display: flex; align-items: center; gap: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; } svg { width: 16px; color: ${({ theme }) => theme.color.cyan}; } strong { display: block; margin-top: 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.5rem; font-weight: 540; } @media (prefers-reduced-motion: reduce) { animation: none; }`;
const Toolbar = styled(GlassPanel)`display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; @media (max-width: 760px) { align-items: stretch; flex-direction: column; }`;
const Search = styled.label`display: flex; align-items: center; gap: 9px; min-width: min(360px,100%); min-height: 44px; padding: 0 11px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; background: ${({ theme }) => theme.color.control}; svg { width: 18px; color: ${({ theme }) => theme.color.textMuted}; } input { width: 100%; min-height: 44px; border: 0; outline: 0; color: ${({ theme }) => theme.color.text}; background: transparent; font: inherit; font-size: .75rem; }`;
const Filters = styled.div`display: flex; flex-wrap: wrap; gap: 7px;`;
const FilterButton = styled.button<{ $active?: boolean }>`min-height: 44px; padding: 0 11px; border: 1px solid ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.controlBorder}; border-radius: 10px 4px 10px 4px; color: ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textSoft}; background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.cyan})` : theme.color.control}; cursor: pointer; font: inherit; font-size: .68rem; font-weight: 600;`;
const Notice = styled(GlassPanel)<{ $error?: boolean }>`display: flex; align-items: flex-start; gap: 10px; padding: 14px; border-color: ${({ $error, theme }) => $error ? theme.color.coral : theme.color.border}; color: ${({ $error, theme }) => $error ? theme.color.coral : theme.color.textSoft}; font-size: .75rem; line-height: 1.55; svg { width: 19px; flex: 0 0 auto; } button { min-width: 44px; min-height: 44px; margin-left: 6px; padding: 0 11px; border: 1px solid currentColor; border-radius: 9px 4px 9px 4px; color: inherit; background: transparent; cursor: pointer; font: inherit; font-weight: 650; }`;
const Roster = styled.div`display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 13px; @media (max-width: 1040px) { grid-template-columns: 1fr; }`;
const ChildCard = styled(GlassPanel)`display: grid; align-content: start; padding: 15px; animation: ${arrive} 260ms ease both; @media (prefers-reduced-motion: reduce) { animation: none; }`;
const ChildHeader = styled.div`display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; @media (max-width: 420px) { flex-direction: column; }`;
const Identity = styled.div`display: flex; align-items: center; gap: 11px; min-width: 0; h2 { overflow: hidden; margin: 0; font-size: .91rem; font-weight: 610; text-overflow: ellipsis; white-space: nowrap; } p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; }`;
const HeaderActions = styled.div`display: flex; align-items: center; gap: 7px;`;
const SafetyButton = styled.button`
  display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 10px; border: 1px solid ${({ theme }) => theme.color.amber}; border-radius: 9px 4px 9px 4px; color: ${({ theme }) => theme.color.amber}; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 92%, ${({ theme }) => theme.color.amber}); cursor: pointer; font: inherit; font-size: .65rem; font-weight: 650;
  svg { width: 15px; }
`;
const ActionDock = styled.div`display: flex; flex-wrap: wrap; gap: 7px; margin-top: 13px; padding: 10px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 80%, transparent);`;
const CareAction = styled.button<{ $finish?: boolean }>`display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 11px; border: 1px solid ${({ $finish, theme }) => $finish ? theme.color.plasmaBright : theme.color.controlBorder}; border-radius: 10px 4px 10px 4px; color: ${({ $finish, theme }) => $finish ? theme.color.plasmaBright : theme.color.textSoft}; background: ${({ theme }) => theme.color.control}; cursor: pointer; font: inherit; font-size: .67rem; font-weight: 610; &:hover { border-color: ${({ theme }) => theme.color.cyan}; color: ${({ theme }) => theme.color.text}; } svg { width: 16px; }`;
const LockedActions = styled.p`margin: 13px 0 0; padding: 10px 12px; border: 1px dashed ${({ theme }) => theme.color.border}; border-radius: 11px; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.5;`;
const TimelineHeader = styled.div`display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 13px; h3 { margin: 0; font-size: .72rem; font-weight: 650; } button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-width: 44px; min-height: 44px; padding: 0 8px; border: 0; color: ${({ theme }) => theme.color.cyan}; background: transparent; cursor: pointer; font: inherit; font-size: .65rem; } svg { width: 14px; }`;
const Timeline = styled.ol`display: grid; gap: 7px; margin: 8px 0 0; padding: 0; list-style: none;`;
const RecordRow = styled.li`
  display: grid; grid-template-columns: 32px minmax(0,1fr) auto; align-items: center; gap: 9px; min-height: 53px; padding: 8px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 11px 5px 11px 5px; background: ${({ theme }) => theme.color.surfaceStrong};
  > svg { width: 17px; margin: auto; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; font-size: .71rem; font-weight: 620; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .64rem; line-height: 1.45; }
  @media (max-width: 520px) { grid-template-columns: 32px minmax(0,1fr); }
`;
const RecordTools = styled.div`display: flex; gap: 3px; button { display: grid; width: 44px; height: 44px; place-items: center; border: 1px solid transparent; border-radius: 8px 3px 8px 3px; color: ${({ theme }) => theme.color.textMuted}; background: transparent; cursor: pointer; &:hover { border-color: ${({ theme }) => theme.color.controlBorder}; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; } svg { width: 16px; } } @media (max-width: 520px) { grid-column: 1 / -1; justify-content: flex-end; }`;
const CorrectionMark = styled.span`margin-left: 5px; color: ${({ theme }) => theme.color.amber}; font-size: .58rem; font-weight: 650; text-transform: uppercase;`;
const Empty = styled(GlassPanel)`display: grid; min-height: 240px; place-items: center; padding: 30px; text-align: center; svg { width: 38px; margin: 0 auto 10px; color: ${({ theme }) => theme.color.textMuted}; } h2 { margin: 0 0 6px; font-size: 1rem; } p { max-width: 500px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.6; }`;

type RosterFilter = 'all' | 'on_site' | 'checked_out' | 'attention';
type DialogState =
  | { kind: 'entry'; child: CareDayChild; careType: CareType; instant: string }
  | { kind: 'finish'; child: CareDayChild; record: CareRecord; instant: string }
  | { kind: 'correction'; child: CareDayChild; record: CareRecord }
  | { kind: 'void'; child: CareDayChild; record: CareRecord }
  | { kind: 'history'; record: CareRecord }
  | { kind: 'safety'; child: CareDayChild }
  | null;

interface DayResource {
  key: string;
  status: 'idle' | 'loading' | 'refreshing' | 'ready' | 'error';
  data: CareRoomDay | null;
  error: string;
}

function formatServiceDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat('en-CA', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

function CareIcon({ type }: { type: CareType }) {
  if (type === 'sleep') return <MoonIcon />;
  if (type === 'mood') return <FaceSmileIcon />;
  if (type === 'activity') return <SparklesIcon />;
  if (type === 'feeding') return <AcademicCapIcon />;
  return <HandRaisedIcon />;
}

function childMatchesFilter(child: CareDayChild, filter: RosterFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'attention') return safetyFlagCount(child.safety) > 0;
  return child.attendance_state === filter;
}

function activeProgramType(workspace: RoomWorkspace | null, room: RoomRecord | undefined): ProgramType | null {
  if (!workspace || !room?.program_id) return null;
  return workspace.programs.find((program) => program.id === room.program_id && program.facility_id === room.facility_id)?.program_type || null;
}

export default function TodayPage() {
  const session = useSession();
  const organizationReady = session.status === 'authenticated' && Boolean(session.organization?.id) && session.organization?.id === session.user?.organization_id && !session.organizationUnavailable;
  const organizationId = organizationReady ? session.organization!.id : '';
  const organizationWide = session.user?.role.key === 'owner' || session.user?.role.key === 'administrator';
  const canViewDailyClose = canOpenDailyClosePreview(session.user);
  const [workspace, setWorkspace] = useState<RoomWorkspace | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [workspaceError, setWorkspaceError] = useState('');
  const [facilityId, setFacilityId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [date, setDate] = useState(() => serviceDateValue(new Date(), session.organization?.timezone || 'America/Edmonton'));
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [view, setView] = useState<TodayView>('daybook');
  const [dayResource, setDayResource] = useState<DayResource>({ key: '', status: 'idle', data: null, error: '' });
  const [dailyCloseResource, setDailyCloseResource] = useState<DailyCloseResourceState>({ key: '', status: 'idle', data: null, error: '' });
  const [dailyCloseRefreshWarning, setDailyCloseRefreshWarning] = useState('');
  const dailyCloseRequests = useRef(createDailyCloseRequestGate());
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<RosterFilter>('all');
  const [expandedChildren, setExpandedChildren] = useState<ReadonlySet<string>>(() => new Set());
  const [dialog, setDialog] = useState<DialogState>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ error: boolean; message: string } | null>(null);

  const loadWorkspace = useCallback((signal?: AbortSignal) => {
    if (!organizationId) return Promise.resolve();
    setWorkspaceStatus('loading'); setWorkspaceError('');
    return fetchRoomWorkspace(organizationId, signal)
      .then((next) => { if (!signal?.aborted) { setWorkspace(next); setWorkspaceStatus('ready'); } })
      .catch((caught) => { if (!signal?.aborted) { setWorkspace(null); setWorkspaceStatus('error'); setWorkspaceError(caught instanceof Error ? caught.message : 'The assigned care rooms could not be loaded.'); } });
  }, [organizationId]);

  useEffect(() => {
    const controller = new AbortController();
    if (organizationReady) void loadWorkspace(controller.signal);
    else { setWorkspace(null); setWorkspaceStatus('idle'); }
    return () => controller.abort();
  }, [loadWorkspace, organizationReady]);

  const activeFacilities = useMemo(() => (workspace?.facilities || []).filter((facility) => facility.status === 'active' && workspace?.rooms.some((room) => room.is_active && room.facility_id === facility.id)), [workspace]);
  useEffect(() => {
    setFacilityId((current) => activeFacilities.some((facility) => facility.id === current) ? current : activeFacilities[0]?.id || '');
  }, [activeFacilities]);
  const rooms = useMemo(() => (workspace?.rooms || []).filter((room) => room.is_active && room.facility_id === facilityId), [facilityId, workspace]);
  useEffect(() => { setRoomId((current) => rooms.some((room) => room.id === current) ? current : rooms[0]?.id || ''); }, [rooms]);
  const facility = activeFacilities.find((item) => item.id === facilityId);
  const room = rooms.find((item) => item.id === roomId);
  const today = serviceDateValue(new Date(), facility?.timezone || session.organization?.timezone || 'America/Edmonton');
  useEffect(() => { if (facility) setDate((current) => !organizationWide || current > today ? today : current); }, [facility, organizationWide, today]);

  const dayKey = organizationId && facilityId && roomId && date
    ? dailyCloseBoundaryKey(organizationId, facilityId, roomId, date)
    : '';
  useRealtimeRefresh({ scope: 'today', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.today.realtimeEntities, refresh: async () => {
    const nextWorkspace = await fetchRoomWorkspace(organizationId);
    const nextFacilities = nextWorkspace.facilities.filter((item) => item.status === 'active' && nextWorkspace.rooms.some((candidate) => candidate.is_active && candidate.facility_id === item.id));
    const nextFacilityId = nextFacilities.some((item) => item.id === facilityId) ? facilityId : nextFacilities[0]?.id || '';
    const nextRooms = nextWorkspace.rooms.filter((item) => item.is_active && item.facility_id === nextFacilityId);
    const nextRoomId = nextRooms.some((item) => item.id === roomId) ? roomId : nextRooms[0]?.id || '';
    const nextKey = nextFacilityId && nextRoomId ? `${organizationId}:${nextFacilityId}:${nextRoomId}:${date}` : '';
    const data = nextKey ? await fetchCareRoomDay(nextRoomId, date, organizationId, nextFacilityId) : null;
    setWorkspace(nextWorkspace); setWorkspaceStatus('ready'); setFacilityId(nextFacilityId); setRoomId(nextRoomId); setDayResource(data ? { key: nextKey, status: 'ready', data, error: '' } : { key: '', status: 'idle', data: null, error: '' });
  } });
  useEffect(() => {
    if (!dayKey) { setDayResource({ key: '', status: 'idle', data: null, error: '' }); return; }
    const controller = new AbortController();
    setDayResource((current) => current.key === dayKey && current.data
      ? { ...current, status: 'refreshing', error: '' }
      : { key: dayKey, status: 'loading', data: null, error: '' });
    fetchCareRoomDay(roomId, date, organizationId, facilityId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setDayResource({ key: dayKey, status: 'ready', data, error: '' }); })
      .catch((caught) => { if (!controller.signal.aborted) setDayResource({ key: dayKey, status: 'error', data: null, error: caught instanceof Error ? caught.message : 'The room daybook could not be loaded.' }); });
    return () => controller.abort();
  }, [date, dayKey, facilityId, organizationId, refreshVersion, roomId]);

  useEffect(() => {
    dailyCloseRequests.current.invalidate();
    setDailyCloseRefreshWarning('');
    if (!canViewDailyClose && view === 'daily_close') setView('daybook');
  }, [canViewDailyClose, dayKey, view]);

  const loadDailyClose = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!dayKey || view !== 'daily_close' || !canViewDailyClose) return;
    const ticket = dailyCloseRequests.current.begin(dayKey);
    if (!quiet) {
      setDailyCloseRefreshWarning('');
      setDailyCloseResource((current) => current.key === dayKey && current.data
        ? { ...current, status: 'refreshing', error: '' }
        : { key: dayKey, status: 'loading', data: null, error: '' });
    }
    try {
      const data = await fetchRoomDailyClosePreview(roomId, date, organizationId, facilityId, signal);
      if (!signal?.aborted && dailyCloseRequests.current.isCurrent(ticket, dayKey)) {
        setDailyCloseRefreshWarning('');
        setDailyCloseResource({ key: dayKey, status: 'ready', data, error: '' });
      }
    } catch (caught) {
      if (signal?.aborted || !dailyCloseRequests.current.isCurrent(ticket, dayKey)) return;
      const error = caught instanceof Error ? caught.message : 'The daily close preview could not be loaded.';
      if (quiet) {
        setDailyCloseResource((current) => settleQuietDailyCloseFailure(current, dayKey, error));
        setDailyCloseRefreshWarning('Automatic refresh could not load a newer server snapshot. Previously loaded facts remain unchanged; use Refresh to try again.');
      } else {
        setDailyCloseRefreshWarning('');
        setDailyCloseResource({ key: dayKey, status: 'error', data: null, error });
      }
      throw caught;
    }
  }, [canViewDailyClose, date, dayKey, facilityId, organizationId, roomId, view]);

  useEffect(() => {
    if (view !== 'daily_close' || !canViewDailyClose) return;
    if (!dayKey) {
      setDailyCloseResource({ key: '', status: 'idle', data: null, error: '' });
      return;
    }
    const controller = new AbortController();
    void loadDailyClose(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [canViewDailyClose, dayKey, loadDailyClose, refreshVersion, view]);

  useRealtimeRefresh({
    scope: 'today-daily-close',
    organizationId,
    enabled: organizationReady && canViewDailyClose && view === 'daily_close' && Boolean(dayKey),
    entityTypes: featureIntegrationManifest.today.realtimeEntities,
    refresh: async () => loadDailyClose(undefined, true),
  });

  useEffect(() => {
    const refresh = () => { if (document.visibilityState !== 'hidden') setRefreshVersion((value) => value + 1); };
    const interval = window.setInterval(refresh, 60_000);
    window.addEventListener('focus', refresh);
    return () => { window.clearInterval(interval); window.removeEventListener('focus', refresh); };
  }, []);

  const currentDay = dayResource.key === dayKey ? dayResource.data : null;
  const currentStatus = dayResource.key === dayKey ? dayResource.status : 'loading';
  const currentDailyClose = dailyCloseResource.key === dayKey ? dailyCloseResource.data : null;
  const dailyCloseStatus = dailyCloseResource.key === dayKey ? dailyCloseResource.status : 'loading';
  const activeStatus = view === 'daybook' ? currentStatus : dailyCloseStatus;
  const counts = careDayCounts(currentDay?.children || []);
  const programType = activeProgramType(workspace, room);
  const careActions = careActionsForRoom(programType, room?.age_group);
  const canRecord = hasPermission(session.user, ACCESS.careRecord);
  const canCorrectAny = hasPermission(session.user, ACCESS.careCorrect);
  const canCorrectOwn = hasPermission(session.user, ACCESS.careCorrectOwn);
  const canVoid = hasPermission(session.user, ACCESS.careVoid);
  const canSafety = hasPermission(session.user, ACCESS.childSafetyRead);
  const canHistory = hasAnyPermission(session.user, [ACCESS.careCorrect, ACCESS.careVoid]);
  const safetyVisible = canPresentCurrentSafety(date, today);
  const historical = !safetyVisible;
  useEffect(() => { if (!safetyVisible && filter === 'attention') setFilter('all'); }, [filter, safetyVisible]);
  const filteredChildren = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (currentDay?.children || []).filter((child) => childMatchesFilter(child, filter) && (!normalized || child.child_name.toLowerCase().includes(normalized)));
  }, [currentDay, filter, query]);

  const handleViewTabKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = nextTodayView(view, event.key, canViewDailyClose);
    setView(next);
    const tabId = next === 'daybook' ? 'daybook-tab' : 'daily-close-preview-tab';
    window.requestAnimationFrame(() => document.getElementById(tabId)?.focus());
  };

  const boundary = (child: CareDayChild) => ({ organizationId, facilityId, roomId, childId: child.child_id, attendanceDayId: child.attendance_day_id || undefined, serviceDate: date });
  const saveEntry = async (state: Extract<DialogState, { kind: 'entry' }>, draft: CareEntryDraft) => {
    if (!state.child.attendance_day_id) throw new Error('This child does not have a verified attendance day.');
    setBusy(`entry:${state.child.child_id}`); setNotice(null);
    try {
      await createCareRecord({ attendance_day_id: state.child.attendance_day_id, care_type: state.careType, occurred_at: draft.occurredAt, payload: draft.payload, note: draft.note, client_operation_id: draft.clientOperationId }, boundary(state.child));
      setDialog(null); setNotice({ error: false, message: `${state.child.child_name}’s ${state.careType} record was saved.` }); setRefreshVersion((value) => value + 1);
    } finally { setBusy(''); }
  };
  const saveFinish = async (state: Extract<DialogState, { kind: 'finish' }>, endedAt: string, operationId: string) => {
    setBusy(`finish:${state.record.id}`); setNotice(null);
    try {
      await finishSleepRecord(state.record.id, endedAt, state.record.version, operationId, boundary(state.child));
      setDialog(null); setNotice({ error: false, message: `${state.child.child_name}’s sleep was finished at the recorded facility time.` }); setRefreshVersion((value) => value + 1);
    } finally { setBusy(''); }
  };
  const saveCorrection = async (state: Extract<DialogState, { kind: 'correction' }>, draft: CareCorrectionDraft) => {
    setBusy(`correct:${state.record.id}`); setNotice(null);
    try {
      await correctCareRecord(state.record.id, { occurred_at: draft.occurredAt, ended_at: draft.endedAt, payload: draft.payload, note: draft.note, reason: draft.reason, expected_version: state.record.version, client_operation_id: draft.clientOperationId }, boundary(state.child));
      setDialog(null); setNotice({ error: false, message: `The ${careRecordTitle(state.record).toLowerCase()} record was corrected with an audit reason.` }); setRefreshVersion((value) => value + 1);
    } finally { setBusy(''); }
  };
  const saveVoid = async (state: Extract<DialogState, { kind: 'void' }>, reason: string, operationId: string) => {
    setBusy(`void:${state.record.id}`); setNotice(null);
    try {
      await voidCareRecord(state.record.id, reason, state.record.version, operationId, boundary(state.child));
      setDialog(null); setNotice({ error: false, message: 'The care record was voided and retained in its audit history.' }); setRefreshVersion((value) => value + 1);
    } finally { setBusy(''); }
  };

  if (!organizationReady) return <Empty><div><ExclamationTriangleIcon /><h2>Confirmed organization required.</h2><p>Care records stay unavailable until the signed-in account and organization context agree.</p></div></Empty>;

  return <Page>
    <Header><div><Eyebrow><CalendarDaysIcon width={14} /> Assigned-room daybook</Eyebrow><h1>Today in care.</h1><p>Record everyday care against actual on-site attendance, with facility-local time, focused safety context, and audited corrections.</p></div><LiveMark><i /> Role-scoped · private, no-store</LiveMark></Header>
    <Scope $accent="cyan">
      <Field><span>Facility</span><select aria-label="Care facility" value={facilityId} onChange={(event) => { setFacilityId(event.target.value); setNotice(null); }}>{activeFacilities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
      <Field><span>Assigned room</span><select aria-label="Care room" value={roomId} onChange={(event) => { setRoomId(event.target.value); setNotice(null); }}>{rooms.map((item) => <option key={item.id} value={item.id}>{item.name}{item.age_group ? ` · ${item.age_group}` : ''}</option>)}</select></Field>
      <Field><span>Service date</span><input aria-label="Care service date" type="date" max={today} disabled={!organizationWide} value={date} onChange={(event) => { setDate(event.target.value); setNotice(null); }} /></Field>
      <RefreshButton type="button" aria-label={`Refresh ${view === 'daybook' ? 'room daybook' : 'daily close preview'}`} title={`Refresh ${view === 'daybook' ? 'room daybook' : 'daily close preview'}`} onClick={() => setRefreshVersion((value) => value + 1)} disabled={!dayKey || activeStatus === 'loading' || activeStatus === 'refreshing'}><ArrowPathIcon /></RefreshButton>
    </Scope>
    {workspaceStatus === 'ready' && workspace && facility && (
      <RoomSafetyCompactSummary
        organizationId={organizationId}
        facilityId={facility.id}
        facilityTimezone={facility.timezone}
        rooms={workspace.rooms}
      />
    )}

    <ViewTabs role="tablist" aria-label="Today workspace view" aria-orientation="horizontal" onKeyDown={handleViewTabKeyDown}>
      <ViewTab id="daybook-tab" role="tab" type="button" tabIndex={view === 'daybook' ? 0 : -1} aria-selected={view === 'daybook'} aria-controls="daybook-panel" $active={view === 'daybook'} onClick={() => setView('daybook')}><CalendarDaysIcon /> Live daybook</ViewTab>
      <ViewTab id="daily-close-preview-tab" role="tab" type="button" tabIndex={view === 'daily_close' ? 0 : -1} aria-selected={view === 'daily_close'} aria-controls="daily-close-preview-panel" aria-disabled={!canViewDailyClose} disabled={!canViewDailyClose} title={!canViewDailyClose ? 'Requires care, safety, medication, and incident read access' : undefined} $active={view === 'daily_close'} onClick={() => setView('daily_close')}><ClipboardDocumentListIcon /> Daily close preview</ViewTab>
    </ViewTabs>
    {!canViewDailyClose && <ViewPermissionNote role="note">Daily close preview is unavailable for this account because its role does not include the complete care, safety, medication, and incident read scope.</ViewPermissionNote>}

    {workspaceStatus === 'loading' && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Loading assigned facilities and rooms…</Notice>}
    {workspaceStatus === 'error' && <Notice $error role="alert"><ExclamationTriangleIcon /> <span>{workspaceError} <button type="button" onClick={() => void loadWorkspace()}>Try again</button></span></Notice>}
    {workspaceStatus === 'ready' && activeFacilities.length === 0 && <Empty><div><UserGroupIcon /><h2>No assigned active rooms.</h2><p>An administrator must assign this account to an active room before its care daybook becomes available.</p></div></Empty>}
    {view === 'daybook' && <ViewPanel id="daybook-panel" role="tabpanel" aria-labelledby="daybook-tab" aria-busy={currentStatus === 'loading' || currentStatus === 'refreshing'}>
      {currentStatus === 'loading' && dayKey && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Loading {room?.name || 'room'} for {formatServiceDate(date)}…</Notice>}
      {currentStatus === 'error' && <Notice $error role="alert"><ExclamationTriangleIcon /> <span>{dayResource.error} <button type="button" onClick={() => setRefreshVersion((value) => value + 1)}>Try again</button></span></Notice>}
      {currentDay && <>
      <MetricGrid role="group" aria-label="Room day summary">
        <Metric><span><UserGroupIcon /> Room children</span><strong>{currentDay.children.length}</strong></Metric>
        <Metric><span><CheckCircleIcon /> On site</span><strong>{counts.on_site}</strong></Metric>
        <Metric><span><ClockIcon /> Checked out</span><strong>{counts.checked_out}</strong></Metric>
        <Metric><span><AcademicCapIcon /> Care records</span><strong>{counts.records}</strong></Metric>
        <Metric><span><ShieldExclamationIcon /> {safetyVisible ? 'Current safety flags' : 'Current safety hidden'}</span><strong>{safetyVisible ? counts.safetyFlags : '—'}</strong></Metric>
      </MetricGrid>
      <Toolbar>
        <Search><MagnifyingGlassIcon /><input aria-label="Search room children" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search children in this room" /></Search>
        <Filters role="group" aria-label="Filter room children"><FilterButton type="button" aria-pressed={filter === 'all'} $active={filter === 'all'} onClick={() => setFilter('all')}>All {currentDay.children.length}</FilterButton><FilterButton type="button" aria-pressed={filter === 'on_site'} $active={filter === 'on_site'} onClick={() => setFilter('on_site')}>On site {counts.on_site}</FilterButton><FilterButton type="button" aria-pressed={filter === 'checked_out'} $active={filter === 'checked_out'} onClick={() => setFilter('checked_out')}>Checked out {counts.checked_out}</FilterButton>{safetyVisible && <FilterButton type="button" aria-pressed={filter === 'attention'} $active={filter === 'attention'} onClick={() => setFilter('attention')}><FunnelIcon width={13} /> Safety attention</FilterButton>}</Filters>
      </Toolbar>
      <div aria-live="polite">{currentStatus === 'refreshing' && <Notice role="status"><ArrowPathIcon /> Refreshing room facts without interrupting your work…</Notice>}{notice && <Notice $error={notice.error} role={notice.error ? 'alert' : 'status'}>{notice.error ? <ExclamationTriangleIcon /> : <CheckCircleIcon />} {notice.message}</Notice>}</div>
      {historical && <Notice><ClockIcon /> Historical daybook. Safety cards are hidden because they contain current profile information, not information proven as of {formatServiceDate(date)}.</Notice>}
      {filteredChildren.length ? <Roster>{filteredChildren.map((child) => {
        const records = activeRecords(child.records); const sleeping = openSleep(records); const expanded = expandedChildren.has(child.child_id); const shown = expanded ? records : records.slice(0, 4); const name = childNameParts(child.child_name); const flags = safetyVisible ? safetyFlagCount(child.safety) : 0; const canAct = canRecord && child.attendance_state === 'on_site' && Boolean(child.attendance_day_id) && !historical;
        return <ChildCard key={child.child_id} $accent={sleeping ? 'plasma' : flags ? 'amber' : 'cyan'}>
          <ChildHeader><Identity><ChildAvatar firstName={name.firstName} lastName={name.lastName} photoUrl={child.profile_photo_url} size={46} /><div><h2>{child.child_name}</h2><p>{room?.age_group || (programType === 'out_of_school_care' ? 'Out-of-school care' : 'Daycare')} · {records.length} care record{records.length === 1 ? '' : 's'}</p></div></Identity><HeaderActions>{canSafety && !historical && <SafetyButton type="button" onClick={() => setDialog({ kind: 'safety', child })} aria-label={`Open current assigned-care safety card for ${child.child_name}`}><ShieldExclamationIcon /> Safety{flags > 0 ? ` ${flags}` : ''}</SafetyButton>}<StatusChip $tone={attendanceTone(child.attendance_state)}>{attendanceLabel(child.attendance_state)}</StatusChip></HeaderActions></ChildHeader>
          {canAct ? <ActionDock aria-label={`Record care for ${child.child_name}`}>{sleeping && <CareAction $finish type="button" onClick={() => setDialog({ kind: 'finish', child, record: sleeping, instant: new Date().toISOString() })}><MoonIcon /> Finish sleep</CareAction>}{careActions.filter((action) => !(action.type === 'sleep' && sleeping)).map((action) => <CareAction key={action.type} type="button" onClick={() => setDialog({ kind: 'entry', child, careType: action.type, instant: new Date().toISOString() })}><CareIcon type={action.type} /> {action.shortLabel}</CareAction>)}</ActionDock> : <LockedActions>{child.attendance_state === 'on_site' ? 'Care entry is unavailable for this account.' : child.attendance_state === 'checked_out' ? 'Checked out — review the completed timeline below.' : child.attendance_state === 'no_show' ? 'No-show — no care entry is available.' : 'Record attendance before adding care facts.'}</LockedActions>}
          <TimelineHeader><h3>Child timeline · {currentDay.facility_timezone}</h3>{records.length > 4 && <button type="button" aria-expanded={expanded} aria-controls={`care-timeline-${child.child_id}`} onClick={() => setExpandedChildren((current) => { const next = new Set(current); if (next.has(child.child_id)) next.delete(child.child_id); else next.add(child.child_id); return next; })}>{expanded ? <><ChevronUpIcon /> Show less</> : <><ChevronDownIcon /> Show all {records.length}</>}</button>}</TimelineHeader>
          {shown.length ? <Timeline id={`care-timeline-${child.child_id}`}>{shown.map((record) => { const corrected = canCorrectCareRecord(record, session.user?.id, canCorrectAny, canCorrectOwn); const systemEnded = record.last_event_type === 'auto_finished_at_checkout'; return <RecordRow key={record.id}><CareIcon type={record.care_type} /><div><strong>{careRecordTitle(record)}{record.was_corrected && <CorrectionMark>Corrected</CorrectionMark>}</strong><p>{formatCareTime(record.occurred_at, currentDay.facility_timezone)}{record.ended_at ? `–${formatCareTime(record.ended_at, currentDay.facility_timezone)}` : ''} · {systemEnded ? 'Closed automatically at checkout — not an observed wake' : careRecordDetail(record)}{record.note ? ` · ${record.note}` : ''}</p></div><RecordTools>{corrected && <button type="button" aria-label={`Correct ${careRecordTitle(record)} for ${child.child_name}`} title="Correct with audit reason" onClick={() => setDialog({ kind: 'correction', child, record })}><PencilSquareIcon /></button>}{canHistory && <button type="button" aria-label={`View audit history for ${careRecordTitle(record)}`} title="View audit history" onClick={() => setDialog({ kind: 'history', record })}><ClockIcon /></button>}{canVoid && <button type="button" aria-label={`Void ${careRecordTitle(record)} for ${child.child_name}`} title="Void with audit reason" onClick={() => setDialog({ kind: 'void', child, record })}><TrashIcon /></button>}</RecordTools></RecordRow>; })}</Timeline> : <LockedActions>No care records have been added for this attendance day.</LockedActions>}
        </ChildCard>;
      })}</Roster> : <Empty><div><MagnifyingGlassIcon /><h2>No children match this view.</h2><p>Change the search or attendance filter. The daybook never invents a child outside the selected room roster.</p></div></Empty>}
      </>}
    </ViewPanel>}
    {view === 'daily_close' && <ViewPanel id="daily-close-preview-panel" role="tabpanel" aria-labelledby="daily-close-preview-tab" aria-busy={dailyCloseStatus === 'loading' || dailyCloseStatus === 'refreshing'}>
      {dailyCloseStatus === 'loading' && dayKey && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Loading the read-only daily close facts for {room?.name || 'room'} on {formatServiceDate(date)}…</Notice>}
      {dailyCloseStatus === 'error' && <Notice $error role="alert"><ExclamationTriangleIcon /> <span>{dailyCloseResource.error} <button type="button" onClick={() => setRefreshVersion((value) => value + 1)}>Try again</button></span></Notice>}
      {dailyCloseRefreshWarning && currentDailyClose && <Notice role="status" aria-live="polite"><ExclamationTriangleIcon /> {dailyCloseRefreshWarning}</Notice>}
      {dailyCloseStatus === 'refreshing' && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Refreshing the daily close facts from the server…</Notice>}
      {currentDailyClose && <DailyClosePreview key={dayKey} preview={currentDailyClose} />}
    </ViewPanel>}

    {dialog?.kind === 'entry' && currentDay && <CareEntryDialog key={`${dialog.child.child_id}:${dialog.careType}`} childName={dialog.child.child_name} type={dialog.careType} timeZone={currentDay.facility_timezone} initialOccurredAt={dialog.instant} busy={busy === `entry:${dialog.child.child_id}`} onClose={() => !busy && setDialog(null)} onSave={(draft) => saveEntry(dialog, draft)} />}
    {dialog?.kind === 'finish' && currentDay && <SleepFinishDialog key={dialog.record.id} record={dialog.record} childName={dialog.child.child_name} timeZone={currentDay.facility_timezone} initialEndedAt={dialog.instant} busy={busy === `finish:${dialog.record.id}`} onClose={() => !busy && setDialog(null)} onSave={(endedAt, operationId) => saveFinish(dialog, endedAt, operationId)} />}
    {dialog?.kind === 'correction' && currentDay && <CareCorrectionDialog key={`${dialog.record.id}:${dialog.record.version}`} record={dialog.record} childName={dialog.child.child_name} timeZone={currentDay.facility_timezone} busy={busy === `correct:${dialog.record.id}`} onClose={() => !busy && setDialog(null)} onSave={(draft) => saveCorrection(dialog, draft)} />}
    {dialog?.kind === 'void' && <CareVoidDialog key={`${dialog.record.id}:${dialog.record.version}`} record={dialog.record} childName={dialog.child.child_name} busy={busy === `void:${dialog.record.id}`} onClose={() => !busy && setDialog(null)} onSave={(reason, operationId) => saveVoid(dialog, reason, operationId)} />}
    {dialog?.kind === 'safety' && currentDay && !historical && <SafetyCardDialog childId={dialog.child.child_id} facilityId={currentDay.facility_id} roomId={currentDay.room_id} onClose={() => setDialog(null)} />}
    {dialog?.kind === 'history' && currentDay && <CareHistoryDialog record={dialog.record} timeZone={currentDay.facility_timezone} onClose={() => setDialog(null)} />}
  </Page>;
}

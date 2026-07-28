import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  BriefcaseIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  PlusIcon,
  SignalIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { addDays, format, parseISO } from 'date-fns';
import { useSearchParams } from 'react-router-dom';
import styled from 'styled-components';
import { ApiError } from '../../api/client';
import { useSession } from '../../auth/SessionContext';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import { useRealtimeRefresh, useRealtimeState } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import { facilityDateTimeInputValue, facilityDateTimeToIso } from '../daily-care/careModel';
import { staffApi } from '../staff/staffApi';
import type { StaffWorkspace } from '../staff/types';
import { reconciliationRows, rotaMetrics, rotaWeekDays, rotaWeekStart, scheduleOriginLabel, scheduleServiceDate, validateScheduleDraft } from './rotaModel';
import { rotaApi, rotaErrorMessage } from './rotaApi';
import type { RotaMonitorRow, StaffSchedule, StaffScheduleDraft, StaffScheduleReconciliation } from './types';
import { WorkforcePlanningPanel } from './WorkforcePlanningPanel';
import { workforceErrorCode } from './workforceApi';
import { ShiftExchangePanel } from './exchange/ShiftExchangePanel';
import { WorkforceModalOverlay, WorkforceModalPortal, WorkforceModalSurface } from './components/WorkforceDialog';
import { clearNotificationTarget, clearNotificationTargets, isSafeNotificationTargetId, resolveNotificationTarget } from '../notifications/notificationTarget';
import {
  parseStaffRotaNotificationRequest,
  resolveStaffRotaActionTarget,
  type StaffRotaActionTarget,
} from './staffRotaNotificationFocus';

const Page = styled.div`display:grid;gap:20px;padding-bottom:44px;`;
const Header = styled.header`
  display:flex;align-items:flex-end;justify-content:space-between;gap:18px;
  h1{margin:8px 0 6px;font-family:"CareSync Display",sans-serif;font-size:clamp(1.55rem,2.8vw,2.25rem);font-weight:600;letter-spacing:-.045em;}
  p{max-width:72ch;margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.8rem;line-height:1.65;}
  @media(max-width:760px){align-items:stretch;flex-direction:column;}
`;
const HeaderActions = styled.div`display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;`;
const Toolbar = styled(GlassPanel)`
  display:flex;align-items:center;gap:10px;padding:12px;
  @media(max-width:760px){align-items:stretch;flex-direction:column;}
`;
const WeekControl = styled.div`display:flex;align-items:center;gap:7px;`;
const WeekLabel = styled.div`
  min-width:210px;text-align:center;
  strong,small{display:block;}strong{font-size:.84rem;font-weight:600;}small{margin-top:3px;color:${({ theme }) => theme.color.textMuted};font-size:.7rem;}
  @media(max-width:760px){flex:1;min-width:0;}
`;
const Select = styled.select`
  min-height:44px;margin-left:auto;padding:0 36px 0 12px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:8px 13px 8px 13px;
  color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;
  @media(max-width:760px){width:100%;margin-left:0;}
`;
const Metrics = styled.section`
  display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;
  @media(max-width:860px){grid-template-columns:repeat(2,minmax(0,1fr));}
  @media(max-width:460px){grid-template-columns:1fr;}
`;
const Metric = styled(GlassPanel)`
  padding:15px 17px;
  span{display:block;color:${({ theme }) => theme.color.textMuted};font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;}
  strong{display:block;margin-top:7px;font-family:"CareSync Display",sans-serif;font-size:1.6rem;font-weight:600;}
  small{display:block;margin-top:3px;color:${({ theme }) => theme.color.textSoft};font-size:.68rem;}
`;
const Notice = styled.div<{ $error?: boolean }>`
  display:flex;align-items:flex-start;gap:9px;padding:12px 14px;border:1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.borderStrong};
  border-radius:9px 14px 9px 14px;color:${({ $error, theme }) => $error ? theme.color.coral : theme.color.textSoft};background:${({ theme }) => theme.color.surfaceStrong};font-size:.76rem;line-height:1.55;
  svg{width:18px;flex:0 0 auto;}
`;
const Section = styled.section`display:grid;gap:11px;`;
const SectionHead = styled.div`
  display:flex;align-items:end;justify-content:space-between;gap:14px;
  h2{margin:0;font-family:"CareSync Display",sans-serif;font-size:1.08rem;font-weight:600;}p{margin:4px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.73rem;}
`;
const PlannerScroll = styled.div`overflow-x:auto;padding-bottom:5px;`;
const Planner = styled.div`display:grid;grid-template-columns:repeat(7,minmax(184px,1fr));gap:9px;min-width:1280px;`;
const Day = styled(GlassPanel)<{ $today?: boolean }>`
  min-height:274px;border-color:${({ $today, theme }) => $today ? theme.color.cyan : theme.color.border};
`;
const DayHead = styled.header`
  display:flex;align-items:center;justify-content:space-between;padding:13px 13px 10px;border-bottom:1px solid ${({ theme }) => theme.color.border};
  strong{font-size:.78rem;font-weight:600;}small{color:${({ theme }) => theme.color.textMuted};font-size:.68rem;}
`;
const DayBody = styled.div`display:grid;gap:7px;padding:9px;`;
const ShiftCard = styled.article<{ $focused?: boolean }>`
  position:relative;z-index:1;display:grid;gap:7px;padding:10px;border:1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.borderStrong};border-radius:8px 12px 8px 12px;background:${({ theme }) => theme.color.surfaceStrong};
  box-shadow:${({ $focused, theme }) => $focused ? `0 0 0 2px color-mix(in srgb, ${theme.color.cyan} 24%, transparent), ${theme.shadow.panel}` : 'none'};
  strong{font-size:.76rem;font-weight:600;line-height:1.35;}small{color:${({ theme }) => theme.color.textMuted};font-size:.67rem;line-height:1.45;}
`;
const ShiftMeta = styled.div`display:flex;flex-wrap:wrap;gap:5px;`;
const MiniChip = styled.span<{ $tone?: 'good' | 'warn' | 'bad' }>`
  padding:3px 6px;border:1px solid ${({ $tone, theme }) => $tone === 'bad' ? theme.color.coral : $tone === 'warn' ? theme.color.amber : $tone === 'good' ? theme.color.mint : theme.color.border};
  border-radius:7px 3px 7px 3px;color:${({ $tone, theme }) => $tone === 'bad' ? theme.color.coral : $tone === 'warn' ? theme.color.amber : $tone === 'good' ? theme.color.mint : theme.color.textSoft};font-size:.6rem;text-transform:capitalize;
`;
const CardActions = styled.div`display:flex;flex-wrap:wrap;gap:5px;button{min-height:32px;padding:0 8px;font-size:.66rem;}button svg{width:14px;}`;
const EmptyDay = styled.p`margin:20px 8px;color:${({ theme }) => theme.color.textMuted};font-size:.69rem;text-align:center;`;
const Monitor = styled(GlassPanel)`overflow-x:auto;`;
const MonitorTable = styled.table`
  width:100%;min-width:840px;border-collapse:collapse;
  th,td{padding:12px 14px;border-bottom:1px solid ${({ theme }) => theme.color.border};text-align:left;}
  th{color:${({ theme }) => theme.color.textMuted};font-size:.64rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;}
  td{font-size:.73rem;}tr:last-child td{border-bottom:0;}small{display:block;margin-top:3px;color:${({ theme }) => theme.color.textMuted};font-size:.66rem;}
`;
const Empty = styled(GlassPanel)`padding:42px 20px;text-align:center;svg{width:38px;color:${({ theme }) => theme.color.textMuted};}h3{margin:10px 0 5px;font-size:.95rem;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;}`;
const Overlay = styled(WorkforceModalOverlay)``;
const Dialog = styled(WorkforceModalSurface)`width:min(650px,100%);`;
const DialogHead = styled.header`display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:17px;h2{margin:6px 0 4px;font-family:"CareSync Display",sans-serif;font-size:1.25rem;font-weight:600;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.74rem;line-height:1.5;}`;
const Form = styled.form`display:grid;gap:14px;`;
const FormGrid = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:11px;@media(max-width:560px){grid-template-columns:1fr;}`;
const Field = styled.label<{ $wide?: boolean }>`
  display:grid;grid-column:${({ $wide }) => $wide ? '1/-1' : 'auto'};gap:6px;color:${({ theme }) => theme.color.textSoft};font-size:.72rem;font-weight:600;
  input,select,textarea{width:100%;min-height:43px;padding:0 11px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:8px 12px 8px 12px;outline:0;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;}
  textarea{min-height:86px;padding:10px;resize:vertical;}input:focus,select:focus,textarea:focus{border-color:${({ theme }) => theme.color.cyan};}small{color:${({ theme }) => theme.color.textMuted};font-weight:400;line-height:1.45;}
`;
const DialogActions = styled.div`display:flex;justify-content:flex-end;gap:8px;@media(max-width:480px){flex-direction:column-reverse;button{width:100%;}}`;
const Proposal = styled.div`display:grid;gap:7px;padding:9px;border:1px solid ${({ theme }) => theme.color.amber};border-radius:7px 10px 7px 10px;color:${({ theme }) => theme.color.amber};font-size:.66rem;line-height:1.4;`;

type EditorState = { schedule: StaffSchedule | null; operationId: string; retryLocked: boolean; lockedDraft: StaffScheduleDraft | null; facilityId: string; roomId: string; userId: string; date: string; start: string; end: string; notes: string };
type CancelState = { schedule: StaffSchedule; operationId: string; retryLocked: boolean; reason: string };
type ProposalState = { schedule: StaffSchedule; decision: 'accept' | 'reject'; operationId: string; retryLocked: boolean; note: string };
type PublishOverrideState = { schedule: StaffSchedule; operationId: string; retryLocked: boolean; reason: string };

function operationId(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('This browser cannot create a secure operation identifier.');
  return globalThis.crypto.randomUUID();
}

function timeLabel(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function dateTimeLabel(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function serviceDate(value: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function isDefinitiveClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500 && ![408, 425, 429].includes(error.status);
}

function statusTone(value: string): 'success' | 'warning' | 'info' | 'neutral' {
  if (['acknowledged', 'active', 'completed'].includes(value)) return 'success';
  if (['declined', 'missed', 'late', 'alternate_proposed'].includes(value)) return 'warning';
  if (['published', 'pending', 'upcoming'].includes(value)) return 'info';
  return 'neutral';
}

function draftFromEditor(editor: EditorState, timezone: string): StaffScheduleDraft {
  return {
    facility_id: editor.facilityId,
    room_id: editor.roomId || null,
    staff_user_id: editor.userId,
    scheduled_start_at: facilityDateTimeToIso(`${editor.date}T${editor.start}`, timezone),
    scheduled_end_at: facilityDateTimeToIso(`${editor.date}T${editor.end}`, timezone),
    notes: editor.notes.trim() || null,
  };
}

export default function StaffRotaPage() {
  const session = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const organizationId = session.organization?.id || '';
  const timezone = session.organization?.timezone || 'America/Edmonton';
  const canManage = hasPermission(session.user, ACCESS.staffManage) || hasPermission(session.user, ACCESS.staffManageEducators);
  const realtimeState = useRealtimeState();
  const [weekStart, setWeekStart] = useState(() => rotaWeekStart());
  const [facilityId, setFacilityId] = useState('');
  const [workspace, setWorkspace] = useState<StaffWorkspace | null>(null);
  const [schedules, setSchedules] = useState<StaffSchedule[]>([]);
  const [reconciliation, setReconciliation] = useState<StaffScheduleReconciliation | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [cancel, setCancel] = useState<CancelState | null>(null);
  const [proposal, setProposal] = useState<ProposalState | null>(null);
  const [publishOverride, setPublishOverride] = useState<PublishOverrideState | null>(null);
  const [coverageSource, setCoverageSource] = useState<StaffSchedule | null>(null);
  const [publishRetryIds, setPublishRetryIds] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState('');
  const actionOperations = useRef(new Map<string, string>());
  const targetLookup = useRef('');
  const workforceTargetLookup = useRef('');
  const [focusedScheduleId, setFocusedScheduleId] = useState<string | null>(null);
  const [focusedWorkforceTarget, setFocusedWorkforceTarget] = useState<StaffRotaActionTarget | null>(null);

  useEffect(() => {
    if (!editor && !cancel && !proposal && !publishOverride) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || busy || editor?.retryLocked || cancel?.retryLocked || proposal?.retryLocked || publishOverride?.retryLocked) return;
      setEditor(null); setCancel(null); setProposal(null); setPublishOverride(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [busy, cancel, editor, proposal, publishOverride]);

  const days = useMemo(() => rotaWeekDays(weekStart), [weekStart]);
  const filterTimezone = workspace?.facilities.find((facility) => facility.id === facilityId)?.timezone || '';
  const range = useMemo(() => {
    const broadStart = `${format(addDays(parseISO(weekStart), -1), 'yyyy-MM-dd')}T00:00:00Z`;
    const broadEnd = `${format(addDays(parseISO(weekStart), 8), 'yyyy-MM-dd')}T00:00:00Z`;
    try {
      if (filterTimezone) return { startAt: facilityDateTimeToIso(`${weekStart}T00:00`, filterTimezone), endAt: facilityDateTimeToIso(`${format(addDays(parseISO(weekStart), 7), 'yyyy-MM-dd')}T00:00`, filterTimezone) };
      return { startAt: broadStart, endAt: broadEnd };
    } catch {
      return { startAt: broadStart, endAt: broadEnd };
    }
  }, [filterTimezone, weekStart]);

  const load = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!organizationId || !canManage) return;
    if (!quiet) setPhase('loading');
    setError('');
    try {
      const filters = { ...range, ...(facilityId ? { facilityId } : {}) };
      const [staff, scheduleList, monitor] = await Promise.all([
        staffApi.workspace(organizationId, signal), rotaApi.list(organizationId, filters, signal), rotaApi.reconciliation(organizationId, filters, signal),
      ]);
      if (signal?.aborted) return;
      const knownFacilities = new Set(staff.facilities.map((facility) => facility.id));
      if (scheduleList.items.some((item) => !knownFacilities.has(item.facility_id)) || monitor.unscheduled.some((item) => !knownFacilities.has(item.facility_id))) throw new Error('The rota returned a facility outside the verified staff workspace.');
      const weekDates = new Set(days);
      const visibleSchedules = scheduleList.items.filter((item) => weekDates.has(scheduleServiceDate(item)));
      const visibleMonitorSchedules = monitor.scheduled.filter((item) => weekDates.has(scheduleServiceDate(item)));
      const visibleUnscheduled = monitor.unscheduled.filter((item) => weekDates.has(serviceDate(item.actual_shift.clocked_in_at, item.facility_timezone)));
      setWorkspace(staff);
      setSchedules(visibleSchedules);
      setPublishRetryIds((current) => {
        const statusById = new Map(visibleSchedules.map((item) => [item.id, item.status]));
        const next = new Set([...current].filter((id) => !statusById.has(id) || statusById.get(id) === 'draft'));
        for (const key of actionOperations.current.keys()) {
          if (!key.startsWith('publish:')) continue;
          const status = statusById.get(key.slice('publish:'.length));
          if (status && status !== 'draft') actionOperations.current.delete(key);
        }
        return next;
      });
      setReconciliation({ ...monitor, scheduled: visibleMonitorSchedules, unscheduled: visibleUnscheduled, total_scheduled: visibleMonitorSchedules.length, total_unscheduled: visibleUnscheduled.length });
      setPhase('ready');
    } catch (caught) {
      if (!signal?.aborted) { setError(rotaErrorMessage(caught)); if (!quiet) setPhase('error'); }
      throw caught;
    }
  }, [canManage, days, facilityId, organizationId, range]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal).catch(() => undefined); return () => controller.abort(); }, [load]);
  useRealtimeRefresh({ scope: 'staff-rota', organizationId, enabled: canManage, eventPrefixes: ['staff_schedule.', 'staff_shift.', 'staff_rotation.', 'staff_open_shift.', 'staff_open_shift_engagement.', 'staff_substitute_profile.', 'staff_shift_swap.'], entityTypes: featureIntegrationManifest['staff-rota'].realtimeEntities, refresh: async () => load(undefined, true) });

  const requestedScheduleId = searchParams.get('schedule');
  useEffect(() => {
    if (!requestedScheduleId) {
      targetLookup.current = '';
      return;
    }
    if (!organizationId || !canManage || phase !== 'ready' || !workspace) return;
    const lookupKey = `${organizationId}:${requestedScheduleId}`;
    if (targetLookup.current === lookupKey) return;
    targetLookup.current = lookupKey;
    const clearTarget = () => setSearchParams(
      (current) => clearNotificationTarget(current, 'schedule'),
      { replace: true },
    );
    if (!isSafeNotificationTargetId(requestedScheduleId)) {
      setFocusedScheduleId(null);
      setNotice('The notification contained an invalid shift target. The current rota is shown instead.');
      clearTarget();
      return;
    }
    const controller = new AbortController();
    const reference = new Date();
    const locatorRange = {
      startAt: addDays(reference, -183).toISOString(),
      endAt: addDays(reference, 183).toISOString(),
    };
    void rotaApi.list(organizationId, locatorRange, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        const resolution = resolveNotificationTarget(
          requestedScheduleId,
          result.items.map((item) => item.id),
        );
        const target = resolution.status === 'available'
          ? result.items.find((item) => item.id === requestedScheduleId)
          : undefined;
        const facilityAvailable = target && workspace.facilities.some(
          (facility) => facility.status === 'active' && facility.id === target.facility_id,
        );
        if (!target || !facilityAvailable) {
          setFocusedScheduleId(null);
          setNotice('That shift is stale, outside the supported notification window, or no longer in your active facility scope. The current rota is shown instead.');
          return;
        }
        setFocusedScheduleId(target.id);
        setFacilityId(target.facility_id);
        setWeekStart(rotaWeekStart(parseISO(`${scheduleServiceDate(target)}T12:00:00`)));
        setNotice(`Opened ${target.staff_display_name}'s shift from the notification.`);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFocusedScheduleId(null);
        setNotice('The requested shift could not be safely verified. The current rota is shown instead.');
      })
      .finally(() => {
        if (!controller.signal.aborted) clearTarget();
      });
    return () => {
      controller.abort();
      if (targetLookup.current === lookupKey) targetLookup.current = '';
    };
  }, [canManage, organizationId, phase, requestedScheduleId, setSearchParams, workspace]);

  const focusedScheduleVisible = Boolean(
    focusedScheduleId && schedules.some((schedule) => schedule.id === focusedScheduleId),
  );
  useEffect(() => {
    if (!focusedScheduleId || !focusedScheduleVisible) return;
    const frame = requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(`[data-schedule-id="${CSS.escape(focusedScheduleId)}"]`);
      card?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      card?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedScheduleId, focusedScheduleVisible]);

  const requestedWorkforceFocus = searchParams.get('focus');
  const requestedWorkforceRecord = searchParams.get('record');
  useEffect(() => {
    if (!requestedWorkforceFocus && !requestedWorkforceRecord) {
      workforceTargetLookup.current = '';
      return;
    }
    if (!organizationId || !canManage || phase !== 'ready' || !workspace) return;
    const parsed = parseStaffRotaNotificationRequest(searchParams);
    const clearTarget = () => setSearchParams(
      (current) => clearNotificationTargets(current, ['focus', 'record']),
      { replace: true },
    );
    if (parsed.status !== 'available') {
      setFocusedWorkforceTarget(null);
      setNotice('The notification contained an invalid workforce target. No workforce row was opened.');
      clearTarget();
      return;
    }
    const lookupKey = `${organizationId}:${parsed.request.entityType}:${parsed.request.entityId}`;
    if (workforceTargetLookup.current === lookupKey) return;
    workforceTargetLookup.current = lookupKey;
    // Reset the prior focus before the canonical re-read so opening the same
    // notification again will scroll and focus its exact row again.
    setFocusedWorkforceTarget(null);
    const controller = new AbortController();
    void resolveStaffRotaActionTarget(parsed.request, organizationId, controller.signal)
      .then((target) => {
        if (controller.signal.aborted) return;
        const facility = workspace.facilities.find(
          (item) => item.id === target.facilityId && item.status === 'active',
        );
        if (!target.visible || !facility) {
          setFocusedWorkforceTarget(null);
          setNotice(
            target.visible
              ? 'That workforce record belongs to a facility that is no longer active in your current scope. No different row was opened.'
              : 'That workforce record is no longer visible after the fresh server read. No different row was opened.',
          );
          return;
        }
        setFacilityId(target.facilityId);
        if (target.startsAt) {
          const targetDate = serviceDate(target.startsAt, facility.timezone);
          setWeekStart(rotaWeekStart(parseISO(`${targetDate}T12:00:00`)));
        }
        setFocusedWorkforceTarget(target);
        setNotice('The exact workforce record was verified from the server. Its owning section is loading the latest canonical row.');
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFocusedWorkforceTarget(null);
        setNotice('The requested workforce record could not be safely verified. No different row was opened.');
      })
      .finally(() => {
        if (!controller.signal.aborted) clearTarget();
      });
    return () => {
      controller.abort();
      if (workforceTargetLookup.current === lookupKey) workforceTargetLookup.current = '';
    };
  }, [canManage, organizationId, phase, requestedWorkforceFocus, requestedWorkforceRecord, searchParams, setSearchParams, workspace]);

  const monitorRows = useMemo(() => reconciliation ? reconciliationRows(reconciliation) : [], [reconciliation]);
  const metrics = useMemo(() => rotaMetrics(monitorRows, schedules), [monitorRows, schedules]);
  const activeMembers = useMemo(() => (workspace?.members || []).filter((member) => member.membership_status === 'active'), [workspace]);
  const selectedFacility = workspace?.facilities.find((facility) => facility.id === (editor?.facilityId || facilityId));
  const formTimezone = editor?.schedule?.facility_timezone || selectedFacility?.timezone || timezone;
  const formRooms = (workspace?.rooms || []).filter((room) => room.is_active && room.facility_id === editor?.facilityId);
  const formMembers = activeMembers.filter((member) => member.assigned_facility_ids.includes(editor?.facilityId || ''));

  const openCreate = (date = days[0]) => { setError(''); setEditor({ schedule: null, operationId: operationId(), retryLocked: false, lockedDraft: null, facilityId: facilityId || workspace?.facilities[0]?.id || '', roomId: '', userId: '', date, start: '08:00', end: '16:00', notes: '' }); };
  const openEdit = (schedule: StaffSchedule) => {
    if (schedule.status !== 'draft') return;
    setError('');
    const start = facilityDateTimeInputValue(schedule.scheduled_start_at, schedule.facility_timezone);
    const end = facilityDateTimeInputValue(schedule.scheduled_end_at, schedule.facility_timezone);
    setEditor({ schedule, operationId: operationId(), retryLocked: false, lockedDraft: null, facilityId: schedule.facility_id, roomId: schedule.room_id || '', userId: schedule.staff_user_id, date: start.slice(0, 10), start: start.slice(11, 16), end: end.slice(11, 16), notes: schedule.notes || '' });
  };
  const openCancel = (schedule: StaffSchedule) => { setError(''); setCancel({ schedule, operationId: operationId(), retryLocked: false, reason: '' }); };
  const openProposal = (schedule: StaffSchedule, decision: ProposalState['decision']) => { setError(''); setProposal({ schedule, decision, operationId: operationId(), retryLocked: false, note: '' }); };
  const refreshAfter = async (message: string) => {
    try { await load(undefined, true); setNotice(message); }
    catch { setNotice(`${message} The follow-up refresh failed, so use Refresh to load the latest canonical view.`); }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault(); if (!editor || (!editor.lockedDraft && !selectedFacility)) return;
    setBusy('save'); setError('');
    let requestStarted = false;
    let attemptedDraft: StaffScheduleDraft | null = editor.lockedDraft;
    try {
      const draft = editor.lockedDraft || draftFromEditor(editor, formTimezone);
      attemptedDraft = draft;
      const errors = validateScheduleDraft(draft);
      if (errors.length) throw new Error(errors.join(' '));
      if (!editor.lockedDraft) {
        const member = activeMembers.find((item) => item.user_id === draft.staff_user_id);
        if (!member?.assigned_facility_ids.includes(draft.facility_id)) throw new Error('The selected staff member is not assigned to this facility.');
        if (draft.room_id && member.assigned_room_ids.length > 0 && !member.assigned_room_ids.includes(draft.room_id)) throw new Error('The selected staff member is not assigned to this room.');
      }
      if (editor.schedule) {
        requestStarted = true;
        await rotaApi.update(organizationId, editor.schedule.id, { ...draft, client_operation_id: editor.operationId, expected_updated_at: editor.schedule.updated_at });
        await refreshAfter('Draft shift updated.');
      } else {
        requestStarted = true;
        await rotaApi.create(organizationId, { ...draft, client_operation_id: editor.operationId });
        await refreshAfter('Draft shift created. Publish it when the plan is ready.');
      }
      setEditor(null);
    } catch (caught) {
      if (requestStarted && isDefinitiveClientError(caught)) setEditor((current) => current ? { ...current, operationId: operationId(), retryLocked: false, lockedDraft: null } : current);
      else if (requestStarted) setEditor((current) => current ? { ...current, retryLocked: true, lockedDraft: attemptedDraft } : current);
      setError(rotaErrorMessage(caught));
    }
    finally { setBusy(''); }
  };

  const actionOperation = (key: string) => {
    const existing = actionOperations.current.get(key); if (existing) return existing;
    const value = operationId(); actionOperations.current.set(key, value); return value;
  };
  const publish = async (schedule: StaffSchedule) => {
    const key = `publish:${schedule.id}`; setBusy(key); setError('');
    try { await rotaApi.publish(organizationId, schedule.id, actionOperation(key), null); actionOperations.current.delete(key); setPublishRetryIds((current) => { const next = new Set(current); next.delete(schedule.id); return next; }); await refreshAfter(`${schedule.staff_display_name}'s shift was published.`); }
    catch (caught) {
      if (isDefinitiveClientError(caught)) { actionOperations.current.delete(key); setPublishRetryIds((current) => { const next = new Set(current); next.delete(schedule.id); return next; }); }
      else setPublishRetryIds((current) => new Set(current).add(schedule.id));
      if (workforceErrorCode(caught) === 'availability_override_required') {
        setPublishOverride({ schedule, operationId: operationId(), retryLocked: false, reason: '' });
        setError('This shift is outside the educator’s declared availability. Publishing requires an explicit manager reason.');
      } else setError(rotaErrorMessage(caught));
    }
    finally { setBusy(''); }
  };
  const confirmPublishOverride = async (event: FormEvent) => {
    event.preventDefault(); if (!publishOverride) return;
    const reason = publishOverride.reason.trim();
    if (reason.length < 5) { setError('Explain the availability override in at least five characters.'); return; }
    setBusy('publish-override'); setError('');
    try {
      await rotaApi.publish(organizationId, publishOverride.schedule.id, publishOverride.operationId, reason);
      await refreshAfter(`${publishOverride.schedule.staff_display_name}'s shift was published with a recorded availability override.`);
      setPublishOverride(null);
    } catch (caught) {
      if (isDefinitiveClientError(caught)) setPublishOverride((current) => current ? { ...current, operationId: operationId(), retryLocked: false } : current);
      else setPublishOverride((current) => current ? { ...current, retryLocked: true } : current);
      setError(rotaErrorMessage(caught));
    } finally { setBusy(''); }
  };
  const confirmCancel = async (event: FormEvent) => {
    event.preventDefault(); if (!cancel) return;
    if (cancel.reason.trim().length < 5) { setError('Explain the cancellation in at least five characters.'); return; }
    setBusy('cancel'); setError('');
    try { await rotaApi.cancel(organizationId, cancel.schedule.id, cancel.operationId, cancel.reason.trim()); await refreshAfter(`${cancel.schedule.staff_display_name}'s shift was cancelled.`); setCancel(null); }
    catch (caught) {
      if (isDefinitiveClientError(caught)) setCancel((current) => current ? { ...current, operationId: operationId(), retryLocked: false } : current);
      else setCancel((current) => current ? { ...current, retryLocked: true } : current);
      setError(rotaErrorMessage(caught));
    }
    finally { setBusy(''); }
  };
  const resolveProposal = async (event: FormEvent) => {
    event.preventDefault(); if (!proposal) return;
    setBusy('proposal'); setError('');
    try {
      const note = proposal.note.trim() || null;
      if (proposal.decision === 'accept') await rotaApi.acceptAlternate(organizationId, proposal.schedule, proposal.operationId, note);
      else await rotaApi.rejectAlternate(organizationId, proposal.schedule, proposal.operationId, note);
      await refreshAfter(proposal.decision === 'accept' ? 'The educator’s alternate time was accepted.' : 'The original shift time was retained.');
      setProposal(null);
    } catch (caught) {
      if (isDefinitiveClientError(caught)) setProposal((current) => current ? { ...current, operationId: operationId(), retryLocked: false } : current);
      else setProposal((current) => current ? { ...current, retryLocked: true } : current);
      setError(rotaErrorMessage(caught));
    } finally { setBusy(''); }
  };

  if (!canManage) return <Page><Header><div><Eyebrow><CalendarDaysIcon width={15} /> Staff rota</Eyebrow><h1>Shift planning requires staff-management access.</h1><p>Your account cannot create or publish staff assignments.</p></div></Header></Page>;

  return <Page>
    <Header>
      <div><Eyebrow><CalendarDaysIcon width={15} /> Daily staff rota</Eyebrow><h1>Plan the room. Reconcile the real day.</h1><p>Create draft shifts, publish them to educators, and compare accepted plans with actual clock records. The server remains the source of truth for late, missed, and unscheduled work.</p></div>
      <HeaderActions><StatusChip $tone={realtimeState === 'connected' ? 'success' : 'warning'}><SignalIcon /> {realtimeState === 'connected' ? 'Live updates' : 'Refreshing manually'}</StatusChip><ActionButton type="button" onClick={() => openCreate()} disabled={phase !== 'ready'} $variant="primary"><PlusIcon /> New shift</ActionButton></HeaderActions>
    </Header>
    <Toolbar>
      <WeekControl><IconButton type="button" onClick={() => setWeekStart(format(addDays(parseISO(weekStart), -7), 'yyyy-MM-dd'))} aria-label="Previous week"><ArrowLeftIcon /></IconButton><WeekLabel><strong>{format(parseISO(days[0]), 'MMM d')} – {format(parseISO(days[6]), 'MMM d, yyyy')}</strong><small>Monday through Sunday</small></WeekLabel><IconButton type="button" onClick={() => setWeekStart(format(addDays(parseISO(weekStart), 7), 'yyyy-MM-dd'))} aria-label="Next week"><ArrowRightIcon /></IconButton></WeekControl>
      <ActionButton type="button" onClick={() => setWeekStart(rotaWeekStart())}>Today</ActionButton>
      <Select aria-label="Filter rota by facility" value={facilityId} onChange={(event) => setFacilityId(event.target.value)}><option value="">All facilities</option>{workspace?.facilities.filter((facility) => facility.status === 'active').map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</Select>
      <IconButton type="button" onClick={() => void load().catch(() => undefined)} disabled={phase === 'loading'} aria-label="Refresh staff rota"><ArrowPathIcon /></IconButton>
    </Toolbar>
    {error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}
    {notice && <Notice role="status"><CheckCircleIcon /> {notice}</Notice>}
    {phase === 'loading' && <Notice role="status"><ArrowPathIcon /> Loading the verified staff plan and clock reconciliation…</Notice>}
    {phase === 'error' && !workspace && <Empty><ExclamationTriangleIcon /><h3>Staff rota unavailable</h3><p>Nothing was changed. Refresh when the connection is available.</p></Empty>}
    {phase === 'ready' && <>
      <Metrics><Metric $accent="cyan"><span>Published shifts</span><strong>{metrics.scheduled}</strong><small>This filtered week</small></Metric><Metric $accent="plasma"><span>Awaiting response</span><strong>{metrics.awaiting}</strong><small>Educator acknowledgement</small></Metric><Metric $accent="cyan"><span>On duty now</span><strong>{metrics.onDuty}</strong><small>Open clock records</small></Metric><Metric $accent="amber"><span>Needs attention</span><strong>{metrics.attention}</strong><small>Late, missed, alternate, unscheduled</small></Metric></Metrics>
      {workspace && <WorkforcePlanningPanel organizationId={organizationId} workspace={workspace} weekStart={weekStart} days={days} preferredFacilityId={facilityId} notificationTarget={focusedWorkforceTarget} onDraftCreated={async () => load(undefined, true)} />}
      {workspace && <ShiftExchangePanel organizationId={organizationId} workspace={workspace} weekStart={weekStart} days={days} preferredFacilityId={facilityId} notificationTarget={focusedWorkforceTarget} requestedSource={coverageSource} onRequestedSourceHandled={() => setCoverageSource(null)} onSchedulesChanged={async () => load(undefined, true)} />}
      <Section><SectionHead><div><h2>Weekly plan</h2><p>Draft privately, then publish. Published shifts cannot be silently edited.</p></div></SectionHead><PlannerScroll><Planner>{days.map((day) => {
        const items = schedules.filter((schedule) => scheduleServiceDate(schedule) === day && (!facilityId || schedule.facility_id === facilityId));
        return <Day key={day} $today={day === serviceDate(new Date().toISOString(), filterTimezone || timezone)}><DayHead><div><strong>{format(parseISO(day), 'EEE')}</strong><small> {format(parseISO(day), 'MMM d')}</small></div><IconButton type="button" onClick={() => openCreate(day)} aria-label={`Create shift on ${format(parseISO(day), 'MMMM d')}`}><PlusIcon /></IconButton></DayHead><DayBody>{items.length ? items.map((schedule) => <ShiftCard key={schedule.id} $focused={focusedScheduleId === schedule.id} data-schedule-id={schedule.id} tabIndex={focusedScheduleId === schedule.id ? -1 : undefined}>
          <div><strong>{timeLabel(schedule.scheduled_start_at, schedule.facility_timezone)}–{timeLabel(schedule.scheduled_end_at, schedule.facility_timezone)} · {schedule.staff_display_name}</strong><small>{schedule.facility_name}{schedule.room_name ? ` · ${schedule.room_name}` : ' · Facility-wide'} · {schedule.facility_timezone}</small></div>
          <ShiftMeta><MiniChip>{schedule.status}</MiniChip>{scheduleOriginLabel(schedule) && <MiniChip $tone="good">{scheduleOriginLabel(schedule)}</MiniChip>}{schedule.status === 'published' && <MiniChip $tone={schedule.response_status === 'acknowledged' ? 'good' : schedule.response_status === 'pending' ? undefined : 'warn'}>{schedule.response_status.replace('_', ' ')}</MiniChip>}{schedule.availability_override_reason && <MiniChip $tone="warn" title={schedule.availability_override_reason}>availability override</MiniChip>}{schedule.reconciliation_status !== 'upcoming' && <MiniChip $tone={['late', 'missed'].includes(schedule.reconciliation_status) ? 'bad' : 'good'}>{schedule.reconciliation_status}</MiniChip>}</ShiftMeta>
          {publishRetryIds.has(schedule.id) && <Proposal><strong>Publication response uncertain</strong><span>Edit and cancellation are locked. Retry exact publish to reuse the same operation safely.</span></Proposal>}
          {schedule.response_status === 'alternate_proposed' && <Proposal><strong>Alternate time proposed</strong><span>{schedule.proposed_start_at ? dateTimeLabel(schedule.proposed_start_at, schedule.facility_timezone) : 'Start not returned'} – {schedule.proposed_end_at ? timeLabel(schedule.proposed_end_at, schedule.facility_timezone) : 'end not returned'}{schedule.response_note ? ` · ${schedule.response_note}` : ''}</span><CardActions><ActionButton type="button" $variant="primary" onClick={() => openProposal(schedule, 'accept')}>Accept alternate</ActionButton><ActionButton type="button" onClick={() => openProposal(schedule, 'reject')}>Keep original</ActionButton></CardActions></Proposal>}
          <CardActions>{schedule.status === 'draft' && <><ActionButton type="button" onClick={() => openEdit(schedule)} disabled={publishRetryIds.has(schedule.id)}><PencilSquareIcon /> Edit</ActionButton><ActionButton type="button" $variant="primary" onClick={() => void publish(schedule)} disabled={Boolean(busy)}><PaperAirplaneIcon /> {busy === `publish:${schedule.id}` ? 'Publishing…' : publishRetryIds.has(schedule.id) ? 'Retry exact publish' : 'Publish'}</ActionButton></>}{schedule.status === 'published' && schedule.reconciliation_status === 'upcoming' && <ActionButton type="button" onClick={() => setCoverageSource(schedule)}><BriefcaseIcon /> Find coverage</ActionButton>}{schedule.status !== 'cancelled' && <ActionButton type="button" $variant="danger" onClick={() => openCancel(schedule)} disabled={publishRetryIds.has(schedule.id)}><XMarkIcon /> Cancel</ActionButton>}</CardActions>
        </ShiftCard>) : <EmptyDay>No shifts planned.</EmptyDay>}</DayBody></Day>;
      })}</Planner></PlannerScroll></Section>
      <Section><SectionHead><div><h2>Planned versus actual</h2><p>Canonical reconciliation refreshed from staff clock records.</p></div></SectionHead>{monitorRows.length ? <Monitor><MonitorTable><thead><tr><th>Staff</th><th>Plan</th><th>Actual</th><th>Facility / room</th><th>Result</th></tr></thead><tbody>{monitorRows.map((row) => <MonitorRow key={row.key} row={row} />)}</tbody></MonitorTable></Monitor> : <Empty><ClockIcon /><h3>No reconciled shifts yet</h3><p>Published shifts and unscheduled clock records will appear here.</p></Empty>}</Section>
    </>}
    {Boolean(editor || cancel || proposal || publishOverride) && <WorkforceModalPortal><>
    {editor && <Overlay role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy && !editor.retryLocked) setEditor(null); }}><Dialog role="dialog" aria-modal="true" aria-labelledby="rota-editor-title"><DialogHead><div><Eyebrow><CalendarDaysIcon width={14} /> {editor.schedule ? 'Edit draft' : 'New draft'}</Eyebrow><h2 id="rota-editor-title">{editor.schedule ? 'Adjust the unpublished shift.' : 'Plan a staff shift.'}</h2><p>Times are entered in {formTimezone}. Saving creates a draft; educators only see it after publication.</p></div><IconButton type="button" onClick={() => setEditor(null)} disabled={Boolean(busy) || editor.retryLocked} aria-label="Close shift editor"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={save}>{editor.retryLocked && <Notice role="status"><ArrowPathIcon /> The last response was uncertain. Fields are locked so Retry exact save reuses the same operation safely.</Notice>}{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<FormGrid>
      <Field><span>Facility</span><select required disabled={editor.retryLocked} value={editor.facilityId} onChange={(event) => setEditor({ ...editor, facilityId: event.target.value, roomId: '', userId: '' })}><option value="">Select facility</option>{workspace?.facilities.filter((facility) => facility.status === 'active').map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</select></Field>
      <Field><span>Room</span><select disabled={editor.retryLocked} value={editor.roomId} onChange={(event) => setEditor({ ...editor, roomId: event.target.value, userId: '' })}><option value="">Facility-wide</option>{formRooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}</select></Field>
      <Field $wide><span>Staff member</span><select required disabled={editor.retryLocked} value={editor.userId} onChange={(event) => setEditor({ ...editor, userId: event.target.value })}><option value="">Select active staff</option>{formMembers.filter((member) => !editor.roomId || member.assigned_room_ids.length === 0 || member.assigned_room_ids.includes(editor.roomId)).map((member) => <option key={member.user_id} value={member.user_id}>{member.first_name} {member.last_name} · {member.role.name}</option>)}</select><small>Only staff assigned to the selected facility and room are available.</small></Field>
      <Field><span>Date</span><input required disabled={editor.retryLocked} type="date" value={editor.date} onChange={(event) => setEditor({ ...editor, date: event.target.value })} /></Field>
      <Field><span>Timezone</span><input readOnly value={formTimezone} /></Field>
      <Field><span>Starts</span><input required disabled={editor.retryLocked} type="time" value={editor.start} onChange={(event) => setEditor({ ...editor, start: event.target.value })} /></Field>
      <Field><span>Ends</span><input required disabled={editor.retryLocked} type="time" value={editor.end} onChange={(event) => setEditor({ ...editor, end: event.target.value })} /></Field>
      <Field $wide><span>Operational note</span><textarea disabled={editor.retryLocked} maxLength={2000} value={editor.notes} onChange={(event) => setEditor({ ...editor, notes: event.target.value })} placeholder="Optional handoff or room coverage note" /></Field>
    </FormGrid><DialogActions><ActionButton type="button" onClick={() => setEditor(null)} disabled={Boolean(busy) || editor.retryLocked}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={Boolean(busy) || !editor.facilityId || !editor.userId}>{busy === 'save' ? 'Saving…' : editor.retryLocked ? 'Retry exact save' : editor.schedule ? 'Save draft changes' : 'Create draft'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {cancel && <Overlay role="presentation"><Dialog role="dialog" aria-modal="true" aria-labelledby="rota-cancel-title"><DialogHead><div><Eyebrow><ExclamationTriangleIcon width={14} /> Cancel shift</Eyebrow><h2 id="rota-cancel-title">Cancel {cancel.schedule.staff_display_name}’s shift?</h2><p>The cancellation remains in the audit trail and published staff will see the updated state.</p></div><IconButton type="button" onClick={() => setCancel(null)} disabled={Boolean(busy) || cancel.retryLocked} aria-label="Close cancellation form"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={confirmCancel}>{cancel.retryLocked && <Notice role="status"><ArrowPathIcon /> The response was uncertain. Retry the exact cancellation before changing its reason.</Notice>}{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Field><span>Required reason</span><textarea required disabled={cancel.retryLocked} minLength={5} maxLength={500} value={cancel.reason} onChange={(event) => setCancel({ ...cancel, reason: event.target.value })} /></Field><DialogActions><ActionButton type="button" onClick={() => setCancel(null)} disabled={Boolean(busy) || cancel.retryLocked}>Keep shift</ActionButton><ActionButton type="submit" $variant="danger" disabled={Boolean(busy)}>{busy === 'cancel' ? 'Cancelling…' : cancel.retryLocked ? 'Retry exact cancellation' : 'Confirm cancellation'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {proposal && <Overlay role="presentation"><Dialog role="dialog" aria-modal="true" aria-labelledby="rota-proposal-title"><DialogHead><div><Eyebrow><ClockIcon width={14} /> Resolve alternate time</Eyebrow><h2 id="rota-proposal-title">{proposal.decision === 'accept' ? 'Accept the educator’s proposed time?' : 'Keep the original shift time?'}</h2><p>{proposal.schedule.staff_display_name} proposed {proposal.schedule.proposed_start_at ? dateTimeLabel(proposal.schedule.proposed_start_at, proposal.schedule.facility_timezone) : 'an alternate start'} to {proposal.schedule.proposed_end_at ? timeLabel(proposal.schedule.proposed_end_at, proposal.schedule.facility_timezone) : 'an alternate end'}. This decision is recorded in the schedule history.</p></div><IconButton type="button" onClick={() => setProposal(null)} disabled={Boolean(busy) || proposal.retryLocked} aria-label="Close proposal resolution"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={resolveProposal}>{proposal.retryLocked && <Notice role="status"><ArrowPathIcon /> The response was uncertain. Retry this exact decision before changing the note.</Notice>}{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Field><span>Decision note (optional)</span><textarea disabled={proposal.retryLocked} maxLength={1000} value={proposal.note} onChange={(event) => setProposal({ ...proposal, note: event.target.value })} placeholder={proposal.decision === 'accept' ? 'Optional approval note' : 'Optional reason for retaining the original time'} /></Field><DialogActions><ActionButton type="button" onClick={() => setProposal(null)} disabled={Boolean(busy) || proposal.retryLocked}>Back</ActionButton><ActionButton type="submit" $variant={proposal.decision === 'accept' ? 'primary' : 'quiet'} disabled={Boolean(busy)}>{busy === 'proposal' ? 'Recording decision…' : proposal.retryLocked ? 'Retry exact decision' : proposal.decision === 'accept' ? 'Accept alternate time' : 'Keep original time'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {publishOverride && <Overlay role="presentation"><Dialog role="dialog" aria-modal="true" aria-labelledby="rota-override-title"><DialogHead><div><Eyebrow><ExclamationTriangleIcon width={14} /> Availability override</Eyebrow><h2 id="rota-override-title">Publish outside declared availability?</h2><p>{publishOverride.schedule.staff_display_name} did not declare availability for this full shift. An override is allowed only for this availability mismatch; approved leave remains a hard block.</p></div><IconButton type="button" onClick={() => setPublishOverride(null)} disabled={Boolean(busy) || publishOverride.retryLocked} aria-label="Close availability override"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={confirmPublishOverride}>{publishOverride.retryLocked && <Notice role="status"><ArrowPathIcon /> The response was uncertain. Retry this exact publication with the same reason and operation identifier.</Notice>}{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Field><span>Required manager reason</span><textarea required disabled={publishOverride.retryLocked} minLength={5} maxLength={500} value={publishOverride.reason} onChange={(event) => setPublishOverride({ ...publishOverride, reason: event.target.value })} placeholder="Explain why this shift should be published outside declared availability" /></Field><DialogActions><ActionButton type="button" onClick={() => setPublishOverride(null)} disabled={Boolean(busy) || publishOverride.retryLocked}>Keep draft</ActionButton><ActionButton type="submit" $variant="primary" disabled={Boolean(busy)}>{busy === 'publish-override' ? 'Publishing…' : publishOverride.retryLocked ? 'Retry exact publication' : 'Publish with override'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    </></WorkforceModalPortal>}
  </Page>;
}

function MonitorRow({ row }: { row: RotaMonitorRow }) {
  const schedule = row.schedule;
  const unscheduled = row.unscheduled;
  const timezone = schedule?.facility_timezone || unscheduled?.facility_timezone || 'UTC';
  const staffName = schedule?.staff_display_name || unscheduled?.staff_display_name || 'Unknown staff';
  const facilityName = schedule?.facility_name || unscheduled?.facility_name || 'Unknown facility';
  return <tr><td><strong>{staffName}</strong><small>{schedule?.response_status ? schedule.response_status.replace('_', ' ') : 'No published plan'}</small></td><td>{schedule ? <>{dateTimeLabel(schedule.scheduled_start_at, timezone)}<small>to {timeLabel(schedule.scheduled_end_at, timezone)}</small></> : 'Unscheduled'}</td><td>{row.actual ? <>{dateTimeLabel(row.actual.clocked_in_at, timezone)}<small>{row.actual.clocked_out_at ? `out ${timeLabel(row.actual.clocked_out_at, timezone)}` : 'Currently clocked in'}</small></> : 'No clock-in'}</td><td>{facilityName}<small>{schedule?.room_name || 'Facility-wide'} · {timezone}</small></td><td><StatusChip $tone={statusTone(row.status)}>{row.status.replace('_', ' ')}{row.minutes_late != null && row.minutes_late > 0 ? ` · ${row.minutes_late}m` : ''}</StatusChip></td></tr>;
}

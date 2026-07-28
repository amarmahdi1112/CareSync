import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  ChartBarSquareIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  PlusIcon,
  SquaresPlusIcon,
  TrashIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { addDays, format, parseISO } from 'date-fns';
import styled from 'styled-components';
import { ApiError } from '../../api/client';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import type { StaffWorkspace } from '../staff/types';
import { workforceApi, workforceErrorMessage } from './workforceApi';
import {
  coverageDayKey,
  coverageSummary,
  coverageTimeLabel,
  coverageTone,
  operationalCoverageDisclaimer,
  shortDateLabel,
  validateCoverageWindows,
  validateWeeklyWindows,
  weekdayLabel,
  WEEKDAYS,
  workforceRoomBoundaryIds,
  type CoverageWindow,
} from './workforceModel';
import type {
  CoverageProjection,
  StaffAvailabilityProfile,
  StaffCoverageTarget,
  StaffShiftTemplate,
  StaffTimeOffRequest,
  WorkforceSnapshot,
} from './workforceTypes';
import { RotationPlanningPanel } from './rotations/RotationPlanningPanel';
import { WorkforceModalOverlay, WorkforceModalPortal, WorkforceModalSurface } from './components/WorkforceDialog';
import type { StaffRotaActionTarget } from './staffRotaNotificationFocus';

const Shell = styled(GlassPanel)`display:grid;gap:0;overflow:visible;`;
const Head = styled.header`
  display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:17px 18px;border-bottom:1px solid ${({ theme }) => theme.color.border};
  h2{margin:6px 0 4px;font-family:"CareSync Display",sans-serif;font-size:1.08rem;font-weight:600;}p{max-width:74ch;margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;line-height:1.55;}
  @media(max-width:720px){align-items:stretch;flex-direction:column;}
`;
const HeadTools = styled.div`display:flex;align-items:center;gap:8px;@media(max-width:720px){>select{flex:1;}}`;
const Select = styled.select`min-height:42px;padding:0 34px 0 11px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:9px 5px 9px 5px;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;font-size:.76rem;`;
const Tabs = styled.div`display:flex;gap:4px;padding:9px 11px;border-bottom:1px solid ${({ theme }) => theme.color.border};overflow-x:auto;`;
const TabPanel = styled.div`display:grid;gap:13px;`;
const Tab = styled.button<{ $active?: boolean }>`
  display:flex;align-items:center;gap:7px;min-height:38px;padding:0 12px;border:1px solid ${({ $active, theme }) => $active ? theme.color.cyan : 'transparent'};border-radius:9px 4px 9px 4px;color:${({ $active, theme }) => $active ? theme.color.text : theme.color.textMuted};background:${({ $active, theme }) => $active ? theme.color.control : 'transparent'};cursor:pointer;font:inherit;font-size:.72rem;font-weight:600;white-space:nowrap;
  svg{width:16px;} &:hover{color:${({ theme }) => theme.color.text};}
`;
const Body = styled.div`display:grid;gap:13px;padding:15px;`;
const Notice = styled.div<{ $error?: boolean }>`display:flex;align-items:flex-start;gap:8px;padding:11px 12px;border:1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.borderStrong};border-radius:8px 12px 8px 12px;color:${({ $error, theme }) => $error ? theme.color.coral : theme.color.textSoft};background:${({ theme }) => theme.color.surfaceStrong};font-size:.72rem;line-height:1.5;svg{width:17px;flex:0 0 auto;}`;
const SectionHead = styled.div`display:flex;align-items:flex-end;justify-content:space-between;gap:12px;h3{margin:0;font-size:.88rem;font-weight:600;}p{margin:4px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.69rem;line-height:1.45;}@media(max-width:600px){align-items:stretch;flex-direction:column;}`;
const Summary = styled.div`display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;@media(max-width:720px){grid-template-columns:repeat(2,minmax(0,1fr));}`;
const SummaryCard = styled.div`padding:11px 12px;border:1px solid ${({ theme }) => theme.color.border};border-radius:8px 12px 8px 12px;background:${({ theme }) => theme.color.surfaceStrong};span,small{display:block;color:${({ theme }) => theme.color.textMuted};font-size:.62rem;}strong{display:block;margin:5px 0 2px;font-size:1.25rem;font-weight:600;}`;
const Heatmap = styled.div`display:grid;gap:7px;overflow-x:auto;padding-bottom:5px;`;
const HeatRow = styled.div`display:grid;grid-template-columns:94px minmax(740px,1fr);align-items:center;gap:9px;strong{font-size:.68rem;font-weight:600;}`;
const HeatCells = styled.div<{ $count: number }>`display:grid;grid-template-columns:repeat(${({ $count }) => Math.max($count, 1)},minmax(5px,1fr));gap:2px;`;
const HeatCell = styled.div<{ $tone: 'clear' | 'watch' | 'gap' | 'inactive' }>`height:20px;border-radius:2px;background:${({ $tone, theme }) => $tone === 'gap' ? theme.color.coral : $tone === 'watch' ? theme.color.amber : $tone === 'clear' ? theme.color.mint : theme.color.control};opacity:${({ $tone }) => $tone === 'inactive' ? .45 : .82};`;
const Legend = styled.div`display:flex;flex-wrap:wrap;gap:10px;color:${({ theme }) => theme.color.textMuted};font-size:.64rem;span{display:flex;align-items:center;gap:5px;}i{width:8px;height:8px;border-radius:2px;background:currentColor;}`;
const Disclaimer = styled.div`padding:10px 12px;border:1px solid ${({ theme }) => theme.color.amber};border-radius:7px 11px 7px 11px;color:${({ theme }) => theme.color.amber};background:rgba(242,190,116,.07);font-size:.68rem;line-height:1.5;`;
const Cards = styled.div`display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;@media(max-width:820px){grid-template-columns:1fr;}`;
const Card = styled.article<{ $focused?: boolean }>`display:grid;gap:9px;padding:12px;border:1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.border};border-radius:9px 13px 9px 13px;background:${({ theme }) => theme.color.surfaceStrong};box-shadow:${({ $focused, theme }) => $focused ? `0 0 0 2px color-mix(in srgb, ${theme.color.cyan} 20%, transparent)` : 'none'};outline:none;h4{margin:0;font-size:.78rem;font-weight:600;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.68rem;line-height:1.45;}small{color:${({ theme }) => theme.color.textMuted};font-size:.64rem;}`;
const CardTop = styled.div`display:flex;align-items:flex-start;justify-content:space-between;gap:10px;`;
const CardActions = styled.div`display:flex;flex-wrap:wrap;gap:6px;button{min-height:34px;padding:0 9px;font-size:.68rem;}button svg{width:14px;}`;
const WindowList = styled.div`display:flex;flex-wrap:wrap;gap:5px;`;
const Window = styled.span`padding:4px 7px;border:1px solid ${({ theme }) => theme.color.borderStrong};border-radius:7px 3px 7px 3px;color:${({ theme }) => theme.color.textSoft};font-size:.62rem;`;
const Empty = styled.div`padding:28px 16px;border:1px dashed ${({ theme }) => theme.color.borderStrong};border-radius:9px;text-align:center;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;`;
const Overlay = styled(WorkforceModalOverlay)``;
const Dialog = styled(WorkforceModalSurface)`width:min(660px,100%);padding:19px;`;
const DialogHead = styled.header`display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:15px;h2{margin:6px 0 4px;font-family:"CareSync Display",sans-serif;font-size:1.18rem;font-weight:600;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.71rem;line-height:1.45;}`;
const Form = styled.form`display:grid;gap:13px;`;
const Grid = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:10px;@media(max-width:570px){grid-template-columns:1fr;}`;
const Field = styled.label<{ $wide?: boolean }>`display:grid;grid-column:${({ $wide }) => $wide ? '1/-1' : 'auto'};gap:5px;color:${({ theme }) => theme.color.textSoft};font-size:.68rem;font-weight:600;input,select,textarea{width:100%;min-height:42px;padding:0 10px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:8px 11px 8px 11px;outline:0;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;}textarea{min-height:78px;padding:9px;resize:vertical;}input:focus,select:focus,textarea:focus{border-color:${({ theme }) => theme.color.cyan};}small{font-weight:400;color:${({ theme }) => theme.color.textMuted};line-height:1.4;}`;
const Rows = styled.div`display:grid;gap:7px;`;
const WindowRow = styled.div`display:grid;grid-template-columns:1.1fr 1fr 1fr .8fr auto;gap:7px;align-items:end;padding:8px;border:1px solid ${({ theme }) => theme.color.border};border-radius:8px;@media(max-width:620px){grid-template-columns:1fr 1fr;.day{grid-column:1/-1}.count{grid-column:1/2}}`;
const DialogActions = styled.div`display:flex;justify-content:flex-end;gap:7px;@media(max-width:480px){flex-direction:column-reverse;button{width:100%;}}`;

type TabKey = 'coverage' | 'timeoff' | 'availability' | 'templates' | 'rotations';
const TAB_KEYS: TabKey[] = ['coverage', 'timeoff', 'availability', 'templates', 'rotations'];
type TimeOffAction = { request: StaffTimeOffRequest; kind: 'approve' | 'decline' | 'cancel'; operationId: string; retryLocked: boolean; note: string };
type TemplateEditor = { template: StaffShiftTemplate | null; operationId: string; retryLocked: boolean; facilityId: string; roomId: string; name: string; weekday: number; start: string; end: string; notes: string };
type TemplateInstantiate = { template: StaffShiftTemplate; operationId: string; retryLocked: boolean; staffUserId: string; serviceDate: string; notes: string };
type TemplateDeactivate = { template: StaffShiftTemplate; operationId: string; retryLocked: boolean };
type TargetEditor = { target: StaffCoverageTarget | null; facilityId: string; roomId: string; operationId: string; retryLocked: boolean; remove: boolean; windows: CoverageWindow[] };

const newOperationId = () => {
  if (!globalThis.crypto?.randomUUID) throw new Error('This browser cannot create a secure operation identifier.');
  return globalThis.crypto.randomUUID();
};
const isDefinitive = (error: unknown) => error instanceof ApiError && error.status >= 400 && error.status < 500 && ![408, 425, 429].includes(error.status);
const dateTime = (value: string, timezone: string) => new Intl.DateTimeFormat('en-CA', { timeZone: timezone, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
const calendarWeekday = (date: string) => (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;

export interface WorkforcePlanningPanelProps {
  organizationId: string;
  workspace: StaffWorkspace;
  weekStart: string;
  days: string[];
  preferredFacilityId?: string;
  notificationTarget?: StaffRotaActionTarget | null;
  onDraftCreated: () => Promise<void> | void;
}

export function WorkforcePlanningPanel({ organizationId, workspace, weekStart, days, preferredFacilityId = '', notificationTarget = null, onDraftCreated }: WorkforcePlanningPanelProps) {
  const activeFacilities = useMemo(() => workspace.facilities.filter((item) => item.status === 'active'), [workspace.facilities]);
  const [facilityId, setFacilityId] = useState(() => preferredFacilityId || activeFacilities[0]?.id || '');
  const [roomId, setRoomId] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>('coverage');
  const [snapshot, setSnapshot] = useState<WorkforceSnapshot | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const [timeOffAction, setTimeOffAction] = useState<TimeOffAction | null>(null);
  const [templateEditor, setTemplateEditor] = useState<TemplateEditor | null>(null);
  const [templateInstantiate, setTemplateInstantiate] = useState<TemplateInstantiate | null>(null);
  const [templateDeactivate, setTemplateDeactivate] = useState<TemplateDeactivate | null>(null);
  const [targetEditor, setTargetEditor] = useState<TargetEditor | null>(null);
  const focusedTargetHandled = useRef('');
  const planningTarget = notificationTarget && ['staff_availability', 'staff_time_off', 'staff_rotation_pattern'].includes(notificationTarget.entityType)
    ? notificationTarget
    : null;

  const tabKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = TAB_KEYS.indexOf(tab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? TAB_KEYS.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + TAB_KEYS.length) % TAB_KEYS.length;
    setTab(TAB_KEYS[next]!);
    requestAnimationFrame(() => document.getElementById(`workforce-tab-${TAB_KEYS[next]}`)?.focus());
  };

  useEffect(() => {
    if (preferredFacilityId && activeFacilities.some((item) => item.id === preferredFacilityId)) { setFacilityId(preferredFacilityId); setRoomId(null); }
  }, [activeFacilities, preferredFacilityId]);
  useEffect(() => {
    if (!planningTarget) {
      focusedTargetHandled.current = '';
      return;
    }
    setFacilityId(planningTarget.facilityId);
    setRoomId(null);
    setTab(
      planningTarget.entityType === 'staff_availability'
        ? 'availability'
        : planningTarget.entityType === 'staff_time_off'
          ? 'timeoff'
          : 'rotations',
    );
    focusedTargetHandled.current = '';
  }, [planningTarget?.entityId, planningTarget?.entityType, planningTarget?.facilityId]);
  const rooms = useMemo(() => workspace.rooms.filter((item) => item.is_active && item.facility_id === facilityId), [facilityId, workspace.rooms]);
  const activeMembers = useMemo(() => workspace.members.filter((item) => item.membership_status === 'active' && item.assigned_facility_ids.includes(facilityId)), [facilityId, workspace.members]);
  const facility = activeFacilities.find((item) => item.id === facilityId);
  const endDate = days[6] || format(addDays(parseISO(weekStart), 6), 'yyyy-MM-dd');
  // Stay just below the server's 366-day maximum. UTC boundaries make the
  // review window broad without guessing a facility wall-clock offset.
  const timeOffStart = `${format(addDays(parseISO(weekStart), -31), 'yyyy-MM-dd')}T00:00:00Z`;
  const timeOffEnd = `${format(addDays(parseISO(weekStart), 334), 'yyyy-MM-dd')}T23:59:59Z`;

  const load = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!organizationId || !facilityId) return;
    if (!quiet) setPhase('loading');
    setError('');
    try {
      const [availability, timeOff, templates, targets, projection] = await Promise.all([
        workforceApi.listAvailability(organizationId, { facilityId }, signal),
        workforceApi.listTimeOff(organizationId, { startAt: timeOffStart, endAt: timeOffEnd }, signal),
        workforceApi.listTemplates(organizationId, { facilityId, includeInactive: true }, signal),
        workforceApi.listTargets(organizationId, facilityId, signal),
        workforceApi.projection({ facilityId, roomId, startDate: weekStart, endDate }, signal),
      ]);
      if (signal?.aborted) return;
      const membershipByUser = new Map(workspace.members.map((item) => [item.user_id, item.membership_id]));
      const knownRooms = workforceRoomBoundaryIds(workspace.rooms, facilityId);
      if (availability.items.some((item) => membershipByUser.get(item.staff_user_id) !== item.membership_id) || timeOff.items.some((item) => membershipByUser.get(item.staff_user_id) !== item.membership_id)) throw new Error('Workforce records returned a staff membership outside the verified workspace.');
      if (templates.items.some((item) => item.room_id && !knownRooms.has(item.room_id)) || targets.items.some((item) => item.room_id && !knownRooms.has(item.room_id))) throw new Error('Workforce records returned a room outside the selected facility.');
      setSnapshot({ availability, timeOff, templates, targets, projection });
      setPhase('ready');
    } catch (caught) {
      if (!signal?.aborted) { setError(workforceErrorMessage(caught)); if (!quiet) setPhase('error'); }
      throw caught;
    }
  }, [endDate, facilityId, organizationId, roomId, rooms, timeOffEnd, timeOffStart, weekStart, workspace.members]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal).catch(() => undefined); return () => controller.abort(); }, [load]);
  useRealtimeRefresh({ scope: 'staff-workforce-planning', organizationId, enabled: Boolean(facilityId), eventPrefixes: ['staff_availability.', 'staff_time_off.', 'staff_shift_template.', 'staff_coverage_target.', 'staff_schedule.', 'staff_shift.'], entityTypes: ['staff_availability', 'staff_time_off', 'staff_shift_template', 'staff_coverage_target', 'staff_schedule', 'staff_shift'], refresh: async () => load(undefined, true) });

  const projection = snapshot?.projection;
  const summary = useMemo(() => coverageSummary(projection?.buckets || []), [projection]);
  const target = snapshot?.targets.items.find((item) => item.room_id === roomId) || null;
  const heatmap = useMemo(() => days.map((day) => ({ day, buckets: (projection?.buckets || []).filter((item) => coverageDayKey(item.starts_at, projection?.facility_timezone || 'UTC') === day) })), [days, projection]);
  const timeOff = useMemo(() => {
    const relevantUsers = new Set(workspace.members.filter((member) => member.assigned_facility_ids.includes(facilityId)).map((member) => member.user_id));
    return [...(snapshot?.timeOff.items || [])].filter((request) => relevantUsers.has(request.staff_user_id)).sort((left, right) => (left.status === 'pending' ? -1 : 1) - (right.status === 'pending' ? -1 : 1) || left.starts_at.localeCompare(right.starts_at));
  }, [facilityId, snapshot, workspace.members]);

  useEffect(() => {
    if (!planningTarget || planningTarget.entityType === 'staff_rotation_pattern' || phase !== 'ready') return;
    const owningTab = planningTarget.entityType === 'staff_availability' ? 'availability' : 'timeoff';
    if (tab !== owningTab) return;
    if (facilityId !== planningTarget.facilityId || snapshot?.projection.facility_id !== planningTarget.facilityId) return;
    const targetKey = `${planningTarget.entityType}:${planningTarget.entityId}`;
    if (focusedTargetHandled.current === targetKey) return;
    focusedTargetHandled.current = targetKey;
    const visible = planningTarget.entityType === 'staff_availability'
      ? snapshot.availability.items.some((item) => item.id === planningTarget.entityId)
      : timeOff.some((item) => item.id === planningTarget.entityId);
    if (!visible) {
      setNotice('The verified workforce record is no longer present in this current manager view. No different row was selected.');
      return;
    }
    const frame = requestAnimationFrame(() => {
      const row = document.querySelector<HTMLElement>(
        `[data-workforce-target="${CSS.escape(targetKey)}"]`,
      );
      row?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      row?.focus({ preventScroll: true });
      setNotice('The exact workforce row is focused from the latest canonical list.');
    });
    return () => cancelAnimationFrame(frame);
  }, [facilityId, phase, planningTarget, snapshot, tab, timeOff]);

  const complete = async (message: string) => {
    try { await load(undefined, true); setNotice(message); }
    catch { setNotice(`${message} The follow-up refresh failed, so use Refresh to load the latest canonical view.`); }
  };
  const resetMutation = <T extends { operationId: string; retryLocked: boolean }>(setter: (value: T | null | ((current: T | null) => T | null)) => void, ambiguous: boolean) => setter((current) => current ? { ...current, operationId: ambiguous ? current.operationId : newOperationId(), retryLocked: ambiguous } : current);

  const submitTimeOff = async (event: FormEvent) => {
    event.preventDefault(); if (!timeOffAction) return;
    if (timeOffAction.kind === 'cancel' && !timeOffAction.note.trim()) { setError('A cancellation reason is required.'); return; }
    setBusy('timeoff'); setError('');
    try {
      const note = timeOffAction.note.trim() || null;
      if (timeOffAction.kind === 'approve') await workforceApi.approveTimeOff(organizationId, timeOffAction.request, timeOffAction.operationId, note);
      else if (timeOffAction.kind === 'decline') await workforceApi.declineTimeOff(organizationId, timeOffAction.request, timeOffAction.operationId, note);
      else await workforceApi.cancelTimeOff(organizationId, timeOffAction.request, timeOffAction.operationId, timeOffAction.note.trim());
      await complete(`Time off ${timeOffAction.kind === 'approve' ? 'approved' : timeOffAction.kind === 'decline' ? 'declined' : 'cancelled'}.`); setTimeOffAction(null);
    } catch (caught) { resetMutation(setTimeOffAction, !isDefinitive(caught)); setError(workforceErrorMessage(caught)); }
    finally { setBusy(''); }
  };

  const submitTemplate = async (event: FormEvent) => {
    event.preventDefault(); if (!templateEditor || !facilityId) return;
    const values = { facility_id: templateEditor.facilityId, room_id: templateEditor.roomId || null, name: templateEditor.name.trim(), weekday: templateEditor.weekday, start_local: templateEditor.start, end_local: templateEditor.end, notes: templateEditor.notes.trim() || null };
    const errors = validateWeeklyWindows([values]);
    if (!values.name || errors.length) { setError(values.name ? errors[0]! : 'Give the template a name.'); return; }
    setBusy('template'); setError('');
    try {
      if (templateEditor.template) await workforceApi.updateTemplate(organizationId, templateEditor.template, templateEditor.operationId, values);
      else await workforceApi.createTemplate(organizationId, { client_operation_id: templateEditor.operationId, ...values });
      await complete(templateEditor.template ? 'Shift template updated.' : 'Reusable shift template created.'); setTemplateEditor(null);
    } catch (caught) { resetMutation(setTemplateEditor, !isDefinitive(caught)); setError(workforceErrorMessage(caught)); }
    finally { setBusy(''); }
  };

  const instantiate = async (event: FormEvent) => {
    event.preventDefault(); if (!templateInstantiate) return;
    if (calendarWeekday(templateInstantiate.serviceDate) !== templateInstantiate.template.weekday) { setError(`Choose a ${weekdayLabel(templateInstantiate.template.weekday)} for this template.`); return; }
    if (!templateInstantiate.retryLocked) {
      const member = activeMembers.find((item) => item.user_id === templateInstantiate.staffUserId);
      if (!member || templateInstantiate.template.room_id && member.assigned_room_ids.length && !member.assigned_room_ids.includes(templateInstantiate.template.room_id)) { setError('Choose a staff member assigned to this template scope.'); return; }
    }
    setBusy('instantiate'); setError('');
    try {
      await workforceApi.instantiateTemplate(organizationId, templateInstantiate.template, templateInstantiate.operationId, templateInstantiate.staffUserId, templateInstantiate.serviceDate, templateInstantiate.notes.trim() || null);
      try { await onDraftCreated(); } catch { /* The mutation receipt is already verified; manual refresh remains available. */ }
      await complete('Template instantiated as an unpublished draft shift.'); setTemplateInstantiate(null);
    } catch (caught) { resetMutation(setTemplateInstantiate, !isDefinitive(caught)); setError(workforceErrorMessage(caught)); }
    finally { setBusy(''); }
  };

  const deactivate = async () => {
    if (!templateDeactivate) return; setBusy('deactivate'); setError('');
    try { await workforceApi.deactivateTemplate(organizationId, templateDeactivate.template, templateDeactivate.operationId); await complete('Shift template deactivated.'); setTemplateDeactivate(null); }
    catch (caught) { resetMutation(setTemplateDeactivate, !isDefinitive(caught)); setError(workforceErrorMessage(caught)); }
    finally { setBusy(''); }
  };

  const submitTarget = async (event: FormEvent) => {
    event.preventDefault(); if (!targetEditor) return;
    if (!targetEditor.remove) {
      const errors = validateCoverageWindows(targetEditor.windows);
      if (errors.length) { setError(errors[0]!); return; }
    }
    setBusy('target'); setError('');
    try {
      const scope = { facilityId: targetEditor.facilityId, roomId: targetEditor.roomId || null };
      if (targetEditor.remove) {
        if (!targetEditor.target) throw new Error('There is no target profile to remove.');
        await workforceApi.removeTarget(scope, targetEditor.target, targetEditor.operationId);
      } else await workforceApi.replaceTarget(organizationId, scope, targetEditor.target, targetEditor.operationId, targetEditor.windows);
      await complete(targetEditor.remove ? 'Operational coverage target removed.' : 'Operational coverage target saved.'); setTargetEditor(null);
    } catch (caught) { resetMutation(setTargetEditor, !isDefinitive(caught)); setError(workforceErrorMessage(caught)); }
    finally { setBusy(''); }
  };

  const openTarget = (remove = false) => setTargetEditor({ target, facilityId, roomId: roomId || '', operationId: newOperationId(), retryLocked: false, remove, windows: target?.windows.map((item) => ({ ...item })) || [{ weekday: 0, start_local: '08:00', end_local: '16:00', required_staff: 1 }] });
  const openTemplate = (value: StaffShiftTemplate | null) => setTemplateEditor({ template: value, operationId: newOperationId(), retryLocked: false, facilityId: value?.facility_id || facilityId, roomId: value?.room_id || '', name: value?.name || '', weekday: value?.weekday ?? 0, start: value?.start_local || '08:00', end: value?.end_local || '16:00', notes: value?.notes || '' });
  const closeDialogs = () => { if (busy || timeOffAction?.retryLocked || templateEditor?.retryLocked || templateInstantiate?.retryLocked || templateDeactivate?.retryLocked || targetEditor?.retryLocked) return; setTimeOffAction(null); setTemplateEditor(null); setTemplateInstantiate(null); setTemplateDeactivate(null); setTargetEditor(null); setError(''); };

  useEffect(() => {
    if (!timeOffAction && !templateEditor && !templateInstantiate && !templateDeactivate && !targetEditor) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') closeDialogs(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [busy, targetEditor, templateDeactivate, templateEditor, templateInstantiate, timeOffAction]);

  return <Shell $accent="cyan">
    <Head><div><Eyebrow><ChartBarSquareIcon width={15} /> Workforce planning</Eyebrow><h2>Coverage, availability, leave, and repeatable shifts</h2><p>Plan against declared availability and approved time off. All dates and wall-clock template times use the facility timezone; the server rejects ambiguous daylight-saving times instead of guessing.</p></div><HeadTools><Select aria-label="Workforce facility" value={facilityId} onChange={(event) => { setFacilityId(event.target.value); setRoomId(null); }} disabled={phase === 'loading'}>{activeFacilities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select><IconButton type="button" onClick={() => void load().catch(() => undefined)} aria-label="Refresh workforce plan" disabled={phase === 'loading'}><ArrowPathIcon /></IconButton></HeadTools></Head>
    <Tabs role="tablist" aria-label="Workforce planning sections" onKeyDown={tabKeyDown}>
      <Tab id="workforce-tab-coverage" role="tab" tabIndex={tab === 'coverage' ? 0 : -1} aria-controls="workforce-panel-coverage" aria-selected={tab === 'coverage'} $active={tab === 'coverage'} onClick={() => setTab('coverage')}><ChartBarSquareIcon /> Coverage</Tab>
      <Tab id="workforce-tab-timeoff" role="tab" tabIndex={tab === 'timeoff' ? 0 : -1} aria-controls="workforce-panel-timeoff" aria-selected={tab === 'timeoff'} $active={tab === 'timeoff'} onClick={() => setTab('timeoff')}><CalendarDaysIcon /> Time off</Tab>
      <Tab id="workforce-tab-availability" role="tab" tabIndex={tab === 'availability' ? 0 : -1} aria-controls="workforce-panel-availability" aria-selected={tab === 'availability'} $active={tab === 'availability'} onClick={() => setTab('availability')}><UserGroupIcon /> Availability</Tab>
      <Tab id="workforce-tab-templates" role="tab" tabIndex={tab === 'templates' ? 0 : -1} aria-controls="workforce-panel-templates" aria-selected={tab === 'templates'} $active={tab === 'templates'} onClick={() => setTab('templates')}><SquaresPlusIcon /> Single-shift templates</Tab>
      <Tab id="workforce-tab-rotations" role="tab" tabIndex={tab === 'rotations' ? 0 : -1} aria-controls="workforce-panel-rotations" aria-selected={tab === 'rotations'} $active={tab === 'rotations'} onClick={() => setTab('rotations')}><ArrowPathIcon /> Rotations</Tab>
    </Tabs>
    <Body>
      {error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}
      {notice && <Notice role="status"><CheckCircleIcon /> {notice}</Notice>}
      {phase === 'loading' && <Notice role="status"><ArrowPathIcon /> Loading canonical workforce records…</Notice>}
      {phase === 'error' && !snapshot && <Empty>Workforce planning is unavailable. Nothing was changed; refresh when the connection returns.</Empty>}
      {phase === 'ready' && tab === 'coverage' && <TabPanel role="tabpanel" id="workforce-panel-coverage" aria-labelledby="workforce-tab-coverage">
        <SectionHead><div><h3>Weekly operational coverage</h3><p>{facility?.name} · {projection?.facility_timezone} · 15-minute server projection</p></div><div><Select aria-label="Coverage room scope" value={roomId || ''} onChange={(event) => setRoomId(event.target.value || null)}><option value="">Facility-wide</option>{rooms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></div></SectionHead>
        <Summary><SummaryCard><span>Intervals covered</span><strong>{summary.coveragePercent}%</strong><small>Non-declined published plan meets target</small></SummaryCard><SummaryCard><span>Published gaps</span><strong>{summary.gapIntervals}</strong><small>Declined shifts do not close gaps</small></SummaryCard><SummaryCard><span>Confirmation risk</span><strong>{summary.acknowledgementRiskIntervals}</strong><small>Published, not acknowledged</small></SummaryCard><SummaryCard><span>Largest gap</span><strong>{summary.maxGap}</strong><small>Staff in one interval</small></SummaryCard></Summary>
        {summary.gapIntervals > 0 && <Notice $error role="status"><ExclamationTriangleIcon /> {summary.gapIntervals} operational interval{summary.gapIntervals === 1 ? '' : 's'} remain below target, with a largest gap of {summary.maxGap} staff. Declined shifts do not count as available coverage.</Notice>}
        {summary.acknowledgementRiskIntervals > 0 && <Notice role="status"><ClockIcon /> {summary.acknowledgementRiskIntervals} interval{summary.acknowledgementRiskIntervals === 1 ? '' : 's'} meet the published target but still depend on staff who have not acknowledged their shifts.</Notice>}
        <Heatmap role="img" aria-label={`Weekly operational coverage heatmap: ${summary.coveragePercent} percent of targeted intervals covered, ${summary.gapIntervals} published gaps, ${summary.acknowledgementRiskIntervals} confirmation risks.`}>{heatmap.map(({ day, buckets }) => <HeatRow key={day}><strong>{shortDateLabel(day)}</strong><HeatCells $count={buckets.length} aria-hidden="true">{buckets.length ? buckets.map((cell) => <HeatCell key={cell.starts_at} $tone={coverageTone(cell)} title={`${coverageTimeLabel(cell.starts_at, projection!.facility_timezone)} · target ${cell.required} · published ${cell.published} · acknowledged ${cell.acknowledged} · declined ${cell.declined} · draft ${cell.draft}`} />) : <HeatCell $tone="inactive" style={{ gridColumn: '1/-1' }} />}</HeatCells></HeatRow>)}</Heatmap>
        <Legend><span style={{ color: '#8ed8b0' }}><i />Target met and acknowledged</span><span style={{ color: '#f2be74' }}><i />Published but awaiting confirmation</span><span style={{ color: '#ee9187' }}><i />Published coverage gap</span><span>Draft counts are visible in cell details but do not close published gaps.</span></Legend>
        <Disclaimer><strong>Boundary:</strong> {operationalCoverageDisclaimer}</Disclaimer>
        <SectionHead><div><h3>{target ? 'Configured target profile' : 'No target configured for this scope'}</h3><p>{target ? `${target.windows.length} recurring local-time window${target.windows.length === 1 ? '' : 's'} · last updated ${dateTime(target.updated_at, target.facility_timezone)}` : 'Without targets, the heatmap reports schedule counts but no staffing gap.'}</p></div><CardActions><ActionButton type="button" onClick={() => openTarget(false)}><PencilSquareIcon /> {target ? 'Edit targets' : 'Set targets'}</ActionButton>{target && <ActionButton type="button" $variant="danger" onClick={() => openTarget(true)}><TrashIcon /> Remove</ActionButton>}</CardActions></SectionHead>
        {target && <WindowList>{target.windows.map((item, index) => <Window key={`${item.weekday}:${item.start_local}:${index}`}>{weekdayLabel(item.weekday)} {item.start_local}–{item.end_local} · {item.required_staff} staff</Window>)}</WindowList>}
      </TabPanel>}
      {phase === 'ready' && tab === 'timeoff' && <TabPanel role="tabpanel" id="workforce-panel-timeoff" aria-labelledby="workforce-tab-timeoff"><SectionHead><div><h3>Manager time-off review</h3><p>Shows organization-wide requests for staff assigned to this facility, even when the request originated elsewhere. Approved leave is membership-wide and cannot overlap a published shift.</p></div></SectionHead>{timeOff.length ? <Cards>{timeOff.map((request) => { const focused = planningTarget?.entityType === 'staff_time_off' && planningTarget.entityId === request.id; return <Card key={request.id} $focused={focused} data-workforce-target={`staff_time_off:${request.id}`} tabIndex={focused ? -1 : undefined}><CardTop><div><h4>{request.staff_display_name}</h4><p>{request.category} · requested under {request.facility_name} · {dateTime(request.starts_at, request.facility_timezone)} to {dateTime(request.ends_at, request.facility_timezone)}</p></div><StatusChip $tone={request.status === 'approved' ? 'success' : request.status === 'pending' ? 'info' : 'warning'}>{request.status}</StatusChip></CardTop>{request.note && <p>Staff note: {request.note}</p>}{request.response_note && <p>Manager note: {request.response_note}</p>}{request.cancellation_reason && <p>Cancellation: {request.cancellation_reason}</p>}<CardActions>{request.status === 'pending' && <><ActionButton type="button" $variant="primary" onClick={() => setTimeOffAction({ request, kind: 'approve', operationId: newOperationId(), retryLocked: false, note: '' })}>Approve</ActionButton><ActionButton type="button" onClick={() => setTimeOffAction({ request, kind: 'decline', operationId: newOperationId(), retryLocked: false, note: '' })}>Decline</ActionButton></>}{request.can_cancel && <ActionButton type="button" $variant="danger" onClick={() => setTimeOffAction({ request, kind: 'cancel', operationId: newOperationId(), retryLocked: false, note: '' })}>Cancel request</ActionButton>}</CardActions></Card>; })}</Cards> : <Empty>No time-off requests for staff assigned to this facility in the loaded planning range.</Empty>}</TabPanel>}
      {phase === 'ready' && tab === 'availability' && <TabPanel role="tabpanel" id="workforce-panel-availability" aria-labelledby="workforce-tab-availability"><SectionHead><div><h3>Declared weekly availability</h3><p>A missing profile means unspecified availability. A saved profile with no windows explicitly means unavailable.</p></div></SectionHead>{snapshot?.availability.items.length ? <Cards>{snapshot.availability.items.map((profile: StaffAvailabilityProfile) => { const focused = planningTarget?.entityType === 'staff_availability' && planningTarget.entityId === profile.id; return <Card key={profile.id} $focused={focused} data-workforce-target={`staff_availability:${profile.id}`} tabIndex={focused ? -1 : undefined}><CardTop><div><h4>{profile.staff_display_name}</h4><p>{profile.facility_name} · {profile.facility_timezone}</p></div><StatusChip $tone={profile.windows.length ? 'success' : 'warning'}>{profile.windows.length ? `${profile.windows.length} windows` : 'Unavailable'}</StatusChip></CardTop>{profile.windows.length ? <WindowList>{profile.windows.map((item, index) => <Window key={`${item.weekday}:${item.start_local}:${index}`}>{weekdayLabel(item.weekday)} {item.start_local}–{item.end_local}</Window>)}</WindowList> : <p>This educator explicitly declared no available time.</p>}{profile.note && <p>Note: {profile.note}</p>}<small>Updated {dateTime(profile.updated_at, profile.facility_timezone)}</small></Card>; })}</Cards> : <Empty>No staff member has declared availability at this facility. Treat these records as unspecified, not unavailable.</Empty>}</TabPanel>}
      {phase === 'ready' && tab === 'templates' && <TabPanel role="tabpanel" id="workforce-panel-templates" aria-labelledby="workforce-tab-templates"><SectionHead><div><h3>Reusable single-shift templates</h3><p>Templates create one selected draft. Rotations generate bounded recurring drafts after a separate server preview.</p></div><ActionButton type="button" $variant="primary" onClick={() => openTemplate(null)}><PlusIcon /> New template</ActionButton></SectionHead>{snapshot?.templates.items.length ? <Cards>{snapshot.templates.items.map((template) => <Card key={template.id}><CardTop><div><h4>{template.name}</h4><p>{weekdayLabel(template.weekday)} · {template.start_local}–{template.end_local} · {template.room_name || 'Facility-wide'}</p></div><StatusChip $tone={template.is_active ? 'success' : 'neutral'}>{template.is_active ? 'Active' : 'Inactive'}</StatusChip></CardTop>{template.notes && <p>{template.notes}</p>}{template.is_active && <CardActions><ActionButton type="button" onClick={() => openTemplate(template)}><PencilSquareIcon /> Edit</ActionButton><ActionButton type="button" $variant="primary" onClick={() => setTemplateInstantiate({ template, operationId: newOperationId(), retryLocked: false, staffUserId: '', serviceDate: days.find((day) => calendarWeekday(day) === template.weekday) || weekStart, notes: '' })}><SquaresPlusIcon /> Create draft</ActionButton><ActionButton type="button" $variant="danger" onClick={() => setTemplateDeactivate({ template, operationId: newOperationId(), retryLocked: false })}>Deactivate</ActionButton></CardActions>}</Card>)}</Cards> : <Empty>No reusable shift templates yet.</Empty>}</TabPanel>}
      {tab === 'rotations' && <RotationPlanningPanel organizationId={organizationId} workspace={workspace} facilityId={facilityId} weekStart={weekStart} enabled={phase === 'ready'} focusedPatternId={planningTarget?.entityType === 'staff_rotation_pattern' ? planningTarget.entityId : null} onDraftsGenerated={onDraftCreated} />}
    </Body>
    {Boolean(timeOffAction || templateEditor || templateInstantiate || templateDeactivate || targetEditor) && <WorkforceModalPortal><>
    {timeOffAction && <Overlay onMouseDown={(event) => { if (event.target === event.currentTarget) closeDialogs(); }}><Dialog role="dialog" aria-modal="true" aria-labelledby="timeoff-action-title"><DialogHead><div><Eyebrow><CalendarDaysIcon width={14} /> Time-off decision</Eyebrow><h2 id="timeoff-action-title">{timeOffAction.kind[0]!.toUpperCase() + timeOffAction.kind.slice(1)} {timeOffAction.request.staff_display_name}’s request?</h2><p>{dateTime(timeOffAction.request.starts_at, timeOffAction.request.facility_timezone)} to {dateTime(timeOffAction.request.ends_at, timeOffAction.request.facility_timezone)}.</p></div><IconButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || timeOffAction.retryLocked} aria-label="Close time-off decision"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={submitTimeOff}>{timeOffAction.retryLocked && <Notice><ArrowPathIcon /> The response was uncertain. Fields are locked so Retry exact decision reuses the same operation.</Notice>}<Field><span>{timeOffAction.kind === 'cancel' ? 'Required cancellation reason' : 'Decision note (optional)'}</span><textarea disabled={timeOffAction.retryLocked} required={timeOffAction.kind === 'cancel'} maxLength={1000} value={timeOffAction.note} onChange={(event) => setTimeOffAction({ ...timeOffAction, note: event.target.value })} /></Field><DialogActions><ActionButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || timeOffAction.retryLocked}>Back</ActionButton><ActionButton type="submit" $variant={timeOffAction.kind === 'approve' ? 'primary' : timeOffAction.kind === 'cancel' ? 'danger' : 'quiet'} disabled={Boolean(busy)}>{busy === 'timeoff' ? 'Recording…' : timeOffAction.retryLocked ? 'Retry exact decision' : 'Confirm'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {templateEditor && <Overlay onMouseDown={(event) => { if (event.target === event.currentTarget) closeDialogs(); }}><Dialog role="dialog" aria-modal="true" aria-labelledby="template-editor-title"><DialogHead><div><Eyebrow><SquaresPlusIcon width={14} /> Shift template</Eyebrow><h2 id="template-editor-title">{templateEditor.template ? 'Edit reusable template' : 'Create reusable template'}</h2><p>Times use {workspace.facilities.find((item) => item.id === templateEditor.facilityId)?.timezone}. Templates do not publish shifts.</p></div><IconButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateEditor.retryLocked} aria-label="Close template editor"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={submitTemplate}>{templateEditor.retryLocked && <Notice><ArrowPathIcon /> The response was uncertain. Retry this exact template save before editing.</Notice>}<Grid><Field $wide><span>Name</span><input required disabled={templateEditor.retryLocked} maxLength={150} value={templateEditor.name} onChange={(event) => setTemplateEditor({ ...templateEditor, name: event.target.value })} /></Field><Field><span>Room scope</span><select disabled={templateEditor.retryLocked} value={templateEditor.roomId} onChange={(event) => setTemplateEditor({ ...templateEditor, roomId: event.target.value })}><option value="">Facility-wide</option>{workspace.rooms.filter((item) => item.is_active && item.facility_id === templateEditor.facilityId).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field><span>Weekday</span><select disabled={templateEditor.retryLocked} value={templateEditor.weekday} onChange={(event) => setTemplateEditor({ ...templateEditor, weekday: Number(event.target.value) })}>{WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></Field><Field><span>Starts</span><input type="time" required disabled={templateEditor.retryLocked} value={templateEditor.start} onChange={(event) => setTemplateEditor({ ...templateEditor, start: event.target.value })} /></Field><Field><span>Ends</span><input type="time" required disabled={templateEditor.retryLocked} value={templateEditor.end} onChange={(event) => setTemplateEditor({ ...templateEditor, end: event.target.value })} /></Field><Field $wide><span>Default note</span><textarea disabled={templateEditor.retryLocked} maxLength={2000} value={templateEditor.notes} onChange={(event) => setTemplateEditor({ ...templateEditor, notes: event.target.value })} /></Field></Grid><DialogActions><ActionButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateEditor.retryLocked}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={Boolean(busy)}>{busy === 'template' ? 'Saving…' : templateEditor.retryLocked ? 'Retry exact save' : 'Save template'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {templateInstantiate && <Overlay onMouseDown={(event) => { if (event.target === event.currentTarget) closeDialogs(); }}><Dialog role="dialog" aria-modal="true" aria-labelledby="instantiate-title"><DialogHead><div><Eyebrow><SquaresPlusIcon width={14} /> Draft from template</Eyebrow><h2 id="instantiate-title">Create a draft from {templateInstantiate.template.name}</h2><p>{weekdayLabel(templateInstantiate.template.weekday)} {templateInstantiate.template.start_local}–{templateInstantiate.template.end_local} in {templateInstantiate.template.facility_timezone}. The server resolves the chosen local date safely.</p></div><IconButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateInstantiate.retryLocked} aria-label="Close draft form"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={instantiate}>{templateInstantiate.retryLocked && <Notice><ArrowPathIcon /> The response was uncertain. Retry this exact draft creation before editing.</Notice>}<Grid><Field><span>Staff member</span><select required disabled={templateInstantiate.retryLocked} value={templateInstantiate.staffUserId} onChange={(event) => setTemplateInstantiate({ ...templateInstantiate, staffUserId: event.target.value })}><option value="">Select staff</option>{activeMembers.filter((member) => !templateInstantiate.template.room_id || !member.assigned_room_ids.length || member.assigned_room_ids.includes(templateInstantiate.template.room_id)).map((member) => <option key={member.user_id} value={member.user_id}>{member.first_name} {member.last_name}</option>)}</select></Field><Field><span>Service date</span><input required type="date" disabled={templateInstantiate.retryLocked} value={templateInstantiate.serviceDate} onChange={(event) => setTemplateInstantiate({ ...templateInstantiate, serviceDate: event.target.value })} /></Field><Field $wide><span>Shift note</span><textarea disabled={templateInstantiate.retryLocked} maxLength={2000} value={templateInstantiate.notes} onChange={(event) => setTemplateInstantiate({ ...templateInstantiate, notes: event.target.value })} placeholder={templateInstantiate.template.notes || 'Optional note'} /></Field></Grid><DialogActions><ActionButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateInstantiate.retryLocked}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={Boolean(busy) || !templateInstantiate.staffUserId}>{busy === 'instantiate' ? 'Creating…' : templateInstantiate.retryLocked ? 'Retry exact creation' : 'Create draft'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    {templateDeactivate && <Overlay><Dialog role="dialog" aria-modal="true" aria-labelledby="deactivate-title"><DialogHead><div><Eyebrow><ExclamationTriangleIcon width={14} /> Deactivate template</Eyebrow><h2 id="deactivate-title">Deactivate {templateDeactivate.template.name}?</h2><p>Existing shifts are unchanged. This template can no longer create new drafts.</p></div><IconButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateDeactivate.retryLocked} aria-label="Close deactivation"><XMarkIcon /></IconButton></DialogHead>{templateDeactivate.retryLocked && <Notice><ArrowPathIcon /> The response was uncertain. Retry the exact deactivation.</Notice>}<DialogActions><ActionButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || templateDeactivate.retryLocked}>Keep active</ActionButton><ActionButton type="button" $variant="danger" onClick={() => void deactivate()} disabled={Boolean(busy)}>{busy === 'deactivate' ? 'Deactivating…' : templateDeactivate.retryLocked ? 'Retry exact deactivation' : 'Deactivate'}</ActionButton></DialogActions></Dialog></Overlay>}
    {targetEditor && <Overlay onMouseDown={(event) => { if (event.target === event.currentTarget) closeDialogs(); }}><Dialog role="dialog" aria-modal="true" aria-labelledby="target-title"><DialogHead><div><Eyebrow><ChartBarSquareIcon width={14} /> Operational coverage target</Eyebrow><h2 id="target-title">{targetEditor.remove ? 'Remove this target profile?' : 'Configure recurring target windows'}</h2><p>{targetEditor.roomId ? workspace.rooms.find((item) => item.id === targetEditor.roomId)?.name : 'Facility-wide'} · {workspace.facilities.find((item) => item.id === targetEditor.facilityId)?.timezone}</p></div><IconButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || targetEditor.retryLocked} aria-label="Close target editor"><XMarkIcon /></IconButton></DialogHead><Form onSubmit={submitTarget}>{targetEditor.retryLocked && <Notice><ArrowPathIcon /> The response was uncertain. Fields are locked so Retry exact operation reuses the same receipt.</Notice>}<Disclaimer>{operationalCoverageDisclaimer}</Disclaimer>{targetEditor.remove ? <Notice $error><TrashIcon /> Removing the profile clears operational targets for this exact scope. It does not change any shift.</Notice> : <><Rows>{targetEditor.windows.map((item, index) => <WindowRow key={index}><Field className="day"><span>Day</span><select disabled={targetEditor.retryLocked} value={item.weekday} onChange={(event) => setTargetEditor({ ...targetEditor, windows: targetEditor.windows.map((row, rowIndex) => rowIndex === index ? { ...row, weekday: Number(event.target.value) } : row) })}>{WEEKDAYS.map((day, dayIndex) => <option key={day} value={dayIndex}>{day}</option>)}</select></Field><Field><span>Starts</span><input type="time" step={900} disabled={targetEditor.retryLocked} value={item.start_local} onChange={(event) => setTargetEditor({ ...targetEditor, windows: targetEditor.windows.map((row, rowIndex) => rowIndex === index ? { ...row, start_local: event.target.value } : row) })} /></Field><Field><span>Ends</span><input type="time" step={900} disabled={targetEditor.retryLocked} value={item.end_local} onChange={(event) => setTargetEditor({ ...targetEditor, windows: targetEditor.windows.map((row, rowIndex) => rowIndex === index ? { ...row, end_local: event.target.value } : row) })} /></Field><Field className="count"><span>Staff</span><input type="number" min={0} max={500} step={1} disabled={targetEditor.retryLocked} value={item.required_staff} onChange={(event) => setTargetEditor({ ...targetEditor, windows: targetEditor.windows.map((row, rowIndex) => rowIndex === index ? { ...row, required_staff: Number(event.target.value) } : row) })} /></Field><IconButton type="button" disabled={targetEditor.retryLocked} onClick={() => setTargetEditor({ ...targetEditor, windows: targetEditor.windows.filter((_, rowIndex) => rowIndex !== index) })} aria-label={`Remove ${weekdayLabel(item.weekday)} target window`}><TrashIcon /></IconButton></WindowRow>)}</Rows><ActionButton type="button" disabled={targetEditor.retryLocked} onClick={() => setTargetEditor({ ...targetEditor, windows: [...targetEditor.windows, { weekday: 0, start_local: '08:00', end_local: '16:00', required_staff: 1 }] })}><PlusIcon /> Add window</ActionButton></>}<DialogActions><ActionButton type="button" onClick={closeDialogs} disabled={Boolean(busy) || targetEditor.retryLocked}>Cancel</ActionButton><ActionButton type="submit" $variant={targetEditor.remove ? 'danger' : 'primary'} disabled={Boolean(busy)}>{busy === 'target' ? 'Saving…' : targetEditor.retryLocked ? 'Retry exact operation' : targetEditor.remove ? 'Remove target' : 'Save target'}</ActionButton></DialogActions></Form></Dialog></Overlay>}
    </></WorkforceModalPortal>}
  </Shell>;
}

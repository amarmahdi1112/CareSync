import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ArrowRightStartOnRectangleIcon,
  ArrowRightEndOnRectangleIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  NoSymbolIcon,
  PencilSquareIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { useSession } from '../../auth/SessionContext';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import ChildAvatar from '../children/ChildAvatar';
import {
  checkIn,
  checkOut,
  correctAttendanceStatus,
  correctInterval,
  fetchAttendanceFacilities,
  fetchAttendanceReleaseCheckoutActivation,
  fetchAttendanceRoster,
  markAbsent,
  AttendanceApiError,
  type AttendanceFacility,
  type AttendanceIntervalRecord,
  type AttendanceReleaseCheckoutActivationStatus,
  type AttendanceRosterRow,
} from './attendanceApi';
import { attendanceCounts, attendancePresentation, attendanceState, validateCorrection, type AttendanceState } from './attendanceModel';
import { attendanceOperationKey, attendanceOperationResolved, readPendingAttendanceOperation, type PendingAttendanceOperation } from './attendanceOperation';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';

const Page = styled.div`display: grid; gap: 24px;`;
const Header = styled.header`
  display: flex; align-items: flex-end; justify-content: space-between; gap: 20px;
  h1 { margin: 10px 0 7px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 3.2vw, 2.8rem); font-weight: 520; letter-spacing: -.035em; line-height: 1.05; }
  p { max-width: 700px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .875rem; line-height: 1.65; }
  @media (max-width: 760px) { align-items: flex-start; flex-direction: column; }
`;
const DateBadge = styled(GlassPanel)`min-width: 245px; padding: 15px 18px; span { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; } strong { display: block; margin-top: 5px; font-size: .8125rem; }`;
const Controls = styled(GlassPanel)`
  display: grid; grid-template-columns: minmax(180px, .7fr) minmax(190px, 1fr) minmax(200px, 1.25fr) minmax(130px,.5fr) auto; gap: 10px; padding: 13px;
  input, select { width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 10px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .8125rem; }
  input:focus, select:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent); }
  @media (max-width: 1000px) { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: 580px) { grid-template-columns: 1fr; }
`;
const Search = styled.label`position: relative; display: block; input { padding-left: 37px; } svg { position: absolute; top: 13px; left: 12px; width: 17px; color: ${({ theme }) => theme.color.textMuted}; }`;
const Metrics = styled.div`display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 10px; @media (max-width: 900px) { grid-template-columns: repeat(2,1fr); } @media (max-width: 480px) { grid-template-columns: 1fr; }`;
const Metric = styled(GlassPanel)<{ $tone?: 'mint' | 'amber' | 'plasma' }>`
  padding: 15px; span { display: flex; align-items: center; gap: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; letter-spacing: .07em; text-transform: uppercase; }
  svg { width: 16px; color: ${({ $tone, theme }) => $tone === 'mint' ? theme.color.mint : $tone === 'amber' ? theme.color.amber : $tone === 'plasma' ? theme.color.plasmaBright : theme.color.cyan}; }
  strong { display: block; margin-top: 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.75rem; font-weight: 590; }
`;
const Notice = styled.div<{ $error?: boolean }>`display: flex; align-items: flex-start; gap: 9px; padding: 12px 14px; border: 1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.cyan}; border-radius: 10px 14px 10px 10px; color: ${({ $error, theme }) => $error ? theme.color.coral : theme.color.cyan}; background: ${({ $error, theme }) => $error ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.coral})` : `color-mix(in srgb, ${theme.color.surfaceStrong} 89%, ${theme.color.cyan})`}; font-size: .8125rem; line-height: 1.55; svg { width: 18px; flex: 0 0 auto; }`;
const NoticeLink = styled(Link)`color: inherit; font-weight: 650; text-decoration: underline; text-underline-offset: 3px;`;
const Roster = styled(GlassPanel)`overflow: visible;`;
const RosterHeader = styled.div`display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 18px 20px; border-bottom: 1px solid ${({ theme }) => theme.color.divider}; h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.25rem; } p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }`;
const Row = styled.div`
  display: grid; grid-template-columns: minmax(190px,1.25fr) minmax(120px,.7fr) minmax(140px,.8fr) minmax(260px,1.25fr) 38px; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid ${({ theme }) => theme.color.divider};
  &:last-child { border-bottom: 0; }
  @media (max-width: 900px) { grid-template-columns: 1fr auto; > div:nth-child(2), > div:nth-child(3) { display: none; } > div:nth-child(4) { grid-column: 1 / -1; } }
`;
const Child = styled.div`min-width: 0;`;
const ChildIdentity = styled.div`
  display: flex; min-width: 0; align-items: center; gap: 11px;
  strong { display: block; overflow: hidden; font-size: .8125rem; text-overflow: ellipsis; white-space: nowrap; }
  small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;
const ChildProfileLink = styled(Link)`
  display: flex; min-width: 0; align-items: center; gap: 11px; border-radius: 11px; color: inherit;
  &:hover strong { color: ${({ theme }) => theme.color.cyan}; }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 4px; }
  strong { display: block; overflow: hidden; font-size: .8125rem; text-overflow: ellipsis; white-space: nowrap; transition: color ${({ theme }) => theme.motion.fast} ease; }
  small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;
const Cell = styled.div`strong { display: block; font-size: .8125rem; font-weight: 600; } small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }`;
const Actions = styled.div`display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; @media (max-width: 900px) { justify-content: flex-start; }`;
const RowAction = styled.button<{ $primary?: boolean; $secondary?: boolean }>`
  display: inline-flex; min-height: 44px; align-items: center; gap: 7px; padding: 0 12px; border: 1px solid ${({ $secondary, $primary, theme }) => $secondary ? theme.color.amber : $primary ? theme.color.mint : theme.color.controlBorder}; border-radius: 9px 12px 9px 9px;
  color: ${({ $secondary, $primary, theme }) => $secondary ? theme.color.amber : $primary ? theme.color.mint : theme.color.textSoft}; background: ${({ $secondary, $primary, theme }) => $secondary ? `color-mix(in srgb, ${theme.color.surfaceStrong} 94%, ${theme.color.amber})` : $primary ? `color-mix(in srgb, ${theme.color.surfaceStrong} 92%, ${theme.color.mint})` : theme.color.surfaceStrong}; cursor: pointer; font-size: .75rem; font-weight: 600; transition: background ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease}, border-color ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};
  &:hover:not(:disabled) { background: ${({ theme }) => theme.color.surfaceHover}; }
  &:disabled { opacity: .45; cursor: wait; } svg { width: 15px; }
`;
const CheckoutHandoff = styled.span`display: inline-flex; min-height: 44px; align-items: center; gap: 7px; padding: 0 12px; border: 1px solid ${({ theme }) => theme.color.cyan}; border-radius: 9px 12px 9px 9px; color: ${({ theme }) => theme.color.cyan}; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 92%, ${({ theme }) => theme.color.cyan}); font-size: .75rem; font-weight: 600; svg { width: 15px; }`;
const Detail = styled.div`grid-column: 1 / -1; display: grid; grid-template-columns: minmax(0,1fr) minmax(240px,.55fr); gap: 14px; padding: 14px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px; background: ${({ theme }) => theme.color.surfaceStrong}; @media (max-width: 720px) { grid-template-columns: 1fr; }`;
const IntervalList = styled.div`display: grid; gap: 7px;`;
const Interval = styled.div`display: grid; grid-template-columns: 32px 1fr auto; align-items: center; gap: 10px; padding: 9px 10px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 9px 12px 9px 9px; background: ${({ theme }) => theme.color.surface}; span { display: grid; width: 28px; height: 28px; place-items: center; border-radius: 7px 10px 7px 7px; color: ${({ theme }) => theme.color.cyan}; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 86%, ${({ theme }) => theme.color.cyan}); font-size: .72rem; font-weight: 600; } strong { display: block; font-size: .8125rem; } small { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }`;
const EventList = styled.div`display: grid; align-content: start; gap: 7px; h3 { margin: 0 0 2px; font-size: .8125rem; } p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.5; }`;
const Empty = styled.div`display: grid; min-height: 280px; place-items: center; padding: 30px; text-align: center; svg { width: 46px; margin: 0 auto 12px; color: ${({ theme }) => theme.color.textMuted}; } h2 { margin: 0 0 7px; } p { max-width: 520px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; line-height: 1.65; }`;
const Gate = styled(GlassPanel)`display: grid; min-height: 340px; place-items: center; padding: 30px; text-align: center; svg { width: 44px; margin: 0 auto 12px; color: ${({ theme }) => theme.color.cyan}; } h2 { margin: 0 0 7px; } p { max-width: 520px; margin: 0 auto 16px; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; }`;
const Overlay = styled.div`position: fixed; inset: 0; z-index: 900; display: grid; place-items: center; padding: 18px; background: ${({ theme }) => theme.color.overlay}; backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});`;
const Dialog = styled(GlassPanel)`width: min(590px,100%); padding: 22px;`;
const DialogHeader = styled.div`display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 18px; h2 { margin: 6px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: 1.5rem; } p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }`;
const Form = styled.form`display: grid; gap: 14px;`;
const Field = styled.label`display: grid; gap: 6px; span { color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; font-weight: 600; } input, textarea { width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 10px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .8125rem; } textarea { min-height: 90px; padding-top: 11px; resize: vertical; } input:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; }`;
const DialogFields = styled.div`display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; @media (max-width: 520px) { grid-template-columns: 1fr; }`;
const DialogActions = styled.div`display: flex; justify-content: flex-end; gap: 8px;`;

function dateInputValue(now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function childNameParts(name: string): { firstName: string; lastName: string } {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return { firstName: parts[0] || 'Child', lastName: parts.slice(1).join(' ') };
}

function time(value: string | null): string {
  if (!value) return 'Open';
  return new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function localDateTime(value: string): string {
  const date = new Date(value);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

type Editor = { kind: 'absence'; row: AttendanceRosterRow } | { kind: 'correction'; row: AttendanceRosterRow; interval: AttendanceIntervalRecord } | { kind: 'status'; row: AttendanceRosterRow };

function AttendanceEditor({ editor, facilityId, organizationId, date, onClose, onSaved }: { editor: Editor; facilityId: string; organizationId: string; date: string; onClose: () => void; onSaved: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const savingRef = useRef(false);
  const [reason, setReason] = useState('');
  const [checkedIn, setCheckedIn] = useState(editor.kind === 'correction' ? localDateTime(editor.interval.checked_in_at) : '');
  const [checkedOut, setCheckedOut] = useState(editor.kind === 'correction' && editor.interval.checked_out_at ? localDateTime(editor.interval.checked_out_at) : '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !savingRef.current) onClose();
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', keyboard);
    requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>('textarea, input')?.focus());
    return () => { window.removeEventListener('keydown', keyboard); document.body.style.overflow = previousOverflow; previous?.focus(); };
  }, [onClose]);

  const save = async (event: FormEvent) => {
    event.preventDefault(); setError('');
    if (editor.kind === 'absence' && reason.trim().length < 2) { setError('Enter a short no-show reason.'); return; }
    if (editor.kind === 'status' && reason.trim().length < 5) { setError('Explain the status correction in at least five characters.'); return; }
    if (editor.kind === 'correction') {
      const errors = validateCorrection(checkedIn, checkedOut, reason);
      if (errors.length) { setError(errors.join(' ')); return; }
    }
    savingRef.current = true; setSaving(true);
    try {
      if (editor.kind === 'absence') await markAbsent(editor.row.child_id, facilityId, date, reason.trim(), organizationId);
      else if (editor.kind === 'status' && editor.row.attendance_day) await correctAttendanceStatus(editor.row.attendance_day.id, 'present', reason.trim(), organizationId);
      else if (editor.kind === 'correction' && editor.row.attendance_day) await correctInterval(editor.row.attendance_day.id, {
        interval_id: editor.interval.id,
        checked_in_at: new Date(checkedIn).toISOString(),
        checked_out_at: new Date(checkedOut).toISOString(),
        reason: reason.trim(),
      }, organizationId);
      onSaved();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Attendance could not be changed.'); }
    finally { savingRef.current = false; setSaving(false); }
  };

  const title = editor.kind === 'absence' ? 'Mark no-show' : editor.kind === 'status' ? 'Correct no-show status' : 'Correct interval';
  return <Overlay onMouseDown={(event) => event.target === event.currentTarget && !saving && onClose()}><Dialog ref={dialogRef} $accent={editor.kind === 'absence' ? 'amber' : 'cyan'} role="dialog" aria-modal="true" aria-labelledby="attendance-editor-title" aria-describedby="attendance-editor-description"><DialogHeader><div><Eyebrow>{editor.kind === 'absence' ? <NoSymbolIcon width={14} /> : <PencilSquareIcon width={14} />} Attendance record</Eyebrow><h2 id="attendance-editor-title">{title}.</h2><p id="attendance-editor-description">{editor.row.child_name} · Every correction keeps an immutable reason in the event history.</p></div><IconButton type="button" disabled={saving} onClick={onClose} aria-label="Close attendance editor"><XMarkIcon /></IconButton></DialogHeader><Form onSubmit={save}>
    {editor.kind === 'correction' && <DialogFields><Field><span>Corrected check-in</span><input required type="datetime-local" value={checkedIn} onChange={(event) => setCheckedIn(event.target.value)} /></Field><Field><span>Corrected check-out</span><input required type="datetime-local" value={checkedOut} onChange={(event) => setCheckedOut(event.target.value)} /></Field></DialogFields>}
    <Field><span>{editor.kind === 'absence' ? 'No-show reason' : 'Reason for correction'}</span><textarea required value={reason} onChange={(event) => setReason(event.target.value)} placeholder={editor.kind === 'absence' ? 'Sick, vacation, family day…' : editor.kind === 'status' ? 'Explain why this no-show record should be changed back to present.' : 'Explain why the recorded interval needs correction.'} /></Field>
    {error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}
    <DialogActions><ActionButton type="button" onClick={onClose} disabled={saving}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={saving}>{saving ? 'Saving…' : editor.kind === 'absence' ? 'Mark no-show' : editor.kind === 'status' ? 'Restore present status' : 'Save correction'}</ActionButton></DialogActions>
  </Form></Dialog></Overlay>;
}

export default function AttendancePage() {
  const session = useSession();
  const organizationReady = session.status === 'authenticated' && Boolean(session.user?.organization_id) && session.user?.organization_id === session.organization?.id && !session.organizationUnavailable;
  const organizationId = organizationReady ? session.organization!.id : '';
  const canRecordAttendance = hasPermission(session.user, ACCESS.attendanceRecord);
  const canCorrectAttendance = hasPermission(session.user, ACCESS.attendanceCorrect);
  const canOpenChildProfile = hasPermission(session.user, ACCESS.childcareRead);
  const canManageSettings = hasPermission(session.user, ACCESS.settingsManage);
  const [facilities, setFacilities] = useState<AttendanceFacility[]>([]);
  const [facilityId, setFacilityId] = useState('');
  const [date, setDate] = useState(dateInputValue());
  const [rows, setRows] = useState<AttendanceRosterRow[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [error, setError] = useState('');
  const [releaseGuardStatus, setReleaseGuardStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [releaseActivation, setReleaseActivation] = useState<AttendanceReleaseCheckoutActivationStatus | null>(null);
  const [releaseGuardError, setReleaseGuardError] = useState('');
  const [search, setSearch] = useState('');
  const [room, setRoom] = useState('');
  const [state, setState] = useState<AttendanceState | ''>('');
  const [pendingOperation, setPendingOperation] = useState<PendingAttendanceOperation | null>(null);
  useEffect(() => { setPendingOperation(organizationId && date ? readPendingAttendanceOperation(organizationId, date) : null); }, [date, organizationId]);
  useEffect(() => { if (!organizationId || !date) return; const key = attendanceOperationKey(organizationId, date); if (pendingOperation?.organizationId === organizationId && pendingOperation.serviceDate === date) sessionStorage.setItem(key, JSON.stringify(pendingOperation)); else sessionStorage.removeItem(key); }, [date, organizationId, pendingOperation]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!organizationReady || !organizationId) {
      setFacilities([]); setFacilityId(''); setRows([]); setStatus('idle');
      setReleaseActivation(null); setReleaseGuardStatus('idle'); setReleaseGuardError('');
      return;
    }
    const controller = new AbortController();
    setStatus('loading'); setError('');
    fetchAttendanceFacilities(organizationId, controller.signal).then((items) => {
      if (controller.signal.aborted) return;
      const active = items.filter((item) => item.status === 'active');
      setFacilities(active);
      setFacilityId((current) => current && active.some((item) => item.id === current) ? current : active[0]?.id || '');
      if (!active.length) { setRows([]); setStatus('ready'); setReleaseActivation(null); setReleaseGuardStatus('idle'); setReleaseGuardError(''); }
    }).catch((caught) => { if (!controller.signal.aborted) { setError(caught instanceof Error ? caught.message : 'Facilities could not be loaded.'); setStatus('error'); } });
    return () => controller.abort();
  }, [organizationId, organizationReady]);

  const load = useCallback((signal?: AbortSignal) => {
    if (!facilityId) {
      setReleaseActivation(null); setReleaseGuardStatus('idle'); setReleaseGuardError('');
      return Promise.resolve();
    }
    setStatus('loading'); setError('');
    setReleaseActivation(null); setReleaseGuardStatus('loading'); setReleaseGuardError('');
    void fetchAttendanceReleaseCheckoutActivation(facilityId, organizationId, signal)
      .then((activation) => {
        setReleaseActivation(activation); setReleaseGuardStatus('ready'); setReleaseGuardError('');
      })
      .catch((caught) => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return;
        setReleaseActivation(null); setReleaseGuardStatus('error');
        setReleaseGuardError(caught instanceof Error ? caught.message : 'Verified-release status could not be loaded.');
      });
    return fetchAttendanceRoster(date, facilityId, organizationId, signal).then((items) => { setRows(items); if (pendingOperation?.organizationId === organizationId && pendingOperation.serviceDate === date && pendingOperation.facilityId === facilityId && attendanceOperationResolved(pendingOperation, items)) setPendingOperation(null); setStatus('ready'); }).catch((caught) => {
      if (!(caught instanceof DOMException && caught.name === 'AbortError')) { setError(caught instanceof Error ? caught.message : 'Attendance could not be loaded.'); setStatus('error'); }
      throw caught;
    });
  }, [date, facilityId, organizationId, pendingOperation]);

  const refreshAttendanceWorkspace = useCallback(async () => {
    if (!organizationId) return;
    const active = (await fetchAttendanceFacilities(organizationId)).filter((item) => item.status === 'active');
    const nextFacilityId = facilityId && active.some((item) => item.id === facilityId) ? facilityId : active[0]?.id || '';
    let items: AttendanceRosterRow[] = [];
    let activationResult: { value: AttendanceReleaseCheckoutActivationStatus | null; error: string } = { value: null, error: '' };
    if (nextFacilityId) {
      [items, activationResult] = await Promise.all([
        fetchAttendanceRoster(date, nextFacilityId, organizationId),
        fetchAttendanceReleaseCheckoutActivation(nextFacilityId, organizationId)
          .then((value) => ({ value, error: '' }))
          .catch((caught) => ({ value: null, error: caught instanceof Error ? caught.message : 'Verified-release status could not be loaded.' })),
      ]);
    }
    setFacilities(active); setFacilityId(nextFacilityId); setRows(items); setStatus('ready'); setError('');
    setReleaseActivation(activationResult.value);
    setReleaseGuardStatus(nextFacilityId ? activationResult.value ? 'ready' : 'error' : 'idle');
    setReleaseGuardError(activationResult.error);
    if (pendingOperation?.organizationId === organizationId && pendingOperation.serviceDate === date && pendingOperation.facilityId === nextFacilityId && attendanceOperationResolved(pendingOperation, items)) setPendingOperation(null);
  }, [date, facilityId, organizationId, pendingOperation]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal).catch(() => undefined); return () => controller.abort(); }, [load, version]);
  useRealtimeRefresh({ scope: 'attendance', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.attendance.realtimeEntities, refresh: refreshAttendanceWorkspace });

  const counts = useMemo(() => attendanceCounts(rows), [rows]);
  const roomNames = useMemo(() => [...new Set(rows.map((item) => item.room_name).filter((value): value is string => Boolean(value)))].sort(), [rows]);
  const filtered = useMemo(() => rows.filter((item) => {
    if (search && !item.child_name.toLowerCase().includes(search.toLowerCase())) return false;
    if (room && item.room_name !== room) return false;
    if (state && attendanceState(item) !== state) return false;
    return true;
  }), [rows, room, search, state]);
  const isToday = date === dateInputValue();
  const selectedFacility = facilities.find((item) => item.id === facilityId);
  const legacyCheckoutAllowed = releaseGuardStatus === 'ready'
    && releaseActivation?.legacy_checkout_allowed === true
    && releaseActivation.activated === false;

  const act = async (row: AttendanceRosterRow, action: 'in' | 'out') => {
    setBusy(row.child_id); setError('');
    if (action === 'out') {
      if (!legacyCheckoutAllowed) {
        setError(releaseActivation?.activated
          ? 'This facility requires verified-recipient release. Complete the departure in the CareSync staff app.'
          : 'Legacy checkout is locked until CareSync can verify this facility’s release mode.');
        setBusy(null);
        return;
      }
      try {
        const latestActivation = await fetchAttendanceReleaseCheckoutActivation(facilityId, organizationId);
        setReleaseActivation(latestActivation); setReleaseGuardStatus('ready'); setReleaseGuardError('');
        if (latestActivation.activated || !latestActivation.legacy_checkout_allowed) {
          setError(latestActivation.activated
            ? 'This facility requires verified-recipient release. Complete the departure in the CareSync staff app.'
            : 'Legacy checkout is unavailable under this facility’s release policy.');
          setBusy(null);
          return;
        }
      } catch (caught) {
        setReleaseActivation(null); setReleaseGuardStatus('error');
        setReleaseGuardError(caught instanceof Error ? caught.message : 'Verified-release status could not be loaded.');
        setError('Legacy checkout stayed locked because CareSync could not verify this facility’s release mode.');
        setBusy(null);
        return;
      }
    }
    if (pendingOperation && (pendingOperation.facilityId !== facilityId || pendingOperation.childId !== row.child_id || pendingOperation.kind !== action)) { setError('A previous attendance change is still unresolved. Retry or reconcile that exact child action before starting another.'); setBusy(null); return; }
    const operation: PendingAttendanceOperation = pendingOperation || { organizationId, serviceDate: date, facilityId, childId: row.child_id, kind: action, occurredAt: new Date().toISOString(), clientOperationId: crypto.randomUUID() };
    setPendingOperation(operation);
    try {
      const day = action === 'in' ? await checkIn(row.child_id, facilityId, organizationId, operation.clientOperationId, operation.occurredAt) : await checkOut(row.child_id, facilityId, organizationId, operation.clientOperationId, operation.occurredAt);
      setPendingOperation(null);
      setRows((current) => current.map((item) => item.child_id === row.child_id ? { ...item, attendance_day: day } : item));
    } catch (caught) {
      if (caught instanceof AttendanceApiError && caught.status >= 400 && caught.status < 500 && ![408, 429].includes(caught.status)) setPendingOperation(null);
      setError(caught instanceof Error ? caught.message : 'Attendance could not be changed.');
    }
    finally { setBusy(null); }
  };

  const saved = () => { setEditor(null); setVersion((value) => value + 1); };

  return <Page><Header><div><Eyebrow><ClockIcon width={14} /> Actual attendance</Eyebrow><h1>Daily presence.</h1><p>Record arrivals, departures, true no-shows, split sessions, and reasoned corrections as operational facts.</p></div><DateBadge $accent="cyan"><span>Selected service date</span><strong>{new Date(`${date}T12:00:00`).toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</strong></DateBadge></Header>
    <Controls $accent="plasma"><input aria-label="Attendance date" type="date" value={date} onChange={(event) => setDate(event.target.value)} /><select aria-label="Facility" value={facilityId} onChange={(event) => setFacilityId(event.target.value)}>{facilities.map((item) => <option key={item.id} value={item.id}>{item.name}{item.city ? ` · ${item.city}` : ''}</option>)}</select><Search><MagnifyingGlassIcon /><input aria-label="Search children" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search children…" /></Search><select aria-label="Filter room" value={room} onChange={(event) => setRoom(event.target.value)}><option value="">All rooms</option>{roomNames.map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter attendance status" value={state} onChange={(event) => setState(event.target.value as AttendanceState | '')}><option value="">All states</option><option value="pending">Not recorded</option><option value="on-site">On site</option><option value="completed">Checked out</option><option value="absent">No-show</option></select></Controls>
    <Metrics><Metric $accent="plasma"><span><UserGroupIcon /> Enrolled</span><strong>{counts.enrolled}</strong></Metric><Metric $accent="amber"><span><ClockIcon /> Not recorded</span><strong>{counts.pending}</strong></Metric><Metric $tone="mint" $accent="cyan"><span><ArrowRightStartOnRectangleIcon /> On site</span><strong>{counts.onSite}</strong></Metric><Metric $accent="cyan"><span><CheckCircleIcon /> Checked out</span><strong>{counts.completed}</strong></Metric><Metric $tone="amber" $accent="amber"><span><NoSymbolIcon /> No-show</span><strong>{counts.absent}</strong></Metric></Metrics>
    {!isToday && <Notice><CalendarDaysIcon /><span>You are reviewing a historical or future service date. Live check-in and check-out are disabled; {canCorrectAttendance ? 'past intervals can be corrected with a reason.' : 'historical records are read only for your role.'}</span></Notice>}
    {releaseGuardStatus === 'loading' && <Notice><ArrowPathIcon /><span>CareSync is verifying this facility’s release mode. Legacy checkout remains locked during this check; check-in, no-show, details, and permitted corrections remain available.</span></Notice>}
    {releaseGuardStatus === 'error' && <Notice $error role="alert"><ExclamationTriangleIcon /><span>Legacy checkout is safely locked because the facility’s verified-release status is unavailable. Check-in, no-show, details, and permitted corrections remain available. {releaseGuardError}</span></Notice>}
    {releaseGuardStatus === 'ready' && releaseActivation?.activated && <Notice><ArrowRightEndOnRectangleIcon /><span><strong>Verified-recipient departures are required at {releaseActivation.facility_name}.</strong> Legacy checkout is permanently closed for this facility. Complete every departure in the CareSync staff app.{canManageSettings && <> <NoticeLink to="/settings?section=facility">View facility activation status.</NoticeLink></>}</span></Notice>}
    {releaseGuardStatus === 'ready' && releaseActivation && !releaseActivation.activated && !releaseActivation.legacy_checkout_allowed && <Notice $error role="alert"><ExclamationTriangleIcon /><span>Legacy checkout is unavailable under this facility’s release policy. Do not record a departure here; use the CareSync staff app or ask an owner or administrator to review the facility status.{canManageSettings && <> <NoticeLink to="/settings?section=facility">View facility status.</NoticeLink></>}</span></Notice>}
    {pendingOperation && <Notice><ArrowPathIcon /><span>An attendance change is awaiting authoritative confirmation. Other check-in/out actions are locked; retry the same child action safely.</span></Notice>}
    {error && status !== 'error' && <Notice $error role="alert"><ExclamationTriangleIcon /><span>{error}</span></Notice>}
    {status === 'idle' && <Gate $accent="amber"><div><ExclamationTriangleIcon /><h2>Attendance is safely locked.</h2><p>CareSync must verify the signed-in organization before loading or changing attendance.</p></div></Gate>}
    {status === 'loading' && <Gate $accent="cyan" aria-busy="true"><div><ArrowPathIcon /><h2>Loading the attendance roster.</h2><p>CareSync is resolving active enrollment and existing daily records for {selectedFacility?.name || 'this facility'}.</p></div></Gate>}
    {status === 'error' && <Gate $accent="amber"><div><ExclamationTriangleIcon /><h2>Attendance stayed unchanged.</h2><p>{error}</p><ActionButton onClick={() => setVersion((value) => value + 1)}><ArrowPathIcon /> Try again</ActionButton></div></Gate>}
    {status === 'ready' && <Roster $accent="cyan"><RosterHeader><div><h2>{selectedFacility?.name || 'Attendance roster'}</h2><p>{filtered.length} of {rows.length} enrolled children shown</p></div><StatusChip $tone={counts.pending ? 'warning' : 'success'}>{counts.pending ? `${counts.pending} need review` : 'Day recorded'}</StatusChip></RosterHeader>{filtered.length ? filtered.map((row) => { const dayState = attendanceState(row); const presentation = attendancePresentation(dayState); const open = row.attendance_day?.intervals.find((item) => !item.checked_out_at); const last = row.attendance_day?.intervals.at(-1); const isBusy = busy === row.child_id; const name = childNameParts(row.child_name); const identity = <><ChildAvatar firstName={name.firstName} lastName={name.lastName} photoUrl={row.profile_photo_url} size={38} /><div><strong>{row.child_name}</strong><small>{row.program_name || 'Active enrollment'}</small></div></>; return <Row key={row.child_id}><Child>{canOpenChildProfile ? <ChildProfileLink to={`/children/${encodeURIComponent(row.child_id)}`} aria-label={`Open ${row.child_name} profile`}>{identity}</ChildProfileLink> : <ChildIdentity>{identity}</ChildIdentity>}</Child><Cell><strong>{row.room_name || 'Unassigned'}</strong><small>Care room</small></Cell><Cell><StatusChip $tone={dayState === 'on-site' ? 'success' : dayState === 'absent' ? 'warning' : dayState === 'pending' || dayState === 'present' ? 'neutral' : 'info'}>{presentation.label}</StatusChip></Cell><Actions>
      {canRecordAttendance && (presentation.primaryAction === 'check-in' || presentation.primaryAction === 'check-in-again') && <RowAction $primary disabled={!isToday || isBusy || Boolean(pendingOperation && (pendingOperation.childId !== row.child_id || pendingOperation.kind !== 'in' || pendingOperation.facilityId !== facilityId))} onClick={() => void act(row, 'in')}><ArrowRightStartOnRectangleIcon /> {pendingOperation?.childId === row.child_id && pendingOperation.kind === 'in' ? 'Retry check in' : presentation.primaryLabel}</RowAction>}
      {canRecordAttendance && presentation.primaryAction === 'check-out' && legacyCheckoutAllowed && <RowAction $primary disabled={!isToday || isBusy || Boolean(pendingOperation && (pendingOperation.childId !== row.child_id || pendingOperation.kind !== 'out' || pendingOperation.facilityId !== facilityId))} onClick={() => void act(row, 'out')}><ArrowRightEndOnRectangleIcon /> {pendingOperation?.childId === row.child_id && pendingOperation.kind === 'out' ? 'Retry check out' : presentation.primaryLabel}</RowAction>}
      {canRecordAttendance && presentation.primaryAction === 'check-out' && releaseGuardStatus === 'ready' && releaseActivation?.activated && <CheckoutHandoff><ArrowRightEndOnRectangleIcon /> Release in staff app</CheckoutHandoff>}
      {canRecordAttendance && presentation.secondaryAction === 'mark-no-show' && <RowAction $secondary disabled={isBusy || date > dateInputValue()} onClick={() => setEditor({ kind: 'absence', row })}><NoSymbolIcon /> {presentation.secondaryLabel}</RowAction>}
      {canCorrectAttendance && dayState === 'absent' && row.attendance_day && <RowAction disabled={isBusy} onClick={() => setEditor({ kind: 'status', row })}><PencilSquareIcon /> Correct status</RowAction>}
      {row.attendance_day && <RowAction onClick={() => setExpanded((value) => value === row.child_id ? null : row.child_id)}>{expanded === row.child_id ? <ChevronUpIcon /> : <ChevronDownIcon />} Details</RowAction>}
    </Actions><div>{isBusy && <ArrowPathIcon width={18} />}</div>
      {expanded === row.child_id && row.attendance_day && <Detail><div><Eyebrow><ClockIcon width={13} /> Attendance intervals</Eyebrow><IntervalList>{row.attendance_day.intervals.length ? row.attendance_day.intervals.map((interval) => <Interval key={interval.id}><span>{interval.sequence}</span><div><strong>{time(interval.checked_in_at)} → {time(interval.checked_out_at)}</strong><small>{interval.checked_out_at ? 'Completed interval' : 'Currently open'}</small></div>{canCorrectAttendance && interval.checked_out_at && <TinyCorrection type="button" onClick={() => setEditor({ kind: 'correction', row, interval })} aria-label={`Correct interval ${interval.sequence}`}><PencilSquareIcon /></TinyCorrection>}</Interval>) : <Notice><ClockIcon /> No arrival interval has been recorded.</Notice>}</IntervalList></div><EventList><h3>Immutable event history</h3>{row.attendance_day.events.slice().reverse().slice(0, 8).map((event) => <p key={event.id}><strong>{event.event_type.replaceAll('_', ' ')}</strong> · {new Date(event.occurred_at).toLocaleString()}{event.reason ? ` — ${event.reason}` : ''}</p>)}{row.attendance_day.events.length === 0 && <p>No events returned.</p>}{last && <p><strong>Last interval:</strong> {time(last.checked_in_at)}–{time(last.checked_out_at)}</p>}{open && <p><strong>Open since:</strong> {time(open.checked_in_at)}</p>}</EventList></Detail>}
    </Row>; }) : <Empty><div><ArrowDownTrayIcon /><h2>No roster rows match.</h2><p>{rows.length ? 'Clear one or more filters to see enrolled children.' : 'No active child enrollments were found for this facility and service date. Add enrollment from the Children area first.'}</p></div></Empty>}</Roster>}
    {editor && organizationId && <AttendanceEditor editor={editor} facilityId={facilityId} organizationId={organizationId} date={date} onClose={() => setEditor(null)} onSaved={saved} />}
  </Page>;
}

const TinyCorrection = styled(IconButton)`width: 44px; height: 44px; border-radius: 9px 12px 9px 9px; svg { width: 15px; }`;

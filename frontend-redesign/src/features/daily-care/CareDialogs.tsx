import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  HeartIcon,
  IdentificationIcon,
  PhoneIcon,
  ShieldCheckIcon,
  UserIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import ChildAvatar from '../children/ChildAvatar';
import {
  fetchCareRecordHistory,
  fetchChildSafetyCard,
  createCareOperationId,
  type ActivityKind,
  type CarePayload,
  type CareRecord,
  type CareRecordEvent,
  type CareType,
  type ChildSafetyCard,
  type DiaperOutcome,
  type FeedingIntake,
  type FeedingKind,
  type MoodValue,
  type ToiletOutcome,
} from './careApi';
import {
  childNameParts,
  facilityDateTimeInputValue,
  formatCareTime,
  resolveFacilityDateTime,
} from './careModel';

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 950;
  display: grid;
  place-items: center;
  padding: 18px;
  overflow-y: auto;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
  @media (max-width: 720px) { padding: 0; align-items: stretch; }
`;

const Dialog = styled(GlassPanel)`
  width: min(680px, 100%);
  max-height: calc(100vh - 36px);
  padding: 22px;
  overflow-y: auto;
  @media (max-width: 720px) {
    width: 100%; max-height: none; min-height: 100dvh; padding: 18px 15px 28px; border: 0; border-radius: 0;
  }
`;

const DialogHeader = styled.header`
  display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 19px;
  h2 { margin: 8px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.35rem, 3vw, 1.75rem); font-weight: 540; letter-spacing: -.04em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .76rem; line-height: 1.6; }
`;

const Form = styled.form`display: grid; gap: 14px;`;
const Grid = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; @media (max-width: 560px) { grid-template-columns: 1fr; }`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid; grid-column: ${({ $wide }) => $wide ? '1 / -1' : 'auto'}; gap: 6px;
  > span { color: ${({ theme }) => theme.color.textSoft}; font-size: .73rem; font-weight: 600; }
  input, select, textarea { width: 100%; min-height: 46px; padding: 0 12px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .8rem; }
  textarea { min-height: 94px; padding-top: 11px; resize: vertical; }
  input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 16%, transparent); }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.5; }
`;
const Actions = styled.div`display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; padding-top: 3px; @media (max-width: 520px) { display: grid; grid-template-columns: 1fr 1fr; } @media (max-width: 390px) { grid-template-columns: 1fr; }`;
const Notice = styled.div<{ $error?: boolean }>`
  display: flex; align-items: flex-start; gap: 8px; padding: 11px 13px; border: 1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.cyan}; border-radius: 12px 5px 12px 5px; color: ${({ $error, theme }) => $error ? theme.color.coral : theme.color.textSoft}; background: ${({ theme }) => theme.color.surfaceStrong}; font-size: .74rem; line-height: 1.55;
  svg { width: 18px; flex: 0 0 auto; }
`;

function Modal({ children, busy = false, onClose, labelId }: { children: ReactNode; busy?: boolean; onClose: () => void; labelId: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
      if (event.key !== 'Tab' || !ref.current) return;
      const focusable = [...ref.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', keydown);
    requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input, select, textarea, button')?.focus());
    return () => {
      window.removeEventListener('keydown', keydown);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [busy, onClose]);
  return <Overlay onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}><Dialog ref={ref} $accent="cyan" role="dialog" aria-modal="true" aria-labelledby={labelId} aria-busy={busy}>{children}</Dialog></Overlay>;
}

interface PayloadState {
  feedingKind: FeedingKind;
  feedingIntake: FeedingIntake;
  volume: string;
  diaperOutcome: DiaperOutcome;
  toiletOutcome: ToiletOutcome;
  mood: MoodValue;
  activity: ActivityKind;
}

function payloadState(record?: CareRecord): PayloadState {
  const payload = record?.payload as Record<string, unknown> | undefined;
  return {
    feedingKind: record?.care_type === 'feeding' ? payload?.kind as FeedingKind : 'meal',
    feedingIntake: record?.care_type === 'feeding' ? payload?.intake as FeedingIntake : 'most',
    volume: record?.care_type === 'feeding' && typeof payload?.volume_ml === 'number' ? String(payload.volume_ml) : '',
    diaperOutcome: record?.care_type === 'diaper' ? payload?.outcome as DiaperOutcome : 'wet',
    toiletOutcome: record?.care_type === 'toilet' ? payload?.outcome as ToiletOutcome : 'success',
    mood: record?.care_type === 'mood' ? payload?.value as MoodValue : 'happy',
    activity: record?.care_type === 'activity' ? payload?.kind as ActivityKind : 'learning',
  };
}

function payloadFor(type: CareType, state: PayloadState): CarePayload {
  if (type === 'feeding') return { kind: state.feedingKind, intake: state.feedingIntake, ...(state.feedingKind === 'bottle' && state.volume !== '' ? { volume_ml: Number(state.volume) } : {}) };
  if (type === 'diaper') return { outcome: state.diaperOutcome };
  if (type === 'toilet') return { outcome: state.toiletOutcome };
  if (type === 'mood') return { value: state.mood };
  if (type === 'activity') return { kind: state.activity };
  return {};
}

function PayloadFields({ type, value, onChange }: { type: CareType; value: PayloadState; onChange: (value: PayloadState) => void }) {
  if (type === 'feeding') return <>
    <Field><span>Feeding type</span><select value={value.feedingKind} onChange={(event) => onChange({ ...value, feedingKind: event.target.value as FeedingKind })}><option value="meal">Meal</option><option value="snack">Snack</option><option value="bottle">Bottle</option></select></Field>
    <Field><span>Amount consumed</span><select value={value.feedingIntake} onChange={(event) => onChange({ ...value, feedingIntake: event.target.value as FeedingIntake })}><option value="none">None</option><option value="some">Some</option><option value="most">Most</option><option value="all">All</option></select></Field>
    {value.feedingKind === 'bottle' && <Field $wide><span>Bottle volume (mL)</span><input type="number" min="0" max="2000" step="1" value={value.volume} onChange={(event) => onChange({ ...value, volume: event.target.value })} placeholder="Optional" /></Field>}
  </>;
  if (type === 'diaper') return <Field $wide><span>Diaper outcome</span><select value={value.diaperOutcome} onChange={(event) => onChange({ ...value, diaperOutcome: event.target.value as DiaperOutcome })}><option value="dry">Dry</option><option value="wet">Wet</option><option value="soiled">Soiled</option><option value="both">Wet and soiled</option></select></Field>;
  if (type === 'toilet') return <Field $wide><span>Toilet outcome</span><select value={value.toiletOutcome} onChange={(event) => onChange({ ...value, toiletOutcome: event.target.value as ToiletOutcome })}><option value="attempt">Attempt</option><option value="success">Success</option><option value="accident">Accident</option></select></Field>;
  if (type === 'mood') return <Field $wide><span>Mood</span><select value={value.mood} onChange={(event) => onChange({ ...value, mood: event.target.value as MoodValue })}><option value="calm">Calm</option><option value="happy">Happy</option><option value="sad">Sad</option><option value="upset">Upset</option><option value="tired">Tired</option><option value="energetic">Energetic</option></select></Field>;
  if (type === 'activity') return <Field $wide><span>Activity type</span><select value={value.activity} onChange={(event) => onChange({ ...value, activity: event.target.value as ActivityKind })}><option value="indoor">Indoor</option><option value="outdoor">Outdoor</option><option value="learning">Learning</option><option value="creative">Creative</option><option value="physical">Physical</option></select></Field>;
  return <Notice><ClockIcon /> Sleep starts at the facility time below. Finish it from the child timeline when the child wakes.</Notice>;
}

const typeLabel: Record<CareType, string> = { feeding: 'feeding', diaper: 'diaper change', toilet: 'toilet visit', sleep: 'sleep', mood: 'mood', activity: 'activity' };

export interface CareEntryDraft { occurredAt: string; payload: CarePayload; note: string | null; clientOperationId: string }

export function CareEntryDialog({ childName, type, timeZone, initialOccurredAt, busy, onClose, onSave }: { childName: string; type: CareType; timeZone: string; initialOccurredAt: string; busy: boolean; onClose: () => void; onSave: (draft: CareEntryDraft) => Promise<void> }) {
  const [occurredInput, setOccurredInput] = useState(() => facilityDateTimeInputValue(initialOccurredAt, timeZone));
  const [clientOperationId] = useState(createCareOperationId);
  const [payload, setPayload] = useState(() => payloadState());
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('');
    try {
      const occurredAt = resolveFacilityDateTime(occurredInput, initialOccurredAt, timeZone);
      if (payload.feedingKind === 'bottle' && payload.volume !== '' && (!Number.isInteger(Number(payload.volume)) || Number(payload.volume) < 0 || Number(payload.volume) > 2000)) throw new Error('Bottle volume must be a whole number from 0 to 2000 mL.');
      await onSave({ occurredAt, payload: payloadFor(type, payload), note: note.trim() || null, clientOperationId });
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The care record could not be saved.'); }
  };
  return <Modal busy={busy} onClose={onClose} labelId="care-entry-title"><DialogHeader><div><Eyebrow><CheckCircleIcon width={14} /> Daily care entry</Eyebrow><h2 id="care-entry-title">Record {typeLabel[type]}.</h2><p>{childName} · Saved against the verified attendance day.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close care entry"><XMarkIcon /></IconButton></DialogHeader><Form onSubmit={submit}><Grid><PayloadFields type={type} value={payload} onChange={setPayload} /><Field $wide><span>Facility date and time</span><input required type="datetime-local" value={occurredInput} onChange={(event) => setOccurredInput(event.target.value)} /><small>{timeZone} · daylight-saving gaps or ambiguous corrected times are rejected.</small></Field><Field $wide><span>Optional note</span><textarea maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add only useful care context." /><small>{note.length}/500</small></Field></Grid>{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Actions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? <><ArrowPathIcon /> Saving…</> : 'Save care record'}</ActionButton></Actions></Form></Modal>;
}

export interface CareCorrectionDraft { occurredAt: string; endedAt: string | null; payload: CarePayload; note: string | null; reason: string; clientOperationId: string }

export function SleepFinishDialog({ record, childName, timeZone, initialEndedAt, busy, onClose, onSave }: { record: CareRecord; childName: string; timeZone: string; initialEndedAt: string; busy: boolean; onClose: () => void; onSave: (endedAt: string, clientOperationId: string) => Promise<void> }) {
  const [endedInput, setEndedInput] = useState(() => facilityDateTimeInputValue(initialEndedAt, timeZone));
  const [clientOperationId] = useState(createCareOperationId);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('');
    try {
      const endedAt = resolveFacilityDateTime(endedInput, initialEndedAt, timeZone);
      if (Date.parse(endedAt) < Date.parse(record.occurred_at)) throw new Error('The wake time cannot be earlier than the sleep start.');
      await onSave(endedAt, clientOperationId);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The sleep record could not be finished.'); }
  };
  return <Modal busy={busy} onClose={onClose} labelId="sleep-finish-title"><DialogHeader><div><Eyebrow><ClockIcon width={14} /> Finish sleep</Eyebrow><h2 id="sleep-finish-title">Record wake time.</h2><p>{childName} · This closes the open sleep interval without changing its start.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close sleep finish form"><XMarkIcon /></IconButton></DialogHeader><Form onSubmit={submit}><Field><span>Facility wake date and time</span><input required type="datetime-local" value={endedInput} onChange={(event) => setEndedInput(event.target.value)} /><small>{timeZone} · use the observed wake time.</small></Field>{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Actions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? <><ArrowPathIcon /> Saving…</> : 'Finish sleep'}</ActionButton></Actions></Form></Modal>;
}

export function CareCorrectionDialog({ record, childName, timeZone, busy, onClose, onSave }: { record: CareRecord; childName: string; timeZone: string; busy: boolean; onClose: () => void; onSave: (draft: CareCorrectionDraft) => Promise<void> }) {
  const [occurredInput, setOccurredInput] = useState(() => facilityDateTimeInputValue(record.occurred_at, timeZone));
  const [clientOperationId] = useState(createCareOperationId);
  const [endedInput, setEndedInput] = useState(() => record.ended_at ? facilityDateTimeInputValue(record.ended_at, timeZone) : '');
  const [payload, setPayload] = useState(() => payloadState(record));
  const [note, setNote] = useState(record.note || '');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('');
    try {
      const occurredAt = resolveFacilityDateTime(occurredInput, record.occurred_at, timeZone);
      const endedAt = endedInput ? resolveFacilityDateTime(endedInput, record.ended_at || occurredAt, timeZone) : null;
      if (endedAt && Date.parse(endedAt) < Date.parse(occurredAt)) throw new Error('The end time cannot be earlier than the start time.');
      if (reason.trim().length < 3) throw new Error('Explain the correction in at least three characters.');
      await onSave({ occurredAt, endedAt, payload: payloadFor(record.care_type, payload), note: note.trim() || null, reason: reason.trim(), clientOperationId });
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The correction could not be saved.'); }
  };
  return <Modal busy={busy} onClose={onClose} labelId="care-correction-title"><DialogHeader><div><Eyebrow><IdentificationIcon width={14} /> Audited correction</Eyebrow><h2 id="care-correction-title">Correct {typeLabel[record.care_type]}.</h2><p>{childName} · The original record remains in immutable history.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close care correction"><XMarkIcon /></IconButton></DialogHeader><Form onSubmit={submit}><Grid><PayloadFields type={record.care_type} value={payload} onChange={setPayload} /><Field><span>Facility start time</span><input required type="datetime-local" value={occurredInput} onChange={(event) => setOccurredInput(event.target.value)} /></Field>{record.care_type === 'sleep' && <Field><span>Facility end time</span><input type="datetime-local" value={endedInput} onChange={(event) => setEndedInput(event.target.value)} /></Field>}<Field $wide><span>Note</span><textarea maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} /></Field><Field $wide><span>Required correction reason</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /><small>{timeZone} · the reason is stored in the audit event.</small></Field></Grid>{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Actions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? <><ArrowPathIcon /> Saving…</> : 'Save audited correction'}</ActionButton></Actions></Form></Modal>;
}

export function CareVoidDialog({ record, childName, busy, onClose, onSave }: { record: CareRecord; childName: string; busy: boolean; onClose: () => void; onSave: (reason: string, clientOperationId: string) => Promise<void> }) {
  const [reason, setReason] = useState(''); const [error, setError] = useState(''); const [clientOperationId] = useState(createCareOperationId);
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(''); try { if (reason.trim().length < 3) throw new Error('Explain why this record must be voided.'); await onSave(reason.trim(), clientOperationId); } catch (caught) { setError(caught instanceof Error ? caught.message : 'The record could not be voided.'); } };
  return <Modal busy={busy} onClose={onClose} labelId="care-void-title"><DialogHeader><div><Eyebrow><ExclamationTriangleIcon width={14} /> Administrative void</Eyebrow><h2 id="care-void-title">Void this {typeLabel[record.care_type]} record?</h2><p>{childName} · It disappears from the active timeline but remains in immutable history.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close void form"><XMarkIcon /></IconButton></DialogHeader><Form onSubmit={submit}><Field><span>Required void reason</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}<Actions><ActionButton type="button" disabled={busy} onClick={onClose}>Keep record</ActionButton><ActionButton type="submit" $variant="danger" disabled={busy}>{busy ? 'Voiding…' : 'Void with audit trail'}</ActionButton></Actions></Form></Modal>;
}

const SafetyHero = styled.div`display: grid; grid-template-columns: auto minmax(0,1fr); align-items: center; gap: 14px; padding: 14px; margin-bottom: 13px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 14px 6px 14px 6px; background: ${({ theme }) => theme.color.surfaceStrong}; h3 { margin: 0; font-size: 1rem; } p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; }`;
const SafetyGrid = styled.div`display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; @media (max-width: 560px) { grid-template-columns: 1fr; }`;
const SafetyItem = styled.div`padding: 13px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 13px 5px 13px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; span { display: flex; align-items: center; gap: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; font-weight: 600; text-transform: uppercase; letter-spacing: .07em; } svg { width: 16px; color: ${({ theme }) => theme.color.cyan}; } strong { display: block; margin-top: 8px; font-size: .78rem; font-weight: 550; line-height: 1.55; } small { display: block; margin-top: 6px; color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; line-height: 1.5; }`;
const Contacts = styled.div`display: grid; gap: 8px; margin-top: 13px;`;
const Contact = styled.a`display: grid; grid-template-columns: 36px minmax(0,1fr) auto; align-items: center; gap: 10px; min-height: 56px; padding: 9px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; > svg { width: 18px; margin: auto; color: ${({ theme }) => theme.color.cyan}; } strong { display: block; font-size: .77rem; } small { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; }`;

export function SafetyCardDialog({ childId, facilityId, roomId, onClose }: { childId: string; facilityId: string; roomId: string; onClose: () => void }) {
  const requestKey = `${childId}:${facilityId}:${roomId}`;
  const [result, setResult] = useState<{ key: string; card: ChildSafetyCard | null; error: string }>(() => ({ key: requestKey, card: null, error: '' }));
  const current = result.key === requestKey ? result : { key: requestKey, card: null, error: '' };
  const { card, error } = current;
  useEffect(() => {
    const controller = new AbortController();
    setResult({ key: requestKey, card: null, error: '' });
    fetchChildSafetyCard(childId, facilityId, roomId, controller.signal)
      .then((nextCard) => { if (!controller.signal.aborted) setResult({ key: requestKey, card: nextCard, error: '' }); })
      .catch((caught) => { if (!controller.signal.aborted) setResult({ key: requestKey, card: null, error: caught instanceof Error ? caught.message : 'The safety card could not be loaded.' }); });
    return () => controller.abort();
  }, [childId, facilityId, requestKey, roomId]);
  const name = childNameParts(card?.child_name || 'Child Profile');
  return <Modal onClose={onClose} labelId="safety-card-title"><DialogHeader><div><Eyebrow><ShieldCheckIcon width={14} /> Assigned-care safety card</Eyebrow><h2 id="safety-card-title">Safety information.</h2><p>Current profile information · only the minimized information needed for assigned-room care is shown.</p></div><IconButton type="button" onClick={onClose} aria-label="Close safety card"><XMarkIcon /></IconButton></DialogHeader>{!card && !error && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Loading current safety information…</Notice>}{error && <Notice $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}{card && <><SafetyHero><ChildAvatar firstName={name.firstName} lastName={name.lastName} photoUrl={card.profile_photo_url} size={58} /><div><h3>{card.child_name}</h3><p>{card.age_group || 'Age group not recorded'} · assigned room safety scope</p></div></SafetyHero><SafetyGrid><SafetyItem><span><HeartIcon /> Allergies</span><strong>{card.safety.allergies || 'Not recorded'}</strong></SafetyItem><SafetyItem><span><ShieldCheckIcon /> Medical conditions</span><strong>{card.safety.medical_conditions || 'Not recorded'}</strong></SafetyItem><SafetyItem><span><IdentificationIcon /> Medication awareness</span><strong>{card.safety.medication_awareness || 'Not recorded'}</strong><small>Awareness only — this is not authorization or an administration instruction.</small></SafetyItem><SafetyItem><span><CheckCircleIcon /> Legacy emergency-medical marker</span><strong>{card.safety.emergency_medical_consent ? 'Affirmative profile marker recorded — verify current signed authorization' : 'No affirmative profile marker recorded — this is not a denial'}</strong></SafetyItem></SafetyGrid><Contacts>{card.contacts.length ? card.contacts.map((contact) => <Contact key={contact.id} href={`tel:${contact.phone}`}><UserIcon /><div><strong>{contact.name}</strong><small>{contact.relationship || (contact.contact_type === 'primary_guardian' ? 'Primary guardian' : 'Emergency contact')} · {contact.authorized_pickup ? 'legacy pickup marker: yes' : 'no affirmative pickup marker recorded'} · not verified authority</small></div><PhoneIcon width={17} /></Contact>) : <Notice><PhoneIcon /> No operational emergency contacts were returned.</Notice>}</Contacts></>}</Modal>;
}

const HistoryList = styled.div`display: grid; gap: 8px;`;
const HistoryRow = styled.div`display: grid; grid-template-columns: 10px minmax(0,1fr); gap: 10px; padding: 11px 12px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 12px 5px 12px 5px; background: ${({ theme }) => theme.color.surfaceStrong}; &::before { width: 7px; height: 7px; margin-top: 5px; border-radius: 50%; content: ''; background: ${({ theme }) => theme.color.cyan}; } strong { display: block; font-size: .76rem; text-transform: capitalize; } p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; }`;
const ChangeList = styled.dl`display: grid; gap: 6px; margin: 9px 0 0; dt { color: ${({ theme }) => theme.color.textSoft}; font-size: .68rem; font-weight: 600; } dd { display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); align-items: start; gap: 7px; margin: 2px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; line-height: 1.45; overflow-wrap: anywhere; } dd > span { display: grid; gap: 2px; } em { color: ${({ theme }) => theme.color.cyan}; font-size: .61rem; font-style: normal; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; } b { align-self: end; color: ${({ theme }) => theme.color.cyan}; font-weight: 500; } @media (max-width: 420px) { dd { grid-template-columns: 1fr; gap: 5px; } b { display: none; } }`;

function historyValue(value: unknown, key: string, timeZone: string): string {
  if (value == null || value === '') return 'Not set';
  if ((key === 'occurred_at' || key === 'ended_at' || key === 'voided_at') && typeof value === 'string') return `${formatCareTime(value, timeZone)} ${timeZone}`;
  if (key === 'payload' && typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([name, item]) => `${name.replaceAll('_', ' ')}: ${String(item)}`).join(' · ') || 'No details';
  return String(value);
}

function historyChanges(event: CareRecordEvent, timeZone: string) {
  const labels: Record<string, string> = { occurred_at: 'Start time', ended_at: 'End time', payload: 'Care detail', note: 'Note', void_reason: 'Void reason' };
  const keys = Object.keys(labels).filter((key) => (event.before?.[key] ?? null) !== (event.after?.[key] ?? null)
    && JSON.stringify(event.before?.[key] ?? null) !== JSON.stringify(event.after?.[key] ?? null));
  if (event.before === null && event.after) return keys.map((key) => ({ label: labels[key], before: 'Not set', after: historyValue(event.after?.[key], key, timeZone) }));
  return keys.map((key) => ({ label: labels[key], before: historyValue(event.before?.[key], key, timeZone), after: historyValue(event.after?.[key], key, timeZone) }));
}

export function CareHistoryDialog({ record, timeZone, onClose }: { record: CareRecord; timeZone: string; onClose: () => void }) {
  const requestKey = record.id;
  const [result, setResult] = useState<{ key: string; events: CareRecordEvent[]; error: string; loading: boolean }>(() => ({ key: requestKey, events: [], error: '', loading: true }));
  const current = result.key === requestKey ? result : { key: requestKey, events: [], error: '', loading: true };
  useEffect(() => {
    const controller = new AbortController();
    setResult({ key: requestKey, events: [], error: '', loading: true });
    fetchCareRecordHistory(record.id, controller.signal)
      .then((events) => { if (!controller.signal.aborted) setResult({ key: requestKey, events, error: '', loading: false }); })
      .catch((caught) => { if (!controller.signal.aborted) setResult({ key: requestKey, events: [], error: caught instanceof Error ? caught.message : 'Care history could not be loaded.', loading: false }); });
    return () => controller.abort();
  }, [record.id, requestKey]);
  return <Modal onClose={onClose} labelId="care-history-title"><DialogHeader><div><Eyebrow><IdentificationIcon width={14} /> Immutable care history</Eyebrow><h2 id="care-history-title">Record audit trail.</h2><p>Every mutation is retained with its actor, reason, and before/after care facts.</p></div><IconButton type="button" onClick={onClose} aria-label="Close care history"><XMarkIcon /></IconButton></DialogHeader>{current.loading && <Notice role="status" aria-live="polite"><ArrowPathIcon /> Loading immutable history…</Notice>}{current.error && <Notice $error role="alert"><ExclamationTriangleIcon /> {current.error}</Notice>}{!current.loading && !current.error && <HistoryList>{current.events.map((event) => { const changes = historyChanges(event, timeZone); return <HistoryRow key={event.id}><div><strong>{event.event_type === 'auto_finished_at_checkout' ? 'Sleep closed automatically at checkout' : event.event_type.replaceAll('_', ' ')}</strong><p>{formatCareTime(event.occurred_at, timeZone)} {timeZone} · {event.actor_name}{event.reason ? ` · ${event.reason}` : ''}</p>{changes.length > 0 && <ChangeList>{changes.map((change) => <div key={change.label}><dt>{change.label}</dt><dd><span><em>Before</em>{change.before}</span><b aria-hidden="true">→</b><span><em>After</em>{change.after}</span></dd></div>)}</ChangeList>}</div></HistoryRow>; })}{current.events.length === 0 && <Notice><ClockIcon /> No history events were returned.</Notice>}</HistoryList>}</Modal>;
}

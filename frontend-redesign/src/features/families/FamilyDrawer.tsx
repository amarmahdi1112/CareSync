import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import {
  ArchiveBoxIcon,
  ArrowPathIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  PencilSquareIcon,
  PlusIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserGroupIcon,
  UsersIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { commandBoundToJournalOperation } from '../../api/childcareCommand';
import { ActionButton, Eyebrow, StatusChip } from '../../components/ui/Primitives';
import {
  ChildcareCommandRecoveredCommitError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
  type ChildcareMutationMetadata,
} from '../../childcare-commands/ChildcareCommandRecoveryContext';
import {
  FamiliesApiError,
  archiveFamily,
  buildFamilyArchiveCommand,
  buildFamilyCreateCommand,
  createFamily,
  fetchFamilyDetail,
  replaceFamilyEmergencyContacts,
  replaceFamilyGuardian,
  updateFamily,
} from './familiesApi';
import { FamilyEditPlanError, runFamilyEditCommandPlan } from './familyCommandPlan';
import {
  FAMILY_FIELD_LIMITS,
  emptyEmergencyContact,
  emptyFamilyRegistration,
  emptyGuardian,
  toFamilyEditInput,
  toFamilyPatchInput,
  validateFamilyEdit,
  validateFamilyRegistration,
  type FamilyValidationErrors,
} from './familyForms';
import {
  RELATIONSHIP_CHOICES,
  relationshipSelection,
  type RelationshipSelection,
} from './relationshipOptions';
import type {
  EmergencyContactInput,
  FamilyDetailRecord,
  FamilyEditInput,
  FamilyRegistrationInput,
  GuardianInput,
} from './types';

export type FamilyDrawerRequest =
  | { mode: 'create'; entry?: 'directory' | 'intake' }
  | { mode: 'detail'; familyId: string }
  | { mode: 'edit'; familyId: string };

interface FamilyDrawerProps {
  request: FamilyDrawerRequest;
  organizationId: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}

type Phase = 'loading' | 'ready' | 'error';
type GuardianSection = 'primary_guardian' | 'secondary_guardian';
type PendingCareRemoval =
  | { kind: 'guardian'; section: GuardianSection; label: string }
  | { kind: 'contact'; clientId: string; label: string };
type PendingFamilyRecovery = {
  operationId: string;
  purpose: 'create' | 'edit' | 'archive';
};

const Backdrop = styled.div`
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});

  @media (max-width: 780px) { padding: 0; }
`;

const Drawer = styled.div`
  position: relative;
  isolation: isolate;
  display: grid;
  width: min(920px, calc(100vw - 48px));
  max-height: calc(100dvh - 48px);
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 20px 8px 20px 8px;
  outline: 0;
  background: ${({ theme }) => theme.color.canvasElevated};
  box-shadow: 0 28px 84px color-mix(in srgb, ${({ theme }) => theme.color.ink} 68%, transparent);

  &::before {
    position: absolute;
    z-index: 0;
    top: 0;
    right: 0;
    width: 220px;
    height: 128px;
    border-bottom: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.cyan} 28%, transparent);
    border-left: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.plasma} 22%, transparent);
    background: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 5%, ${({ theme }) => theme.color.canvasElevated});
    clip-path: polygon(100% 0, 100% 100%, 0 0);
    content: '';
    pointer-events: none;
  }

  > * {
    position: relative;
    z-index: 1;
  }

  @media (max-width: 780px) { width: 100vw; max-height: 100dvh; border: 0; border-radius: 0; }
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 21px 24px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surface} 72%, ${({ theme }) => theme.color.canvasElevated});

  h2 {
    margin: 10px 0 5px;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(1.35rem, 2.5vw, 1.9rem);
    font-weight: 560;
    letter-spacing: -.045em;
  }

  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .75rem;
    line-height: 1.6;
  }
`;

const Close = styled.button`
  display: grid;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  transition:
    transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease},
    border-color ${({ theme }) => theme.motion.fast} ease,
    color ${({ theme }) => theme.motion.fast} ease,
    background ${({ theme }) => theme.motion.fast} ease;

  &:hover {
    border-color: ${({ theme }) => theme.color.cyan};
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.surfaceHover};
    transform: translateY(-1px);
  }

  &:disabled { cursor: wait; opacity: .45; }
  svg { width: 19px; }
`;

const Body = styled.div`
  min-height: 0;
  overflow-y: auto;
  scrollbar-color: ${({ theme }) => theme.color.borderStrong} transparent;
`;

const Center = styled.div`
  display: grid;
  min-height: 68dvh;
  place-items: center;
  padding: 36px 24px;
  text-align: center;
  > div { max-width: 500px; }
  svg { width: 46px; margin: 0 auto 17px; color: ${({ theme }) => theme.color.plasmaBright}; }
  h3 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.2rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.7; }
`;

const Form = styled.form`display: grid; min-height: 100%; grid-template-rows: 1fr auto;`;
const Content = styled.fieldset`
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 16px;
  margin: 0;
  padding: 20px 24px 30px;
  border: 0;

  &:disabled { opacity: .72; }
  @media (max-width:580px){padding:16px 14px 26px;}
`;
const Section = styled.section`
  padding: 17px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.radius.lg};
  background: ${({ theme }) => theme.color.surface};
  box-shadow: inset 0 1px 0 color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 5%, transparent);
`;

const SectionHead = styled.header`
  display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 15px;
  > div { display: flex; align-items: center; gap: 10px; }
  svg { width: 20px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .92rem; font-weight: 600; }
  p { margin: 2px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const Grid = styled.div`display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:13px; @media(max-width:580px){grid-template-columns:1fr;}`;
const Field = styled.div<{ $wide?: boolean }>`
  min-width:0; ${({ $wide }) => $wide ? 'grid-column:1/-1;' : ''}

  label {
    display: block;
    margin: 0 0 6px 2px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .72rem;
    font-weight: 600;
    letter-spacing: .07em;
    text-transform: uppercase;
  }

  input, select, textarea {
    width: 100%;
    min-height: 44px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 12px;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: .8125rem;
    transition:
      border-color ${({ theme }) => theme.motion.fast} ease,
      background ${({ theme }) => theme.motion.fast} ease,
      box-shadow ${({ theme }) => theme.motion.fast} ease;
  }

  input::placeholder, textarea::placeholder { color: ${({ theme }) => theme.color.textMuted}; }
  textarea { min-height:88px; padding-block:11px; resize:vertical; line-height:1.55; }
  input:hover, select:hover, textarea:hover { border-color: ${({ theme }) => theme.color.borderStrong}; }
  input:focus, select:focus, textarea:focus {
    border-color: ${({ theme }) => theme.color.cyan};
    background: ${({ theme }) => theme.color.surfaceStrong};
    box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 14%, transparent);
  }
  [aria-invalid='true'] { border-color: ${({ theme }) => theme.color.coral}; }
`;

const FieldError = styled.p`margin:6px 2px 0; color:${({ theme }) => theme.color.coral}; font-size:.72rem;`;
const CustomRelationship = styled.div`margin-top:10px;`;
const Choice = styled.label`
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .75rem;
  cursor: pointer;
  transition:
    border-color ${({ theme }) => theme.motion.fast} ease,
    background ${({ theme }) => theme.motion.fast} ease;

  &:hover {
    border-color: ${({ theme }) => theme.color.borderStrong};
    background: ${({ theme }) => theme.color.surfaceHover};
  }

  input { width:18px; height:18px; accent-color:${({ theme }) => theme.color.cyan}; }
`;
const ChoiceGrid = styled.div`display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; @media(max-width:520px){grid-template-columns:1fr;}`;
const ErrorBox = styled.div`
  padding: 13px 14px;
  border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.coral} 45%, ${({ theme }) => theme.color.border});
  border-radius: 13px;
  outline: 0;
  color: ${({ theme }) => theme.color.coral};
  background: color-mix(in srgb, ${({ theme }) => theme.color.coral} 10%, ${({ theme }) => theme.color.surface});
  font-size: .75rem;
  line-height: 1.55;

  strong { display:block; margin-bottom:3px; color:${({ theme }) => theme.color.text}; }
`;

const IntakeNotice = styled.div`
  padding: 13px 14px;
  border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.cyan} 42%, ${({ theme }) => theme.color.border});
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 7%, ${({ theme }) => theme.color.surfaceStrong});
  font-size: .73rem;
  line-height: 1.58;
  strong { color: ${({ theme }) => theme.color.text}; }
`;

const Footer = styled.footer`
  position: sticky;
  z-index: 2;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 24px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  background: color-mix(in srgb, ${({ theme }) => theme.color.canvasElevated} 94%, transparent);
  backdrop-filter: blur(${({ theme }) => theme.effect.panelBlur});

  p { max-width:360px; margin:0; color:${({ theme }) => theme.color.textMuted}; font-size:.72rem; line-height:1.5; }
  div { display:flex; gap:9px; }

  @media(max-width:580px) {
    align-items: stretch;
    flex-direction: column;
    padding: 13px 14px;
    div { display:grid; grid-template-columns:1fr 1fr; }
  }
`;
const Detail = styled.div`display:grid; gap:16px; padding:20px 24px 30px; @media(max-width:580px){padding:16px 14px 26px;}`;
const DetailGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(2,minmax(0,1fr));
  gap: 13px;
  margin: 0;

  div { padding:12px; border:1px solid ${({ theme }) => theme.color.border}; border-radius:12px; background:${({ theme }) => theme.color.surfaceStrong}; }
  dt { color:${({ theme }) => theme.color.textMuted}; font-size:.72rem; font-weight:600; letter-spacing:.07em; text-transform:uppercase; }
  dd { margin:5px 0 0; color:${({ theme }) => theme.color.textSoft}; font-size:.8125rem; line-height:1.5; }

  @media(max-width:520px){grid-template-columns:1fr;}
`;
const RecordList = styled.div`display:grid;gap:8px;`;
const Record = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  background: ${({ theme }) => theme.color.surfaceStrong};

  strong { display:block; font-size:.8125rem; font-weight:600; }
  small { display:block; margin-top:3px; color:${({ theme }) => theme.color.textMuted}; font-size:.75rem; line-height:1.45; }
`;
const Actions = styled.div`display:flex;flex-wrap:wrap;gap:9px;`;
const Confirm = styled.div`
  padding: 15px;
  border: 1px solid color-mix(in srgb, ${({ theme }) => theme.color.amber} 42%, ${({ theme }) => theme.color.border});
  border-radius: 14px;
  background: color-mix(in srgb, ${({ theme }) => theme.color.amber} 9%, ${({ theme }) => theme.color.surface});

  p { margin:0 0 12px; color:${({ theme }) => theme.color.textSoft}; font-size:.75rem; line-height:1.6; }
`;

function message(caught: unknown): string {
  if (caught instanceof FamilyEditPlanError) return caught.message;
  if (caught instanceof FamiliesApiError) return caught.message;
  return caught instanceof Error ? caught.message : 'The family request could not be completed.';
}

function RelationshipField({
  id,
  value,
  error,
  onChange,
}: {
  id: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  const [customSelected, setCustomSelected] = useState(() => relationshipSelection(value) === 'Other');
  const selection: RelationshipSelection = customSelected ? 'Other' : relationshipSelection(value);
  const errorId = `${id}-error`;
  const choose = (next: RelationshipSelection) => {
    if (next === 'Other') {
      setCustomSelected(true);
      if (relationshipSelection(value) !== 'Other') onChange('');
      return;
    }
    setCustomSelected(false);
    onChange(next);
  };

  return <Field>
    <label htmlFor={id}>Relationship *</label>
    <select id={id} required value={selection} onChange={(event) => choose(event.target.value as RelationshipSelection)} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined}>
      <option value="">Select relationship</option>
      {RELATIONSHIP_CHOICES.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
    </select>
    {customSelected && <CustomRelationship>
      <label htmlFor={`${id}-custom`}>Custom relationship *</label>
      <input id={`${id}-custom`} required maxLength={FAMILY_FIELD_LIMITS.relationship} value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} />
    </CustomRelationship>}
    {error && <FieldError id={errorId}>{error}</FieldError>}
  </Field>;
}

function GuardianFields({
  prefix,
  value,
  errors,
  onChange,
}: {
  prefix: 'primary_guardian' | 'secondary_guardian';
  value: GuardianInput;
  errors: FamilyValidationErrors;
  onChange: (value: GuardianInput) => void;
}) {
  type GuardianTextField = Exclude<keyof GuardianInput, 'record_id' | 'authorized_pickup' | 'guardian_type'>;
  const update = (field: GuardianTextField, next: string) => onChange({ ...value, [field]: next });
  const input = (field: GuardianTextField, label: string, type = 'text') => (
    <Field>
      <label htmlFor={`family-${prefix}-${field}`}>{label}{['first_name', 'last_name', 'email', 'cell_phone'].includes(field) ? ' *' : ''}</label>
      <input id={`family-${prefix}-${field}`} type={type} maxLength={FAMILY_FIELD_LIMITS[field]} value={value[field]} onChange={(event) => update(field, event.target.value)} aria-invalid={Boolean(errors[`${prefix}.${field}`])} />
      {errors[`${prefix}.${field}`] && <FieldError>{errors[`${prefix}.${field}`]}</FieldError>}
    </Field>
  );
  return <Grid>{input('first_name', 'First name')}{input('last_name', 'Last name')}<RelationshipField id={`family-${prefix}-relationship`} value={value.relationship} error={errors[`${prefix}.relationship`]} onChange={(relationship) => update('relationship', relationship)} />{input('email', 'Email', 'email')}{input('cell_phone', 'Cell phone', 'tel')}{input('home_phone', 'Home phone', 'tel')}{input('work_phone', 'Work phone', 'tel')}{input('address', 'Address')}{input('city', 'City')}{input('postal_code', 'Postal code')}<Field $wide><Choice><input type="checkbox" checked={value.authorized_pickup} onChange={(event) => onChange({ ...value, authorized_pickup: event.target.checked })} /> Record affirmative legacy pickup marker (not verified authority)</Choice></Field></Grid>;
}

function EmergencyContactFields({
  idPrefix,
  errorPrefix,
  value,
  errors,
  onChange,
}: {
  idPrefix: string;
  errorPrefix: string;
  value: EmergencyContactInput;
  errors: FamilyValidationErrors;
  onChange: (value: EmergencyContactInput) => void;
}) {
  type ContactTextField = 'first_name' | 'last_name' | 'cell_phone' | 'home_phone';
  const update = <K extends keyof EmergencyContactInput>(field: K, next: EmergencyContactInput[K]) => {
    onChange({ ...value, [field]: next });
  };
  const input = (field: ContactTextField, label: string, required = false, type = 'text') => {
    const error = errors[`${errorPrefix}.${field}`];
    return <Field>
      <label htmlFor={`${idPrefix}-${field}`}>{label}{required ? ' *' : ''}</label>
      <input id={`${idPrefix}-${field}`} type={type} maxLength={FAMILY_FIELD_LIMITS[field]} value={value[field]} onChange={(event) => update(field, event.target.value)} aria-invalid={Boolean(error)} />
      {error && <FieldError>{error}</FieldError>}
    </Field>;
  };
  return <Grid>
    {input('first_name', 'First name', true)}
    {input('last_name', 'Last name', true)}
    <RelationshipField id={`${idPrefix}-relationship`} value={value.relationship} error={errors[`${errorPrefix}.relationship`]} onChange={(relationship) => update('relationship', relationship)} />
    {input('cell_phone', 'Cell phone', true, 'tel')}
    {input('home_phone', 'Home phone', false, 'tel')}
    <Field $wide><Choice><input type="checkbox" checked={value.authorized_pickup} onChange={(event) => update('authorized_pickup', event.target.checked)} /> Record affirmative legacy pickup marker (not verified authority)</Choice></Field>
  </Grid>;
}

export default function FamilyDrawer({ request, organizationId, onClose, onSaved }: FamilyDrawerProps) {
  const commandRecovery = useChildcareCommandRecovery();
  const [phase, setPhase] = useState<Phase>(request.mode === 'create' ? 'ready' : 'loading');
  const [detail, setDetail] = useState<FamilyDetailRecord | null>(null);
  const [registration, setRegistration] = useState<FamilyRegistrationInput>(() => {
    return emptyFamilyRegistration(request.mode === 'create' && request.entry === 'intake' ? 'pending' : 'active');
  });
  const [edit, setEdit] = useState<FamilyEditInput | null>(null);
  const [editing, setEditing] = useState(request.mode === 'edit');
  const [errors, setErrors] = useState<FamilyValidationErrors>({});
  const [requestError, setRequestError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pendingRecovery, setPendingRecovery] = useState<PendingFamilyRecovery | null>(null);
  const [requiresReload, setRequiresReload] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [pendingCareRemoval, setPendingCareRemoval] = useState<PendingCareRemoval | null>(null);
  const [revision, setRevision] = useState(0);
  const drawerRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const saveController = useRef<AbortController | null>(null);

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
      saveController.current?.abort();
      previousFocus.current?.focus();
    };
  }, []);

  useEffect(() => {
    if (request.mode === 'create') return;
    const controller = new AbortController();
    setPhase('loading');
    setRequestError('');
    fetchFamilyDetail(request.familyId, organizationId, controller.signal)
      .then((record) => {
        if (controller.signal.aborted) return;
        setDetail(record);
        setEdit(toFamilyEditInput(record));
        setEditing(request.mode === 'edit');
        setPendingRecovery(null);
        setRequiresReload(false);
        setPhase('ready');
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setRequestError(message(caught));
        setPhase('error');
      });
    return () => controller.abort();
  }, [request, organizationId, revision]);

  useEffect(() => {
    if (phase !== 'ready') return;
    requestAnimationFrame(() => {
      const target = drawerRef.current?.querySelector<HTMLElement>('[data-autofocus="true"]')
        || drawerRef.current?.querySelector<HTMLElement>('button, input, select, textarea');
      target?.focus();
    });
  }, [phase]);

  const mutationLocked = childcareMutationControlDisabled(
    commandRecovery.laneBlocked,
    saving,
    requiresReload,
    Boolean(pendingRecovery),
  );
  const close = useCallback(() => { if (!saving) onClose(); }, [saving, onClose]);
  const trapFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      if (pendingCareRemoval) setPendingCareRemoval(null);
      else close();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...(drawerRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]') || [])];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };

  const failValidation = (nextErrors: FamilyValidationErrors) => {
    setErrors(nextErrors);
    setRequestError('Review the highlighted fields before saving.');
    requestAnimationFrame(() => errorRef.current?.focus());
  };

  const executeExact = async (
    run: (signal?: AbortSignal) => Promise<FamilyDetailRecord>,
    onSuccess: (saved: FamilyDetailRecord) => void,
  ) => {
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    setRequestError('');
    try {
      const saved = await run(controller.signal);
      setPendingRecovery(null);
      setRequiresReload(false);
      onSuccess(saved);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const recoveryCause = caught instanceof FamilyEditPlanError ? caught.cause : caught;
      if (recoveryCause instanceof ChildcareCommandRecoveredCommitError) {
        setPendingRecovery(null);
        onSaved('The interrupted family change was confirmed saved.');
        return;
      }
      if (caught instanceof FamilyEditPlanError && caught.confirmedStages.length > 0) {
        setRequiresReload(true);
      }
      setRequestError(message(caught));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setSaving(false);
      saveController.current = null;
    }
  };

  useEffect(() => {
    if (
      saving
      || !pendingRecovery
      || commandRecovery.lastResolved?.clientOperationId !== pendingRecovery.operationId
    ) return;
    if (pendingRecovery.purpose !== 'edit') {
      setPendingRecovery(null);
      onSaved(`The previously unresolved family ${pendingRecovery.purpose === 'create' ? 'registration' : 'archive'} was confirmed saved.`);
      return;
    }
    const controller = new AbortController();
    void fetchFamilyDetail(
      commandRecovery.lastResolved.targetId,
      organizationId,
      controller.signal,
    ).then((record) => {
      if (controller.signal.aborted) return;
      setDetail(record);
      setPendingRecovery(null);
      setRequiresReload(false);
      setRequestError('The saved section was confirmed. Review the remaining in-memory changes and choose Save changes to continue with a new command.');
      requestAnimationFrame(() => errorRef.current?.focus());
    }).catch((caught) => {
      if (controller.signal.aborted) return;
      setPendingRecovery(null);
      setRequiresReload(true);
      setRequestError(`The saved family section was confirmed, but its current record could not be refreshed. ${message(caught)}`);
      requestAnimationFrame(() => errorRef.current?.focus());
    });
    return () => controller.abort();
  }, [commandRecovery.lastResolved, onSaved, organizationId, pendingRecovery, saving]);

  useEffect(() => {
    if (!pendingRecovery || !childcareFinalAbsenceAcknowledged(
      pendingRecovery.operationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    const purpose = pendingRecovery.purpose;
    if (purpose === 'edit' && detail) {
      const controller = new AbortController();
      void fetchFamilyDetail(detail.id, organizationId, controller.signal).then((record) => {
        if (controller.signal.aborted) return;
        setDetail(record);
        setPendingRecovery(null);
        setRequiresReload(false);
        setRequestError('The server proved this family section was not saved. The canonical family was refreshed; review the retained values and choose Save changes to create a new operation.');
        requestAnimationFrame(() => errorRef.current?.focus());
      }).catch((caught) => {
        if (controller.signal.aborted) return;
        setPendingRecovery(null);
        setRequiresReload(true);
        setRequestError(`The server proved this family section was not saved, but the current family could not be refreshed. ${message(caught)}`);
        requestAnimationFrame(() => errorRef.current?.focus());
      });
      return () => controller.abort();
    }
    setPendingRecovery(null);
    setRequiresReload(false);
    setRequestError(
      `The server proved this ${purpose === 'create' ? 'registration' : purpose === 'archive' ? 'archive action' : 'family section'} was not saved. Review the retained values and choose ${purpose === 'archive' ? 'Confirm archive' : purpose === 'create' ? 'Register family' : 'Save changes'} to create a new operation.`,
    );
    requestAnimationFrame(() => errorRef.current?.focus());
  }, [commandRecovery.lastFinalAbsenceAcknowledgedOperationId, detail, organizationId, pendingRecovery]);

  const runRecoveredFamilyCommand = (
    metadata: ChildcareMutationMetadata,
    send: (operationId: string) => Promise<FamilyDetailRecord>,
    purpose: PendingFamilyRecovery['purpose'] = 'edit',
    signal?: AbortSignal,
  ): Promise<FamilyDetailRecord> => {
    setPendingRecovery({ operationId: metadata.clientOperationId, purpose });
    return commandRecovery.execute(metadata, send)
      .then(async (result) => {
        const canonical = purpose === 'edit' && metadata.expectedTargetId
          ? await fetchFamilyDetail(metadata.expectedTargetId, organizationId, signal)
          : result;
        setPendingRecovery(null);
        return canonical;
      })
      .catch(async (caught) => {
        if (childcareCommandWasNotPrepared(caught, metadata.clientOperationId)) {
          setPendingRecovery(null);
          throw caught;
        }
        if (purpose !== 'edit' || !(caught instanceof ChildcareCommandRecoveredCommitError)) throw caught;
        const canonical = await fetchFamilyDetail(caught.resolution.targetId, organizationId, signal);
        setPendingRecovery(null);
        return canonical;
      });
  };

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (mutationLocked) return;
    const nextErrors = validateFamilyRegistration(registration);
    if (Object.keys(nextErrors).length) { failValidation(nextErrors); return; }
    const command = buildFamilyCreateCommand(registration);
    await executeExact(
      (signal) => runRecoveredFamilyCommand({
        clientOperationId: command.clientOperationId,
        commandType: 'family.create',
        targetType: 'family',
        expectedTargetId: null,
        expectedActionOwnerId: null,
      }, (operationId) => createFamily(
        commandBoundToJournalOperation(command, operationId),
        organizationId,
        signal,
      ), 'create', signal),
      (saved) => onSaved(`${saved.name} was registered.`),
    );
  };

  const submitEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (mutationLocked) return;
    if (!detail || !edit) return;
    const careNetworkLoaded = ['primary_guardian', 'secondary_guardian', 'emergency_contacts'].every(
      (section) => Object.prototype.hasOwnProperty.call(edit, section),
    );
    if (!careNetworkLoaded) {
      setRequestError('The complete care network did not load. Close and reopen this family before saving; no records were changed.');
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    const patchInput = toFamilyPatchInput(edit, detail);
    const nextErrors = validateFamilyEdit(patchInput);
    if (Object.keys(nextErrors).length) { failValidation(nextErrors); return; }
    await executeExact(
      (signal) => runFamilyEditCommandPlan({
        baseline: detail,
        edit,
        organizationId,
        signal,
      }, {
        updateCore: (familyId, command, scopedOrganizationId, commandSignal) => runRecoveredFamilyCommand({
          clientOperationId: command.clientOperationId,
          commandType: 'family.update',
          targetType: 'family',
          expectedTargetId: familyId,
          expectedActionOwnerId: null,
        }, (operationId) => updateFamily(
          familyId,
          commandBoundToJournalOperation(command, operationId),
          scopedOrganizationId,
          commandSignal,
        ), 'edit', commandSignal),
        replaceGuardian: (familyId, slot, command, scopedOrganizationId, commandSignal) => runRecoveredFamilyCommand({
          clientOperationId: command.clientOperationId,
          commandType: slot === 'primary' ? 'family.guardian.primary.replace' : 'family.guardian.secondary.replace',
          targetType: 'family',
          expectedTargetId: familyId,
          expectedActionOwnerId: null,
        }, (operationId) => replaceFamilyGuardian(
          familyId,
          slot,
          commandBoundToJournalOperation(command, operationId),
          scopedOrganizationId,
          commandSignal,
        ), 'edit', commandSignal),
        replaceEmergencyContacts: (familyId, command, scopedOrganizationId, commandSignal) => runRecoveredFamilyCommand({
          clientOperationId: command.clientOperationId,
          commandType: 'family.emergency_contacts.replace',
          targetType: 'family',
          expectedTargetId: familyId,
          expectedActionOwnerId: null,
        }, (operationId) => replaceFamilyEmergencyContacts(
          familyId,
          commandBoundToJournalOperation(command, operationId),
          scopedOrganizationId,
          commandSignal,
        ), 'edit', commandSignal),
      }),
      (saved) => {
        setDetail(saved);
        setEdit(toFamilyEditInput(saved));
        setPendingCareRemoval(null);
        setEditing(false);
        onSaved(`${saved.name} was updated.`);
      },
    );
  };

  const archive = async () => {
    if (!detail || mutationLocked) return;
    const command = buildFamilyArchiveCommand(detail);
    await executeExact(
      (signal) => runRecoveredFamilyCommand({
        clientOperationId: command.clientOperationId,
        commandType: 'family.update',
        targetType: 'family',
        expectedTargetId: detail.id,
        expectedActionOwnerId: null,
      }, (operationId) => archiveFamily(
        detail,
        commandBoundToJournalOperation(command, operationId),
        organizationId,
        signal,
      ), 'archive', signal),
      (saved) => onSaved(`${saved.name} was archived.`),
    );
  };

  const confirmCareRemoval = () => {
    if (!pendingCareRemoval) return;
    setEdit((current) => {
      if (!current) return current;
      if (pendingCareRemoval.kind === 'guardian') {
        return { ...current, [pendingCareRemoval.section]: null };
      }
      return {
        ...current,
        emergency_contacts: (current.emergency_contacts || []).filter(
          (contact) => contact.client_id !== pendingCareRemoval.clientId,
        ),
      };
    });
    setPendingCareRemoval(null);
  };

  const cancelEdit = () => {
    if (request.mode === 'edit') {
      close();
      return;
    }
    if (detail) setEdit(toFamilyEditInput(detail));
    setEditing(false);
    setPendingCareRemoval(null);
    setErrors({});
    setRequestError('');
  };

  const title = request.mode === 'create'
    ? request.entry === 'intake' ? 'Start a family intake record' : 'Register a family'
    : request.mode === 'edit' ? `Edit ${detail?.name || 'family'}` : detail?.name || 'Family record';

  return createPortal(
    <Backdrop onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <Drawer ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="family-drawer-title" aria-describedby="family-drawer-description" onKeyDown={trapFocus}>
        <Header><div><Eyebrow><ShieldCheckIcon width={14} /> Organization-scoped family record</Eyebrow><h2 id="family-drawer-title">{title}</h2><p id="family-drawer-description">Family records are saved through versioned, receipt-backed commands.</p></div><Close type="button" onClick={close} disabled={saving} aria-label="Close family panel"><XMarkIcon /></Close></Header>
        <Body>
          {phase === 'loading' ? <Center aria-busy="true"><div><ArrowPathIcon /><h3>Loading the family record</h3><p>CareSync is confirming this record belongs to the active organization.</p></div></Center>
            : phase === 'error' ? <Center role="alert"><div><ExclamationTriangleIcon /><h3>The family record could not open</h3><p>{requestError}</p><Actions style={{ justifyContent: 'center', marginTop: 20 }}><ActionButton $variant="primary" onClick={() => setRevision((value) => value + 1)}><ArrowPathIcon /> Retry</ActionButton><ActionButton onClick={close}>Cancel</ActionButton></Actions></div></Center>
              : request.mode === 'create' ? (
                <Form onSubmit={submitCreate} noValidate>
                  <Content disabled={mutationLocked}>
                    {requestError && <ErrorBox ref={errorRef} tabIndex={-1} role="alert"><strong>{pendingRecovery ? 'Registration needs saved-result review' : 'The family was not saved'}</strong>{requestError}</ErrorBox>}
                    {request.entry === 'intake' && <IntakeNotice role="note"><strong>Intake entry starts as Pending.</strong> Pending is an operational family status, not an admissions decision or certification. Review the explicit status choice before saving.</IntakeNotice>}
                    <Section><SectionHead><div><IdentificationIcon /><div><h3>Household identity</h3><p>Core family record</p></div></div></SectionHead><Grid>
                      <Field><label htmlFor="family-create-name">Family name *</label><input id="family-create-name" data-autofocus="true" maxLength={FAMILY_FIELD_LIMITS.name} value={registration.name} onChange={(event) => setRegistration((value) => ({ ...value, name: event.target.value }))} aria-invalid={Boolean(errors.name)} />{errors.name && <FieldError>{errors.name}</FieldError>}</Field>
                      <Field><label htmlFor="family-create-file">Internal file number</label><input id="family-create-file" maxLength={FAMILY_FIELD_LIMITS.file_number} value={registration.file_number} onChange={(event) => setRegistration((value) => ({ ...value, file_number: event.target.value }))} aria-invalid={Boolean(errors.file_number)} />{errors.file_number && <FieldError>{errors.file_number}</FieldError>}</Field>
                      <Field><label htmlFor="family-create-status">Status</label><select id="family-create-status" value={registration.status} onChange={(event) => setRegistration((value) => ({ ...value, status: event.target.value }))}><option value="active">Active</option><option value="pending">Pending</option></select></Field>
                    </Grid></Section>
                    <Section><SectionHead><div><UserGroupIcon /><div><h3>Primary guardian</h3><p>Optional during initial registration</p></div></div></SectionHead><Choice><input type="checkbox" checked={registration.include_primary_guardian} onChange={(event) => setRegistration((value) => ({ ...value, include_primary_guardian: event.target.checked }))} /> Add a primary guardian now</Choice>{registration.include_primary_guardian && <div style={{ marginTop: 14 }}><GuardianFields prefix="primary_guardian" value={registration.primary_guardian} errors={errors} onChange={(primary_guardian) => setRegistration((value) => ({ ...value, primary_guardian }))} /></div>}
                      <div style={{ marginTop: 12 }}><Choice><input type="checkbox" checked={registration.include_secondary_guardian} onChange={(event) => setRegistration((value) => ({ ...value, include_secondary_guardian: event.target.checked }))} /> Add a second guardian</Choice></div>{registration.include_secondary_guardian && <div style={{ marginTop: 14 }}><GuardianFields prefix="secondary_guardian" value={registration.secondary_guardian} errors={errors} onChange={(secondary_guardian) => setRegistration((value) => ({ ...value, secondary_guardian }))} /></div>}
                    </Section>
                    <Section><SectionHead><div><UsersIcon /><div><h3>Emergency contacts</h3><p>Contact relationship and optional legacy pickup marker</p></div></div><ActionButton type="button" onClick={() => setRegistration((value) => ({ ...value, emergency_contacts: [...value.emergency_contacts, emptyEmergencyContact()] }))}><PlusIcon /> Add contact</ActionButton></SectionHead><RecordList>
                      {registration.emergency_contacts.length === 0 && <Record><div><strong>No emergency contacts added yet</strong><small>You can register the family now and add one before care begins.</small></div></Record>}
                      {registration.emergency_contacts.map((contact, index) => <Section key={contact.client_id}><SectionHead><div><UsersIcon /><div><h3>Contact {index + 1}</h3></div></div><ActionButton type="button" aria-label={`Remove emergency contact ${index + 1}`} onClick={() => setRegistration((value) => ({ ...value, emergency_contacts: value.emergency_contacts.filter((item) => item.client_id !== contact.client_id) }))}><TrashIcon /> Remove</ActionButton></SectionHead><Grid>
                        {(['first_name', 'last_name'] as const).map((field) => <Field key={field}><label htmlFor={`family-contact-${index}-${field}`}>{field.replaceAll('_', ' ')} *</label><input id={`family-contact-${index}-${field}`} maxLength={FAMILY_FIELD_LIMITS[field]} value={contact[field]} onChange={(event) => setRegistration((value) => ({ ...value, emergency_contacts: value.emergency_contacts.map((item) => item.client_id === contact.client_id ? { ...item, [field]: event.target.value } : item) }))} aria-invalid={Boolean(errors[`emergency_contacts.${index}.${field}`])} />{errors[`emergency_contacts.${index}.${field}`] && <FieldError>{errors[`emergency_contacts.${index}.${field}`]}</FieldError>}</Field>)}
                        <RelationshipField id={`family-contact-${index}-relationship`} value={contact.relationship} error={errors[`emergency_contacts.${index}.relationship`]} onChange={(relationship) => setRegistration((value) => ({ ...value, emergency_contacts: value.emergency_contacts.map((item) => item.client_id === contact.client_id ? { ...item, relationship } : item) }))} />
                        {(['cell_phone', 'home_phone'] as const).map((field) => <Field key={field}><label htmlFor={`family-contact-${index}-${field}`}>{field.replaceAll('_', ' ')}{field === 'cell_phone' ? ' *' : ''}</label><input id={`family-contact-${index}-${field}`} type="tel" maxLength={FAMILY_FIELD_LIMITS[field]} value={contact[field]} onChange={(event) => setRegistration((value) => ({ ...value, emergency_contacts: value.emergency_contacts.map((item) => item.client_id === contact.client_id ? { ...item, [field]: event.target.value } : item) }))} aria-invalid={Boolean(errors[`emergency_contacts.${index}.${field}`])} />{errors[`emergency_contacts.${index}.${field}`] && <FieldError>{errors[`emergency_contacts.${index}.${field}`]}</FieldError>}</Field>)}
                        <Field $wide><Choice><input type="checkbox" checked={contact.authorized_pickup} onChange={(event) => setRegistration((value) => ({ ...value, emergency_contacts: value.emergency_contacts.map((item) => item.client_id === contact.client_id ? { ...item, authorized_pickup: event.target.checked } : item) }))} /> Record affirmative legacy pickup marker (not verified authority)</Choice></Field>
                      </Grid></Section>)}
                    </RecordList></Section>
                    <Section><SectionHead><div><CheckIcon /><div><h3>Legacy profile markers and notes</h3><p>These booleans are not versioned consent evidence; 0029 adds that authority layer.</p></div></div></SectionHead><ChoiceGrid>
                      <Choice><input type="checkbox" checked={registration.consents.photo_consent} onChange={(event) => setRegistration((value) => ({ ...value, consents: { ...value.consents, photo_consent: event.target.checked } }))} /> Record affirmative photo marker</Choice>
                      <Choice><input type="checkbox" checked={registration.consents.field_trip_consent} onChange={(event) => setRegistration((value) => ({ ...value, consents: { ...value.consents, field_trip_consent: event.target.checked } }))} /> Record affirmative field-trip marker</Choice>
                      <Choice><input type="checkbox" checked={registration.consents.emergency_medical_consent} onChange={(event) => setRegistration((value) => ({ ...value, consents: { ...value.consents, emergency_medical_consent: event.target.checked } }))} /> Record affirmative emergency-medical marker</Choice>
                    </ChoiceGrid><Field $wide style={{ marginTop: 13 }}><label htmlFor="family-create-notes">Additional notes</label><textarea id="family-create-notes" value={registration.additional_notes} onChange={(event) => setRegistration((value) => ({ ...value, additional_notes: event.target.value }))} /></Field></Section>
                  </Content><Footer><p>{pendingRecovery ? 'The form stays in memory while the saved result is checked. CareSync will not resend it.' : 'Registration is one transaction: a controlled failure creates no partial family, guardian, or contact records.'}</p><div><ActionButton type="button" onClick={close} disabled={saving}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={mutationLocked}>{saving ? <><ArrowPathIcon /> Saving…</> : <><PlusIcon /> Register family</>}</ActionButton></div></Footer>
                </Form>
              ) : editing && detail && edit ? (
                <Form onSubmit={submitEdit} noValidate><Content disabled={mutationLocked}>
                  {requestError && <ErrorBox ref={errorRef} tabIndex={-1} role="alert"><strong>{pendingRecovery ? 'A section needs saved-result review' : requiresReload ? 'Some sections were saved' : 'The family was not saved'}</strong>{requestError}</ErrorBox>}
                  <Section><SectionHead><div><PencilSquareIcon /><div><h3>Family details</h3><p>Edit core status, legacy profile markers, and notes</p></div></div></SectionHead><Grid>
                    <Field><label htmlFor="family-edit-name">Family name *</label><input id="family-edit-name" data-autofocus="true" maxLength={FAMILY_FIELD_LIMITS.name} value={edit.name} onChange={(event) => setEdit((value) => value && ({ ...value, name: event.target.value }))} aria-invalid={Boolean(errors.name)} />{errors.name && <FieldError>{errors.name}</FieldError>}</Field>
                    <Field><label htmlFor="family-edit-file">Internal file number</label><input id="family-edit-file" maxLength={FAMILY_FIELD_LIMITS.file_number} value={edit.file_number} onChange={(event) => setEdit((value) => value && ({ ...value, file_number: event.target.value }))} aria-invalid={Boolean(errors.file_number)} />{errors.file_number && <FieldError>{errors.file_number}</FieldError>}</Field>
                    <Field><label htmlFor="family-edit-status">Status</label><select id="family-edit-status" value={edit.status} onChange={(event) => setEdit((value) => value && ({ ...value, status: event.target.value }))}><option value="active">Active</option><option value="pending">Pending</option><option value="inactive">Inactive</option><option value="archived">Archived</option></select></Field>
                  </Grid></Section>
                  <Section><SectionHead><div><UserGroupIcon /><div><h3>Primary guardian</h3><p>{edit.primary_guardian?.record_id ? 'Saved guardian record' : edit.primary_guardian ? 'New guardian' : 'Not recorded'}</p></div></div>{edit.primary_guardian ? <ActionButton type="button" onClick={() => setPendingCareRemoval({ kind: 'guardian', section: 'primary_guardian', label: `${edit.primary_guardian?.first_name} ${edit.primary_guardian?.last_name}`.trim() || 'the primary guardian' })}><TrashIcon /> Remove</ActionButton> : <ActionButton type="button" onClick={() => { setEdit((value) => value && ({ ...value, primary_guardian: emptyGuardian('primary') })); setPendingCareRemoval(null); }}><PlusIcon /> Add guardian</ActionButton>}</SectionHead>
                    {edit.primary_guardian ? <GuardianFields key={edit.primary_guardian.record_id || 'new-primary'} prefix="primary_guardian" value={edit.primary_guardian} errors={errors} onChange={(primary_guardian) => setEdit((value) => value && ({ ...value, primary_guardian }))} /> : <Record><div><strong>No primary guardian recorded</strong><small>Add one without changing any other care-network section.</small></div></Record>}
                    {pendingCareRemoval?.kind === 'guardian' && pendingCareRemoval.section === 'primary_guardian' && <Confirm style={{ marginTop: 13 }}><p>Retire <strong>{pendingCareRemoval.label}</strong> as the current primary guardian when you save? Their prior record remains in the auditable family history.</p><Actions><ActionButton type="button" onClick={() => setPendingCareRemoval(null)}>Keep guardian</ActionButton><ActionButton type="button" $variant="primary" onClick={confirmCareRemoval}><TrashIcon /> Confirm retirement</ActionButton></Actions></Confirm>}
                  </Section>
                  <Section><SectionHead><div><UserGroupIcon /><div><h3>Secondary guardian</h3><p>{edit.secondary_guardian?.record_id ? 'Saved guardian record' : edit.secondary_guardian ? 'New guardian' : 'Not recorded'}</p></div></div>{edit.secondary_guardian ? <ActionButton type="button" onClick={() => setPendingCareRemoval({ kind: 'guardian', section: 'secondary_guardian', label: `${edit.secondary_guardian?.first_name} ${edit.secondary_guardian?.last_name}`.trim() || 'the secondary guardian' })}><TrashIcon /> Remove</ActionButton> : <ActionButton type="button" onClick={() => { setEdit((value) => value && ({ ...value, secondary_guardian: emptyGuardian('secondary') })); setPendingCareRemoval(null); }}><PlusIcon /> Add guardian</ActionButton>}</SectionHead>
                    {edit.secondary_guardian ? <GuardianFields key={edit.secondary_guardian.record_id || 'new-secondary'} prefix="secondary_guardian" value={edit.secondary_guardian} errors={errors} onChange={(secondary_guardian) => setEdit((value) => value && ({ ...value, secondary_guardian }))} /> : <Record><div><strong>No secondary guardian recorded</strong><small>This role can remain empty.</small></div></Record>}
                    {pendingCareRemoval?.kind === 'guardian' && pendingCareRemoval.section === 'secondary_guardian' && <Confirm style={{ marginTop: 13 }}><p>Retire <strong>{pendingCareRemoval.label}</strong> as the current secondary guardian when you save? Their prior record remains in the auditable family history.</p><Actions><ActionButton type="button" onClick={() => setPendingCareRemoval(null)}>Keep guardian</ActionButton><ActionButton type="button" $variant="primary" onClick={confirmCareRemoval}><TrashIcon /> Confirm retirement</ActionButton></Actions></Confirm>}
                  </Section>
                  <Section><SectionHead><div><UsersIcon /><div><h3>Emergency contacts</h3><p>{edit.emergency_contacts?.length || 0} in this replacement set</p></div></div><ActionButton type="button" onClick={() => { setEdit((value) => value && ({ ...value, emergency_contacts: [...(value.emergency_contacts || []), emptyEmergencyContact()] })); setPendingCareRemoval(null); }}><PlusIcon /> Add contact</ActionButton></SectionHead><RecordList>
                    {(edit.emergency_contacts?.length || 0) === 0 && <Record><div><strong>No current emergency contacts</strong><small>Saving this empty replacement retires the current set; prior contact history remains auditable.</small></div></Record>}
                    {(edit.emergency_contacts || []).map((contact, index) => <Section key={contact.client_id}><SectionHead><div><UsersIcon /><div><h3>Contact {index + 1}</h3><p>{contact.record_id ? 'Saved contact record' : 'New contact'}</p></div></div><ActionButton type="button" aria-label={`Remove emergency contact ${index + 1}`} onClick={() => setPendingCareRemoval({ kind: 'contact', clientId: contact.client_id, label: `${contact.first_name} ${contact.last_name}`.trim() || `contact ${index + 1}` })}><TrashIcon /> Remove</ActionButton></SectionHead>
                      <EmergencyContactFields idPrefix={`family-edit-contact-${index}`} errorPrefix={`emergency_contacts.${index}`} value={contact} errors={errors} onChange={(next) => setEdit((value) => value && ({ ...value, emergency_contacts: (value.emergency_contacts || []).map((item) => item.client_id === contact.client_id ? next : item) }))} />
                      {pendingCareRemoval?.kind === 'contact' && pendingCareRemoval.clientId === contact.client_id && <Confirm style={{ marginTop: 13 }}><p>Retire <strong>{pendingCareRemoval.label}</strong> from the current emergency-contact set when you save? The replacement keeps prior history auditable.</p><Actions><ActionButton type="button" onClick={() => setPendingCareRemoval(null)}>Keep contact</ActionButton><ActionButton type="button" $variant="primary" onClick={confirmCareRemoval}><TrashIcon /> Confirm retirement</ActionButton></Actions></Confirm>}
                    </Section>)}
                  </RecordList></Section>
                  <Section><SectionHead><div><CheckIcon /><div><h3>Legacy profile markers and notes</h3><p>Imported yes/no markers only; protected versioned consent and release authority are reviewed separately.</p></div></div></SectionHead><ChoiceGrid>
                    <Choice><input type="checkbox" checked={edit.consents.photo_consent} onChange={(event) => setEdit((value) => value && ({ ...value, consents: { ...value.consents, photo_consent: event.target.checked } }))} /> Record affirmative photo marker</Choice>
                    <Choice><input type="checkbox" checked={edit.consents.field_trip_consent} onChange={(event) => setEdit((value) => value && ({ ...value, consents: { ...value.consents, field_trip_consent: event.target.checked } }))} /> Record affirmative field-trip marker</Choice>
                    <Choice><input type="checkbox" checked={edit.consents.emergency_medical_consent} onChange={(event) => setEdit((value) => value && ({ ...value, consents: { ...value.consents, emergency_medical_consent: event.target.checked } }))} /> Record affirmative emergency-medical marker</Choice>
                  </ChoiceGrid><Field $wide style={{ marginTop: 13 }}><label htmlFor="family-edit-notes">Additional notes</label><textarea id="family-edit-notes" value={edit.additional_notes} onChange={(event) => setEdit((value) => value && ({ ...value, additional_notes: event.target.value }))} /></Field></Section>
                </Content><Footer><p>{pendingRecovery ? 'The unresolved section is held for receipt reconciliation; it will not be resent.' : requiresReload ? 'Reload the confirmed server state before making another change.' : pendingCareRemoval ? 'Confirm or cancel the pending removal before saving.' : 'Each changed section is saved in order with the version returned by the previous command.'}</p><div><ActionButton type="button" onClick={cancelEdit} disabled={saving}>Cancel</ActionButton>{requiresReload && !commandRecovery.laneBlocked ? <ActionButton type="button" $variant="primary" onClick={() => { setRequiresReload(false); setRequestError(''); setRevision((value) => value + 1); }}><ArrowPathIcon /> Reload saved record</ActionButton> : <ActionButton type="submit" $variant="primary" disabled={mutationLocked || Boolean(pendingCareRemoval)}>{saving ? <><ArrowPathIcon /> Saving…</> : <><CheckIcon /> Save changes</>}</ActionButton>}</div></Footer></Form>
              ) : detail ? (
                <Detail>
                  {requestError && <ErrorBox ref={errorRef} tabIndex={-1} role="alert"><strong>{pendingRecovery ? 'Archive needs saved-result review' : 'The action did not finish'}</strong>{requestError}</ErrorBox>}
                  <Actions><ActionButton $variant="primary" disabled={mutationLocked} onClick={() => { setEdit(toFamilyEditInput(detail)); setEditing(true); setPendingCareRemoval(null); setConfirmArchive(false); setErrors({}); setRequestError(''); }}><PencilSquareIcon /> Edit family</ActionButton>{detail.status !== 'archived' && <ActionButton disabled={mutationLocked} onClick={() => setConfirmArchive(true)}><ArchiveBoxIcon /> Archive</ActionButton>}</Actions>
                  {confirmArchive && <Confirm><p>Archive <strong>{detail.name}</strong>? The record remains in history and can be reviewed, but it will no longer be active.</p><Actions><ActionButton onClick={() => setConfirmArchive(false)} disabled={saving}>Keep active</ActionButton><ActionButton $variant="primary" onClick={archive} disabled={mutationLocked}>{saving ? <><ArrowPathIcon /> Archiving…</> : <><ArchiveBoxIcon /> Confirm archive</>}</ActionButton></Actions></Confirm>}
                  <Section><SectionHead><div><IdentificationIcon /><div><h3>Household record</h3></div></div><StatusChip $tone={detail.status === 'active' ? 'success' : 'neutral'}>{detail.status}</StatusChip></SectionHead><DetailGrid><div><dt>Family name</dt><dd>{detail.name}</dd></div><div><dt>File number</dt><dd>{detail.file_number || 'Not recorded'}</dd></div><div><dt>Added</dt><dd>{new Date(detail.created_at).toLocaleDateString('en-CA')}</dd></div><div><dt>Notes</dt><dd>{detail.additional_notes || 'No notes recorded'}</dd></div></DetailGrid></Section>
                  <Section><SectionHead><div><UserGroupIcon /><div><h3>Guardians</h3><p>{detail.guardians.length} saved · verified release authority is reviewed in the protected family workspace</p></div></div></SectionHead><RecordList>{detail.guardians.length === 0 ? <Record><div><strong>No guardians recorded</strong></div></Record> : detail.guardians.map((guardian) => <Record key={guardian.id}><div><strong>{guardian.first_name} {guardian.last_name}</strong><small>{guardian.relationship || guardian.guardian_type} · {guardian.email || 'No email'} · {guardian.cell_phone || 'No phone'}</small></div><StatusChip $tone={guardian.authorized_pickup ? 'info' : 'neutral'}>{guardian.authorized_pickup ? 'Legacy pickup marker: yes' : 'No affirmative marker recorded'}</StatusChip></Record>)}</RecordList></Section>
                  <Section><SectionHead><div><UsersIcon /><div><h3>Children</h3><p>{detail.children.length} linked</p></div></div></SectionHead><RecordList>{detail.children.length === 0 ? <Record><div><strong>No children linked yet</strong><small>Add a child from the Children directory.</small></div></Record> : detail.children.map((child) => <Record key={child.id}><div><strong>{child.first_name} {child.last_name}</strong><small>{child.age_group || 'Age group not recorded'}</small></div><StatusChip $tone={child.is_active ? 'success' : 'neutral'}>{child.is_active ? 'Active' : 'Archived'}</StatusChip></Record>)}</RecordList></Section>
                  <Section><SectionHead><div><UsersIcon /><div><h3>Emergency contacts</h3><p>{detail.emergency_contacts.length} saved · pickup values are legacy markers, not verified authority</p></div></div></SectionHead><RecordList>{detail.emergency_contacts.length === 0 ? <Record><div><strong>No emergency contacts recorded</strong></div></Record> : detail.emergency_contacts.map((contact) => <Record key={contact.id}><div><strong>{contact.first_name} {contact.last_name}</strong><small>{contact.relationship} · {contact.cell_phone}</small></div><StatusChip $tone={contact.authorized_pickup ? 'info' : 'neutral'}>{contact.authorized_pickup ? 'Legacy pickup marker: yes' : 'No affirmative marker recorded'}</StatusChip></Record>)}</RecordList></Section>
                  <Section><SectionHead><div><CheckIcon /><div><h3>Legacy profile markers</h3><p>These are not versioned consent evidence; 0029 adds consent authority.</p></div></div></SectionHead><DetailGrid><div><dt>Photo</dt><dd>{detail.photo_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</dd></div><div><dt>Field trip</dt><dd>{detail.field_trip_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</dd></div><div><dt>Emergency medical</dt><dd>{detail.emergency_medical_consent ? 'Recorded yes (legacy marker)' : 'No affirmative marker recorded'}</dd></div></DetailGrid></Section>
                </Detail>
              ) : null}
        </Body>
      </Drawer>
    </Backdrop>,
    document.body,
  );
}

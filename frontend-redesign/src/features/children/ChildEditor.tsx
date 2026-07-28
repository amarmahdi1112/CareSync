import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import {
  ArrowPathIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  HeartIcon,
  HomeModernIcon,
  IdentificationIcon,
  LockClosedIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { commandBoundToJournalOperation } from '../../api/childcareCommand';
import { ActionButton, Eyebrow, StatusChip } from '../../components/ui/Primitives';
import { CHILD_GENDER_OPTIONS, includesDomainValue } from '../../models/domainOptions';
import {
  ChildrenApiError,
  buildChildCreateCommand,
  buildChildUpdateCommand,
  createChild,
  fetchChildDetails,
  fetchChildFamilies,
  updateChild,
  type ChildFamilyOption,
} from './childrenApi';
import {
  ChildcareCommandRecoveredCommitError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
} from '../../childcare-commands/ChildcareCommandRecoveryContext';
import {
  EMPTY_CHILD_EDITOR_VALUES,
  CHILD_EDITOR_FIELD_LIMITS,
  ageGroupFromDateOfBirth,
  childEditorValuesFromDetails,
  childMutationInput,
  validateChildEditor,
  type ChildEditorErrors,
  type ChildEditorValues,
} from './childEditorModel';
import type { ChildListItem } from './childrenModel';
import { currentChildEnrollment } from './enrollmentModel';

export type ChildEditorRequest =
  | { mode: 'create'; familyId?: string }
  | { mode: 'edit'; child: ChildListItem };

interface ChildEditorProps {
  request: ChildEditorRequest;
  organizationId: string;
  onClose: () => void;
  onSaved: (message: string) => void;
  onManageEnrollment?: () => void;
}

type LoadPhase = 'loading' | 'ready' | 'error';

const Backdrop = styled.div`
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
  @media (max-width: 760px) { padding: 0; }
`;

const Dialog = styled.div`
  display: grid;
  width: min(880px, calc(100vw - 48px));
  max-height: calc(100dvh - 48px);
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 20px 8px 20px 8px;
  outline: 0;
  background:
    radial-gradient(circle at 85% 5%, color-mix(in srgb, ${({ theme }) => theme.color.plasma} 8%, transparent), transparent 34%),
    ${({ theme }) => theme.color.surface};
  box-shadow: ${({ theme }) => theme.shadow.panel};

  @media (max-width: 760px) {
    width: 100vw;
    max-height: 100dvh;
    border: 0;
    border-radius: 0;
  }
`;

const DialogHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 {
    margin: 10px 0 5px;
    font-family: 'CareSync Display', ui-rounded, sans-serif;
    font-size: clamp(1.45rem, 3vw, 2rem);
    font-weight: 560;
    letter-spacing: -.055em;
  }

  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.6; }
`;

const CloseButton = styled.button`
  display: grid;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  cursor: pointer;
  &:hover { border-color: ${({ theme }) => theme.color.borderStrong}; color: ${({ theme }) => theme.color.text}; }
  &:disabled { cursor: wait; opacity: .45; }
  svg { width: 19px; }
`;

const Body = styled.div`
  min-height: 0;
  overflow-y: auto;
`;

const CenterState = styled.div`
  display: grid;
  min-height: 65dvh;
  place-items: center;
  padding: 36px 24px;
  text-align: center;

  > div { max-width: 460px; }
  svg { width: 46px; margin: 0 auto 18px; color: ${({ theme }) => theme.color.plasmaBright}; }
  h3 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.18rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.7; }
`;

const StateActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 9px;
  margin-top: 20px;
`;

const FamilyLink = styled(Link)`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid ${({ theme }) => theme.color.plasma};
  border-radius: ${({ theme }) => theme.radius.md};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 86%, ${({ theme }) => theme.color.plasma});
  font-size: .76rem;
  font-weight: 600;
  svg { width: 18px; }
`;

const EditorForm = styled.form`
  display: grid;
  min-height: 100%;
  grid-template-rows: 1fr auto;
`;

const FormContent = styled.fieldset`
  display: grid;
  align-content: start;
  gap: 16px;
  min-width: 0;
  margin: 0;
  padding: 20px 24px 30px;
  border: 0;

  &:disabled { opacity: .72; }

  @media (max-width: 580px) { padding: 16px 14px 26px; }
`;

const Section = styled.section`
  padding: 17px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.radius.lg};
  background: ${({ theme }) => theme.color.surfaceStrong};
`;

const SectionHeader = styled.header`
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 16px;
  svg { width: 20px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .91rem; font-weight: 600; letter-spacing: -.025em; }
  p { margin: 2px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const FieldGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;
  @media (max-width: 580px) { grid-template-columns: 1fr; }
`;

const Field = styled.div<{ $wide?: boolean }>`
  min-width: 0;
  ${({ $wide }) => $wide ? 'grid-column: 1 / -1;' : ''}

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
    font-size: .75rem;
  }

  textarea { min-height: 84px; padding-block: 11px; resize: vertical; line-height: 1.55; }
  select { background: ${({ theme }) => theme.color.surfaceStrong}; }
  input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent); }
  input[aria-invalid='true'], select[aria-invalid='true'], textarea[aria-invalid='true'] { border-color: ${({ theme }) => theme.color.coral}; }
`;

const FieldError = styled.p`
  margin: 6px 2px 0;
  color: ${({ theme }) => theme.color.coral};
  font-size: .72rem;
  line-height: 1.45;
`;
const FieldHint = styled.p`margin: 6px 2px 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.45;`;

const ChoiceGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 470px) { grid-template-columns: 1fr; }
`;

const CheckChoice = styled.label`
  display: flex;
  min-height: 52px;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 13px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  font-size: .75rem;
  input { width: 17px; height: 17px; accent-color: ${({ theme }) => theme.color.plasmaBright}; }
`;

const ErrorSummary = styled.div`
  padding: 13px 14px;
  border: 1px solid ${({ theme }) => theme.color.coral};
  border-radius: 13px;
  outline: 0;
  color: ${({ theme }) => theme.color.coral};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, ${({ theme }) => theme.color.coral});
  font-size: .75rem;
  line-height: 1.55;
  strong { display: block; margin-bottom: 3px; color: ${({ theme }) => theme.color.text}; }
`;
const ArchiveNotice = styled.div`
  display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; padding: 12px; border: 1px solid ${({ theme }) => theme.color.amber}; border-radius: 12px; color: ${({ theme }) => theme.color.textSoft}; background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, ${({ theme }) => theme.color.amber});
  p { margin: 0; font-size: .75rem; line-height: 1.5; } strong { color: ${({ theme }) => theme.color.amber}; }
  @media (max-width: 540px) { align-items: stretch; flex-direction: column; }
`;

const FormFooter = styled.footer`
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 24px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.glass};
  backdrop-filter: blur(${({ theme }) => theme.effect.panelBlur});

  p { max-width: 320px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
  div { display: flex; gap: 9px; }
  @media (max-width: 580px) { align-items: stretch; flex-direction: column; padding: 13px 14px; div { display: grid; grid-template-columns: 1fr 1fr; } }
`;

function errorText(caught: unknown): string {
  if (caught instanceof ChildrenApiError) return caught.message;
  if (caught instanceof Error) return caught.message;
  return 'The child editor could not complete the request.';
}

export default function ChildEditor({
  request,
  organizationId,
  onClose,
  onSaved,
  onManageEnrollment,
}: ChildEditorProps) {
  const commandRecovery = useChildcareCommandRecovery();
  const [phase, setPhase] = useState<LoadPhase>('loading');
  const [families, setFamilies] = useState<ChildFamilyOption[]>([]);
  const [values, setValues] = useState<ChildEditorValues>(EMPTY_CHILD_EDITOR_VALUES);
  const [customGender, setCustomGender] = useState(false);
  const [archiveLocked, setArchiveLocked] = useState(false);
  const [errors, setErrors] = useState<ChildEditorErrors>({});
  const [loadError, setLoadError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pendingRecoveryOperationId, setPendingRecoveryOperationId] = useState<string | null>(null);
  const [baselineVersion, setBaselineVersion] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const saveController = useRef<AbortController | null>(null);
  const childId = request.mode === 'edit' ? request.child.id : null;
  const requestedFamilyId = request.mode === 'create' ? request.familyId || '' : '';

  const allowedFamilyIds = useMemo(() => new Set(families.map((family) => family.id)), [families]);

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
    const controller = new AbortController();
    setPhase('loading');
    setLoadError('');
    setErrors({});
    setSaveError('');
    setPendingRecoveryOperationId(null);
    void (async () => {
      try {
        const nextFamilies = await fetchChildFamilies(organizationId, controller.signal);
        if (controller.signal.aborted) return;
        const familyIds = new Set(nextFamilies.map((family) => family.id));
        let nextValues = {
          ...EMPTY_CHILD_EDITOR_VALUES,
          familyId: familyIds.has(requestedFamilyId)
            ? requestedFamilyId
            : nextFamilies.length === 1 ? nextFamilies[0].id : '',
        };
        let nextArchiveLocked = false;
        if (childId) {
          const details = await fetchChildDetails(childId, familyIds, organizationId, controller.signal);
          nextValues = childEditorValuesFromDetails(details);
          nextArchiveLocked = Boolean(currentChildEnrollment(details.enrollments));
          setBaselineVersion(details.version);
        } else {
          setBaselineVersion(null);
        }
        if (controller.signal.aborted) return;
        setFamilies(nextFamilies);
        setValues(nextValues);
        setArchiveLocked(nextArchiveLocked);
        setCustomGender(Boolean(nextValues.gender && !includesDomainValue(CHILD_GENDER_OPTIONS, nextValues.gender)));
        setPhase('ready');
      } catch (caught) {
        if (controller.signal.aborted) return;
        setLoadError(errorText(caught));
        setPhase('error');
      }
    })();
    return () => controller.abort();
  }, [organizationId, childId, requestedFamilyId, revision]);

  useEffect(() => {
    if (phase !== 'ready') return;
    requestAnimationFrame(() => {
      const target = dialogRef.current?.querySelector<HTMLElement>('[data-autofocus="true"]');
      target?.focus();
    });
  }, [phase]);

  const close = useCallback(() => {
    if (!saving) onClose();
  }, [saving, onClose]);

  const trapFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
    ) || [])].filter((element) => !element.hidden);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const update = <Key extends keyof ChildEditorValues>(field: Key, value: ChildEditorValues[Key]) => {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
    setSaveError('');
  };

  const executeExactCommand = async (
    operationId: string,
    operation: (signal: AbortSignal) => Promise<unknown>,
    successMessage: string,
  ) => {
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    setSaveError('');
    setPendingRecoveryOperationId(operationId);
    try {
      await operation(controller.signal);
      setPendingRecoveryOperationId(null);
      onSaved(successMessage);
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (childcareCommandWasNotPrepared(caught, operationId)) {
        setPendingRecoveryOperationId(null);
      }
      if (caught instanceof ChildcareCommandRecoveredCommitError) {
        setPendingRecoveryOperationId(null);
        onSaved('The interrupted child change was confirmed saved.');
        return;
      }
      const message = errorText(caught);
      setSaveError(message);
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      saveController.current = null;
    }
  };

  useEffect(() => {
    if (saving || !pendingRecoveryOperationId || commandRecovery.lastResolved?.clientOperationId !== pendingRecoveryOperationId) return;
    setPendingRecoveryOperationId(null);
    onSaved('The previously unresolved child change was confirmed saved.');
  }, [commandRecovery.lastResolved, onSaved, pendingRecoveryOperationId, saving]);

  useEffect(() => {
    if (!childcareFinalAbsenceAcknowledged(
      pendingRecoveryOperationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    setPendingRecoveryOperationId(null);
    setSaveError('The server proved this child change was not saved. Review the retained values and choose Save again to create a new operation.');
    requestAnimationFrame(() => errorRef.current?.focus());
  }, [commandRecovery.lastFinalAbsenceAcknowledgedOperationId, pendingRecoveryOperationId]);

  const mutationLocked = childcareMutationControlDisabled(
    commandRecovery.laneBlocked,
    saving,
    Boolean(pendingRecoveryOperationId),
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (mutationLocked) return;
    if (archiveLocked && !values.isActive) {
      setSaveError('End the child’s open enrollment before archiving this record.');
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    const nextErrors = validateChildEditor(values, allowedFamilyIds);
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      setSaveError('Review the highlighted fields before saving.');
      requestAnimationFrame(() => {
        errorRef.current?.focus();
        const firstField = Object.keys(nextErrors)[0];
        document.getElementById(`child-editor-${firstField}`)?.focus();
      });
      return;
    }

    const input = childMutationInput(values);
    if (request.mode === 'create') {
      const command = buildChildCreateCommand(input);
      await executeExactCommand(
        command.clientOperationId,
        (signal) => commandRecovery.execute({
          clientOperationId: command.clientOperationId,
          commandType: 'child.create',
          targetType: 'child',
          expectedTargetId: null,
          expectedActionOwnerId: null,
        }, (operationId) => createChild(
          commandBoundToJournalOperation(command, operationId),
          allowedFamilyIds,
          organizationId,
          signal,
        )),
        `${input.first_name} ${input.last_name} was added.`,
      );
    } else {
      if (!baselineVersion) {
        setSaveError('Reload this child before saving; its record version is unavailable.');
        return;
      }
      const command = buildChildUpdateCommand(input, baselineVersion);
      await executeExactCommand(
        command.clientOperationId,
        (signal) => commandRecovery.execute({
          clientOperationId: command.clientOperationId,
          commandType: 'child.update',
          targetType: 'child',
          expectedTargetId: request.child.id,
          expectedActionOwnerId: null,
        }, (operationId) => updateChild(
          request.child.id,
          commandBoundToJournalOperation(command, operationId),
          allowedFamilyIds,
          organizationId,
          signal,
        )),
        `${input.first_name} ${input.last_name} was updated.`,
      );
    }
  };

  const title = request.mode === 'create' ? 'Add a child record' : `Edit ${request.child.fullName}`;
  const derivedAgeGroup = ageGroupFromDateOfBirth(values.dateOfBirth);
  const genderUsesCustomValue = customGender || Boolean(values.gender && !includesDomainValue(CHILD_GENDER_OPTIONS, values.gender));

  return createPortal(
    <Backdrop onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <Dialog
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="child-editor-title"
        aria-describedby="child-editor-description"
        onKeyDown={trapFocus}
      >
        <DialogHeader>
          <div>
            <Eyebrow><LockClosedIcon width={14} /> Verified organization write</Eyebrow>
            <h2 id="child-editor-title">{title}</h2>
            <p id="child-editor-description">Changes are saved through the organization-scoped children service.</p>
          </div>
          <CloseButton type="button" onClick={close} disabled={saving} aria-label="Close child editor"><XMarkIcon /></CloseButton>
        </DialogHeader>

        <Body>
          {phase === 'loading' ? (
            <CenterState aria-live="polite" aria-busy="true"><div><ArrowPathIcon /><h3>Verifying families and child data</h3><p>The editor stays locked until the organization-scoped records are confirmed.</p></div></CenterState>
          ) : phase === 'error' ? (
            <CenterState role="alert"><div><ExclamationTriangleIcon /><h3>The editor could not open safely</h3><p>{loadError}</p><StateActions><ActionButton $variant="primary" onClick={() => setRevision((value) => value + 1)}><ArrowPathIcon /> Retry</ActionButton><ActionButton onClick={close}>Cancel</ActionButton></StateActions></div></CenterState>
          ) : families.length === 0 ? (
            <CenterState><div><HomeModernIcon /><h3>A family is required first</h3><p>No family records are available inside this organization. A child cannot be saved without a valid family relationship.</p><StateActions><FamilyLink to="/families" onClick={close}><HomeModernIcon /> Open families</FamilyLink><ActionButton onClick={close}>Cancel</ActionButton></StateActions></div></CenterState>
          ) : (
            <EditorForm onSubmit={submit} noValidate>
              <FormContent disabled={mutationLocked}>
                {saveError && <ErrorSummary ref={errorRef} tabIndex={-1} role="alert"><strong>{pendingRecoveryOperationId ? 'The saved result needs review' : 'The record was not saved'}</strong>{saveError}</ErrorSummary>}

                <Section aria-labelledby="child-identity-heading">
                  <SectionHeader><IdentificationIcon /><div><h3 id="child-identity-heading">Identity and enrollment</h3><p>Required child and family relationship fields</p></div></SectionHeader>
                  <FieldGrid>
                    <Field $wide>
                      <label htmlFor="child-editor-familyId">Family *</label>
                      <select id="child-editor-familyId" data-autofocus="true" value={values.familyId} onChange={(event) => update('familyId', event.target.value)} aria-invalid={Boolean(errors.familyId)} aria-describedby={errors.familyId ? 'child-editor-familyId-error' : undefined}>
                        <option value="">Select a verified family</option>
                        {families.map((family) => <option key={family.id} value={family.id}>{family.name} · {family.status}</option>)}
                      </select>
                      {errors.familyId && <FieldError id="child-editor-familyId-error">{errors.familyId}</FieldError>}
                    </Field>
                    <Field><label htmlFor="child-editor-firstName">First name *</label><input id="child-editor-firstName" value={values.firstName} onChange={(event) => update('firstName', event.target.value)} maxLength={CHILD_EDITOR_FIELD_LIMITS.firstName} autoComplete="off" aria-invalid={Boolean(errors.firstName)} aria-describedby={errors.firstName ? 'child-editor-firstName-error' : undefined} />{errors.firstName && <FieldError id="child-editor-firstName-error">{errors.firstName}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-middleName">Middle name</label><input id="child-editor-middleName" value={values.middleName} onChange={(event) => update('middleName', event.target.value)} maxLength={CHILD_EDITOR_FIELD_LIMITS.middleName} autoComplete="off" aria-invalid={Boolean(errors.middleName)} />{errors.middleName && <FieldError>{errors.middleName}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-lastName">Last name *</label><input id="child-editor-lastName" value={values.lastName} onChange={(event) => update('lastName', event.target.value)} maxLength={CHILD_EDITOR_FIELD_LIMITS.lastName} autoComplete="off" aria-invalid={Boolean(errors.lastName)} aria-describedby={errors.lastName ? 'child-editor-lastName-error' : undefined} />{errors.lastName && <FieldError id="child-editor-lastName-error">{errors.lastName}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-dateOfBirth">Date of birth *</label><input id="child-editor-dateOfBirth" type="date" value={values.dateOfBirth} onChange={(event) => update('dateOfBirth', event.target.value)} aria-invalid={Boolean(errors.dateOfBirth)} aria-describedby={errors.dateOfBirth ? 'child-editor-dateOfBirth-error' : undefined} />{errors.dateOfBirth && <FieldError id="child-editor-dateOfBirth-error">{errors.dateOfBirth}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-gender">Gender</label><select id="child-editor-gender" value={genderUsesCustomValue ? '__other__' : values.gender} onChange={(event) => { if (event.target.value === '__other__') { setCustomGender(true); update('gender', ''); } else { setCustomGender(false); update('gender', event.target.value); } }} aria-invalid={Boolean(errors.gender)}><option value="">Not recorded</option>{CHILD_GENDER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}<option value="__other__">Other / self-described</option></select>{genderUsesCustomValue && <><label htmlFor="child-editor-gender-custom">Self-described gender</label><input id="child-editor-gender-custom" value={values.gender} onChange={(event) => update('gender', event.target.value)} maxLength={20} aria-invalid={Boolean(errors.gender)} /></>}{errors.gender && <FieldError>{errors.gender}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-ageGroup">Age group</label><input id="child-editor-ageGroup" value={derivedAgeGroup} readOnly aria-readonly="true" placeholder="Derived after date of birth" /><FieldHint>System-managed from date of birth.{values.ageGroup && values.ageGroup !== derivedAgeGroup ? ` Previously saved as “${values.ageGroup}”.` : ''}</FieldHint></Field>
                  </FieldGrid>
                </Section>

                <Section aria-labelledby="child-care-heading">
                  <SectionHeader><HomeModernIcon /><div><h3 id="child-care-heading">Enrollment status</h3><p>Archive a child by turning off the active record</p></div></SectionHeader>
                  <ChoiceGrid><CheckChoice title={archiveLocked ? 'End the open enrollment before archiving this child.' : undefined}><input type="checkbox" checked={values.isActive} disabled={archiveLocked} onChange={(event) => update('isActive', event.target.checked)} /> Active child record (turn off to archive)</CheckChoice></ChoiceGrid>
                  {archiveLocked && <ArchiveNotice><p><strong>End enrollment first.</strong><br />This child has a pending, active, or paused enrollment. Open Manage enrollment, choose a final day, then return here to archive the child safely.</p><ActionButton type="button" onClick={onManageEnrollment || close}>Manage enrollment</ActionButton></ArchiveNotice>}
                </Section>

                <Section aria-labelledby="child-health-heading">
                  <SectionHeader><HeartIcon /><div><h3 id="child-health-heading">Health record</h3><p>Optional fields already supported by the children table</p></div></SectionHeader>
                  <FieldGrid>
                    <Field><label htmlFor="child-editor-healthCareNumber">Health care number</label><input id="child-editor-healthCareNumber" value={values.healthCareNumber} onChange={(event) => update('healthCareNumber', event.target.value)} maxLength={100} aria-invalid={Boolean(errors.healthCareNumber)} />{errors.healthCareNumber && <FieldError>{errors.healthCareNumber}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-immunization">Immunization status</label><select id="child-editor-immunization" value={values.immunization} onChange={(event) => update('immunization', event.target.value as ChildEditorValues['immunization'])}><option value="unknown">Not recorded</option><option value="yes">Up to date</option><option value="no">Not up to date</option></select></Field>
                    <Field><label htmlFor="child-editor-doctorName">Doctor name</label><input id="child-editor-doctorName" value={values.doctorName} onChange={(event) => update('doctorName', event.target.value)} maxLength={255} aria-invalid={Boolean(errors.doctorName)} />{errors.doctorName && <FieldError>{errors.doctorName}</FieldError>}</Field>
                    <Field><label htmlFor="child-editor-doctorPhone">Doctor phone</label><input id="child-editor-doctorPhone" type="tel" value={values.doctorPhone} onChange={(event) => update('doctorPhone', event.target.value)} maxLength={CHILD_EDITOR_FIELD_LIMITS.doctorPhone} aria-invalid={Boolean(errors.doctorPhone)} />{errors.doctorPhone && <FieldError>{errors.doctorPhone}</FieldError>}</Field>
                    <Field $wide><label htmlFor="child-editor-allergies">Allergies</label><textarea id="child-editor-allergies" value={values.allergies} onChange={(event) => update('allergies', event.target.value)} /></Field>
                    <Field $wide><label htmlFor="child-editor-medicalConditions">Medical conditions</label><textarea id="child-editor-medicalConditions" value={values.medicalConditions} onChange={(event) => update('medicalConditions', event.target.value)} /></Field>
                    <Field $wide><label htmlFor="child-editor-medications">Medications</label><textarea id="child-editor-medications" value={values.medications} onChange={(event) => update('medications', event.target.value)} /></Field>
                  </FieldGrid>
                </Section>
              </FormContent>

              <FormFooter>
                <p>{pendingRecoveryOperationId ? 'The form stays in memory while CareSync checks the receipt. It will not resend the operation.' : 'Only Basic child fields and verified family IDs are submitted. A failed request leaves this form open.'}</p>
                <div><ActionButton type="button" onClick={close} disabled={saving}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={mutationLocked}>{saving ? <><ArrowPathIcon /> Saving…</> : <><CheckIcon /> {request.mode === 'create' ? 'Add child' : 'Save changes'}</>}</ActionButton></div>
              </FormFooter>
            </EditorForm>
          )}
        </Body>
      </Dialog>
    </Backdrop>,
    document.body,
  );
}

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
  BuildingOffice2Icon,
  CalendarDaysIcon,
  ExclamationTriangleIcon,
  MapPinIcon,
  ShieldCheckIcon,
  StopCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { commandBoundToJournalOperation } from '../../api/childcareCommand';
import { ActionButton, Eyebrow, StatusChip } from '../../components/ui/Primitives';
import {
  ChildrenApiError,
  buildEnrollmentCreateCommand,
  buildEnrollmentEndCommand,
  createChildEnrollment,
  endChildEnrollment,
  type ApiChildProfile,
  type ChildProfileEnrollment,
  type EnrollmentFacilityOption,
} from './childrenApi';
import {
  enrollmentCreateInput,
  enrollmentValues,
  facilityIsoDate,
  validateEnrollmentCreate,
  validateEnrollmentEnd,
  type EnrollmentEditorErrors,
  type EnrollmentEditorValues,
} from './enrollmentModel';
import type { ChildListItem } from './childrenModel';
import { loadEnrollmentEditorData } from './enrollmentEditorData';
import {
  ChildcareCommandRecoveredCommitError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
} from '../../childcare-commands/ChildcareCommandRecoveryContext';

interface EnrollmentEditorProps {
  child: ChildListItem;
  organizationId: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}

type Phase = 'loading' | 'ready' | 'error';

const Backdrop = styled.div`
  position: fixed;
  z-index: 1220;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
  @media (max-width: 720px) { padding: 0; }
`;

const Drawer = styled.div`
  display: grid;
  width: min(820px, calc(100vw - 48px));
  max-height: calc(100dvh - 48px);
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 20px 8px 20px 8px;
  outline: 0;
  background:
    radial-gradient(circle at 84% 4%, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 7%, transparent), transparent 32%),
    ${({ theme }) => theme.color.surface};
  box-shadow: ${({ theme }) => theme.shadow.panel};

  @media (max-width: 720px) { width: 100vw; max-height: 100dvh; border: 0; border-radius: 0; }
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 { margin: 10px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.45rem, 3vw, 2rem); font-weight: 560; letter-spacing: -.055em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.6; }
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
  background: ${({ theme }) => theme.color.surfaceStrong};
  cursor: pointer;
  &:hover { border-color: ${({ theme }) => theme.color.borderStrong}; color: ${({ theme }) => theme.color.text}; }
  &:disabled { cursor: wait; opacity: .45; }
  svg { width: 19px; }
`;

const Body = styled.div`min-height: 0; overflow-y: auto;`;

const Center = styled.div`
  display: grid;
  min-height: 68dvh;
  place-items: center;
  padding: 36px 24px;
  text-align: center;
  > div { max-width: 490px; }
  svg { width: 46px; margin: 0 auto 17px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.2rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.7; }
`;

const Form = styled.form`display: grid; min-height: 100%; grid-template-rows: 1fr auto;`;
const Content = styled.fieldset`display: grid; min-width: 0; align-content: start; gap: 16px; margin: 0; padding: 20px 24px 30px; border: 0; &:disabled { opacity: .72; } @media (max-width: 580px) { padding: 16px 14px 26px; }`;
const Section = styled.section`padding: 17px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: ${({ theme }) => theme.radius.lg}; background: ${({ theme }) => theme.color.surfaceStrong};`;

const SectionHead = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  > div { display: flex; align-items: flex-start; gap: 10px; }
  svg { width: 20px; flex: 0 0 auto; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .92rem; font-weight: 600; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
`;

const Grid = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; @media (max-width: 580px) { grid-template-columns: 1fr; }`;

const Field = styled.div<{ $wide?: boolean }>`
  min-width: 0;
  ${({ $wide }) => $wide ? 'grid-column: 1 / -1;' : ''}
  label { display: block; margin: 0 0 6px 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; }
  input, select { width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 12px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .75rem; }
  input:focus, select:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent); }
  [aria-invalid='true'] { border-color: ${({ theme }) => theme.color.coral}; }
  input:disabled, select:disabled { cursor: not-allowed; opacity: .62; }
`;

const FieldError = styled.p`margin: 6px 2px 0; color: ${({ theme }) => theme.color.coral}; font-size: .72rem; line-height: 1.45;`;

const Notice = styled.div<{ $tone?: 'warning' | 'info' }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 13px 14px;
  border: 1px solid ${({ $tone, theme }) => $tone === 'warning' ? theme.color.amber : theme.color.cyan};
  border-radius: 13px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $tone, theme }) => $tone === 'warning'
    ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.amber})`
    : `color-mix(in srgb, ${theme.color.surfaceStrong} 90%, ${theme.color.cyan})`};
  font-size: .75rem;
  line-height: 1.6;
  svg { width: 18px; flex: 0 0 auto; color: ${({ $tone, theme }) => $tone === 'warning' ? theme.color.amber : theme.color.cyan}; }
`;

const ErrorBox = styled.div`
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

const EmptyOptions = styled.div`
  padding: 16px;
  border: 1px dashed ${({ theme }) => theme.color.borderStrong};
  border-radius: 13px;
  text-align: center;
  p { margin: 0 0 12px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.6; }
  a { display: inline-flex; min-height: 44px; align-items: center; gap: 8px; padding: 0 13px; border: 1px solid ${({ theme }) => theme.color.cyan}; border-radius: 11px; color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.control}; font-size: .75rem; font-weight: 600; }
  svg { width: 17px; }
`;

const History = styled.div`display: grid; gap: 8px;`;
const HistoryRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  background: ${({ theme }) => theme.color.surface};
  strong { display: block; font-size: .75rem; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
`;

const EndPanel = styled.div`
  display: grid;
  gap: 13px;
  margin-top: 13px;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.amber};
  border-radius: 13px;
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, ${({ theme }) => theme.color.amber});
  p { margin: 0; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; line-height: 1.6; }
`;

const Actions = styled.div`display: flex; flex-wrap: wrap; gap: 9px;`;

const Footer = styled.footer`
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
  p { max-width: 370px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
  div { display: flex; gap: 9px; }
  @media (max-width: 580px) { align-items: stretch; flex-direction: column; padding: 13px 14px; div { display: grid; grid-template-columns: 1fr 1fr; } }
`;

function requestMessage(caught: unknown): string {
  if (caught instanceof ChildrenApiError) return caught.message;
  return caught instanceof Error ? caught.message : 'The enrollment request could not be completed.';
}

function enrollmentTone(status: string): 'success' | 'warning' | 'neutral' {
  if (status === 'active') return 'success';
  if (status === 'pending' || status === 'paused') return 'warning';
  return 'neutral';
}

export default function EnrollmentEditor({ child, organizationId, onClose, onSaved }: EnrollmentEditorProps) {
  const commandRecovery = useChildcareCommandRecovery();
  const [profile, setProfile] = useState<ApiChildProfile | null>(null);
  const currentEnrollment = profile?.current_enrollment || null;
  const placementApprovalAvailable = Boolean(
    currentEnrollment
    && currentEnrollment.status !== 'ended'
    && !currentEnrollment.program_id
    && !currentEnrollment.room_id,
  );
  const [phase, setPhase] = useState<Phase>('loading');
  const [facilities, setFacilities] = useState<EnrollmentFacilityOption[]>([]);
  const [values, setValues] = useState<EnrollmentEditorValues>(() => enrollmentValues(null));
  const [errors, setErrors] = useState<EnrollmentEditorErrors>({});
  const [requestError, setRequestError] = useState('');
  const [endDate, setEndDate] = useState('');
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingRecoveryOperationId, setPendingRecoveryOperationId] = useState<string | null>(null);
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
    const controller = new AbortController();
    setPhase('loading');
    setRequestError('');
    setProfile(null);
    setFacilities([]);
    setValues(enrollmentValues(null));
    setEndDate('');
    setConfirmEnd(false);
    loadEnrollmentEditorData(child.id, organizationId, controller.signal)
      .then(({ facilities: records, profile: canonicalProfile }) => {
        if (controller.signal.aborted) return;
        const canonicalEnrollment = canonicalProfile.current_enrollment;
        setFacilities(records);
        setProfile(canonicalProfile);
        setValues({
          ...enrollmentValues(canonicalEnrollment),
          facilityId: canonicalEnrollment?.facility_id || records.find((record) => record.status === 'active')?.id || '',
        });
        setPhase('ready');
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setRequestError(requestMessage(caught));
        setPhase('error');
      });
    return () => controller.abort();
  }, [child.id, organizationId, revision]);

  useEffect(() => {
    if (phase !== 'ready') return;
    requestAnimationFrame(() => {
      const target = drawerRef.current?.querySelector<HTMLElement>('[data-autofocus="true"]:not(:disabled)')
        || drawerRef.current?.querySelector<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]');
      target?.focus();
    });
  }, [phase]);

  const close = useCallback(() => { if (!saving) onClose(); }, [saving, onClose]);
  const trapFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;
    const focusable = [...(drawerRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]') || [])];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };

  const selectedFacilityIsActive = facilities.some((facility) => facility.id === values.facilityId && facility.status === 'active');
  const currentFacility = facilities.find((facility) => facility.id === currentEnrollment?.facility_id) || null;
  const currentDate = useMemo(
    () => currentFacility ? facilityIsoDate(currentFacility.timezone) : '',
    [currentFacility],
  );
  const canEndAsOfCurrentDate = Boolean(
    currentEnrollment && currentDate && currentEnrollment.start_date.slice(0, 10) <= currentDate,
  );

  useEffect(() => {
    if (currentDate) setEndDate((value) => value || currentDate);
  }, [currentDate]);

  const failValidation = (nextErrors: EnrollmentEditorErrors, message = 'Review the highlighted enrollment fields before saving.') => {
    setErrors(nextErrors);
    setRequestError(message);
    requestAnimationFrame(() => errorRef.current?.focus());
  };

  const executeExactCommand = async (
    operationId: string,
    operation: (signal: AbortSignal) => Promise<unknown>,
    successMessage: string,
  ) => {
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    setRequestError('');
    setErrors({});
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
        onSaved('The interrupted enrollment change was confirmed saved.');
        return;
      }
      setRequestError(requestMessage(caught));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      saveController.current = null;
    }
  };

  useEffect(() => {
    if (saving || !pendingRecoveryOperationId || commandRecovery.lastResolved?.clientOperationId !== pendingRecoveryOperationId) return;
    setPendingRecoveryOperationId(null);
    onSaved('The previously unresolved enrollment change was confirmed saved.');
  }, [commandRecovery.lastResolved, onSaved, pendingRecoveryOperationId, saving]);

  useEffect(() => {
    if (!childcareFinalAbsenceAcknowledged(
      pendingRecoveryOperationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    setPendingRecoveryOperationId(null);
    setRequestError('The server proved this enrollment change was not saved. Review the retained values and choose the action again to create a new operation.');
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
    if (currentEnrollment) {
      failValidation({}, placementApprovalAvailable
        ? 'Open the approval-first placement review to choose from the server-authored DOB and capacity recommendations.'
        : 'Saved placements cannot be overwritten here. Use the future effective-dated transfer workflow when available.');
      return;
    }
    const nextErrors = validateEnrollmentCreate(values, facilities);
    if (Object.keys(nextErrors).length) { failValidation(nextErrors); return; }
    const command = buildEnrollmentCreateCommand(enrollmentCreateInput(values));
    await executeExactCommand(
      command.clientOperationId,
      (signal) => commandRecovery.execute({
        clientOperationId: command.clientOperationId,
        commandType: 'enrollment.create',
        targetType: 'enrollment',
        expectedTargetId: null,
        expectedActionOwnerId: child.id,
      }, (operationId) => createChildEnrollment(
        child.id,
        organizationId,
        commandBoundToJournalOperation(command, operationId),
        facilities,
        signal,
      )),
      `${child.fullName}'s pending enrollment was created. Approve a compatible room from placement review.`,
    );
  };

  const endEnrollment = async () => {
    if (!currentEnrollment || mutationLocked) return;
    const nextErrors = validateEnrollmentEnd(endDate, currentEnrollment, currentDate);
    if (Object.keys(nextErrors).length) { failValidation(nextErrors, nextErrors.endDate); return; }
    const command = buildEnrollmentEndCommand(endDate, currentEnrollment.version);
    await executeExactCommand(
      command.clientOperationId,
      (signal) => commandRecovery.execute({
        clientOperationId: command.clientOperationId,
        commandType: 'enrollment.update',
        targetType: 'enrollment',
        expectedTargetId: currentEnrollment.id,
        expectedActionOwnerId: child.id,
      }, (operationId) => endChildEnrollment(
        currentEnrollment,
        organizationId,
        commandBoundToJournalOperation(command, operationId),
        signal,
      )),
      `${child.fullName}'s enrollment ended on ${endDate}.`,
    );
  };

  const changeFacility = (facilityId: string) => {
    setErrors({});
    setValues((current) => ({ ...current, facilityId, programId: '', roomId: '' }));
  };

  const enrollmentLocation = (enrollment: ChildProfileEnrollment): string => {
    return [
      enrollment.facility_name,
      enrollment.program_name || 'No program assigned',
      enrollment.room_name || 'No room assigned',
    ].join(' · ');
  };

  const title = currentEnrollment ? 'Manage enrollment' : 'Create enrollment';

  return createPortal(
    <Backdrop onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <Drawer ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="enrollment-editor-title" aria-describedby="enrollment-editor-description" onKeyDown={trapFocus}>
        <Header>
          <div>
            <Eyebrow><ShieldCheckIcon width={14} /> Verified organization enrollment</Eyebrow>
            <h2 id="enrollment-editor-title">{title}</h2>
            <p id="enrollment-editor-description">{profile ? `${profile.first_name} ${profile.last_name} · ${profile.family.name}` : `${child.fullName} · ${child.familyName}`}</p>
          </div>
          <Close type="button" onClick={close} disabled={saving} aria-label="Close enrollment panel"><XMarkIcon /></Close>
        </Header>
        <Body>
          {phase === 'loading' ? (
            <Center aria-busy="true"><div><ArrowPathIcon /><h3>Loading canonical enrollment data</h3><p>CareSync is checking the child profile, full enrollment history, and organization facilities.</p></div></Center>
          ) : phase === 'error' ? (
            <Center role="alert"><div><ExclamationTriangleIcon /><h3>Enrollment could not open</h3><p>{requestError}</p><Actions style={{ justifyContent: 'center', marginTop: 20 }}><ActionButton $variant="primary" onClick={() => setRevision((value) => value + 1)}><ArrowPathIcon /> Retry</ActionButton><ActionButton onClick={close}>Cancel</ActionButton></Actions></div></Center>
          ) : (
            <Form onSubmit={submit} noValidate>
              <Content disabled={mutationLocked}>
                {requestError && <ErrorBox ref={errorRef} tabIndex={-1} role="alert"><strong>{pendingRecoveryOperationId ? 'The saved result needs review' : 'The enrollment was not saved'}</strong>{requestError}</ErrorBox>}

                {currentEnrollment && (
                  <Notice>
                    <ShieldCheckIcon />
                    <span>{placementApprovalAvailable ? 'This open enrollment is unassigned. Placement must use the server-authored DOB, facility-date, capacity, and version review.' : 'This saved placement is read-only here. CareSync does not overwrite placement history; end the enrollment before changing facilities.'}</span>
                  </Notice>
                )}

                {currentEnrollment && !selectedFacilityIsActive && (
                  <Notice $tone="warning"><ExclamationTriangleIcon /><span>The current facility is no longer active, so placement changes are locked. You can still end this enrollment safely below.</span></Notice>
                )}

                <Section>
                  <SectionHead>
                    <div><BuildingOffice2Icon /><div><h3>Placement</h3><p>Only active choices returned for this organization are available.</p></div></div>
                    {currentEnrollment && <StatusChip $tone={enrollmentTone(currentEnrollment.status)}>{currentEnrollment.status}</StatusChip>}
                  </SectionHead>

                  {!currentEnrollment && facilities.length === 0 ? (
                    <EmptyOptions><p>No active facilities are available yet. Add and activate a facility before enrolling this child.</p><Link to="/rooms" onClick={close}><BuildingOffice2Icon /> Open rooms & programs</Link></EmptyOptions>
                  ) : (
                    <Grid>
                      <Field $wide>
                        <label htmlFor="enrollment-facility">Facility *</label>
                        <select
                          id="enrollment-facility"
                          data-autofocus="true"
                          value={values.facilityId}
                          onChange={(event) => changeFacility(event.target.value)}
                          disabled={Boolean(currentEnrollment) || saving}
                          aria-invalid={Boolean(errors.facilityId)}
                          aria-describedby={errors.facilityId ? 'enrollment-facility-error' : undefined}
                        >
                          <option value="">Select a facility</option>
                          {currentEnrollment && !selectedFacilityIsActive && <option value={currentEnrollment.facility_id}>Current inactive facility · {currentEnrollment.facility_id.slice(0, 8)}</option>}
                          {facilities.filter((facility) => facility.status === 'active').map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
                        </select>
                        {errors.facilityId && <FieldError id="enrollment-facility-error">{errors.facilityId}</FieldError>}
                      </Field>

                      <Field $wide>
                        <label htmlFor="enrollment-start-date">First day of care *</label>
                        <input id="enrollment-start-date" type="date" value={values.startDate} onChange={(event) => setValues((current) => ({ ...current, startDate: event.target.value }))} disabled={Boolean(currentEnrollment) || saving} aria-invalid={Boolean(errors.startDate)} aria-describedby={errors.startDate ? 'enrollment-start-error' : undefined} />
                        {errors.startDate && <FieldError id="enrollment-start-error">{errors.startDate}</FieldError>}
                      </Field>
                    </Grid>
                  )}

                  {placementApprovalAvailable && currentEnrollment && <EmptyOptions style={{ marginTop: 13 }}><p>Program, room, effective date, DOB eligibility, and interval capacity are owned by placement review—not this generic enrollment editor.</p><Link to={`/rooms?facility_id=${encodeURIComponent(currentEnrollment.facility_id)}&placement_enrollment_id=${encodeURIComponent(currentEnrollment.id)}`} onClick={close}><BuildingOffice2Icon /> Open exact placement review</Link></EmptyOptions>}
                  {!currentEnrollment && selectedFacilityIsActive && <Notice style={{ marginTop: 13 }}><ShieldCheckIcon /><span>Creation saves a pending, unassigned enrollment. Room approval is a separate reviewed command.</span></Notice>}
                </Section>

                {currentEnrollment && (
                  <Section>
                    <SectionHead><div><StopCircleIcon /><div><h3>End enrollment now or as of a past date</h3><p>Future scheduled departures require a separate effective-dated workflow.</p></div></div></SectionHead>
                    {!canEndAsOfCurrentDate ? (
                      <Notice $tone="warning"><ExclamationTriangleIcon /><span>This enrollment starts in the future, so it cannot be ended as of today. Use the future cancellation workflow when it is available.</span></Notice>
                    ) : !confirmEnd ? (
                      <ActionButton type="button" onClick={() => setConfirmEnd(true)} disabled={saving}><StopCircleIcon /> End enrollment</ActionButton>
                    ) : (
                      <EndPanel>
                        <p>Choose today or a past final day of care. This command cannot schedule a future departure.</p>
                        <Field>
                          <label htmlFor="enrollment-end-date">Final day of care *</label>
                          <input id="enrollment-end-date" type="date" min={currentEnrollment.start_date.slice(0, 10)} max={currentDate} value={endDate} onChange={(event) => setEndDate(event.target.value)} disabled={saving} aria-invalid={Boolean(errors.endDate)} aria-describedby={errors.endDate ? 'enrollment-end-error' : undefined} />
                          {errors.endDate && <FieldError id="enrollment-end-error">{errors.endDate}</FieldError>}
                        </Field>
                        <Actions><ActionButton type="button" onClick={() => { setConfirmEnd(false); setErrors((current) => ({ ...current, endDate: undefined })); }} disabled={saving}>Keep enrollment</ActionButton><ActionButton type="button" $variant="primary" onClick={endEnrollment} disabled={mutationLocked}>{saving ? <><ArrowPathIcon /> Ending…</> : <><StopCircleIcon /> Confirm final day</>}</ActionButton></Actions>
                      </EndPanel>
                    )}
                  </Section>
                )}

                {profile && profile.enrollments.length > 0 && (
                  <Section>
                    <SectionHead><div><CalendarDaysIcon /><div><h3>Enrollment history</h3><p>{profile.enrollments.length} saved {profile.enrollments.length === 1 ? 'record' : 'records'}</p></div></div></SectionHead>
                    <History>{profile.enrollments.map((enrollment) => (
                      <HistoryRow key={enrollment.id}>
                        <div><strong>{enrollment.start_date.slice(0, 10)}{enrollment.end_date ? ` — ${enrollment.end_date.slice(0, 10)}` : ' — present'}</strong><small>{enrollmentLocation(enrollment)}</small></div>
                        <StatusChip $tone={enrollmentTone(enrollment.status)}>{enrollment.status}</StatusChip>
                      </HistoryRow>
                    ))}</History>
                  </Section>
                )}
              </Content>
              <Footer>
                <p>{pendingRecoveryOperationId ? 'The form stays in memory while CareSync checks the receipt. It will not resend the operation.' : placementApprovalAvailable ? 'Open the targeted approval-first workflow; no loose placement command is available here.' : currentEnrollment ? 'Saved placement is preserved; lifecycle controls remain available below.' : 'Enrollment creation records facility and start date only; no room is assigned automatically.'}</p>
                <div><ActionButton type="button" onClick={close} disabled={saving}>{currentEnrollment ? 'Close' : 'Cancel'}</ActionButton>{!currentEnrollment && <ActionButton type="submit" $variant="primary" disabled={mutationLocked || !selectedFacilityIsActive}>{saving ? <><ArrowPathIcon /> Saving…</> : <><MapPinIcon /> Create pending enrollment</>}</ActionButton>}</div>
              </Footer>
            </Form>
          )}
        </Body>
      </Drawer>
    </Backdrop>,
    document.body,
  );
}

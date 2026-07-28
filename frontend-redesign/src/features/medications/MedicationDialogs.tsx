import { useEffect, useState, type FormEvent } from 'react';
import {
  ArrowPathIcon,
  BeakerIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PlusIcon,
  ShieldCheckIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { ActionButton, Eyebrow, IconButton } from '../../components/ui/Primitives';
import { facilityDateTimeInputValue, facilityDateTimeToIso } from '../daily-care/careModel';
import {
  OperationDialog,
  OperationDialogActions,
  OperationDialogHeader,
  OperationForm,
  OperationFormGrid,
} from '../safety-operations/OperationDialog';
import { OperationField, OperationNotice } from '../safety-operations/OperationStyles';
import {
  createMedicationOperationId,
  fetchMedicationAdministrationHistory,
  fetchMedicationPlanHistory,
  type MedicationAdministration,
  type MedicationAdministrationEvent,
  type MedicationGuardianOption,
  type MedicationKind,
  type MedicationOutcome,
  type MedicationPlan,
  type MedicationPlanEvent,
  type MedicationRoute,
  type MedicationStorageMethod,
} from './medicationApi';
import { formatCareTime } from '../daily-care/careModel';

const CheckField = styled.label`
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
  min-height: 44px;
  padding: 10px 11px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  font-size: .73rem;
  line-height: 1.5;

  input { width: 20px; height: 20px; accent-color: ${({ theme }) => theme.color.cyan}; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; }
`;

const ScheduleList = styled.div`
  display: grid;
  gap: 7px;
  grid-column: 1 / -1;

  > span { color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; }
`;

const ScheduleRow = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px;
  gap: 7px;

  input { width: 100%; min-height: 44px; padding: 0 11px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; }
`;

export interface MedicationPlanDraft {
  medicationName: string;
  dosage: string;
  route: MedicationRoute;
  labelDirections: string;
  scheduledTimes: string[];
  asNeeded: boolean;
  startDate: string;
  endDate: string | null;
  medicationKind: MedicationKind;
  storageMethod: MedicationStorageMethod;
  storageInstructions: string;
  emergencyPlanReference: string | null;
  reason: string | null;
  clientOperationId: string;
}

export function MedicationPlanDialog({
  childName,
  serviceDate,
  plan,
  busy,
  onClose,
  onSave,
}: {
  childName: string;
  serviceDate: string;
  plan?: MedicationPlan;
  busy: boolean;
  onClose: () => void;
  onSave: (draft: MedicationPlanDraft) => Promise<void>;
}) {
  const [medicationName, setMedicationName] = useState(plan?.medication_name || '');
  const [dosage, setDosage] = useState(plan?.dosage || '');
  const [route, setRoute] = useState<MedicationRoute>(plan?.route || 'oral');
  const [labelDirections, setLabelDirections] = useState(plan?.label_directions || '');
  const [scheduledTimes, setScheduledTimes] = useState<string[]>(plan?.scheduled_times.length ? plan.scheduled_times : ['']);
  const [asNeeded, setAsNeeded] = useState(plan?.as_needed || false);
  const [startDate, setStartDate] = useState(plan?.start_date || serviceDate);
  const [endDate, setEndDate] = useState(plan?.end_date || '');
  const [medicationKind, setMedicationKind] = useState<MedicationKind>(plan?.medication_kind || 'non_emergency');
  const [storageInstructions, setStorageInstructions] = useState(plan?.storage_instructions || '');
  const [emergencyReference, setEmergencyReference] = useState(plan?.emergency_plan_reference || '');
  const [reason, setReason] = useState('');
  const [clientOperationId] = useState(createMedicationOperationId);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      const schedule = [...new Set(scheduledTimes.filter(Boolean))].sort();
      if (!asNeeded && schedule.length === 0) throw new Error('Add at least one labelled schedule time, or mark the plan as as-needed.');
      if (endDate && endDate < startDate) throw new Error('The end date cannot be before the start date.');
      if (medicationKind === 'emergency' && emergencyReference.trim().length < 3) throw new Error('Record the agreed emergency-plan reference before saving an emergency medication plan.');
      await onSave({
        medicationName: medicationName.trim(), dosage: dosage.trim(), route, labelDirections: labelDirections.trim(),
        scheduledTimes: schedule, asNeeded, startDate, endDate: endDate || null, medicationKind,
        storageMethod: medicationKind === 'emergency' ? 'emergency_accessible_per_plan' : 'locked_inaccessible',
        storageInstructions: storageInstructions.trim(), emergencyPlanReference: medicationKind === 'emergency' ? emergencyReference.trim() : null,
        reason: plan ? reason.trim() : null,
        clientOperationId,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The medication plan could not be saved.');
    }
  };

  return (
    <OperationDialog busy={busy} onClose={onClose} labelId="medication-plan-title">
      <OperationDialogHeader><div><Eyebrow><BeakerIcon width={14} /> Medication plan transcription</Eyebrow><h2 id="medication-plan-title">{plan ? 'Edit' : 'Create'} internal medication plan.</h2><p>{childName} · Transcribe signed consent and original label facts; CareSync does not recommend a medication or dosage.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close medication plan"><XMarkIcon /></IconButton></OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        <OperationNotice $warning><ExclamationTriangleIcon /> Updating core plan facts returns the plan to draft and clears prior activation and signed-consent verification. New evidence must be checked again before recording administration.</OperationNotice>
        <OperationFormGrid>
          <OperationField><span>Medication name on original label</span><input required maxLength={200} autoComplete="off" value={medicationName} onChange={(event) => setMedicationName(event.target.value)} /></OperationField>
          <OperationField><span>Dosage on original label</span><input required maxLength={200} autoComplete="off" value={dosage} onChange={(event) => setDosage(event.target.value)} /><small>Transcribe; do not calculate or alter the dose.</small></OperationField>
          <OperationField><span>Route on original label</span><select value={route} onChange={(event) => setRoute(event.target.value as MedicationRoute)}><option value="oral">Oral</option><option value="topical">Topical</option><option value="inhaled">Inhaled</option><option value="injected">Injected</option><option value="other">Other</option></select></OperationField>
          <OperationField><span>Medication kind</span><select value={medicationKind} onChange={(event) => setMedicationKind(event.target.value as MedicationKind)}><option value="non_emergency">Non-emergency</option><option value="emergency">Emergency medication</option></select></OperationField>
          <OperationField $wide><span>Original label directions</span><textarea required maxLength={1500} value={labelDirections} onChange={(event) => setLabelDirections(event.target.value)} /><small>Copy the directions exactly enough for verification. This field is not medical advice.</small></OperationField>
          <ScheduleList><span>Labelled schedule times</span>{scheduledTimes.map((value, index) => <ScheduleRow key={index}><input aria-label={`Medication schedule time ${index + 1}`} type="time" value={value} onChange={(event) => setScheduledTimes((current) => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} /><IconButton type="button" aria-label={`Remove schedule time ${index + 1}`} disabled={scheduledTimes.length === 1} onClick={() => setScheduledTimes((current) => current.filter((_, itemIndex) => itemIndex !== index))}><TrashIcon /></IconButton></ScheduleRow>)}<ActionButton type="button" onClick={() => setScheduledTimes((current) => [...current, ''])}><PlusIcon /> Add schedule time</ActionButton></ScheduleList>
          <CheckField><input type="checkbox" checked={asNeeded} onChange={(event) => setAsNeeded(event.target.checked)} /><span>Original label includes as-needed use.<small>This enables an unscheduled recording option; it does not decide when medication should be given.</small></span></CheckField>
          <OperationField><span>Plan start date</span><input required type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></OperationField>
          <OperationField><span>Plan end date</span><input type="date" min={startDate} value={endDate} onChange={(event) => setEndDate(event.target.value)} /></OperationField>
          <OperationField $wide><span>{medicationKind === 'emergency' ? 'Emergency storage and access instructions' : 'Locked storage instructions'}</span><textarea required maxLength={1000} value={storageInstructions} onChange={(event) => setStorageInstructions(event.target.value)} /><small>{medicationKind === 'emergency' ? 'Record the agreed plan: accessible to designated staff and the child, but inaccessible to other children.' : 'Non-emergency medication must remain locked and inaccessible to children.'}</small></OperationField>
          {medicationKind === 'emergency' && <OperationField $wide><span>Agreed emergency-plan reference</span><input required maxLength={300} value={emergencyReference} onChange={(event) => setEmergencyReference(event.target.value)} placeholder="Reference the signed plan on file" /><small>CareSync records the reference; it does not approve the safety plan.</small></OperationField>}
          {plan && <OperationField $wide><span>Required update reason</span><textarea required minLength={3} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /><small>Core changes return the plan to draft and remain in its audit history.</small></OperationField>}
        </OperationFormGrid>
        {error && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> {error}</OperationNotice>}
        <OperationDialogActions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? <><ArrowPathIcon /> Saving…</> : plan ? 'Save and return to draft' : 'Save draft plan'}</ActionButton></OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

export interface MedicationAuthorizationDraft {
  guardianId: string;
  reference: string;
  signedAt: string;
  validUntil: string | null;
  clientOperationId: string;
}

export function MedicationAuthorizationDialog({ plan, childName, guardians, timeZone, busy, onClose, onSave }: { plan: MedicationPlan; childName: string; guardians: MedicationGuardianOption[]; timeZone: string; busy: boolean; onClose: () => void; onSave: (draft: MedicationAuthorizationDraft) => Promise<void> }) {
  const [guardianId, setGuardianId] = useState(guardians[0]?.id || '');
  const [reference, setReference] = useState('');
  const [signedInput, setSignedInput] = useState(() => facilityDateTimeInputValue(new Date().toISOString(), timeZone));
  const [validUntil, setValidUntil] = useState('');
  const [evidenceChecked, setEvidenceChecked] = useState(false);
  const [clientOperationId] = useState(createMedicationOperationId);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('');
    try {
      if (!guardianId) throw new Error('Select the guardian named in the signed evidence.');
      if (!evidenceChecked) throw new Error('Confirm that the required written consent evidence was reviewed.');
      await onSave({ guardianId, reference: reference.trim(), signedAt: facilityDateTimeToIso(signedInput, timeZone), validUntil: validUntil || null, clientOperationId });
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The signed consent evidence could not be recorded.'); }
  };
  return <OperationDialog busy={busy} onClose={onClose} labelId="medication-authorization-title"><OperationDialogHeader><div><Eyebrow><ShieldCheckIcon width={14} /> Written consent evidence</Eyebrow><h2 id="medication-authorization-title">Record signed consent on file.</h2><p>{childName} · {plan.medication_name}. This records reviewed evidence; it does not create a signature or infer consent from a profile checkbox.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close consent evidence form"><XMarkIcon /></IconButton></OperationDialogHeader><OperationForm onSubmit={submit}><OperationFormGrid><OperationField><span>Signing guardian</span><select required value={guardianId} onChange={(event) => setGuardianId(event.target.value)}><option value="">Select guardian</option>{guardians.map((guardian) => <option key={guardian.id} value={guardian.id}>{guardian.name}{guardian.relationship ? ` · ${guardian.relationship}` : ''}</option>)}</select></OperationField><OperationField><span>Signed evidence reference</span><input required maxLength={300} value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Document or secure-file reference" /></OperationField><OperationField><span>Consent signature date and time</span><input required type="datetime-local" value={signedInput} onChange={(event) => setSignedInput(event.target.value)} /><small>{timeZone}</small></OperationField><OperationField><span>Valid until</span><input type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} /></OperationField><CheckField><input type="checkbox" checked={evidenceChecked} onChange={(event) => setEvidenceChecked(event.target.checked)} /><span>I reviewed signed written evidence containing the guardian name/signature/date and this child’s medication name, dosage, duration, and labelled-direction statement.</span></CheckField></OperationFormGrid>{guardians.length === 0 && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> No eligible guardian was returned for this child. Add or verify the family relationship before recording consent evidence.</OperationNotice>}{error && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> {error}</OperationNotice>}<OperationDialogActions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy || guardians.length === 0}>{busy ? 'Saving…' : 'Record reviewed evidence'}</ActionButton></OperationDialogActions></OperationForm></OperationDialog>;
}

export function MedicationActivationDialog({ plan, childName, busy, onClose, onSave }: { plan: MedicationPlan; childName: string; busy: boolean; onClose: () => void; onSave: (clientOperationId: string) => Promise<void> }) {
  const [container, setContainer] = useState(false); const [directions, setDirections] = useState(false); const [error, setError] = useState(''); const [clientOperationId] = useState(createMedicationOperationId);
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(''); try { if (!container || !directions) throw new Error('Both physical-container and label-direction checks are required.'); await onSave(clientOperationId); } catch (caught) { setError(caught instanceof Error ? caught.message : 'The plan could not be activated.'); } };
  return <OperationDialog busy={busy} onClose={onClose} labelId="medication-activation-title"><OperationDialogHeader><div><Eyebrow><CheckCircleIcon width={14} /> Physical safety verification</Eyebrow><h2 id="medication-activation-title">Activate this internal plan?</h2><p>{childName} · {plan.medication_name}. Activation is blocked unless signed consent evidence is current and the physical label facts are verified.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close medication activation"><XMarkIcon /></IconButton></OperationDialogHeader><OperationForm onSubmit={submit}><CheckField><input type="checkbox" checked={container} onChange={(event) => setContainer(event.target.checked)} /><span>The medication is present in its original labelled container.</span></CheckField><CheckField><input type="checkbox" checked={directions} onChange={(event) => setDirections(event.target.checked)} /><span>The transcribed medication name, dosage, duration, and directions match the original label.<small>This is a verification, not a dosage recommendation.</small></span></CheckField>{error && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> {error}</OperationNotice>}<OperationDialogActions><ActionButton type="button" disabled={busy} onClick={onClose}>Keep draft</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? 'Activating…' : 'Activate verified plan'}</ActionButton></OperationDialogActions></OperationForm></OperationDialog>;
}

export interface MedicationAdministrationDraft {
  outcome: MedicationOutcome;
  scheduledFor: string | null;
  occurredAt: string;
  amount: string | null;
  reason: string | null;
  note: string | null;
  clientOperationId: string;
}

export function MedicationAdministrationDialog({ plan, childName, dueTime, timeZone, busy, onClose, onSave }: { plan: MedicationPlan; childName: string; dueTime: string | null; timeZone: string; busy: boolean; onClose: () => void; onSave: (draft: MedicationAdministrationDraft) => Promise<void> }) {
  const [outcome, setOutcome] = useState<MedicationOutcome>('administered');
  const [occurredInput, setOccurredInput] = useState(() => facilityDateTimeInputValue(new Date().toISOString(), timeZone));
  const [amount, setAmount] = useState(plan.dosage);
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [clientOperationId] = useState(createMedicationOperationId);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(''); try { if (outcome === 'administered' && !amount.trim()) throw new Error('Record the amount actually administered.'); if (outcome !== 'administered' && reason.trim().length < 3) throw new Error('Record why the medication was refused or not given.'); await onSave({ outcome, scheduledFor: dueTime, occurredAt: facilityDateTimeToIso(occurredInput, timeZone), amount: outcome === 'administered' ? amount.trim() : null, reason: outcome === 'administered' ? null : reason.trim(), note: note.trim() || null, clientOperationId }); } catch (caught) { setError(caught instanceof Error ? caught.message : 'The medication outcome could not be recorded.'); } };
  return <OperationDialog busy={busy} onClose={onClose} labelId="medication-administration-title"><OperationDialogHeader><div><Eyebrow><BeakerIcon width={14} /> Administration outcome</Eyebrow><h2 id="medication-administration-title">Record what happened.</h2><p>{childName} · {plan.medication_name} · {dueTime ? `scheduled ${dueTime}` : 'as-needed plan'}. Do not use this screen to decide whether or how much medication should be given.</p></div><IconButton type="button" disabled={busy} onClick={onClose} aria-label="Close medication outcome form"><XMarkIcon /></IconButton></OperationDialogHeader><OperationForm onSubmit={submit}><OperationNotice><ShieldCheckIcon /> Signed consent evidence recorded · original labelled container and directions were verified when the plan was activated. Re-check the physical label before acting.</OperationNotice><OperationFormGrid><OperationField><span>Observed outcome</span><select value={outcome} onChange={(event) => setOutcome(event.target.value as MedicationOutcome)}><option value="administered">Administered</option><option value="refused">Refused</option><option value="omitted">Not given</option></select></OperationField><OperationField><span>Facility date and time</span><input required type="datetime-local" value={occurredInput} onChange={(event) => setOccurredInput(event.target.value)} /><small>{timeZone}</small></OperationField>{outcome === 'administered' ? <OperationField $wide><span>Amount actually administered</span><input required maxLength={200} value={amount} onChange={(event) => setAmount(event.target.value)} /><small>Transcribe the observed amount. Defaulted from the plan’s labelled dosage; verify it against the physical label.</small></OperationField> : <OperationField $wide><span>Required {outcome === 'refused' ? 'refusal' : 'not-given'} reason</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></OperationField>}<OperationField $wide><span>Optional factual note</span><textarea maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} /></OperationField></OperationFormGrid>{error && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> {error}</OperationNotice>}<OperationDialogActions><ActionButton type="button" disabled={busy} onClick={onClose}>Cancel</ActionButton><ActionButton type="submit" $variant="primary" disabled={busy}>{busy ? 'Recording…' : 'Record observed outcome'}</ActionButton></OperationDialogActions></OperationForm></OperationDialog>;
}

const AuditList = styled.div`display: grid; gap: 8px;`;
const AuditRow = styled.div`
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr);
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  &::before { width: 7px; height: 7px; margin-top: 5px; border-radius: 50%; content: ''; background: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; font-size: .76rem; text-transform: capitalize; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; }
`;

export function MedicationHistoryDialog({ subject, timeZone, onClose }: { subject: MedicationPlan | MedicationAdministration; timeZone: string; onClose: () => void }) {
  const isPlan = 'medication_name' in subject;
  const [result, setResult] = useState<{ events: (MedicationPlanEvent | MedicationAdministrationEvent)[]; loading: boolean; error: string }>({ events: [], loading: true, error: '' });
  useEffect(() => {
    const controller = new AbortController();
    setResult({ events: [], loading: true, error: '' });
    const request = isPlan ? fetchMedicationPlanHistory(subject.id, controller.signal) : fetchMedicationAdministrationHistory(subject.id, controller.signal);
    request.then((events) => { if (!controller.signal.aborted) setResult({ events, loading: false, error: '' }); }).catch((caught) => { if (!controller.signal.aborted) setResult({ events: [], loading: false, error: caught instanceof Error ? caught.message : 'Medication history could not be loaded.' }); });
    return () => controller.abort();
  }, [isPlan, subject.id]);
  return <OperationDialog onClose={onClose} labelId="medication-history-title"><OperationDialogHeader><div><Eyebrow><ShieldCheckIcon width={14} /> Immutable medication history</Eyebrow><h2 id="medication-history-title">{isPlan ? 'Plan' : 'Administration'} audit trail.</h2><p>Every mutation stays attributed with its reason. Administration records retain the plan facts that were current when the outcome was recorded.</p></div><IconButton type="button" onClick={onClose} aria-label="Close medication history"><XMarkIcon /></IconButton></OperationDialogHeader>{result.loading && <OperationNotice role="status"><ArrowPathIcon /> Loading medication history…</OperationNotice>}{result.error && <OperationNotice $error role="alert"><ExclamationTriangleIcon /> {result.error}</OperationNotice>}{!result.loading && !result.error && <AuditList>{result.events.map((event) => <AuditRow key={event.id}><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{formatCareTime(event.occurred_at, timeZone)} {timeZone} · {event.actor_name}{event.reason ? ` · ${event.reason}` : ''}</p></div></AuditRow>)}{result.events.length === 0 && <OperationNotice>No medication history events were returned.</OperationNotice>}</AuditList>}</OperationDialog>;
}

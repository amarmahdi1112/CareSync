import { useMemo, useState, type FormEvent } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { ActionButton, IconButton } from '../../components/ui/Primitives';
import {
  WorkforceDialog,
  WorkforceDialogActions,
  WorkforceDialogField,
  WorkforceDialogForm,
  WorkforceDialogGrid,
  WorkforceDialogHeader,
} from '../staff-rota/components/WorkforceDialog';
import {
  MAX_TRANSPORT_EVIDENCE_BYTES,
  transportRegistryApi,
  type QualificationVersion,
  type TransportStaffRecord,
  type TransportVehicleRecord,
  type VehicleEvidence,
  type VehicleFactsInput,
} from './transportRegistryApi';
import {
  TransportOperationPendingError,
  clearTransportOperation,
  withTransportOperation,
  type TransportOperationScope,
} from './transportOperationJournal';

export type TransportDialogAction =
  | { kind: 'self-declaration'; staff: TransportStaffRecord }
  | { kind: 'self-qualification'; staff: TransportStaffRecord }
  | { kind: 'qualification-review'; staff: TransportStaffRecord; qualification: QualificationVersion }
  | { kind: 'authorization'; staff: TransportStaffRecord }
  | { kind: 'readiness'; staff: TransportStaffRecord; vehicles: TransportVehicleRecord[] }
  | { kind: 'vehicle-create' }
  | { kind: 'vehicle-version'; vehicle: TransportVehicleRecord }
  | { kind: 'vehicle-retire'; vehicle: TransportVehicleRecord }
  | { kind: 'vehicle-evidence'; vehicle: TransportVehicleRecord }
  | { kind: 'vehicle-review'; vehicle: TransportVehicleRecord; evidence: VehicleEvidence };

interface Props {
  action: TransportDialogAction;
  scope: TransportOperationScope;
  evidenceUploadAvailable: boolean;
  onClose: () => void;
  onCommitted: (message: string) => Promise<void>;
}

const actionTitle = (action: TransportDialogAction): string => {
  switch (action.kind) {
    case 'self-declaration': return 'Update my driver declaration';
    case 'self-qualification': return 'Add my qualification evidence';
    case 'qualification-review': return `Review ${action.staff.first_name}’s evidence`;
    case 'authorization': return `Record authorization for ${action.staff.first_name}`;
    case 'readiness': return `Re-evaluate ${action.staff.first_name}`;
    case 'vehicle-create': return 'Register organization vehicle';
    case 'vehicle-version': return 'Record vehicle changes';
    case 'vehicle-retire': return 'Retire vehicle';
    case 'vehicle-evidence': return 'Add vehicle evidence';
    case 'vehicle-review': return 'Review vehicle evidence';
  }
};

const actionCopy = (action: TransportDialogAction): string => {
  switch (action.kind) {
    case 'self-declaration': return 'This is your own declaration, not an employer approval or transport permission.';
    case 'self-qualification': return 'The original is encrypted and privately scoped after the server scanner accepts it.';
    case 'qualification-review': return 'Review the immutable source version. Your decision creates a new result version.';
    case 'authorization': return 'Authorization is an employer evidence decision only. It cannot authorize dispatch or a child trip.';
    case 'readiness': return 'The server rechecks every required fact and records only incomplete, needs review, or blocked.';
    case 'vehicle-create': return 'Create the first immutable facts version for an organization-owned vehicle.';
    case 'vehicle-version': return 'Changes append a new vehicle version; earlier facts remain in history.';
    case 'vehicle-retire': return 'Retirement is one-way and does not delete the evidence history.';
    case 'vehicle-evidence': return 'The selected file is hashed before its exact-retry operation is durably prepared.';
    case 'vehicle-review': return 'Review the selected immutable evidence version. The original remains private.';
  }
};

function requiredText(data: FormData, name: string, label: string): string {
  const value = String(data.get(name) || '').trim();
  if (!value) throw new Error(`${label} is required.`);
  return value;
}

function optionalText(data: FormData, name: string): string | null {
  const value = String(data.get(name) || '').trim();
  return value || null;
}

function integer(data: FormData, name: string, label: string): number {
  const value = Number(data.get(name));
  if (!Number.isInteger(value)) throw new Error(`${label} must be a whole number.`);
  return value;
}

function option<const Values extends readonly string[]>(data: FormData, name: string, values: Values, label: string): Values[number] {
  const value = requiredText(data, name, label);
  if (!values.includes(value)) throw new Error(`${label} is invalid.`);
  return value as Values[number];
}

function validateDateOrder(issueDate: string | null, expiryDate: string | null): void {
  if (issueDate && expiryDate && expiryDate < issueDate) throw new Error('Expiry date cannot be before issue date.');
}

function selectedFile(data: FormData): File {
  const value = data.get('file');
  if (!(value instanceof File) || !value.name || value.size <= 0) throw new Error('Choose a PDF, PNG, or JPEG evidence file.');
  if (!['application/pdf', 'image/png', 'image/jpeg'].includes(value.type)) throw new Error('Evidence must be a PDF, PNG, or JPEG.');
  if (value.size > MAX_TRANSPORT_EVIDENCE_BYTES) throw new Error('Evidence must be 50 MB or smaller.');
  return value;
}

function vehicleFacts(data: FormData): VehicleFactsInput {
  const passengerCapacity = integer(data, 'passenger_capacity', 'Passenger capacity');
  const childCapacity = integer(data, 'child_passenger_capacity', 'Child passenger capacity');
  if (passengerCapacity < 1 || passengerCapacity > 30 || childCapacity < 0 || childCapacity >= passengerCapacity) {
    throw new Error('Child capacity must be non-negative and lower than total passenger capacity.');
  }
  const modelYear = integer(data, 'model_year', 'Model year');
  if (modelYear < 1900 || modelYear > 2100) throw new Error('Model year must be between 1900 and 2100.');
  return {
    make: requiredText(data, 'make', 'Make'),
    model: requiredText(data, 'model', 'Model'),
    model_year: modelYear,
    color: optionalText(data, 'color'),
    plate_token: requiredText(data, 'plate_token', 'Plate'),
    plate_jurisdiction: requiredText(data, 'plate_jurisdiction', 'Plate jurisdiction'),
    passenger_capacity: passengerCapacity,
    child_passenger_capacity: childCapacity,
    wheelchair_accessible: data.get('wheelchair_accessible') === 'on',
  };
}

function VehicleFields({ vehicle }: { vehicle?: TransportVehicleRecord }) {
  const latest = vehicle?.versions[0];
  return <WorkforceDialogGrid>
    <WorkforceDialogField>Make<input name="make" required maxLength={80} defaultValue={latest?.make || ''} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Model<input name="model" required maxLength={80} defaultValue={latest?.model || ''} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Model year<input name="model_year" type="number" min="1900" max="2100" required defaultValue={latest?.model_year || new Date().getFullYear()} /></WorkforceDialogField>
    <WorkforceDialogField>Color<input name="color" maxLength={40} defaultValue={latest?.color || ''} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Plate<input name="plate_token" required maxLength={24} defaultValue={latest?.plate_token || ''} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Jurisdiction<input name="plate_jurisdiction" required minLength={2} maxLength={20} defaultValue={latest?.plate_jurisdiction || 'AB'} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Total seats<input name="passenger_capacity" type="number" min="1" max="30" required defaultValue={latest?.passenger_capacity || 5} /></WorkforceDialogField>
    <WorkforceDialogField>Child seats<input name="child_passenger_capacity" type="number" min="0" max="29" required defaultValue={latest?.child_passenger_capacity ?? 4} /></WorkforceDialogField>
    <WorkforceDialogField $wide><span><input name="wheelchair_accessible" type="checkbox" defaultChecked={latest?.wheelchair_accessible || false} /> Wheelchair accessible</span></WorkforceDialogField>
  </WorkforceDialogGrid>;
}

function DialogFields({ action, evidenceUploadAvailable }: { action: TransportDialogAction; evidenceUploadAvailable: boolean }) {
  if (action.kind === 'self-declaration') {
    const current = action.staff.capabilities[0];
    return <WorkforceDialogGrid>
      <WorkforceDialogField>Status<select name="status" defaultValue={current?.status || 'declared'}><option value="declared">Declared</option><option value="withdrawn">Withdraw declaration</option></select></WorkforceDialogField>
      <WorkforceDialogField>Vehicle access<select name="vehicle_access" defaultValue={current?.vehicle_access || 'organization_vehicle_only'}><option value="organization_vehicle_only">Organization vehicle only</option><option value="personal_vehicle">Personal vehicle</option><option value="either">Either</option><option value="none">None</option></select></WorkforceDialogField>
      <WorkforceDialogField>Licence jurisdiction<input name="licence_jurisdiction" minLength={2} maxLength={20} defaultValue={current?.licence_jurisdiction || 'AB'} /></WorkforceDialogField>
      <WorkforceDialogField>Licence class<input name="licence_class" maxLength={30} defaultValue={current?.licence_class || ''} /></WorkforceDialogField>
      <WorkforceDialogField>Radius (km)<input name="preferred_service_radius_km" type="number" min="0" max="1000" defaultValue={current?.preferred_service_radius_km ?? ''} /></WorkforceDialogField>
      <WorkforceDialogField>Other jurisdiction<input name="licence_jurisdiction_other" maxLength={100} placeholder="Required only when jurisdiction is OTHER" /></WorkforceDialogField>
    </WorkforceDialogGrid>;
  }
  if (action.kind === 'self-qualification') return <WorkforceDialogGrid>
    {!evidenceUploadAvailable && <WorkforceDialogField $wide><small>Evidence uploads are temporarily unavailable. Existing metadata remains available; exact source retrieval is checked when opened.</small></WorkforceDialogField>}
    <WorkforceDialogField>Evidence type<select name="qualification_type" defaultValue="driver_licence"><option value="driver_licence">Driver licence</option><option value="driver_abstract">Driver abstract</option><option value="police_check">Police check</option><option value="vulnerable_sector_search">Vulnerable sector search</option><option value="first_aid">First aid</option><option value="vehicle_insurance_permission">Vehicle insurance permission</option></select></WorkforceDialogField>
    <WorkforceDialogField>Document<input name="file" type="file" accept="application/pdf,image/png,image/jpeg" required disabled={!evidenceUploadAvailable} /></WorkforceDialogField>
    <WorkforceDialogField>Jurisdiction<input name="jurisdiction" maxLength={20} defaultValue="AB" /></WorkforceDialogField>
    <WorkforceDialogField>Class<input name="qualification_class" maxLength={40} /></WorkforceDialogField>
    <WorkforceDialogField>Identifier last characters<input name="identifier_last4" minLength={2} maxLength={8} autoComplete="off" /></WorkforceDialogField>
    <WorkforceDialogField>Issue date<input name="issue_date" type="date" /></WorkforceDialogField>
    <WorkforceDialogField>Expiry date<input name="expiry_date" type="date" /></WorkforceDialogField>
  </WorkforceDialogGrid>;
  if (action.kind === 'qualification-review' || action.kind === 'vehicle-review') return <WorkforceDialogGrid>
    <WorkforceDialogField>Decision<select name="decision" defaultValue="verified"><option value="verified">Verify</option><option value="rejected">Reject</option></select></WorkforceDialogField>
    <WorkforceDialogField>Reason code<input name="reason_code" required maxLength={80} placeholder="e.g. original_document_verified" /></WorkforceDialogField>
  </WorkforceDialogGrid>;
  if (action.kind === 'authorization') {
    const latestCapability = action.staff.capabilities[0];
    return <WorkforceDialogGrid>
      <WorkforceDialogField>Declaration version<select name="capability_version_id" required defaultValue={latestCapability?.id || ''}><option value="" disabled>Select declaration</option>{action.staff.capabilities.map((item) => <option key={item.id} value={item.id}>v{item.version_number} · {item.status}</option>)}</select></WorkforceDialogField>
      <WorkforceDialogField>Decision<select name="decision" defaultValue="needs_review"><option value="needs_review">Needs review</option><option value="authorized">Authorized evidence window</option><option value="denied">Denied</option><option value="revoked">Revoked</option></select></WorkforceDialogField>
      <WorkforceDialogField $wide>Qualification versions<select name="qualification_version_ids" required multiple size={Math.min(7, Math.max(3, action.staff.qualifications.length))}>{action.staff.qualifications.map((item) => <option key={item.id} value={item.id}>{item.qualification_type.replaceAll('_', ' ')} · v{item.version_number} · {item.status}</option>)}</select><small>Choose every exact immutable version used by this decision.</small></WorkforceDialogField>
      <WorkforceDialogField>Valid from<input name="authorization_valid_from" type="datetime-local" /></WorkforceDialogField>
      <WorkforceDialogField>Valid until<input name="authorization_valid_until" type="datetime-local" /></WorkforceDialogField>
      <WorkforceDialogField $wide>Reason code<input name="reason_code" required maxLength={80} placeholder="Evidence-based decision reason" /></WorkforceDialogField>
    </WorkforceDialogGrid>;
  }
  if (action.kind === 'readiness') return <WorkforceDialogGrid>
    <WorkforceDialogField $wide>Vehicle<select name="vehicle_id" defaultValue=""><option value="">No vehicle selected</option>{action.vehicles.filter((item) => !item.retired_at).map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.versions[0] ? `${vehicle.versions[0].make} ${vehicle.versions[0].model} · ${vehicle.versions[0].plate_token}` : vehicle.id}</option>)}</select><small>The server re-evaluates the complete record set; this selection does not grant authority.</small></WorkforceDialogField>
  </WorkforceDialogGrid>;
  if (action.kind === 'vehicle-create' || action.kind === 'vehicle-version') return <VehicleFields vehicle={action.kind === 'vehicle-version' ? action.vehicle : undefined} />;
  if (action.kind === 'vehicle-retire') return <WorkforceDialogGrid>
    <WorkforceDialogField $wide>Retirement reason<input name="reason_code" required maxLength={80} placeholder="e.g. sold_or_removed_from_service" /></WorkforceDialogField>
    <WorkforceDialogField $wide><span><input name="confirm_retire" value="confirmed" type="checkbox" required style={{ width: 'auto', minHeight: 0, marginRight: 8 }} /> I understand retirement is one-way and preserves the immutable history.</span></WorkforceDialogField>
  </WorkforceDialogGrid>;
  if (action.kind === 'vehicle-evidence') return <WorkforceDialogGrid>
    {!evidenceUploadAvailable && <WorkforceDialogField $wide><small>Evidence uploads are temporarily unavailable. Existing metadata remains available; exact source retrieval is checked when opened.</small></WorkforceDialogField>}
    <WorkforceDialogField>Evidence type<select name="evidence_type" defaultValue="insurance"><option value="registration">Registration</option><option value="insurance">Insurance</option><option value="inspection">Inspection</option><option value="maintenance">Maintenance</option></select></WorkforceDialogField>
    <WorkforceDialogField>Document<input name="file" type="file" accept="application/pdf,image/png,image/jpeg" required disabled={!evidenceUploadAvailable} /></WorkforceDialogField>
    <WorkforceDialogField>Issue date<input name="issue_date" type="date" /></WorkforceDialogField>
    <WorkforceDialogField>Expiry date<input name="expiry_date" type="date" /></WorkforceDialogField>
  </WorkforceDialogGrid>;
  return null;
}

function localDateTimeToIso(value: string | null, label: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error(`${label} is invalid.`);
  return parsed.toISOString();
}

export function TransportRegistryDialog({ action, scope, evidenceUploadAvailable, onClose, onCommitted }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pendingConflict, setPendingConflict] = useState<TransportOperationPendingError | null>(null);
  const titleId = useMemo(() => `transport-dialog-${action.kind}`, [action.kind]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    setPendingConflict(null);
    const data = new FormData(event.currentTarget);
    try {
      let committedMessage = 'Registry updated.';
      if (action.kind === 'self-declaration') {
        const status = option(data, 'status', ['declared', 'withdrawn'] as const, 'Status');
        const jurisdiction = optionalText(data, 'licence_jurisdiction');
        const otherJurisdiction = optionalText(data, 'licence_jurisdiction_other');
        const payload = status === 'withdrawn' ? {
          status, willing_to_drive: false, licence_jurisdiction: null, licence_jurisdiction_other: null, licence_class: null,
          vehicle_access: 'none' as const, preferred_service_radius_km: null,
        } : {
          status, willing_to_drive: true,
          licence_jurisdiction: jurisdiction || requiredText(data, 'licence_jurisdiction', 'Licence jurisdiction'),
          licence_jurisdiction_other: otherJurisdiction,
          licence_class: requiredText(data, 'licence_class', 'Licence class'),
          vehicle_access: option(data, 'vehicle_access', ['organization_vehicle_only', 'personal_vehicle', 'either'] as const, 'Vehicle access'),
          preferred_service_radius_km: optionalText(data, 'preferred_service_radius_km') == null ? null : integer(data, 'preferred_service_radius_km', 'Service radius'),
        };
        if (status === 'declared' && (payload.licence_jurisdiction === 'OTHER') !== Boolean(payload.licence_jurisdiction_other)) throw new Error('OTHER jurisdiction requires its explicit jurisdiction name.');
        await withTransportOperation({ scope, lane: 'self:declaration', intent: payload, send: (operationId) => transportRegistryApi.declareSelf(operationId, payload) });
        committedMessage = status === 'withdrawn' ? 'Your declaration was withdrawn.' : 'Your declaration version was recorded.';
      } else if (action.kind === 'self-qualification') {
        if (!evidenceUploadAvailable) throw new Error('Evidence uploads are temporarily unavailable.');
        const file = selectedFile(data);
        const payload = {
          qualification_type: option(data, 'qualification_type', ['driver_licence', 'driver_abstract', 'police_check', 'vulnerable_sector_search', 'first_aid', 'vehicle_insurance_permission'] as const, 'Evidence type'),
          jurisdiction: optionalText(data, 'jurisdiction'), qualification_class: optionalText(data, 'qualification_class'), identifier_last4: optionalText(data, 'identifier_last4'),
          issue_date: optionalText(data, 'issue_date'), expiry_date: optionalText(data, 'expiry_date'), file,
        };
        validateDateOrder(payload.issue_date, payload.expiry_date);
        if (payload.qualification_type === 'driver_licence' && (!payload.jurisdiction || !payload.qualification_class || !payload.expiry_date)) throw new Error('Driver licence evidence requires jurisdiction, class, and expiry date.');
        const intent = { qualification_type: payload.qualification_type, jurisdiction: payload.jurisdiction, qualification_class: payload.qualification_class, identifier_last4: payload.identifier_last4, issue_date: payload.issue_date, expiry_date: payload.expiry_date };
        await withTransportOperation({ scope, lane: `self:qualification:${payload.qualification_type}`, intent, file, send: (operationId) => transportRegistryApi.uploadSelfQualification(operationId, payload) });
        committedMessage = 'Your qualification evidence was stored for independent review.';
      } else if (action.kind === 'qualification-review') {
        const payload = { source_qualification_version_id: action.qualification.id, decision: option(data, 'decision', ['verified', 'rejected'] as const, 'Decision'), reason_code: requiredText(data, 'reason_code', 'Reason') };
        await withTransportOperation({ scope, lane: `staff:${action.staff.membership_id}:qualification:${action.qualification.qualification_type}:review`, intent: payload, send: (operationId) => transportRegistryApi.reviewQualification(action.staff.membership_id, operationId, payload) });
        committedMessage = 'Qualification review recorded.';
      } else if (action.kind === 'authorization') {
        const decision = option(data, 'decision', ['needs_review', 'authorized', 'denied', 'revoked'] as const, 'Decision');
        const selectedQualifications = data.getAll('qualification_version_ids').map(String);
        if (!selectedQualifications.length) throw new Error('Choose at least one qualification version.');
        if (selectedQualifications.length > 20) throw new Error('An authorization can reference at most 20 exact qualification versions.');
        const payload = {
          capability_version_id: requiredText(data, 'capability_version_id', 'Declaration version'),
          qualification_version_ids: selectedQualifications,
          decision,
          reason_code: requiredText(data, 'reason_code', 'Reason'),
          authorization_valid_from: decision === 'authorized' ? localDateTimeToIso(optionalText(data, 'authorization_valid_from'), 'Valid from') : null,
          authorization_valid_until: decision === 'authorized' ? localDateTimeToIso(optionalText(data, 'authorization_valid_until'), 'Valid until') : null,
        };
        if (decision === 'authorized' && (!payload.authorization_valid_from || !payload.authorization_valid_until)) throw new Error('Authorized evidence decisions require a finite start and end time.');
        if (payload.authorization_valid_from && payload.authorization_valid_until && Date.parse(payload.authorization_valid_until) <= Date.parse(payload.authorization_valid_from)) throw new Error('Authorization end time must follow its start time.');
        await withTransportOperation({ scope, lane: `staff:${action.staff.membership_id}:authorization`, intent: payload, send: (operationId) => transportRegistryApi.authorize(action.staff.membership_id, operationId, payload) });
        committedMessage = 'Authorization evidence decision recorded. No dispatch authority was granted.';
      } else if (action.kind === 'readiness') {
        const vehicleId = optionalText(data, 'vehicle_id');
        await withTransportOperation({ scope, lane: `staff:${action.staff.membership_id}:readiness`, intent: { vehicle_id: vehicleId }, send: (operationId) => transportRegistryApi.evaluateReadiness(action.staff.membership_id, operationId, vehicleId) });
        committedMessage = 'Readiness evidence was re-evaluated.';
      } else if (action.kind === 'vehicle-create') {
        const payload = vehicleFacts(data);
        await withTransportOperation({ scope, lane: `vehicle:create:${payload.plate_jurisdiction}:${payload.plate_token}`.replace(/[^a-z0-9:._-]/gi, '-'), intent: payload, send: (operationId) => transportRegistryApi.createOrganizationVehicle(operationId, payload) });
        committedMessage = 'Organization vehicle registered.';
      } else if (action.kind === 'vehicle-version') {
        const payload = vehicleFacts(data);
        await withTransportOperation({ scope, lane: `vehicle:${action.vehicle.id}:version`, intent: payload, send: (operationId) => transportRegistryApi.versionVehicle(action.vehicle.id, operationId, payload) });
        committedMessage = 'New vehicle facts version recorded.';
      } else if (action.kind === 'vehicle-retire') {
        const reason = requiredText(data, 'reason_code', 'Retirement reason');
        if (data.get('confirm_retire') !== 'confirmed') throw new Error('Confirm the one-way vehicle retirement before continuing.');
        await withTransportOperation({ scope, lane: `vehicle:${action.vehicle.id}:retire`, intent: { reason_code: reason }, send: (operationId) => transportRegistryApi.retireVehicle(action.vehicle.id, operationId, reason) });
        committedMessage = 'Vehicle retired. Its evidence history was preserved.';
      } else if (action.kind === 'vehicle-evidence') {
        if (!evidenceUploadAvailable) throw new Error('Evidence uploads are temporarily unavailable.');
        const file = selectedFile(data);
        const payload = { evidence_type: option(data, 'evidence_type', ['registration', 'insurance', 'inspection', 'maintenance'] as const, 'Evidence type'), issue_date: optionalText(data, 'issue_date'), expiry_date: optionalText(data, 'expiry_date'), file };
        validateDateOrder(payload.issue_date, payload.expiry_date);
        if (payload.evidence_type !== 'maintenance' && !payload.expiry_date) throw new Error('Registration, insurance, and inspection evidence require an expiry date.');
        const intent = { evidence_type: payload.evidence_type, issue_date: payload.issue_date, expiry_date: payload.expiry_date };
        await withTransportOperation({ scope, lane: `vehicle:${action.vehicle.id}:evidence:${payload.evidence_type}`, intent, file, send: (operationId) => transportRegistryApi.uploadVehicleEvidence(action.vehicle.id, operationId, payload) });
        committedMessage = 'Vehicle evidence stored for review.';
      } else {
        const payload = { source_evidence_version_id: action.evidence.id, decision: option(data, 'decision', ['verified', 'rejected'] as const, 'Decision'), reason_code: requiredText(data, 'reason_code', 'Reason') };
        await withTransportOperation({ scope, lane: `vehicle:${action.vehicle.id}:evidence:${action.evidence.evidence_type}:review`, intent: payload, send: (operationId) => transportRegistryApi.reviewVehicleEvidence(action.vehicle.id, operationId, payload) });
        committedMessage = 'Vehicle evidence review recorded.';
      }
      await onCommitted(committedMessage);
      onClose();
    } catch (caught) {
      if (caught instanceof TransportOperationPendingError) setPendingConflict(caught);
      setError(caught instanceof Error ? caught.message : 'The registry change could not be completed.');
    } finally {
      setBusy(false);
    }
  };

  const uploadBlocked = (action.kind === 'self-qualification' || action.kind === 'vehicle-evidence') && !evidenceUploadAvailable;
  return <WorkforceDialog onClose={onClose} busy={busy} retryLocked={false} labelId={titleId}>
    <WorkforceDialogHeader>
      <div><h2 id={titleId}>{actionTitle(action)}</h2><p>{actionCopy(action)}</p></div>
      <IconButton type="button" onClick={onClose} disabled={busy} aria-label="Close dialog"><XMarkIcon /></IconButton>
    </WorkforceDialogHeader>
    <WorkforceDialogForm onSubmit={submit}>
      <DialogFields action={action} evidenceUploadAvailable={evidenceUploadAvailable} />
      {error && <p role="alert" style={{ margin: 0, color: 'var(--color-coral, #ee9187)', fontSize: '.74rem' }}>{error}</p>}
      {pendingConflict && <div role="alert" style={{ display: 'grid', gap: 8, padding: 12, border: '1px solid rgba(242,190,116,.4)', borderRadius: 10, fontSize: '.7rem' }}>
        <strong>Saved retry from {new Date(pendingConflict.createdAt).toLocaleString()}</strong>
        <span>It may already have committed. Refresh and inspect the history first. Discard only when you intentionally abandon that exact saved command.</span>
        <ActionButton type="button" $variant="danger" onClick={() => {
          clearTransportOperation(scope, pendingConflict.lane, pendingConflict.operationId);
          setPendingConflict(null);
          setError('Saved retry discarded. Review the form, then submit again to create a new operation.');
        }}>Discard saved retry</ActionButton>
      </div>}
      <WorkforceDialogActions>
        <ActionButton type="button" onClick={onClose} disabled={busy}>Cancel</ActionButton>
        <ActionButton type="submit" $variant={action.kind === 'vehicle-retire' ? 'danger' : 'primary'} disabled={busy || uploadBlocked}>{busy ? 'Recording…' : action.kind === 'vehicle-retire' ? 'Retire vehicle permanently' : 'Record immutable change'}</ActionButton>
      </WorkforceDialogActions>
    </WorkforceDialogForm>
  </WorkforceDialog>;
}

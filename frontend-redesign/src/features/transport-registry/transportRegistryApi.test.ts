import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchPrivateEvidence,
  isSafeManagerEvidencePath,
  parseTransportCommandReceipt,
  parseTransportRegistryWorkspace,
  TransportRegistryApiError,
  transportRegistryApi,
} from './transportRegistryApi';

const ids = {
  membership: '11111111-1111-4111-8111-111111111111',
  capability: '22222222-2222-4222-8222-222222222222',
  qualification: '33333333-3333-4333-8333-333333333333',
  qualificationResult: '44444444-4444-4444-8444-444444444444',
  qualificationReview: '55555555-5555-4555-8555-555555555555',
  authorization: '66666666-6666-4666-8666-666666666666',
  readiness: '77777777-7777-4777-8777-777777777777',
  vehicle: '88888888-8888-4888-8888-888888888888',
  vehicleVersion: '99999999-9999-4999-8999-999999999999',
  evidence: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  evidenceResult: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  evidenceReview: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  operation: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  result: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
};

const timestamp = '2026-07-21T17:00:00Z';

function fixture(): Record<string, any> {
  return {
    schema_version: '0032', generated_at: timestamp,
    staff: [{
      membership_id: ids.membership, first_name: 'Amar', last_name: 'Tester',
      capabilities: [{ id: ids.capability, version_number: 1, status: 'declared', willing_to_drive: true, licence_jurisdiction: 'AB', licence_class: '5', vehicle_access: 'organization_vehicle_only', preferred_service_radius_km: 25, effective_at: timestamp }],
      qualifications: [
        { id: ids.qualificationResult, qualification_type: 'driver_licence', version_number: 2, status: 'verified', jurisdiction: 'AB', qualification_class: '5', identifier_last4: '1234', issue_date: '2025-07-21', expiry_date: '2027-07-21', evidence_present: true, content_path: `/api/v1/staff/transport-registry/${ids.membership}/qualification-evidence/${ids.qualificationResult}/content`, effective_at: timestamp },
        { id: ids.qualification, qualification_type: 'driver_licence', version_number: 1, status: 'declared', jurisdiction: 'AB', qualification_class: '5', identifier_last4: '1234', issue_date: '2025-07-21', expiry_date: '2027-07-21', evidence_present: true, content_path: `/api/v1/staff/transport-registry/${ids.membership}/qualification-evidence/${ids.qualification}/content`, effective_at: timestamp },
      ],
      qualification_reviews: [{ id: ids.qualificationReview, source_qualification_version_id: ids.qualification, result_qualification_version_id: ids.qualificationResult, decision: 'verified', reason_code: 'original_verified', reviewed_at: timestamp }],
      authorizations: [{ id: ids.authorization, decision_sequence: 1, capability_version_id: ids.capability, qualification_version_ids: [ids.qualification], decision: 'authorized', reason_code: 'requirements_met', authorization_valid_from: timestamp, authorization_valid_until: '2026-08-21T17:00:00Z', reviewed_at: timestamp, operational_driver_ready: false, dispatch_authorized: false }],
      readiness: [{ id: ids.readiness, decision_sequence: 1, decision: 'needs_review', reason_codes: ['vehicle_evidence_incomplete'], vehicle_id: ids.vehicle, evaluated_at: timestamp, operational_driver_ready: false, dispatch_authorized: false }],
      capabilities_truncated: false, qualification_types_truncated: [], qualification_reviews_truncated: false, authorizations_truncated: false, readiness_truncated: false,
    }],
    vehicles: [{
      id: ids.vehicle, owner_kind: 'organization', staff_owner_membership_id: null, retired_at: null,
      versions: [{ id: ids.vehicleVersion, version_number: 1, make: 'Honda', model: 'Odyssey', model_year: 2025, color: 'Blue', plate_token: 'ABC123', plate_jurisdiction: 'AB', passenger_capacity: 8, child_passenger_capacity: 7, wheelchair_accessible: false, effective_at: timestamp }],
      evidence: [
        { id: ids.evidenceResult, vehicle_version_id: ids.vehicleVersion, evidence_type: 'insurance', version_number: 2, status: 'verified', issue_date: '2026-01-01', expiry_date: '2027-01-01', original_filename: 'insurance.pdf', media_type: 'application/pdf', byte_size: 1024, content_path: `/api/v1/staff/transport-registry/vehicles/${ids.vehicle}/evidence/${ids.evidenceResult}/content`, recorded_at: timestamp },
        { id: ids.evidence, vehicle_version_id: ids.vehicleVersion, evidence_type: 'insurance', version_number: 1, status: 'provided', issue_date: '2026-01-01', expiry_date: '2027-01-01', original_filename: 'insurance.pdf', media_type: 'application/pdf', byte_size: 1024, content_path: `/api/v1/staff/transport-registry/vehicles/${ids.vehicle}/evidence/${ids.evidence}/content`, recorded_at: timestamp },
      ],
      evidence_reviews: [{ id: ids.evidenceReview, source_evidence_version_id: ids.evidence, result_evidence_version_id: ids.evidenceResult, decision: 'verified', reason_code: 'policy_confirmed', reviewed_at: timestamp }],
      versions_truncated: false, evidence_types_truncated: [], evidence_reviews_truncated: false,
    }],
    staff_truncated: false, vehicles_truncated: false, operational_driver_ready: false, dispatch_authorized: false,
  };
}

describe('0032 transport registry workspace parser', () => {
  it('accepts the exact bounded evidence-only contract', () => {
    const parsed = parseTransportRegistryWorkspace(fixture());
    expect(parsed.staff[0]?.qualifications[0]?.content_path).toContain(ids.membership);
    expect(parsed.vehicles[0]?.evidence[0]?.content_path).toContain(ids.vehicle);
    expect(parsed.operational_driver_ready).toBe(false);
  });

  it('rejects extra fields and any authority-granting marker', () => {
    expect(() => parseTransportRegistryWorkspace({ ...fixture(), secret: 'drift' })).toThrow(TransportRegistryApiError);
    expect(() => parseTransportRegistryWorkspace({ ...fixture(), dispatch_authorized: true })).toThrow(TransportRegistryApiError);
    const payload = fixture();
    payload.staff[0]!.readiness[0]!.operational_driver_ready = true as false;
    expect(() => parseTransportRegistryWorkspace(payload)).toThrow(TransportRegistryApiError);
  });

  it('rejects impossible dates, oversized fields, and empty evidence', () => {
    const impossible = fixture();
    impossible.staff[0]!.qualifications[0]!.expiry_date = '2026-02-31';
    expect(() => parseTransportRegistryWorkspace(impossible)).toThrow(TransportRegistryApiError);
    const leapDay = fixture();
    leapDay.staff[0]!.qualifications[0]!.expiry_date = '2028-02-29';
    expect(parseTransportRegistryWorkspace(leapDay).staff[0]?.qualifications[0]?.expiry_date).toBe('2028-02-29');
    const oversized = fixture();
    oversized.vehicles[0]!.versions[0]!.make = 'x'.repeat(81);
    expect(() => parseTransportRegistryWorkspace(oversized)).toThrow(TransportRegistryApiError);
    const empty = fixture();
    empty.vehicles[0]!.evidence[0]!.byte_size = 0;
    expect(() => parseTransportRegistryWorkspace(empty)).toThrow(TransportRegistryApiError);
  });

  it('allows out-of-window references only when the matching history says it was truncated', () => {
    const bounded = fixture();
    bounded.staff[0]!.capabilities = [];
    bounded.staff[0]!.capabilities_truncated = true;
    bounded.staff[0]!.qualifications = [];
    bounded.staff[0]!.qualification_types_truncated = ['driver_licence'];
    bounded.vehicles[0]!.versions = [];
    bounded.vehicles[0]!.versions_truncated = true;
    bounded.vehicles[0]!.evidence = [];
    bounded.vehicles[0]!.evidence_types_truncated = ['insurance'];
    expect(parseTransportRegistryWorkspace(bounded).staff[0]?.authorizations).toHaveLength(1);

    const dangling = fixture();
    dangling.staff[0]!.capabilities = [];
    expect(() => parseTransportRegistryWorkspace(dangling)).toThrow(TransportRegistryApiError);
    const danglingEvidence = fixture();
    danglingEvidence.vehicles[0]!.versions = [];
    expect(() => parseTransportRegistryWorkspace(danglingEvidence)).toThrow(TransportRegistryApiError);

    const missingReviewResult = fixture();
    missingReviewResult.staff[0]!.qualifications = missingReviewResult.staff[0]!.qualifications.filter((item: { id: string }) => item.id !== ids.qualificationResult);
    expect(() => parseTransportRegistryWorkspace(missingReviewResult)).toThrow('qualification review linkage');

    const missingVehicleReviewResult = fixture();
    missingVehicleReviewResult.vehicles[0]!.evidence = missingVehicleReviewResult.vehicles[0]!.evidence.filter((item: { id: string }) => item.id !== ids.evidenceResult);
    expect(() => parseTransportRegistryWorkspace(missingVehicleReviewResult)).toThrow('vehicle review linkage');
  });

  it('does not require a personal vehicle owner to be in the active staff window', () => {
    const payload = fixture();
    payload.vehicles[0]!.owner_kind = 'staff_personal';
    payload.vehicles[0]!.staff_owner_membership_id = 'ffffffff-ffff-4fff-8fff-ffffffffffff';
    expect(parseTransportRegistryWorkspace(payload).vehicles[0]?.staff_owner_membership_id).toBe('ffffffff-ffff-4fff-8fff-ffffffffffff');
  });
});

describe('private evidence destinations', () => {
  it('allows only exact manager content routes with UUID identities', () => {
    expect(isSafeManagerEvidencePath(`/api/v1/staff/transport-registry/${ids.membership}/qualification-evidence/${ids.qualification}/content`)).toBe(true);
    expect(isSafeManagerEvidencePath(`/api/v1/staff/transport-registry/vehicles/${ids.vehicle}/evidence/${ids.evidence}/content`)).toBe(true);
    for (const path of [
      `https://evil.example/api/v1/staff/transport-registry/${ids.membership}/qualification-evidence/${ids.qualification}/content`,
      `/api/v1/staff/transport-registry/${ids.membership}/qualification-evidence/${ids.qualification}/content?download=1`,
      '/api/v1/staff/transport-registry/../../auth/me',
      '/api/v1/staff/transport-registry/not-a-uuid/qualification-evidence/not-a-uuid/content',
    ]) expect(isSafeManagerEvidencePath(path)).toBe(false);
  });
});

describe('0032 command receipt parser', () => {
  it('binds exact operation, kind, and no-authority markers', () => {
    const receipt = { schema_version: '0032', client_operation_id: ids.operation, command_kind: 'vehicle_create', result_kind: 'vehicle', result_id: ids.result, committed_at: timestamp, exact_retry: false, operational_driver_ready: false, dispatch_authorized: false };
    expect(parseTransportCommandReceipt(receipt, ids.operation, 'vehicle_create').result_id).toBe(ids.result);
    expect(() => parseTransportCommandReceipt(receipt, ids.result, 'vehicle_create')).toThrow(TransportRegistryApiError);
    expect(() => parseTransportCommandReceipt({ ...receipt, dispatch_authorized: true }, ids.operation, 'vehicle_create')).toThrow(TransportRegistryApiError);
    expect(() => parseTransportCommandReceipt({ ...receipt, result_kind: 'driver_readiness' }, ids.operation, 'vehicle_create')).toThrow('receipt result binding');
  });
});

describe('transport registry HTTP adapter', () => {
  afterEach(() => vi.unstubAllGlobals());

  const receipt = (kind: 'qualification_review' | 'vehicle_evidence', resultKind: 'driver_qualification' | 'vehicle_evidence') => ({
    schema_version: '0032', client_operation_id: ids.operation, command_kind: kind, result_kind: resultKind,
    result_id: ids.result, committed_at: timestamp, exact_retry: false, operational_driver_ready: false, dispatch_authorized: false,
  });

  function sessionStorageStub() {
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => key === 'caresync-redesign-token' ? 'token' : key === 'caresync-redesign-organization' ? '11111111-1111-4111-8111-111111111111' : null,
    });
  }

  it('sends the exact manager review path, operation id, and intent body', async () => {
    sessionStorageStub();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(receipt('qualification_review', 'driver_qualification')), { status: 201, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    await transportRegistryApi.reviewQualification(ids.membership, ids.operation, { source_qualification_version_id: ids.qualification, decision: 'verified', reason_code: 'original_verified' });
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(new RegExp(`/staff/transport-registry/${ids.membership}/qualification-reviews$`));
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.method).toBe('POST');
    expect(JSON.parse(String(request.body))).toEqual({ operation_id: ids.operation, source_qualification_version_id: ids.qualification, decision: 'verified', reason_code: 'original_verified' });
  });

  it('uses multipart without overriding its boundary for evidence uploads', async () => {
    sessionStorageStub();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(receipt('vehicle_evidence', 'vehicle_evidence')), { status: 201, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['proof'], 'insurance.pdf', { type: 'application/pdf' });
    await transportRegistryApi.uploadVehicleEvidence(ids.vehicle, ids.operation, { evidence_type: 'insurance', issue_date: '2026-01-01', expiry_date: '2027-01-01', file });
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = request.headers as Headers;
    expect(headers.has('content-type')).toBe(false);
    expect(request.body).toBeInstanceOf(FormData);
    const body = request.body as FormData;
    expect(body.get('operation_id')).toBe(ids.operation);
    expect(body.get('evidence_type')).toBe('insurance');
    expect((body.get('file') as File).name).toBe('insurance.pdf');
  });

  it('fetches private evidence only with bearer and organization headers and no-store cache', async () => {
    sessionStorageStub();
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['private'], { type: 'application/pdf' }), { status: 200, headers: { 'content-type': 'application/pdf' } }));
    vi.stubGlobal('fetch', fetchMock);
    const path = `/api/v1/staff/transport-registry/vehicles/${ids.vehicle}/evidence/${ids.evidence}/content`;
    await expect(fetchPrivateEvidence(path, ids.membership)).resolves.toMatchObject({ mediaType: 'application/pdf' });
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(new RegExp(`${path}$`));
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = request.headers as Headers;
    expect(headers.get('authorization')).toBe('Bearer token');
    expect(headers.get('x-organization-id')).toBe('11111111-1111-4111-8111-111111111111');
    expect(request.cache).toBe('no-store');
  });

  it('fails before fetching if the selected organization no longer matches the mounted workspace', async () => {
    sessionStorageStub();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const path = `/api/v1/staff/transport-registry/vehicles/${ids.vehicle}/evidence/${ids.evidence}/content`;
    await expect(fetchPrivateEvidence(path, 'ffffffff-ffff-4fff-8fff-ffffffffffff')).rejects.toThrow('selected organization');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

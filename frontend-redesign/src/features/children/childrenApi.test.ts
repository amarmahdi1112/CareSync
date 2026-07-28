import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isCommandOutcomeUnknown } from '../../api/childcareCommand';
import {
  ChildrenApiError,
  archiveChild,
  approveChildEnrollmentPlacement,
  buildChildCreateCommand,
  buildChildActiveStateCommand,
  buildChildUpdateCommand,
  buildEnrollmentCreateCommand,
  buildEnrollmentEndCommand,
  buildEnrollmentPlacementApprovalCommand,
  createChild,
  createChildEnrollment,
  deleteChildPhoto,
  endChildEnrollment,
  fetchChildDetails,
  fetchChildDirectoryPage,
  fetchChildPhoto,
  fetchChildProfile,
  fetchChildFamilies,
  fetchEnrollmentFacilities,
  fetchEnrollmentPlacementOptions,
  updateChild,
  uploadChildPhoto,
  type ApiChildEnrollment,
  type ChildMutationInput,
  type EnrollmentFacilityOption,
  type EnrollmentPlacementOptions,
} from './childrenApi';

const DIRECTORY_ORG_ID = '11111111-1111-4111-8111-111111111111';
const DIRECTORY_CHILD_ID = '22222222-2222-4222-8222-222222222222';
const DIRECTORY_FAMILY_ID = '33333333-3333-4333-8333-333333333333';
const DIRECTORY_ENROLLMENT_ID = '44444444-4444-4444-8444-444444444444';
const DIRECTORY_FACILITY_ID = '55555555-5555-4555-8555-555555555555';
const DIRECTORY_PROGRAM_ID = '66666666-6666-4666-8666-666666666666';
const DIRECTORY_ROOM_ID = '77777777-7777-4777-8777-777777777777';

const input: ChildMutationInput = {
  family_id: 'family-a', first_name: 'Amina', middle_name: null, last_name: 'Noor',
  date_of_birth: '2022-04-12', gender: null, age_group: 'Preschool', is_active: true,
  health_care_number: null, allergies: null, medical_conditions: null, medications: null,
  immunization_up_to_date: null, doctor_name: null, doctor_phone: null,
};

const childResponse = {
  id: 'child-1', organization_id: 'org-a', ...input,
  enrollments: [], created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z',
  version: 2, replayed: false,
};

const facility: EnrollmentFacilityOption = {
  id: 'facility-1', organization_id: 'org-a', name: 'North Centre', status: 'active', timezone: 'America/Edmonton',
};

const placementOptions: EnrollmentPlacementOptions = {
  programs: [{ id: 'program-1', organization_id: 'org-a', facility_id: 'facility-1', name: 'Preschool', program_type: 'daycare', is_active: true }],
  rooms: [{ id: 'room-1', organization_id: 'org-a', facility_id: 'facility-1', program_id: 'program-1', name: 'Starlight', age_group: 'Preschool', capacity: 12, occupancy: 2, is_active: true }],
};

const pendingEnrollment: ApiChildEnrollment = {
  id: 'enrollment-1', organization_id: 'org-a', child_id: 'child-1', facility_id: 'facility-1',
  program_id: null, room_id: null, start_date: '2026-07-14', end_date: null, status: 'pending',
  is_active: false, placement_effective_date: null, version: 1, replayed: false,
};

const activeEnrollment: ApiChildEnrollment = {
  ...pendingEnrollment, program_id: 'program-1', room_id: 'room-1', status: 'active', is_active: true,
  placement_effective_date: '2026-07-14', version: 2,
};

const directoryEnrollment = {
  id: DIRECTORY_ENROLLMENT_ID,
  organization_id: DIRECTORY_ORG_ID,
  child_id: DIRECTORY_CHILD_ID,
  facility_id: DIRECTORY_FACILITY_ID,
  facility_name: 'North Centre',
  program_id: DIRECTORY_PROGRAM_ID,
  program_name: 'Daycare',
  program_type: 'daycare',
  room_id: DIRECTORY_ROOM_ID,
  room_name: 'Starlight',
  placement_effective_date: '2026-07-01',
  start_date: '2026-07-01',
  end_date: null,
  status: 'active',
  version: 3,
  placement_state: 'current',
};

const directoryItem = {
  id: DIRECTORY_CHILD_ID,
  organization_id: DIRECTORY_ORG_ID,
  family_id: DIRECTORY_FAMILY_ID,
  family_name: 'Noor Family',
  first_name: 'Amina',
  middle_name: null,
  last_name: 'Noor',
  date_of_birth: '2022-04-12',
  age_group: 'Preschool',
  is_active: true,
  version: 2,
  profile_photo_url: null,
  profile_photo_updated_at: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-15T00:00:00Z',
  care_lane: 'daycare',
  open_enrollment: directoryEnrollment,
};

const directoryCounts = {
  total: 1,
  active: 1,
  inactive: 0,
  daycare: 1,
  out_of_school_care: 0,
  unassigned: 0,
  reserved: 0,
  needs_review: 0,
};

function directoryPage(
  items: unknown[] = [directoryItem],
  total = items.length,
  limit = 50,
  offset = 0,
  counts: Record<string, number> = directoryCounts,
) {
  return { items, total, limit, offset, counts };
}

function okJson(value: unknown, status = 200) {
  return { ok: true, status, json: async () => value };
}

describe('versioned children and enrollment commands', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(okJson(childResponse));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('creates and updates through exact versioned child commands', async () => {
    const createCommand = buildChildCreateCommand(input);
    await createChild(createCommand, new Set(['family-a']), 'org-a');
    const createBody = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(createBody.client_operation_id).toBe(createCommand.clientOperationId);
    expect(createBody).not.toHaveProperty('expected_version');

    const updateCommand = buildChildUpdateCommand(input, 1);
    await updateChild('child-1', updateCommand, new Set(['family-a']), 'org-a');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toMatch(/\/children\/child-1$/);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(String(init.body))).toMatchObject({
      client_operation_id: updateCommand.clientOperationId,
      expected_version: 1,
    });
  });

  it('accepts a replayed archive command whose canonical child was later reactivated', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...childResponse, replayed: true, is_active: true, version: 5 }));
    await expect(archiveChild(
      'child-1',
      'family-a',
      buildChildActiveStateCommand(false, 2),
      new Set(['family-a']),
      'org-a',
    )).resolves.toMatchObject({ replayed: true, is_active: true, version: 5 });
  });

  it('creates a pending unassigned enrollment with facility and start date only', async () => {
    fetchMock.mockResolvedValueOnce(okJson(pendingEnrollment, 201));
    const command = buildEnrollmentCreateCommand({ facility_id: 'facility-1', start_date: '2026-07-14' });
    const saved = await createChildEnrollment('child-1', 'org-a', command, [facility]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/children\/child-1\/enrollments$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      facility_id: 'facility-1', start_date: '2026-07-14', client_operation_id: command.clientOperationId,
    });
    expect(saved).toMatchObject({ status: 'pending', program_id: null, room_id: null });
  });

  it('approves initial placement through the named route and activates the enrollment', async () => {
    fetchMock.mockResolvedValueOnce(okJson(activeEnrollment));
    const command = buildEnrollmentPlacementApprovalCommand({ room_id: 'room-1', effective_date: '2026-07-14' }, 1);
    await approveChildEnrollmentPlacement(pendingEnrollment, 'org-a', command, [facility], placementOptions);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/enrollments\/enrollment-1\/placement-approval$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      room_id: 'room-1', effective_date: '2026-07-14',
      client_operation_id: command.clientOperationId, expected_version: 1,
    });
  });

  it('refuses to overwrite an already assigned enrollment through initial placement approval', async () => {
    const command = buildEnrollmentPlacementApprovalCommand({ room_id: 'room-1', effective_date: '2026-07-15' }, 2);
    await expect(approveChildEnrollmentPlacement(activeEnrollment, 'org-a', command, [facility], placementOptions))
      .rejects.toMatchObject({ status: 409 } satisfies Partial<ChildrenApiError>);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('allows a reconciled legacy active-unassigned enrollment through guarded approval', async () => {
    const legacyUnassigned = { ...pendingEnrollment, status: 'active' as const, is_active: true, version: 4 };
    const approved = { ...activeEnrollment, version: 5 };
    fetchMock.mockResolvedValueOnce(okJson(approved));
    const command = buildEnrollmentPlacementApprovalCommand({ room_id: 'room-1', effective_date: '2026-07-14' }, 4);
    await expect(approveChildEnrollmentPlacement(legacyUnassigned, 'org-a', command, [facility], placementOptions))
      .resolves.toMatchObject({ status: 'active', room_id: 'room-1', version: 5 });
  });

  it('ends enrollment with an exact lifecycle command', async () => {
    const ended = { ...activeEnrollment, status: 'ended', is_active: false, end_date: '2026-07-17', version: 3 };
    fetchMock.mockResolvedValueOnce(okJson(ended));
    const command = buildEnrollmentEndCommand('2026-07-17', 2);
    await endChildEnrollment(activeEnrollment, 'org-a', command);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/enrollments\/enrollment-1$/);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(String(init.body))).toMatchObject({ status: 'ended', end_date: '2026-07-17', expected_version: 2 });
  });

  it('loads active facilities and tenant-scoped placement options', async () => {
    fetchMock.mockResolvedValueOnce(okJson([facility, { ...facility, id: 'facility-2', status: 'inactive' }]));
    await expect(fetchEnrollmentFacilities('org-a')).resolves.toEqual([facility]);

    const roster = {
      facility_id: 'facility-1', facility_date: '2026-07-17', unassigned_children: [],
      rooms: [{ room_id: 'room-1', facility_id: 'facility-1', program_id: 'program-1', name: 'Starlight', capacity: 12, is_active: true, occupancy: 2, children: [], reserved_children: [] }],
    };
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/programs?')) return Promise.resolve(okJson(placementOptions.programs));
      if (url.includes('/room-rosters?')) return Promise.resolve(okJson(roster));
      return Promise.resolve(okJson(placementOptions.rooms.map(({ occupancy: _occupancy, ...room }) => room)));
    });
    await expect(fetchEnrollmentPlacementOptions('org-a', 'facility-1', [facility])).resolves.toEqual(placementOptions);
  });

  it('pages through all minimal family options and encodes server search', async () => {
    const firstItems = Array.from({ length: 200 }, (_, index) => ({
      id: `family-${index}`, organization_id: 'org-a', name: `Family ${index}`, status: 'active',
    }));
    fetchMock.mockImplementation((url: string) => {
      const parsed = new URL(url);
      expect(parsed.pathname).toMatch(/\/families\/options$/);
      expect(parsed.searchParams.get('search')).toBe('Noor & Co');
      const offset = Number(parsed.searchParams.get('offset'));
      return Promise.resolve(okJson({
        items: offset === 0 ? firstItems : [{ id: 'family-200', organization_id: 'org-a', name: 'Family 200', status: 'pending' }],
        total: 201,
        limit: 200,
        offset,
      }));
    });

    const options = await fetchChildFamilies('org-a', new AbortController().signal, ' Noor & Co ');
    expect(options).toHaveLength(201);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(options.find((option) => option.id === 'family-200')).toMatchObject({ status: 'pending' });
  });

  it('rejects cross-tenant or malformed family-options pages', async () => {
    fetchMock.mockResolvedValueOnce(okJson({
      items: [{ id: 'family-b', organization_id: 'org-b', name: 'Other', status: 'active' }],
      total: 1, limit: 200, offset: 0,
    }));
    await expect(fetchChildFamilies('org-a', new AbortController().signal)).rejects.toMatchObject({ status: 403 });

    fetchMock.mockResolvedValueOnce(okJson({
      items: [{ id: 'family-a', organization_id: 'org-a', name: 'Noor', status: 'active', guardians: [] }],
      total: 1, limit: 200, offset: 0,
    }));
    await expect(fetchChildFamilies('org-a', new AbortController().signal)).rejects.toThrow('invalid family record');
  });

  it('loads only the bounded child directory with encoded server filters and no rich bulk fetch', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage()));
    const page = await fetchChildDirectoryPage(DIRECTORY_ORG_ID, {
      search: ' Noor & Family ', status: 'active', careLane: 'daycare', familyId: DIRECTORY_FAMILY_ID,
      limit: 50, offset: 0,
    });
    expect(page.items[0]).toMatchObject({ id: DIRECTORY_CHILD_ID, care_lane: 'daycare' });
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.pathname).toMatch(/\/children\/directory$/);
    expect(url.pathname).not.toMatch(/\/children$/);
    expect(url.searchParams.get('search')).toBe('Noor & Family');
    expect(url.searchParams.get('status')).toBe('active');
    expect(url.searchParams.get('care_lane')).toBe('daycare');
    expect(url.searchParams.get('family_id')).toBe(DIRECTORY_FAMILY_ID);
    expect(url.searchParams.get('limit')).toBe('50');
  });

  it('accepts a future-reserved placement without presenting it as current', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage(
      [{ ...directoryItem, open_enrollment: { ...directoryEnrollment, placement_effective_date: '2026-08-01', start_date: '2026-08-01', placement_state: 'reserved' } }],
      1,
      50,
      0,
      { ...directoryCounts, reserved: 1 },
    )));
    const page = await fetchChildDirectoryPage(DIRECTORY_ORG_ID);
    expect(page.items[0].open_enrollment?.placement_state).toBe('reserved');
    expect(page.counts.reserved).toBe(1);
  });

  it('validates exact paging windows and filtered count reconciliation', async () => {
    const pageCounts = {
      total: 51, active: 50, inactive: 1, daycare: 40, out_of_school_care: 5,
      unassigned: 5, reserved: 2, needs_review: 1,
    };
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem], 51, 50, 50, pageCounts)));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID, { limit: 50, offset: 50 })).resolves.toMatchObject({ total: 51, offset: 50 });

    fetchMock.mockResolvedValueOnce(okJson(directoryPage([], 1, 50, 0, directoryCounts)));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('requested window');

    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem, directoryItem], 2, 50, 0, directoryCounts)));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('filters and counts');
  });

  it.each([
    ['extra item field', { ...directoryItem, health_care_number: 'private' }],
    ['invalid child UUID', { ...directoryItem, id: 'child-1' }],
    ['invalid calendar date', { ...directoryItem, date_of_birth: '2026-02-31' }],
    ['invalid care enum', { ...directoryItem, care_lane: 'school' }],
    ['invalid placement enum', { ...directoryItem, open_enrollment: { ...directoryEnrollment, placement_state: 'future' } }],
    ['extra enrollment field', { ...directoryItem, open_enrollment: { ...directoryEnrollment, is_active: true } }],
    ['external photo', { ...directoryItem, profile_photo_url: 'https://example.com/api/v1/children/photo', profile_photo_updated_at: '2026-07-15T00:00:00Z' }],
    ['cross-tenant item', { ...directoryItem, organization_id: '88888888-8888-4888-8888-888888888888' }],
    ['cross-child enrollment', { ...directoryItem, open_enrollment: { ...directoryEnrollment, child_id: '99999999-9999-4999-8999-999999999999' } }],
    ['incoherent current placement', { ...directoryItem, open_enrollment: { ...directoryEnrollment, room_id: null } }],
  ])('rejects malformed or unsafe directory rows: %s', async (_label, row) => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([row])));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toBeInstanceOf(ChildrenApiError);
  });

  it('rejects duplicate child and open-enrollment IDs', async () => {
    const secondChildId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    const duplicateChildCounts = { ...directoryCounts, total: 2, active: 2, daycare: 2 };
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem, directoryItem], 2, 50, 0, duplicateChildCounts)));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('duplicate child IDs');

    fetchMock.mockResolvedValueOnce(okJson(directoryPage([
      directoryItem,
      { ...directoryItem, id: secondChildId, open_enrollment: { ...directoryEnrollment, child_id: secondChildId } },
    ], 2, 50, 0, duplicateChildCounts)));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('duplicate enrollment IDs');
  });

  it('rejects malformed counts and cross-filter rows', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem], 1, 50, 0, { ...directoryCounts, inactive: 1 })));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('inconsistent');

    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem])));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID, { status: 'inactive' })).rejects.toBeInstanceOf(ChildrenApiError);
  });

  it('requires exact page and count keys', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...directoryPage(), debug: true }));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('invalid child-directory page');

    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem], 1, 50, 0, { ...directoryCounts, other: 0 })));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).rejects.toThrow('counts');
  });

  it('accepts only the protected photo route for the same child', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([{
      ...directoryItem,
      profile_photo_url: `/api/v1/children/${DIRECTORY_CHILD_ID}/photo`,
      profile_photo_updated_at: '2026-07-15T00:00:00Z',
    }])));
    await expect(fetchChildDirectoryPage(DIRECTORY_ORG_ID)).resolves.toMatchObject({
      items: [{ profile_photo_url: `/api/v1/children/${DIRECTORY_CHILD_ID}/photo` }],
    });
  });

  it.each([
    ['AbortError', () => { const error = new Error('aborted'); error.name = 'AbortError'; throw error; }],
    ['invalid JSON', () => { throw new SyntaxError('bad json'); }],
  ])('marks ambiguous child creation as unknown: %s', async (_label, failure) => {
    fetchMock.mockImplementationOnce(async () => failure());
    const caught = await createChild(buildChildCreateCommand(input), new Set(['family-a']), 'org-a').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it.each([
    ['tenant', { ...childResponse, organization_id: 'org-b' }],
    ['family', { ...childResponse, family_id: 'family-b' }],
  ])('locks the exact child command when a 2xx mutation projection crosses the %s boundary', async (_label, projection) => {
    fetchMock.mockResolvedValueOnce(okJson(projection));
    await expect(createChild(buildChildCreateCommand(input), new Set(['family-a']), 'org-a'))
      .rejects.toSatisfy((caught: unknown) => isCommandOutcomeUnknown(caught));
  });

  it.each([401, 403, 409, 422])('keeps a genuine HTTP %s child mutation rejection definite', async (status) => {
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({ detail: 'definite rejection' }) });
    const caught = await createChild(buildChildCreateCommand(input), new Set(['family-a']), 'org-a').catch((error) => error);
    expect(caught).toBeInstanceOf(ChildrenApiError);
    expect(caught).toMatchObject({ status, origin: 'http' });
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
  });

  it('does not turn a controlled stale 409 into an unknown outcome', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: { code: 'stale_childcare_resource', resource_type: 'child', current_version: 8 } }) });
    const caught = await updateChild('child-1', buildChildUpdateCommand(input, 2), new Set(['family-a']), 'org-a').catch((error) => error);
    expect(caught).toBeInstanceOf(ChildrenApiError);
    expect(caught.status).toBe(409);
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
  });

  it('fails closed when canonical child detail omits enrollment history', async () => {
    const { enrollments: _enrollments, ...incomplete } = childResponse;
    fetchMock.mockResolvedValueOnce(okJson(incomplete));
    await expect(fetchChildDetails('child-1', new Set(['family-a']), 'org-a', new AbortController().signal))
      .rejects.toThrow('enrollments');
  });

  it('requires an exact +1 version on a fresh child mutation projection', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...childResponse, version: 4, replayed: false }));
    const caught = await updateChild('child-1', buildChildUpdateCommand(input, 1), new Set(['family-a']), 'org-a')
      .catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it('requires exact +1 versions on fresh placement and lifecycle projections', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...activeEnrollment, version: 5, replayed: false }));
    const placementCaught = await approveChildEnrollmentPlacement(
      pendingEnrollment,
      'org-a',
      buildEnrollmentPlacementApprovalCommand({ room_id: 'room-1', effective_date: '2026-07-14' }, 1),
      [facility],
      placementOptions,
    ).catch((error) => error);
    expect(isCommandOutcomeUnknown(placementCaught)).toBe(true);

    fetchMock.mockResolvedValueOnce(okJson({
      ...activeEnrollment, status: 'ended', is_active: false, end_date: '2026-07-17', version: 8, replayed: false,
    }));
    const endCaught = await endChildEnrollment(activeEnrollment, 'org-a', buildEnrollmentEndCommand('2026-07-17', 2))
      .catch((error) => error);
    expect(isCommandOutcomeUnknown(endCaught)).toBe(true);
  });

  it.each([408, 425, 500])('locks the exact child command after ambiguous HTTP %s', async (status) => {
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({ detail: 'response not confirmed' }) });
    const caught = await createChild(buildChildCreateCommand(input), new Set(['family-a']), 'org-a').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it('retries an ambiguous child create with the identical operation id and intent', async () => {
    const command = buildChildCreateCommand(input);
    fetchMock
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: 'commit outcome unavailable' }) })
      .mockResolvedValueOnce(okJson({ ...childResponse, replayed: true }));

    await expect(createChild(command, new Set(['family-a']), 'org-a'))
      .rejects.toSatisfy((caught: unknown) => isCommandOutcomeUnknown(caught));
    await expect(createChild(command, new Set(['family-a']), 'org-a'))
      .resolves.toMatchObject({ id: 'child-1', replayed: true });

    const firstBody = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    const retryBody = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body));
    expect(retryBody).toEqual(firstBody);
    expect(retryBody.client_operation_id).toBe(command.clientOperationId);
  });

  it('parses a tenant-checked child profile with non-replayed nested records', async () => {
    fetchMock.mockResolvedValueOnce(okJson({
      ...childResponse,
      enrollments: [{ ...activeEnrollment, facility_name: 'North Centre', program_name: 'Preschool', program_type: 'daycare', room_name: 'Starlight' }],
      current_enrollment: { ...activeEnrollment, facility_name: 'North Centre', program_name: 'Preschool', program_type: 'daycare', room_name: 'Starlight' },
      family: {
        id: 'family-a', organization_id: 'org-a', name: 'Noor Family', file_number: null, status: 'active', additional_notes: null,
        photo_consent: true, field_trip_consent: false, emergency_medical_consent: true,
        guardians: [], emergency_contacts: [], version: 1, replayed: false,
      },
    }));
    const profile = await fetchChildProfile('child-1', 'org-a');
    expect(profile.current_enrollment?.room_name).toBe('Starlight');
  });

  it('uses authenticated multipart photo routes and rejects external URLs', async () => {
    fetchMock.mockResolvedValueOnce(okJson({
      child_id: 'child-1', url: '/api/v1/children/child-1/photo', content_type: 'image/jpeg', size_bytes: 1200,
      width: 600, height: 800, sha256: 'abc123', original_filename: 'portrait.png', updated_at: '2026-07-15T12:00:00Z',
    }));
    await uploadChildPhoto('child-1', new File(['image'], 'portrait.png', { type: 'image/png' }));
    expect((fetchMock.mock.calls[0][1] as RequestInit).body).toBeInstanceOf(FormData);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204 });
    await deleteChildPhoto('child-1');
    await expect(fetchChildPhoto('https://example.com/api/v1/children/child-1/photo'))
      .rejects.toMatchObject({ status: 403 } satisfies Partial<ChildrenApiError>);
  });
});

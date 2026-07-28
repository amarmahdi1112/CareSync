import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isCommandOutcomeUnknown } from '../../api/childcareCommand';
import {
  RoomsApiError,
  approveRoomPlacement,
  approveRoomPlacementsBatch,
  buildRoomPlacementPlan,
  createRoom,
  fetchRoomDeactivationImpact,
  fetchRoomPlacementReviews,
  fetchRoomRoster,
  parseFacility,
  parseProgram,
  parseRoom,
  parseRoomPlacementReview,
  parseRoomRoster,
  updateRoom,
  type RoomRecord,
  type RoomWorkspace,
} from './roomsApi';

const room: RoomRecord = {
  id: 'room-1', organization_id: 'org', facility_id: 'facility', program_id: 'program', name: 'North',
  capacity: 10, age_group: 'Infant', minimum_age_months: 0, maximum_age_months: 18, is_active: true,
};

const rosterChild = {
  child_id: 'child-1', enrollment_id: 'enrollment-1', family_id: 'family-1', family_name: 'Noor',
  first_name: 'Amina', middle_name: null, last_name: 'Noor', date_of_birth: '2022-04-12', age_group: 'Preschool',
  child_is_active: true, facility_id: 'facility', program_id: 'program', room_id: 'room-1', enrollment_status: 'active',
  enrollment_version: 1, start_date: '2026-07-01', placement_effective_date: '2026-07-01', end_date: null,
};

const rosterPayload = {
  facility_id: 'facility',
  facility_date: '2026-07-17',
  rooms: [{ room_id: 'room-1', facility_id: 'facility', program_id: 'program', name: 'North', capacity: 10, is_active: true, occupancy: 1, children: [rosterChild], reserved_children: [] }],
  unassigned_children: [],
};

const workspace: RoomWorkspace = {
  facilities: [{ id: 'facility', organization_id: 'org', name: 'Main', license_number: null, licensed_capacity: 40, city: null, province: 'Alberta', timezone: 'America/Edmonton', status: 'active' }],
  programs: [{ id: 'program', organization_id: 'org', facility_id: 'facility', name: 'Daycare', program_type: 'daycare', capacity: 10, minimum_age_months: 0, maximum_age_months: 71, is_active: true }],
  rooms: [room],
};

const placementCandidate = {
  room_id: 'room-1', room_name: 'North', room_age_group: 'Infant', minimum_age_months: 0,
  maximum_age_months: 18, capacity: 10, occupancy: 9, available_places: 1,
  program_id: 'program', program_name: 'Daycare', program_type: 'daycare',
};

const placementReview = {
  organization_id: 'org', facility_id: 'facility', enrollment_id: 'enrollment-1', child_id: 'child-1',
  enrollment_version: 1,
  child_first_name: 'Amina', child_middle_name: null, child_last_name: 'Noor', date_of_birth: '2025-01-15',
  enrollment_start_date: '2025-01-01', effective_date: '2026-07-15', age_months: 18,
  suggestion_state: 'one', candidates: [placementCandidate],
};

function placementApproval(
  review = placementReview,
  overrides: Record<string, unknown> = {},
) {
  const candidate = review.candidates[0];
  return {
    id: review.enrollment_id,
    organization_id: review.organization_id,
    facility_id: review.facility_id,
    child_id: review.child_id,
    program_id: candidate.program_id,
    room_id: candidate.room_id,
    placement_effective_date: review.effective_date,
    start_date: review.enrollment_start_date,
    end_date: null,
    status: 'active',
    version: review.enrollment_version + 1,
    replayed: false,
    is_active: true,
    facility_name: 'Main',
    program_name: candidate.program_name,
    program_type: candidate.program_type,
    room_name: candidate.room_name,
    created_at: '2026-07-15T18:00:00Z',
    updated_at: '2026-07-15T18:00:00Z',
    ...overrides,
  };
}

describe('rooms API adapters', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('normalizes the Basic facility, program, and room contracts', () => {
    expect(parseFacility({ id: 'facility', organization_id: 'org', name: 'Main', license_number: null, licensed_capacity: 40, city: null, province: 'AB', timezone: 'America/Edmonton', status: 'active' }).licensed_capacity).toBe(40);
    expect(parseProgram({ id: 'program', organization_id: 'org', facility_id: 'facility', name: 'Infants', program_type: 'daycare', capacity: 0, minimum_age_months: null, maximum_age_months: null, is_active: true }).capacity).toBe(0);
    expect(parseRoom({ id: 'room', organization_id: 'org', facility_id: 'facility', program_id: null, name: 'North', capacity: 10, age_group: null, minimum_age_months: null, maximum_age_months: null, is_active: true }).capacity).toBe(10);
  });

  it('rejects nullable values for non-null capacity fields', () => {
    expect(() => parseFacility({ id: 'facility', organization_id: 'org', name: 'Main', license_number: null, licensed_capacity: null, city: null, province: 'AB', timezone: 'America/Edmonton', status: 'active' })).toThrow(RoomsApiError);
    expect(() => parseProgram({ id: 'program', organization_id: 'org', facility_id: 'facility', name: 'Infants', program_type: 'daycare', capacity: null, minimum_age_months: null, maximum_age_months: null, is_active: true })).toThrow(RoomsApiError);
  });

  it('requires a supported licensed program type', () => {
    expect(() => parseProgram({ id: 'program', organization_id: 'org', facility_id: 'facility', name: 'Infants', program_type: null, capacity: 12, minimum_age_months: null, maximum_age_months: null, is_active: true })).toThrow(RoomsApiError);
    expect(parseProgram({ id: 'program', organization_id: 'org', facility_id: 'facility', name: 'OSC', program_type: 'osc', capacity: 20, minimum_age_months: null, maximum_age_months: null, is_active: true }).program_type).toBe('out_of_school_care');
  });

  it('sends both required room age bounds without dropping a zero minimum', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => room });
    await createRoom({ facility_id: 'facility', program_id: 'program', name: 'North', capacity: 10, age_group: 'Infant', minimum_age_months: 0, maximum_age_months: 18, is_active: true }, 'org');
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toMatchObject({ minimum_age_months: 0, maximum_age_months: 18 });

    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ...room, maximum_age_months: 20 }) });
    await updateRoom('room-1', { facility_id: 'facility', program_id: 'program', name: 'North', capacity: 10, age_group: 'Infant', minimum_age_months: 0, maximum_age_months: 20, is_active: true }, 'org');
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toMatchObject({ minimum_age_months: 0, maximum_age_months: 20 });
  });

  it('loads a room-scoped deactivation impact and sends the audited confirmation', async () => {
    const impact = { organization_id: 'org', entity_type: 'room', entity_id: 'room-1', entity_name: 'North', active_programs: 0, active_rooms: 0, open_enrollments: 0, open_attendance_intervals: 0, active_staff_assignments: 1, open_staff_shifts: 0, blockers: [], warnings: ['Assignment retained'], can_deactivate: true, confirmation_text: 'North' };
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => impact });
    await expect(fetchRoomDeactivationImpact('room-1', 'org')).resolves.toEqual(impact);

    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ...room, is_active: false }) });
    await updateRoom('room-1', { facility_id: 'facility', program_id: 'program', name: 'North', capacity: 10, age_group: 'Infant', minimum_age_months: 0, maximum_age_months: 18, is_active: false, deactivation_confirmation: 'North', deactivation_reason: 'Seasonal closure' }, 'org');
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toMatchObject({ is_active: false, deactivation_confirmation: 'North', deactivation_reason: 'Seasonal closure' });
  });

  it('parses every room roster row and rejects inconsistent occupancy', () => {
    expect(parseRoomRoster(rosterPayload).rooms[0]).toMatchObject({ room_id: 'room-1', occupancy: 1, capacity: 10 });
    expect(() => parseRoomRoster({ ...rosterPayload, rooms: [{ ...rosterPayload.rooms[0], occupancy: 2 }] })).toThrow('occupancy');
  });

  it('loads a roster only when it matches the verified facility workspace', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => rosterPayload });
    await expect(fetchRoomRoster('facility', 'org', [room])).resolves.toEqual(parseRoomRoster(rosterPayload));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/room-rosters\?facility_id=facility$/);
    await expect(fetchRoomRoster('elsewhere', 'org', [room])).rejects.toBeInstanceOf(RoomsApiError);
  });

  it('keeps current occupancy separate from reserved and unassigned enrollment projections', () => {
    const reserved = {
      ...rosterChild,
      child_id: 'child-2',
      enrollment_id: 'enrollment-2',
      first_name: 'Sam',
      enrollment_status: 'paused',
      enrollment_version: 3,
      placement_effective_date: '2026-08-01',
    };
    const unassigned = {
      ...rosterChild,
      child_id: 'child-3',
      enrollment_id: 'enrollment-3',
      first_name: 'Omar',
      program_id: null,
      room_id: null,
      enrollment_status: 'pending',
      placement_effective_date: null,
    };
    const parsed = parseRoomRoster({
      ...rosterPayload,
      rooms: [{ ...rosterPayload.rooms[0], reserved_children: [reserved] }],
      unassigned_children: [unassigned],
    });
    expect(parsed.rooms[0].occupancy).toBe(1);
    expect(parsed.rooms[0].children).toHaveLength(1);
    expect(parsed.rooms[0].reserved_children).toHaveLength(1);
    expect(parsed.unassigned_children).toHaveLength(1);
  });

  it('strictly derives none, one, and multiple placement states from available capacity', () => {
    expect(parseRoomPlacementReview(placementReview).suggestion_state).toBe('one');
    const fullCandidate = { ...placementCandidate, occupancy: 10, available_places: 0 };
    expect(parseRoomPlacementReview({ ...placementReview, suggestion_state: 'none', candidates: [fullCandidate] })).toMatchObject({
      suggestion_state: 'none', candidates: [{ available_places: 0 }],
    });
    const secondCandidate = { ...placementCandidate, room_id: 'room-2', room_name: 'South' };
    expect(parseRoomPlacementReview({ ...placementReview, suggestion_state: 'multiple', candidates: [placementCandidate, secondCandidate] }).suggestion_state).toBe('multiple');
    expect(() => parseRoomPlacementReview({ ...placementReview, suggestion_state: 'multiple' })).toThrow('did not match');
    expect(() => parseRoomPlacementReview({ ...placementReview, candidates: [{ ...placementCandidate, available_places: 2 }] })).toThrow('capacity');
  });

  it('preserves every compatible backend candidate while preferring the narrowest interval', () => {
    const broadCandidate = { ...placementCandidate, room_id: 'room-2', room_name: 'All ages', maximum_age_months: 71 };
    const result = parseRoomPlacementReview({ ...placementReview, candidates: [broadCandidate, placementCandidate] });
    expect(result.suggestion_state).toBe('one');
    expect(result.candidates.map((candidate) => candidate.room_id)).toEqual(['room-2', 'room-1']);
  });

  it('rejects placement review organization, facility, room, and enrollment duplication drift', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ ...placementReview, organization_id: 'other' }] });
    await expect(fetchRoomPlacementReviews('facility', 'org', workspace)).rejects.toThrow('organization boundary');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ ...placementReview, facility_id: 'other' }] });
    await expect(fetchRoomPlacementReviews('facility', 'org', workspace)).rejects.toThrow('facility boundary');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ ...placementReview, candidates: [{ ...placementCandidate, room_id: 'outside' }] }] });
    await expect(fetchRoomPlacementReviews('facility', 'org', workspace)).rejects.toThrow('facility boundary');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => [placementReview, placementReview] });
    await expect(fetchRoomPlacementReviews('facility', 'org', workspace)).rejects.toThrow('twice');
  });

  it('approves only the reviewed enrollment and exact room/date payload', async () => {
    const parsedReview = parseRoomPlacementReview(placementReview);
    const approval = placementApproval();
    const plan = buildRoomPlacementPlan(parsedReview, 'room-1');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => approval });
    await expect(approveRoomPlacement(plan, 'org')).resolves.toEqual(approval);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/enrollments\/enrollment-1\/placement-approval$/);
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({
      room_id: 'room-1', effective_date: '2026-07-15', expected_version: 1,
      client_operation_id: plan.command.clientOperationId,
    });
    expect(() => buildRoomPlacementPlan(parsedReview, 'not-reviewed')).toThrow('recommended room');
  });

  it('rejects a fresh placement response that skips the exact next enrollment version', async () => {
    const plan = buildRoomPlacementPlan(parseRoomPlacementReview(placementReview), 'room-1');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => placementApproval(placementReview, { version: 3, replayed: false }) });
    const caught = await approveRoomPlacement(plan, 'org').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it('accepts a future approved placement as reserved and a replayed later lifecycle projection', async () => {
    const parsedReview = parseRoomPlacementReview(placementReview);
    const futurePlan = buildRoomPlacementPlan(parsedReview, 'room-1');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => placementApproval(placementReview, { is_active: false }) });
    await expect(approveRoomPlacement(futurePlan, 'org')).resolves.toMatchObject({ status: 'active', is_active: false });

    const replayPlan = buildRoomPlacementPlan(parsedReview, 'room-1');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => placementApproval(placementReview, { replayed: true, status: 'paused', is_active: false, version: 4 }) });
    await expect(approveRoomPlacement(replayPlan, 'org')).resolves.toMatchObject({ replayed: true, status: 'paused' });
  });

  it('approves a reviewed placement plan through one strict batch request', async () => {
    const first = parseRoomPlacementReview(placementReview);
    const secondCandidate = { ...placementCandidate, room_id: 'room-2', room_name: 'South', program_id: 'program-2', program_name: 'Daycare South' };
    const second = parseRoomPlacementReview({ ...placementReview, enrollment_id: 'enrollment-2', child_id: 'child-2', child_first_name: 'Sam', candidates: [secondCandidate] });
    const plans = [buildRoomPlacementPlan(first, 'room-1'), buildRoomPlacementPlan(second, 'room-2')];
    const approvals = [placementApproval(), placementApproval({ ...placementReview, enrollment_id: 'enrollment-2', child_id: 'child-2', child_first_name: 'Sam', candidates: [secondCandidate] })];
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ approvals }) });
    await expect(approveRoomPlacementsBatch(plans, 'org')).resolves.toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/room-placement-approvals\/batch$/);
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(body.placements).toEqual([
      { enrollment_id: 'enrollment-1', room_id: 'room-1', effective_date: '2026-07-15', expected_version: 1, client_operation_id: plans[0].command.clientOperationId },
      { enrollment_id: 'enrollment-2', room_id: 'room-2', effective_date: '2026-07-15', expected_version: 1, client_operation_id: plans[1].command.clientOperationId },
    ]);
  });

  it('rejects a batch response that does not exactly match every reviewed placement', async () => {
    const parsed = parseRoomPlacementReview(placementReview);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ approvals: [placementApproval(placementReview, { room_id: 'other-room' })] }) });
    await expect(approveRoomPlacementsBatch([buildRoomPlacementPlan(parsed, 'room-1')], 'org')).rejects.toSatisfy((caught: unknown) => isCommandOutcomeUnknown(caught));
  });

  it('locks and retries the exact placement command after an HTTP 500 ambiguity', async () => {
    const plan = buildRoomPlacementPlan(parseRoomPlacementReview(placementReview), 'room-1');
    fetchMock
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: 'projection failed' }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => placementApproval(placementReview, { replayed: true }) });
    const caught = await approveRoomPlacement(plan, 'org').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
    await expect(approveRoomPlacement(plan, 'org')).resolves.toMatchObject({ replayed: true });
    const firstBody = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    const retryBody = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body));
    expect(retryBody).toEqual(firstBody);
    expect(retryBody.client_operation_id).toBe(plan.command.clientOperationId);
  });
});

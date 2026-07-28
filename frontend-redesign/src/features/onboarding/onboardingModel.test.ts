import { describe, expect, it } from 'vitest';
import {
  EMPTY_ONBOARDING_DRAFT,
  draftFromResponse,
  reconcileCareStructure,
  recoverCareStructureIds,
  validateFacility,
  validateOrganization,
  validateRooms,
} from './onboardingModel';
import type { OnboardingDraft, OnboardingResponse, ProgramRecord, RoomRecord } from './types';

function response(draft: Record<string, unknown> = {}): OnboardingResponse {
  return {
    organization_id: 'org-1', status: 'in_progress', current_step: 'rooms', completed_steps: ['organization', 'facility'], draft, completed_at: null,
    organization: { id: 'org-1', name: 'Centre', legal_name: null, status: 'active', email: null, phone: null, timezone: 'America/Edmonton', preferences: {} },
    facilities: [{ id: 'facility-1', organization_id: 'org-1', name: 'Main', license_number: null, status: 'active', email: null, phone: null, street_address: '1 Main St', city: 'Calgary', province: 'Alberta', postal_code: 'T2P 1J9', timezone: 'America/Edmonton', licensed_capacity: 80, opening_time: '07:00:00', closing_time: '18:00:00' }],
  };
}

function program(id: string, type: ProgramRecord['program_type'], name: string): ProgramRecord {
  return { id, organization_id: 'org-1', facility_id: 'facility-1', name, program_type: type, capacity: type === 'daycare' ? 50 : 30, minimum_age_months: null, maximum_age_months: null, is_active: true };
}

function room(id: string, name: string, programId: string | null, overrides: Partial<RoomRecord> = {}): RoomRecord {
  return { id, organization_id: 'org-1', facility_id: 'facility-1', program_id: programId, name, capacity: 10, age_group: null, is_active: true, ...overrides };
}

describe('Basic onboarding validation', () => {
  it('requires organization identity', () => {
    expect(validateOrganization({ ...EMPTY_ONBOARDING_DRAFT.organization, name: '' })).toHaveProperty('organization.name');
  });

  it('rejects impossible facility hours and capacity', () => {
    const errors = validateFacility({ ...EMPTY_ONBOARDING_DRAFT.facility, name: 'Centre', streetAddress: '1 Main St', city: 'Calgary', postalCode: 'T2P 1J9', licensedCapacity: '0', openingTime: '18:00', closingTime: '07:00' });
    expect(errors).toHaveProperty('facility.licensedCapacity');
    expect(errors).toHaveProperty('facility.closingTime');
  });

  it('requires a licensed service and at least one assigned room', () => {
    const errors = validateRooms({ ...EMPTY_ONBOARDING_DRAFT, selectedProgramTypes: [], rooms: [] });
    expect(errors).toHaveProperty('selectedProgramTypes');
    expect(errors).toHaveProperty('rooms');
  });

  it('validates each repeated room against its assigned program', () => {
    const rooms = [{ ...EMPTY_ONBOARDING_DRAFT.rooms[0], draftKey: 'osc-room', programType: 'out_of_school_care' as const, name: 'OSC room', capacity: '12' }];
    const errors = validateRooms({
      ...EMPTY_ONBOARDING_DRAFT,
      selectedProgramTypes: ['daycare', 'out_of_school_care'],
      programs: {
        daycare: { ...EMPTY_ONBOARDING_DRAFT.programs.daycare, capacity: '50' },
        out_of_school_care: { ...EMPTY_ONBOARDING_DRAFT.programs.out_of_school_care, capacity: '10' },
      },
      rooms,
    });
    expect(errors['rooms.osc-room.capacity']).toContain('assigned program');
  });

  it('rejects duplicate room names and combined room capacity above the assigned program', () => {
    const errors = validateRooms({
      ...EMPTY_ONBOARDING_DRAFT,
      programs: { ...EMPTY_ONBOARDING_DRAFT.programs, daycare: { ...EMPTY_ONBOARDING_DRAFT.programs.daycare, capacity: '20' } },
      rooms: [
        { draftKey: 'a', id: null, programType: 'daycare', name: 'Infant', capacity: '12', ageGroup: '' },
        { draftKey: 'b', id: null, programType: 'daycare', name: ' infant ', capacity: '11', ageGroup: '' },
      ],
    });
    expect(errors['rooms.a.name']).toContain('unique');
    expect(errors['rooms.b.name']).toContain('unique');
    expect(errors['programs.daycare.capacity']).toContain('Combined');
  });
});

describe('Basic onboarding care-structure restoration', () => {
  it('defaults safely to Daycare with one empty repeatable room', () => {
    const draft = draftFromResponse(response());
    expect(draft.selectedProgramTypes).toEqual(['daycare']);
    expect(draft.programs.out_of_school_care.name).toBe('OSC');
    expect(draft.rooms).toHaveLength(1);
  });

  it('normalizes legacy province and room age-group labels for constrained selectors', () => {
    const draft = draftFromResponse({
      ...response({
        rooms: [{ draftKey: 'school-room', programType: 'daycare', name: 'School room', capacity: '12', ageGroup: 'school age' }],
      }),
      facilities: [{ ...response().facilities[0], province: 'AB' }],
    });
    expect(draft.facility.province).toBe('Alberta');
    expect(draft.rooms[0].ageGroup).toBe('School-Age');
  });

  it('migrates the former single program and room draft', () => {
    const draft = draftFromResponse(response({
      program: { id: 'osc-1', name: 'School Age', programType: 'osc', capacity: '25', minimumAgeMonths: '60', maximumAgeMonths: '144' },
      room: { id: null, name: 'Blue room', capacity: '20', ageGroup: 'School-Age' },
    }));
    expect(draft.selectedProgramTypes).toEqual(['out_of_school_care']);
    expect(draft.programs.out_of_school_care).toMatchObject({ id: 'osc-1', name: 'School Age' });
    expect(draft.rooms[0]).toMatchObject({ name: 'Blue room', programType: 'out_of_school_care' });
  });

  it('restores an unlimited rooms array and stable draft keys', () => {
    const draft = draftFromResponse(response({
      selectedProgramTypes: ['daycare', 'out_of_school_care'],
      programs: { daycare: { id: 'daycare-1', name: 'Early Years', capacity: '45' }, out_of_school_care: { id: 'osc-1', name: 'School Crew', capacity: '30' } },
      rooms: [
        { draftKey: 'infant-draft', id: null, programType: 'daycare', name: 'Infant', capacity: '12' },
        { draftKey: 'osc-draft', id: null, programType: 'out_of_school_care', name: 'OSC North', capacity: '20' },
      ],
    }));
    expect(draft.rooms.map((value) => value.draftKey)).toEqual(['infant-draft', 'osc-draft']);
    expect(draft.rooms[1].programType).toBe('out_of_school_care');
  });

  it('reconciles saved rooms by id and unique name without depending on API order', () => {
    const base = draftFromResponse(response({
      selectedProgramTypes: ['daycare', 'out_of_school_care'],
      programs: { daycare: { name: 'Edited Daycare', capacity: '50' }, out_of_school_care: { name: 'Edited OSC', capacity: '30' } },
      rooms: [
        { draftKey: 'osc-edit', id: 'room-osc', programType: 'out_of_school_care', name: 'Edited OSC room', capacity: '18', ageGroup: 'Edited' },
        { draftKey: 'infant-edit', id: null, programType: 'daycare', name: 'Infant North', capacity: '14', ageGroup: 'Edited infant' },
      ],
    }));
    const programs = [program('osc-1', 'out_of_school_care', 'School Crew'), program('daycare-1', 'daycare', 'Early Years')];
    const restored = reconcileCareStructure(base, programs, [room('room-infant', 'infant north', 'daycare-1'), room('room-osc', 'Old OSC room', 'osc-1')]);
    expect(restored.rooms[0]).toMatchObject({ id: 'room-osc', name: 'Edited OSC room', capacity: '18', programType: 'out_of_school_care' });
    expect(restored.rooms[1]).toMatchObject({ id: 'room-infant', name: 'Infant North', capacity: '14', programType: 'daycare' });
  });

  it('adds unmatched active API rooms while ignoring inactive and pending-archive rooms', () => {
    const base: OnboardingDraft = { ...draftFromResponse(response()), rooms: [], archivedRoomIds: ['room-archived'] };
    const restored = reconcileCareStructure(base, [program('daycare-1', 'daycare', 'Daycare')], [
      room('room-active', 'Active room', 'daycare-1'),
      room('room-inactive', 'Inactive room', 'daycare-1', { is_active: false }),
      room('room-archived', 'Pending archive', 'daycare-1'),
    ]);
    expect(restored.rooms.map((value) => value.id)).toEqual(['room-active']);
  });

  it('does not invent Daycare when an existing facility only has OSC', () => {
    const restored = reconcileCareStructure(draftFromResponse(response()), [program('osc-1', 'out_of_school_care', 'School Crew')], []);
    expect(restored.selectedProgramTypes).toEqual(['out_of_school_care']);
    expect(restored.rooms[0].programType).toBe('out_of_school_care');
  });
});

describe('Basic onboarding interrupted-create recovery', () => {
  it('recovers a program id by canonical type without overwriting edits', () => {
    const current: OnboardingDraft = {
      ...draftFromResponse(response()),
      selectedProgramTypes: ['daycare', 'out_of_school_care'],
      programs: {
        daycare: { id: 'daycare-1', name: 'Edited Early Years', capacity: '55', minimumAgeMonths: '10', maximumAgeMonths: '60' },
        out_of_school_care: { id: null, name: 'My edited OSC name', capacity: '31', minimumAgeMonths: '60', maximumAgeMonths: '144' },
      },
    };
    const recovered = recoverCareStructureIds(current, [program('daycare-1', 'daycare', 'Old'), program('osc-committed', 'out_of_school_care', 'Old OSC')], []);
    expect(recovered.programs.out_of_school_care).toMatchObject({ id: 'osc-committed', name: 'My edited OSC name', capacity: '31' });
  });

  it('recovers every committed room by unique normalized name without overwriting edits', () => {
    const current: OnboardingDraft = {
      ...draftFromResponse(response()),
      rooms: [
        { draftKey: 'infant-edit', id: null, programType: 'daycare', name: '  Infant North  ', capacity: '14', ageGroup: 'Edited infant' },
        { draftKey: 'toddler-edit', id: null, programType: 'daycare', name: 'Toddler', capacity: '16', ageGroup: 'Edited toddler' },
      ],
    };
    const recovered = recoverCareStructureIds(current, [], [room('room-toddler', 'toddler', 'daycare-1'), room('room-infant', 'infant north', 'daycare-1')]);
    expect(recovered.rooms).toEqual([
      { ...current.rooms[0], id: 'room-infant' },
      { ...current.rooms[1], id: 'room-toddler' },
    ]);
  });

  it('reuses a removed saved room with the same name instead of creating a duplicate', () => {
    const current: OnboardingDraft = {
      ...draftFromResponse(response()),
      rooms: [{ draftKey: 'replacement', id: null, programType: 'daycare', name: 'Infant', capacity: '15', ageGroup: 'New edits' }],
      archivedRoomIds: ['room-infant'],
    };
    const recovered = recoverCareStructureIds(current, [], [room('room-infant', 'Infant', 'daycare-1')]);
    expect(recovered.rooms[0]).toMatchObject({ id: 'room-infant', capacity: '15', ageGroup: 'New edits' });
    expect(recovered.archivedRoomIds).toEqual([]);
  });

  it('does not recover records from another facility', () => {
    const current: OnboardingDraft = { ...draftFromResponse(response()), rooms: [{ ...EMPTY_ONBOARDING_DRAFT.rooms[0], name: 'Infant North' }] };
    const recovered = recoverCareStructureIds(current, [{ ...program('other', 'daycare', 'Elsewhere'), facility_id: 'facility-2' }], [room('room-other', 'Infant North', null, { facility_id: 'facility-2' })]);
    expect(recovered).toBe(current);
  });
});

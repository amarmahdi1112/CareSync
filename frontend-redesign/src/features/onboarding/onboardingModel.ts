import {
  PROGRAM_TYPES,
  PROGRAM_TYPE_LABELS,
  isProgramType,
  normalizeProgramType,
  type ProgramType,
} from '../../models/programTypes';
import { normalizeCanadianProvince, normalizeRoomAgeGroup } from '../../models/domainOptions';
import type {
  OnboardingDraft,
  OnboardingResponse,
  OnboardingStep,
  ProgramDraft,
  ProgramRecord,
  RoomDraft,
  RoomRecord,
} from './types';

export type DraftErrors = Record<string, string>;

export const STEP_ORDER: OnboardingStep[] = ['organization', 'facility', 'rooms', 'review'];

const EMPTY_PROGRAMS: Record<ProgramType, ProgramDraft> = {
  daycare: { id: null, name: 'Daycare', capacity: '', minimumAgeMonths: '', maximumAgeMonths: '' },
  out_of_school_care: { id: null, name: 'OSC', capacity: '', minimumAgeMonths: '', maximumAgeMonths: '' },
};

export function createEmptyRoomDraft(draftKey = 'room-1'): RoomDraft {
  return { draftKey, id: null, programType: 'daycare', name: '', capacity: '', ageGroup: '' };
}

export const EMPTY_ONBOARDING_DRAFT: OnboardingDraft = {
  organization: { name: '', legalName: '', email: '', phone: '', timezone: 'America/Edmonton' },
  facility: { id: null, name: '', licenseNumber: '', email: '', phone: '', streetAddress: '', city: '', province: 'Alberta', postalCode: '', timezone: 'America/Edmonton', licensedCapacity: '', openingTime: '07:00', closingTime: '18:00' },
  selectedProgramTypes: ['daycare'],
  programs: {
    daycare: { ...EMPTY_PROGRAMS.daycare },
    out_of_school_care: { ...EMPTY_PROGRAMS.out_of_school_care },
  },
  rooms: [createEmptyRoomDraft()],
  archivedRoomIds: [],
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const POSTAL = /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/;

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function nullableText(value: unknown): string | null {
  const result = text(value);
  return result || null;
}

function uniqueProgramTypes(values: unknown[]): ProgramType[] {
  return [...new Set(values.map(normalizeProgramType).filter((value): value is ProgramType => Boolean(value)))];
}

function programDraft(value: unknown, fallback: ProgramDraft): ProgramDraft {
  const saved = object(value);
  return {
    id: nullableText(saved.id) ?? fallback.id,
    name: text(saved.name, fallback.name),
    capacity: text(saved.capacity, fallback.capacity),
    minimumAgeMonths: text(saved.minimumAgeMonths, text(saved.minimum_age_months, fallback.minimumAgeMonths)),
    maximumAgeMonths: text(saved.maximumAgeMonths, text(saved.maximum_age_months, fallback.maximumAgeMonths)),
  };
}

function savedPrograms(value: unknown): Partial<Record<ProgramType, ProgramDraft>> {
  const result: Partial<Record<ProgramType, ProgramDraft>> = {};
  if (Array.isArray(value)) {
    value.forEach((entry) => {
      const candidate = object(entry);
      const type = normalizeProgramType(candidate.programType ?? candidate.program_type ?? candidate.type);
      if (type) result[type] = programDraft(candidate, EMPTY_PROGRAMS[type]);
    });
    return result;
  }
  const candidate = object(value);
  PROGRAM_TYPES.forEach((type) => {
    if (candidate[type] !== undefined) result[type] = programDraft(candidate[type], EMPTY_PROGRAMS[type]);
  });
  return result;
}

function restoredRoom(value: unknown, index: number, selectedTypes: ProgramType[]): RoomDraft {
  const saved = object(value);
  const requestedType = normalizeProgramType(saved.programType ?? saved.program_type);
  return {
    draftKey: text(saved.draftKey, text(saved.key, text(saved.id, `room-${index + 1}`))),
    id: nullableText(saved.id),
    programType: requestedType && selectedTypes.includes(requestedType) ? requestedType : selectedTypes[0] || '',
    name: text(saved.name),
    capacity: text(saved.capacity),
    ageGroup: normalizeRoomAgeGroup(text(saved.ageGroup, text(saved.age_group))),
  };
}

/** Restores the keyed programs, repeatable rooms, and both former single-record shapes. */
export function draftFromResponse(response: OnboardingResponse): OnboardingDraft {
  const saved = object(response.draft);
  const savedFacility = object(saved.facility);
  const facility = response.facilities[0];
  const restoredPrograms = savedPrograms(saved.programs);
  const legacyProgram = object(saved.program);
  const legacyType = normalizeProgramType(legacyProgram.programType ?? legacyProgram.program_type);
  if (legacyType && !restoredPrograms[legacyType]) {
    restoredPrograms[legacyType] = programDraft(legacyProgram, EMPTY_PROGRAMS[legacyType]);
  }

  const explicitSelection = Array.isArray(saved.selectedProgramTypes)
    ? uniqueProgramTypes(saved.selectedProgramTypes)
    : [];
  const restoredTypes = PROGRAM_TYPES.filter((type) => Boolean(restoredPrograms[type]));
  const selectedProgramTypes = explicitSelection.length
    ? explicitSelection
    : restoredTypes.length
      ? restoredTypes
      : legacyType
        ? [legacyType]
        : ['daycare' as const];

  const savedRoomValues = Array.isArray(saved.rooms)
    ? saved.rooms
    : Object.keys(object(saved.room)).length
      ? [saved.room]
      : [];
  const rooms = savedRoomValues.length
    ? savedRoomValues.map((value, index) => restoredRoom(value, index, selectedProgramTypes))
    : [{ ...createEmptyRoomDraft(), programType: selectedProgramTypes[0] || '' }];
  const archivedRoomIds = Array.isArray(saved.archivedRoomIds)
    ? [...new Set(saved.archivedRoomIds.filter((value): value is string => typeof value === 'string' && Boolean(value)))]
    : [];

  return {
    organization: {
      name: response.organization.name || text(object(saved.organization).name),
      legalName: response.organization.legal_name || text(object(saved.organization).legalName),
      email: response.organization.email || text(object(saved.organization).email),
      phone: response.organization.phone || text(object(saved.organization).phone),
      timezone: response.organization.timezone || 'America/Edmonton',
    },
    facility: {
      id: facility?.id || text(savedFacility.id) || null,
      name: facility?.name || text(savedFacility.name),
      licenseNumber: facility?.license_number || text(savedFacility.licenseNumber),
      email: facility?.email || text(savedFacility.email),
      phone: facility?.phone || text(savedFacility.phone),
      streetAddress: facility?.street_address || text(savedFacility.streetAddress),
      city: facility?.city || text(savedFacility.city),
      province: normalizeCanadianProvince(facility?.province || text(savedFacility.province, 'Alberta')),
      postalCode: facility?.postal_code || text(savedFacility.postalCode),
      timezone: facility?.timezone || text(savedFacility.timezone, 'America/Edmonton'),
      licensedCapacity: facility ? String(facility.licensed_capacity) : text(savedFacility.licensedCapacity),
      openingTime: facility?.opening_time?.slice(0, 5) || text(savedFacility.openingTime, '07:00'),
      closingTime: facility?.closing_time?.slice(0, 5) || text(savedFacility.closingTime, '18:00'),
    },
    selectedProgramTypes,
    programs: {
      daycare: restoredPrograms.daycare || { ...EMPTY_PROGRAMS.daycare },
      out_of_school_care: restoredPrograms.out_of_school_care || { ...EMPTY_PROGRAMS.out_of_school_care },
    },
    rooms,
    archivedRoomIds,
  };
}

function recordToProgramDraft(record: ProgramRecord): ProgramDraft {
  return {
    id: record.id,
    name: record.name,
    capacity: String(record.capacity),
    minimumAgeMonths: record.minimum_age_months == null ? '' : String(record.minimum_age_months),
    maximumAgeMonths: record.maximum_age_months == null ? '' : String(record.maximum_age_months),
  };
}

function normalizedRoomName(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function roomHasInput(room: RoomDraft): boolean {
  return Boolean(room.id || room.name.trim() || room.capacity || room.ageGroup.trim());
}

function uniqueDraftKey(preferred: string, used: Set<string>): string {
  let candidate = preferred || `room-${used.size + 1}`;
  let suffix = 2;
  while (used.has(candidate)) candidate = `${preferred || 'room'}-${suffix++}`;
  used.add(candidate);
  return candidate;
}

/** Reconciles API records by program type and rooms by id/name, never array position. */
export function reconcileCareStructure(
  draft: OnboardingDraft,
  records: ProgramRecord[],
  roomRecords: RoomRecord[],
): OnboardingDraft {
  const byType: Partial<Record<ProgramType, ProgramRecord>> = {};
  const savedTypeById = new Map<string, ProgramType>();
  PROGRAM_TYPES.forEach((type) => {
    const id = draft.programs[type].id;
    if (id) savedTypeById.set(id, type);
  });
  records.forEach((record) => {
    const type = normalizeProgramType(record.program_type) || savedTypeById.get(record.id) || null;
    if (type && !byType[type]) byType[type] = record;
  });

  const recordTypes = PROGRAM_TYPES.filter((type) => Boolean(byType[type]));
  const meaningfulSelections = draft.selectedProgramTypes.filter((type) => {
    const value = draft.programs[type];
    const fallback = EMPTY_PROGRAMS[type];
    return Boolean(value.id || value.capacity || value.minimumAgeMonths || value.maximumAgeMonths || value.name !== fallback.name);
  });
  const selectedProgramTypes = recordTypes.length
    ? uniqueProgramTypes([...meaningfulSelections, ...recordTypes])
    : draft.selectedProgramTypes;
  const nextPrograms: Record<ProgramType, ProgramDraft> = {
    daycare: byType.daycare ? recordToProgramDraft(byType.daycare) : draft.programs.daycare,
    out_of_school_care: byType.out_of_school_care ? recordToProgramDraft(byType.out_of_school_care) : draft.programs.out_of_school_care,
  };

  const programTypeById = new Map<string, ProgramType>();
  records.forEach((record) => {
    const type = normalizeProgramType(record.program_type) || savedTypeById.get(record.id);
    if (type) programTypeById.set(record.id, type);
  });
  const archivedRoomIds = new Set(draft.archivedRoomIds);
  const facilityRooms = roomRecords.filter((room) => room.facility_id === draft.facility.id && room.is_active && !archivedRoomIds.has(room.id));
  const claimed = new Set<string>();
  const usedKeys = new Set<string>();
  const sourceDraftRooms = facilityRooms.length ? draft.rooms.filter(roomHasInput) : draft.rooms;
  const nextRooms: RoomDraft[] = sourceDraftRooms.map((room) => {
    let match = room.id ? facilityRooms.find((record) => record.id === room.id) : undefined;
    if (!match && room.name.trim()) {
      const matches = facilityRooms.filter((record) => !claimed.has(record.id) && normalizedRoomName(record.name) === normalizedRoomName(room.name));
      if (matches.length === 1) match = matches[0];
    }
    if (match) claimed.add(match.id);
    const assignedType = match?.program_id ? programTypeById.get(match.program_id) : undefined;
    const requestedType = room.programType && selectedProgramTypes.includes(room.programType) ? room.programType : undefined;
    return {
      ...room,
      draftKey: uniqueDraftKey(room.draftKey || match?.id || '', usedKeys),
      id: match?.id || room.id,
      programType: requestedType || assignedType || selectedProgramTypes[0] || '',
    };
  });

  facilityRooms.filter((room) => !claimed.has(room.id)).forEach((room) => {
    const assignedType = room.program_id ? programTypeById.get(room.program_id) : undefined;
    nextRooms.push({
      draftKey: uniqueDraftKey(room.id, usedKeys),
      id: room.id,
      programType: assignedType || '',
      name: room.name,
      capacity: String(room.capacity),
      ageGroup: normalizeRoomAgeGroup(room.age_group),
    });
  });

  if (!nextRooms.length) nextRooms.push({ ...createEmptyRoomDraft(), programType: selectedProgramTypes[0] || '' });
  return { ...draft, selectedProgramTypes, programs: nextPrograms, rooms: nextRooms };
}

/** Recovers ids after committed creates with lost responses, preserving every form value. */
export function recoverCareStructureIds(
  draft: OnboardingDraft,
  records: ProgramRecord[],
  roomRecords: RoomRecord[],
): OnboardingDraft {
  if (!draft.facility.id) return draft;
  let nextPrograms = draft.programs;
  draft.selectedProgramTypes.forEach((type) => {
    if (nextPrograms[type].id) return;
    const matches = records.filter((record) => record.facility_id === draft.facility.id && normalizeProgramType(record.program_type) === type);
    if (matches.length > 1) throw new Error(`CareSync found more than one ${PROGRAM_TYPE_LABELS[type]} program and cannot safely choose one for this retry.`);
    if (matches.length === 1) nextPrograms = { ...nextPrograms, [type]: { ...nextPrograms[type], id: matches[0].id } };
  });

  let changed = nextPrograms !== draft.programs;
  const archivedRoomIds = new Set(draft.archivedRoomIds);
  const nextRooms = draft.rooms.map((room) => {
    if (room.id) return room;
    const matches = roomRecords.filter((record) => record.facility_id === draft.facility.id && normalizedRoomName(record.name) === normalizedRoomName(room.name));
    if (matches.length > 1) throw new Error(`CareSync found more than one room named “${room.name.trim()}” and cannot safely choose one for this retry.`);
    if (matches.length === 1) {
      changed = true;
      archivedRoomIds.delete(matches[0].id);
      return { ...room, id: matches[0].id };
    }
    return room;
  });
  const nextArchivedRoomIds = [...archivedRoomIds];
  if (nextArchivedRoomIds.length !== draft.archivedRoomIds.length) changed = true;
  return changed ? { ...draft, programs: nextPrograms, rooms: nextRooms, archivedRoomIds: nextArchivedRoomIds } : draft;
}

export function validateOrganization(input: OnboardingDraft['organization']): DraftErrors {
  const errors: DraftErrors = {};
  if (!input.name.trim()) errors['organization.name'] = 'Enter the operating name.';
  if (input.email && !EMAIL.test(input.email.trim())) errors['organization.email'] = 'Enter a complete email address.';
  if (!input.timezone.trim()) errors['organization.timezone'] = 'Choose a timezone.';
  return errors;
}

export function validateFacility(input: OnboardingDraft['facility']): DraftErrors {
  const errors: DraftErrors = {};
  if (!input.name.trim()) errors['facility.name'] = 'Enter the facility name.';
  if (!input.streetAddress.trim()) errors['facility.streetAddress'] = 'Enter the street address.';
  if (!input.city.trim()) errors['facility.city'] = 'Enter the city.';
  if (!input.province.trim()) errors['facility.province'] = 'Enter the province.';
  if (!input.timezone.trim()) errors['facility.timezone'] = 'Choose a timezone.';
  if (!POSTAL.test(input.postalCode.trim())) errors['facility.postalCode'] = 'Enter a Canadian postal code.';
  const capacity = Number(input.licensedCapacity);
  if (!Number.isInteger(capacity) || capacity <= 0) errors['facility.licensedCapacity'] = 'Enter a licensed capacity greater than zero.';
  if (input.email && !EMAIL.test(input.email.trim())) errors['facility.email'] = 'Enter a complete facility email.';
  if (!input.openingTime || !input.closingTime || input.closingTime <= input.openingTime) errors['facility.closingTime'] = 'Closing time must be later than opening time.';
  return errors;
}

export function validateRooms(input: Pick<OnboardingDraft, 'selectedProgramTypes' | 'programs' | 'rooms'>): DraftErrors {
  const errors: DraftErrors = {};
  if (!input.selectedProgramTypes.length) errors.selectedProgramTypes = 'Select at least one licensed service.';
  input.selectedProgramTypes.forEach((type) => {
    const program = input.programs[type];
    const prefix = `programs.${type}`;
    const label = PROGRAM_TYPE_LABELS[type];
    if (!program.name.trim()) errors[`${prefix}.name`] = `Enter a name for the ${label} program.`;
    const programCapacity = Number(program.capacity);
    if (!Number.isInteger(programCapacity) || programCapacity <= 0) errors[`${prefix}.capacity`] = `Enter a ${label} capacity greater than zero.`;
    const min = program.minimumAgeMonths ? Number(program.minimumAgeMonths) : null;
    const max = program.maximumAgeMonths ? Number(program.maximumAgeMonths) : null;
    if (min !== null && (!Number.isInteger(min) || min < 0)) errors[`${prefix}.minimumAgeMonths`] = 'Minimum age must be zero or greater.';
    if (max !== null && (!Number.isInteger(max) || max < 0)) errors[`${prefix}.maximumAgeMonths`] = 'Maximum age must be zero or greater.';
    if (min !== null && max !== null && max < min) errors[`${prefix}.maximumAgeMonths`] = 'Maximum age cannot be lower than minimum age.';
  });

  if (!input.rooms.length) errors.rooms = 'Add at least one room.';
  const names = new Map<string, number>();
  const roomCapacityByProgram: Record<ProgramType, number> = { daycare: 0, out_of_school_care: 0 };
  input.rooms.forEach((room) => {
    const prefix = `rooms.${room.draftKey}`;
    if (!room.programType || !input.selectedProgramTypes.includes(room.programType)) errors[`${prefix}.programType`] = 'Choose which licensed program this room belongs to.';
    if (!room.name.trim()) errors[`${prefix}.name`] = 'Enter a room name.';
    const normalizedName = normalizedRoomName(room.name);
    if (normalizedName) names.set(normalizedName, (names.get(normalizedName) || 0) + 1);
    const roomCapacity = Number(room.capacity);
    if (!Number.isInteger(roomCapacity) || roomCapacity <= 0) errors[`${prefix}.capacity`] = 'Enter a room capacity greater than zero.';
    if (room.programType && isProgramType(room.programType) && Number.isInteger(roomCapacity) && roomCapacity > 0) roomCapacityByProgram[room.programType] += roomCapacity;
    const assignedProgram = room.programType && isProgramType(room.programType) ? input.programs[room.programType] : null;
    const programCapacity = assignedProgram ? Number(assignedProgram.capacity) : Number.NaN;
    if (Number.isInteger(programCapacity) && Number.isInteger(roomCapacity) && roomCapacity > programCapacity) errors[`${prefix}.capacity`] = 'Room capacity cannot exceed its assigned program capacity.';
  });
  input.rooms.forEach((room) => {
    if (room.name.trim() && names.get(normalizedRoomName(room.name))! > 1) errors[`rooms.${room.draftKey}.name`] = 'Room names must be unique within this facility.';
  });
  input.selectedProgramTypes.forEach((type) => {
    const capacity = Number(input.programs[type].capacity);
    if (Number.isInteger(capacity) && capacity > 0 && roomCapacityByProgram[type] > capacity) {
      errors[`programs.${type}.capacity`] = `Combined ${PROGRAM_TYPE_LABELS[type]} room capacity (${roomCapacityByProgram[type]}) exceeds the program capacity (${capacity}).`;
    }
  });
  return errors;
}

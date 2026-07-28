import type {
  ApiChildEnrollment,
  EnrollmentCreateInput,
  EnrollmentFacilityOption,
  EnrollmentPlacementApprovalInput,
  EnrollmentPlacementOptions,
  EnrollmentRoomOption,
} from './childrenApi';

export interface EnrollmentEditorValues {
  facilityId: string;
  programId: string;
  roomId: string;
  startDate: string;
  effectiveDate: string;
}

export type EnrollmentEditorErrors = Partial<Record<keyof EnrollmentEditorValues | 'endDate', string>>;

function validIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

export function localIsoDate(now = new Date()): string {
  return [
    now.getFullYear().toString().padStart(4, '0'),
    (now.getMonth() + 1).toString().padStart(2, '0'),
    now.getDate().toString().padStart(2, '0'),
  ].join('-');
}

export function facilityIsoDate(timezone: string, now = new Date()): string {
  if (!timezone.trim()) throw new Error('A facility timezone is required.');
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  if (!value.year || !value.month || !value.day) throw new Error('The facility date could not be calculated.');
  return `${value.year}-${value.month}-${value.day}`;
}

export function currentChildEnrollment(enrollments: readonly ApiChildEnrollment[], today = localIsoDate()): ApiChildEnrollment | null {
  const open = enrollments.filter((enrollment) => enrollment.status !== 'ended' && (!enrollment.end_date || enrollment.end_date.slice(0, 10) >= today));
  return open.find((enrollment) => enrollment.status === 'active' && enrollment.is_active)
    || open[0]
    || null;
}

export function enrollmentValues(enrollment: ApiChildEnrollment | null, today = localIsoDate()): EnrollmentEditorValues {
  return {
    facilityId: enrollment?.facility_id || '',
    programId: enrollment?.program_id || '',
    roomId: enrollment?.room_id || '',
    startDate: enrollment?.start_date.slice(0, 10) || today,
    effectiveDate: enrollment?.placement_effective_date?.slice(0, 10) || today,
  };
}

function validatePlacement(
  values: EnrollmentEditorValues,
  facilities: readonly EnrollmentFacilityOption[],
  options: EnrollmentPlacementOptions,
  currentEnrollment: ApiChildEnrollment | null = null,
): EnrollmentEditorErrors {
  const errors: EnrollmentEditorErrors = {};
  const facility = facilities.find((option) => option.id === values.facilityId && option.status === 'active');
  if (!values.facilityId) errors.facilityId = 'Select a facility.';
  else if (!facility) errors.facilityId = 'Select an active facility returned for this organization.';

  const program = values.programId
    ? options.programs.find((option) => option.id === values.programId && option.is_active)
    : null;
  if (!values.programId) errors.programId = 'Select an active program.';
  else if (!program || program.facility_id !== values.facilityId) {
    errors.programId = 'Select an active program from this facility.';
  }

  const room = values.roomId
    ? options.rooms.find((option) => option.id === values.roomId && option.is_active)
    : null;
  if (!values.roomId) errors.roomId = 'Select an active room.';
  else if (!room || room.facility_id !== values.facilityId) {
    errors.roomId = 'Select an active room from this facility.';
  } else if (room.program_id !== values.programId) {
    errors.roomId = 'This room belongs to another program.';
  } else if (room.occupancy >= room.capacity && currentEnrollment?.room_id !== room.id) {
    errors.roomId = `${room.name} is full. Choose another room.`;
  }
  return errors;
}

export function validateEnrollmentCreate(
  values: EnrollmentEditorValues,
  facilities: readonly EnrollmentFacilityOption[],
): EnrollmentEditorErrors {
  const errors: EnrollmentEditorErrors = {};
  const facility = facilities.find((option) => option.id === values.facilityId && option.status === 'active');
  if (!values.facilityId) errors.facilityId = 'Select a facility.';
  else if (!facility) errors.facilityId = 'Select an active facility returned for this organization.';
  if (!values.startDate) errors.startDate = 'Select the first day of care.';
  else if (!validIsoDate(values.startDate)) errors.startDate = 'Enter a valid start date.';
  return errors;
}

export function validateEnrollmentPlacement(
  values: EnrollmentEditorValues,
  enrollment: ApiChildEnrollment,
  facilities: readonly EnrollmentFacilityOption[],
  options: EnrollmentPlacementOptions,
): EnrollmentEditorErrors {
  const errors = validatePlacement(values, facilities, options, enrollment);
  if (values.facilityId !== enrollment.facility_id) {
    errors.facilityId = 'End this enrollment before enrolling the child at another facility.';
  }
  if (!values.effectiveDate) errors.effectiveDate = 'Select the placement effective date.';
  else if (!validIsoDate(values.effectiveDate)) errors.effectiveDate = 'Enter a valid placement effective date.';
  else if (values.effectiveDate < enrollment.start_date.slice(0, 10)) {
    errors.effectiveDate = 'Placement cannot take effect before enrollment starts.';
  }
  return errors;
}

export function validateEnrollmentEnd(
  endDate: string,
  enrollment: ApiChildEnrollment,
  latestAllowedDate = localIsoDate(),
): EnrollmentEditorErrors {
  if (!endDate) return { endDate: 'Select the final day of care.' };
  if (!validIsoDate(endDate)) return { endDate: 'Enter a valid end date.' };
  if (endDate < enrollment.start_date.slice(0, 10)) {
    return { endDate: 'The final day cannot be before the enrollment start date.' };
  }
  if (endDate > latestAllowedDate) {
    return { endDate: 'End enrollment now or as of a past date. Future departures require the scheduled-departure workflow.' };
  }
  return {};
}

export function enrollmentCreateInput(values: EnrollmentEditorValues): EnrollmentCreateInput {
  return {
    facility_id: values.facilityId,
    start_date: values.startDate,
  };
}

export function enrollmentPlacementApprovalInput(values: EnrollmentEditorValues): EnrollmentPlacementApprovalInput {
  return {
    room_id: values.roomId,
    effective_date: values.effectiveDate,
  };
}

export function placementChanged(values: EnrollmentEditorValues, enrollment: ApiChildEnrollment): boolean {
  return (values.programId || null) !== enrollment.program_id
    || (values.roomId || null) !== enrollment.room_id
    || values.effectiveDate !== (enrollment.placement_effective_date?.slice(0, 10) || '');
}

export function roomsForProgram(
  rooms: readonly EnrollmentRoomOption[],
  programId: string,
): EnrollmentRoomOption[] {
  if (!programId) return [];
  return rooms.filter((room) => room.program_id === programId);
}

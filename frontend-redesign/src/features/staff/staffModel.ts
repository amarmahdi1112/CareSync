import type { StaffInviteInput, StaffRole, StaffRoom } from './types';

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function roomFacilityIds(roomIds: readonly string[], rooms: readonly StaffRoom[]): string[] {
  const selected = new Set(roomIds);
  return [...new Set(rooms.filter((room) => selected.has(room.id)).map((room) => room.facility_id))];
}

export function validateStaffDraft(input: StaffInviteInput, role: StaffRole | undefined, rooms: readonly StaffRoom[]): string[] {
  const errors: string[] = [];
  if (!input.first_name.trim()) errors.push('First name is required.');
  if (!input.last_name.trim()) errors.push('Last name is required.');
  if (!EMAIL.test(input.email.trim())) errors.push('A valid work email is required.');
  if (!role || role.id !== input.role_id) errors.push('Choose an available role.');
  const knownRooms = new Set(rooms.filter((room) => room.is_active).map((room) => room.id));
  if (input.assigned_room_ids.some((id) => !knownRooms.has(id))) errors.push('One or more selected rooms are unavailable.');
  if (role?.key === 'educator' && input.assigned_room_ids.length === 0) errors.push('Assign at least one active room to an educator.');
  const expectedFacilities = roomFacilityIds(input.assigned_room_ids, rooms).sort();
  if (JSON.stringify([...input.assigned_facility_ids].sort()) !== JSON.stringify(expectedFacilities)) {
    errors.push('Room and facility assignments do not agree.');
  }
  return errors;
}

export function passwordErrors(password: string, confirmation: string): string[] {
  const errors: string[] = [];
  if (password.length < 12) errors.push('Password must contain at least 12 characters.');
  if (password !== confirmation) errors.push('Password confirmation does not match.');
  return errors;
}

export function oneTimeTokenFromHash(hash: string): string {
  const values = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash).getAll('token');
  return values.length === 1 ? values[0].trim() : '';
}

export function absoluteHandoffUrl(value: string, origin = window.location.origin): string {
  const currentOrigin = new URL(origin).origin;
  const parsed = new URL(value, currentOrigin);
  if (parsed.origin !== currentOrigin) throw new Error('The server returned a handoff link outside this CareSync origin.');
  if (parsed.search) throw new Error('The server returned a handoff link with an unsafe query string.');
  if (!oneTimeTokenFromHash(parsed.hash)) throw new Error('The server returned a handoff link without a one-time fragment token.');
  return parsed.toString();
}

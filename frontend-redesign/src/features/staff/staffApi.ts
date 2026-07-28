import { apiRequest, parseLoginResponse, type LoginResponse } from '../../api/client';
import type {
  OneTimeActivation, OneTimePasswordReset, PasswordResetPreview, StaffActivationPreview,
  StaffFacility, StaffInvitation, StaffInviteInput, StaffMember, StaffRole, StaffRoom, StaffWorkspace,
} from './types';

export class StaffApiError extends Error {
  constructor(message: string) { super(message); this.name = 'StaffApiError'; }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new StaffApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const string = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new StaffApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableString = (value: unknown, label: string): string | null => value == null ? null : string(value, label);
const timeZone = (value: unknown, label: string): string => { const result = string(value, label); try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new StaffApiError(`The server returned an invalid ${label}.`); } return result; };
const boolean = (value: unknown, label: string): boolean => { if (typeof value !== 'boolean') throw new StaffApiError(`The server returned an invalid ${label}.`); return value; };
const strings = (value: unknown, label: string): string[] => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || !item.trim())) throw new StaffApiError(`The server returned invalid ${label}.`);
  const result = [...new Set(value as string[])];
  if (result.length !== value.length) throw new StaffApiError(`The server returned duplicate ${label}.`);
  return result;
};
const array = <T,>(value: unknown, label: string, parser: (item: unknown) => T): T[] => {
  if (!Array.isArray(value)) throw new StaffApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};

export function parseStaffRole(value: unknown): StaffRole {
  const data = object(value, 'staff role');
  return { id: string(data.id, 'role id'), key: string(data.key, 'role key'), name: string(data.name, 'role name'), description: nullableString(data.description, 'role description'), permissions: strings(data.permissions, 'role permissions') };
}

export function parseStaffMember(value: unknown): StaffMember {
  const data = object(value, 'staff member');
  const status = string(data.membership_status, 'membership status');
  if (!['active', 'suspended'].includes(status)) throw new StaffApiError('The server returned an unsupported member status.');
  const credential = data.credential == null ? null : (() => { const row = object(data.credential, 'staff credential'); const verification = string(row.verification_status, 'credential verification status'); if (!['unverified', 'pending', 'verified', 'rejected'].includes(verification)) throw new StaffApiError('The server returned an unsupported credential verification status.'); return { certification_type: nullableString(row.certification_type, 'certification type'), certification_number: nullableString(row.certification_number, 'certification number'), expiry_date: nullableString(row.expiry_date, 'credential expiry'), verification_status: verification as NonNullable<StaffMember['credential']>['verification_status'], ready: boolean(row.ready, 'credential readiness') }; })();
  const currentShift = data.current_shift == null ? null : (() => { const row = object(data.current_shift, 'staff shift'); const shiftStatus = string(row.status, 'shift status'); if (!['open', 'closed'].includes(shiftStatus)) throw new StaffApiError('The server returned an unsupported shift status.'); return { id: string(row.id, 'shift id'), facility_id: string(row.facility_id, 'shift facility id'), status: shiftStatus as 'open' | 'closed', clocked_in_at: string(row.clocked_in_at, 'shift clock-in time'), clocked_out_at: nullableString(row.clocked_out_at, 'shift clock-out time') }; })();
  if (data.private_hr_fields_exposed !== false) throw new StaffApiError('The server exposed private HR fields in the staff directory.');
  return {
    membership_id: string(data.membership_id, 'membership id'), organization_id: string(data.organization_id, 'member organization id'), user_id: string(data.user_id, 'staff user id'),
    email: string(data.email, 'staff email'), first_name: string(data.first_name, 'staff first name'), last_name: string(data.last_name, 'staff last name'), role: parseStaffRole(data.role),
    membership_status: status as StaffMember['membership_status'], assigned_facility_ids: strings(data.assigned_facility_ids, 'assigned facility ids'), assigned_room_ids: strings(data.assigned_room_ids, 'assigned room ids'),
    joined_at: nullableString(data.joined_at, 'staff joined time'), created_at: string(data.created_at, 'staff created time'), updated_at: string(data.updated_at, 'staff updated time'),
    active_assignments: array(data.active_assignments, 'active staff assignments', (value) => { const row = object(value, 'staff assignment'); return { facility_id: string(row.facility_id, 'assignment facility id'), facility_name: string(row.facility_name, 'assignment facility name'), room_id: nullableString(row.room_id, 'assignment room id'), room_name: nullableString(row.room_name, 'assignment room name') }; }),
    credential,
    current_shift: currentShift,
    private_hr_fields_exposed: false,
  };
}

export function parseStaffInvitation(value: unknown): StaffInvitation {
  const data = object(value, 'staff invitation');
  const status = string(data.status, 'invitation status');
  if (!['pending', 'accepted', 'revoked', 'expired'].includes(status)) throw new StaffApiError('The server returned an unsupported invitation status.');
  return {
    id: string(data.id, 'invitation id'), organization_id: string(data.organization_id, 'invitation organization id'), email: string(data.email, 'invitation email'), first_name: string(data.first_name, 'invitation first name'), last_name: string(data.last_name, 'invitation last name'), role: parseStaffRole(data.role), status: status as StaffInvitation['status'],
    assigned_facility_ids: strings(data.assigned_facility_ids, 'invitation facility ids'), assigned_room_ids: strings(data.assigned_room_ids, 'invitation room ids'), expires_at: string(data.expires_at, 'invitation expiry'), created_at: string(data.created_at, 'invitation created time'),
  };
}

const parseFacility = (value: unknown): StaffFacility => { const data = object(value, 'staff facility'); return { id: string(data.id, 'facility id'), organization_id: string(data.organization_id, 'facility organization id'), name: string(data.name, 'facility name'), timezone: timeZone(data.timezone, 'facility timezone'), status: string(data.status, 'facility status') }; };
const parseRoom = (value: unknown): StaffRoom => { const data = object(value, 'staff room'); if (typeof data.is_active !== 'boolean') throw new StaffApiError('The server returned an invalid room status.'); return { id: string(data.id, 'room id'), organization_id: string(data.organization_id, 'room organization id'), facility_id: string(data.facility_id, 'room facility id'), name: string(data.name, 'room name'), is_active: data.is_active }; };

const hasDuplicateIds = (items: readonly { id: string }[]) => new Set(items.map((item) => item.id)).size !== items.length;

export function parseStaffWorkspace(value: unknown, organizationId: string): StaffWorkspace {
  const data = object(value, 'staff workspace');
  const result: StaffWorkspace = { organization_id: string(data.organization_id, 'workspace organization id'), roles: array(data.roles, 'staff roles', parseStaffRole), facilities: array(data.facilities, 'staff facilities', parseFacility), rooms: array(data.rooms, 'staff rooms', parseRoom), members: array(data.members, 'staff members', parseStaffMember), invitations: array(data.invitations, 'staff invitations', parseStaffInvitation) };
  if (result.organization_id !== organizationId) throw new StaffApiError('The staff workspace crossed the active organization boundary.');
  const roleIds = new Set(result.roles.map((role) => role.id));
  const facilityIds = new Set(result.facilities.map((facility) => facility.id));
  const roomIds = new Set(result.rooms.map((room) => room.id));
  const roomFacility = new Map(result.rooms.map((room) => [room.id, room.facility_id]));
  if (hasDuplicateIds(result.roles) || hasDuplicateIds(result.facilities) || hasDuplicateIds(result.rooms)) throw new StaffApiError('The staff workspace returned duplicate record identifiers.');
  if ([...result.facilities, ...result.rooms, ...result.members, ...result.invitations].some((item) => item.organization_id !== organizationId)) throw new StaffApiError('A staff record crossed the active organization boundary.');
  if (result.rooms.some((room) => !facilityIds.has(room.facility_id))) throw new StaffApiError('A staff room points outside the verified workspace.');
  if (result.members.some((member) => !roleIds.has(member.role.id) || member.assigned_facility_ids.some((id) => !facilityIds.has(id)) || member.assigned_room_ids.some((id) => !roomIds.has(id) || !member.assigned_facility_ids.includes(roomFacility.get(id)!)) || member.active_assignments.some((assignment) => !facilityIds.has(assignment.facility_id) || (assignment.room_id != null && (!roomIds.has(assignment.room_id) || roomFacility.get(assignment.room_id) !== assignment.facility_id))) || (member.current_shift != null && !facilityIds.has(member.current_shift.facility_id)))) throw new StaffApiError('A staff member points outside the verified workspace.');
  if (result.invitations.some((invite) => !roleIds.has(invite.role.id) || invite.assigned_facility_ids.some((id) => !facilityIds.has(id)) || invite.assigned_room_ids.some((id) => !roomIds.has(id) || !invite.assigned_facility_ids.includes(roomFacility.get(id)!)))) throw new StaffApiError('A staff invitation points outside the verified workspace.');
  return result;
}

const parseOneTimeActivation = (value: unknown): OneTimeActivation => { const data = object(value, 'one-time activation'); return { invitation: parseStaffInvitation(data.invitation), activation_url: string(data.activation_url, 'activation link') }; };
const parsePasswordReset = (value: unknown): OneTimePasswordReset => { const data = object(value, 'one-time password reset'); return { reset_url: string(data.reset_url, 'password reset link'), expires_at: string(data.expires_at, 'password reset expiry') }; };

export function parseStaffActivationPreview(value: unknown): StaffActivationPreview {
  const data = object(value, 'staff activation preview');
  return {
    organization_name: string(data.organization_name, 'activation organization name'),
    email: string(data.email, 'activation email'),
    first_name: string(data.first_name, 'activation first name'),
    last_name: string(data.last_name, 'activation last name'),
    role_name: string(data.role_name, 'activation role name'),
    expires_at: string(data.expires_at, 'activation expiry'),
    assigned_room_names: strings(data.assigned_room_names, 'activation room names'),
  };
}

export function parsePasswordResetPreview(value: unknown): PasswordResetPreview {
  const data = object(value, 'password reset preview');
  return {
    organization_name: string(data.organization_name, 'reset organization name'),
    email: string(data.email, 'reset email'),
    expires_at: string(data.expires_at, 'reset expiry'),
  };
}

export const staffApi = {
  workspace: async (organizationId: string, signal?: AbortSignal) => parseStaffWorkspace(await apiRequest<unknown>('/staff/workspace', { signal }), organizationId),
  invite: async (payload: StaffInviteInput) => parseOneTimeActivation(await apiRequest<unknown>('/staff/invitations', { method: 'POST', body: JSON.stringify(payload) })),
  regenerate: async (id: string) => parseOneTimeActivation(await apiRequest<unknown>(`/staff/invitations/${encodeURIComponent(id)}/regenerate`, { method: 'POST' })),
  revoke: (id: string) => apiRequest<void>(`/staff/invitations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  updateMember: async (membershipId: string, payload: { role_id: string; assigned_facility_ids: string[]; assigned_room_ids: string[]; membership_status?: 'active' | 'suspended' }) => parseStaffMember(await apiRequest<unknown>(`/staff/members/${encodeURIComponent(membershipId)}`, { method: 'PATCH', body: JSON.stringify(payload) })),
  passwordReset: async (membershipId: string) => parsePasswordReset(await apiRequest<unknown>(`/staff/members/${encodeURIComponent(membershipId)}/password-reset`, { method: 'POST' })),
  activationPreview: async (token: string, signal?: AbortSignal): Promise<StaffActivationPreview> => parseStaffActivationPreview(await apiRequest<unknown>('/auth/staff-activation', { method: 'POST', body: JSON.stringify({ token }), signal })),
  activate: async (token: string, password: string): Promise<LoginResponse> => parseLoginResponse(await apiRequest<unknown>('/auth/staff-activation/accept', { method: 'POST', body: JSON.stringify({ token, password }) })),
  resetPreview: async (token: string, signal?: AbortSignal): Promise<PasswordResetPreview> => parsePasswordResetPreview(await apiRequest<unknown>('/auth/password-reset', { method: 'POST', body: JSON.stringify({ token }), signal })),
  completeReset: (token: string, password: string): Promise<void> => apiRequest('/auth/password-reset/complete', { method: 'POST', body: JSON.stringify({ token, password }) }),
};

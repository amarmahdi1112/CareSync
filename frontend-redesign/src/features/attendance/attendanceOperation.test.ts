import { describe, expect, it } from 'vitest';
import { attendanceOperationResolved, readPendingAttendanceOperation, type PendingAttendanceOperation } from './attendanceOperation';
import type { AttendanceRosterRow } from './attendanceApi';

const operation: PendingAttendanceOperation = { organizationId: 'org', serviceDate: '2026-07-16', kind: 'in', childId: 'child', facilityId: 'facility', occurredAt: '2026-07-16T12:00:00Z', clientOperationId: 'operation' };
const rows = (checkedIn: string, checkedOut: string | null = null): AttendanceRosterRow[] => [{ child_id: 'child', child_name: 'Child', profile_photo_url: null, enrollment_id: 'enrollment', room_id: null, room_name: null, program_name: null, attendance_day: { id: 'day', organization_id: 'org', facility_id: 'facility', child_id: 'child', enrollment_id: 'enrollment', service_date: '2026-07-16', status: 'present', absence_reason: null, notes: null, version: 1, child_name: 'Child', intervals: [{ id: 'interval', sequence: 1, checked_in_at: checkedIn, checked_out_at: checkedOut }], events: [], created_at: checkedIn, updated_at: checkedIn } }];

describe('pending attendance operations', () => {
  it('restores only the exact organization and service-date scope', () => { const storage = { getItem: () => JSON.stringify(operation) }; expect(readPendingAttendanceOperation('org', '2026-07-16', storage)).toEqual(operation); expect(readPendingAttendanceOperation('org-b', '2026-07-16', storage)).toBeNull(); expect(readPendingAttendanceOperation('org', '2026-07-17', storage)).toBeNull(); expect(readPendingAttendanceOperation('org', '2026-07-16', { getItem: () => '{' })).toBeNull(); });
  it('reconciles only the exact server timestamp for the requested action', () => { expect(attendanceOperationResolved(operation, rows(operation.occurredAt))).toBe(true); expect(attendanceOperationResolved(operation, rows('2026-07-16T11:00:00Z'))).toBe(false); expect(attendanceOperationResolved({ ...operation, kind: 'out' }, rows('2026-07-16T11:00:00Z', operation.occurredAt))).toBe(true); });
});

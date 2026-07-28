import type { AttendanceRosterRow } from './attendanceApi';

export interface PendingAttendanceOperation { organizationId: string; serviceDate: string; kind: 'in' | 'out'; childId: string; facilityId: string; occurredAt: string; clientOperationId: string; }
export const attendanceOperationKey = (organizationId: string, serviceDate: string) => `caresync:pending-attendance-operation:v2:${organizationId}:${serviceDate}`;

export function readPendingAttendanceOperation(organizationId: string, serviceDate: string, storage: Pick<Storage, 'getItem'> = sessionStorage): PendingAttendanceOperation | null {
  try {
    const value = JSON.parse(storage.getItem(attendanceOperationKey(organizationId, serviceDate)) || 'null') as Partial<PendingAttendanceOperation> | null;
    if (!value || value.organizationId !== organizationId || value.serviceDate !== serviceDate || !['in', 'out'].includes(value.kind || '') || !value.childId || !value.facilityId || !value.occurredAt || !value.clientOperationId) return null;
    return value as PendingAttendanceOperation;
  } catch { return null; }
}

export function attendanceOperationResolved(operation: PendingAttendanceOperation, rows: AttendanceRosterRow[]): boolean {
  const day = rows.find((row) => row.child_id === operation.childId)?.attendance_day;
  if (!day) return false;
  return day.intervals.some((interval) => operation.kind === 'in' ? interval.checked_in_at === operation.occurredAt : interval.checked_out_at === operation.occurredAt);
}

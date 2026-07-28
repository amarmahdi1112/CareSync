export type DeactivationEntityType = 'facility' | 'room';

export interface DeactivationImpact {
  organization_id: string;
  entity_type: DeactivationEntityType;
  entity_id: string;
  entity_name: string;
  active_programs: number;
  active_rooms: number;
  open_enrollments: number;
  open_attendance_intervals: number;
  active_staff_assignments: number;
  open_staff_shifts: number;
  blockers: string[];
  warnings: string[];
  can_deactivate: boolean;
  confirmation_text: string;
}

const record = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The server returned an invalid deactivation impact.');
  return value as Record<string, unknown>;
};
const text = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`The server returned an invalid ${label}.`);
  return value;
};
const count = (value: unknown, label: string): number => {
  if (!Number.isInteger(value) || Number(value) < 0) throw new Error(`The server returned an invalid ${label}.`);
  return Number(value);
};
const messages = (value: unknown, label: string): string[] => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || !item.trim())) throw new Error(`The server returned invalid ${label}.`);
  return value as string[];
};

export function parseDeactivationImpact(
  value: unknown,
  expected: { organizationId: string; entityType: DeactivationEntityType; entityId: string },
): DeactivationImpact {
  const data = record(value);
  const impact: DeactivationImpact = {
    organization_id: text(data.organization_id, 'deactivation organization'),
    entity_type: text(data.entity_type, 'deactivation entity type') as DeactivationEntityType,
    entity_id: text(data.entity_id, 'deactivation entity id'),
    entity_name: text(data.entity_name, 'deactivation entity name'),
    active_programs: count(data.active_programs, 'active program count'),
    active_rooms: count(data.active_rooms, 'active room count'),
    open_enrollments: count(data.open_enrollments, 'open enrollment count'),
    open_attendance_intervals: count(data.open_attendance_intervals, 'open attendance interval count'),
    active_staff_assignments: count(data.active_staff_assignments, 'active staff assignment count'),
    open_staff_shifts: count(data.open_staff_shifts, 'open staff shift count'),
    blockers: messages(data.blockers, 'deactivation blockers'),
    warnings: messages(data.warnings, 'deactivation warnings'),
    can_deactivate: data.can_deactivate as boolean,
    confirmation_text: text(data.confirmation_text, 'deactivation confirmation text'),
  };
  if (typeof data.can_deactivate !== 'boolean') throw new Error('The server returned an invalid deactivation readiness flag.');
  if (impact.organization_id !== expected.organizationId || impact.entity_type !== expected.entityType || impact.entity_id !== expected.entityId) {
    throw new Error('The deactivation impact was returned outside the active organization or entity boundary.');
  }
  if (impact.can_deactivate && impact.blockers.length) throw new Error('The deactivation impact contradicted its blocker state.');
  return impact;
}

import type {
  MedicationAdministration,
  MedicationDayChild,
  MedicationOutcome,
  MedicationPlan,
} from './medicationApi';

export type MedicationPlanGate =
  | 'ready'
  | 'draft'
  | 'archived'
  | 'authorization_missing'
  | 'authorization_revoked'
  | 'authorization_expired'
  | 'authorization_not_current'
  | 'outside_date_range';

export interface MedicationDueItem {
  key: string;
  plan: MedicationPlan;
  dueTime: string | null;
  kind: 'scheduled' | 'as_needed';
  administration: MedicationAdministration | null;
}

export function authorizationEvidenceLabel(plan: MedicationPlan, serviceDate: string): string {
  if (plan.authorization_status === 'revoked') return 'Signed consent evidence revoked';
  if (plan.authorization_status !== 'verified') return 'Signed consent evidence not recorded';
  if (plan.authorization_valid_until && plan.authorization_valid_until < serviceDate) return 'Signed consent evidence expired';
  if (!plan.authorization_is_current) return 'Signed consent evidence not current';
  return 'Signed consent evidence recorded';
}

export function medicationPlanGate(plan: MedicationPlan, serviceDate: string): MedicationPlanGate {
  if (plan.status === 'archived') return 'archived';
  if (plan.status !== 'active') return 'draft';
  if (plan.authorization_status === 'revoked') return 'authorization_revoked';
  if (plan.authorization_status !== 'verified') return 'authorization_missing';
  if (plan.authorization_valid_until && plan.authorization_valid_until < serviceDate) return 'authorization_expired';
  if (!plan.authorization_is_current) return 'authorization_not_current';
  if (plan.start_date > serviceDate || (plan.end_date && plan.end_date < serviceDate)) return 'outside_date_range';
  return 'ready';
}

export function medicationPlanGateLabel(gate: MedicationPlanGate): string {
  if (gate === 'ready') return 'Ready for recording';
  if (gate === 'draft') return 'Draft plan';
  if (gate === 'archived') return 'Archived plan';
  if (gate === 'authorization_missing') return 'Signed consent evidence missing';
  if (gate === 'authorization_revoked') return 'Signed consent evidence revoked';
  if (gate === 'authorization_expired') return 'Signed consent evidence expired';
  if (gate === 'authorization_not_current') return 'Signed consent evidence not current';
  return 'Outside plan date range';
}

export function medicationPlanGateTone(gate: MedicationPlanGate): 'success' | 'warning' | 'info' | 'neutral' {
  if (gate === 'ready') return 'success';
  if (gate === 'archived' || gate === 'outside_date_range') return 'neutral';
  if (gate === 'draft') return 'info';
  return 'warning';
}

export function activeAdministrations(records: readonly MedicationAdministration[]): MedicationAdministration[] {
  return records.filter((record) => !record.voided_at).slice().sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at));
}

function sameDueSlot(record: MedicationAdministration, planId: string, serviceDate: string, dueTime: string | null): boolean {
  if (record.medication_plan_id !== planId || record.service_date !== serviceDate || record.voided_at) return false;
  return record.scheduled_for === dueTime;
}

export function medicationDueItems(child: MedicationDayChild, serviceDate: string): MedicationDueItem[] {
  return child.plans
    .filter((plan) => plan.status !== 'archived' && plan.start_date <= serviceDate && (!plan.end_date || plan.end_date >= serviceDate))
    .flatMap((plan) => {
      const scheduled = plan.scheduled_times.map((dueTime) => ({
        key: `${plan.id}:${serviceDate}:${dueTime}`,
        plan,
        dueTime,
        kind: 'scheduled' as const,
        administration: activeAdministrations(child.administrations).find((record) => sameDueSlot(record, plan.id, serviceDate, dueTime)) || null,
      }));
      if (!plan.as_needed) return scheduled;
      return [...scheduled, {
        key: `${plan.id}:${serviceDate}:as-needed`,
        plan,
        dueTime: null,
        kind: 'as_needed' as const,
        administration: null,
      }];
    });
}

export function medicationOutcomeLabel(outcome: MedicationOutcome): string {
  if (outcome === 'administered') return 'Administered';
  if (outcome === 'refused') return 'Refused';
  return 'Not given';
}

export function medicationOutcomeTone(outcome: MedicationOutcome): 'success' | 'warning' | 'info' {
  if (outcome === 'administered') return 'success';
  if (outcome === 'refused') return 'warning';
  return 'info';
}

export function medicationDayCounts(children: readonly MedicationDayChild[], serviceDate: string) {
  return children.reduce((counts, child) => {
    const due = medicationDueItems(child, serviceDate).filter((item) => item.kind === 'scheduled');
    counts.children += 1;
    counts.activePlans += child.plans.filter((plan) => medicationPlanGate(plan, serviceDate) === 'ready').length;
    counts.due += due.length;
    counts.recorded += due.filter((item) => item.administration).length;
    counts.blocked += child.plans.filter((plan) => ['authorization_missing', 'authorization_revoked', 'authorization_expired'].includes(medicationPlanGate(plan, serviceDate))).length;
    return counts;
  }, { children: 0, activePlans: 0, due: 0, recorded: 0, blocked: 0 });
}

export function canRecordMedication(child: MedicationDayChild, plan: MedicationPlan, serviceDate: string): boolean {
  return child.attendance_state === 'on_site' && Boolean(child.attendance_day_id) && medicationPlanGate(plan, serviceDate) === 'ready';
}

export function childMedicationMatches(child: MedicationDayChild, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return `${child.child_name} ${child.plans.map((plan) => plan.medication_name).join(' ')}`.toLowerCase().includes(normalized);
}

import type { AdmissionIntakeCase, AdmissionIntakeQueue, AdmissionIntakeStage } from './admissionsApi';

export const INTAKE_STAGE_PRESENTATION: Record<AdmissionIntakeStage, { label: string; short: string }> = {
  family_contacts: { label: 'Intake review', short: 'Family contact records need attention' },
  child_record: { label: 'Record attention', short: 'Child records need a canonical update' },
  enrollment_setup: { label: 'Ready to start enrollment', short: 'No open enrollment is recorded' },
  record_conflict: { label: 'Record attention', short: 'Saved records conflict and need review' },
  family_review: { label: 'Intake review', short: 'Family lifecycle needs a manual decision' },
  placement_review: { label: 'Placement review', short: 'Enrollment placement needs review' },
};

export function admissionStageLabel(stage: AdmissionIntakeStage): string {
  return INTAKE_STAGE_PRESENTATION[stage].label;
}

export function admissionCaseWho(item: AdmissionIntakeCase): string {
  if (!item.children.length) return `${item.family_name} · no child record`;
  const names = item.children.slice(0, 3).map((child) => child.display_name);
  const remaining = item.children.length - names.length;
  return `${item.family_name} · ${names.join(', ')}${remaining > 0 ? ` +${remaining}` : ''}`;
}

export function admissionQueueWindow(queue: AdmissionIntakeQueue): {
  start: number;
  end: number;
  page: number;
  pageCount: number;
  canPrevious: boolean;
  canNext: boolean;
} {
  return {
    start: queue.total ? queue.offset + 1 : 0,
    end: Math.min(queue.offset + queue.items.length, queue.total),
    page: Math.floor(queue.offset / queue.limit) + 1,
    pageCount: Math.max(1, Math.ceil(queue.total / queue.limit)),
    canPrevious: queue.offset > 0,
    canNext: queue.offset + queue.items.length < queue.total,
  };
}

export function lastAdmissionPageOffset(total: number, limit: number): number {
  if (!Number.isInteger(total) || total <= 0 || !Number.isInteger(limit) || limit <= 0) return 0;
  return Math.floor((total - 1) / limit) * limit;
}

export function formatIntakeTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Time unavailable';
  return parsed.toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
}

export interface AdmissionRefreshOutcome {
  queueError: unknown | null;
  facilityError: unknown | null;
}

/** Always attempt both canonical sources so one outage cannot leave the other stale. */
export async function refreshAdmissionSources(
  refreshQueue: () => Promise<void>,
  refreshFacilities: () => Promise<void>,
): Promise<AdmissionRefreshOutcome> {
  const [queue, facilities] = await Promise.allSettled([refreshQueue(), refreshFacilities()]);
  return {
    queueError: queue.status === 'rejected' ? queue.reason : null,
    facilityError: facilities.status === 'rejected' ? facilities.reason : null,
  };
}

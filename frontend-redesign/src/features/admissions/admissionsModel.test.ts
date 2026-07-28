import { describe, expect, it } from 'vitest';
import type { AdmissionIntakeCase, AdmissionIntakeQueue } from './admissionsApi';
import { admissionCaseWho, admissionQueueWindow, admissionStageLabel, lastAdmissionPageOffset, refreshAdmissionSources } from './admissionsModel';

const item = {
  family_name: 'Asefa Family',
  children: [
    { id: 'child-1', display_name: 'Adel Asefa', is_active: true },
    { id: 'child-2', display_name: 'Muna Asefa', is_active: true },
  ],
} as AdmissionIntakeCase;

describe('admissions presentation model', () => {
  it('uses factual record-attention language', () => {
    expect(admissionStageLabel('family_contacts')).toBe('Intake review');
    expect(admissionStageLabel('enrollment_setup')).toBe('Ready to start enrollment');
    expect(admissionStageLabel('placement_review')).toBe('Placement review');
    expect(admissionCaseWho(item)).toBe('Asefa Family · Adel Asefa, Muna Asefa');
  });

  it('reports a bounded server page without inventing progress', () => {
    const queue = { total: 62, limit: 25, offset: 25, items: Array.from({ length: 25 }) } as AdmissionIntakeQueue;
    expect(admissionQueueWindow(queue)).toEqual({ start: 26, end: 50, page: 2, pageCount: 3, canPrevious: true, canNext: true });
    expect(lastAdmissionPageOffset(62, 25)).toBe(50);
    expect(lastAdmissionPageOffset(0, 25)).toBe(0);
  });

  it('attempts both canonical realtime sources and reports each failure independently', async () => {
    const calls: string[] = [];
    const outcome = await refreshAdmissionSources(
      async () => { calls.push('queue'); throw new Error('queue unavailable'); },
      async () => { calls.push('facilities'); },
    );
    expect(calls).toEqual(['queue', 'facilities']);
    expect(outcome.queueError).toBeInstanceOf(Error);
    expect(outcome.facilityError).toBeNull();
  });
});

import { describe, expect, it, vi } from 'vitest';
import { fetchMedicationRealtimeSnapshot } from './medicationRealtime';

const workspace = {
  organization_id: 'org-1',
  facilities: [{ id: 'facility-1', name: 'Main', status: 'active', timezone: 'America/Edmonton' }],
  programs: [],
  rooms: [{ id: 'room-1', facility_id: 'facility-1', name: 'Infants', age_group: 'infant', capacity: 12, is_active: true, program_ids: [] }],
};

describe('medication realtime canonical snapshot', () => {
  it('re-reads a retained exact plan in the same checkpoint as its room day', async () => {
    const roomDay = vi.fn(async () => ({ organization_id: 'org-1' }) as never);
    const plan = vi.fn(async () => ({ id: 'plan-1', organization_id: 'org-1' }) as never);
    const result = await fetchMedicationRealtimeSnapshot({
      organizationId: 'org-1', facilityId: 'facility-1', roomId: 'room-1',
      date: '2026-07-22', focusedPlanId: 'plan-1',
    }, { workspace: vi.fn(async () => workspace as never), roomDay, plan });

    expect(roomDay).toHaveBeenCalledWith('room-1', '2026-07-22', 'org-1', 'facility-1');
    expect(plan).toHaveBeenCalledWith('plan-1', 'org-1');
    expect(result.focusedPlan).toMatchObject({ id: 'plan-1' });
  });

  it('rejects the whole cursor checkpoint when the exact plan cannot be refreshed', async () => {
    await expect(fetchMedicationRealtimeSnapshot({
      organizationId: 'org-1', facilityId: 'facility-1', roomId: 'room-1',
      date: '2026-07-22', focusedPlanId: 'plan-1',
    }, {
      workspace: vi.fn(async () => workspace as never),
      roomDay: vi.fn(async () => ({ organization_id: 'org-1' }) as never),
      plan: vi.fn(async () => { throw new Error('plan refresh failed'); }),
    })).rejects.toThrow('plan refresh failed');
  });
});

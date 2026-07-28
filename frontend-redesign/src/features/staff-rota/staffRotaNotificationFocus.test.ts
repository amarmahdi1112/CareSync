import { describe, expect, it } from 'vitest';
import {
  parseStaffRotaActionTarget,
  parseStaffRotaNotificationRequest,
  type StaffRotaNotificationRequest,
} from './staffRotaNotificationFocus';

const request: StaffRotaNotificationRequest = {
  entityType: 'staff_open_shift_engagement',
  entityId: 'engagement-1',
};

describe('staff-rota notification focus', () => {
  it('accepts one closed entity/record pair and rejects duplicates or unsafe ids', () => {
    expect(parseStaffRotaNotificationRequest(new URLSearchParams('focus=staff_time_off&record=leave-1'))).toEqual({
      status: 'available',
      request: { entityType: 'staff_time_off', entityId: 'leave-1' },
    });
    expect(parseStaffRotaNotificationRequest(new URLSearchParams('focus=staff_time_off'))).toEqual({ status: 'invalid', request: null });
    expect(parseStaffRotaNotificationRequest(new URLSearchParams('focus=unknown&record=row-1'))).toEqual({ status: 'invalid', request: null });
    expect(parseStaffRotaNotificationRequest(new URLSearchParams('focus=staff_time_off&record=../leave'))).toEqual({ status: 'invalid', request: null });
    expect(parseStaffRotaNotificationRequest(new URLSearchParams('focus=staff_time_off&focus=staff_availability&record=row-1'))).toEqual({ status: 'invalid', request: null });
  });

  it('requires the canonical resolver to confirm tenant, type, id, and parent linkage', () => {
    const value = {
      organization_id: 'org-1', entity_type: request.entityType, entity_id: request.entityId,
      facility_id: 'facility-1', starts_at: '2026-07-22T15:00:00Z',
      parent_entity_id: 'open-shift-1', membership_id: 'membership-1', visible: true,
    };
    expect(parseStaffRotaActionTarget(value, request, 'org-1')).toMatchObject({ parentEntityId: 'open-shift-1', visible: true });
    expect(() => parseStaffRotaActionTarget({ ...value, organization_id: 'org-2' }, request, 'org-1')).toThrow(/crossed/i);
    expect(() => parseStaffRotaActionTarget({ ...value, entity_id: 'engagement-2' }, request, 'org-1')).toThrow(/crossed/i);
    expect(() => parseStaffRotaActionTarget({ ...value, parent_entity_id: null }, request, 'org-1')).toThrow(/incomplete/i);
    expect(() => parseStaffRotaActionTarget({ ...value, redirect: '/staff' }, request, 'org-1')).toThrow(/invalid/i);
    expect(() => parseStaffRotaActionTarget({ ...value, facility_id: '../facility' }, request, 'org-1')).toThrow(/invalid/i);
    const { visible: _visible, ...missingVisibility } = value;
    expect(() => parseStaffRotaActionTarget(missingVisibility, request, 'org-1')).toThrow(/invalid/i);
  });
});

import { describe, expect, it } from 'vitest';
import { notificationOrganizationTarget, safeNotificationActionPath } from './notificationNavigation';

describe('notification action navigation', () => {
  it('focuses application actions in the internal jobs pipeline', () => {
    expect(safeNotificationActionPath({ path: '/jobs', entity_type: 'application', entity_id: 'app-1' })).toBe('/jobs?view=applicants&application=app-1');
    expect(safeNotificationActionPath({ path: '/jobs', entity_type: 'application', entity_id: '../application' })).toBeNull();
  });
  it('normalizes only the exact legacy UUID application route', () => { const id = '11111111-1111-4111-8111-111111111111'; expect(safeNotificationActionPath({ path: `/jobs/applications/${id}`, entity_type: 'application', entity_id: id })).toBe(`/jobs?view=applicants&application=${id}`); expect(safeNotificationActionPath({ path: '/jobs/applications/not-a-uuid', entity_type: 'application', entity_id: 'not-a-uuid' })).toBeNull(); expect(safeNotificationActionPath({ path: `/jobs/applications/${id}/edit`, entity_type: 'application', entity_id: id })).toBeNull(); });
  it('opens only the exact admission application named by the notification authority tuple', () => {
    const id = '22222222-2222-4222-8222-222222222222';
    expect(safeNotificationActionPath({ path: `/admissions/applications/${id}`, entity_type: 'admission_application', entity_id: id }))
      .toBe(`/admissions/applications/${id}`);
    expect(safeNotificationActionPath({ path: `/admissions/applications/${id}`, entity_type: 'application', entity_id: id })).toBeNull();
    expect(safeNotificationActionPath({ path: `/admissions/applications/${id}`, entity_type: 'admission_application', entity_id: '33333333-3333-4333-8333-333333333333' })).toBeNull();
    expect(safeNotificationActionPath({ path: `/admissions/applications/${id}/edit`, entity_type: 'admission_application', entity_id: id })).toBeNull();
  });
  it.each([
    ['/shifts', 'staff_schedule', '/staff-rota?schedule=shift-1'],
    ['/shifts/time-off', 'staff_time_off', '/staff-rota?focus=staff_time_off&record=shift-1'],
    ['/staff/schedule', 'staff_open_shift', '/staff-rota?focus=staff_open_shift&record=shift-1'],
    ['/staff/self/exchange/open-shift-activity', 'staff_open_shift_engagement', '/staff-rota?focus=staff_open_shift_engagement&record=shift-1'],
    ['/staff/self/exchange/open-shifts', 'staff_open_shift', '/staff-rota?focus=staff_open_shift&record=shift-1'],
    ['/staff/self/exchange/swaps', 'staff_shift_swap', '/staff-rota?focus=staff_shift_swap&record=shift-1'],
  ])('translates the exact staff-app destination %s to a focused admin workforce target', (path, entityType, expected) => {
    expect(safeNotificationActionPath({ path, entity_type: entityType, entity_id: 'shift-1' })).toBe(expected);
  });
  it('rejects staff-app paths paired with an entity they cannot own', () => {
    expect(safeNotificationActionPath({ path: '/shifts/time-off', entity_type: 'staff_schedule', entity_id: 'shift-1' })).toBeNull();
    expect(safeNotificationActionPath({ path: '/staff/self/exchange/swaps', entity_type: 'staff_open_shift', entity_id: 'shift-1' })).toBeNull();
  });
  it('focuses exact incident and staff-schedule records without accepting malformed target ids', () => {
    expect(safeNotificationActionPath({ path: '/incidents', entity_type: 'incident_record', entity_id: 'incident-1' })).toBe('/incidents?incident=incident-1');
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_schedule', entity_id: 'schedule-1' })).toBe('/staff-rota?schedule=schedule-1');
    expect(safeNotificationActionPath({ path: '/incidents', entity_type: 'incident_record', entity_id: '../incident' })).toBeNull();
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_schedule', entity_id: 'schedule?redirect=/jobs' })).toBeNull();
  });
  it('allows known internal records and rejects external, traversal, hash, and unknown-query actions', () => {
    expect(safeNotificationActionPath({ path: '/children/child-1', entity_type: 'child', entity_id: 'child-1' })).toBe('/children/child-1');
    for (const path of [
      'https://evil.test/jobs',
      '//evil.test/jobs',
      '/unknown',
      '/jobs?redirect=https://evil.test',
      '/staff#secret',
      '/shifts?redirect=/jobs',
      '/shifts/',
      '/staff/self/exchange/open-shifts/extra',
      '/jobs/../staff',
      '/jobs?view=applicants&view=offers',
      '/jobs?application=one&application=two',
    ]) expect(safeNotificationActionPath({ path, entity_type: 'test', entity_id: 'id' })).toBeNull();
  });
  it('allows the exact internal staff-rota destination emitted for manager workforce notifications', () => {
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_schedule', entity_id: 'shift-1' })).toBe('/staff-rota?schedule=shift-1');
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_time_off', entity_id: 'leave-1' })).toBe('/staff-rota?focus=staff_time_off&record=leave-1');
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_availability', entity_id: 'availability-1' })).toBe('/staff-rota?focus=staff_availability&record=availability-1');
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'staff_shift_swap', entity_id: 'swap-1' })).toBe('/staff-rota?focus=staff_shift_swap&record=swap-1');
    expect(safeNotificationActionPath({ path: '/staff-rota', entity_type: 'unknown_record', entity_id: 'row-1' })).toBeNull();
    for (const path of ['/staff-rota?redirect=/jobs', '/staff-rota#private', '/staff-rota/unknown']) {
      expect(safeNotificationActionPath({ path, entity_type: 'staff_schedule', entity_id: 'shift-1' })).toBeNull();
    }
  });
  it('focuses only an exact medication plan identifier', () => {
    expect(safeNotificationActionPath({ path: '/medications', entity_type: 'medication_plan', entity_id: 'plan-1' })).toBe('/medications?plan=plan-1');
    expect(safeNotificationActionPath({ path: '/medications', entity_type: 'medication_administration', entity_id: 'record-1' })).toBeNull();
    expect(safeNotificationActionPath({ path: '/medications', entity_type: 'medication_plan', entity_id: '../plan' })).toBeNull();
  });
  it('allows only the exact transport-registry workspace destination', () => {
    expect(safeNotificationActionPath({ path: '/transport-registry', entity_type: 'transport_registry', entity_id: 'registry' })).toBe('/transport-registry');
    for (const path of ['/transport-registry?membership=staff-1', '/transport-registry#private', '/transport-registry/vehicle-1']) {
      expect(safeNotificationActionPath({ path, entity_type: 'transport_registry', entity_id: 'registry' })).toBeNull();
    }
  });
  it('focuses only registered billing facts on the internal financial workspace', () => {
    expect(safeNotificationActionPath({ path: '/billing', entity_type: 'billing_invoice', entity_id: 'invoice-1' })).toBe('/billing?focus=billing_invoice&record=invoice-1');
    expect(safeNotificationActionPath({ path: '/billing', entity_type: 'billing_payment', entity_id: 'payment-1' })).toBe('/billing?focus=billing_payment&record=payment-1');
    expect(safeNotificationActionPath({ path: '/billing', entity_type: 'billing_rate_plan', entity_id: 'rate-1' })).toBe('/billing?focus=billing_rate_plan&record=rate-1');
    expect(safeNotificationActionPath({ path: '/billing', entity_type: 'child', entity_id: 'child-1' })).toBeNull();
    expect(safeNotificationActionPath({ path: '/billing', entity_type: 'billing_invoice', entity_id: '../invoice' })).toBeNull();
  });
  it('accepts only the exact room-operations notification tuple and keeps its entity as data', () => {
    const exceptionId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    expect(safeNotificationActionPath({
      path: '/rooms',
      entity_type: 'room_operational_exception',
      entity_id: exceptionId,
    })).toBe(`/rooms?view=live&exception=${exceptionId}`);
    expect(safeNotificationActionPath({
      path: '/rooms',
      entity_type: 'room_operational_exception',
      entity_id: '../rooms',
    })).toBeNull();
    expect(safeNotificationActionPath({
      path: '/rooms',
      entity_type: 'billing_invoice',
      entity_id: exceptionId,
    })).toBeNull();
    expect(safeNotificationActionPath({
      path: '/rooms',
      entity_type: 'room',
      entity_id: 'room-1',
    })).toBe('/rooms');
  });
  it('requires an explicit available organization target before a cross-org notification can open', () => { const choice = { organization_id: 'org-b', organization_name: 'B', membership_id: 'member', role_key: 'owner' }; expect(notificationOrganizationTarget('org-a', 'org-a', [choice])).toBe('current'); expect(notificationOrganizationTarget('org-b', 'org-a', [choice])).toEqual(choice); expect(notificationOrganizationTarget('org-c', 'org-a', [choice])).toBeNull(); });
});

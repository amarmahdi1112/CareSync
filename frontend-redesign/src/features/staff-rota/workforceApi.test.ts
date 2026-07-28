import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseProjection, parseTemplate, parseTimeOff, WorkforceApiError, workforceApi } from './workforceApi';

const now = '2026-07-16T12:00:00Z';
const availability = (overrides: Record<string, unknown> = {}) => ({
  id: 'availability-1', organization_id: 'org-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care',
  facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', windows: [{ weekday: 0, start_local: '08:00', end_local: '16:00' }], note: null,
  recorded_operation_id: 'operation-1', created_at: now, updated_at: now, ...overrides,
});
const timeOff = (overrides: Record<string, unknown> = {}) => ({
  id: 'leave-1', organization_id: 'org-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care',
  facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', starts_at: '2026-07-20T14:00:00Z', ends_at: '2026-07-21T14:00:00Z',
  category: 'vacation', note: 'Family day', status: 'pending', can_cancel: true, response_note: null, recorded_create_operation_id: 'create-1', recorded_last_operation_id: 'create-1',
  decided_at: null, decided_by_user_id: null, cancelled_at: null, cancelled_by_user_id: null, cancellation_reason: null, created_at: now, updated_at: now, ...overrides,
});
const target = (overrides: Record<string, unknown> = {}) => ({
  id: 'target-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: null, room_name: null,
  windows: [{ weekday: 0, start_local: '08:00', end_local: '16:00', required_staff: 3 }], recorded_last_operation_id: 'operation-1', created_at: now, updated_at: now, ...overrides,
});
const template = (overrides: Record<string, unknown> = {}) => ({
  id: 'template-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: null, room_name: null,
  name: 'Monday opening', weekday: 0, start_local: '08:00', end_local: '16:00', notes: 'Opening shift', is_active: true,
  recorded_create_operation_id: 'template-create-1', recorded_last_operation_id: 'template-create-1', created_by_user_id: 'manager-1', deactivated_at: null, deactivated_by_user_id: null, created_at: now, updated_at: now, ...overrides,
});
const schedule = (overrides: Record<string, unknown> = {}) => ({
  id: 'schedule-1', organization_id: 'org-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care',
  facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: null, room_name: null,
  scheduled_start_at: '2026-07-20T14:00:00Z', scheduled_end_at: '2026-07-20T22:00:00Z', proposed_start_at: null, proposed_end_at: null,
  notes: 'Opening shift', status: 'draft', response_status: 'pending', response_note: null, responded_at: null, actual_shift: null, reconciliation_status: 'upcoming', is_late: false, minutes_late: 0,
  published_at: null, cancelled_at: null, cancellation_reason: null, availability_override_reason: null, recorded_create_operation_id: 'instantiate-1', created_by_user_id: 'manager-1', published_by_user_id: null, cancelled_by_user_id: null, created_at: now, updated_at: now, ...overrides,
});
const projectionBuckets = () => Array.from({ length: 7 * 24 * 4 }, (_, index) => {
  const startsAt = new Date(Date.parse('2026-07-20T06:00:00Z') + index * 15 * 60_000).toISOString();
  const endsAt = new Date(Date.parse(startsAt) + 15 * 60_000).toISOString();
  return index === 0
    ? { starts_at: startsAt, ends_at: endsAt, required: 3, published: 2, acknowledged: 1, declined: 1, draft: 1, gap: 2, confirmation_gap: 2 }
    : { starts_at: startsAt, ends_at: endsAt, required: 0, published: 0, acknowledged: 0, declined: 0, draft: 0, gap: 0, confirmation_gap: 0 };
});
const projection = (overrides: Record<string, unknown> = {}) => ({
  facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: null, room_name: null,
  start_date: '2026-07-20', end_date: '2026-07-26', interval_minutes: 15,
  buckets: projectionBuckets(), total_buckets: 7 * 24 * 4, gap_buckets: 1, generated_at: now, ...overrides,
});
const response = (payload: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });

describe('workforce API boundary', () => {
  beforeEach(() => vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }));
  afterEach(() => vi.unstubAllGlobals());

  it('rejects inconsistent lifecycle and non-canonical coverage arithmetic', () => {
    expect(() => parseTimeOff(timeOff({ status: 'approved', can_cancel: true }))).toThrow('inconsistent time-off lifecycle');
    expect(() => parseTimeOff(timeOff({ decided_by_user_id: 'manager-1' }))).toThrow('inconsistent time-off lifecycle');
    expect(() => parseTemplate(template({ is_active: false, deactivated_at: now, deactivated_by_user_id: null }))).toThrow('inconsistent template lifecycle');
    expect(() => parseTemplate(template({ is_active: true, deactivated_at: now, deactivated_by_user_id: 'manager-1' }))).toThrow('inconsistent template lifecycle');
    expect(() => parseProjection(projection({ buckets: [{ ...(projection().buckets as Record<string, unknown>[])[0], gap: 0 }] }), { facilityId: 'facility-1', roomId: null, startDate: '2026-07-20', endDate: '2026-07-26' })).toThrow('canonical gap arithmetic');
  });

  it('rejects organization and facility boundary crossings in list envelopes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ items: [availability({ organization_id: 'org-2' })], total: 1, generated_at: now })));
    await expect(workforceApi.listAvailability('org-1', { facilityId: 'facility-1' })).rejects.toThrow('organization boundary');
    vi.stubGlobal('fetch', vi.fn(async () => response({ items: [availability({ facility_id: 'facility-2' })], total: 1, generated_at: now })));
    await expect(workforceApi.listAvailability('org-1', { facilityId: 'facility-1' })).rejects.toThrow('facility boundary');
  });

  it('uses bounded leave filters and verifies the exact action receipt', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes('/approve')) return response(timeOff({ status: 'approved', response_note: 'Coverage arranged', can_cancel: true, recorded_last_operation_id: 'approve-1', decided_at: '2026-07-16T13:00:00Z', decided_by_user_id: 'manager-1', updated_at: '2026-07-16T13:00:00Z' }));
      return response({ items: [timeOff()], total: 1, generated_at: now });
    });
    vi.stubGlobal('fetch', fetchMock);
    await workforceApi.listTimeOff('org-1', { startAt: '2026-07-01T00:00:00Z', endAt: '2026-08-01T00:00:00Z' });
    expect(String(fetchMock.mock.calls[0][0])).toContain('start_at=');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('facility_id=');
    const request = parseTimeOff(timeOff());
    await workforceApi.approveTimeOff('org-1', request, 'approve-1', 'Coverage arranged');
    expect(fetchMock.mock.calls[1][1]?.body).toContain(`"expected_updated_at":"${now}"`);
  });

  it('requests inactive templates through the canonical active_only query', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ items: [], total: 0, generated_at: now }));
    vi.stubGlobal('fetch', fetchMock);
    await workforceApi.listTemplates('org-1', { facilityId: 'facility-1', includeInactive: true });
    expect(String(fetchMock.mock.calls[0][0])).toContain('active_only=false');
  });

  it('treats null instantiation notes as inheritance from the template', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(schedule()));
    vi.stubGlobal('fetch', fetchMock);
    const result = await workforceApi.instantiateTemplate('org-1', template() as never, 'instantiate-1', 'user-1', '2026-07-20', null);
    expect(result.notes).toBe('Opening shift');
    expect(fetchMock.mock.calls[0][1]?.body).toContain('"notes":null');
  });

  it('verifies target scope, optimistic timestamp, windows, and operation receipt', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => response(target({ recorded_last_operation_id: 'replace-1', updated_at: '2026-07-16T13:00:00Z' })));
    vi.stubGlobal('fetch', fetchMock);
    const previous = { ...target(), recorded_last_operation_id: 'operation-1' } as never;
    await workforceApi.replaceTarget('org-1', { facilityId: 'facility-1', roomId: null }, previous, 'replace-1', [{ weekday: 0, start_local: '08:00', end_local: '16:00', required_staff: 3 }]);
    expect(fetchMock.mock.calls[0][1]?.body).toContain(`"expected_updated_at":"${now}"`);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/coverage-targets/facility-1');
  });

  it('requires an exact operation receipt when removing a target', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ removed: true, recorded_operation_id: 'remove-1', generated_at: now }));
    vi.stubGlobal('fetch', fetchMock);
    await workforceApi.removeTarget({ facilityId: 'facility-1', roomId: null }, target() as never, 'remove-1');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
    expect(fetchMock.mock.calls[0][1]?.body).toContain('"client_operation_id":"remove-1"');
  });

  it('fails closed when projection scope changes', () => {
    expect(() => parseProjection(projection({ facility_id: 'facility-2' }), { facilityId: 'facility-1', roomId: null, startDate: '2026-07-20', endDate: '2026-07-26' })).toThrow(WorkforceApiError);
  });
});

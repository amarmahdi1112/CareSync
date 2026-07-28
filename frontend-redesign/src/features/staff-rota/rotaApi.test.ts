import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RotaApiError, parseReconciliation, parseStaffSchedule, rotaApi } from './rotaApi';

const schedule = (overrides: Record<string, unknown> = {}) => ({
  id: 'schedule-1', organization_id: 'org-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care',
  facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton',
  room_id: 'room-1', room_name: 'Infants', scheduled_start_at: '2026-07-20T14:00:00Z',
  scheduled_end_at: '2026-07-20T22:00:00Z', proposed_start_at: null, proposed_end_at: null,
  notes: null, status: 'draft', response_status: 'pending', response_note: null, responded_at: null, actual_shift: null,
  reconciliation_status: 'upcoming', is_late: false, minutes_late: 0, published_at: null,
  cancelled_at: null, cancellation_reason: null, availability_override_reason: null, recorded_create_operation_id: 'operation-1', created_by_user_id: 'admin-1',
  origin_type: null, origin_id: null, origin_occurrence_key: null, supersedes_schedule_id: null,
  published_by_user_id: null, cancelled_by_user_id: null, created_at: '2026-07-16T12:00:00Z',
  updated_at: '2026-07-16T12:00:00Z', ...overrides,
});
const response = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('staff rota API boundary', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('rejects unsupported schedule states and crossed organizations', () => {
    expect(() => parseStaffSchedule(schedule({ status: 'mystery' }))).toThrow(RotaApiError);
    expect(() => parseReconciliation({ scheduled: [schedule({ organization_id: 'org-2' })], unscheduled: [], total_scheduled: 1, total_unscheduled: 0, generated_at: '2026-07-16T12:00:00Z' }, 'org-1')).toThrow('crossed the active organization boundary');
  });

  it('requires complete, internally consistent schedule provenance', () => {
    expect(() => parseStaffSchedule(schedule({ origin_type: 'rotation', origin_id: null, origin_occurrence_key: 'slot:date' }))).toThrow('incomplete source provenance');
    expect(() => parseStaffSchedule(schedule({ origin_type: 'rotation', origin_id: 'rotation-1', origin_occurrence_key: 'slot:date', supersedes_schedule_id: 'schedule-0' }))).toThrow('cannot supersede');
    expect(() => parseStaffSchedule(schedule({ origin_type: 'swap', origin_id: 'swap-1', origin_occurrence_key: 'replacement-a' }))).toThrow('did not identify');
    expect(parseStaffSchedule(schedule({ origin_type: 'open_shift', origin_id: 'post-1', origin_occurrence_key: 'fill', supersedes_schedule_id: 'schedule-0' })).origin_type).toBe('open_shift');
  });

  it('sends range filters and keeps endpoint knowledge in the adapter', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ items: [], total: 0, generated_at: '2026-07-16T12:00:00Z' }));
    vi.stubGlobal('fetch', fetchMock);
    await rotaApi.list('org-1', { startAt: '2026-07-20T00:00:00Z', endAt: '2026-07-27T00:00:00Z', facilityId: 'facility-1' });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/staff-schedules?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('facility_id=facility-1');
  });

  it('requires the publish endpoint to confirm a published lifecycle', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(schedule())));
    await expect(rotaApi.publish('org-1', 'schedule-1', 'operation-1')).rejects.toThrow('did not confirm');
  });

  it('sends and strictly confirms a recorded availability override', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(schedule({ status: 'published', availability_override_reason: 'Emergency coverage' })));
    vi.stubGlobal('fetch', fetchMock);
    await rotaApi.publish('org-1', 'schedule-1', 'operation-2', 'Emergency coverage');
    expect(fetchMock.mock.calls[0][1]?.body).toContain('"availability_override_reason":"Emergency coverage"');
  });

  it('posts an idempotency key and verifies the created schedule receipt', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(schedule()));
    vi.stubGlobal('fetch', fetchMock);
    await rotaApi.create('org-1', {
      client_operation_id: 'operation-1', staff_user_id: 'user-1', facility_id: 'facility-1', room_id: 'room-1',
      scheduled_start_at: '2026-07-20T14:00:00Z', scheduled_end_at: '2026-07-20T22:00:00Z', notes: null,
    });
    expect(fetchMock.mock.calls[0][1]?.body).toContain('operation-1');
  });

  it('strictly confirms an accepted alternate time', async () => {
    const proposed = schedule({ response_status: 'alternate_proposed', proposed_start_at: '2026-07-20T15:00:00Z', proposed_end_at: '2026-07-20T23:00:00Z' });
    const resolved = schedule({ status: 'published', response_status: 'acknowledged', response_note: 'Approved', scheduled_start_at: proposed.proposed_start_at, scheduled_end_at: proposed.proposed_end_at, proposed_start_at: null, proposed_end_at: null });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(resolved));
    vi.stubGlobal('fetch', fetchMock);
    await rotaApi.acceptAlternate('org-1', parseStaffSchedule(proposed), 'operation-2', 'Approved');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/staff-schedules/schedule-1/alternate/accept');
    expect(fetchMock.mock.calls[0][1]?.body).toContain('expected_updated_at');
  });

  it('rejects an alternate receipt that silently changes the original interval', async () => {
    const proposed = parseStaffSchedule(schedule({ response_status: 'alternate_proposed', proposed_start_at: '2026-07-20T15:00:00Z', proposed_end_at: '2026-07-20T23:00:00Z' }));
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(schedule({ status: 'published', response_status: 'pending', scheduled_start_at: '2026-07-20T15:00:00Z' }))));
    await expect(rotaApi.rejectAlternate('org-1', proposed, 'operation-3', null)).rejects.toThrow('original shift time');
  });
});

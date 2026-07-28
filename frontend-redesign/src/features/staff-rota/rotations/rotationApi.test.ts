import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseRotationPattern, parseRotationPreview, rotationApi } from './rotationApi';

const now = '2026-07-16T12:00:00Z';
const patternDigest = 'a'.repeat(64);
const previewDigest = 'b'.repeat(64);
const slot = { slot_id: 'slot-1', membership_id: 'membership-1', cycle_week: 0, weekday: 0, staff_user_id: 'user-1', room_id: 'room-1', start_local: '08:00', end_local: '16:00', notes: null };
const pattern = (overrides: Record<string, unknown> = {}) => ({
  id: 'rotation-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', name: 'Infant rotation', version: 1, anchor_date: '2026-07-20', cycle_weeks: 1, slots: [slot], status: 'active', snapshot_digest: patternDigest,
  recorded_create_operation_id: 'create-1', recorded_last_operation_id: 'activate-1', created_by_user_id: 'manager-1', activated_at: now, activated_by_user_id: 'manager-1', retired_at: null, retired_by_user_id: null,
  retirement_reason: null, created_at: now, updated_at: now, can_edit: false, can_activate: false, can_retire: true, can_preview: true, can_generate: true, ...overrides,
});
const occurrence = { occurrence_key: 'slot-1:2026-07-20', slot_id: 'slot-1', service_date: '2026-07-20', staff_user_id: 'user-1', membership_id: 'membership-1', staff_display_name: 'Ada Care', room_id: 'room-1', room_name: 'Infants', scheduled_start_at: '2026-07-20T14:00:00Z', scheduled_end_at: '2026-07-20T22:00:00Z', notes: null };
const preview = (overrides: Record<string, unknown> = {}) => ({ pattern_id: 'rotation-1', snapshot_digest: previewDigest, start_date: '2026-07-20', end_date: '2026-07-26', occurrences: [occurrence], total: 1, issues: [], can_generate: true, generated_at: now, ...overrides });
const response = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('rotation API boundary', () => {
  beforeEach(() => vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }));
  afterEach(() => vi.unstubAllGlobals());

  it('rejects inconsistent lifecycle and slot overlap', () => {
    expect(() => parseRotationPattern(pattern({ status: 'draft' }))).toThrow('inconsistent rotation lifecycle');
    expect(() => parseRotationPattern(pattern({ slots: [slot, { ...slot, slot_id: 'slot-2', start_local: '15:00' }] }))).toThrow('overlaps');
    expect(() => parseRotationPattern(pattern({ snapshot_digest: 'not-a-digest' }))).toThrow('snapshot digest');
    expect(() => parseRotationPattern(pattern({ can_preview: false }))).toThrow('lifecycle');
  });

  it('fails closed on pattern, date, occurrence and readiness drift', () => {
    const source = parseRotationPattern(pattern());
    expect(() => parseRotationPreview(preview({ pattern_id: 'rotation-2' }), source, { startDate: '2026-07-20', endDate: '2026-07-26' })).toThrow('crossed');
    expect(() => parseRotationPreview(preview({ total: 2 }), source, { startDate: '2026-07-20', endDate: '2026-07-26' })).toThrow('inconsistent');
    expect(() => parseRotationPreview(preview({ issues: [{ code: 'overlap', message: 'Overlap', occurrence_key: occurrence.occurrence_key, slot_id: slot.slot_id, service_date: occurrence.service_date }], can_generate: true }), source, { startDate: '2026-07-20', endDate: '2026-07-26' })).toThrow('readiness');
  });

  it('verifies exact all-or-none generation receipt', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ pattern_id: 'rotation-1', snapshot_digest: previewDigest, schedule_ids: ['schedule-1'], total: 1, recorded_operation_id: 'generate-1', generated_at: now }));
    vi.stubGlobal('fetch', fetchMock);
    const source = parseRotationPattern(pattern());
    const plan = parseRotationPreview(preview(), source, { startDate: '2026-07-20', endDate: '2026-07-26' });
    await rotationApi.generate(source, plan, 'generate-1');
    expect(fetchMock.mock.calls[0][1]?.body).toContain(`"preview_digest":"${previewDigest}"`);
    expect(fetchMock.mock.calls[0][1]?.body).toContain(`"expected_updated_at":"${now}"`);
  });

  it('sends a read-only bounded preview command without mutation fields', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(preview()));
    vi.stubGlobal('fetch', fetchMock);
    const source = parseRotationPattern(pattern());
    await rotationApi.preview(source, { startDate: '2026-07-20', endDate: '2026-07-26' });
    expect(fetchMock.mock.calls[0][1]?.body).toBe('{"start_date":"2026-07-20","end_date":"2026-07-26"}');
    await expect(rotationApi.preview(source, { startDate: '2026-07-20', endDate: '2026-10-20' })).rejects.toThrow('between 1 and 84');
  });

  it('rejects crossed organization rows in canonical lists', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ items: [pattern({ organization_id: 'org-2' })], total: 1, generated_at: now })));
    await expect(rotationApi.list('org-1', 'facility-1')).rejects.toThrow('boundary');
  });

  it('accepts server-sorted slot receipts and never sends response-only membership ids', async () => {
    const second = { ...slot, slot_id: 'slot-2', weekday: 1 };
    const server = pattern({ status: 'draft', snapshot_digest: null, slots: [slot, second], recorded_create_operation_id: 'create-2', recorded_last_operation_id: 'create-2', activated_at: null, activated_by_user_id: null, can_edit: true, can_activate: true, can_retire: false, can_preview: false, can_generate: false });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(server));
    vi.stubGlobal('fetch', fetchMock);
    const input = { facility_id: 'facility-1', name: 'Infant rotation', anchor_date: '2026-07-20', cycle_weeks: 1, slots: [second, slot].map(({ membership_id: _membershipId, ...item }) => item) };
    await rotationApi.create('org-1', input, 'create-2');
    expect(fetchMock.mock.calls[0][1]?.body).not.toContain('membership_id');
    const draft = parseRotationPattern(server);
    const updateMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ ...server, recorded_last_operation_id: 'update-1' }));
    vi.stubGlobal('fetch', updateMock);
    await rotationApi.update('org-1', draft, input, 'update-1');
    const updateBody = updateMock.mock.calls[0][1]?.body as string;
    expect(updateBody).not.toContain('membership_id');
    expect(updateBody).not.toContain('facility_id');
  });
});

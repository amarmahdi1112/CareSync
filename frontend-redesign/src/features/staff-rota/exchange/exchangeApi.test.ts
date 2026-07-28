import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { exchangeApi, parseEngagement, parseOpenShift, parseSwap } from './exchangeApi';

const now = '2026-07-16T12:00:00Z';
const engagement = (overrides: Record<string, unknown> = {}) => ({
  id: 'engagement-1', organization_id: 'org-1', open_shift_id: 'post-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care', kind: 'offer', status: 'pending', note: null, response_note: null, expires_at: '2026-07-19T12:00:00Z', source_interest_id: null, converted_offer_id: null, resulting_schedule_id: null,
  recorded_create_operation_id: 'offer-1', recorded_last_operation_id: 'offer-1', can_withdraw: true, can_accept: false, can_decline: false, is_expired: false, created_at: now, updated_at: now, ...overrides,
});
const post = (overrides: Record<string, unknown> = {}) => ({
  id: 'post-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infants', source_schedule_id: null,
  scheduled_start_at: '2026-07-20T14:00:00Z', scheduled_end_at: '2026-07-20T22:00:00Z', status: 'open', public_note: 'Coverage available', is_replacement: false, eligibility_reasons: [], can_express_interest: false, my_engagement: null, my_engagements: [],
  recorded_create_operation_id: 'create-1', recorded_last_operation_id: 'post-operation', created_by_user_id: 'manager-1', posted_at: now, posted_by_user_id: 'manager-1', filled_at: null, filled_engagement_id: null, filled_schedule_id: null,
  cancelled_at: null, cancelled_by_user_id: null, cancellation_reason: null, created_at: now, updated_at: now, can_edit: false, can_post: false, can_cancel: true, ...overrides,
});
const candidate = { membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care', substitute_opted_in: true, eligibility: 'eligible', eligibility_reasons: [] };
const scheduleSummary = (id: string, membershipId: string, name: string, start = '2026-07-20T14:00:00Z') => ({ id, membership_id: membershipId, staff_display_name: name, facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infants', scheduled_start_at: start, scheduled_end_at: new Date(Date.parse(start) + 8 * 60 * 60_000).toISOString(), updated_at: now });
const swap = (overrides: Record<string, unknown> = {}) => ({
  id: 'swap-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton', kind: 'trade', status: 'pending_manager', requester_membership_id: 'membership-1', requester_staff_user_id: 'user-1', requester_display_name: 'Ada Care', counterparty_membership_id: 'membership-2', counterparty_staff_user_id: 'user-2', counterparty_display_name: 'Sam Care', requester_schedule_id: 'schedule-1', counterparty_schedule_id: 'schedule-2', requester_schedule: scheduleSummary('schedule-1', 'membership-1', 'Ada Care'), counterparty_schedule: scheduleSummary('schedule-2', 'membership-2', 'Sam Care', '2026-07-21T14:00:00Z'), requester_replacement_schedule_id: null, counterparty_replacement_schedule_id: null, note: 'Trade days', counterparty_response_note: 'Works for me', manager_decision_reason: null, cancellation_reason: null, recorded_create_operation_id: 'swap-create', recorded_last_operation_id: 'counterparty-accept', counterparty_responded_at: now, manager_decided_at: null, cancelled_at: null, created_at: now, updated_at: now, can_counterparty_accept: false, can_counterparty_decline: false, can_cancel: false, can_approve: true, can_reject: true, ...overrides,
});
const response = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('staff exchange API boundary', () => {
  beforeEach(() => vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }));
  afterEach(() => vi.unstubAllGlobals());

  it('rejects impossible posting and engagement lifecycles', () => {
    expect(() => parseOpenShift(post({ status: 'filled' }))).toThrow('inconsistent open-shift lifecycle');
    expect(() => parseOpenShift(post({ source_schedule_id: 'schedule-1', is_replacement: false }))).toThrow('scope');
    expect(() => parseEngagement(engagement({ kind: 'interest', status: 'accepted', resulting_schedule_id: 'schedule-1' }))).toThrow('incompatible');
    expect(() => parseEngagement(engagement({ status: 'accepted', resulting_schedule_id: null }))).toThrow('assignment evidence');
    expect(() => parseOpenShift(post({ can_express_interest: true }))).toThrow('manager scope');
    expect(() => parseOpenShift(post({ my_engagements: [engagement()] }))).toThrow('manager scope');
    expect(() => parseOpenShift(post({ can_edit: true }))).toThrow('capabilities outside manager lifecycle');
    expect(parseOpenShift(post({
      status: 'draft', posted_at: null, posted_by_user_id: null,
      can_edit: false, can_post: false, can_cancel: true,
    })).status).toBe('draft');
  });

  it('fails closed when canonical open shifts cross organization or facility', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ items: [post({ facility_id: 'facility-2' })], total: 1, generated_at: now })));
    await expect(exchangeApi.listOpenShifts('org-1', { facilityId: 'facility-1', startAt: '2026-07-20T00:00:00Z', endAt: '2026-07-27T00:00:00Z' })).rejects.toThrow('facility boundary');
  });

  it('verifies candidate uniqueness and exact targeted offer receipt', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => String(input).includes('/candidates')
      ? response({ items: [candidate], total: 1, generated_at: now })
      : response(engagement()));
    vi.stubGlobal('fetch', fetchMock);
    const source = parseOpenShift(post());
    await exchangeApi.candidates(source);
    await exchangeApi.createOffer('org-1', source, 'offer-1', { staff_user_id: 'user-1', source_interest_id: null, note: null, expires_at: '2026-07-19T12:00:00Z' });
    expect(fetchMock.mock.calls[1][1]?.body).toContain('"client_operation_id":"offer-1"');
  });

  it('requires a syntactically valid offer expiry and validates server-authored expiry capabilities', async () => {
    expect(() => parseEngagement(engagement({ is_expired: true, can_accept: true }))).toThrow('expired-offer capabilities');
    expect(parseEngagement(engagement({ is_expired: true })).is_expired).toBe(true);
    expect(() => parseEngagement(engagement({ can_decline: true }))).toThrow('manager scope');
    vi.stubGlobal('fetch', vi.fn(async () => response(engagement())));
    await expect(exchangeApi.createOffer('org-1', parseOpenShift(post()), 'offer-1', { staff_user_id: 'user-1', source_interest_id: null, note: null, expires_at: 'not-a-time' })).rejects.toThrow('valid offer expiry');
    await expect(exchangeApi.createOffer('org-1', parseOpenShift(post()), 'offer-1', { staff_user_id: 'user-1', source_interest_id: null, note: null, expires_at: '2026-07-20T14:00:00Z' })).rejects.toThrow('before the shift starts');
  });

  it('requires exact interest-to-offer linkage', () => {
    expect(() => parseEngagement(engagement({ kind: 'interest', expires_at: null, source_interest_id: 'other' }))).toThrow('interest-to-offer linkage');
    expect(() => parseEngagement(engagement({ kind: 'interest', status: 'converted', expires_at: null, converted_offer_id: null }))).toThrow('interest-to-offer linkage');
    expect(parseEngagement(engagement({ kind: 'interest', status: 'converted', expires_at: null, converted_offer_id: 'offer-2', can_withdraw: false })).converted_offer_id).toBe('offer-2');
  });

  it('loads engagements only inside the selected posting', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ items: [engagement({ open_shift_id: 'post-2' })], total: 1, generated_at: now })));
    await expect(exchangeApi.engagements('org-1', parseOpenShift(post()))).rejects.toThrow('selected open-shift boundary');
  });

  it('strictly validates swap participant, schedule and approval cardinality', () => {
    expect(() => parseSwap(swap({ counterparty_schedule_id: 'schedule-3' }))).toThrow('boundary');
    expect(() => parseSwap(swap({ status: 'approved', requester_replacement_schedule_id: 'replacement-1', counterparty_replacement_schedule_id: null, manager_decided_at: now }))).toThrow('lifecycle');
    expect(() => parseSwap(swap({ can_approve: false }))).toThrow('manager scope');
    expect(() => parseSwap(swap({ can_counterparty_accept: true }))).toThrow('manager scope');
    expect(parseSwap(swap()).status).toBe('pending_manager');
    expect(parseSwap(swap({ status: 'declined', counterparty_response_note: null, can_approve: false, can_reject: false })).status).toBe('declined');
  });

  it('requires exact operation and reason on a manager rejection receipt', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(swap({ status: 'rejected', manager_decided_at: now, manager_decision_reason: 'Coverage risk', recorded_last_operation_id: 'reject-1', can_approve: false, can_reject: false })));
    vi.stubGlobal('fetch', fetchMock);
    await exchangeApi.rejectSwap('org-1', parseSwap(swap()), 'reject-1', 'Coverage risk');
    expect(fetchMock.mock.calls[0][1]?.body).toContain('"reason":"Coverage risk"');
  });
});

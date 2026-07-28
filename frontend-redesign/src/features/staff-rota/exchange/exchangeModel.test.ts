import { describe, expect, it } from 'vitest';
import { engagementStatusLabel, filterCandidates, managerOfferPath, managerOfferWindowOpen, sortOpenShifts, sortSwaps, swapStatusLabel, validateManagerOfferExpiry, validateOpenShiftInput } from './exchangeModel';
import type { OpenShiftCandidate, OpenShiftEngagement } from './exchangeTypes';

const candidate = (overrides: Partial<OpenShiftCandidate> = {}): OpenShiftCandidate => ({ membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care', substitute_opted_in: false, eligibility: 'eligible', eligibility_reasons: [], ...overrides });
const engagement = (overrides: Partial<OpenShiftEngagement> = {}): OpenShiftEngagement => ({ id: 'interest-1', organization_id: 'org-1', open_shift_id: 'post-1', membership_id: 'membership-1', staff_user_id: 'user-1', staff_display_name: 'Ada Care', kind: 'interest', status: 'pending', note: null, response_note: null, expires_at: null, is_expired: false, source_interest_id: null, converted_offer_id: null, resulting_schedule_id: null, recorded_create_operation_id: 'create-1', recorded_last_operation_id: 'create-1', can_withdraw: true, can_accept: false, can_decline: false, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z', ...overrides });

describe('staff exchange model', () => {
  it('validates bounded concrete open-shift intervals', () => {
    expect(validateOpenShiftInput({ facility_id: 'facility-1', scheduled_start_at: '2026-07-20T14:00:00Z', scheduled_end_at: '2026-07-20T22:00:00Z', public_note: null })).toEqual([]);
    expect(validateOpenShiftInput({ facility_id: '', scheduled_start_at: '2026-07-20T22:00:00Z', scheduled_end_at: '2026-07-20T14:00:00Z', public_note: null })).toEqual(['Choose a facility.', 'Shift end must be after shift start.']);
  });

  it('puts actionable coverage ahead of history', () => {
    const values = [{ id: 'filled', status: 'filled', scheduled_start_at: '2026-07-20' }, { id: 'open', status: 'open', scheduled_start_at: '2026-07-21' }, { id: 'draft', status: 'draft', scheduled_start_at: '2026-07-19' }];
    expect(sortOpenShifts(values as never).map((item) => item.id)).toEqual(['open', 'draft', 'filled']);
  });

  it('uses staff-visible participation labels and searchable candidates', () => {
    expect(engagementStatusLabel({ kind: 'offer', status: 'pending', is_expired: false })).toBe('Offer needs response');
    expect(engagementStatusLabel({ kind: 'offer', status: 'pending', is_expired: true })).toBe('Expired');
    expect(engagementStatusLabel({ kind: 'interest', status: 'superseded', is_expired: false })).toBe('Not selected');
    const candidates = [{ staff_display_name: 'Ada Care', eligibility: 'eligible' }, { staff_display_name: 'Sam North', eligibility: 'warning' }];
    expect(filterCandidates(candidates as never, 'ada', 'eligible').map((item) => item.staff_display_name)).toEqual(['Ada Care']);
  });

  it('puts manager swap decisions ahead of passive and historical states', () => {
    const schedule = (value: string) => ({ scheduled_start_at: value });
    const values = [{ id: 'history', status: 'approved', requester_schedule: schedule('2026-07-19') }, { id: 'peer', status: 'pending_counterparty', requester_schedule: schedule('2026-07-20') }, { id: 'manager', status: 'pending_manager', requester_schedule: schedule('2026-07-21') }];
    expect(sortSwaps(values as never).map((item) => item.id)).toEqual(['manager', 'peer', 'history']);
    expect(swapStatusLabel('pending_manager')).toBe('Awaiting manager');
  });

  it('requires substitute consent or a pending interest before a manager offer', () => {
    expect(managerOfferPath(candidate(), [])).toMatchObject({ allowed: false, sourceInterestId: null });
    expect(managerOfferPath(candidate({ substitute_opted_in: true }), [])).toEqual({ allowed: true, sourceInterestId: null, reason: null });
    expect(managerOfferPath(candidate(), [engagement()])).toEqual({ allowed: true, sourceInterestId: 'interest-1', reason: null });
    expect(managerOfferPath(candidate({ eligibility: 'ineligible' }), [engagement()]).allowed).toBe(false);
    expect(managerOfferPath(candidate({ substitute_opted_in: true }), [engagement({ id: 'offer-1', kind: 'offer', expires_at: '2026-07-20T12:00:00Z' })]).reason).toBe('A pending offer already exists.');
  });

  it('bounds an offer after server time and strictly before the shift', () => {
    expect(managerOfferWindowOpen('2026-07-20T13:00:00Z', '2026-07-20T13:07:00Z')).toBe(true);
    expect(managerOfferWindowOpen('2026-07-20T13:00:00Z', '2026-07-20T13:06:00Z')).toBe(false);
    expect(validateManagerOfferExpiry('2026-07-20T13:30:00Z', '2026-07-20T13:00:00Z', '2026-07-20T14:00:00Z')).toBeNull();
    expect(validateManagerOfferExpiry('2026-07-20T14:00:00Z', '2026-07-20T13:00:00Z', '2026-07-20T14:00:00Z')).toContain('strictly before');
    expect(validateManagerOfferExpiry('2026-07-20T12:59:00Z', '2026-07-20T13:00:00Z', '2026-07-20T14:00:00Z')).toContain('server time');
  });
});

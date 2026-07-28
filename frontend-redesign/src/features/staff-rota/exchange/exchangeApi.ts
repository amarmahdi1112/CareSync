import { ApiError, apiRequest } from '../../../api/client';
import type {
  ExchangeList,
  OpenShiftCandidate,
  OpenShiftEngagement,
  OpenShiftInput,
  OpenShiftOfferInput,
  OpenShiftPosting,
  ShiftSwapRequest,
  ShiftSwapScheduleSummary,
  SubstituteCandidate,
} from './exchangeTypes';

export const EXCHANGE_ENDPOINTS = {
  root: '/staff-exchange',
  openShifts: '/staff-exchange/open-shifts',
  engagements: '/staff-exchange/open-shift-engagements',
  substitutes: '/staff-exchange/substitutes',
  swaps: '/staff-exchange/swaps',
} as const;

export class ExchangeApiError extends Error {
  constructor(message: string) { super(message); this.name = 'ExchangeApiError'; }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ExchangeApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const text = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new ExchangeApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableText = (value: unknown, label: string): string | null => value == null ? null : text(value, label);
const timestamp = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (Number.isNaN(Date.parse(result))) throw new ExchangeApiError(`The server returned an invalid ${label}.`);
  return result;
};
const nullableTimestamp = (value: unknown, label: string): string | null => value == null ? null : timestamp(value, label);
const boolean = (value: unknown, label: string): boolean => {
  if (typeof value !== 'boolean') throw new ExchangeApiError(`The server returned an invalid ${label}.`);
  return value;
};
const integer = (value: unknown, label: string, maximum = Number.MAX_SAFE_INTEGER): number => {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > maximum) throw new ExchangeApiError(`The server returned an invalid ${label}.`);
  return Number(value);
};
const timeZone = (value: unknown, label: string): string => {
  const result = text(value, label);
  try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new ExchangeApiError(`The server returned an invalid ${label}.`); }
  return result;
};
const choice = <T extends string>(value: unknown, label: string, values: readonly T[]): T => {
  const result = text(value, label);
  if (!values.includes(result as T)) throw new ExchangeApiError(`The server returned an unsupported ${label}.`);
  return result as T;
};
const array = <T,>(value: unknown, label: string, parser: (item: unknown) => T): T[] => {
  if (!Array.isArray(value)) throw new ExchangeApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};
const stringList = (value: unknown, label: string): string[] => {
  const result = array(value, label, (item) => text(item, label));
  if (new Set(result).size !== result.length) throw new ExchangeApiError(`The server returned duplicate ${label}.`);
  return result;
};

export function parseEngagement(value: unknown): OpenShiftEngagement {
  const row = object(value, 'open-shift engagement');
  const result: OpenShiftEngagement = {
    id: text(row.id, 'engagement id'), organization_id: text(row.organization_id, 'engagement organization id'), open_shift_id: text(row.open_shift_id, 'engagement open-shift id'),
    membership_id: text(row.membership_id, 'engagement membership id'), staff_user_id: text(row.staff_user_id, 'engagement staff user id'), staff_display_name: text(row.staff_display_name, 'engagement staff name'),
    kind: choice(row.kind, 'engagement kind', ['interest', 'offer'] as const), status: choice(row.status, 'engagement status', ['pending', 'accepted', 'declined', 'withdrawn', 'rejected', 'converted', 'superseded'] as const),
    note: nullableText(row.note, 'engagement note'), response_note: nullableText(row.response_note, 'engagement response note'), expires_at: nullableTimestamp(row.expires_at, 'engagement expiry'), is_expired: boolean(row.is_expired, 'engagement expiry state'), source_interest_id: nullableText(row.source_interest_id, 'engagement source interest id'), converted_offer_id: nullableText(row.converted_offer_id, 'engagement converted offer id'), resulting_schedule_id: nullableText(row.resulting_schedule_id, 'engagement resulting schedule id'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'engagement create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'engagement action receipt'),
    can_withdraw: boolean(row.can_withdraw, 'engagement withdrawal capability'), can_accept: boolean(row.can_accept, 'engagement acceptance capability'), can_decline: boolean(row.can_decline, 'engagement decline capability'),
    created_at: timestamp(row.created_at, 'engagement creation time'), updated_at: timestamp(row.updated_at, 'engagement update time'),
  };
  const allowed = result.kind === 'interest' ? ['pending', 'withdrawn', 'rejected', 'converted', 'superseded'] : ['pending', 'accepted', 'declined', 'withdrawn', 'superseded'];
  if (!allowed.includes(result.status)) throw new ExchangeApiError('The server returned a status incompatible with the engagement kind.');
  if ((result.status === 'accepted') !== (result.resulting_schedule_id !== null)) throw new ExchangeApiError('The server returned inconsistent engagement assignment evidence.');
  if (result.kind === 'interest' && result.expires_at !== null || result.kind === 'offer' && result.expires_at === null) throw new ExchangeApiError('The server returned inconsistent engagement expiry evidence.');
  if (result.kind === 'interest' && result.source_interest_id !== null || result.kind === 'offer' && result.converted_offer_id !== null || (result.status === 'converted') !== (result.converted_offer_id !== null)) throw new ExchangeApiError('The server returned inconsistent interest-to-offer linkage.');
  if (result.source_interest_id === result.id || result.converted_offer_id === result.id) throw new ExchangeApiError('The server returned a self-referencing engagement link.');
  if (result.is_expired && (result.kind !== 'offer' || result.status !== 'pending' || result.can_accept || result.can_decline)) throw new ExchangeApiError('The server returned inconsistent expired-offer capabilities.');
  if (result.can_accept || result.can_decline || result.can_withdraw !== (result.kind === 'offer' && result.status === 'pending')) throw new ExchangeApiError('The server returned engagement capabilities outside manager scope.');
  return result;
}

export function parseOpenShift(value: unknown): OpenShiftPosting {
  const row = object(value, 'open shift');
  const selfReasons = stringList(row.eligibility_reasons, 'open-shift self eligibility reasons');
  const selfCanExpress = boolean(row.can_express_interest, 'open-shift self interest capability');
  if (row.my_engagement !== null || !Array.isArray(row.my_engagements) || row.my_engagements.length || selfCanExpress || selfReasons.length) throw new ExchangeApiError('The server returned self-only open-shift fields in manager scope.');
  const result: OpenShiftPosting = {
    id: text(row.id, 'open-shift id'), organization_id: text(row.organization_id, 'open-shift organization id'), facility_id: text(row.facility_id, 'open-shift facility id'), facility_name: text(row.facility_name, 'open-shift facility name'), facility_timezone: timeZone(row.facility_timezone, 'open-shift facility timezone'),
    room_id: nullableText(row.room_id, 'open-shift room id'), room_name: nullableText(row.room_name, 'open-shift room name'), source_schedule_id: nullableText(row.source_schedule_id, 'open-shift source schedule id'),
    scheduled_start_at: timestamp(row.scheduled_start_at, 'open-shift start'), scheduled_end_at: timestamp(row.scheduled_end_at, 'open-shift end'), status: choice(row.status, 'open-shift status', ['draft', 'open', 'filled', 'cancelled'] as const),
    public_note: nullableText(row.public_note, 'open-shift public note'), is_replacement: boolean(row.is_replacement, 'open-shift replacement state'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'open-shift create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'open-shift action receipt'), created_by_user_id: text(row.created_by_user_id, 'open-shift creator id'),
    posted_at: nullableTimestamp(row.posted_at, 'open-shift posting time'), posted_by_user_id: nullableText(row.posted_by_user_id, 'open-shift posting actor'), filled_at: nullableTimestamp(row.filled_at, 'open-shift fill time'), filled_engagement_id: nullableText(row.filled_engagement_id, 'open-shift filled engagement'), filled_schedule_id: nullableText(row.filled_schedule_id, 'open-shift filled schedule'),
    cancelled_at: nullableTimestamp(row.cancelled_at, 'open-shift cancellation time'), cancelled_by_user_id: nullableText(row.cancelled_by_user_id, 'open-shift cancellation actor'), cancellation_reason: nullableText(row.cancellation_reason, 'open-shift cancellation reason'),
    created_at: timestamp(row.created_at, 'open-shift creation time'), updated_at: timestamp(row.updated_at, 'open-shift update time'), can_edit: boolean(row.can_edit, 'open-shift edit capability'), can_post: boolean(row.can_post, 'open-shift posting capability'), can_cancel: boolean(row.can_cancel, 'open-shift cancellation capability'),
  };
  if (Date.parse(result.scheduled_end_at) <= Date.parse(result.scheduled_start_at) || result.room_id == null !== (result.room_name == null) || result.is_replacement !== (result.source_schedule_id !== null)) throw new ExchangeApiError('The server returned an inconsistent open-shift scope or interval.');
  const postedComplete = result.posted_at !== null && result.posted_by_user_id !== null;
  const postedPartial = (result.posted_at === null) !== (result.posted_by_user_id === null);
  const filledComplete = result.filled_at !== null && result.filled_engagement_id !== null && result.filled_schedule_id !== null;
  const filledAny = result.filled_at !== null || result.filled_engagement_id !== null || result.filled_schedule_id !== null;
  const cancelledComplete = result.cancelled_at !== null && result.cancelled_by_user_id !== null && result.cancellation_reason !== null;
  const cancelledAny = result.cancelled_at !== null || result.cancelled_by_user_id !== null || result.cancellation_reason !== null;
  if (postedPartial || result.status === 'draft' && (postedComplete || filledAny || cancelledAny)
    || result.status === 'open' && (!postedComplete || filledAny || cancelledAny)
    || result.status === 'filled' && (!postedComplete || !filledComplete || cancelledAny)
    || result.status === 'cancelled' && (!cancelledComplete || filledAny)) throw new ExchangeApiError('The server returned an inconsistent open-shift lifecycle.');
  if (result.can_edit !== result.can_post
    || (result.can_edit && result.status !== 'draft')
    || result.can_cancel !== (result.status === 'draft' || result.status === 'open')) throw new ExchangeApiError('The server returned open-shift capabilities outside manager lifecycle.');
  return result;
}

export function parseCandidate(value: unknown): OpenShiftCandidate {
  const row = object(value, 'open-shift candidate');
  return {
    membership_id: text(row.membership_id, 'candidate membership id'), staff_user_id: text(row.staff_user_id, 'candidate staff user id'), staff_display_name: text(row.staff_display_name, 'candidate staff name'), substitute_opted_in: boolean(row.substitute_opted_in, 'candidate substitute preference'), eligibility: choice(row.eligibility, 'candidate eligibility', ['eligible', 'warning', 'ineligible'] as const), eligibility_reasons: stringList(row.eligibility_reasons, 'candidate eligibility reasons'),
  };
}

function parseSubstitute(value: unknown): SubstituteCandidate {
  const row = object(value, 'substitute candidate');
  const candidate = parseCandidate(row);
  if (!candidate.substitute_opted_in) throw new ExchangeApiError('The substitute discovery list included staff who did not opt in.');
  return { ...candidate, facility_id: text(row.facility_id, 'substitute facility id'), facility_name: text(row.facility_name, 'substitute facility name'), facility_timezone: timeZone(row.facility_timezone, 'substitute facility timezone') };
}

function parseSwapSchedule(value: unknown): ShiftSwapScheduleSummary {
  const row = object(value, 'swap schedule summary');
  const result: ShiftSwapScheduleSummary = {
    id: text(row.id, 'swap schedule id'), membership_id: text(row.membership_id, 'swap schedule membership id'), staff_display_name: text(row.staff_display_name, 'swap schedule staff name'),
    facility_id: text(row.facility_id, 'swap schedule facility id'), facility_name: text(row.facility_name, 'swap schedule facility name'), facility_timezone: timeZone(row.facility_timezone, 'swap schedule facility timezone'),
    room_id: nullableText(row.room_id, 'swap schedule room id'), room_name: nullableText(row.room_name, 'swap schedule room name'), scheduled_start_at: timestamp(row.scheduled_start_at, 'swap schedule start'), scheduled_end_at: timestamp(row.scheduled_end_at, 'swap schedule end'), updated_at: timestamp(row.updated_at, 'swap schedule update time'),
  };
  if (result.room_id == null !== (result.room_name == null) || Date.parse(result.scheduled_end_at) <= Date.parse(result.scheduled_start_at)) throw new ExchangeApiError('The server returned an inconsistent swap schedule summary.');
  return result;
}

export function parseSwap(value: unknown): ShiftSwapRequest {
  const row = object(value, 'shift swap');
  const canCounterpartyAccept = boolean(row.can_counterparty_accept, 'swap counterparty acceptance capability');
  const canCounterpartyDecline = boolean(row.can_counterparty_decline, 'swap counterparty decline capability');
  const canSelfCancel = boolean(row.can_cancel, 'swap self cancellation capability');
  if (canCounterpartyAccept || canCounterpartyDecline || canSelfCancel) throw new ExchangeApiError('The server returned self-only swap capabilities in manager scope.');
  const requesterSchedule = parseSwapSchedule(row.requester_schedule);
  const counterpartySchedule = row.counterparty_schedule == null ? null : parseSwapSchedule(row.counterparty_schedule);
  const result: ShiftSwapRequest = {
    id: text(row.id, 'swap id'), organization_id: text(row.organization_id, 'swap organization id'), facility_id: text(row.facility_id, 'swap facility id'), facility_name: text(row.facility_name, 'swap facility name'), facility_timezone: timeZone(row.facility_timezone, 'swap facility timezone'),
    kind: choice(row.kind, 'swap kind', ['cover', 'trade'] as const), status: choice(row.status, 'swap status', ['pending_counterparty', 'pending_manager', 'approved', 'declined', 'cancelled', 'rejected'] as const),
    requester_membership_id: text(row.requester_membership_id, 'swap requester membership'), requester_staff_user_id: text(row.requester_staff_user_id, 'swap requester user'), requester_display_name: text(row.requester_display_name, 'swap requester name'),
    counterparty_membership_id: text(row.counterparty_membership_id, 'swap counterparty membership'), counterparty_staff_user_id: text(row.counterparty_staff_user_id, 'swap counterparty user'), counterparty_display_name: text(row.counterparty_display_name, 'swap counterparty name'),
    requester_schedule_id: text(row.requester_schedule_id, 'swap requester schedule id'), counterparty_schedule_id: nullableText(row.counterparty_schedule_id, 'swap counterparty schedule id'), requester_schedule: requesterSchedule, counterparty_schedule: counterpartySchedule,
    requester_replacement_schedule_id: nullableText(row.requester_replacement_schedule_id, 'swap requester replacement id'), counterparty_replacement_schedule_id: nullableText(row.counterparty_replacement_schedule_id, 'swap counterparty replacement id'),
    note: nullableText(row.note, 'swap note'), counterparty_response_note: nullableText(row.counterparty_response_note, 'swap counterparty response note'), manager_decision_reason: nullableText(row.manager_decision_reason, 'swap manager decision reason'), cancellation_reason: nullableText(row.cancellation_reason, 'swap cancellation reason'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'swap create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'swap action receipt'),
    counterparty_responded_at: nullableTimestamp(row.counterparty_responded_at, 'swap counterparty response time'), manager_decided_at: nullableTimestamp(row.manager_decided_at, 'swap manager decision time'), cancelled_at: nullableTimestamp(row.cancelled_at, 'swap cancellation time'),
    created_at: timestamp(row.created_at, 'swap creation time'), updated_at: timestamp(row.updated_at, 'swap update time'), can_approve: boolean(row.can_approve, 'swap approval capability'), can_reject: boolean(row.can_reject, 'swap rejection capability'),
  };
  if (result.requester_membership_id === result.counterparty_membership_id || result.requester_schedule_id !== requesterSchedule.id || result.requester_membership_id !== requesterSchedule.membership_id || requesterSchedule.facility_id !== result.facility_id
    || result.kind === 'cover' && (result.counterparty_schedule_id !== null || counterpartySchedule !== null)
    || result.kind === 'trade' && (!result.counterparty_schedule_id || !counterpartySchedule || result.counterparty_schedule_id !== counterpartySchedule.id || result.counterparty_membership_id !== counterpartySchedule.membership_id || counterpartySchedule.facility_id !== result.facility_id)) throw new ExchangeApiError('The shift swap crossed its participant, schedule, or facility boundary.');
  const responded = result.counterparty_responded_at !== null;
  const decided = result.manager_decided_at !== null;
  const cancelled = result.cancelled_at !== null;
  const replacements = [result.requester_replacement_schedule_id, result.counterparty_replacement_schedule_id].filter((item): item is string => Boolean(item));
  if (new Set(replacements).size !== replacements.length || replacements.some((item) => item === result.requester_schedule_id || item === result.counterparty_schedule_id)) throw new ExchangeApiError('The shift swap returned duplicate original or replacement schedules.');
  if (result.status === 'pending_counterparty' && (responded || decided || cancelled || replacements.length || result.counterparty_response_note || result.manager_decision_reason || result.cancellation_reason)
    || result.status === 'pending_manager' && (!responded || decided || cancelled || replacements.length || result.manager_decision_reason || result.cancellation_reason)
    || result.status === 'approved' && (!responded || !decided || cancelled || !result.requester_replacement_schedule_id || result.kind === 'trade' !== Boolean(result.counterparty_replacement_schedule_id) || result.cancellation_reason)
    || result.status === 'declined' && (!responded || decided || cancelled || replacements.length || result.manager_decision_reason || result.cancellation_reason)
    || result.status === 'rejected' && (!responded || !decided || cancelled || replacements.length || !result.manager_decision_reason || result.cancellation_reason)
    || result.status === 'cancelled' && (decided || !cancelled || replacements.length || !result.cancellation_reason || result.manager_decision_reason)) throw new ExchangeApiError('The server returned an inconsistent shift-swap lifecycle.');
  if (result.can_approve !== (result.status === 'pending_manager') || result.can_reject !== (result.status === 'pending_manager')) throw new ExchangeApiError('The server returned swap capabilities outside manager scope.');
  return result;
}

function parseList<T extends { id: string; organization_id: string }>(value: unknown, label: string, parser: (item: unknown) => T, organizationId: string): ExchangeList<T> {
  const row = object(value, `${label} list`);
  const result = { items: array(row.items, `${label} rows`, parser), total: integer(row.total, `${label} total`), generated_at: timestamp(row.generated_at, `${label} list generation time`) };
  if (result.total !== result.items.length || new Set(result.items.map((item) => item.id)).size !== result.items.length) throw new ExchangeApiError(`The ${label} list returned inconsistent totals or duplicate rows.`);
  if (result.items.some((item) => item.organization_id !== organizationId)) throw new ExchangeApiError(`A ${label} crossed the active organization boundary.`);
  return result;
}

function parseCandidates(value: unknown): ExchangeList<OpenShiftCandidate> {
  const row = object(value, 'candidate list');
  const result = { items: array(row.items, 'candidate rows', parseCandidate), total: integer(row.total, 'candidate total'), generated_at: timestamp(row.generated_at, 'candidate list generation time') };
  if (result.total !== result.items.length || new Set(result.items.map((item) => item.membership_id)).size !== result.items.length || new Set(result.items.map((item) => item.staff_user_id)).size !== result.items.length) throw new ExchangeApiError('The candidate list returned inconsistent totals or duplicate staff.');
  return result;
}

function parseSubstitutes(value: unknown, facilityId: string): ExchangeList<SubstituteCandidate> {
  const row = object(value, 'substitute list');
  const result = { items: array(row.items, 'substitute rows', parseSubstitute), total: integer(row.total, 'substitute total'), generated_at: timestamp(row.generated_at, 'substitute list generation time') };
  if (result.total !== result.items.length || new Set(result.items.map((item) => item.membership_id)).size !== result.items.length || result.items.some((item) => item.facility_id !== facilityId)) throw new ExchangeApiError('The substitute list returned inconsistent totals, duplicate staff, or crossed facilities.');
  return result;
}

const query = (values: Record<string, string | undefined>) => { const params = new URLSearchParams(); Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); }); return params.toString(); };
const sameInstant = (left: string, right: string) => Date.parse(left) === Date.parse(right);
const sameInput = (post: OpenShiftPosting, input: OpenShiftInput) => post.facility_id === input.facility_id && post.room_id === input.room_id && post.source_schedule_id === input.source_schedule_id && post.public_note === input.public_note && sameInstant(post.scheduled_start_at, input.scheduled_start_at) && sameInstant(post.scheduled_end_at, input.scheduled_end_at);

export const exchangeApi = {
  listOpenShifts: async (organizationId: string, filters: { facilityId: string; startAt: string; endAt: string }, signal?: AbortSignal) => {
    const result = parseList(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}?${query({ facility_id: filters.facilityId, start_at: filters.startAt, end_at: filters.endAt })}`, { signal }), 'open shift', parseOpenShift, organizationId);
    if (result.items.some((item) => item.facility_id !== filters.facilityId || Date.parse(item.scheduled_start_at) >= Date.parse(filters.endAt) || Date.parse(item.scheduled_end_at) <= Date.parse(filters.startAt))) throw new ExchangeApiError('An open shift crossed the selected facility boundary or date boundary.');
    return result;
  },
  createOpenShift: async (organizationId: string, input: OpenShiftInput, operationId: string) => {
    const result = parseOpenShift(await apiRequest<unknown>(EXCHANGE_ENDPOINTS.openShifts, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, ...input }) }));
    if (result.organization_id !== organizationId || result.status !== 'draft' || result.recorded_create_operation_id !== operationId || result.recorded_last_operation_id !== operationId || !sameInput(result, input)) throw new ExchangeApiError('The server receipt did not match the open shift that was created.');
    return result;
  },
  updateOpenShift: async (organizationId: string, post: OpenShiftPosting, input: OpenShiftInput, operationId: string) => {
    const result = parseOpenShift(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}`, { method: 'PATCH', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: post.updated_at, ...input }) }));
    if (result.id !== post.id || result.organization_id !== organizationId || result.status !== 'draft' || result.recorded_last_operation_id !== operationId || !sameInput(result, input)) throw new ExchangeApiError('The server receipt did not match the open-shift update.');
    return result;
  },
  postOpenShift: async (organizationId: string, post: OpenShiftPosting, operationId: string) => {
    const result = parseOpenShift(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}/post`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: post.updated_at }) }));
    if (result.id !== post.id || result.organization_id !== organizationId || result.status !== 'open' || result.recorded_last_operation_id !== operationId || !result.posted_at) throw new ExchangeApiError('The server did not confirm exact open-shift posting.');
    return result;
  },
  cancelOpenShift: async (organizationId: string, post: OpenShiftPosting, operationId: string, reason: string) => {
    const result = parseOpenShift(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}/cancel`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: post.updated_at, reason }) }));
    if (result.id !== post.id || result.organization_id !== organizationId || result.status !== 'cancelled' || result.recorded_last_operation_id !== operationId || result.cancellation_reason !== reason) throw new ExchangeApiError('The server did not confirm exact open-shift cancellation.');
    return result;
  },
  candidates: async (post: OpenShiftPosting, signal?: AbortSignal) => parseCandidates(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}/candidates`, { signal })),
  engagements: async (organizationId: string, post: OpenShiftPosting, signal?: AbortSignal) => {
    const result = parseList(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}/engagements`, { signal }), 'open-shift engagement', parseEngagement, organizationId);
    if (result.items.some((item) => item.open_shift_id !== post.id)) throw new ExchangeApiError('An engagement crossed the selected open-shift boundary.');
    return result;
  },
  createOffer: async (organizationId: string, post: OpenShiftPosting, operationId: string, payload: OpenShiftOfferInput) => {
    if (Number.isNaN(Date.parse(payload.expires_at))) throw new ExchangeApiError('Choose a valid offer expiry.');
    if (Date.parse(payload.expires_at) >= Date.parse(post.scheduled_start_at)) throw new ExchangeApiError('Offer expiry must be before the shift starts.');
    const result = parseEngagement(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.openShifts}/${encodeURIComponent(post.id)}/offers`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, ...payload }) }));
    if (result.organization_id !== organizationId || result.open_shift_id !== post.id || result.staff_user_id !== payload.staff_user_id || result.kind !== 'offer' || result.status !== 'pending' || result.is_expired || result.source_interest_id !== payload.source_interest_id || result.note !== payload.note || Date.parse(result.expires_at || '') !== Date.parse(payload.expires_at) || result.recorded_create_operation_id !== operationId || result.recorded_last_operation_id !== operationId) throw new ExchangeApiError('The server receipt did not match the targeted offer.');
    return result;
  },
  withdrawEngagement: async (organizationId: string, engagement: OpenShiftEngagement, operationId: string, note: string | null) => {
    const result = parseEngagement(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.engagements}/${encodeURIComponent(engagement.id)}/withdraw`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: engagement.updated_at, note }) }));
    if (result.id !== engagement.id || result.organization_id !== organizationId || result.status !== 'withdrawn' || result.recorded_last_operation_id !== operationId || result.response_note !== note) throw new ExchangeApiError('The server did not confirm exact engagement withdrawal.');
    return result;
  },
  substitutes: async (facilityId: string, signal?: AbortSignal) => parseSubstitutes(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.substitutes}?facility_id=${encodeURIComponent(facilityId)}`, { signal }), facilityId),
  listSwaps: async (organizationId: string, filters: { facilityId: string; startAt: string; endAt: string; status?: ShiftSwapRequest['status'] }, signal?: AbortSignal) => {
    const result = parseList(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.swaps}?${query({ facility_id: filters.facilityId, start_at: filters.startAt, end_at: filters.endAt, status: filters.status })}`, { signal }), 'shift swap', parseSwap, organizationId);
    if (result.items.some((item) => item.facility_id !== filters.facilityId || Date.parse(item.requester_schedule.scheduled_start_at) >= Date.parse(filters.endAt) || Date.parse(item.requester_schedule.scheduled_end_at) <= Date.parse(filters.startAt))) throw new ExchangeApiError('A shift swap crossed the selected facility boundary or date boundary.');
    return result;
  },
  approveSwap: async (organizationId: string, swap: ShiftSwapRequest, operationId: string) => {
    const result = parseSwap(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.swaps}/${encodeURIComponent(swap.id)}/approve`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: swap.updated_at }) }));
    const replacementCount = [result.requester_replacement_schedule_id, result.counterparty_replacement_schedule_id].filter(Boolean).length;
    if (result.id !== swap.id || result.organization_id !== organizationId || result.status !== 'approved' || result.recorded_last_operation_id !== operationId || replacementCount !== (result.kind === 'trade' ? 2 : 1)) throw new ExchangeApiError('The server did not confirm the exact atomic swap approval.');
    return result;
  },
  rejectSwap: async (organizationId: string, swap: ShiftSwapRequest, operationId: string, reason: string) => {
    const result = parseSwap(await apiRequest<unknown>(`${EXCHANGE_ENDPOINTS.swaps}/${encodeURIComponent(swap.id)}/reject`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: swap.updated_at, reason }) }));
    if (result.id !== swap.id || result.organization_id !== organizationId || result.status !== 'rejected' || result.recorded_last_operation_id !== operationId || result.manager_decision_reason !== reason) throw new ExchangeApiError('The server did not confirm the exact swap rejection.');
    return result;
  },
};

export function exchangeErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== 'object') return null;
  const row = error.details as Record<string, unknown>; const detail = row.detail && typeof row.detail === 'object' ? row.detail as Record<string, unknown> : row;
  return typeof detail.code === 'string' ? detail.code : null;
}

export function exchangeErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Staff exchange could not be loaded. Try again.';
}

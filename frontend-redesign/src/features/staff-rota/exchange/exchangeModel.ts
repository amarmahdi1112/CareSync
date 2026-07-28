import type { OpenShiftCandidate, OpenShiftEngagement, OpenShiftPosting, ShiftSwapRequest } from './exchangeTypes';

export function openShiftStatusLabel(status: OpenShiftPosting['status']): string {
  if (status === 'open') return 'Open';
  if (status === 'filled') return 'Filled';
  if (status === 'cancelled') return 'Cancelled';
  return 'Draft';
}

export function engagementStatusLabel(engagement: Pick<OpenShiftEngagement, 'kind' | 'status' | 'is_expired'>): string {
  if (engagement.kind === 'interest' && engagement.status === 'pending') return 'Interest sent';
  if (engagement.kind === 'offer' && engagement.status === 'pending' && engagement.is_expired) return 'Expired';
  if (engagement.kind === 'offer' && engagement.status === 'pending') return 'Offer needs response';
  if (engagement.status === 'accepted') return 'Assigned';
  if (engagement.status === 'declined' || engagement.status === 'rejected') return 'Declined';
  if (engagement.status === 'withdrawn') return 'Withdrawn';
  if (engagement.status === 'superseded') return 'Not selected';
  if (engagement.status === 'converted') return 'Offer sent';
  return engagement.status;
}

export function validateOpenShiftInput(input: { facility_id: string; scheduled_start_at: string; scheduled_end_at: string; public_note: string | null }): string[] {
  const errors: string[] = [];
  if (!input.facility_id) errors.push('Choose a facility.');
  const start = Date.parse(input.scheduled_start_at);
  const end = Date.parse(input.scheduled_end_at);
  if (Number.isNaN(start)) errors.push('Enter a valid shift start.');
  if (Number.isNaN(end)) errors.push('Enter a valid shift end.');
  if (!Number.isNaN(start) && !Number.isNaN(end) && end <= start) errors.push('Shift end must be after shift start.');
  if (!Number.isNaN(start) && !Number.isNaN(end) && end - start > 24 * 60 * 60_000) errors.push('An open shift cannot be longer than 24 hours.');
  if ((input.public_note || '').length > 1000) errors.push('The public note must be 1,000 characters or fewer.');
  return errors;
}

export function sortOpenShifts(items: readonly OpenShiftPosting[]): OpenShiftPosting[] {
  const rank = { open: 0, draft: 1, filled: 2, cancelled: 3 } as const;
  return [...items].sort((left, right) => rank[left.status] - rank[right.status] || left.scheduled_start_at.localeCompare(right.scheduled_start_at));
}

export function filterCandidates(items: readonly OpenShiftCandidate[], query: string, eligibility = 'all'): OpenShiftCandidate[] {
  const normalized = query.trim().toLocaleLowerCase();
  return items.filter((item) => (!normalized || item.staff_display_name.toLocaleLowerCase().includes(normalized)) && (eligibility === 'all' || item.eligibility === eligibility));
}

export function managerOfferPath(candidate: OpenShiftCandidate, engagements: readonly OpenShiftEngagement[]): { allowed: boolean; sourceInterestId: string | null; reason: string | null } {
  const pendingInterest = engagements.find((item) => item.staff_user_id === candidate.staff_user_id && item.kind === 'interest' && item.status === 'pending') || null;
  const pendingOffer = engagements.find((item) => item.staff_user_id === candidate.staff_user_id && item.kind === 'offer' && item.status === 'pending') || null;
  if (pendingOffer) return { allowed: false, sourceInterestId: null, reason: 'A pending offer already exists.' };
  if (candidate.eligibility === 'ineligible') return { allowed: false, sourceInterestId: null, reason: 'This educator is not eligible for the shift.' };
  if (pendingInterest) return { allowed: true, sourceInterestId: pendingInterest.id, reason: null };
  if (candidate.substitute_opted_in && candidate.eligibility === 'eligible') return { allowed: true, sourceInterestId: null, reason: null };
  return { allowed: false, sourceInterestId: null, reason: candidate.substitute_opted_in ? 'Direct offer unavailable while eligibility needs review.' : 'Direct offer unavailable until this educator expresses interest.' };
}

export function managerOfferWindowOpen(serverTimestamp: string, shiftStartsAt: string): boolean {
  const serverNow = Date.parse(serverTimestamp);
  const shiftStart = Date.parse(shiftStartsAt);
  return !Number.isNaN(serverNow) && !Number.isNaN(shiftStart) && shiftStart - serverNow > 6 * 60_000;
}

export function validateManagerOfferExpiry(expiresAt: string, serverTimestamp: string, shiftStartsAt: string): string | null {
  const expiry = Date.parse(expiresAt);
  const serverNow = Date.parse(serverTimestamp);
  const shiftStart = Date.parse(shiftStartsAt);
  if ([expiry, serverNow, shiftStart].some(Number.isNaN)) return 'Enter a valid offer expiry.';
  if (expiry <= serverNow) return 'Offer expiry must be after the verified server time.';
  if (expiry >= shiftStart) return 'Offer expiry must be strictly before the shift starts.';
  return null;
}

export function exchangeSummary(posts: readonly OpenShiftPosting[], engagements: readonly OpenShiftEngagement[], pendingManagerSwaps: number) {
  return {
    open: posts.filter((item) => item.status === 'open').length,
    pendingOffers: engagements.filter((item) => item.kind === 'offer' && item.status === 'pending' && !item.is_expired).length,
    pendingInterests: engagements.filter((item) => item.kind === 'interest' && item.status === 'pending').length,
    pendingManagerSwaps,
  };
}

export function swapStatusLabel(status: ShiftSwapRequest['status']): string {
  if (status === 'pending_counterparty') return 'Awaiting coworker';
  if (status === 'pending_manager') return 'Awaiting manager';
  if (status === 'approved') return 'Approved';
  if (status === 'rejected') return 'Rejected by manager';
  if (status === 'declined') return 'Declined by coworker';
  if (status === 'cancelled') return 'Cancelled';
  return status;
}

export function sortSwaps(items: readonly ShiftSwapRequest[]): ShiftSwapRequest[] {
  const rank = { pending_manager: 0, pending_counterparty: 1, approved: 2, rejected: 3, declined: 4, cancelled: 5 } as const;
  return [...items].sort((left, right) => rank[left.status] - rank[right.status] || left.requester_schedule.scheduled_start_at.localeCompare(right.requester_schedule.scheduled_start_at));
}

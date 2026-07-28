export type OpenShiftStatus = 'draft' | 'open' | 'filled' | 'cancelled';
export type OpenShiftEngagementKind = 'interest' | 'offer';
export type OpenShiftEngagementStatus = 'pending' | 'accepted' | 'declined' | 'withdrawn' | 'rejected' | 'converted' | 'superseded';

export interface OpenShiftEngagement {
  id: string;
  organization_id: string;
  open_shift_id: string;
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  kind: OpenShiftEngagementKind;
  status: OpenShiftEngagementStatus;
  note: string | null;
  response_note: string | null;
  expires_at: string | null;
  is_expired: boolean;
  source_interest_id: string | null;
  converted_offer_id: string | null;
  resulting_schedule_id: string | null;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  can_withdraw: boolean;
  can_accept: boolean;
  can_decline: boolean;
  created_at: string;
  updated_at: string;
}

export interface OpenShiftPosting {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  source_schedule_id: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  status: OpenShiftStatus;
  public_note: string | null;
  is_replacement: boolean;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  created_by_user_id: string;
  posted_at: string | null;
  posted_by_user_id: string | null;
  filled_at: string | null;
  filled_engagement_id: string | null;
  filled_schedule_id: string | null;
  cancelled_at: string | null;
  cancelled_by_user_id: string | null;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
  can_post: boolean;
  can_cancel: boolean;
}

export interface OpenShiftCandidate {
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  substitute_opted_in: boolean;
  eligibility: 'eligible' | 'warning' | 'ineligible';
  eligibility_reasons: string[];
}

export interface SubstituteCandidate extends OpenShiftCandidate {
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
}

export type ShiftSwapKind = 'cover' | 'trade';
export type ShiftSwapStatus = 'pending_counterparty' | 'pending_manager' | 'approved' | 'declined' | 'cancelled' | 'rejected';

export interface ShiftSwapScheduleSummary {
  id: string;
  membership_id: string;
  staff_display_name: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  updated_at: string;
}

export interface ShiftSwapRequest {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  kind: ShiftSwapKind;
  status: ShiftSwapStatus;
  requester_membership_id: string;
  requester_staff_user_id: string;
  requester_display_name: string;
  counterparty_membership_id: string;
  counterparty_staff_user_id: string;
  counterparty_display_name: string;
  requester_schedule_id: string;
  counterparty_schedule_id: string | null;
  requester_schedule: ShiftSwapScheduleSummary;
  counterparty_schedule: ShiftSwapScheduleSummary | null;
  requester_replacement_schedule_id: string | null;
  counterparty_replacement_schedule_id: string | null;
  note: string | null;
  counterparty_response_note: string | null;
  manager_decision_reason: string | null;
  cancellation_reason: string | null;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  counterparty_responded_at: string | null;
  manager_decided_at: string | null;
  cancelled_at: string | null;
  can_approve: boolean;
  can_reject: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExchangeList<T> {
  items: T[];
  total: number;
  generated_at: string;
}

export interface OpenShiftInput {
  facility_id: string;
  room_id: string | null;
  source_schedule_id: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  public_note: string | null;
}

export interface OpenShiftOfferInput {
  staff_user_id: string;
  source_interest_id: string | null;
  note: string | null;
  expires_at: string;
}

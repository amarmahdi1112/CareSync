export type StaffScheduleStatus = 'draft' | 'published' | 'cancelled';
export type StaffScheduleResponseStatus = 'pending' | 'acknowledged' | 'declined' | 'alternate_proposed';
export type StaffScheduleOriginType = 'rotation' | 'open_shift' | 'swap';
export type ReconciliationStatus = 'upcoming' | 'active' | 'completed' | 'missed' | 'late' | 'cancelled' | 'unscheduled';

export interface StaffScheduleActualShift {
  id: string;
  membership_id: string;
  facility_id: string;
  scheduled_shift_id: string | null;
  status: 'open' | 'closed';
  clocked_in_at: string;
  clocked_out_at: string | null;
}

export interface StaffSchedule {
  id: string;
  organization_id: string;
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  proposed_start_at: string | null;
  proposed_end_at: string | null;
  notes: string | null;
  status: StaffScheduleStatus;
  response_status: StaffScheduleResponseStatus;
  response_note: string | null;
  responded_at: string | null;
  actual_shift: StaffScheduleActualShift | null;
  reconciliation_status: Exclude<ReconciliationStatus, 'unscheduled'>;
  is_late: boolean;
  minutes_late: number;
  published_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  availability_override_reason: string | null;
  origin_type: StaffScheduleOriginType | null;
  origin_id: string | null;
  origin_occurrence_key: string | null;
  supersedes_schedule_id: string | null;
  recorded_create_operation_id: string;
  created_by_user_id: string;
  published_by_user_id: string | null;
  cancelled_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface UnscheduledStaffShift {
  staff_user_id: string;
  staff_display_name: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  reconciliation_status: 'unscheduled';
  actual_shift: StaffScheduleActualShift;
}

export interface StaffScheduleReconciliation {
  scheduled: StaffSchedule[];
  unscheduled: UnscheduledStaffShift[];
  total_scheduled: number;
  total_unscheduled: number;
  generated_at: string;
}

export interface StaffScheduleList {
  items: StaffSchedule[];
  total: number;
  generated_at: string;
}

export interface StaffScheduleDraft {
  staff_user_id: string;
  facility_id: string;
  room_id: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  notes: string | null;
}

export interface StaffScheduleCreate extends StaffScheduleDraft {
  client_operation_id: string;
}

export interface StaffScheduleUpdate extends StaffScheduleDraft {
  client_operation_id: string;
  expected_updated_at: string;
}

export interface RotaMonitorRow {
  key: string;
  schedule: StaffSchedule | null;
  actual: StaffScheduleActualShift | null;
  unscheduled: UnscheduledStaffShift | null;
  status: ReconciliationStatus;
  minutes_late: number | null;
}

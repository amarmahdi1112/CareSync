import type { CoverageWindow, WeeklyWindow } from './workforceModel';

export interface StaffAvailabilityProfile {
  id: string;
  organization_id: string;
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  windows: WeeklyWindow[];
  note: string | null;
  recorded_operation_id: string;
  created_at: string;
  updated_at: string;
}

export type TimeOffStatus = 'pending' | 'approved' | 'declined' | 'cancelled';
export type TimeOffCategory = 'vacation' | 'sick' | 'personal' | 'medical' | 'bereavement' | 'unpaid' | 'other';

export interface StaffTimeOffRequest {
  id: string;
  organization_id: string;
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  starts_at: string;
  ends_at: string;
  category: TimeOffCategory;
  note: string | null;
  status: TimeOffStatus;
  response_note: string | null;
  can_cancel: boolean;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  decided_at: string | null;
  decided_by_user_id: string | null;
  cancelled_at: string | null;
  cancelled_by_user_id: string | null;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface StaffShiftTemplate {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  name: string;
  weekday: number;
  start_local: string;
  end_local: string;
  notes: string | null;
  is_active: boolean;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  created_by_user_id: string;
  deactivated_at: string | null;
  deactivated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface StaffCoverageTarget {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  windows: CoverageWindow[];
  recorded_last_operation_id: string;
  created_at: string;
  updated_at: string;
}

export interface CoverageProjectionBucket {
  starts_at: string;
  ends_at: string;
  required: number;
  published: number;
  acknowledged: number;
  declined: number;
  draft: number;
  gap: number;
  confirmation_gap: number;
}

export interface CoverageProjection {
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string | null;
  room_name: string | null;
  start_date: string;
  end_date: string;
  interval_minutes: 15;
  buckets: CoverageProjectionBucket[];
  total_buckets: number;
  gap_buckets: number;
  generated_at: string;
}

export interface WorkforceList<T> {
  items: T[];
  total: number;
  generated_at: string;
}

export interface WorkforceSnapshot {
  availability: WorkforceList<StaffAvailabilityProfile>;
  timeOff: WorkforceList<StaffTimeOffRequest>;
  templates: WorkforceList<StaffShiftTemplate>;
  targets: WorkforceList<StaffCoverageTarget>;
  projection: CoverageProjection;
}

export type RotationStatus = 'draft' | 'active' | 'retired';

export interface RotationSlot {
  slot_id: string;
  membership_id: string;
  cycle_week: number;
  weekday: number;
  staff_user_id: string;
  room_id: string | null;
  start_local: string;
  end_local: string;
  notes: string | null;
}

export interface RotationPattern {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  name: string;
  version: number;
  status: RotationStatus;
  anchor_date: string;
  cycle_weeks: number;
  slots: RotationSlot[];
  snapshot_digest: string | null;
  can_edit: boolean;
  can_activate: boolean;
  can_retire: boolean;
  can_preview: boolean;
  can_generate: boolean;
  recorded_create_operation_id: string;
  recorded_last_operation_id: string;
  created_by_user_id: string;
  activated_at: string | null;
  activated_by_user_id: string | null;
  retired_at: string | null;
  retired_by_user_id: string | null;
  retirement_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface RotationOccurrence {
  occurrence_key: string;
  slot_id: string;
  service_date: string;
  membership_id: string;
  staff_user_id: string;
  staff_display_name: string;
  room_id: string | null;
  room_name: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  notes: string | null;
}

export interface RotationPreviewIssue {
  code: string;
  message: string;
  occurrence_key: string | null;
  slot_id: string | null;
  service_date: string | null;
}

export interface RotationPreview {
  pattern_id: string;
  start_date: string;
  end_date: string;
  snapshot_digest: string;
  occurrences: RotationOccurrence[];
  total: number;
  issues: RotationPreviewIssue[];
  can_generate: boolean;
  generated_at: string;
}

export interface RotationGenerationReceipt {
  pattern_id: string;
  snapshot_digest: string;
  recorded_operation_id: string;
  schedule_ids: string[];
  total: number;
  generated_at: string;
}

export interface RotationSlotInput {
  slot_id: string;
  cycle_week: number;
  weekday: number;
  staff_user_id: string;
  room_id: string | null;
  start_local: string;
  end_local: string;
  notes: string | null;
}

export interface RotationPatternInput {
  facility_id: string;
  name: string;
  anchor_date: string;
  cycle_weeks: number;
  slots: RotationSlotInput[];
}

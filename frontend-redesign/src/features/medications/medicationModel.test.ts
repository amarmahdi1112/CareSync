import { describe, expect, it } from 'vitest';
import type { MedicationAdministration, MedicationDayChild, MedicationPlan } from './medicationApi';
import {
  authorizationEvidenceLabel,
  canRecordMedication,
  medicationDayCounts,
  medicationDueItems,
  medicationPlanGate,
} from './medicationModel';

const plan = (overrides: Partial<MedicationPlan> = {}): MedicationPlan => ({
  id: 'plan-1', organization_id: 'org-1', facility_id: 'facility-1', child_id: 'child-1', child_name: 'Child One', medication_name: 'Prescribed medicine', dosage: 'Labelled dose', route: 'oral', label_directions: 'Follow the original pharmacy label.', scheduled_times: ['09:00', '15:00'], as_needed: false, start_date: '2026-07-01', end_date: null, medication_kind: 'non_emergency', storage_method: 'locked_inaccessible', storage_instructions: 'Locked cabinet', emergency_plan_reference: null, status: 'active', authorization_status: 'verified', authorization_is_current: true, signed_authorization_reference: 'Consent file CS-7', authorization_guardian_id: 'guardian-1', authorization_guardian_name: 'Parent One', authorization_signed_at: '2026-07-01T15:00:00Z', authorization_valid_until: '2026-08-01', authorization_verified_at: '2026-07-01T16:00:00Z', authorization_verified_by_user_id: 'owner-1', authorization_revoked_at: null, authorization_revocation_reason: null, original_labelled_container_verified_at: '2026-07-01T16:05:00Z', label_directions_verified_at: '2026-07-01T16:05:00Z', created_by_user_id: 'owner-1', created_by_name: 'Owner One', eligible_guardians: [], signed_authorization_required: true, version: 2, archived_at: null, archive_reason: null, last_event_type: 'activated', created_at: '2026-07-01T15:00:00Z', updated_at: '2026-07-01T16:00:00Z',
  ...overrides,
});

const administration = (overrides: Partial<MedicationAdministration> = {}): MedicationAdministration => ({
  id: 'administration-1',
  organization_id: 'org-1',
  facility_id: 'facility-1',
  room_id: 'room-1',
  child_id: 'child-1',
  enrollment_id: 'enrollment-1',
  attendance_day_id: 'day-1',
  medication_plan_id: 'plan-1',
  plan_version: 2,
  service_date: '2026-07-15',
  outcome: 'administered',
  scheduled_for: '09:00',
  occurred_at: '2026-07-15T09:00:00-06:00',
  amount: 'Labelled dose',
  reason: null,
  note: null,
  plan_snapshot: { medication_name: 'Prescribed medicine', dosage: 'Labelled dose', route: 'oral', label_directions: 'Follow label', scheduled_times: ['09:00', '15:00'], as_needed: false, medication_kind: 'non_emergency', storage_method: 'locked_inaccessible', authorization_status: 'verified', signed_authorization_reference: 'Consent file CS-7', authorization_guardian_name: 'Parent One', authorization_signed_at: '2026-07-01T15:00:00Z', authorization_valid_until: '2026-08-01', plan_version: 2 },
  staff_name_snapshot: 'Care Educator',
  staff_initials_snapshot: 'CE',
  created_by_user_id: 'educator-1',
  created_by_name: 'Care Educator',
  version: 1,
  voided_at: null,
  voided_by_user_id: null,
  void_reason: null,
  last_event_type: 'recorded',
  was_corrected: false,
  created_at: '2026-07-15T09:00:00-06:00',
  updated_at: '2026-07-15T09:00:00-06:00',
  ...overrides,
});

const child = (overrides: Partial<MedicationDayChild> = {}): MedicationDayChild => ({
  child_id: 'child-1', child_name: 'Child One', profile_photo_url: null, enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', attendance_state: 'on_site', eligible_guardians: [], plans: [plan()], administrations: [administration()],
  ...overrides,
});

describe('medication safety model', () => {
  it('fails closed on absent, revoked, expired, or out-of-range consent evidence', () => {
    expect(medicationPlanGate(plan({ authorization_status: 'not_recorded', authorization_is_current: false }), '2026-07-15')).toBe('authorization_missing');
    expect(medicationPlanGate(plan({ authorization_status: 'revoked', authorization_is_current: false }), '2026-07-15')).toBe('authorization_revoked');
    expect(medicationPlanGate(plan({ authorization_valid_until: '2026-07-14', authorization_is_current: false }), '2026-07-15')).toBe('authorization_expired');
    expect(medicationPlanGate(plan({ start_date: '2026-07-16' }), '2026-07-15')).toBe('outside_date_range');
    expect(authorizationEvidenceLabel(plan({ authorization_status: 'not_recorded', authorization_is_current: false }), '2026-07-15')).toContain('not recorded');
  });

  it('only permits recording for an on-site child and an active evidenced plan', () => {
    expect(canRecordMedication(child(), plan(), '2026-07-15')).toBe(true);
    expect(canRecordMedication(child({ attendance_state: 'checked_out' }), plan(), '2026-07-15')).toBe(false);
    expect(canRecordMedication(child(), plan({ status: 'draft' }), '2026-07-15')).toBe(false);
  });

  it('builds scheduled and as-needed work without inventing an as-needed administration', () => {
    const result = medicationDueItems(child({ plans: [plan({ as_needed: true })] }), '2026-07-15');
    expect(result).toHaveLength(3);
    expect(result[0].administration?.id).toBe('administration-1');
    expect(result[2]).toMatchObject({ kind: 'as_needed', dueTime: null, administration: null });
  });

  it('counts due, recorded, ready, and blocked work separately', () => {
    const blocked = plan({ id: 'plan-2', authorization_status: 'not_recorded', authorization_is_current: false, signed_authorization_reference: null, authorization_guardian_id: null, authorization_guardian_name: null, authorization_signed_at: null, authorization_valid_until: null, authorization_verified_at: null, authorization_verified_by_user_id: null, original_labelled_container_verified_at: null, label_directions_verified_at: null, last_event_type: 'updated' });
    const result = medicationDayCounts([child({ plans: [plan(), blocked] })], '2026-07-15');
    expect(result).toEqual({ children: 1, activePlans: 1, due: 4, recorded: 1, blocked: 1 });
  });
});

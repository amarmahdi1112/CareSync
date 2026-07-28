import { describe, expect, it } from 'vitest';
import {
  AttendanceApiError,
  buildAttendanceMutationPayload,
  parseAttendanceDay,
  parseAttendanceReleaseCheckoutActivationStatus,
  parseAttendanceRosterRow,
} from './attendanceApi';

const day = {
  id: 'day', organization_id: 'org', facility_id: 'facility', child_id: 'child', enrollment_id: 'enrollment', service_date: '2026-07-14', status: 'present', absence_reason: null, notes: null, version: 1, child_name: 'Test Child', intervals: [], events: [], created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z',
};
const releaseActivation = {
  schema_version: 'release-checkout-activation-status-v1',
  organization_id: 'org',
  facility_id: 'facility',
  facility_name: 'Main',
  runtime_available: true,
  activation_command_available: true,
  database_writable: true,
  actor_authorized: true,
  facility_active: true,
  activated: true,
  legacy_checkout_allowed: false,
  activation_policy_version: 'normal_verified_release_v1',
  open_enrollment_children: 2,
  release_ready_children: 2,
  children_needing_authority_review: 0,
  prerequisites: [
    { code: 'runtime_available', label: 'Runtime', satisfied: true },
    { code: 'activation_command_available', label: 'Command', satisfied: true },
    { code: 'database_writable', label: 'Writable', satisfied: true },
    { code: 'facility_active', label: 'Facility', satisfied: true },
    { code: 'privileged_actor', label: 'Actor', satisfied: true },
    { code: 'authority_records_complete', label: 'Authority', satisfied: true },
    { code: 'not_already_activated', label: 'Inactive', satisfied: false },
  ],
  can_activate: false,
  confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT',
};

describe('attendance API adapters', () => {
  it('accepts an actual Basic attendance day', () => {
    expect(parseAttendanceDay(day)).toMatchObject({ organization_id: 'org', facility_id: 'facility', status: 'present' });
  });

  it('rejects unknown statuses and missing event arrays', () => {
    expect(() => parseAttendanceDay({ ...day, status: 'scheduled' })).toThrow(AttendanceApiError);
    expect(() => parseAttendanceDay({ ...day, events: null })).toThrow(AttendanceApiError);
  });

  it('retains the authenticated child photo resource on a roster row', () => {
    expect(parseAttendanceRosterRow({
      child_id: 'child',
      child_name: 'Test Child',
      profile_photo_url: '/api/v1/children/child/photo',
      enrollment_id: 'enrollment',
      room_id: 'room',
      room_name: 'Infants',
      program_name: 'Daycare',
      attendance_day: null,
    })).toMatchObject({
      child_id: 'child',
      profile_photo_url: '/api/v1/children/child/photo',
    });
  });

  it('includes the stable client operation id required by check-in and check-out', () => {
    const operationId = '11111111-1111-4111-8111-111111111111';
    expect(buildAttendanceMutationPayload('child', 'facility', operationId)).toEqual({ child_id: 'child', facility_id: 'facility', occurred_at: null, client_operation_id: operationId });
    expect(() => buildAttendanceMutationPayload('child', 'facility', '')).toThrow(AttendanceApiError);
  });

  it('accepts a coherent irreversible release activation status', () => {
    expect(parseAttendanceReleaseCheckoutActivationStatus(releaseActivation)).toMatchObject({
      organization_id: 'org',
      facility_id: 'facility',
      activated: true,
      legacy_checkout_allowed: false,
    });
  });

  it('rejects malformed or contradictory release activation states', () => {
    expect(() => parseAttendanceReleaseCheckoutActivationStatus({ ...releaseActivation, legacy_checkout_allowed: true })).toThrow(AttendanceApiError);
    expect(() => parseAttendanceReleaseCheckoutActivationStatus({ ...releaseActivation, release_ready_children: 1 })).toThrow(AttendanceApiError);
    expect(() => parseAttendanceReleaseCheckoutActivationStatus({
      ...releaseActivation,
      prerequisites: [...releaseActivation.prerequisites, releaseActivation.prerequisites[0]],
    })).toThrow(AttendanceApiError);
    expect(() => parseAttendanceReleaseCheckoutActivationStatus({
      ...releaseActivation,
      prerequisites: releaseActivation.prerequisites.slice(0, -1),
    })).toThrow(AttendanceApiError);
    expect(() => parseAttendanceReleaseCheckoutActivationStatus({ ...releaseActivation, actor_authorized: 'yes' })).toThrow(AttendanceApiError);
  });
});

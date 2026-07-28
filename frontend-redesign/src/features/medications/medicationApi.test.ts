import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchMedicationPlan, parseMedicationAdministration, parseMedicationPlan, parseMedicationRoomDay } from './medicationApi';

const plan = (overrides: Record<string, unknown> = {}) => ({
  id: 'plan-1', organization_id: 'org-1', facility_id: 'facility-1', child_id: 'child-1', child_name: 'Child One', medication_name: 'Label medicine', dosage: '5 mL', route: 'oral', label_directions: 'Use only as directed on the original label.', scheduled_times: ['09:00'], as_needed: false, start_date: '2026-07-01', end_date: null, medication_kind: 'non_emergency', storage_method: 'locked_inaccessible', storage_instructions: 'Locked medication cabinet', emergency_plan_reference: null, status: 'active', authorization_status: 'verified', authorization_is_current: true, signed_authorization_required: true, signed_authorization_reference: 'Consent-7', authorization_guardian_id: 'guardian-1', authorization_guardian_name: 'Parent One', authorization_signed_at: '2026-07-01T15:00:00Z', authorization_valid_until: '2026-08-01', authorization_verified_at: '2026-07-01T16:00:00Z', authorization_verified_by_user_id: 'owner-1', authorization_revoked_at: null, authorization_revocation_reason: null, original_labelled_container_verified_at: '2026-07-01T16:05:00Z', label_directions_verified_at: '2026-07-01T16:05:00Z', created_by_user_id: 'owner-1', created_by_name: 'Owner One', eligible_guardians: [{ id: 'guardian-1', name: 'Parent One', relationship: 'Parent' }], version: 3, archived_at: null, archive_reason: null, last_event_type: 'activated', created_at: '2026-07-01T14:00:00Z', updated_at: '2026-07-01T16:05:00Z',
  ...overrides,
});

const administration = (overrides: Record<string, unknown> = {}) => ({
  id: 'admin-1', organization_id: 'org-1', facility_id: 'facility-1', room_id: 'room-1', child_id: 'child-1', enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', service_date: '2026-07-15', medication_plan_id: 'plan-1', plan_version: 3,
  plan_snapshot: { medication_name: 'Label medicine', dosage: '5 mL', route: 'oral', label_directions: 'Use only as directed.', scheduled_times: ['09:00'], as_needed: false, medication_kind: 'non_emergency', storage_method: 'locked_inaccessible', authorization_status: 'verified', signed_authorization_reference: 'Consent-7', authorization_guardian_name: 'Parent One', authorization_signed_at: '2026-07-01T15:00:00Z', authorization_valid_until: '2026-08-01', plan_version: 3 },
  outcome: 'administered', scheduled_for: '09:00', occurred_at: '2026-07-15T15:00:00Z', amount: '5 mL', reason: null, note: null, staff_name_snapshot: 'Care Educator', staff_initials_snapshot: 'CE', created_by_user_id: 'educator-1', created_by_name: 'Care Educator', version: 1, voided_at: null, voided_by_user_id: null, void_reason: null, last_event_type: 'recorded', was_corrected: false, created_at: '2026-07-15T15:00:00Z', updated_at: '2026-07-15T15:00:00Z',
  ...overrides,
});

describe('strict medication response parsing', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('accepts complete separate consent, physical-label, actor, and snapshot evidence', () => {
    expect(parseMedicationPlan(plan())).toMatchObject({ status: 'active', authorization_status: 'verified', signed_authorization_required: true });
    expect(parseMedicationAdministration(administration())).toMatchObject({ medication_plan_id: 'plan-1', scheduled_for: '09:00', outcome: 'administered' });
  });

  it('allows an active plan to become blocked by expired current evidence without erasing its audit facts', () => {
    expect(parseMedicationPlan(plan({ authorization_is_current: false, authorization_valid_until: '2026-07-14' })).authorization_is_current).toBe(false);
  });

  it('fails closed on extra profile-derived flags or incomplete authorization evidence', () => {
    expect(() => parseMedicationPlan(plan({ profile_medication_checkbox: true }))).toThrow(/invalid medication plan payload/i);
    expect(() => parseMedicationPlan(plan({ authorization_guardian_name: null }))).toThrow(/incomplete signed authorization evidence/i);
  });

  it('rejects a schedule slot or plan version outside the immutable snapshot', () => {
    expect(() => parseMedicationAdministration(administration({ scheduled_for: '10:00' }))).toThrow(/schedule slot/i);
    expect(() => parseMedicationAdministration(administration({ plan_version: 4 }))).toThrow(/immutable plan evidence/i);
  });

  it('rejects cross-boundary child, room, attendance, or plan records in a day response', () => {
    const day = { organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'Care Centre', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infants', service_date: '2026-07-15', generated_at: '2026-07-15T16:00:00Z', children: [{ child_id: 'child-1', child_name: 'Child One', profile_photo_url: '/api/v1/children/child-1/photo', enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', attendance_state: 'on_site', eligible_guardians: [{ id: 'guardian-1', name: 'Parent One', relationship: 'Parent' }], plans: [plan()], administrations: [administration()] }] };
    expect(parseMedicationRoomDay(day).children).toHaveLength(1);
    expect(() => parseMedicationRoomDay({ ...day, children: [{ ...day.children[0], administrations: [administration({ room_id: 'room-2' })] }] })).toThrow(/crossed/i);
  });

  it('re-reads an exact plan and rejects a cross-tenant or substituted target', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify(plan()), { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchMedicationPlan('plan-1', 'org-1')).resolves.toMatchObject({ id: 'plan-1', organization_id: 'org-1' });
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/medications/plans/plan-1');

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(plan({ id: 'plan-2' })), { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(fetchMedicationPlan('plan-1', 'org-1')).rejects.toThrow(/crossed the requested record boundary/i);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(plan({ organization_id: 'org-2' })), { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(fetchMedicationPlan('plan-1', 'org-1')).rejects.toThrow(/crossed the requested record boundary/i);
  });
});

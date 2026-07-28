import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadEnrollmentEditorData } from './enrollmentEditorData';

const ORG_ID = '11111111-1111-4111-8111-111111111111';
const CHILD_ID = '22222222-2222-4222-8222-222222222222';

function okJson(value: unknown) {
  return { ok: true, status: 200, json: async () => value };
}

describe('enrollment editor canonical hydration', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('loads full child detail and facilities rather than trusting the directory preview', async () => {
    const enrollment = {
      id: '44444444-4444-4444-8444-444444444444', organization_id: ORG_ID, child_id: CHILD_ID,
      facility_id: '55555555-5555-4555-8555-555555555555', program_id: null, room_id: null,
      start_date: '2026-07-01', end_date: null, status: 'pending', is_active: false,
      placement_effective_date: null, version: 1, replayed: false,
      facility_name: 'North', program_name: null, program_type: null, room_name: null,
    };
    const profile = {
      id: CHILD_ID, organization_id: ORG_ID, family_id: '33333333-3333-4333-8333-333333333333',
      first_name: 'Amina', middle_name: null, last_name: 'Noor', date_of_birth: '2022-04-12',
      start_date: '2026-07-01', gender: null, age_group: 'Preschool', is_active: true,
      profile_photo_url: null, profile_photo_updated_at: null, enrollments: [enrollment], current_enrollment: enrollment,
      created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-15T00:00:00Z', version: 2, replayed: false,
      health_care_number: null, allergies: null, medical_conditions: null, medications: null,
      immunization_up_to_date: null, doctor_name: null, doctor_phone: null,
      family: {
        id: '33333333-3333-4333-8333-333333333333', organization_id: ORG_ID, name: 'Noor Family',
        file_number: null, status: 'active', additional_notes: null, photo_consent: false,
        field_trip_consent: false, emergency_medical_consent: false, guardians: [], emergency_contacts: [],
        version: 1, replayed: false,
      },
    };
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/facilities')) return Promise.resolve(okJson([{ id: enrollment.facility_id, organization_id: ORG_ID, name: 'North', status: 'active', timezone: 'America/Edmonton' }]));
      if (url.endsWith(`/children/${CHILD_ID}`)) return Promise.resolve(okJson(profile));
      throw new Error(`Unexpected URL: ${url}`);
    });

    const result = await loadEnrollmentEditorData(CHILD_ID, ORG_ID, new AbortController().signal);
    expect(result.profile.enrollments).toHaveLength(1);
    expect(result.profile.current_enrollment?.id).toBe(enrollment.id);
    expect(fetchMock.mock.calls.map(([url]) => new URL(String(url)).pathname)).toEqual(expect.arrayContaining([
      expect.stringMatching(/\/facilities$/),
      expect.stringMatching(new RegExp(`/children/${CHILD_ID}$`)),
    ]));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/children/directory'))).toBe(false);
  });
});

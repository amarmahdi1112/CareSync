import { describe, expect, it } from 'vitest';
import { candidateTransitions, HiringApiError, jobTransitions, parseHiringWorkspace, parseProvisionStaff, payloadForScreeningSchema } from './hiringApi';
const job = { id: 'job-1', organization_id: 'org-1', facility_id: null, title: 'Educator', description: 'Join the team.', employment_type: 'full_time', location: 'North', requirements: [], openings: 3, status: 'open', published_at: null, closed_at: null, version: 2, created_at: '2026-07-15T12:00:00Z', updated_at: '2026-07-15T12:00:00Z' };
const person = { id: 'person-1', organization_id: 'org-1', email: 'ari@example.com', first_name: 'Ari', last_name: 'Lee', phone: '780-555-0101', status: 'active', notes: null, onboarding_status: 'submitted', candidate_type: 'certified_educator', institution: null, program: null, expected_graduation_date: null, certification_type: 'Level 2 ECE', certification_number: 'ECE-123', certification_expiry_date: '2027-08-01', certification_verification_status: 'pending', certification_verified_at: null, certification_review_note: null, certification_provenance: 'local_ocr', certification_candidate_confirmed_at: '2026-07-15T11:00:00Z', work_history: [{ employer: 'Little Pines', position: 'Educator' }], work_history_provenance: 'manual', work_history_candidate_confirmed_at: '2026-07-15T11:05:00Z', created_at: '2026-07-15T12:00:00Z', updated_at: '2026-07-15T12:00:00Z' };
const application = { id: 'app-1', organization_id: 'org-1', job_id: 'job-1', candidate_id: 'person-1', status: 'interview', source: 'marketplace_application', candidate_consent_status: 'accepted', stage_notes: null, hire_handoff_requested_at: null, hire_handoff_requested_by_user_id: null, version: 3, created_at: '2026-07-15T12:00:00Z', updated_at: '2026-07-15T12:00:00Z' };
const offer = { id: 'offer-1', organization_id: 'org-1', application_id: 'app-1', version: 1, status: 'draft', position_title: 'Educator', start_date: '2026-08-01', compensation: '$24.50/hour', terms: 'Subject to references.', expires_at: null, sent_at: null, accepted_at: null, terminal_at: null, created_at: '2026-07-15T12:00:00Z', updated_at: '2026-07-15T12:00:00Z' };
const interview = { id: 'interview-1', organization_id: 'org-1', application_id: 'app-1', scheduled_at: '2026-07-20T18:00:00Z', timezone: 'America/Edmonton', location_or_link: 'Video meeting', status: 'requested', created_at: '2026-07-15T12:00:00Z', updated_at: '2026-07-15T12:00:00Z' };
const structuredTerms = { position_shape: 'educator_only', driving_requirement: 'not_applicable', vehicle_expectation: 'none', required_licence_jurisdiction: null, required_licence_jurisdiction_other: null, required_licence_class: null, minimum_driving_experience_months: 0, service_area: null, service_windows: [], mileage_policy: null, driving_time_paid: false, screening_conditions: [] };
describe('canonical ATS workspace boundary', () => {
  it('joins tenant-scoped people, applications, jobs, interviews, and versioned offers', () => { const result = parseHiringWorkspace({ jobs: [job], candidates: [person], applications: [application], offers: [offer], interviews: [interview] }, 'org-1'); expect(result.candidates[0]).toMatchObject({ id: 'app-1', first_name: 'Ari', phone: '780-555-0101', version: 3, source: 'marketplace_application', candidate_consent_status: 'accepted', candidate_type: 'certified_educator', certification_provenance: 'local_ocr', certification_candidate_confirmed_at: '2026-07-15T11:00:00Z', certification_verification_status: 'pending', work_history_provenance: 'manual' }); expect(result.listings[0]?.openings).toBe(3); expect(result.offers[0].versions[0].compensation).toBe('$24.50/hour'); expect(result.interviews[0]).toMatchObject({ application_id: 'app-1', status: 'requested' }); });
  it('removes candidate phone until application contact consent is accepted', () => { const result = parseHiringWorkspace({ jobs: [job], candidates: [{ ...person, date_of_birth: '2001-02-03', profile_photo_url: '/private/photo' }], applications: [{ ...application, candidate_consent_status: 'requested' }], offers: [], interviews: [] }, 'org-1'); expect(result.candidates[0].phone).toBeNull(); expect(result.candidates[0]).not.toHaveProperty('date_of_birth'); expect(result.candidates[0]).not.toHaveProperty('profile_photo_url'); });
  it('retains student education without manufacturing certification evidence', () => { const student = { ...person, candidate_type: 'student', institution: 'NorQuest College', program: 'Early Learning and Child Care', expected_graduation_date: '2027-06-01', certification_type: null, certification_number: null, certification_provenance: null, certification_candidate_confirmed_at: null }; const result = parseHiringWorkspace({ jobs: [job], candidates: [student], applications: [application], offers: [], interviews: [] }, 'org-1'); expect(result.candidates[0]).toMatchObject({ candidate_type: 'student', institution: 'NorQuest College', program: 'Early Learning and Child Care', certification_type: null }); });
  it('rejects unsupported evidence provenance instead of interpreting it as verification', () => expect(() => parseHiringWorkspace({ jobs: [job], candidates: [{ ...person, certification_provenance: 'verified_by_ocr' }], applications: [application], offers: [], interviews: [] }, 'org-1')).toThrow('certification provenance'));
  it('fails closed on cross-organization records', () => expect(() => parseHiringWorkspace({ jobs: [job], candidates: [{ ...person, organization_id: 'org-2' }], applications: [application], offers: [], interviews: [] }, 'org-1')).toThrow(HiringApiError));
  it('rejects broken references', () => expect(() => parseHiringWorkspace({ jobs: [job], candidates: [person], applications: [], offers: [offer], interviews: [] }, 'org-1')).toThrow('inconsistent'));
  it('exposes only employer-owned legal state-machine transitions', () => { expect(jobTransitions('closed')).toEqual([]); expect(candidateTransitions('invited')).toEqual([]); expect(candidateTransitions('interview')).toEqual(['screening', 'rejected']); expect(candidateTransitions('accepted')).toEqual([]); });
  it('accepts only educator provisioning with zero rooms', () => { const result = parseProvisionStaff({ application: { ...application, status: 'hired' }, membership_id: 'membership-1', membership_created: true, role_key: 'educator', assigned_room_ids: [], provisioning_id: 'provision-1' }, 'org-1'); expect(result).toMatchObject({ membership_created: true, role_key: 'educator', assigned_room_ids: [] }); });
  it('fails closed if provisioning unexpectedly grants a room', () => expect(() => parseProvisionStaff({ application, membership_id: 'membership-1', membership_created: true, role_key: 'educator', assigned_room_ids: ['room-1'], provisioning_id: 'provision-1' }, 'org-1')).toThrow('assigned room'));
  it('keeps 0030 controls off until the workspace advertises the exact schema marker', () => {
    const legacy = parseHiringWorkspace({ jobs: [job], candidates: [person], applications: [application], offers: [], interviews: [] }, 'org-1');
    const current = parseHiringWorkspace({ screening_schema_version: '0030', jobs: [{ ...job, structured_terms: structuredTerms }], candidates: [person], applications: [application], offers: [], interviews: [] }, 'org-1');
    expect(legacy.screening_schema_version).toBeNull();
    expect(current.screening_schema_version).toBe('0030');
  });
  it('fails closed when a 0030 workspace omits structured role fields', () => {
    expect(() => parseHiringWorkspace({ screening_schema_version: '0030', jobs: [job], candidates: [person], applications: [application], offers: [], interviews: [] }, 'org-1')).toThrow('incomplete versioned role terms');
  });
  it('fails closed when a sent 0030 offer omits exact terms evidence', () => {
    const sent = { ...offer, status: 'sent', sent_at: '2026-07-18T12:00:00Z', structured_terms: structuredTerms };
    expect(() => parseHiringWorkspace({ screening_schema_version: '0030', jobs: [{ ...job, structured_terms: structuredTerms }], candidates: [person], applications: [application], offers: [sent], interviews: [] }, 'org-1')).toThrow('exact terms evidence');
  });
  it('removes every screening/driving term from requests in 0028 mode', () => {
    const payload = {
      title: 'Driver',
      description: 'Role',
      employment_type: 'full_time',
      requirements: [],
      position_shape: 'driver_only',
      driving_requirement: 'required',
      vehicle_expectation: 'organization_vehicle',
      required_licence_jurisdiction: 'CA-AB',
      required_licence_jurisdiction_other: null,
      required_licence_class: '5',
      minimum_driving_experience_months: 12,
      service_area: 'Edmonton',
      service_windows: [{ days: ['monday'], start_time: '15:00', end_time: '18:00', timezone: 'America/Edmonton' }],
      mileage_policy: null,
      driving_time_paid: true,
      screening_conditions: ['CRC'],
    };
    const legacy = payloadForScreeningSchema(payload, null);
    expect(legacy).toEqual({ title: 'Driver', description: 'Role', employment_type: 'full_time', requirements: [] });
    expect(payloadForScreeningSchema(payload, '0030')).toEqual(payload);
  });
});

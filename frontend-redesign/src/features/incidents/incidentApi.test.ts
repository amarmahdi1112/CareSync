import { describe, expect, it } from 'vitest';
import { parseIncidentList, parseIncidentRecord, parseIncidentRoomContext } from './incidentApi';

const draft = (overrides: Record<string, unknown> = {}) => ({
  id: 'incident-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'Care Centre', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infants', child_id: 'child-1', child_name: 'Child One', enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', service_date: '2026-07-15', occurred_at: '2026-07-15T16:00:00Z', category: 'injury', severity: 'moderate', summary: 'Factual observed event.', immediate_actions: 'First aid and supervisor contact were recorded.', medical_attention: 'first_aid', parent_notification_status: 'notified', parent_notified_at: '2026-07-15T16:10:00Z', parent_notification_notes: 'Parent reached by phone.', authorities_contacted: [], staff_present: ['Care Educator'], status: 'draft', reportability_assessment: 'unassessed', reporting_timeline: 'not_assessed', reviewer_note: null, finalized_at: null, finalized_by_user_id: null, external_report_status: 'not_assessed', external_reported_at: null, external_confirmation_reference: null, external_submission_channel: null, external_submitted_by_name: null, external_report_recorded_by_user_id: null, external_submission_performed_by_caresync: false, created_by_user_id: 'educator-1', created_by_name: 'Care Educator', version: 1, last_event_type: 'drafted', created_at: '2026-07-15T16:05:00Z', updated_at: '2026-07-15T16:05:00Z',
  ...overrides,
});

describe('strict incident response parsing', () => {
  it('accepts an internal draft without external or premature review evidence', () => {
    expect(parseIncidentRecord(draft())).toMatchObject({ status: 'draft', reportability_assessment: 'unassessed', external_submission_performed_by_caresync: false });
  });

  it('accepts critical finalized state while keeping external action pending and explicit', () => {
    const result = parseIncidentRecord(draft({ status: 'finalized', reportability_assessment: 'critical', reporting_timeline: 'as_soon_as_possible_no_later_than_24_hours', reviewer_note: 'Human reviewer checked current Alberta guidance.', finalized_at: '2026-07-15T17:00:00Z', finalized_by_user_id: 'owner-1', external_report_status: 'pending', last_event_type: 'finalized', version: 3 }));
    expect(result.external_report_status).toBe('pending');
  });

  it('requires complete manual external confirmation and proof CareSync did not submit', () => {
    const recorded = draft({ status: 'finalized', reportability_assessment: 'other_reportable', reporting_timeline: 'within_2_business_days', reviewer_note: 'Human reviewer assessed the event.', finalized_at: '2026-07-15T17:00:00Z', finalized_by_user_id: 'owner-1', external_report_status: 'recorded', external_reported_at: '2026-07-15T18:00:00Z', external_confirmation_reference: 'Portal-77', external_submission_channel: 'alberta_licensing_portal', external_submitted_by_name: 'Director One', external_report_recorded_by_user_id: 'owner-1', last_event_type: 'external_report_recorded', version: 4 });
    expect(parseIncidentRecord(recorded).external_confirmation_reference).toBe('Portal-77');
    expect(() => parseIncidentRecord({ ...recorded, external_submission_performed_by_caresync: true })).toThrow(/performed no external submission/i);
    expect(() => parseIncidentRecord({ ...recorded, external_confirmation_reference: null })).toThrow(/manual external-report evidence/i);
  });

  it('fails closed on inconsistent parent contact and premature finalization facts', () => {
    expect(() => parseIncidentRecord(draft({ parent_notification_status: 'unable_to_reach', parent_notified_at: '2026-07-15T16:10:00Z' }))).toThrow(/parent-notification evidence/i);
    expect(() => parseIncidentRecord(draft({ reportability_assessment: 'critical' }))).toThrow(/premature finalization evidence/i);
  });

  it('strictly parses unique room attendance options and organization-bounded lists', () => {
    const context = { organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'Care Centre', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infants', service_date: '2026-07-15', generated_at: '2026-07-15T16:00:00Z', attendance_options: [{ attendance_day_id: 'day-1', child_id: 'child-1', child_name: 'Child One', attendance_state: 'on_site' }] };
    expect(parseIncidentRoomContext(context).attendance_options).toHaveLength(1);
    expect(() => parseIncidentRoomContext({ ...context, attendance_options: [...context.attendance_options, { ...context.attendance_options[0] }] })).toThrow(/duplicate/i);
    expect(parseIncidentList({ organization_id: 'org-1', generated_at: '2026-07-15T16:00:00Z', incidents: [draft()] }).incidents).toHaveLength(1);
    expect(() => parseIncidentList({ organization_id: 'org-2', generated_at: '2026-07-15T16:00:00Z', incidents: [draft()] })).toThrow(/organization boundary/i);
  });
});

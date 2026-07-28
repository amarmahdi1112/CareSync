import { describe, expect, it } from 'vitest';
import type { IncidentRecord } from './incidentApi';
import {
  canEditIncident,
  canRecordExternalReport,
  externalReportLabel,
  incidentCounts,
  incidentStatusLabel,
  reportGuidance,
} from './incidentModel';

const incident = (overrides: Partial<IncidentRecord> = {}): IncidentRecord => ({
  id: 'incident-1', organization_id: 'org-1', facility_id: 'facility-1', facility_name: 'Care Centre', facility_timezone: 'America/Edmonton', room_id: 'room-1', room_name: 'Infant room', attendance_day_id: 'day-1', child_id: 'child-1', child_name: 'Child One', enrollment_id: 'enrollment-1', service_date: '2026-07-15', occurred_at: '2026-07-15T10:00:00-06:00', category: 'injury', severity: 'moderate', summary: 'Observed event', immediate_actions: 'Immediate care and supervisor notification recorded.', medical_attention: 'first_aid', parent_notification_status: 'notified', parent_notified_at: '2026-07-15T10:10:00-06:00', parent_notification_notes: 'Parent reached by phone.', authorities_contacted: [], staff_present: ['Care Educator'], status: 'draft', reportability_assessment: 'unassessed', reporting_timeline: 'not_assessed', reviewer_note: null, finalized_at: null, finalized_by_user_id: null, external_report_status: 'not_assessed', external_reported_at: null, external_confirmation_reference: null, external_submission_channel: null, external_submitted_by_name: null, external_report_recorded_by_user_id: null, external_submission_performed_by_caresync: false, version: 1, created_by_user_id: 'educator-1', created_by_name: 'Care Educator', last_event_type: 'drafted', created_at: '2026-07-15T10:05:00-06:00', updated_at: '2026-07-15T10:05:00-06:00',
  ...overrides,
});

describe('incident workflow model', () => {
  it('uses internal-state language and never implies ministry submission', () => {
    expect(incidentStatusLabel('under_review')).toBe('Under internal review');
    expect(externalReportLabel('recorded')).toBe('External confirmation manually recorded');
  });

  it('keeps editing and external confirmation behind state gates', () => {
    expect(canEditIncident(incident())).toBe(true);
    expect(canEditIncident(incident({ status: 'under_review', last_event_type: 'submitted_for_review' }))).toBe(false);
    expect(canRecordExternalReport(incident({ status: 'finalized', reportability_assessment: 'critical', reporting_timeline: 'as_soon_as_possible_no_later_than_24_hours', reviewer_note: 'Reviewed against current guidance.', finalized_at: '2026-07-15T11:00:00-06:00', finalized_by_user_id: 'owner-1', external_report_status: 'pending', last_event_type: 'finalized' }))).toBe(true);
    expect(canRecordExternalReport(incident({ status: 'finalized', reportability_assessment: 'not_reportable', reporting_timeline: 'not_reportable', reviewer_note: 'Reviewed against current guidance.', finalized_at: '2026-07-15T11:00:00-06:00', finalized_by_user_id: 'owner-1', external_report_status: 'not_required', last_event_type: 'finalized' }))).toBe(false);
  });

  it('gives urgent but non-diagnostic guidance for critical working selections', () => {
    const guidance = reportGuidance(incident({ severity: 'critical' }));
    expect(guidance.urgent).toBe(true);
    expect(guidance.detail).toContain('Do not delay');
    expect(guidance.detail).toContain('Confirm');
  });

  it('counts workflow states and pending external human action', () => {
    expect(incidentCounts([
      incident(),
      incident({ id: 'incident-2', status: 'under_review', last_event_type: 'submitted_for_review' }),
      incident({ id: 'incident-3', status: 'finalized', reportability_assessment: 'critical', reporting_timeline: 'as_soon_as_possible_no_later_than_24_hours', reviewer_note: 'Reviewed against current guidance.', finalized_at: '2026-07-15T12:00:00-06:00', finalized_by_user_id: 'owner-1', external_report_status: 'pending', last_event_type: 'finalized' }),
    ])).toEqual({ total: 3, draft: 1, under_review: 1, finalized: 1, externalPending: 1 });
  });
});

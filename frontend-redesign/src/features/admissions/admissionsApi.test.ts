import { describe, expect, it } from 'vitest';
import { buildAdmissionIntakeQueuePath, parseAdmissionIntakeQueue } from './admissionsApi';

const organizationId = '11111111-1111-4111-8111-111111111111';
const familyId = '22222222-2222-4222-8222-222222222222';
const childId = '33333333-3333-4333-8333-333333333333';

function response() {
  const action = { label: 'Review family status', path: `/families/${familyId}?focus=family-status` };
  return {
    organization_id: organizationId,
    generated_at: '2026-07-21T18:30:00Z',
    projection_kind: 'derived_current_intake_queue',
    read_only: true,
    waitlist_supported: false,
    compliance_certified: false,
    notice: 'Current record signals only.',
    items: [{
      key: `family:${familyId}`,
      family_id: familyId,
      family_name: 'Asefa Family',
      family_status: 'pending',
      stage: 'family_review',
      severity: 'warning',
      children: [{ id: childId, display_name: 'Adel Asefa', is_active: true }],
      enrollments: [],
      reasons: [{
        code: 'family_pending_manual_review', stage: 'family_review', severity: 'warning',
        title: 'Family status needs review', instruction: 'Review the current family record.',
        entity_type: 'family', entity_id: familyId, action,
      }],
      primary_action: action,
      updated_at: '2026-07-21T18:00:00Z',
    }],
    total: 1,
    limit: 25,
    offset: 0,
    counts: {
      total: 1, critical: 0, warning: 1,
      by_stage: { family_contacts: 0, child_record: 0, enrollment_setup: 0, record_conflict: 0, family_review: 1, placement_review: 0 },
    },
  };
}

describe('admissions intake queue contract', () => {
  it('accepts the bounded read-only projection and exact canonical action', () => {
    const parsed = parseAdmissionIntakeQueue(response(), organizationId, { limit: 25, offset: 0 });
    expect(parsed.items[0].primary_action.path).toBe(`/families/${familyId}?focus=family-status`);
    expect(parsed.items[0].children[0]).toEqual({ id: childId, display_name: 'Adel Asefa', is_active: true });
    expect(parsed.counts.by_stage.family_review).toBe(1);
  });

  it('rejects expanded claims, child DOB exposure, and destinations outside supported workflows', () => {
    const claimed = response();
    claimed.waitlist_supported = true;
    expect(() => parseAdmissionIntakeQueue(claimed, organizationId, { limit: 25 })).toThrow(/projection claims/i);

    const exposed = response();
    Object.assign(exposed.items[0].children[0], { date_of_birth: '2022-01-01' });
    expect(() => parseAdmissionIntakeQueue(exposed, organizationId, { limit: 25 })).toThrow(/child reference fields/i);

    const unsafe = response();
    unsafe.items[0].reasons[0].action = { label: 'Leave CareSync', path: 'https://example.com' };
    unsafe.items[0].primary_action = unsafe.items[0].reasons[0].action;
    expect(() => parseAdmissionIntakeQueue(unsafe, organizationId, { limit: 25 })).toThrow(/unsafe intake action path/i);
  });

  it('fails closed when counts, filters, or the primary action diverge', () => {
    const badCounts = response();
    badCounts.counts.warning = 0;
    expect(() => parseAdmissionIntakeQueue(badCounts, organizationId, { limit: 25 })).toThrow(/counts did not reconcile/i);

    expect(() => parseAdmissionIntakeQueue(response(), organizationId, { stage: 'placement_review', limit: 25 })).toThrow(/stage filter/i);

    const badPrimary = response();
    badPrimary.items[0].primary_action = { label: 'Different label', path: `/families/${familyId}?focus=family-status` };
    expect(() => parseAdmissionIntakeQueue(badPrimary, organizationId, { limit: 25 })).toThrow(/primary action/i);

    const crossCaseReason = response();
    crossCaseReason.items[0].reasons[0].entity_id = '99999999-9999-4999-8999-999999999999';
    expect(() => parseAdmissionIntakeQueue(crossCaseReason, organizationId, { limit: 25 })).toThrow(/outside its family case/i);

    const hiddenCritical = response();
    hiddenCritical.items[0].reasons.push({ ...hiddenCritical.items[0].reasons[0], code: 'family_lifecycle_conflict', severity: 'critical' });
    expect(() => parseAdmissionIntakeQueue(hiddenCritical, organizationId, { limit: 25 })).toThrow(/higher-severity reason/i);
  });

  it('builds only the closed stage/facility pagination query', () => {
    const facilityId = '44444444-4444-4444-8444-444444444444';
    expect(buildAdmissionIntakeQueuePath({ stage: 'record_conflict', facilityId, limit: 25, offset: 50 }))
      .toBe(`/admissions/intake-queue?limit=25&offset=50&stage=record_conflict&facility_id=${facilityId}`);
    expect(() => buildAdmissionIntakeQueuePath({ facilityId: 'not-an-id' })).toThrow(/valid intake facility/i);
    expect(() => buildAdmissionIntakeQueuePath({ limit: 201 })).toThrow(/page size/i);
  });
});

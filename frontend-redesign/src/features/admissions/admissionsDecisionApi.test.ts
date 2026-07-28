import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SELECTED_ORGANIZATION_KEY } from '../../api/client';
import {
  ADMISSION_STATUSES,
  parseAdmissionDetail,
  parseAdmissionConversionCandidates,
  parseAdmissionLaneDirectory,
  parseAdmissionListItem,
  parseAdmissionWaitlistPage,
  parseAdmissionWorkspace,
} from './admissionsDecisionApi';

const organizationId = '11111111-1111-4111-8111-111111111111';
const applicationId = '22222222-2222-4222-8222-222222222222';
const preferenceId = '33333333-3333-4333-8333-333333333333';
const facilityId = '44444444-4444-4444-8444-444444444444';
const programId = '55555555-5555-4555-8555-555555555555';
const eventId = '66666666-6666-4666-8666-666666666666';
const actorId = '77777777-7777-4777-8777-777777777777';
const operationId = '88888888-8888-4888-8888-888888888888';
const waitlistId = '99999999-9999-4999-8999-999999999999';

function listItem(status = 'draft') {
  return {
    id: applicationId,
    reference: 'ADM-2026-0001',
    status,
    version: 1,
    source: 'administrator_entry',
    preference_count: 1,
    submitted_at: null,
    updated_at: '2026-07-23T03:00:00Z',
    current_lane: { facility_id: facilityId, program_id: programId },
    offer_status: null,
  };
}

function detail(): Record<string, any> {
  return {
    id: applicationId,
    organization_id: organizationId,
    reference: 'ADM-2026-0001',
    source: 'administrator_entry',
    status: 'draft',
    version: 1,
    child: { first_name: 'Amina', last_name: 'Noor', date_of_birth: '2023-04-15' },
    contact: { first_name: 'Samira', last_name: 'Noor', relationship: 'Mother', email: 'samira@example.com', telephone: null },
    internal_note: null,
    preferences: [{
      id: preferenceId,
      rank: 1,
      facility_id: facilityId,
      facility_name: 'North Centre',
      program_id: programId,
      program_name: 'Daycare',
      requested_start_date: '2026-09-01',
      application_version: 1,
    }],
    waitlist: null,
    offer: null,
    conversion: null,
    timeline: [{
      id: eventId,
      application_version: 1,
      command: 'create',
      from_status: null,
      to_status: 'draft',
      reason_code: 'create',
      actor_user_id: actorId,
      client_operation_id: operationId,
      occurred_at: '2026-07-23T03:00:00Z',
    }],
    timeline_total: 1,
    allowed_actions: ['update', 'submit', 'withdraw'],
    committed_versions: { application: 1, waitlist: null, offer: null },
    replayed: false,
    replay_receipt: null,
    created_at: '2026-07-23T03:00:00Z',
    updated_at: '2026-07-23T03:00:00Z',
    submitted_at: null,
    review_started_at: null,
    terminal_at: null,
  };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => key === SELECTED_ORGANIZATION_KEY ? organizationId : null,
    setItem: () => undefined,
    removeItem: () => undefined,
  });
});

describe('0039 admissions decision API contract', () => {
  it('parses every canonical pipeline lane without exposing intake PII', () => {
    const counts = Object.fromEntries(ADMISSION_STATUSES.map((status) => [status, status === 'draft' ? 1 : 0]));
    const workspace = parseAdmissionWorkspace({
      counts,
      lanes: ADMISSION_STATUSES.map((status) => ({
        status,
        count: status === 'draft' ? 1 : 0,
        applications: status === 'draft' ? [listItem()] : [],
      })),
      waitlist_lane_count: 0,
    });
    expect(workspace.counts.draft).toBe(1);
    expect(workspace.lanes.find((lane) => lane.status === 'draft')?.applications[0].reference).toBe('ADM-2026-0001');

    const exposed = listItem() as Record<string, unknown>;
    exposed.child_name = 'Amina Noor';
    expect(() => parseAdmissionListItem(exposed)).toThrow(/summary fields/i);
  });

  it('accepts the exact private application profile and reconciles committed versions', () => {
    const parsed = parseAdmissionDetail(detail(), organizationId, applicationId);
    expect(parsed.child).toEqual({ first_name: 'Amina', last_name: 'Noor', date_of_birth: '2023-04-15' });
    expect(parsed.allowed_actions).toEqual(['update', 'submit', 'withdraw']);
    expect(parsed.timeline[0].client_operation_id).toBe(operationId);

    const conflicted = detail();
    conflicted.committed_versions.application = 2;
    expect(() => parseAdmissionDetail(conflicted, organizationId, applicationId)).toThrow(/versions did not reconcile/i);
  });

  it('requires replay evidence to reconcile exactly with the replay marker', () => {
    const replayed = detail();
    replayed.replayed = true;
    replayed.replay_receipt = {
      command_type: 'admission.application.create',
      target_type: 'admission_application',
      target_id: applicationId,
      committed_version: 1,
    };
    expect(parseAdmissionDetail(replayed, organizationId).replay_receipt?.target_id).toBe(applicationId);

    const missing = detail();
    missing.replayed = true;
    expect(() => parseAdmissionDetail(missing, organizationId)).toThrow(/replay marker/i);

    const unexpected = detail();
    unexpected.replay_receipt = replayed.replay_receipt;
    expect(() => parseAdmissionDetail(unexpected, organizationId)).toThrow(/replay marker/i);

    const unknownCommand = detail();
    unknownCommand.replayed = true;
    unknownCommand.replay_receipt = {
      ...replayed.replay_receipt,
      command_type: 'admission.application.erase',
    };
    expect(() => parseAdmissionDetail(unknownCommand, organizationId)).toThrow(/unsupported admission receipt command/i);

    const mismatchedTarget = detail();
    mismatchedTarget.replayed = true;
    mismatchedTarget.replay_receipt = {
      ...replayed.replay_receipt,
      command_type: 'admission.offer.issue',
    };
    expect(() => parseAdmissionDetail(mismatchedTarget, organizationId)).toThrow(/command did not match its target type/i);

    const mismatchedVersion = detail();
    mismatchedVersion.replayed = true;
    mismatchedVersion.replay_receipt = {
      ...replayed.replay_receipt,
      committed_version: 2,
    };
    expect(() => parseAdmissionDetail(mismatchedVersion, organizationId)).toThrow(/owning application history/i);
  });

  it('accepts delayed historical receipts after the application or nested admission target advances', () => {
    const delayedApplication = detail();
    delayedApplication.version = 3;
    delayedApplication.committed_versions.application = 3;
    delayedApplication.replayed = true;
    delayedApplication.replay_receipt = {
      command_type: 'admission.application.submit',
      target_type: 'admission_application',
      target_id: applicationId,
      committed_version: 2,
    };
    expect(parseAdmissionDetail(delayedApplication, organizationId).replay_receipt)
      .toMatchObject({ committed_version: 2 });

    const delayedWaitlist = detail();
    delayedWaitlist.status = 'waitlisted';
    delayedWaitlist.waitlist = {
      id: waitlistId,
      status: 'active',
      version: 5,
      facility_id: facilityId,
      facility_name: 'North Centre',
      program_id: programId,
      program_name: 'Daycare',
      requested_start_date: '2026-09-01',
      priority_at: '2026-07-23T03:10:00Z',
      position: 1,
      closure_reason: null,
      created_at: '2026-07-23T03:10:00Z',
      updated_at: '2026-07-23T03:10:00Z',
      closed_at: null,
    };
    delayedWaitlist.committed_versions.waitlist = 5;
    delayedWaitlist.replayed = true;
    delayedWaitlist.replay_receipt = {
      command_type: 'admission.waitlist.enter',
      target_type: 'admission_waitlist',
      target_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      committed_version: 1,
    };
    expect(parseAdmissionDetail(delayedWaitlist, organizationId).replay_receipt)
      .toMatchObject({
        target_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        committed_version: 1,
      });

    const delayedOffer = detail();
    delayedOffer.status = 'offered';
    delayedOffer.offer = {
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      status: 'open',
      version: 4,
      facility_id: facilityId,
      facility_name: 'North Centre',
      program_id: programId,
      program_name: 'Daycare',
      proposed_start_date: '2026-09-01',
      respond_by_date: '2026-08-25',
      prior_application_status: 'under_review',
      issued_at: '2026-07-23T03:20:00Z',
      withdrawn_at: null,
      declined_at: null,
      accepted_at: null,
    };
    delayedOffer.committed_versions.offer = 4;
    delayedOffer.replayed = true;
    delayedOffer.replay_receipt = {
      command_type: 'admission.offer.issue',
      target_type: 'admission_offer',
      target_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      committed_version: 1,
    };
    expect(parseAdmissionDetail(delayedOffer, organizationId).replay_receipt)
      .toMatchObject({
        target_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        committed_version: 1,
      });
  });

  it('reconciles the bounded timeline total and strict contact telephone projection', () => {
    const timelineMismatch = detail();
    timelineMismatch.timeline_total = 2;
    expect(() => parseAdmissionDetail(timelineMismatch, organizationId)).toThrow(/bounded total/i);

    const invalidTelephone = detail();
    invalidTelephone.contact.telephone = 'CALL-ME';
    expect(() => parseAdmissionDetail(invalidTelephone, organizationId)).toThrow(/telephone/i);

    const tooLongTelephone = detail();
    tooLongTelephone.contact.telephone = `+1 ${'2'.repeat(28)}`;
    expect(() => parseAdmissionDetail(tooLongTelephone, organizationId)).toThrow(/telephone/i);
  });

  it('parses only the privacy-minimal active admissions lane directory', () => {
    const directory = parseAdmissionLaneDirectory({
      facilities: [{
        id: facilityId,
        name: 'North Centre',
        programs: [{ id: programId, name: 'Daycare', program_type: 'daycare' }],
      }],
    });
    expect(directory.facilities[0].programs[0].program_type).toBe('daycare');
    expect(() => parseAdmissionLaneDirectory({
      facilities: [{
        id: facilityId,
        name: 'North Centre',
        programs: [{
          id: programId,
          name: 'Daycare',
          program_type: 'daycare',
          room_roster: ['private'],
        }],
      }],
    })).toThrow(/lane program fields/i);
  });

  it('binds conversion candidates to the current application and offer versions', () => {
    const offered = detail();
    offered.status = 'offered';
    offered.offer = {
      id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      status: 'open',
      version: 3,
      facility_id: facilityId,
      facility_name: 'North Centre',
      program_id: programId,
      program_name: 'Daycare',
      proposed_start_date: '2026-09-01',
      respond_by_date: '2026-08-25',
      prior_application_status: 'under_review',
      issued_at: '2026-07-23T04:00:00Z',
      withdrawn_at: null,
      declined_at: null,
      accepted_at: null,
    };
    offered.committed_versions.offer = 3;
    const review = {
      application_id: applicationId,
      application_version: 1,
      offer_id: offered.offer.id,
      offer_version: 3,
      families: [{
        id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        display_label: 'Family candidate',
        version: 2,
        status: 'active',
        match_reasons: ['primary_contact_email'],
      }],
      children: [],
      review_token: 'signed-token',
      expires_at: '2026-07-23T04:15:00Z',
    };
    expect(parseAdmissionConversionCandidates(review, organizationId, parseAdmissionDetail(offered, organizationId)).families).toHaveLength(1);
    expect(() => parseAdmissionConversionCandidates({
      ...review,
      offer_version: 4,
    }, organizationId, parseAdmissionDetail(offered, organizationId))).toThrow(/did not match/i);
  });

  it('fails closed across organization and application identities', () => {
    expect(() => parseAdmissionDetail(detail(), organizationId, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')).toThrow(/requested application/i);
    const crossTenant = detail();
    crossTenant.organization_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    expect(() => parseAdmissionDetail(crossTenant, organizationId, applicationId)).toThrow(/crossed the selected organization/i);
  });

  it('parses a privacy-minimal deterministic waitlist page', () => {
    const page = parseAdmissionWaitlistPage({
      items: [{
        entry_id: waitlistId,
        application_id: applicationId,
        application_reference: 'ADM-2026-0001',
        status: 'active',
        version: 1,
        facility_id: facilityId,
        program_id: programId,
        desired_start_date: '2026-09-01',
        priority_at: '2026-07-23T03:00:00Z',
        position: 1,
      }],
      total: 1,
      limit: 100,
      offset: 0,
    });
    expect(page.items[0].position).toBe(1);
    expect(page.items[0]).not.toHaveProperty('child_name');

    const exposed = structuredClone({
      items: [{
        entry_id: waitlistId,
        application_id: applicationId,
        application_reference: 'ADM-2026-0001',
        status: 'active',
        version: 1,
        facility_id: facilityId,
        program_id: programId,
        desired_start_date: '2026-09-01',
        priority_at: '2026-07-23T03:00:00Z',
        position: 1,
        contact_email: 'private@example.com',
      }],
      total: 1,
      limit: 100,
      offset: 0,
    });
    expect(() => parseAdmissionWaitlistPage(exposed)).toThrow(/waitlist row fields/i);
  });
});

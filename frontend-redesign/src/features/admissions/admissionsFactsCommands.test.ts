import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SELECTED_ORGANIZATION_KEY,
  SESSION_TOKEN_KEY,
} from '../../api/client';
import {
  correctAdmissionApplication,
  createAdmissionOffer,
  updateAdmissionApplication,
  type AdmissionCreateInput,
  type AdmissionDetail,
} from './admissionsDecisionApi';

const organizationId = '11111111-1111-4111-8111-111111111111';
const applicationId = '22222222-2222-4222-8222-222222222222';
const preferenceId = '33333333-3333-4333-8333-333333333333';
const facilityId = '44444444-4444-4444-8444-444444444444';
const programId = '55555555-5555-4555-8555-555555555555';
const operationId = '66666666-6666-4666-8666-666666666666';

function canonicalDetail(): AdmissionDetail {
  return {
    id: applicationId,
    organization_id: organizationId,
    reference: 'ADM-2026-0001',
    source: 'administrator_entry',
    status: 'draft',
    version: 3,
    child: { first_name: 'Amina', last_name: 'Noor', date_of_birth: '2023-04-15' },
    contact: {
      first_name: 'Samira',
      last_name: 'Noor',
      relationship: 'Mother',
      email: 'samira@example.com',
      telephone: null,
    },
    internal_note: 'Call after 4 PM.',
    preferences: [{
      id: preferenceId,
      rank: 1,
      facility_id: facilityId,
      facility_name: 'North Centre',
      program_id: programId,
      program_name: 'Daycare',
      requested_start_date: '2026-09-01',
      application_version: 3,
    }],
    waitlist: null,
    offer: null,
    conversion: null,
    timeline: [],
    timeline_total: 0,
    allowed_actions: ['update', 'submit'],
    committed_versions: { application: 3, waitlist: null, offer: null },
    replayed: false,
    replay_receipt: null,
    created_at: '2026-07-23T03:00:00Z',
    updated_at: '2026-07-23T03:05:00Z',
    submitted_at: null,
    review_started_at: null,
    terminal_at: null,
  };
}

const input: AdmissionCreateInput = {
  child: { first_name: 'Amina', last_name: 'Noor', date_of_birth: '2023-04-15' },
  primary_contact: {
    first_name: 'Samira',
    last_name: 'Noor',
    relationship: 'Mother',
    email: 'samira@example.com',
    telephone: null,
  },
  preferences: [{
    rank: 1,
    facility_id: facilityId,
    program_id: programId,
    desired_start_date: '2026-09-01',
  }],
  internal_note: 'Call after 4 PM.',
};

beforeEach(() => {
  const storage = new Map<string, string>([
    [SELECTED_ORGANIZATION_KEY, organizationId],
    [SESSION_TOKEN_KEY, 'test-token'],
  ]);
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('0039 admission facts command wire contract', () => {
  it.each([
    ['update', updateAdmissionApplication],
    ['correct', correctAdmissionApplication],
  ] as const)('sends the exact frozen %s request shape', async (suffix, command) => {
    let requestedUrl = '';
    let requestedBody: Record<string, unknown> | null = null;
    vi.stubGlobal('fetch', vi.fn(async (resource: string | URL | Request, init?: RequestInit) => {
      requestedUrl = String(resource);
      requestedBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify(canonicalDetail()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await command(organizationId, canonicalDetail(), operationId, input);

    expect(requestedUrl).toMatch(new RegExp(`/admissions/applications/${applicationId}/${suffix}$`));
    expect(Object.keys(requestedBody!).sort()).toEqual([
      'child',
      'client_operation_id',
      'expected_application_version',
      'internal_note',
      'preferences',
      'primary_contact',
    ]);
    expect(requestedBody).toMatchObject({
      client_operation_id: operationId,
      expected_application_version: 3,
      primary_contact: input.primary_contact,
      preferences: input.preferences,
    });
    expect(requestedBody).not.toHaveProperty('contact');
    expect(requestedBody).not.toHaveProperty('expected_waitlist_version');
    expect(JSON.stringify(requestedBody)).not.toContain('requested_start_date');
  });

  it('binds a waitlisted offer to the current waitlist version', async () => {
    let requestedBody: Record<string, unknown> | null = null;
    vi.stubGlobal('fetch', vi.fn(async (_resource: string | URL | Request, init?: RequestInit) => {
      requestedBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify(canonicalDetail()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await createAdmissionOffer(organizationId, {
      ...canonicalDetail(),
      status: 'waitlisted',
      waitlist: {
        id: '77777777-7777-4777-8777-777777777777',
        status: 'active',
        version: 8,
        facility_id: facilityId,
        facility_name: 'North Centre',
        program_id: programId,
        program_name: 'Daycare',
        requested_start_date: '2026-09-01',
        priority_at: '2026-07-23T03:04:00Z',
        position: 1,
        closure_reason: null,
        created_at: '2026-07-23T03:04:00Z',
        updated_at: '2026-07-23T03:04:00Z',
        closed_at: null,
      },
    }, operationId, {
      facility_id: facilityId,
      program_id: programId,
      proposed_start_date: '2026-09-01',
      respond_by_date: null,
    });

    expect(requestedBody).toHaveProperty('expected_waitlist_version', 8);
    expect(Object.keys(requestedBody!).sort()).toEqual([
      'client_operation_id',
      'expected_application_version',
      'expected_waitlist_version',
      'facility_id',
      'program_id',
      'proposed_start_date',
      'respond_by_date',
    ]);
  });

  it('omits a waitlist version when issuing directly from review', async () => {
    let requestedBody: Record<string, unknown> | null = null;
    vi.stubGlobal('fetch', vi.fn(async (_resource: string | URL | Request, init?: RequestInit) => {
      requestedBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify(canonicalDetail()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await createAdmissionOffer(organizationId, {
      ...canonicalDetail(),
      status: 'under_review',
    }, operationId, {
      facility_id: facilityId,
      program_id: programId,
      proposed_start_date: '2026-09-01',
      respond_by_date: '2026-08-25',
    });

    expect(requestedBody).not.toHaveProperty('expected_waitlist_version');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { latestScreeningDecision, parseEmployerScreeningProjection, screeningApi, ScreeningApiError } from './screeningApi';

const payload = {
  screening_schema_version: '0030',
  application_id: 'application-1',
  candidate_id: 'candidate-1',
  snapshot: {
    pathway: 'educator_driver',
    screening_profile_version: 4,
    job_terms_version: 6,
    driver_declaration: {
      willing_to_drive: true,
      licence_jurisdiction: 'CA-AB',
      licence_jurisdiction_other: null,
      licence_class: '5',
      vehicle_access: 'personal_vehicle',
      preferred_service_radius_km: 20,
      candidate_provided: true,
    },
    job_terms: {
      position_shape: 'educator_driver',
      driving_requirement: 'required',
      vehicle_expectation: 'personal_vehicle',
      required_licence_jurisdiction: 'CA-AB',
      required_licence_jurisdiction_other: null,
      required_licence_class: '5',
      minimum_driving_experience_months: 12,
      service_area: 'Edmonton',
      service_windows: [],
      mileage_policy: 'Approved mileage reimbursed',
      driving_time_paid: true,
      screening_conditions: ['Employer review before start'],
    },
    candidate_acknowledged_at: '2026-07-18T09:45:00Z',
  },
  shares: [
    {
      id: 'share-1',
      shared_at: '2026-07-18T10:00:00Z',
      screening_profile_version: 4,
      shared_version: {
        id: 'version-2',
        version_number: 2,
        declared_coverage: ['criminal_record_check', 'vulnerable_sector_search'],
        subject_name: 'Amina Noor',
        account_name_snapshot: 'Amina Noor',
        subject_name_match: true,
        mismatch_resolution: 'matched',
        issue_date: '2026-06-01',
        expiry_date: null,
        candidate_confirmed_at: '2026-07-18T09:30:00Z',
        content_url: '/api/v1/ats/applications/application-1/screening-shares/share-1/content',
        storage_path: '/private/not-for-clients',
        raw_ocr_text: 'not-for-clients',
      },
      reviews: [
        {
          id: 'review-1',
          requirement_class: 'criminal_record_check',
          decision: 'accepted',
          reason_code: 'current_and_applicable',
          note: null,
          reviewed_at: '2026-07-18T11:00:00Z',
          reviewer_user_id: 'reviewer-1',
          review_sequence: 1,
        },
      ],
    },
  ],
};

describe('confidential employer screening projection', () => {
  it('preserves one-file multi-requirement coverage and strips unprojected source fields', () => {
    const result = parseEmployerScreeningProjection(payload, 'application-1');
    expect(result.snapshot?.pathway).toBe('educator_driver');
    expect(result.snapshot?.driver_declaration.candidate_provided).toBe(true);
    expect(result.snapshot?.job_terms_version).toBe(6);
    expect(result.shares[0]?.shared_version.declared_coverage).toEqual([
      'criminal_record_check',
      'vulnerable_sector_search',
    ]);
    expect(result.shares[0]?.shared_version).not.toHaveProperty('storage_path');
    expect(result.shares[0]?.shared_version).not.toHaveProperty('raw_ocr_text');
  });

  it('strictly preserves employer-authorized identity reconciliation evidence', () => {
    const result = parseEmployerScreeningProjection({
      ...payload,
      shares: [{
        ...payload.shares[0],
        shared_version: {
          ...payload.shares[0].shared_version,
          subject_name: 'Amina Noor-Smith',
          account_name_snapshot: 'Amina Noor',
          subject_name_match: false,
          mismatch_resolution: 'candidate_attests_same_person',
        },
      }],
    }, 'application-1');

    expect(result.shares[0]?.shared_version).toMatchObject({
      subject_name: 'Amina Noor-Smith',
      account_name_snapshot: 'Amina Noor',
      subject_name_match: false,
      mismatch_resolution: 'candidate_attests_same_person',
    });
  });

  it.each([
    ['missing account snapshot', { account_name_snapshot: undefined }],
    ['non-boolean match result', { subject_name_match: 'false' }],
    ['unsupported reconciliation', { mismatch_resolution: 'reviewer_approved' }],
    ['contradictory matched result', { subject_name_match: true, mismatch_resolution: 'candidate_attests_same_person' }],
    ['contradictory mismatch result', { subject_name_match: false, mismatch_resolution: 'matched' }],
  ])('fails closed on %s', (_label, identityFields) => {
    expect(() => parseEmployerScreeningProjection({
      ...payload,
      shares: [{
        ...payload.shares[0],
        shared_version: {
          ...payload.shares[0].shared_version,
          ...identityFields,
        },
      }],
    }, 'application-1')).toThrow(ScreeningApiError);
  });

  it('fails closed when the selected application and response differ', () => {
    expect(() => parseEmployerScreeningProjection(payload, 'application-2')).toThrow(
      ScreeningApiError,
    );
  });

  it('never accepts a candidate declaration as driver readiness', () => {
    expect(() =>
      parseEmployerScreeningProjection(
        {
          ...payload,
          snapshot: {
            ...payload.snapshot,
            driver_declaration: {
              ...payload.snapshot.driver_declaration,
              candidate_provided: false,
              driver_ready: true,
            },
          },
        },
        'application-1',
      ),
    ).toThrow('candidate driver declaration');
  });

  it('derives the latest requirement decision by sequence rather than response order', () => {
    const projection = parseEmployerScreeningProjection({
      ...payload,
      shares: [{
        ...payload.shares[0],
        reviews: [
          { ...payload.shares[0].reviews[0], id: 'review-2', decision: 'rejected', review_sequence: 2 },
          payload.shares[0].reviews[0],
        ],
      }],
    }, 'application-1');
    expect(latestScreeningDecision(projection.shares[0]!, 'criminal_record_check')?.decision).toBe('rejected');
  });

  it('fetches exact share content with auth/no-store and posts reviews by share id', async () => {
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => key.includes('token') ? 'token' : 'org-1',
    });
    const projection = parseEmployerScreeningProjection(payload, 'application-1');
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      if (String(input).endsWith('/content'))
        return new Response(new Blob(['image'], { type: 'image/jpeg' }), {
          status: 200,
          headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'private, no-store' },
        });
      return new Response(JSON.stringify({ id: 'review-3' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      });
    }));
    const viewed = await screeningApi.viewExactSource('application-1', projection.shares[0]!);
    expect(viewed.document_version_id).toBe('version-2');
    expect(new Headers(calls[0]?.init?.headers).get('Authorization')).toBe('Bearer token');
    await screeningApi.review('application-1', 'share-1', {
      requirement_class: 'criminal_record_check',
      decision: 'accepted',
      reason_code: 'current_and_applicable',
    });
    expect(calls[1]?.url).toContain('/screening-shares/share-1/reviews');
  });
});

afterEach(() => vi.unstubAllGlobals());

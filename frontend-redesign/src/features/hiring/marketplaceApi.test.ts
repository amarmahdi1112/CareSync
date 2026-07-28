import { afterEach, describe, expect, it, vi } from 'vitest';
import { marketplaceApi, MarketplaceApiError, parseDiscoverableCandidate } from './marketplaceApi';
describe('consent-safe employer marketplace summaries', () => {
  const certified = { user_id: 'user-1', city: 'Edmonton', headline: 'Level 2 educator', candidate_type: 'certified_educator', institution: null, program: null, expected_graduation_date: null, onboarding_completed_at: '2026-07-15T19:00:00Z', certification_type: 'Level 2 ECE', certification_verification_status: 'pending', certification_provenance: 'local_ocr', certification_candidate_confirmed_at: '2026-07-15T18:00:00Z', discoverable: true, experience_count: 3, updated_at: '2026-07-15T20:00:00Z' };
  it('keeps OCR provenance and employer verification as separate certified-educator states', () => expect(parseDiscoverableCandidate(certified)).toMatchObject({ candidate_type: 'certified_educator', certification_provenance: 'local_ocr', certification_candidate_confirmed_at: '2026-07-15T18:00:00Z', certification_verification_status: 'pending' }));
  it('parses student education without treating the student as a certified educator', () => expect(parseDiscoverableCandidate({ ...certified, candidate_type: 'student', institution: 'NorQuest College', program: 'Early Learning and Child Care', expected_graduation_date: '2027-06-01', certification_type: null, certification_verification_status: 'unverified', certification_provenance: null, certification_candidate_confirmed_at: null })).toMatchObject({ candidate_type: 'student', institution: 'NorQuest College', program: 'Early Learning and Child Care', certification_type: null }));
  it('fails closed when a non-discoverable profile leaks into search', () => expect(() => parseDiscoverableCandidate({ ...certified, discoverable: false })).toThrow(MarketplaceApiError));
  it('rejects an unsupported candidate type', () => expect(() => parseDiscoverableCandidate({ ...certified, candidate_type: 'unverified_educator' })).toThrow('candidate type'));
  it('discards private phone, date of birth, and unapproved photo fields from discovery', () => { const result = parseDiscoverableCandidate({ ...certified, phone: '780-555-0199', date_of_birth: '2001-02-03', profile_photo_url: '/private/photo' }); expect(result).not.toHaveProperty('phone'); expect(result).not.toHaveProperty('date_of_birth'); expect(result).not.toHaveProperty('profile_photo_url'); });
  it('fails closed when discovery returns a candidate without completed onboarding', () => expect(() => parseDiscoverableCandidate({ ...certified, onboarding_completed_at: null })).toThrow('onboarding completion time'));
  it('binds employer interest to a discoverable profile and open job without private contact data', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'token', setItem: () => undefined, removeItem: () => undefined });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ id: 'interest-1', profile_user_id: 'user-1', job_id: 'job-1', status: 'requested', message: 'Please consider this role.', created_at: '2026-07-15T20:00:00Z' }), { status: 200, headers: { 'Content-Type': 'application/json' } })); vi.stubGlobal('fetch', fetchMock);
    await marketplaceApi.expressInterest('user-1', 'job-1', 'Please consider this role.'); const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/ats/marketplace/interests'); expect(JSON.parse(String(init?.body))).toEqual({ profile_user_id: 'user-1', job_id: 'job-1', message: 'Please consider this role.' });
  });
});

afterEach(() => vi.unstubAllGlobals());

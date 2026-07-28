import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseOnboardingResponse } from './onboardingApi';

const organization = { id: 'org-a', name: 'Care', legal_name: null, status: 'active', email: null, phone: null, timezone: 'America/Edmonton', preferences: {} };
const facility = { id: 'facility', organization_id: 'org-a', name: 'Main', license_number: null, status: 'active', email: null, phone: null, street_address: null, city: null, province: 'AB', postal_code: null, timezone: 'America/Edmonton', licensed_capacity: 80, opening_time: null, closing_time: null };
const response = { organization_id: 'org-a', status: 'in_progress', current_step: 'facility', completed_steps: ['organization'], draft: {}, completed_at: null, organization, facilities: [facility] };

describe('onboarding runtime boundary', () => {
  it('parses a selected-tenant workspace and rejects nested cross-tenant records', () => { vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : null }); expect(parseOnboardingResponse(response).organization_id).toBe('org-a'); expect(() => parseOnboardingResponse({ ...response, facilities: [{ ...facility, organization_id: 'org-b' }] })).toThrow('selected organization boundary'); });
});
afterEach(() => vi.unstubAllGlobals());

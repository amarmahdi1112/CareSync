import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, addOrganizationHeader, apiRequest, isSessionBoundaryStorageKey, parseApiUser, parseFamilyStats, parseLoginResponse, parseOrganizationRecord } from './client';

afterEach(() => vi.unstubAllGlobals());

const verifiedAt = '2026-07-14T22:30:00Z';
const verifiedUser = {
  id: 'user',
  email: 'owner@example.com',
  first_name: 'Care',
  last_name: 'Owner',
  organization_id: 'org',
  role: { id: 'role', key: 'owner', name: 'Owner', permissions: ['settings:manage'] },
  membership_id: 'membership',
  membership_status: 'active',
  assigned_facility_ids: [],
  assigned_room_ids: [],
  is_active: true,
  email_verification_status: 'verified',
  email_verified_at: verifiedAt,
  email_verification_method: 'temporary_auto_approval',
};

describe('family statistics adapter', () => {
  it('accepts the complete Basic statistics contract', () => {
    expect(parseFamilyStats({ families: 4, active_families: 3, children: 6, active_children: 5, pending_families: 1, by_age_group: { Infant: 2 } })).toMatchObject({ families: 4, active_children: 5 });
  });

  it('rejects missing and negative counts', () => {
    expect(() => parseFamilyStats({ families: 4 })).toThrow(ApiError);
    expect(() => parseFamilyStats({ families: -1, active_families: 0, children: 0, active_children: 0, pending_families: 0, by_age_group: {} })).toThrow(ApiError);
  });
});

describe('session verification adapters', () => {
  it('parses verification state for authenticated identity and organization', () => {
    expect(parseApiUser(verifiedUser).email_verification_status).toBe('verified');
    expect(parseOrganizationRecord({
      id: 'org',
      name: 'Care Centre',
      status: 'draft',
      timezone: 'America/Edmonton',
      verification_status: 'verified',
      verified_at: verifiedAt,
      verification_method: 'temporary_auto_approval',
    })).toMatchObject({ verification_method: 'temporary_auto_approval', timezone: 'America/Edmonton' });
    expect(parseLoginResponse({ access_token: 'token', token_type: 'bearer', user: verifiedUser }).user.email_verified_at).toBe(verifiedAt);
  });

  it('fails closed when a verification field is absent or inconsistent', () => {
    expect(() => parseApiUser({ ...verifiedUser, email_verified_at: null })).toThrow(ApiError);
    expect(() => parseOrganizationRecord({ id: 'org', name: 'Care Centre', status: 'active' })).toThrow(ApiError);
  });
});

describe('selected organization isolation', () => {
  it('treats token and selected-organization changes as cross-tab session boundaries', () => {
    expect(isSessionBoundaryStorageKey('caresync-redesign-token')).toBe(true);
    expect(isSessionBoundaryStorageKey('caresync-redesign-organization')).toBe(true);
    expect(isSessionBoundaryStorageKey('unrelated-preference')).toBe(false);
  });
  it('adds the selected organization to protected requests and rejects a cross-org expectation', () => {
    vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : null });
    const headers = addOrganizationHeader(new Headers(), 'org-a');
    expect(headers.get('X-Organization-ID')).toBe('org-a');
    expect(() => addOrganizationHeader(new Headers(), 'org-b')).toThrow('do not match the selected organization');
  });

  it('does not invent an organization header when no selection exists', () => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    expect(addOrganizationHeader(new Headers()).has('X-Organization-ID')).toBe(false);
  });
});

describe('authorization-loss signals', () => {
  it('requests context revalidation for protected 403 and still purges on a profile-save 401', async () => {
    const events: string[] = []; vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : 'token' }); vi.stubGlobal('window', { dispatchEvent: (event: Event) => { events.push(event.type); } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'denied' }), { status: 403, headers: { 'Content-Type': 'application/json' } })));
    await expect(apiRequest('/families')).rejects.toMatchObject({ status: 403 }); expect(events).toContain('caresync-redesign:authorization-recheck'); expect(events).not.toContain('caresync-redesign:unauthorized');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'expired' }), { status: 401, headers: { 'Content-Type': 'application/json' } })));
    await expect(apiRequest('/auth/me', { method: 'PATCH', body: '{}' })).rejects.toMatchObject({ status: 401 }); expect(events).toContain('caresync-redesign:unauthorized');
  });

  it('allows an optional fail-closed probe to suppress only its global 403 recheck', async () => {
    const events: string[] = [];
    vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : 'token' });
    vi.stubGlobal('window', { dispatchEvent: (event: Event) => { events.push(event.type); } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'unavailable' }), { status: 403, headers: { 'Content-Type': 'application/json' } })));

    await expect(apiRequest('/optional-capability', { suppressAuthorizationRecheck: true })).rejects.toMatchObject({ status: 403 });

    expect(events).not.toContain('caresync-redesign:authorization-recheck');
    await expect(apiRequest('/families')).rejects.toMatchObject({ status: 403 });
    expect(events).toEqual(['caresync-redesign:authorization-recheck']);
  });
});

describe('structured API errors', () => {
  it('presents a structured server message without stringifying the detail object', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: { code: 'offer_expired', message: 'This offer has expired.' } }), { status: 409, headers: { 'Content-Type': 'application/json' } })));
    await expect(apiRequest('/staff-exchange/open-shifts')).rejects.toMatchObject({ status: 409, message: 'This offer has expired.' });
  });
});

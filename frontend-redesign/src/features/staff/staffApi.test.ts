import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseStaffWorkspace, staffApi } from './staffApi';

const jsonResponse = (payload: unknown) => new Response(JSON.stringify(payload), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
});

describe('one-time staff credential previews', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts activation secrets in the request body instead of the URL', async () => {
    const secret = 'activation-secret-that-must-not-enter-the-url';
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({
      organization_name: 'Care Centre',
      email: 'educator@example.com',
      first_name: 'Ada',
      last_name: 'Care',
      role_name: 'Educator',
      expires_at: '2026-07-16T00:00:00Z',
      assigned_room_names: ['Infants'],
    }));
    vi.stubGlobal('fetch', fetchMock);

    await staffApi.activationPreview(secret);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain(secret);
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ token: secret }));
  });

  it('posts reset secrets in the request body instead of the URL', async () => {
    const secret = 'password-reset-secret-that-must-not-enter-the-url';
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({
      organization_name: 'Care Centre',
      email: 'educator@example.com',
      expires_at: '2026-07-16T00:00:00Z',
    }));
    vi.stubGlobal('fetch', fetchMock);

    await staffApi.resetPreview(secret);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain(secret);
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ token: secret }));
  });
});

describe('staff workspace facility timezone boundary', () => {
  it('requires a valid timezone for every staff facility selector', () => {
    const workspace = { organization_id: 'org-1', roles: [], facilities: [{ id: 'facility-1', organization_id: 'org-1', name: 'North', status: 'active', timezone: 'America/Edmonton' }], rooms: [], members: [], invitations: [] };
    expect(parseStaffWorkspace(workspace, 'org-1').facilities[0].timezone).toBe('America/Edmonton');
    expect(() => parseStaffWorkspace({ ...workspace, facilities: [{ ...workspace.facilities[0], timezone: 'Mars/Olympus' }] }, 'org-1')).toThrow('facility timezone');
  });
});

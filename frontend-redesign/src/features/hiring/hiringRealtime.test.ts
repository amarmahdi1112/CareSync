import { describe, expect, it, vi } from 'vitest';
import { fetchHiringRealtimeSnapshot } from './hiringRealtime';

describe('hiring realtime canonical snapshot', () => {
  it('reloads the consent-based discovery projection while Discover Talent is mounted', async () => {
    const searchCandidates = vi.fn(async () => [{ user_id: 'candidate-1' }] as never);
    const result = await fetchHiringRealtimeSnapshot('org-1', 'Edmonton', {
      workspace: vi.fn(async () => ({ organization_id: 'org-1' }) as never),
      credentialNotifications: vi.fn(async () => []),
      searchCandidates,
    });

    expect(searchCandidates).toHaveBeenCalledWith('Edmonton');
    expect(result.discoverable).toEqual([{ user_id: 'candidate-1' }]);
  });

  it('does not query public candidate discovery when another ATS view is mounted', async () => {
    const searchCandidates = vi.fn(async () => []);
    const result = await fetchHiringRealtimeSnapshot('org-1', null, {
      workspace: vi.fn(async () => ({ organization_id: 'org-1' }) as never),
      credentialNotifications: vi.fn(async () => []),
      searchCandidates,
    });

    expect(searchCandidates).not.toHaveBeenCalled();
    expect(result.discoverable).toBeNull();
  });

  it('rejects the checkpoint rather than acknowledging a stale discovery result', async () => {
    await expect(fetchHiringRealtimeSnapshot('org-1', '', {
      workspace: vi.fn(async () => ({ organization_id: 'org-1' }) as never),
      credentialNotifications: vi.fn(async () => []),
      searchCandidates: vi.fn(async () => { throw new Error('discovery failed'); }),
    })).rejects.toThrow('discovery failed');
  });
});

import { describe, expect, it, vi } from 'vitest';
import type { HiringEvent } from '../features/hiring/hiringEvents';
import { createCoalescedRefresh, matchesRealtimeEvent, RealtimeInvalidationRegistry } from './realtimeRegistry';
import { featureIntegrationManifest } from './featureIntegrationManifest';

const event = (patch: Partial<HiringEvent> = {}): HiringEvent => ({
  id: 'event-1', cursor: 1, type: 'check_in', entity_type: 'attendance_day', entity_id: 'day-1', occurred_at: '2026-07-16T18:00:00Z', payload: {}, ...patch,
});

describe('central realtime invalidation registry', () => {
  it('matches both event prefixes and canonical entity types, while reset refreshes everything', () => {
    expect(matchesRealtimeEvent(event(), { entityTypes: ['attendance_day'] })).toBe(true);
    expect(matchesRealtimeEvent(event({ type: 'offer.sent', entity_type: 'offer' }), { eventPrefixes: ['offer.'] })).toBe(true);
    expect(matchesRealtimeEvent(event(), { entityTypes: ['family'] })).toBe(false);
    expect(matchesRealtimeEvent(event({ type: 'reset_required' }), { entityTypes: ['family'] })).toBe(true);
  });

  it('never crosses organizations and waits for canonical refreshes before resolving', async () => {
    const registry = new RealtimeInvalidationRegistry();
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const refresh = vi.fn(() => pending);
    const other = vi.fn(async () => undefined);
    registry.register({ id: 'attendance', organizationId: 'org-a', entityTypes: ['attendance_day'], refresh });
    registry.register({ id: 'other-org', organizationId: 'org-b', all: true, refresh: other });
    let completed = false;
    const applying = registry.invalidate('org-a', event()).then(() => { completed = true; });
    await Promise.resolve();
    expect(refresh).toHaveBeenCalledOnce();
    expect(other).not.toHaveBeenCalled();
    expect(completed).toBe(false);
    release();
    await applying;
    expect(completed).toBe(true);
  });

  it('rejects when a canonical refresh fails so the socket cursor cannot advance', async () => {
    const registry = new RealtimeInvalidationRegistry();
    registry.register({ id: 'screen', organizationId: 'org-a', all: true, refresh: async () => { throw new Error('REST refresh failed'); } });
    await expect(registry.invalidate('org-a', event())).rejects.toThrow('REST refresh failed');
  });

  it('refreshes the child profile summary for a canonical authority-head event', async () => {
    const registry = new RealtimeInvalidationRegistry();
    const refresh = vi.fn(async () => undefined);
    registry.register({
      id: 'child-authority-summary',
      organizationId: 'org-a',
      entityTypes: featureIntegrationManifest.children.realtimeEntities,
      refresh,
    });
    await registry.invalidate('org-a', event({
      type: 'family_authority.release_context_invalidated',
      entity_type: 'child_authority_head',
      entity_id: null,
    }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('coalesces simultaneous focus, visibility, and online recovery signals', async () => {
    let release!: () => void; let calls = 0;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const recover = createCoalescedRefresh(async () => { calls += 1; await pending; });
    const first = recover(); const second = recover();
    expect(first).toBe(second); expect(calls).toBe(1); release(); await first;
    await recover(); expect(calls).toBe(2);
  });
});

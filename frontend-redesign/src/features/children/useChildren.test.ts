import { describe, expect, it } from 'vitest';
import {
  beginChildrenRequest,
  createChildrenRequestGate,
  invalidateChildrenRequests,
  isCurrentChildrenRequest,
  refreshChildrenRequest,
} from './useChildren';

describe('children directory request sequencing', () => {
  it('rejects a stale search response after a newer filter request starts', () => {
    const gate = createChildrenRequestGate();
    const oldSearch = beginChildrenRequest(gate, 'org\u0000amina\u0000all');
    const newestFilter = beginChildrenRequest(gate, 'org\u0000amina\u0000active');
    expect(isCurrentChildrenRequest(gate, oldSearch)).toBe(false);
    expect(isCurrentChildrenRequest(gate, newestFilter)).toBe(true);
  });

  it('invalidates every in-flight response when the tenant/session boundary closes', () => {
    const gate = createChildrenRequestGate();
    const pending = beginChildrenRequest(gate, 'org-a\u0000page-2');
    invalidateChildrenRequests(gate);
    expect(isCurrentChildrenRequest(gate, pending)).toBe(false);
    expect(gate.requestKey).toBeNull();
  });

  it('lets realtime canonical refresh supersede an older initial load', async () => {
    const gate = createChildrenRequestGate();
    const initial = beginChildrenRequest(gate, 'org-a\u0000children');
    const refreshed = await refreshChildrenRequest(
      gate,
      'org-a\u0000children',
      async () => ({ items: [], total: 0, limit: 50, offset: 0 }) as never,
    );

    expect(refreshed).toMatchObject({ total: 0 });
    expect(isCurrentChildrenRequest(gate, initial)).toBe(false);
  });

  it('does not apply a realtime response after the active filter changes', async () => {
    const gate = createChildrenRequestGate();
    let release!: (page: never) => void;
    const pending = new Promise<never>((resolve) => { release = resolve; });
    const refresh = refreshChildrenRequest(gate, 'org-a\u0000all', () => pending);
    beginChildrenRequest(gate, 'org-a\u0000active');
    release({ items: [], total: 0, limit: 50, offset: 0 } as never);

    await expect(refresh).resolves.toBeNull();
  });
});

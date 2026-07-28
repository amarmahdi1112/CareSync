import { describe, expect, it, vi } from 'vitest';
import { createCheckpointedEventQueue } from './checkpointedEventQueue';

interface TestEvent { cursor: number; type: string }

describe('checkpointed realtime event queue', () => {
  it('collapses a synchronous burst and checkpoints its highest cursor after refresh', async () => {
    const applied: TestEvent[] = [];
    const committed: number[] = [];
    const queue = createCheckpointedEventQueue<TestEvent>({
      apply: async (event) => { applied.push(event); },
      collapse: (_events, cursor) => ({ cursor, type: 'reset_required' }),
      commit: (cursor) => committed.push(cursor),
    });

    queue.enqueue({ cursor: 4, type: 'job.updated' });
    queue.enqueue({ cursor: 5, type: 'offer.sent' });
    queue.enqueue({ cursor: 6, type: 'notification.created' });
    await queue.whenIdle();

    expect(applied).toEqual([{ cursor: 6, type: 'reset_required' }]);
    expect(committed).toEqual([6]);
  });

  it('runs one follow-up refresh for events that arrive during an in-flight refresh', async () => {
    let release!: () => void;
    const firstRefresh = new Promise<void>((resolve) => { release = resolve; });
    const applied: TestEvent[] = [];
    const committed: number[] = [];
    const queue = createCheckpointedEventQueue<TestEvent>({
      apply: vi.fn(async (event) => {
        applied.push(event);
        if (applied.length === 1) await firstRefresh;
      }),
      collapse: (_events, cursor) => ({ cursor, type: 'reset_required' }),
      commit: (cursor) => committed.push(cursor),
    });

    queue.enqueue({ cursor: 10, type: 'job.updated' });
    await Promise.resolve();
    queue.enqueue({ cursor: 11, type: 'offer.sent' });
    queue.enqueue({ cursor: 12, type: 'interview.scheduled' });
    expect(committed).toEqual([]);

    release();
    await queue.whenIdle();

    expect(applied).toEqual([
      { cursor: 10, type: 'job.updated' },
      { cursor: 12, type: 'reset_required' },
    ]);
    expect(committed).toEqual([10, 12]);
  });

  it('does not checkpoint a failed canonical refresh', async () => {
    const committed: number[] = [];
    const onError = vi.fn();
    const queue = createCheckpointedEventQueue<TestEvent>({
      apply: async () => { throw new Error('snapshot failed'); },
      collapse: (_events, cursor) => ({ cursor, type: 'reset_required' }),
      commit: (cursor) => committed.push(cursor),
      onError,
    });

    queue.enqueue({ cursor: 21, type: 'job.updated' });
    await queue.whenIdle();

    expect(committed).toEqual([]);
    expect(onError).toHaveBeenCalledOnce();
  });
});

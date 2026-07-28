export interface CursorEvent {
  cursor: number;
}

export interface CheckpointedEventQueue<T extends CursorEvent> {
  enqueue: (event: T) => void;
  whenIdle: () => Promise<void>;
}

interface CheckpointedEventQueueOptions<T extends CursorEvent> {
  apply: (event: T) => Promise<void>;
  collapse: (events: readonly T[], checkpoint: number) => T;
  commit: (checkpoint: number) => void;
  onError?: (error: unknown) => void;
}

/**
 * Coalesces event bursts into canonical refreshes while preserving the central
 * realtime invariant: a cursor is checkpointed only after its refresh succeeds.
 */
export function createCheckpointedEventQueue<T extends CursorEvent>(
  options: CheckpointedEventQueueOptions<T>,
): CheckpointedEventQueue<T> {
  let pending: T[] = [];
  let active: Promise<void> | null = null;

  const drain = async () => {
    while (pending.length > 0) {
      const batch = pending;
      pending = [];
      const checkpoint = Math.max(...batch.map((event) => event.cursor));
      const event = batch.length === 1 ? batch[0] : options.collapse(batch, checkpoint);

      try {
        await options.apply(event);
        options.commit(checkpoint);
      } catch (error) {
        // A failed canonical refresh invalidates the whole accumulated batch.
        // The socket reconnect will replay it from the last durable checkpoint.
        pending = [];
        options.onError?.(error);
        return;
      }
    }
  };

  const ensureDrain = () => {
    if (active) return;
    active = Promise.resolve()
      .then(drain)
      .finally(() => {
        active = null;
        if (pending.length > 0) ensureDrain();
      });
  };

  return {
    enqueue: (event) => {
      pending.push(event);
      ensureDrain();
    },
    whenIdle: async () => {
      while (active) await active;
    },
  };
}

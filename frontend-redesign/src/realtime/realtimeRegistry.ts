import type { HiringEvent } from '../features/hiring/hiringEvents';

export interface RealtimeSelector {
  all?: boolean;
  eventPrefixes?: readonly string[];
  entityTypes?: readonly string[];
}

export interface RealtimeRegistration extends RealtimeSelector {
  id: string;
  organizationId: string;
  refresh: (event: HiringEvent) => Promise<void>;
}

export function matchesRealtimeEvent(event: HiringEvent, selector: RealtimeSelector): boolean {
  if (event.type === 'reset_required' || selector.all) return true;
  return Boolean(
    selector.eventPrefixes?.some((prefix) => event.type.startsWith(prefix))
    || selector.entityTypes?.includes(event.entity_type),
  );
}

/**
 * Mounted screens register their canonical REST reload here. The socket cursor
 * is allowed to advance only after every matching reload has completed.
 */
export class RealtimeInvalidationRegistry {
  private readonly registrations = new Map<string, RealtimeRegistration>();

  register(registration: RealtimeRegistration): () => void {
    this.registrations.set(registration.id, registration);
    return () => {
      if (this.registrations.get(registration.id) === registration) {
        this.registrations.delete(registration.id);
      }
    };
  }

  async invalidate(organizationId: string, event: HiringEvent): Promise<number> {
    const matching = [...this.registrations.values()].filter((registration) => (
      registration.organizationId === organizationId
      && matchesRealtimeEvent(event, registration)
    ));
    await Promise.all(matching.map((registration) => registration.refresh(event)));
    return matching.length;
  }

  clear(): void {
    this.registrations.clear();
  }
}

export function createCoalescedRefresh(refresh: () => Promise<void>): () => Promise<void> {
  let pending: Promise<void> | null = null;
  return () => {
    if (!pending) pending = refresh().finally(() => { pending = null; });
    return pending;
  };
}

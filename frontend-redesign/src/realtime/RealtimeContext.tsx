import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useSession } from '../auth/SessionContext';
import {
  subscribeHiringEvents,
  type HiringEvent,
  type HiringStreamState,
} from '../features/hiring/hiringEvents';
import {
  RealtimeInvalidationRegistry,
  createCoalescedRefresh,
  type RealtimeRegistration,
  type RealtimeSelector,
} from './realtimeRegistry';
import { featureIntegrationManifest } from './featureIntegrationManifest';

interface RealtimeContextValue {
  organizationId: string;
  state: HiringStreamState;
  register: (registration: RealtimeRegistration) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const organizationId = session.status === 'authenticated'
    && session.user?.organization_id
    && session.user.organization_id === session.organization?.id
    && !session.organizationUnavailable
    ? session.user.organization_id
    : '';
  const registry = useMemo(() => new RealtimeInvalidationRegistry(), [organizationId]);
  const [state, setState] = useState<HiringStreamState>('manual');

  useEffect(() => {
    if (!organizationId) return;
    return registry.register({
      id: 'session-shell',
      organizationId,
      entityTypes: featureIntegrationManifest['session-shell'].realtimeEntities,
      refresh: async () => session.refreshOrganizationFacts(),
    });
  }, [organizationId, registry, session.refreshOrganizationFacts]);

  useEffect(() => {
    if (!organizationId) {
      setState('manual');
      return;
    }
    const subscription = subscribeHiringEvents({
      organizationId,
      cursorScope: 'portal',
      onState: setState,
      onInvalidate: async (event) => {
        await registry.invalidate(organizationId, event);
      },
    });
    const recoverCanonical = createCoalescedRefresh(async () => {
      if (document.visibilityState === 'hidden') return;
      await registry.invalidate(organizationId, {
        id: 'portal-recovery', cursor: 0, type: 'reset_required', entity_type: 'workspace', entity_id: organizationId, occurred_at: new Date().toISOString(), payload: { reason: 'browser_resumed' },
      });
    });
    const recover = () => { void recoverCanonical().catch(() => undefined); };
    const visible = () => { if (document.visibilityState !== 'hidden') recover(); };
    window.addEventListener('focus', recover);
    window.addEventListener('online', recover);
    document.addEventListener('visibilitychange', visible);
    return () => {
      subscription.close();
      window.removeEventListener('focus', recover);
      window.removeEventListener('online', recover);
      document.removeEventListener('visibilitychange', visible);
      registry.clear();
    };
  }, [organizationId, registry]);

  const register = useCallback((registration: RealtimeRegistration) => registry.register(registration), [registry]);
  const value = useMemo(() => ({ organizationId, state, register }), [organizationId, register, state]);
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtimeState(): HiringStreamState {
  return useContext(RealtimeContext)?.state || 'manual';
}

export interface UseRealtimeRefreshOptions extends RealtimeSelector {
  scope: string;
  organizationId: string;
  enabled?: boolean;
  refresh: (event: HiringEvent) => Promise<void>;
}

export function useRealtimeRefresh(options: UseRealtimeRefreshOptions): void {
  const context = useContext(RealtimeContext);
  const reactId = useId();
  const latest = useRef(options);
  latest.current = options;
  const register = context?.register;
  const providerOrganizationId = context?.organizationId || '';

  useEffect(() => {
    if (!register || options.enabled === false || !options.organizationId || providerOrganizationId !== options.organizationId) return;
    const registration: RealtimeRegistration = {
      id: `${options.scope}:${reactId}`,
      organizationId: options.organizationId,
      get all() { return latest.current.all; },
      get eventPrefixes() { return latest.current.eventPrefixes; },
      get entityTypes() { return latest.current.entityTypes; },
      refresh: (event) => latest.current.refresh(event),
    };
    return register(registration);
  }, [options.enabled, options.organizationId, options.scope, providerOrganizationId, reactId, register]);
}

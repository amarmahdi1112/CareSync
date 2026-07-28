import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, apiRequest } from '../../api/client';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';

/**
 * The manager gate is deliberately separate from the 0031 staff-self marker.
 * A deployed 0031 registry therefore cannot make the admin route, navigation,
 * search results, or command controls appear.
 */
export const TRANSPORT_REGISTRY_CAPABILITY_ENDPOINT = '/staff/transport-registry/capability';
export const TRANSPORT_REGISTRY_WORKSPACE_PATH = '/api/v1/staff/transport-registry' as const;

export interface TransportRegistryCapability {
  schema_version: '0032';
  runtime_available: true;
  manager_available: true;
  workspace_path: typeof TRANSPORT_REGISTRY_WORKSPACE_PATH;
  evidence_upload_available: boolean;
  operational_driver_ready: false;
  dispatch_authorized: false;
}

export class TransportRegistryCapabilityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TransportRegistryCapabilityError';
  }
}

const capabilityKeys = [
  'schema_version',
  'runtime_available',
  'manager_available',
  'workspace_path',
  'evidence_upload_available',
  'operational_driver_ready',
  'dispatch_authorized',
] as const;

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === expected.length
    && expected.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

export function parseTransportRegistryCapability(value: unknown): TransportRegistryCapability {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TransportRegistryCapabilityError('The server returned an invalid transport-registry capability.');
  }
  const row = value as Record<string, unknown>;
  if (!hasExactKeys(row, capabilityKeys)
    || row.schema_version !== '0032'
    || row.runtime_available !== true
    || row.manager_available !== true
    || row.workspace_path !== TRANSPORT_REGISTRY_WORKSPACE_PATH
    || typeof row.evidence_upload_available !== 'boolean'
    || row.operational_driver_ready !== false
    || row.dispatch_authorized !== false) {
    throw new TransportRegistryCapabilityError('The manager transport-registry capability is unavailable or unsupported.');
  }
  return row as unknown as TransportRegistryCapability;
}

export const transportRegistryCapabilityApi = {
  get: async (signal?: AbortSignal): Promise<TransportRegistryCapability> =>
    parseTransportRegistryCapability(await apiRequest<unknown>(TRANSPORT_REGISTRY_CAPABILITY_ENDPOINT, {
      signal,
      suppressAuthorizationRecheck: true,
    })),
};

export type TransportRegistryCapabilityPhase = 'idle' | 'checking' | 'enabled' | 'disabled';

interface TransportRegistryCapabilityState {
  phase: TransportRegistryCapabilityPhase;
  capability: TransportRegistryCapability | null;
  enabled: boolean;
}

const disabledState: TransportRegistryCapabilityState = { phase: 'disabled', capability: null, enabled: false };
const TransportRegistryCapabilityContext = createContext<TransportRegistryCapabilityState | null>(null);

export function TransportRegistryCapabilityProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const organizationId = session.user?.organization_id || null;
  const canManage = hasPermission(session.user, ACCESS.transportManage);
  const [state, setState] = useState<TransportRegistryCapabilityState>(
    session.status === 'authenticated' && canManage ? { phase: 'checking', capability: null, enabled: false } : disabledState,
  );

  useEffect(() => {
    if (session.status !== 'authenticated' || !organizationId || !canManage) {
      setState(disabledState);
      return;
    }
    const controller = new AbortController();
    setState({ phase: 'checking', capability: null, enabled: false });
    void transportRegistryCapabilityApi.get(controller.signal)
      .then((capability) => {
        if (controller.signal.aborted) return;
        setState({ phase: 'enabled', capability, enabled: true });
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        // Missing, forbidden, malformed, unavailable, or unsupported data all fail closed.
        if (caught instanceof ApiError || caught instanceof TransportRegistryCapabilityError) setState(disabledState);
        else setState(disabledState);
      });
    return () => controller.abort();
  }, [canManage, organizationId, session.status]);

  const value = useMemo(() => state, [state]);
  return <TransportRegistryCapabilityContext.Provider value={value}>{children}</TransportRegistryCapabilityContext.Provider>;
}

export function useTransportRegistryCapability(): TransportRegistryCapabilityState {
  const value = useContext(TransportRegistryCapabilityContext);
  if (!value) return disabledState;
  return value;
}

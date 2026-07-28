import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSession } from '../../auth/SessionContext';
import {
  ChildrenApiError,
  fetchChildDirectoryPage,
  type ChildDirectoryPage,
  type ChildDirectoryQuery,
} from './childrenApi';
import { toChildListItem, type ChildListItem } from './childrenModel';
import {
  resolveChildrenOrganizationBoundary,
  type ChildrenOrganizationBoundary,
} from './childrenOrganizationBoundary';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';

export type ChildrenPhase = ChildrenOrganizationBoundary | 'loading' | 'error';

interface ChildrenState {
  phase: ChildrenPhase;
  children: ChildListItem[];
  page: ChildDirectoryPage | null;
  error: ChildrenApiError | null;
  scopeOrganizationId: string | null;
  requestKey: string | null;
}

export interface ChildrenRequestGate {
  sequence: number;
  requestKey: string | null;
}

export interface ChildrenRequestToken {
  sequence: number;
  requestKey: string;
}

export function createChildrenRequestGate(): ChildrenRequestGate {
  return { sequence: 0, requestKey: null };
}

export function beginChildrenRequest(gate: ChildrenRequestGate, requestKey: string): ChildrenRequestToken {
  gate.sequence += 1;
  gate.requestKey = requestKey;
  return { sequence: gate.sequence, requestKey };
}

export function invalidateChildrenRequests(gate: ChildrenRequestGate): void {
  gate.sequence += 1;
  gate.requestKey = null;
}

export function isCurrentChildrenRequest(gate: ChildrenRequestGate, token: ChildrenRequestToken): boolean {
  return gate.sequence === token.sequence && gate.requestKey === token.requestKey;
}

export async function refreshChildrenRequest(
  gate: ChildrenRequestGate,
  requestKey: string,
  load: () => Promise<ChildDirectoryPage>,
): Promise<ChildDirectoryPage | null> {
  const token = beginChildrenRequest(gate, requestKey);
  const page = await load();
  return isCurrentChildrenRequest(gate, token) ? page : null;
}

const EMPTY_STATE: ChildrenState = {
  phase: 'checking-session',
  children: [],
  page: null,
  error: null,
  scopeOrganizationId: null,
  requestKey: null,
};

function keyForRequest(organizationId: string, query: ChildDirectoryQuery, revision: number): string {
  return [
    organizationId,
    query.search,
    query.status,
    query.careLane,
    query.familyId || '',
    String(query.limit),
    String(query.offset),
    String(revision),
  ].join('\u0000');
}

function readyState(
  page: ChildDirectoryPage,
  organizationId: string,
  requestKey: string,
): ChildrenState {
  return {
    phase: 'ready',
    children: page.items.map(toChildListItem),
    page,
    error: null,
    scopeOrganizationId: organizationId,
    requestKey,
  };
}

export function useChildren(query: ChildDirectoryQuery) {
  const session = useSession();
  const organizationId = session.user?.organization_id || null;
  const loadedOrganizationId = session.organization?.id || null;
  const boundary = resolveChildrenOrganizationBoundary({
    sessionStatus: session.status,
    identityOrganizationId: organizationId,
    loadedOrganizationId,
    organizationUnavailable: session.organizationUnavailable,
  });
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ChildrenState>(EMPTY_STATE);
  const gate = useRef(createChildrenRequestGate());
  const requestKey = boundary === 'ready' && organizationId
    ? keyForRequest(organizationId, query, revision)
    : null;

  useRealtimeRefresh({
    scope: 'children',
    organizationId: organizationId || '',
    enabled: boundary === 'ready',
    entityTypes: featureIntegrationManifest.children.realtimeEntities,
    refresh: async () => {
      if (!organizationId || !requestKey) return;
      const refreshKey = requestKey;
      const page = await refreshChildrenRequest(
        gate.current,
        refreshKey,
        () => fetchChildDirectoryPage(organizationId, query),
      );
      if (page) {
        setState(readyState(page, organizationId, refreshKey));
      }
    },
  });

  useEffect(() => {
    if (!requestKey || !organizationId) {
      invalidateChildrenRequests(gate.current);
      setState({ ...EMPTY_STATE, phase: boundary });
      return undefined;
    }

    const controller = new AbortController();
    const token = beginChildrenRequest(gate.current, requestKey);
    setState({
      phase: 'loading',
      children: [],
      page: null,
      error: null,
      scopeOrganizationId: organizationId,
      requestKey,
    });
    fetchChildDirectoryPage(organizationId, query, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted && isCurrentChildrenRequest(gate.current, token)) {
          setState(readyState(page, organizationId, requestKey));
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || !isCurrentChildrenRequest(gate.current, token)) return;
        const error = caught instanceof ChildrenApiError
          ? caught
          : new ChildrenApiError(0, caught instanceof Error ? caught.message : 'Unable to load the children directory.');
        setState({
          phase: 'error',
          children: [],
          page: null,
          error,
          scopeOrganizationId: organizationId,
          requestKey,
        });
      });
    return () => controller.abort();
  }, [boundary, organizationId, query.careLane, query.familyId, query.limit, query.offset, query.search, query.status, requestKey]);

  const retry = useCallback(() => {
    if (
      boundary === 'session-unavailable'
      || boundary === 'organization-loading'
      || boundary === 'organization-unavailable'
      || boundary === 'organization-mismatch'
    ) {
      session.retry();
      return;
    }
    setRevision((value) => value + 1);
  }, [boundary, session.retry]);

  return useMemo(() => {
    const exposedState: ChildrenState = boundary !== 'ready'
      ? { ...EMPTY_STATE, phase: boundary }
      : state.scopeOrganizationId === organizationId && state.requestKey === requestKey
        ? state
        : {
          phase: 'loading', children: [], page: null, error: null,
          scopeOrganizationId: organizationId, requestKey,
        };

    return {
      ...exposedState,
      retry,
      organizationId,
      organizationName: boundary === 'ready' ? session.organization?.name || null : null,
    };
  }, [state, retry, organizationId, boundary, requestKey, session.organization?.name]);
}

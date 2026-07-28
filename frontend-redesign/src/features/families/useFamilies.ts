import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchFamiliesSnapshot } from './familiesApi';
import type { FamiliesSnapshot, FamilyDirectoryQuery } from './types';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';

type FamiliesLoadStatus = 'idle' | 'loading' | 'success' | 'error';

interface FamiliesLoadState {
  status: FamiliesLoadStatus;
  data: FamiliesSnapshot | null;
  error: string | null;
  requestKey: string | null;
}

const IDLE_STATE: FamiliesLoadState = {
  status: 'idle',
  data: null,
  error: null,
  requestKey: null,
};

export function useFamilies(
  organizationId: string | null,
  enabled: boolean,
  query: FamilyDirectoryQuery,
): FamiliesLoadState & { retry: () => void } {
  const [state, setState] = useState<FamiliesLoadState>(IDLE_STATE);
  const [requestVersion, setRequestVersion] = useState(0);
  const sequence = useRef(0);
  const requestKey = enabled && organizationId
    ? [organizationId, query.search, query.status, query.limit, query.offset, requestVersion].join('\u0000')
    : null;
  const latestRequestKey = useRef(requestKey);
  latestRequestKey.current = requestKey;

  const retry = useCallback(() => {
    setRequestVersion((version) => version + 1);
  }, []);

  useRealtimeRefresh({
    scope: 'families',
    organizationId: organizationId || '',
    enabled,
    entityTypes: featureIntegrationManifest.families.realtimeEntities,
    refresh: async () => {
      if (!organizationId || !requestKey) return;
      const refreshKey = requestKey;
      const refreshSequence = ++sequence.current;
      const data = await fetchFamiliesSnapshot(organizationId, query);
      if (refreshSequence === sequence.current && latestRequestKey.current === refreshKey) {
        setState({ status: 'success', data, error: null, requestKey: refreshKey });
      }
    },
  });

  useEffect(() => {
    if (!requestKey || !organizationId) {
      ++sequence.current;
      setState(IDLE_STATE);
      return undefined;
    }

    const controller = new AbortController();
    const loadSequence = ++sequence.current;
    setState({ status: 'loading', data: null, error: null, requestKey });

    fetchFamiliesSnapshot(organizationId, query, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted
          && loadSequence === sequence.current
          && latestRequestKey.current === requestKey) {
          setState({ status: 'success', data, error: null, requestKey });
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted
          || loadSequence !== sequence.current
          || latestRequestKey.current !== requestKey) return;
        setState({
          status: 'error',
          data: null,
          error: caught instanceof Error ? caught.message : 'The family directory could not be loaded.',
          requestKey,
        });
      });

    return () => controller.abort();
  }, [organizationId, query.limit, query.offset, query.search, query.status, requestKey]);

  if (requestKey && state.requestKey !== requestKey) {
    return { status: 'loading', data: null, error: null, requestKey, retry };
  }

  return { ...state, retry };
}

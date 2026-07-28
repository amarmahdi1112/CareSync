import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './client';

type QueryValue = string | number | boolean | null | undefined;

export interface ApiQueryResult<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
  refetch: () => Promise<void>;
}

export function useApiQuery<T>(
  path: string,
  query?: Record<string, QueryValue>,
  enabled = true,
): ApiQueryResult<T> {
  const queryKey = JSON.stringify(query || {});
  const stableQuery = useMemo(
    () => JSON.parse(queryKey) as Record<string, QueryValue>,
    [queryKey],
  );
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error>();

  const refetch = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(undefined);
    try {
      setData(await api.get<T>(path, stableQuery));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('Request failed'));
    } finally {
      setLoading(false);
    }
  }, [enabled, path, stableQuery]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}

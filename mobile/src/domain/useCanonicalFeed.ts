import { useCallback, useEffect, useRef, useState } from 'react';
import { getCanonicalSystemSnapshot } from '../api/canonical';
import type { CanonicalSystemSnapshot, DataFreshness } from './canonical';

export type CanonicalFeedState = {
  snapshot: CanonicalSystemSnapshot | null;
  loading: boolean;
  error: string;
  freshness: DataFreshness;
  lastSuccessMs: number;
};

export function useCanonicalFeed(baseUrl: string, adminKey?: string, refreshMs = 4500): CanonicalFeedState & { refresh: () => Promise<void> } {
  const [state, setState] = useState<CanonicalFeedState>({ snapshot: null, loading: true, error: '', freshness: 'unavailable', lastSuccessMs: 0 });
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!baseUrl) {
      setState((current) => ({ ...current, loading: false, error: 'backend_url_missing', freshness: 'unavailable' }));
      return;
    }
    try {
      const snapshot = await getCanonicalSystemSnapshot(baseUrl, adminKey);
      const now = Date.now();
      setState({ snapshot, loading: false, error: '', freshness: snapshot.freshness, lastSuccessMs: now });
    } catch (error: unknown) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : String(error),
        freshness: current.snapshot ? 'stale' : 'unavailable',
      }));
    }
  }, [adminKey, baseUrl]);

  useEffect(() => {
    void refresh();
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => void refresh(), Math.max(1500, Number(refreshMs) || 4500));
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh, refreshMs]);

  return { ...state, refresh };
}

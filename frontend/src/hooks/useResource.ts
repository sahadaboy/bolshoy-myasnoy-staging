import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { ResourceEntry, resourceCache } from '../lib/resourceCache';

type Options = {
  cacheKey?: string;
  staleTime?: number;
  refreshInterval?: number;
  enabled?: boolean;
};

export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  { cacheKey, staleTime = 60_000, refreshInterval = 0, enabled = true }: Options = {}
) {
  // Sharing is explicit: account-dependent and parameterized loaders need scoped keys.
  const entry = useMemo(
    () => (cacheKey ? resourceCache.get<T>(cacheKey) : new ResourceEntry<T>()),
    [cacheKey, cacheKey ? null : load]
  );
  const initialRevision = useMemo(() => entry.getSnapshot().revision, [entry, enabled]);
  const snapshot = useSyncExternalStore(entry.subscribe, entry.getSnapshot);
  const retry = useCallback(() => {
    if (enabled) void entry.load(load, { force: true }).catch(() => {});
  }, [entry, load, enabled]);
  useEffect(() => {
    if (!enabled) return;
    const update = () => {
      void entry.load(load, { staleTime }).catch(() => {});
    };
    const visible = () => {
      if (!document.hidden) update();
    };
    update();
    if (cacheKey) {
      window.addEventListener('focus', visible);
      window.addEventListener('online', visible);
      document.addEventListener('visibilitychange', visible);
    }
    const timer = refreshInterval ? setInterval(visible, refreshInterval) : undefined;
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', visible);
      window.removeEventListener('online', visible);
      document.removeEventListener('visibilitychange', visible);
      // Shared GETs may finish after unmount to warm the cache for a quick return.
      if (!cacheKey) entry.cancel();
    };
  }, [entry, load, cacheKey, staleTime, refreshInterval, enabled]);
  const hasData = snapshot.data !== undefined;
  return {
    data: snapshot.data ?? null,
    loading: enabled && !hasData && !snapshot.error,
    refreshing: snapshot.refreshing,
    error: hasData ? null : snapshot.error,
    refreshError: hasData ? snapshot.error : null,
    // Cached display data must never overwrite fresher cart metadata on remount.
    revalidated: enabled && hasData && snapshot.revision > initialRevision,
    retry,
    entry,
  };
}

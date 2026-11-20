import { useCallback, useEffect, useRef, useState } from 'react';

/** Retain data only for the same account/page. Hidden tabs make no polling requests. */
export function useOrderResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  scope: string,
  enabled: boolean,
  active?: (data: T) => boolean,
) {
  const [state, setState] = useState<{
    scope: string;
    data: T | null;
    loading: boolean;
    error: string | null;
  }>({ scope, data: null, loading: true, error: null });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const last = useRef(Date.now());
  const polling =
    enabled && (state.scope !== scope || state.data === null || !active || active(state.data));
  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({
      scope,
      data: previous.scope === scope ? previous.data : null,
      loading: true,
      error: null,
    }));
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ scope, data, loading: false, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState((previous) => ({
            ...previous,
            loading: false,
            error: error instanceof Error ? error.message : 'Не удалось обновить заказ.',
          }));
      });
    return () => controller.abort();
  }, [load, scope, attempt]);
  useEffect(() => {
    if (!polling) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const update = () => {
      if (document.visibilityState === 'visible' && Date.now() - last.current > 1000) {
        last.current = Date.now();
        retry();
      }
    };
    const visibility = () => {
      clearInterval(timer);
      if (document.visibilityState === 'visible') {
        update();
        timer = setInterval(update, 12000);
      }
    };
    visibility();
    window.addEventListener('focus', update);
    window.addEventListener('online', update);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', update);
      window.removeEventListener('online', update);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [polling, retry]);
  const data = state.scope === scope ? state.data : null;
  return {
    data,
    loading: !data && (state.scope !== scope || state.loading),
    error: data ? null : state.error,
    refreshError: data ? state.error : null,
    retry,
  };
}

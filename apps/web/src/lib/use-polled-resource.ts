"use client";

import { useCallback, useEffect, useState } from "react";

type State<T> = {
  data: T | null;
  error: string | null;
  checkedAt: string | null;
  loading: boolean;
};

/**
 * Fetch a resource on mount and optionally re-fetch on an interval.
 *
 * The effect only schedules timers — it never calls setState during its own
 * synchronous phase, which is what `react-hooks/set-state-in-effect` guards
 * against. The first load is deferred to the next tick for the same reason.
 */
export function usePolledResource<T>(
  fetcher: () => Promise<T>,
  intervalMs?: number,
): State<T> & { refresh: () => void } {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    checkedAt: null,
    loading: true,
  });

  const load = useCallback(async () => {
    setState((previous) => ({ ...previous, loading: true }));
    try {
      const data = await fetcher();
      setState({
        data,
        error: null,
        checkedAt: new Date().toLocaleTimeString(),
        loading: false,
      });
    } catch (cause) {
      setState({
        data: null,
        error: cause instanceof Error ? cause.message : String(cause),
        checkedAt: new Date().toLocaleTimeString(),
        loading: false,
      });
    }
  }, [fetcher]);

  useEffect(() => {
    const tick = () => {
      void load();
    };

    const firstRun = setTimeout(tick, 0);
    const poll = intervalMs ? setInterval(tick, intervalMs) : undefined;

    return () => {
      clearTimeout(firstRun);
      if (poll) clearInterval(poll);
    };
  }, [load, intervalMs]);

  return { ...state, refresh: () => void load() };
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type State<T> = {
  data: T | null;
  error: string | null;
  checkedAt: string | null;
  loading: boolean;
};

/**
 * Fetch a resource on mount, and optionally re-fetch on an interval.
 *
 * The fetcher is held in a ref rather than used as a dependency, which is the
 * whole point of this hook's shape. Most call sites pass an inline arrow that
 * closes over a workspace id:
 *
 *     usePolledResource(() => getShopifyStatus(workspaceId), undefined, [workspaceId])
 *
 * That arrow is a new function on every render. When it drove the effect
 * directly, every fetch set state, every state change re-rendered, every render
 * produced a new fetcher, and the effect ran again — a loop that fetched about
 * five times a second, forever, on a page nobody was touching. It was invisible
 * in the UI and only showed up as the browser and the API both working hard for
 * no reason.
 *
 * So the effect depends on `deps`, which the caller states explicitly: the
 * values that should actually cause a re-fetch. The fetcher itself is read from
 * a ref at call time, so it is always the current closure without ever being a
 * reason to re-run.
 *
 * The effect only schedules timers; it never calls setState during its own
 * synchronous phase, which is what `react-hooks/set-state-in-effect` guards
 * against. The first load is deferred to the next tick for the same reason.
 */
export function usePolledResource<T>(
  fetcher: () => Promise<T>,
  intervalMs?: number,
  deps: readonly unknown[] = [],
): State<T> & { refresh: () => void } {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    checkedAt: null,
    loading: true,
  });

  // Updated in an effect rather than during render: writing to a ref while
  // rendering is a side effect, and the React Compiler rightly rejects it.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const load = useCallback(async () => {
    setState((previous) => ({ ...previous, loading: true }));
    try {
      const data = await fetcherRef.current();
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
  }, []);

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
    // `load` is stable by construction; `deps` is what the caller says should
    // cause a re-fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, intervalMs, ...deps]);

  return { ...state, refresh: () => void load() };
}

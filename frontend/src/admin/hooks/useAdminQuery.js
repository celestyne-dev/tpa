import { useCallback, useEffect, useRef, useState } from "react";

/** Loads admin data with loading/error state; `reload` re-runs the request. */
export function useAdminQuery(fetcher, deps = []) {
  const [state, setState] = useState({ data: null, meta: null, error: null, loading: true });
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await fetchRef.current();
      if (id === requestId.current)
        setState({ data: res.data, meta: res.meta ?? null, error: null, loading: false });
    } catch (error) {
      if (id === requestId.current) setState((s) => ({ ...s, error, loading: false }));
    }
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === "function" ? updater(s.data) : updater }));
  }, []);

  return { ...state, reload: load, setData };
}

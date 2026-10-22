import { useCallback, useEffect, useState } from "react";
import { useAdminApi } from "../../adminApiContext";
import { BuilderLookupsContext } from "./lookups";

const empty = {
  options: { articles: [], topics: [], authors: [] },
  ctas: [],
  shared: [],
  links: [],
};

/** Loads picker data once per screen; each list degrades to empty if not permitted. */
export function BuilderLookups({ children }) {
  const api = useAdminApi();
  const [data, setData] = useState(empty);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let cancelled = false;
    const settle = (promise, fallback) => promise.then((r) => r.data).catch(() => fallback);
    Promise.all([
      settle(api.builderOptions(), empty.options),
      settle(api.ctas.list(), []),
      settle(api.shared.list(), []),
      settle(api.linkOptions(""), []),
    ]).then(([options, ctas, shared, links]) => {
      if (!cancelled) setData({ options, ctas, shared, links });
    });
    return () => {
      cancelled = true;
    };
  }, [api, version]);
  return (
    <BuilderLookupsContext.Provider value={{ ...data, reload }}>
      {children}
    </BuilderLookupsContext.Provider>
  );
}

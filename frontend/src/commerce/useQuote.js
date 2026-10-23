import { useCallback, useEffect, useState } from "react";
import { useShopApi } from "@/components/products/shopApiContext";

/** Validates the browser cart with the server on every change (prices are never trusted locally). */
export function useQuote(items, currency) {
  const shopApi = useShopApi();
  const [state, setState] = useState({ quote: null, error: null, loading: false });
  const ids = items.map((i) => i.id).join(",");
  const load = useCallback(() => {
    if (!ids) return Promise.resolve();
    setState((s) => ({ ...s, loading: true }));
    return shopApi.quote(ids.split(","), currency).then(
      (res) => setState({ quote: res.data, error: null, loading: false }),
      (error) => setState({ quote: null, error, loading: false }),
    );
  }, [ids, currency, shopApi]);
  useEffect(() => {
    Promise.resolve().then(load);
  }, [load]);
  return { ...state, reload: load, empty: !ids };
}

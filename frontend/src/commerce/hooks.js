import { useCallback, useEffect, useState } from "react";
import { routes } from "@/config/navigation";

/** Load data from the customer API with loading/error state and a reload function. */
export function useLoad(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true, version: 0 });
  const reload = useCallback(() => setState((s) => ({ ...s, version: s.version + 1 })), []);
  useEffect(() => {
    let alive = true;
    Promise.resolve()
      .then(() => setState((s) => ({ ...s, loading: true })))
      .then(loader)
      .then(
        (res) =>
          alive && setState((s) => ({ ...s, data: res?.data ?? res, error: null, loading: false })),
        (error) => alive && setState((s) => ({ ...s, error, loading: false })),
      );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, state.version]);
  return { ...state, reload };
}

export function newKey() {
  const bytes = new Uint8Array(16);
  (globalThis.crypto ?? window.crypto).getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function fieldErrors(error) {
  const details = error?.details;
  if (!details || typeof details !== "object") return {};
  return Object.fromEntries(
    Object.entries(details).map(([k, v]) => [k, Array.isArray(v) ? v.join(" ") : String(v)]),
  );
}

/** Only same-site paths are accepted as "next" destinations (no open redirects). */
export function safeNext(value, fallback = routes.account) {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/admin")
    ? value
    : fallback;
}

/** Sends the shopper to Paystack's hosted page or a download link (overridable in tests). */
export const redirectTo = { go: (url) => window.location.assign(url) };

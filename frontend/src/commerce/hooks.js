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

/**
 * Only same-site paths are accepted as "next" destinations (no open redirects): a single
 * leading slash, no backslashes or control characters (browsers treat "/\\host" like
 * "//host"), and never the admin area, the API or another sign-in page.
 */
export function safeNext(value, fallback = routes.account) {
  if (typeof value !== "string" || value.length > 500) return fallback;
  const unsafeChar = [...value].some((c) => c === "\\" || c.charCodeAt(0) < 33);
  if (!value.startsWith("/") || value.startsWith("//") || unsafeChar) return fallback;
  let decoded;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return fallback;
  }
  if (decoded.startsWith("//") || decoded.includes("\\")) return fallback;
  const path = value.split(/[?#]/)[0];
  const blocked = ["/admin", "/api", routes.signIn, routes.register, routes.forgotPassword];
  if (blocked.some((b) => path === b || path.startsWith(`${b}/`))) return fallback;
  return value;
}

/** Sends the shopper to Paystack's hosted page or a download link (overridable in tests). */
export const redirectTo = { go: (url) => window.location.assign(url) };

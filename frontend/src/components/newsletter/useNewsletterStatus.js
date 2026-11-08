import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import { useShopApi } from "@/components/products/shopApiContext";
import { useSite } from "@/hooks/useContent";

/**
 * Whether The Positive Reset sign-up is open, as the backend's readiness check says.
 *
 * Pages are prerendered with the site payload (site.newsletter.is_open), so the first
 * paint matches the HTML. After loading, every newsletter placement on the page shares one
 * request to GET /newsletter/status and follows the live answer: a form appears only when
 * the backend reports sign-ups open (setting on, sending enabled, mail backend, sender and
 * consent wording configured), and disappears if the backend says sign-ups have closed.
 * Nothing here can open sign-ups; it only reads the readiness check.
 */

const MAX_AGE_MS = 60_000;
const stores = new WeakMap();

function storeFor(api) {
  let store = stores.get(api);
  if (!store) {
    store = { value: null, at: 0, pending: null, listeners: new Set() };
    stores.set(api, store);
  }
  return store;
}

function publish(store, value) {
  store.value = value;
  store.at = Date.now();
  store.listeners.forEach((listener) => listener());
}

function load(api, store, force = false) {
  if (typeof api?.newsletterStatus !== "function") return Promise.resolve();
  if (store.pending) return store.pending;
  if (!force && store.value && Date.now() - store.at < MAX_AGE_MS) return Promise.resolve();
  store.pending = Promise.resolve()
    .then(() => api.newsletterStatus())
    .then((res) => {
      if (res?.data) publish(store, res.data);
    })
    .catch(() => {}) // keep the prerendered state; never open on an error
    .finally(() => {
      store.pending = null;
    });
  return store.pending;
}

export function useNewsletterStatus() {
  const api = useShopApi();
  const { data: site } = useSite();
  const store = storeFor(api);
  const subscribe = useCallback(
    (listener) => {
      store.listeners.add(listener);
      return () => store.listeners.delete(listener);
    },
    [store],
  );
  const live = useSyncExternalStore(
    subscribe,
    () => store.value,
    () => null,
  );

  useEffect(() => {
    load(api, store);
  }, [api, store]);

  const base = site?.newsletter ?? null;
  const status = useMemo(() => {
    if (!live) return base;
    return {
      ...base,
      name: live.name ?? base?.name,
      tagline: live.tagline ?? base?.tagline,
      is_open: live.signup_open === true,
      consent_text: live.consent_text ?? "",
      consent_version: live.consent_version ?? "",
      signup_mode: live.signup_mode ?? base?.signup_mode,
      confirmation_email: live.confirmation_email ?? base?.confirmation_email,
    };
  }, [base, live]);

  /** Fetch the live status again (after "consent changed" or "sign-ups closed"). */
  const refresh = useCallback(() => load(api, store, true), [api, store]);

  return { status, isOpen: status?.is_open === true, refresh };
}

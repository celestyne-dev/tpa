import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { siteConfig } from "@/config/site";

/**
 * First-party, cookieless page-view beacon (Batch 11.1). Nothing is stored in the
 * browser. Skipped for automated browsers, Do Not Track / Global Privacy Control and
 * private routes (the server applies the same rules and more).
 */
const PRIVATE = [
  "/admin",
  "/account",
  "/checkout",
  "/cart",
  "/purchases",
  "/learn",
  "/certificates",
  "/login",
  "/register",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/newsletter/confirm",
  "/newsletter/preferences",
  "/newsletter/unsubscribe",
  "/resources/access",
];

/** Transport (replaceable in tests). Uses sendBeacon only: no fallback request. */
export const beacon = {
  send(url, body) {
    if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") {
      return false;
    }
    return navigator.sendBeacon(url, new Blob([body], { type: "text/plain" }));
  },
};

export function shouldTrack(pathname) {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  if (navigator.webdriver) return false;
  if (navigator.doNotTrack === "1" || window.doNotTrack === "1") return false;
  if (navigator.globalPrivacyControl === true) return false;
  return !PRIVATE.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function trackPageView({ pathname, search, spa }) {
  if (!shouldTrack(pathname)) return false;
  const body = JSON.stringify({
    path: pathname,
    // Only UTM parameters are kept by the server; everything else is discarded.
    search: spa ? "" : search,
    referrer: spa ? "" : document.referrer,
    spa,
  });
  return beacon.send(`${siteConfig.apiBaseUrl}/analytics/collect`, body);
}

/** Sends one page view per route (first load and each client-side navigation). */
export function usePageViewTracking() {
  const { pathname, search } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    trackPageView({ pathname, search, spa: !first.current });
    first.current = false;
    // Query-only changes (filters, pagination) are not new page views.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);
}

import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { siteConfig } from "@/config/site";
import { useSite } from "@/hooks/useContent";
import { statisticsDecision, usePrivacyChoice } from "@/privacy/choices";

/**
 * First-party, cookieless page-view beacon (Batch 11.1). Nothing is stored in the
 * browser. Skipped for automated browsers, Do Not Track / Global Privacy Control,
 * private routes (the server applies the same rules and more) and when the visitor's
 * Cookie settings say no (Batch 13, see privacy/choices.js).
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

export function trackPageView({ pathname, search, spa, consent = false }) {
  if (!shouldTrack(pathname)) return false;
  const body = JSON.stringify({
    path: pathname,
    // Only UTM parameters are kept by the server; everything else is discarded.
    search: spa ? "" : search,
    referrer: spa ? "" : document.referrer,
    spa,
    // The visitor accepted usage statistics in Cookie settings (required in consent mode).
    ...(consent ? { consent: true } : {}),
  });
  return beacon.send(`${siteConfig.apiBaseUrl}/analytics/collect`, body);
}

/**
 * Sends one page view per route (first load and each client-side navigation), only once
 * the site's privacy settings are known and the visitor's Cookie settings allow it. A
 * visitor who accepts on a page has that page counted; one who switches statistics off is
 * not counted from then on.
 */
export function usePageViewTracking() {
  const { pathname, search } = useLocation();
  const privacy = useSite().data?.privacy;
  const choice = usePrivacyChoice();
  const { allowed, consent } = statisticsDecision(privacy, choice);
  const sentFor = useRef(null);
  const landing = useRef(pathname);
  const navigated = useRef(false);
  useEffect(() => {
    // The landing page keeps its referrer and campaign labels even if it is counted only
    // after the visitor accepts; later pages are client-side navigations.
    if (pathname !== landing.current) navigated.current = true;
    if (!privacy) return;
    if (allowed && sentFor.current !== pathname) {
      trackPageView({ pathname, search, spa: navigated.current, consent });
      sentFor.current = pathname;
    }
    // Query-only changes (filters, pagination) are not new page views.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, Boolean(privacy), allowed]);
}

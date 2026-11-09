import { useSyncExternalStore } from "react";

/**
 * The visitor's Cookie settings, kept in this browser (localStorage, key below; listed in
 * the Cookie Policy). Only one category is optional today: "statistics", the site's own
 * cookieless page-view counting. Necessary cookies and storage are always on.
 *
 * How the stored choice applies depends on the mode the server sends in
 * site.privacy.statistics_mode (application configuration, not CMS wording):
 * - "objection": statistics count unless the visitor switched them off (any version);
 * - "consent": statistics count only after the visitor accepted the current version.
 */
export const STORAGE_KEY = "tpa:privacy-choices";
const EVENT = "tpa:privacy-choices-changed";
const OPEN_EVENT = "tpa:privacy-settings-open";

let cachedRaw;
let cachedValue = null;
// Used only when the browser refuses storage (some private modes): lasts for this visit.
let memoryChoice = null;

function readRaw() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** The stored choice ({ version, statistics, decided_at }) or null. */
export function readChoice() {
  if (typeof window === "undefined") return null;
  const raw = readRaw();
  if (raw === null && memoryChoice) return memoryChoice;
  if (raw === cachedRaw) return cachedValue;
  cachedRaw = raw;
  try {
    const value = JSON.parse(raw ?? "null");
    cachedValue =
      value && typeof value === "object" && typeof value.statistics === "boolean" ? value : null;
  } catch {
    cachedValue = null;
  }
  return cachedValue;
}

/** Remembers a choice (and tells every open part of the page). */
export function saveChoice({ version, statistics }) {
  const value = { version: String(version ?? ""), statistics: Boolean(statistics) };
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...value, decided_at: new Date().toISOString() }),
    );
  } catch {
    // Storage blocked (private mode): the choice lasts for this visit only.
    memoryChoice = value;
  }
  window.dispatchEvent(new Event(EVENT));
  return value;
}

function subscribe(callback) {
  const onStorage = (event) => {
    if (event.key === STORAGE_KEY) callback();
  };
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", onStorage);
  };
}

/** The stored choice, updated live (also across tabs). Null on the server. */
export function usePrivacyChoice() {
  return useSyncExternalStore(subscribe, readChoice, () => null);
}

/** Whether the site has an optional category the visitor can choose about. */
export function hasOptionalCategories(privacy) {
  return Boolean(privacy?.categories?.some((c) => !c.required));
}

/**
 * Whether usage statistics may be sent, and whether the visitor explicitly accepted them.
 * Without the site's privacy settings nothing is sent.
 */
export function statisticsDecision(privacy, choice) {
  const offered = Boolean(privacy?.categories?.some((c) => c.key === "statistics"));
  if (!offered) return { allowed: false, consent: false };
  const accepted = choice?.statistics === true && choice.version === privacy.version;
  if (privacy.statistics_mode === "objection") {
    return { allowed: choice?.statistics !== false, consent: accepted };
  }
  return { allowed: accepted, consent: accepted };
}

/**
 * In consent mode, a visitor who has not chosen is asked. An earlier acceptance counts only
 * for the current version (a new version asks again); an earlier refusal is always
 * respected and never asked about again (nothing optional runs either way).
 */
export function needsDecision(privacy, choice) {
  if (privacy?.statistics_mode === "objection" || !hasOptionalCategories(privacy)) return false;
  if (!choice) return true;
  return choice.statistics === true && choice.version !== privacy.version;
}

/** Opens the Cookie settings panel (from the footer link, the notice or a page). */
export function openPrivacySettings() {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function onOpenPrivacySettings(callback) {
  window.addEventListener(OPEN_EVENT, callback);
  return () => window.removeEventListener(OPEN_EVENT, callback);
}

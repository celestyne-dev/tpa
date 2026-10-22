import { useSyncExternalStore } from "react";

let current = null;

function subscribe(onChange) {
  current = Date.now();
  const timer = setInterval(() => {
    current = Date.now();
    onChange();
  }, 60_000);
  return () => clearInterval(timer);
}

function getSnapshot() {
  if (current === null) current = Date.now();
  return current;
}

/**
 * The current time (refreshed every minute) once the page has hydrated; null on the
 * server and during hydration, so time-dependent markup always matches the
 * prerendered HTML first and updates right after.
 */
export function useNow() {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

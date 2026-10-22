import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Debounced, conflict-aware autosave.
 *
 * - Waits `delay` ms after the last change, never sends on every keystroke.
 * - Only one request is in flight; changes made meanwhile are saved right after.
 * - Responses never overwrite the form (the author may have kept typing); they
 *   only advance the saved baseline and the lock version (via `onSaved`).
 * - A 409 edit_conflict stops autosaving until the author decides what to do.
 * - Network failures retry with backoff (and when the browser comes back online).
 *
 * `save(payload, lockVersion)` must resolve to the API response `{ data }`.
 */
export function useAutosave({ enabled, dirty, payload, lockVersion, save, onSaved, delay = 2500 }) {
  const [status, setStatus] = useState("idle"); // idle|saving|saved|error|conflict|offline
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [conflict, setConflict] = useState(null);
  const state = useRef({ inFlight: false, again: false, attempt: 0, timer: null });
  const latest = useRef({ payload, lockVersion, save, onSaved });
  const runRef = useRef(null);

  useLayoutEffect(() => {
    latest.current = { payload, lockVersion, save, onSaved };
  });

  useLayoutEffect(() => {
    runRef.current = async () => {
      const s = state.current;
      if (s.inFlight) {
        s.again = true;
        return;
      }
      s.inFlight = true;
      const { payload: body, lockVersion: version, save: send } = latest.current;
      const sent = JSON.parse(JSON.stringify(body));
      setStatus("saving");
      try {
        const res = await send(body, version);
        s.attempt = 0;
        setLastSavedAt(new Date());
        setStatus("saved");
        latest.current.onSaved?.(res, sent);
      } catch (err) {
        if (err.status === 409 && err.code === "edit_conflict") {
          setConflict(err.details ?? {});
          setStatus("conflict");
        } else if (!err.status || err.status >= 500) {
          // Offline or server hiccup: retry with backoff (2s, 4s, 8s ... max 60s).
          s.attempt += 1;
          setStatus(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "error");
          clearTimeout(s.timer);
          s.timer = setTimeout(() => runRef.current(), Math.min(60000, 1000 * 2 ** s.attempt));
        } else {
          setStatus("error"); // validation errors: shown by the editor, no retry
        }
      } finally {
        s.inFlight = false;
        if (s.again) {
          s.again = false;
          runRef.current();
        }
      }
    };
  }, []);

  const serialized = JSON.stringify(payload);
  useEffect(() => {
    const s = state.current;
    if (!enabled || !dirty || status === "conflict") return undefined;
    clearTimeout(s.timer);
    s.timer = setTimeout(() => runRef.current(), delay);
    return () => clearTimeout(s.timer);
    // `status` is read only to pause during conflicts; re-arming on every status
    // change would resend immediately after each save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, dirty, serialized, delay, status === "conflict"]);

  useEffect(() => {
    const retry = () => state.current.attempt > 0 && runRef.current();
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, []);

  useEffect(() => {
    const s = state.current;
    return () => clearTimeout(s.timer);
  }, []);

  // "pending" is derived: there are unsaved edits and nothing is being sent yet.
  const shown = dirty && ["idle", "saved"].includes(status) ? "pending" : status;

  return {
    status: shown,
    lastSavedAt,
    conflict,
    clearConflict: () => {
      setConflict(null);
      setStatus("idle");
    },
    flush: () => runRef.current?.(),
  };
}

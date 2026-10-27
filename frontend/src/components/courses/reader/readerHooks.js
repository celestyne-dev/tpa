import { useCallback, useEffect, useRef, useState } from "react";
import { blockElement } from "./textAnchors";

/**
 * Debounced autosave with a visible status ("Saving…", "Saved", or the error).
 * ``save(value)`` returns a promise; the latest value always wins.
 */
export function useAutosave(save, delay = 900) {
  const [status, setStatus] = useState({ state: "idle", message: "" });
  const timer = useRef(null);
  const pending = useRef(null);
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  const run = useCallback(async () => {
    clearTimeout(timer.current);
    timer.current = null;
    if (pending.current === null) return;
    const value = pending.current;
    pending.current = null;
    setStatus({ state: "saving", message: "Saving…" });
    try {
      await saveRef.current(value);
      if (pending.current === null) setStatus({ state: "saved", message: "Saved" });
    } catch (error) {
      pending.current = pending.current ?? value;
      setStatus({
        state: "error",
        message: error?.message || "Couldn't save. Check your connection.",
      });
    }
  }, []);
  const schedule = useCallback(
    (value) => {
      pending.current = value;
      setStatus({ state: "pending", message: "Unsaved changes" });
      clearTimeout(timer.current);
      timer.current = setTimeout(run, delay);
    },
    [delay, run],
  );
  useEffect(
    () => () => {
      // Leaving the page or the editor: save what's left straight away.
      if (pending.current !== null) run();
    },
    [run],
  );
  return { status, schedule, flush: run };
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

export const scrollBehavior = () => (prefersReducedMotion() ? "auto" : "smooth");

const MIN_INTERVAL = 10_000; // never more than one save every 10 seconds
const SETTLE = 2_500; // wait until the reader stops scrolling for a moment
const MIN_CHANGE = 5; // percent

function measure(article) {
  const rect = article.getBoundingClientRect();
  const viewport = window.innerHeight || 800;
  const read = viewport * 0.3 - rect.top;
  const percent = Math.max(0, Math.min(100, (read / Math.max(rect.height, 1)) * 100));
  let block = null;
  for (const el of article.querySelectorAll("[data-block-uid]")) {
    if (el.getBoundingClientRect().bottom > viewport * 0.2) {
      block = el.getAttribute("data-block-uid");
      break;
    }
  }
  return { block, percent: Math.round(percent * 10) / 10 };
}

/**
 * Remembers where a learner is in a lesson without writing on every scroll event: a
 * position is saved after scrolling settles, only when it moved meaningfully, at most
 * every 10 seconds, plus once when the page is hidden or left. It never completes a lesson.
 * On load the reader is returned near the saved block (unless it was the very top/end).
 */
export function useReadingPosition({ articleRef, enabled, initial, save, saveOnExit }) {
  const [restored, setRestored] = useState(false);
  const last = useRef({ block: initial?.block ?? null, percent: initial?.percent ?? 0, at: 0 });
  const current = useRef(null);
  const timer = useRef(null);
  const saveRef = useRef(save);
  const exitRef = useRef(saveOnExit);
  useEffect(() => {
    saveRef.current = save;
    exitRef.current = saveOnExit;
  });

  useEffect(() => {
    const article = articleRef.current;
    if (!enabled || !article || !initial?.block) return;
    if (initial.percent < 3 || initial.percent > 97) return;
    const target = blockElement(article, initial.block);
    if (!target) return;
    target.scrollIntoView?.({ block: "start", behavior: "auto" });
    setRestored(true);
    // Only on first render of this lesson.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  useEffect(() => {
    const article = articleRef.current;
    if (!enabled || !article) return undefined;
    const changed = (pos) =>
      pos.block !== last.current.block ||
      Math.abs(pos.percent - last.current.percent) >= MIN_CHANGE;
    const commit = () => {
      timer.current = null;
      const pos = current.current;
      if (!pos || !changed(pos)) return;
      const wait = last.current.at + MIN_INTERVAL - Date.now();
      if (wait > 0) {
        timer.current = setTimeout(commit, wait);
        return;
      }
      last.current = { ...pos, at: Date.now() };
      saveRef.current(pos).catch(() => {
        last.current = { ...last.current, block: null };
      });
    };
    let frame = null;
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        current.current = measure(article);
        clearTimeout(timer.current);
        timer.current = setTimeout(commit, SETTLE);
      });
    };
    const onHide = () => {
      const pos = current.current;
      if (pos && changed(pos)) {
        last.current = { ...pos, at: Date.now() };
        exitRef.current?.(pos);
      }
    };
    const onVisibility = () => document.visibilityState === "hidden" && onHide();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onVisibility);
      if (frame) cancelAnimationFrame(frame);
      clearTimeout(timer.current);
      onHide(); // moving to another lesson or page
    };
  }, [articleRef, enabled]);

  return { restored, dismiss: () => setRestored(false) };
}

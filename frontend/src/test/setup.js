import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  vi.useRealTimers(); // a failed fake-timer test must not leak fake timers
  cleanup();
  document.head.querySelectorAll("[data-seo]").forEach((el) => el.remove());
  document.body.style.overflow = "";
});

if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  });
}
window.scrollTo = () => {};

// Testing Library only advances fake timers (in waitFor and its async wrapper) when it
// sees a global `jest`. Point it at Vitest's timers so tests using vi.useFakeTimers()
// don't stall on Testing Library's own setTimeout calls.
globalThis.jest = { advanceTimersByTime: (ms) => vi.advanceTimersByTime(ms) };

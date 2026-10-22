import { createContext } from "react";

/**
 * During prerendering a collector is provided (see createHeadCollector) and the
 * page's <Seo> records its tags in it. On the client the value is null and
 * <Seo> updates document.head directly.
 */
export const HeadContext = createContext(null);

/** Per-render collector used by the prerenderer. */
export function createHeadCollector() {
  const collector = {
    head: null,
    status: 200,
    setHead(head) {
      collector.head = head;
    },
    setStatus(status) {
      collector.status = status;
    },
  };
  return collector;
}

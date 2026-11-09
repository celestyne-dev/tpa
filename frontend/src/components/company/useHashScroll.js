import { useEffect } from "react";
import { useLocation } from "react-router";

/**
 * Scrolls to the element with `id` when the page is opened with that #hash (for example
 * "Start a partnership inquiry" on /advertise links to /partner-with-us#partnership-inquiry).
 * The site layout scrolls to the top on every navigation, so this runs after it.
 */
export function useHashScroll(id) {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash !== `#${id}`) return undefined;
    const frame = requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView?.({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [hash, id]);
}

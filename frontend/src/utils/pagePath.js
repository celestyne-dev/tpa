// Mirrors the backend's page path rule (lowercase slugs, at most four levels).
const PAGE_PATH = /^\/(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:\/[a-z0-9]+(?:-[a-z0-9]+)*){0,3})?$/;

/** A CMS page path for a URL pathname, or null when it cannot be a CMS page. */
export function normalisePath(pathname) {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return PAGE_PATH.test(path) ? path : null;
}

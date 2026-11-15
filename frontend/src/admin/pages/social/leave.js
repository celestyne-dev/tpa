/** Leaves the CMS for a platform's consent screen (separate so tests can replace it). */
export function leaveTo(url) {
  window.location.assign(url);
}

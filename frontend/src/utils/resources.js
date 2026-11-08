/** Statuses a visitor can act on now ("coming soon" and unavailable items are never listed). */
const AVAILABLE = ["free", "available"];

/** Published free resources visitors can get now (never drafts, bundles or "coming soon"). */
export function availableFreeResources(products) {
  return listedResources(products).filter((p) => p.is_free);
}

/**
 * Resources for the Resource Library: published written resources visitors can get now,
 * free or paid (bundles, "coming soon" and unavailable items are left out; the public
 * API never returns drafts).
 */
export function listedResources(products) {
  return (products ?? []).filter((p) => p.type !== "bundle" && AVAILABLE.includes(p.availability));
}

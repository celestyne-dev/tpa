/** Published free resources visitors can get now (never drafts, bundles or "coming soon"). */
export function availableFreeResources(products) {
  return (products ?? []).filter(
    (p) => p.type !== "bundle" && p.is_free && ["free", "available"].includes(p.availability),
  );
}

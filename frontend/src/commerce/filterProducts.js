/** Client-side catalogue filtering and sorting (the full catalogue is prerendered). */
function priceOf(product, currency) {
  if (product.availability === "free") return 0;
  if (product.availability !== "available") return null;
  return product.prices.find((p) => p.currency === currency)?.amount_minor ?? null;
}

export function filterProducts(products, { q, category, collection, type, sort }, currency) {
  let items = products;
  if (category) items = items.filter((p) => p.categories.some((c) => c.slug === category));
  if (collection) items = items.filter((p) => p.collections?.includes(collection));
  if (type) items = items.filter((p) => p.type === type);
  if (q) {
    const needle = q.toLowerCase();
    items = items.filter((p) =>
      `${p.title} ${p.subtitle} ${p.description} ${p.type_label}`.toLowerCase().includes(needle),
    );
  }
  const sorted = [...items];
  if (sort === "newest")
    sorted.sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
  else if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
  else if (sort === "price_asc" || sort === "price_desc") {
    const dir = sort === "price_asc" ? 1 : -1;
    sorted.sort((a, b) => {
      const pa = priceOf(a, currency);
      const pb = priceOf(b, currency);
      if (pa === null) return 1;
      if (pb === null) return -1;
      return (pa - pb) * dir;
    });
  }
  return sorted;
}

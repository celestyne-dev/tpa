import { BookOpen, Search } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { ProductCard } from "@/components/products/ProductCard";
import { Seo } from "@/components/seo/Seo";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconFeature } from "@/components/ui/IconFeature";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { shopPromise } from "@/data/marketing";
import { useProducts, useSite } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { breadcrumbJsonLd } from "@/utils/structuredData";
import { filterProducts } from "@/commerce/filterProducts";

const SORTS = {
  featured: "Featured",
  newest: "Newest",
  price_asc: "Price: low to high",
  price_desc: "Price: high to low",
  title: "Title A–Z",
};

export function ShopPage() {
  const { data: site } = useSite();
  const { data: products, meta, isLoading, isError, retry } = useProducts();
  const { currency, setCurrency, currencies } = useDisplayCurrency();
  const [params, setParams] = useSearchParams();
  const filters = {
    q: params.get("q") ?? "",
    category: params.get("category") ?? "",
    collection: params.get("collection") ?? "",
    sort: SORTS[params.get("sort")] ? params.get("sort") : "featured",
  };
  const update = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const visible = useMemo(
    () => filterProducts(products ?? [], filters, currency),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [products, filters.q, filters.category, filters.collection, filters.sort, currency],
  );
  const shop = site?.shop ?? {};
  const categories = meta.categories ?? [];
  const collections = meta.collections ?? [];
  const hasFilters = filters.q || filters.category || filters.collection;
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Shop", href: routes.shop },
  ];

  return (
    <>
      <Seo
        title="Shop — eBooks, Workbooks & Personal Growth Guides"
        description={
          shop.intro ||
          "Original Think Positive Always eBooks, workbooks and journals for a stronger mindset, confidence and resilience."
        }
        path={routes.shop}
        jsonLd={[breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader
        eyebrow="The shop"
        title={shop.title || "Tools for Your Growth Journey"}
        description={shop.intro}
        breadcrumbs={crumbs}
      />

      <Section aria-labelledby="catalog-heading">
        <SectionHeading
          id="catalog-heading"
          eyebrow="Digital resources"
          title="Browse the collection"
          description="Every title is an original Think Positive Always resource. Products marked “Coming soon” are still being written and can't be bought yet."
        />
        {shop.notice && (
          <div className="mt-8 max-w-3xl">
            <Notice title="Good to know">{shop.notice}</Notice>
          </div>
        )}

        <form
          role="search"
          aria-label="Filter products"
          className="mt-10 grid gap-4 rounded-2xl border border-charcoal/10 bg-white/70 p-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]"
          onSubmit={(event) => event.preventDefault()}
        >
          <label className="relative block">
            <span className="sr-only">Search products</span>
            <Search
              aria-hidden
              className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted"
            />
            <input
              type="search"
              value={filters.q}
              onChange={(e) => update("q", e.target.value)}
              placeholder="Search titles"
              className="w-full rounded-xl border border-charcoal/15 bg-white py-2.5 pr-3 pl-10 text-base focus:border-sage-600 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="sr-only">Category</span>
            <select
              value={filters.category}
              onChange={(e) => update("category", e.target.value)}
              className="w-full rounded-xl border border-charcoal/15 bg-white px-3 py-2.5 text-base"
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="sr-only">Collection</span>
            <select
              value={filters.collection}
              onChange={(e) => update("collection", e.target.value)}
              className="w-full rounded-xl border border-charcoal/15 bg-white px-3 py-2.5 text-base"
            >
              <option value="">All collections</option>
              {collections.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="sr-only">Sort by</span>
            <select
              value={filters.sort}
              onChange={(e) => update("sort", e.target.value === "featured" ? "" : e.target.value)}
              className="w-full rounded-xl border border-charcoal/15 bg-white px-3 py-2.5 text-base"
            >
              {Object.entries(SORTS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </form>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-muted" aria-live="polite">
            {isLoading
              ? "Loading products…"
              : `${visible.length} ${visible.length === 1 ? "product" : "products"}`}
          </p>
          <CurrencySwitcher currency={currency} currencies={currencies} onChange={setCurrency} />
        </div>

        <div className="mt-8">
          {isLoading ? (
            <CardGridSkeleton count={4} className="lg:grid-cols-3" />
          ) : isError ? (
            <ErrorState onRetry={retry} title="We couldn't load the shop" />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title={hasFilters ? "No products match" : "No products yet"}
              description={
                hasFilters
                  ? "Try a different search or clear the filters."
                  : "Our first titles are being written. Please check back soon."
              }
            />
          ) : (
            <ul className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((product) => (
                <li key={product.id}>
                  <ProductCard product={product} currency={currency} showHighlights />
                </li>
              ))}
            </ul>
          )}
        </div>
      </Section>

      <Section tone="cream" aria-labelledby="shop-promise-heading">
        <SectionHeading
          id="shop-promise-heading"
          title="What to expect from our resources"
          align="center"
        />
        <ul className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {shopPromise.map((item) => (
            <li key={item.title}>
              <IconFeature icon={item.icon} title={item.title} className="flex-col">
                {item.text}
              </IconFeature>
            </li>
          ))}
        </ul>
      </Section>

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel description="Want to know when new titles launch? The Positive Reset will share news about new resources once sign-ups open." />
      </Section>
    </>
  );
}

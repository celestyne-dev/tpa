import { BookOpen } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { ProductCard } from "@/components/products/ProductCard";
import { Seo } from "@/components/seo/Seo";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useProducts } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { breadcrumbJsonLd } from "@/utils/structuredData";

const ACCESS = [
  ["", "All"],
  ["free", "Free"],
  ["premium", "Premium"],
];

function Chip({ active, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
        active
          ? "bg-sage-700 text-ivory"
          : "border border-charcoal/15 bg-white text-charcoal hover:border-sage-600"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Written resources by type (eBooks, workbooks, planners, templates …). Uses the same
 * prerendered catalogue as the shop; each card opens the resource's own page.
 */
export function ResourceLibraryPage() {
  const { data: products, isLoading, isError, retry } = useProducts();
  const { currency, setCurrency, currencies } = useDisplayCurrency();
  const [params, setParams] = useSearchParams();
  const type = params.get("type") ?? "";
  const access = ["free", "premium"].includes(params.get("access")) ? params.get("access") : "";
  const update = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const resources = useMemo(() => (products ?? []).filter((p) => p.type !== "bundle"), [products]);
  const types = useMemo(() => {
    const seen = new Map();
    resources.forEach((p) => seen.set(p.type, p.type_label));
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [resources]);
  const visible = resources.filter(
    (p) => (!type || p.type === type) && (!access || (access === "free" ? p.is_free : !p.is_free)),
  );
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Resource library", href: routes.resources },
  ];

  return (
    <>
      <Seo
        title="Resource Library — Written Guides, Workbooks & Templates"
        description="Browse Think Positive Always eBooks, workbooks, planners, worksheets, guides, templates and checklists. Free and premium written resources for personal growth."
        path={routes.resources}
        jsonLd={[breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader
        eyebrow="Resource library"
        title="Written resources for your growth"
        description="Practical eBooks, workbooks, planners and templates you can download and use at your own pace."
        breadcrumbs={crumbs}
      />
      <Section aria-labelledby="library-heading">
        <h2 id="library-heading" className="sr-only">
          Resources
        </h2>
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Type</legend>
            <div className="flex flex-wrap gap-2">
              <Chip active={!type} onClick={() => update("type", "")}>
                All types
              </Chip>
              {types.map(([key, label]) => (
                <Chip key={key} active={type === key} onClick={() => update("type", key)}>
                  {label}
                </Chip>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Access</legend>
            <div className="flex flex-wrap gap-2">
              {ACCESS.map(([key, label]) => (
                <Chip
                  key={key || "all"}
                  active={access === key}
                  onClick={() => update("access", key)}
                >
                  {label}
                </Chip>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-muted" aria-live="polite">
            {isLoading
              ? "Loading resources…"
              : `${visible.length} ${visible.length === 1 ? "resource" : "resources"}`}
          </p>
          <CurrencySwitcher currency={currency} currencies={currencies} onChange={setCurrency} />
        </div>
        <div className="mt-8">
          {isLoading ? (
            <CardGridSkeleton count={4} className="lg:grid-cols-3" />
          ) : isError ? (
            <ErrorState onRetry={retry} title="We couldn't load the resource library" />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title={type || access ? "No resources match" : "No resources yet"}
              description={
                type || access
                  ? "Try another type or show all resources."
                  : "Our first resources are being written. Please check back soon."
              }
              action={
                <Link to={routes.shop} className="underline underline-offset-4">
                  Visit the shop
                </Link>
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
        <p className="mt-10 max-w-2xl text-sm text-muted">
          Prices are shown in the currency you choose and charged in that currency; we never convert
          them. Downloads are delivered through your library after purchase, or by email when you
          check out as a guest.
        </p>
      </Section>
    </>
  );
}

import { Search } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { ArticleGrid, ArticleRows } from "@/components/articles/ArticleGrid";
import { NewsletterPromo } from "@/components/newsletter/NewsletterPromo";
import { Seo } from "@/components/seo/Seo";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { Section } from "@/components/ui/Section";
import { routes } from "@/config/navigation";
import { LATEST_QUERY, QUOTES_FEATURED_QUERY, pageParam, quoteListQuery } from "@/data/queries";
import { useArticles, useQuoteCollections } from "@/hooks/useContent";
import { quoteCollectionsJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

const TITLE = "Positive Quote Collections";
const DESCRIPTION =
  "Curated quote collections on mindset, confidence, resilience and intentional living, with reflections and practical ways to put each idea to use.";

const chip =
  "inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-medium whitespace-nowrap transition-colors";

/**
 * /quotes and /quotes/page/N: the quote collections (Admin › Quotes). Page 1 opens with
 * the featured collections. Topic and search filters (?topic=, ?q=) narrow the list in
 * the browser; the canonical URL stays the unfiltered page and filtered views are noindex.
 */
export function QuotesPage() {
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = pageParam(params.page);
  const topic = searchParams.get("topic") || undefined;
  const q = searchParams.get("q")?.trim() || undefined;
  const filtered = Boolean(topic || q);
  const featured = useQuoteCollections(QUOTES_FEATURED_QUERY);
  const list = useQuoteCollections({ ...quoteListQuery(page ?? 1), topic, q });
  const { data: articles } = useArticles(LATEST_QUERY);

  const outOfRange =
    page === null ||
    (params.page !== undefined && list.pagination && page > list.pagination.total_pages);
  if (outOfRange && !filtered) return <NotFoundPage />;

  const leads = page === 1 && !filtered ? (featured.data ?? []) : [];
  const leadSlugs = new Set(leads.map((c) => c.slug));
  const items = (list.data ?? []).filter((c) => !leadSlugs.has(c.slug));
  const topics = list.topics?.length ? list.topics : (featured.topics ?? []);
  const empty = list.data && list.data.length === 0 && !filtered;

  const onSearch = (event) => {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("q")?.toString().trim();
    const next = new URLSearchParams(searchParams);
    if (value) next.set("q", value);
    else next.delete("q");
    setSearchParams(next);
  };

  return (
    <>
      <Seo
        title={page > 1 ? `${TITLE} (Page ${page})` : TITLE}
        description={DESCRIPTION}
        path={routes.quotesPage(page)}
        // Nothing to offer yet, or a filtered view of this page: kept out of search.
        noIndex={empty || filtered}
        jsonLd={list.data?.length ? [quoteCollectionsJsonLd(list.data, routes.quotes)] : []}
      />
      <PageHeader
        eyebrow="Words to live by"
        title="Quote collections"
        size="wide"
        description="Carefully chosen quotes on mindset, confidence, resilience and intentional living, each collection with our own reflections and practical ways to use the ideas in everyday life."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Quotes", href: routes.quotes },
        ]}
      >
        <div className="flex flex-col gap-4">
          <form role="search" onSubmit={onSearch} className="flex max-w-md gap-2">
            <label htmlFor="quotes-search" className="sr-only">
              Search quote collections
            </label>
            <input
              id="quotes-search"
              name="q"
              type="search"
              defaultValue={q ?? ""}
              placeholder="Search collections"
              className="min-h-11 w-full rounded-full border border-charcoal/15 bg-white px-4 text-base"
            />
            <button
              type="submit"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-sage-700 px-4 text-white hover:bg-sage-800"
            >
              <Search aria-hidden className="size-4" />
              <span className="sr-only">Search</span>
            </button>
          </form>
          {topics.length > 0 && (
            <nav aria-label="Quote categories" className="-mx-5 sm:mx-0">
              <ul className="flex [scrollbar-width:none] gap-2 overflow-x-auto px-5 pb-1 sm:flex-wrap sm:overflow-visible sm:px-0">
                <li className="shrink-0">
                  <Link
                    to={routes.quotes}
                    aria-current={!topic ? "page" : undefined}
                    className={`${chip} ${!topic ? "border-sage-700 bg-sage-700 text-white" : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600"}`}
                  >
                    All
                  </Link>
                </li>
                {topics.map((t) => (
                  <li key={t.slug} className="shrink-0">
                    <Link
                      to={`${routes.quotes}?topic=${encodeURIComponent(t.slug)}`}
                      aria-current={topic === t.slug ? "page" : undefined}
                      className={`${chip} ${topic === t.slug ? "border-sage-700 bg-sage-700 text-white" : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600"}`}
                    >
                      {t.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>
      </PageHeader>

      {leads.length > 0 && (
        <Section spacing="sm" size="wide" aria-labelledby="featured-quotes-heading">
          <EditorialHeading id="featured-quotes-heading" title="Featured collections" />
          <ArticleGrid articles={leads} className="mt-6" />
        </Section>
      )}

      <Section tone="cream" spacing="sm" size="wide" aria-labelledby="latest-quotes-heading">
        <EditorialHeading
          id="latest-quotes-heading"
          title={
            filtered
              ? "Matching collections"
              : page > 1
                ? `Latest collections · Page ${page}`
                : "Latest collections"
          }
        />
        {list.isLoading ? (
          <p className="mt-6 text-muted">Loading collections…</p>
        ) : items.length > 0 ? (
          <ArticleGrid articles={items} className="mt-6" />
        ) : (
          <p className="mt-6 text-muted">
            {filtered
              ? "No collections match yet. Try another category or search."
              : leads.length
                ? "More collections are on the way."
                : "Our first quote collections are on the way."}
          </p>
        )}
        {!filtered && (
          <Pagination
            page={page ?? 1}
            totalPages={list.pagination?.total_pages}
            hrefFor={routes.quotesPage}
            label="Quote collection pages"
          />
        )}
      </Section>

      {articles?.length > 0 && (
        <Section spacing="sm" size="wide" aria-labelledby="quotes-articles-heading">
          <EditorialHeading
            id="quotes-articles-heading"
            title="Read more from the journal"
            action={{ to: routes.articles, label: "All articles" }}
          />
          <ArticleRows articles={articles.slice(0, 3)} className="mt-6" />
        </Section>
      )}
      <NewsletterPromo className="bg-ivory py-12 sm:py-16" />
    </>
  );
}

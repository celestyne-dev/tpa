import { SearchX } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Pagination } from "@/components/ui/Pagination";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { PAGE_SIZE } from "@/data/queries";
import { useArticles } from "@/hooks/useContent";
import { cn } from "@/utils/format";
import { ArticleGrid } from "./ArticleGrid";

/** URL of an archive page: /articles/page/N, or ?topic=&page= while a topic is chosen. */
function archiveHref(topic, page) {
  if (!topic) return routes.articlesPage(page);
  const params = new URLSearchParams({ topic });
  if (page > 1) params.set("page", String(page));
  return `${routes.articles}?${params}`;
}

/**
 * Topic filter + paginated grid. Pages are real links (/articles/page/N, prerendered), so
 * every article is reachable without JavaScript; the topic chips filter in place
 * (?topic=), whose canonical pages are the topic pages themselves.
 */
export function ArticleFilter({ topics, page: routePage = 1 }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const active = searchParams.get("topic") || null;
  // Old ?page=N links keep working; /articles/page/N is the canonical form.
  const queryPage = Math.max(1, Number.parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const page = active || routePage === 1 ? queryPage : routePage;
  const {
    data: articles,
    pagination,
    isLoading,
    isError,
    isNotFound,
    retry,
  } = useArticles({
    topic: active ?? undefined,
    page,
    pageSize: PAGE_SIZE,
  });
  const activeTopic = topics.find((t) => t.slug === active);

  const update = (next) => {
    navigate(archiveHref(next.topic ?? null, next.page ?? 1), { preventScrollReset: true });
  };

  const chip = (slug, label) => {
    const pressed = active === slug;
    return (
      <button
        key={slug ?? "all"}
        type="button"
        aria-pressed={pressed}
        onClick={() => update({ topic: slug })}
        className={cn(
          "rounded-full border px-4 py-2 text-sm font-medium transition-colors",
          pressed
            ? "border-sage-700 bg-sage-700 text-ivory"
            : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600 hover:text-sage-800",
        )}
      >
        {label}
      </button>
    );
  };

  let content;
  if (isLoading) content = <CardGridSkeleton count={3} />;
  else if (isNotFound || (isError === false && articles?.length === 0)) {
    content = (
      <EmptyState
        icon={SearchX}
        title="No articles in this topic yet"
        description={`We are still writing for ${activeTopic?.name ?? "this topic"}. In the meantime, explore our other articles or learn more about the topic.`}
        action={
          <div className="flex flex-wrap justify-center gap-3">
            <Button onClick={() => update({})}>Show all articles</Button>
            {activeTopic && (
              <ButtonLink to={routes.topic(activeTopic.slug)} variant="outline">
                About {activeTopic.name}
              </ButtonLink>
            )}
          </div>
        }
      />
    );
  } else if (isError) content = <ErrorState onRetry={retry} />;
  else content = <ArticleGrid articles={articles} />;

  const total = pagination?.total ?? 0;

  return (
    <div>
      <div role="group" aria-label="Filter articles by topic" className="flex flex-wrap gap-2.5">
        {chip(null, "All topics")}
        {topics.map((t) => chip(t.slug, t.name))}
      </div>
      <p aria-live="polite" className="mt-6 min-h-6 text-sm text-muted">
        {!isLoading &&
          !isError &&
          (activeTopic
            ? `Showing ${total} ${total === 1 ? "article" : "articles"} in ${activeTopic.name}`
            : `Showing all ${total} articles`)}
      </p>
      <div className="mt-8">{content}</div>
      {pagination && (
        <Pagination
          page={pagination.page}
          totalPages={pagination.total_pages}
          hrefFor={(p) => archiveHref(active, p)}
          label={activeTopic ? `${activeTopic.name} article pages` : "Article pages"}
        />
      )}
    </div>
  );
}

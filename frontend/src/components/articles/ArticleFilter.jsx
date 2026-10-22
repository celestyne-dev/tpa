import { ArrowLeft, ArrowRight, SearchX } from "lucide-react";
import { useSearchParams } from "react-router";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useArticles } from "@/hooks/useContent";
import { cn } from "@/utils/format";
import { ArticleGrid } from "./ArticleGrid";

const PAGE_SIZE = 12;

/** Topic filter + paginated grid. Filter state lives in the URL (?topic=&page=). */
export function ArticleFilter({ topics }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const active = searchParams.get("topic") || null;
  const page = Math.max(1, Number.parseInt(searchParams.get("page") ?? "1", 10) || 1);
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
    const params = new URLSearchParams();
    if (next.topic) params.set("topic", next.topic);
    if (next.page && next.page > 1) params.set("page", String(next.page));
    setSearchParams(params, { preventScrollReset: true });
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
      {pagination && pagination.total_pages > 1 && (
        <nav aria-label="Pagination" className="mt-12 flex items-center justify-between gap-4">
          <Button
            variant="outline"
            disabled={!pagination.has_prev}
            onClick={() => update({ topic: active, page: page - 1 })}
          >
            <ArrowLeft aria-hidden />
            Newer
          </Button>
          <span className="text-sm text-muted">
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <Button
            variant="outline"
            disabled={!pagination.has_next}
            onClick={() => update({ topic: active, page: page + 1 })}
          >
            Older
            <ArrowRight aria-hidden />
          </Button>
        </nav>
      )}
    </div>
  );
}

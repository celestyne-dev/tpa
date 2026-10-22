import { EyeOff } from "lucide-react";
import { Link, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { ErrorState } from "@/components/ui/ErrorState";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

/**
 * Private draft preview (working copy, unpublished changes included). Served from
 * the authenticated admin API with no-store and noindex headers; never prerendered.
 */
export function ArticlePreviewPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const { data, error, loading, reload } = useAdminQuery(() => api.articles.preview(id), [id]);

  if (error)
    return (
      <ErrorState title="We couldn't load the preview" message={error.message} onRetry={reload} />
    );
  if (loading && !data) return <ArticleSkeleton />;
  const { article, status, has_pending_changes: pending } = data;

  return (
    <div className="-mx-4 sm:-mx-6 lg:-mx-8">
      <div
        role="status"
        className="flex flex-wrap items-center justify-between gap-3 bg-charcoal px-4 py-2 text-sm text-ivory sm:px-6"
      >
        <span className="flex items-center gap-2">
          <EyeOff aria-hidden className="size-4" />
          Private preview · {status}
          {pending ? " · includes unpublished changes" : ""} · not public, not indexed
        </span>
        <Link to={`/admin/articles/${id}/edit`} className="underline">
          Back to the editor
        </Link>
      </div>
      <article className="bg-ivory pb-16">
        <header className="bg-cream">
          <div className="mx-auto max-w-3xl px-4 pt-10 pb-10 sm:px-6">
            {article.topic && (
              <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
                {article.topic.name}
              </p>
            )}
            <h1 className="mt-4 text-4xl leading-[1.1] font-medium sm:text-5xl">{article.title}</h1>
            {article.subtitle && (
              <p className="mt-5 font-serif text-xl text-muted italic">{article.subtitle}</p>
            )}
            <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-charcoal/10 pt-5">
              <p className="text-sm font-medium">By {article.author?.name}</p>
              {article.published_at && (
                <ArticleMeta
                  publishedAt={article.published_at}
                  readingTimeMinutes={article.reading_time_minutes}
                />
              )}
            </div>
          </div>
        </header>
        {article.image && (
          <div className="mx-auto mt-6 max-w-4xl px-4 sm:px-6">
            <div className="relative aspect-[16/10] overflow-hidden rounded-[var(--radius-card)] bg-beige">
              <ContentImage
                image={article.image}
                fill
                priority
                sizes={IMAGE_SIZES.hero}
                className="object-cover"
              />
            </div>
          </div>
        )}
        <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
          <ArticleBody blocks={article.body} />
        </div>
      </article>
    </div>
  );
}

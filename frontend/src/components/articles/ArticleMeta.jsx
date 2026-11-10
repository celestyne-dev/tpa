import { Clock } from "lucide-react";
import { cn, formatDate } from "@/utils/format";

/**
 * The author (on cards, when the article has one), publication date, the "Last updated"
 * date after a material update, and reading time.
 */
export function ArticleMeta({ author, publishedAt, updatedAt, readingTimeMinutes, className }) {
  const showUpdated = updatedAt && updatedAt.slice(0, 10) > (publishedAt ?? "").slice(0, 10);
  return (
    <p className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted", className)}>
      {author && (
        <>
          <span className="font-medium text-charcoal">By {author}</span>
          <span aria-hidden className="size-1 rounded-full bg-sand" />
        </>
      )}
      <time dateTime={publishedAt}>{formatDate(publishedAt)}</time>
      {showUpdated && (
        <>
          <span aria-hidden className="size-1 rounded-full bg-sand" />
          <span>
            Last updated <time dateTime={updatedAt}>{formatDate(updatedAt)}</time>
          </span>
        </>
      )}
      <span aria-hidden className="size-1 rounded-full bg-sand" />
      <span className="inline-flex items-center gap-1.5">
        <Clock aria-hidden className="size-3.5" />
        {readingTimeMinutes} min read
      </span>
    </p>
  );
}

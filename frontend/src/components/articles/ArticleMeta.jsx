import { Clock } from "lucide-react";
import { cn, formatDate } from "@/utils/format";

// Text size: "sm" (default) or "card": 12px on phones and 13px from tablets, with short month
// names ("Nov 20, 2026") so the line fits on homepage cards.
const SIZES = { sm: "text-sm", card: "text-xs sm:text-[0.8125rem]" };

/**
 * The author (on cards, when the article has one), publication date, the "Last updated"
 * date after a material update, and reading time.
 */
export function ArticleMeta({
  author,
  publishedAt,
  updatedAt,
  readingTimeMinutes,
  className,
  size = "sm",
}) {
  const showUpdated = updatedAt && updatedAt.slice(0, 10) > (publishedAt ?? "").slice(0, 10);
  return (
    <p
      className={cn(
        "flex flex-wrap items-center gap-y-1 text-muted",
        size === "card" ? "gap-x-2" : "gap-x-3",
        SIZES[size] ?? SIZES.sm,
        className,
      )}
    >
      {author && (
        <>
          <span className="font-medium text-charcoal">By {author}</span>
          <span aria-hidden className="size-1 rounded-full bg-sand" />
        </>
      )}
      <time dateTime={publishedAt}>
        {formatDate(publishedAt, size === "card" ? "short" : "long")}
      </time>
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

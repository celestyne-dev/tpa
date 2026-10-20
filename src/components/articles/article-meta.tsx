import { Clock } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

export function ArticleMeta({
  publishedAt,
  readingTimeMinutes,
  className,
}: {
  publishedAt: string;
  readingTimeMinutes: number;
  className?: string;
}) {
  return (
    <p className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted", className)}>
      <time dateTime={publishedAt}>{formatDate(publishedAt)}</time>
      <span aria-hidden className="size-1 rounded-full bg-sand" />
      <span className="inline-flex items-center gap-1.5">
        <Clock aria-hidden className="size-3.5" />
        {readingTimeMinutes} min read
      </span>
    </p>
  );
}

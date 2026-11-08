import { ArrowLeft, ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";

function Item({ article, direction }) {
  const next = direction === "next";
  const Icon = next ? ArrowRight : ArrowLeft;
  return (
    <Link
      to={routes.article(article.slug)}
      rel={next ? "next" : "prev"}
      className={cn(
        "group flex h-full flex-col gap-2 rounded-[var(--radius-card)] border border-charcoal/[0.08] bg-white/60 p-5 transition-colors hover:border-sage-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-700",
        next && "sm:items-end sm:text-right",
      )}
    >
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
        {!next && <Icon aria-hidden className="size-3.5" />}
        {next ? "Next article" : "Previous article"}
        {next && <Icon aria-hidden className="size-3.5" />}
      </span>
      <span className="font-serif text-lg leading-snug font-medium text-balance group-hover:text-sage-800">
        {article.title}
      </span>
    </Link>
  );
}

/** Previous (older) and next (newer) published articles, at the end of an article. */
export function ArticleNav({ previous, next, className }) {
  if (!previous && !next) return null;
  return (
    <nav aria-label="More articles" className={cn("grid gap-4 sm:grid-cols-2", className)}>
      {previous ? (
        <Item article={previous} direction="previous" />
      ) : (
        <span aria-hidden className="hidden sm:block" />
      )}
      {next && <Item article={next} direction="next" />}
    </nav>
  );
}

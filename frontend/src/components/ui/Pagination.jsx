import { ArrowLeft, ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { cn } from "@/utils/format";
import { pageWindow } from "@/utils/pagination";

const linkStyles =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-full border px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-700";

/**
 * Crawlable pagination: every page is a real link (`<a href>`), so search engines and
 * visitors without JavaScript reach every article. `hrefFor(page)` returns the page URL.
 */
export function Pagination({ page, totalPages, hrefFor, label = "Pagination", className }) {
  if (!totalPages || totalPages < 2) return null;
  const pages = pageWindow(page, totalPages);
  return (
    <nav aria-label={label} className={cn("mt-12", className)}>
      <ul className="flex flex-wrap items-center justify-center gap-2">
        {page > 1 && (
          <li>
            <Link
              to={hrefFor(page - 1)}
              rel="prev"
              className={cn(linkStyles, "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600")}
            >
              <ArrowLeft aria-hidden className="size-4" />
              Newer<span className="sr-only"> articles</span>
            </Link>
          </li>
        )}
        {pages.map((p, i) =>
          p === null ? (
            <li key={`gap-${i}`} aria-hidden className="px-1 text-muted">
              …
            </li>
          ) : (
            <li key={p}>
              <Link
                to={hrefFor(p)}
                aria-current={p === page ? "page" : undefined}
                className={cn(
                  linkStyles,
                  p === page
                    ? "border-sage-700 bg-sage-700 text-ivory"
                    : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600",
                )}
              >
                <span className="sr-only">Page </span>
                {p}
              </Link>
            </li>
          ),
        )}
        {page < totalPages && (
          <li>
            <Link
              to={hrefFor(page + 1)}
              rel="next"
              className={cn(linkStyles, "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600")}
            >
              Older<span className="sr-only"> articles</span>
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </li>
        )}
      </ul>
      <p className="mt-4 text-center text-sm text-muted">
        Page {page} of {totalPages}
      </p>
    </nav>
  );
}

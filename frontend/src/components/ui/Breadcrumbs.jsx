import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { cn } from "@/utils/format";

/** Accessible breadcrumb trail; the last item is the current page. */
export function Breadcrumbs({ items, className }) {
  return (
    <nav aria-label="Breadcrumb" className={cn("text-sm", className)}>
      <ol className="flex flex-wrap items-center gap-1.5 text-muted">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li key={item.href} className="flex items-center gap-1.5">
              {isLast ? (
                <span aria-current="page" className="line-clamp-1 text-charcoal">
                  {item.name}
                </span>
              ) : (
                <>
                  <Link
                    to={item.href}
                    className="underline-offset-4 hover:text-sage-700 hover:underline"
                  >
                    {item.name}
                  </Link>
                  <ChevronRight aria-hidden className="size-3.5 text-sand" />
                </>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

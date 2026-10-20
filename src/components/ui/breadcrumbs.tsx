import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export interface BreadcrumbItem {
  name: string;
  href: string;
}

/** Accessible breadcrumb trail. The final item is rendered as the current page. */
export function Breadcrumbs({ items, className }: { items: BreadcrumbItem[]; className?: string }) {
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
                    href={item.href}
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

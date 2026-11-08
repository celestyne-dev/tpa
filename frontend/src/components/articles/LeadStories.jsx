import { cn } from "@/utils/format";
import { ArticleCard } from "./ArticleCard";

/**
 * A large lead story with up to three smaller stories alongside (stacked below on phones
 * and tablets): the opening of the homepage, the articles archive and topic pages.
 */
export function LeadStories({ articles, priority = false, className }) {
  const [lead, ...rest] = articles ?? [];
  if (!lead) return null;
  return (
    <div
      className={cn(
        "grid gap-8",
        rest.length > 0 && "lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:gap-12",
        className,
      )}
    >
      <ArticleCard article={lead} variant="lead" priority={priority} />
      {rest.length > 0 && (
        <ul className="divide-y divide-charcoal/10 lg:border-l lg:border-charcoal/10 lg:pl-10">
          {rest.slice(0, 3).map((article) => (
            <li key={article.slug} className="py-5 first:pt-0 last:pb-0">
              <ArticleCard article={article} variant="compact" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

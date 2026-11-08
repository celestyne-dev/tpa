import { cn } from "@/utils/format";
import { ArticleCard } from "./ArticleCard";

const COLUMNS = {
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-2 lg:grid-cols-3",
  4: "sm:grid-cols-2 lg:grid-cols-4",
};

/** Responsive grid of article cards (`columns` is the widest layout: 2, 3 or 4). */
export function ArticleGrid({ articles, headingLevel = "h3", columns = 3, className }) {
  return (
    <ul className={cn("grid gap-8", COLUMNS[columns] ?? COLUMNS[3], className)}>
      {articles.map((article) => (
        <li key={article.slug}>
          <ArticleCard article={article} headingLevel={headingLevel} />
        </li>
      ))}
    </ul>
  );
}

/** A list of horizontal stories with excerpts, separated by thin rules. */
export function ArticleRows({ articles, headingLevel = "h3", label, className }) {
  return (
    <ul aria-label={label} className={cn("divide-y divide-charcoal/10", className)}>
      {articles.map((article) => (
        <li key={article.slug} className="py-6 first:pt-0 last:pb-0">
          <ArticleCard article={article} variant="row" headingLevel={headingLevel} />
        </li>
      ))}
    </ul>
  );
}

import { cn } from "@/utils/format";
import { ArticleCard } from "./ArticleCard";

export function ArticleGrid({ articles, headingLevel = "h3", className }) {
  return (
    <ul className={cn("grid gap-8 sm:grid-cols-2 lg:grid-cols-3", className)}>
      {articles.map((article) => (
        <li key={article.slug}>
          <ArticleCard article={article} headingLevel={headingLevel} />
        </li>
      ))}
    </ul>
  );
}

import { cn } from "@/lib/utils";
import { ArticleCard, type ArticleCardData } from "./article-card";

export function ArticleGrid({
  articles,
  headingLevel = "h3",
  className,
}: {
  articles: ArticleCardData[];
  headingLevel?: "h2" | "h3";
  className?: string;
}) {
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

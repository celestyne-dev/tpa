import { ArrowRight } from "lucide-react";
import { routes } from "@/config/navigation";
import { ArticleCard, type ArticleCardData } from "@/components/articles/article-card";
import { ButtonLink } from "@/components/ui/button";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";

export function FeaturedArticles({ articles }: { articles: ArticleCardData[] }) {
  const [lead, ...rest] = articles;
  if (!lead) return null;
  return (
    <Section tone="cream" aria-labelledby="featured-articles-heading">
      <SectionHeading
        id="featured-articles-heading"
        eyebrow="From the journal"
        title="Fresh Perspectives for Everyday Life"
        description="Thoughtful articles on mindset, confidence, resilience, and intentional living."
        action={
          <ButtonLink href={routes.articles} variant="outline">
            View all articles
            <ArrowRight aria-hidden />
          </ButtonLink>
        }
      />
      <div className="mt-12 space-y-8">
        <ArticleCard article={lead} variant="feature" />
        {rest.length > 0 && (
          <ul className="grid gap-8 sm:grid-cols-2">
            {rest.map((article) => (
              <li key={article.slug}>
                <ArticleCard article={article} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

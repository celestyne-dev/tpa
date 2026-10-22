import { ArrowRight } from "lucide-react";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { FEATURED_QUERY } from "@/data/queries";
import { useArticles } from "@/hooks/useContent";

export function FeaturedArticles() {
  const { data: articles, isLoading, isError, retry } = useArticles(FEATURED_QUERY);
  const [lead, ...rest] = articles ?? [];
  return (
    <Section tone="cream" aria-labelledby="featured-articles-heading">
      <SectionHeading
        id="featured-articles-heading"
        eyebrow="From the journal"
        title="Fresh Perspectives for Everyday Life"
        description="Thoughtful articles on mindset, confidence, resilience, and intentional living."
        action={
          <ButtonLink to={routes.articles} variant="outline">
            View all articles
            <ArrowRight aria-hidden />
          </ButtonLink>
        }
      />
      <div className="mt-12 space-y-8">
        {isLoading && <CardGridSkeleton count={3} />}
        {isError && <ErrorState onRetry={retry} title="We couldn't load the latest articles" />}
        {lead && <ArticleCard article={lead} variant="feature" />}
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

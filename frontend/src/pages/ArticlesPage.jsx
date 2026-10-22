import { ArticleCard } from "@/components/articles/ArticleCard";
import { ArticleFilter } from "@/components/articles/ArticleFilter";
import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { Seo } from "@/components/seo/Seo";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { FEATURED_QUERY } from "@/data/queries";
import { useArticles, useTopics } from "@/hooks/useContent";

export function ArticlesPage() {
  const { data: featured } = useArticles(FEATURED_QUERY);
  const { data: topics } = useTopics();
  const lead = featured?.[0];
  // Only offer filters for topics that have articles.
  const usedTopics = (topics ?? []).filter((t) => t.article_count > 0);

  return (
    <>
      <Seo
        title="Articles on Mindset, Confidence & Personal Growth"
        description="Read thoughtful articles on positive mindset, personal growth, confidence, resilience, boundaries, and intentional living from Think Positive Always."
        path={routes.articles}
      />
      <PageHeader
        eyebrow="The journal"
        title="Articles"
        description="Encouragement, perspective, and practical ideas for building a stronger mindset and a more intentional life."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Articles", href: routes.articles },
        ]}
      />

      {lead && (
        <Section spacing="sm" aria-labelledby="featured-heading">
          <h2 id="featured-heading" className="sr-only">
            Featured article
          </h2>
          <ArticleCard article={lead} variant="feature" priority />
        </Section>
      )}

      <Section tone="cream" aria-labelledby="all-articles-heading">
        <SectionHeading
          id="all-articles-heading"
          title="Browse by topic"
          description="Choose a topic to focus on what matters most to you right now."
        />
        <div className="mt-10">
          <ArticleFilter topics={usedTopics} />
        </div>
      </Section>

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel />
      </Section>
    </>
  );
}

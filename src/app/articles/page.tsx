import type { Metadata } from "next";
import { ArticleCard } from "@/components/articles/article-card";
import { ArticleFilter } from "@/components/articles/article-filter";
import { toCardData } from "@/components/articles/to-card-data";
import { NewsletterPanel } from "@/components/newsletter/newsletter-panel";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { EmptyState } from "@/components/ui/empty-state";
import { routes } from "@/config/navigation";
import { getArticles, getFeaturedArticles, getTopics } from "@/lib/content";
import { buildMetadata } from "@/lib/seo";
import { BookOpen } from "lucide-react";

export const metadata: Metadata = buildMetadata({
  title: "Articles on Mindset, Confidence & Personal Growth",
  description:
    "Read thoughtful articles on positive mindset, personal growth, confidence, resilience, boundaries, and intentional living from Think Positive Always.",
  path: routes.articles,
});

export default async function ArticlesPage() {
  const [articles, featured, topics] = await Promise.all([
    getArticles(),
    getFeaturedArticles(1),
    getTopics(),
  ]);
  const lead = featured[0];
  // Only offer filters for topics that actually have articles, ordered by topic list.
  const usedTopics = topics
    .filter((t) => articles.some((a) => a.topicSlug === t.slug))
    .map(({ slug, name }) => ({ slug, name }));

  return (
    <>
      <PageHeader
        eyebrow="The journal"
        title="Articles"
        description="Encouragement, perspective, and practical ideas for building a stronger mindset and a more intentional life."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Articles", href: routes.articles },
        ]}
      />

      {articles.length === 0 ? (
        <Section>
          <EmptyState
            icon={BookOpen}
            title="Articles are on their way"
            description="We are preparing our first articles. Please check back soon."
          />
        </Section>
      ) : (
        <>
          {lead && (
            <Section spacing="sm" aria-labelledby="featured-heading">
              <h2 id="featured-heading" className="sr-only">
                Featured article
              </h2>
              <ArticleCard
                article={toCardData(lead)}
                variant="feature"
                headingLevel="h3"
                priority
              />
            </Section>
          )}
          <Section tone="cream" aria-labelledby="all-articles-heading">
            <SectionHeading
              id="all-articles-heading"
              title="Browse by topic"
              description="Choose a topic to focus on what matters most to you right now."
            />
            <div className="mt-10">
              <ArticleFilter articles={articles.map(toCardData)} topics={usedTopics} />
            </div>
          </Section>
        </>
      )}

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel />
      </Section>
    </>
  );
}

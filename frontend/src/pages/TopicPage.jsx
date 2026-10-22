import { ArrowRight, PenLine } from "lucide-react";
import { Link, useParams } from "react-router";
import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { Seo } from "@/components/seo/Seo";
import { TopicIcon } from "@/components/topics/TopicIcon";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { topicArticlesQuery } from "@/data/queries";
import { useArticles, useTopic, useTopics } from "@/hooks/useContent";
import { breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

export function TopicPage() {
  const { slug } = useParams();
  const topicState = useTopic(slug);
  const articlesState = useArticles(topicArticlesQuery(slug));
  const { data: allTopics } = useTopics();

  if (topicState.isNotFound) return <NotFoundPage />;
  if (topicState.isError)
    return (
      <Container className="py-20">
        <Seo title="Topic unavailable" path={routes.topic(slug)} noIndex />
        <ErrorState title="We couldn't load this topic" onRetry={topicState.retry} />
      </Container>
    );
  if (topicState.isLoading)
    return (
      <Container className="space-y-5 py-16" role="status" aria-label="Loading topic">
        <Skeleton className="h-12 w-2/3" />
        <Skeleton className="h-5 w-full max-w-2xl" />
        <CardGridSkeleton count={3} className="pt-8" />
      </Container>
    );

  const topic = topicState.data;
  const articles = articlesState.data ?? [];
  const otherTopics = (allTopics ?? []).filter((t) => t.slug !== topic.slug);
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    { name: topic.name, href: routes.topic(topic.slug) },
  ];

  return (
    <>
      <Seo
        title={topic.seo?.title ?? `${topic.name} Articles & Resources`}
        description={topic.seo?.description ?? topic.description}
        path={routes.topic(topic.slug)}
        jsonLd={breadcrumbJsonLd(crumbs)}
      />
      <PageHeader eyebrow="Topic" title={topic.name} description={topic.intro} breadcrumbs={crumbs}>
        <span className="inline-flex items-center gap-3 rounded-full bg-ivory/80 px-4 py-2 text-sm text-sage-800 shadow-soft">
          <TopicIcon name={topic.icon} className="size-4" />
          {topic.article_count} {topic.article_count === 1 ? "article" : "articles"}
        </span>
      </PageHeader>

      <Section aria-labelledby="topic-articles-heading">
        <SectionHeading id="topic-articles-heading" title={`Articles on ${topic.name}`} />
        <div className="mt-10">
          {articlesState.isLoading && <CardGridSkeleton count={3} />}
          {articlesState.isError && !articlesState.isNotFound && (
            <ErrorState onRetry={articlesState.retry} />
          )}
          {articlesState.data &&
            (articles.length > 0 ? (
              <ArticleGrid articles={articles} />
            ) : (
              <EmptyState
                icon={PenLine}
                title="New articles are being written"
                description={`We are preparing thoughtful articles on ${topic.name.toLowerCase()}. In the meantime, explore our latest writing.`}
                action={<ButtonLink to={routes.articles}>Browse all articles</ButtonLink>}
              />
            ))}
        </div>
      </Section>

      {otherTopics.length > 0 && (
        <Section tone="cream" spacing="sm" aria-labelledby="other-topics-heading">
          <h2 id="other-topics-heading" className="text-2xl font-medium">
            Explore other topics
          </h2>
          <ul className="mt-6 flex flex-wrap gap-3">
            {otherTopics.map((t) => (
              <li key={t.slug}>
                <Link
                  to={routes.topic(t.slug)}
                  className="inline-flex items-center gap-2 rounded-full border border-charcoal/15 bg-white/60 px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-sage-600 hover:text-sage-800"
                >
                  <TopicIcon name={t.icon} className="size-4 text-sage-700" />
                  {t.name}
                  <ArrowRight aria-hidden className="size-3.5" />
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

import { PenLine } from "lucide-react";
import { useParams } from "react-router";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { Seo } from "@/components/seo/Seo";
import { TopicIcon } from "@/components/topics/TopicIcon";
import { TopicLinks } from "@/components/topics/TopicLinks";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { Pagination } from "@/components/ui/Pagination";
import { CardGridSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { pageParam, topicArticlesQuery } from "@/data/queries";
import { useArticles, useTopic, useTopics } from "@/hooks/useContent";
import { breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

export function TopicPage() {
  const { slug, page: pageSegment } = useParams();
  const page = pageParam(pageSegment);
  const topicState = useTopic(slug);
  const articlesState = useArticles(topicArticlesQuery(slug, page ?? 1));
  const { data: allTopics } = useTopics();
  const pagination = articlesState.pagination;

  if (topicState.isNotFound || page === null) return <NotFoundPage />;
  // /topics/<slug>/page/N exists only for real pages.
  if (pageSegment !== undefined && pagination && page > pagination.total_pages) {
    return <NotFoundPage />;
  }
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
  const otherTopics = (allTopics ?? []).filter((t) => t.slug !== topic.slug && t.article_count > 0);
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    { name: topic.name, href: routes.topic(topic.slug) },
  ];
  // Page 1 opens with its newest story as the featured one; later pages are plain grids.
  const firstPage = (page ?? 1) === 1;
  const [lead, ...rest] = firstPage ? articles : [null, ...articles];
  const count = `${topic.article_count} ${topic.article_count === 1 ? "article" : "articles"}`;

  return (
    <>
      <Seo
        title={`${topic.seo?.title ?? `${topic.name} Articles & Resources`}${page > 1 ? ` (Page ${page})` : ""}`}
        description={topic.seo?.description ?? topic.description}
        path={routes.topicPage(topic.slug, page)}
        jsonLd={breadcrumbJsonLd(crumbs)}
      />
      <PageHeader
        eyebrow="Topic"
        title={topic.name}
        description={topic.intro}
        breadcrumbs={crumbs}
        size="wide"
        media={
          <span className="grid size-16 place-items-center rounded-2xl bg-sage-100 text-sage-700 sm:size-20">
            <TopicIcon name={topic.icon} className="size-7 sm:size-8" />
          </span>
        }
      >
        <p className="text-sm font-medium text-muted">
          {count}
          {page > 1 && pagination ? ` · Page ${page} of ${pagination.total_pages}` : ""}
        </p>
      </PageHeader>

      <Section aria-labelledby="topic-articles-heading" spacing="sm" size="wide">
        {articlesState.isLoading && <CardGridSkeleton count={3} />}
        {articlesState.isError && !articlesState.isNotFound && (
          <ErrorState onRetry={articlesState.retry} />
        )}
        {articlesState.data &&
          (articles.length > 0 ? (
            <>
              {lead && (
                <div className="mb-14">
                  <h2 id="topic-featured-heading" className="sr-only">
                    Featured in {topic.name}
                  </h2>
                  <ArticleCard article={lead} variant="feature" headingLevel="h3" priority />
                </div>
              )}
              {rest.length > 0 && (
                <>
                  <EditorialHeading
                    id="topic-articles-heading"
                    title={firstPage ? `Latest in ${topic.name}` : `More in ${topic.name}`}
                  />
                  <ArticleGrid articles={rest} className="mt-8" />
                </>
              )}
              {!rest.length && (
                <h2 id="topic-articles-heading" className="sr-only">
                  Articles on {topic.name}
                </h2>
              )}
              {pagination && (
                <Pagination
                  page={pagination.page}
                  totalPages={pagination.total_pages}
                  hrefFor={(p) => routes.topicPage(topic.slug, p)}
                  label={`${topic.name} article pages`}
                />
              )}
            </>
          ) : (
            <>
              <h2 id="topic-articles-heading" className="sr-only">
                Articles on {topic.name}
              </h2>
              <EmptyState
                icon={PenLine}
                title="New articles are being written"
                description={`We are preparing thoughtful articles on ${topic.name.toLowerCase()}. In the meantime, explore our latest writing.`}
                action={<ButtonLink to={routes.articles}>Browse all articles</ButtonLink>}
              />
            </>
          ))}
      </Section>

      {otherTopics.length > 0 && (
        <Section tone="cream" spacing="sm" size="wide" aria-labelledby="other-topics-heading">
          <EditorialHeading
            id="other-topics-heading"
            title="Explore other topics"
            size="sm"
            action={{ to: routes.articles, label: "All articles" }}
          />
          <TopicLinks topics={otherTopics} label="Other topics" className="mt-6" />
        </Section>
      )}
    </>
  );
}

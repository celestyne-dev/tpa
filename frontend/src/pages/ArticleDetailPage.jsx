import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { SponsoredLabel } from "@/components/articles/SponsoredLabel";
import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { Seo } from "@/components/seo/Seo";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { ErrorState } from "@/components/ui/ErrorState";
import { Notice } from "@/components/ui/Notice";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useArticle } from "@/hooks/useContent";
import { articleJsonLd, breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

export function ArticleDetailPage() {
  const { slug } = useParams();
  const { data, isLoading, isNotFound, isError, retry } = useArticle(slug);

  if (isNotFound) return <NotFoundPage />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Article unavailable" path={routes.article(slug)} noIndex />
        <ErrorState title="We couldn't load this article" onRetry={retry} />
      </Container>
    );
  if (isLoading || !data) return <ArticleSkeleton />;

  const { article, related } = data;
  const topic = article.topic;
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    ...(topic ? [{ name: topic.name, href: routes.topic(topic.slug) }] : []),
    { name: article.title, href: routes.article(article.slug) },
  ];

  return (
    <>
      <Seo
        title={article.seo?.title ?? article.title}
        description={article.seo?.description ?? article.excerpt}
        path={routes.article(article.slug)}
        canonicalUrl={article.canonical_url ?? undefined}
        noIndex={article.seo?.no_index}
        image={article.seo?.og_image ?? undefined}
        socialTitle={article.seo?.og_title}
        socialDescription={article.seo?.og_description}
        type="article"
        article={{
          publishedTime: article.published_at,
          modifiedTime: article.updated_at,
          section: topic?.name,
          authors: [article.author.name],
          tags: article.tags,
        }}
        jsonLd={[articleJsonLd(article), breadcrumbJsonLd(crumbs)]}
      />
      <article>
        <header className="bg-cream">
          <Container size="narrow" className="pt-10 pb-12 sm:pt-14">
            <Breadcrumbs items={crumbs} />
            <div className="mt-10 flex flex-wrap items-center gap-3">
              {topic && (
                <Link
                  to={routes.topic(topic.slug)}
                  className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase hover:underline hover:underline-offset-4"
                >
                  {topic.name}
                </Link>
              )}
              {article.source === "sample" && <Badge tone="neutral">Sample article</Badge>}
            </div>
            <h1 className="mt-4 text-4xl leading-[1.1] font-medium sm:text-5xl lg:text-[3.4rem]">
              {article.title}
            </h1>
            <SponsoredLabel sponsorship={article.sponsorship} className="mt-4" />
            {article.subtitle && (
              <p className="mt-5 font-serif text-xl text-muted italic sm:text-2xl">
                {article.subtitle}
              </p>
            )}
            <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-charcoal/10 pt-6">
              <p className="text-sm font-medium text-charcoal">By {article.author.name}</p>
              <ArticleMeta
                publishedAt={article.published_at}
                readingTimeMinutes={article.reading_time_minutes}
              />
            </div>
          </Container>
        </header>

        <div className="bg-gradient-to-b from-cream from-50% to-ivory to-50%">
          <Container>
            <div className="relative mx-auto aspect-[16/10] max-w-4xl overflow-hidden rounded-[var(--radius-card)] bg-beige shadow-soft">
              <ContentImage
                image={article.image}
                fill
                priority
                sizes={IMAGE_SIZES.hero}
                className="object-cover"
              />
            </div>
          </Container>
        </div>

        <Container size="narrow" className="py-12 sm:py-16">
          {article.source === "sample" && (
            <div className="mb-10">
              <Notice title="Sample editorial content">
                This article was written as sample content while the new Think Positive Always
                website is in development. It will be replaced or updated alongside our published
                articles.
              </Notice>
            </div>
          )}
          <ArticleBody blocks={article.body} sponsoredLinks={article.sponsorship?.links} />

          <footer className="mt-14 flex flex-col gap-6 border-t border-charcoal/10 pt-8 sm:flex-row sm:items-center sm:justify-between">
            {article.tags?.length > 0 && (
              <ul aria-label="Tags" className="flex flex-wrap gap-2">
                {article.tags.map((tag) => (
                  <li key={tag}>
                    <Badge tone="outline">{tag}</Badge>
                  </li>
                ))}
              </ul>
            )}
            <Link
              to={routes.articles}
              className="inline-flex items-center gap-2 text-sm font-semibold text-sage-700 hover:underline hover:underline-offset-4"
            >
              <ArrowLeft aria-hidden className="size-4" />
              Back to all articles
            </Link>
          </footer>
        </Container>
      </article>

      {related.length > 0 && (
        <Section tone="cream" aria-labelledby="related-heading">
          <SectionHeading
            id="related-heading"
            title="Keep reading"
            description="More perspectives you may find helpful."
          />
          <ArticleGrid articles={related} className="mt-10" />
        </Section>
      )}

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel source="article" sourceDetail={routes.article(slug)} />
      </Section>
    </>
  );
}

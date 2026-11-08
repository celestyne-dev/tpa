import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ArticleRows } from "@/components/articles/ArticleGrid";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { ArticleNav } from "@/components/articles/ArticleNav";
import { AuthorBox } from "@/components/articles/AuthorBox";
import { ShareLinks } from "@/components/articles/ShareLinks";
import { SponsoredLabel } from "@/components/articles/SponsoredLabel";
import { Seo } from "@/components/seo/Seo";
import { ArticleSidebar } from "@/components/sidebar/ArticleSidebar";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { ErrorState } from "@/components/ui/ErrorState";
import { Notice } from "@/components/ui/Notice";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useArticle } from "@/hooks/useContent";
import { articleJsonLd, breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

/** The byline: author (linked to their page when they have one), dates and reading time. */
function Byline({ article }) {
  const { author } = article;
  const portrait = article.author_profile?.image;
  return (
    <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-3 border-y border-charcoal/10 py-4">
      {portrait?.src && author.has_page && (
        <span className="relative block size-11 shrink-0 overflow-hidden rounded-full bg-beige">
          <ContentImage image={portrait} fill sizes="44px" className="object-cover" />
        </span>
      )}
      <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4">
        <p className="text-sm font-medium text-charcoal">
          By{" "}
          {author.has_page ? (
            <Link
              to={routes.author(author.slug)}
              rel="author"
              className="underline-offset-4 hover:text-sage-700 hover:underline"
            >
              {author.name}
            </Link>
          ) : (
            author.name
          )}
        </p>
        <ArticleMeta
          publishedAt={article.published_at}
          updatedAt={article.content_modified_at}
          readingTimeMinutes={article.reading_time_minutes}
        />
      </div>
    </div>
  );
}

/**
 * The reading page. Wide screens: the article (title, byline, image, body, sharing,
 * author, related and previous/next) with the article sidebar beside it. Phones and
 * tablets: the article full width with the sidebar sections below. Nothing is sticky;
 * the sidebar comes with the article (and is prerendered), so nothing shifts.
 */
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

  const { article, related, adjacent, sidebar } = data;
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
          // Only a material update moves the modified time (never an ordinary save).
          modifiedTime: article.content_modified_at ?? undefined,
          section: topic?.name,
          authors: [article.author.name],
          tags: article.tags,
        }}
        jsonLd={[articleJsonLd(article), breadcrumbJsonLd(crumbs)]}
      />
      <Container size="wide" className="pt-8 pb-16 sm:pt-10 sm:pb-24">
        <Breadcrumbs items={crumbs} />
        <div className="mt-8 lg:grid lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_21rem] xl:gap-16">
          <article aria-labelledby="article-title" className="min-w-0">
            <header>
              <div className="flex flex-wrap items-center gap-3">
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
              <h1
                id="article-title"
                className="mt-4 text-4xl leading-[1.1] font-medium text-balance sm:text-5xl lg:text-[3.25rem]"
              >
                {article.title}
              </h1>
              <SponsoredLabel sponsorship={article.sponsorship} className="mt-4" />
              {article.subtitle && (
                <p className="mt-5 font-serif text-xl text-muted italic sm:text-2xl">
                  {article.subtitle}
                </p>
              )}
              <Byline article={article} />
            </header>

            <div className="relative mt-8 aspect-[16/10] overflow-hidden rounded-[var(--radius-card)] bg-beige">
              <ContentImage
                image={article.image}
                fill
                priority
                sizes="(min-width: 1280px) 860px, (min-width: 1024px) 62vw, 100vw"
                className="object-cover"
              />
            </div>

            <div className="mt-10 max-w-[46rem] sm:mt-12">
              {article.source === "sample" && (
                <div className="mb-10">
                  <Notice title="Sample editorial content">
                    This article was written as sample content while the new Think Positive Always
                    website is in development. It will be replaced or updated alongside our
                    published articles.
                  </Notice>
                </div>
              )}
              <ArticleBody blocks={article.body} sponsoredLinks={article.sponsorship?.links} />

              <footer className="mt-14 space-y-8 border-t border-charcoal/10 pt-8">
                {article.tags?.length > 0 && (
                  <ul aria-label="Tags" className="flex flex-wrap gap-2">
                    {article.tags.map((tag) => (
                      <li key={tag}>
                        <Badge tone="outline">{tag}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
                <ShareLinks
                  title={article.title}
                  path={routes.article(article.slug)}
                  canonicalUrl={article.canonical_url}
                />
                <AuthorBox author={article.author} profile={article.author_profile} />
              </footer>
            </div>

            {related.length > 0 && (
              <section aria-labelledby="related-heading" className="mt-16 max-w-[46rem]">
                <EditorialHeading
                  id="related-heading"
                  title="Related articles"
                  action={
                    topic ? { to: routes.topic(topic.slug), label: `More in ${topic.name}` } : null
                  }
                />
                <ArticleRows articles={related} className="mt-6" />
              </section>
            )}

            <div className="mt-14 max-w-[46rem] space-y-6">
              <ArticleNav previous={adjacent?.previous} next={adjacent?.next} />
              <Link
                to={routes.articles}
                className="inline-flex items-center gap-2 text-sm font-semibold text-sage-700 hover:underline hover:underline-offset-4"
              >
                <ArrowLeft aria-hidden className="size-4" />
                Back to all articles
              </Link>
            </div>
          </article>

          <ArticleSidebar
            sections={sidebar}
            className="mt-16 border-t border-charcoal/10 pt-12 lg:mt-0 lg:border-t-0 lg:pt-0"
          />
        </div>
      </Container>
    </>
  );
}

import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ArticleGrid, ArticleRows } from "@/components/articles/ArticleGrid";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { ShareLinks } from "@/components/articles/ShareLinks";
import { ArticleNewsletterCta } from "@/components/newsletter/ArticleNewsletterCta";
import { Seo } from "@/components/seo/Seo";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { ErrorState } from "@/components/ui/ErrorState";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { useQuoteCollection } from "@/hooks/useContent";
import { absoluteUrl } from "@/utils/format";
import { articleJsonLd, breadcrumbJsonLd } from "@/utils/structuredData";
import { CmsRoute } from "./CmsPage";
import { NotFoundPage } from "./NotFoundPage";

/**
 * One quote collection (/quotes/:slug): the introduction, the numbered quotes with images
 * between them, the editor's reflections, then related articles and collections. The
 * whole collection is one page (images are never pages of their own).
 */
export function QuoteCollectionView({ collection, relatedArticles = [], relatedCollections = [] }) {
  const topic = collection.topic;
  const path = routes.quote(collection.slug);
  const pinPage = collection.canonical_url || absoluteUrl(path, siteConfig.url);
  return (
    <Container size="wide" className="pt-8 pb-16 sm:pt-10 sm:pb-24">
      <Breadcrumbs
        items={[
          { name: "Home", href: routes.home },
          { name: "Quotes", href: routes.quotes },
          { name: collection.title, href: path },
        ]}
      />
      <article aria-labelledby="collection-title" className="mx-auto mt-8 max-w-[46rem]">
        <header>
          {topic && (
            <Link
              to={`${routes.quotes}?topic=${encodeURIComponent(topic.slug)}`}
              className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase hover:underline hover:underline-offset-4"
            >
              {topic.name} quotes
            </Link>
          )}
          <h1
            id="collection-title"
            className="mt-4 text-4xl leading-[1.1] font-medium text-balance sm:text-5xl"
          >
            {collection.title}
          </h1>
          {(collection.subtitle || collection.excerpt) && (
            <p className="mt-5 font-serif text-xl text-muted italic sm:text-2xl">
              {collection.subtitle || collection.excerpt}
            </p>
          )}
          <div className="mt-6 border-y border-charcoal/10 py-4">
            <ArticleMeta
              publishedAt={collection.published_at}
              updatedAt={collection.content_modified_at}
              readingTimeMinutes={collection.reading_time_minutes}
            />
          </div>
        </header>
        {collection.image?.src && (
          <div className="relative mt-8 aspect-[16/10] overflow-hidden rounded-[var(--radius-card)] bg-beige">
            <ContentImage
              image={collection.image}
              fill
              priority
              sizes="(min-width: 768px) 736px, 100vw"
              className="object-cover"
            />
          </div>
        )}
        <div className="mt-10">
          <ArticleBody blocks={collection.body ?? []} variant="quotes" pinPage={pinPage} />
        </div>
        <footer className="mt-14 border-t border-charcoal/10 pt-8">
          <ShareLinks
            title={collection.title}
            path={path}
            canonicalUrl={collection.canonical_url}
          />
        </footer>
        <ArticleNewsletterCta className="mt-14" />
        {relatedArticles.length > 0 && (
          <section aria-labelledby="related-articles-heading" className="mt-16">
            <EditorialHeading
              id="related-articles-heading"
              title="Related articles"
              action={
                topic ? { to: routes.topic(topic.slug), label: `More on ${topic.name}` } : null
              }
            />
            <ArticleRows articles={relatedArticles} className="mt-6" />
          </section>
        )}
      </article>
      {relatedCollections.length > 0 && (
        <section aria-labelledby="related-collections-heading" className="mt-16">
          <EditorialHeading
            id="related-collections-heading"
            title="More quote collections"
            action={{ to: routes.quotes, label: "All collections" }}
          />
          <ArticleGrid articles={relatedCollections} className="mt-6" />
        </section>
      )}
      <div className="mx-auto mt-14 max-w-[46rem]">
        <Link
          to={routes.quotes}
          className="inline-flex items-center gap-2 text-sm font-semibold text-sage-700 hover:underline hover:underline-offset-4"
        >
          <ArrowLeft aria-hidden className="size-4" />
          Back to all quote collections
        </Link>
      </div>
    </Container>
  );
}

export function QuoteCollectionPage() {
  const { slug } = useParams();
  const { data, isLoading, isNotFound, isError, retry } = useQuoteCollection(slug);
  // Not a collection: a CMS page published at this path (if any), otherwise a 404.
  if (isNotFound) return <CmsRoute />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Quote collection unavailable" path={routes.quote(slug)} noIndex />
        <ErrorState title="We couldn't load this collection" onRetry={retry} />
      </Container>
    );
  if (isLoading || !data) return <ArticleSkeleton />;
  const { collection } = data;
  const path = routes.quote(collection.slug);
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Quotes", href: routes.quotes },
    { name: collection.title, href: path },
  ];
  return (
    <>
      <Seo
        title={collection.seo?.title ?? collection.title}
        description={collection.seo?.description ?? collection.excerpt}
        path={path}
        canonicalUrl={collection.canonical_url ?? undefined}
        noIndex={collection.seo?.no_index}
        image={collection.seo?.og_image ?? undefined}
        socialTitle={collection.seo?.og_title}
        socialDescription={collection.seo?.og_description}
        type="article"
        article={{
          publishedTime: collection.published_at,
          modifiedTime: collection.content_modified_at ?? undefined,
          section: collection.topic?.name,
          authors: [collection.author?.name].filter(Boolean),
          tags: collection.tags,
        }}
        jsonLd={[articleJsonLd(collection), breadcrumbJsonLd(crumbs)]}
      />
      <QuoteCollectionView
        collection={collection}
        relatedArticles={data.related_articles ?? []}
        relatedCollections={data.related_collections ?? []}
      />
    </>
  );
}

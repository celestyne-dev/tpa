import { useParams } from "react-router";
import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { pageParam } from "@/data/queries";
import { useAuthor } from "@/hooks/useContent";
import { authorPageJsonLd, breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

/**
 * A writer's page: name, bio and portrait as recorded in Admin › Authors, and their
 * published articles. Only authors marked as real people with a bio have one.
 */
export function AuthorPage() {
  const { slug, page: pageSegment } = useParams();
  const page = pageParam(pageSegment);
  const { data, isLoading, isNotFound, isError, retry, pagination } = useAuthor(slug, page ?? 1);

  if (page === null || isNotFound) return <NotFoundPage />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Author unavailable" path={routes.author(slug)} noIndex />
        <ErrorState title="We couldn't load this page" onRetry={retry} />
      </Container>
    );
  if (isLoading || !data)
    return (
      <Container className="space-y-5 py-16" role="status" aria-label="Loading author">
        <Skeleton className="h-12 w-2/3" />
        <CardGridSkeleton count={3} className="pt-8" />
      </Container>
    );

  if (pageSegment !== undefined && pagination && page > pagination.total_pages) {
    return <NotFoundPage />;
  }
  const { author, articles } = data;
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    { name: author.name, href: routes.author(author.slug) },
  ];
  const description = author.bio.length > 160 ? `${author.bio.slice(0, 157).trimEnd()}…` : author.bio;

  return (
    <>
      <Seo
        title={page > 1 ? `${author.name} (Page ${page})` : author.name}
        description={description}
        path={routes.authorPage(author.slug, page)}
        jsonLd={[authorPageJsonLd(author), breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader eyebrow="Author" title={author.name} breadcrumbs={crumbs}>
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
          {author.image?.src && (
            <span className="relative block size-24 shrink-0 overflow-hidden rounded-full bg-beige">
              <ContentImage image={author.image} fill sizes="96px" className="object-cover" />
            </span>
          )}
          <p className="max-w-2xl text-lg leading-relaxed text-charcoal">{author.bio}</p>
        </div>
      </PageHeader>
      <Section aria-labelledby="author-articles-heading">
        <SectionHeading
          id="author-articles-heading"
          title={`Articles by ${author.name}`}
          description={`${author.article_count} ${author.article_count === 1 ? "article" : "articles"}`}
        />
        <ArticleGrid articles={articles} className="mt-10" />
        {pagination && (
          <Pagination
            page={pagination.page}
            totalPages={pagination.total_pages}
            hrefFor={(p) => routes.authorPage(author.slug, p)}
            label={`Pages of articles by ${author.name}`}
          />
        )}
      </Section>
    </>
  );
}

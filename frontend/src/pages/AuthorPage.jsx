import { useParams } from "react-router";
import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { Section } from "@/components/ui/Section";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
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
    { name: "Authors", href: routes.authors },
    { name: author.name, href: routes.author(author.slug) },
  ];
  const description =
    author.bio.length > 160 ? `${author.bio.slice(0, 157).trimEnd()}…` : author.bio;
  const count = `${author.article_count} published ${author.article_count === 1 ? "article" : "articles"}`;

  return (
    <>
      <Seo
        title={page > 1 ? `${author.name} (Page ${page})` : author.name}
        description={description}
        path={routes.authorPage(author.slug, page)}
        jsonLd={[authorPageJsonLd(author), breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader
        eyebrow="Author"
        title={author.name}
        breadcrumbs={crumbs}
        size="wide"
        description={<p className="leading-relaxed text-ink">{author.bio}</p>}
        media={
          author.image?.src && (
            <span className="relative block size-24 overflow-hidden rounded-full bg-beige ring-4 ring-ivory sm:size-32">
              <ContentImage image={author.image} fill sizes="128px" className="object-cover" />
            </span>
          )
        }
      >
        <p className="text-sm font-medium text-muted">
          {count}
          {page > 1 && pagination ? ` · Page ${page} of ${pagination.total_pages}` : ""}
        </p>
      </PageHeader>
      <Section aria-labelledby="author-articles-heading" spacing="sm" size="wide">
        <EditorialHeading
          id="author-articles-heading"
          title={`Articles by ${author.name}`}
          action={{ to: routes.authors, label: "All authors" }}
        />
        <ArticleGrid articles={articles} className="mt-8" />
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

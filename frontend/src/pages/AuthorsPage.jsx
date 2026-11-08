import { ArrowRight, PenLine } from "lucide-react";
import { Link } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ContentImage } from "@/components/ui/ContentImage";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useAuthors } from "@/hooks/useContent";
import { breadcrumbJsonLd } from "@/utils/structuredData";

const DESCRIPTION =
  "Meet the writers behind Think Positive Always and read their articles on mindset, confidence and personal growth.";

function AuthorCard({ author }) {
  const count = `${author.article_count} ${author.article_count === 1 ? "article" : "articles"}`;
  return (
    <Card interactive className="group flex h-full flex-col p-6 sm:p-7">
      <div className="flex items-center gap-4">
        <span className="relative grid size-16 shrink-0 place-items-center overflow-hidden rounded-full bg-sage-100 font-serif text-2xl text-sage-800">
          {author.image?.src ? (
            <ContentImage image={author.image} fill sizes="64px" className="object-cover" />
          ) : (
            <span aria-hidden>{author.name.charAt(0)}</span>
          )}
        </span>
        <div className="min-w-0">
          <h2 className="text-xl font-medium">
            <Link
              to={routes.author(author.slug)}
              className="after:absolute after:inset-0 after:rounded-[var(--radius-card)] group-hover:text-sage-800 focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-offset-2 focus-visible:after:outline-sage-600"
            >
              {author.name}
            </Link>
          </h2>
          <p className="mt-1 text-sm text-muted">{count}</p>
        </div>
      </div>
      {author.bio && <p className="mt-5 line-clamp-4 flex-1 text-muted">{author.bio}</p>}
      <span
        aria-hidden
        className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-sage-700"
      >
        Read their articles
        <ArrowRight className="size-4 transition-transform group-hover:translate-x-1 motion-reduce:group-hover:translate-x-0" />
      </span>
    </Card>
  );
}

/**
 * The writers who have an author page (real people with a bio and published articles,
 * as recorded in Admin › Authors). Nothing is listed for anyone else, and nothing is
 * made up: with no author pages the index says so and is kept out of search engines.
 */
export function AuthorsPage() {
  const { data: authors, isLoading, isError, retry } = useAuthors();
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Authors", href: routes.authors },
  ];
  const empty = Boolean(authors) && authors.length === 0;

  return (
    <>
      <Seo
        title="Our Authors"
        description={DESCRIPTION}
        path={routes.authors}
        noIndex={empty}
        jsonLd={breadcrumbJsonLd(crumbs)}
      />
      <PageHeader
        eyebrow="The writers"
        title="Authors"
        description="The people behind the articles: their perspective, experience and writing."
        breadcrumbs={crumbs}
        size="wide"
      />
      <Section spacing="sm" size="wide" aria-label="Authors">
        {isLoading && <CardGridSkeleton count={3} />}
        {isError && <ErrorState onRetry={retry} />}
        {authors &&
          (authors.length > 0 ? (
            <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {authors.map((author) => (
                <li key={author.slug}>
                  <AuthorCard author={author} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={PenLine}
              headingLevel="h2"
              title="Author profiles aren't published yet"
              description="There are no author profiles to show right now."
              action={<ButtonLink to={routes.articles}>Browse all articles</ButtonLink>}
            />
          ))}
      </Section>
    </>
  );
}

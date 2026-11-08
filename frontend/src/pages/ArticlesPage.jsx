import { ArticleFilter } from "@/components/articles/ArticleFilter";
import { LeadStories } from "@/components/articles/LeadStories";
import { NewsletterPromo } from "@/components/newsletter/NewsletterPromo";
import { Seo } from "@/components/seo/Seo";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { Link, useParams, useSearchParams } from "react-router";
import { routes } from "@/config/navigation";
import { FEATURED_QUERY, articleListQuery, pageParam } from "@/data/queries";
import { useArticles, useTopics } from "@/hooks/useContent";
import { NotFoundPage } from "./NotFoundPage";

const TITLE = "Articles on Mindset, Confidence & Personal Growth";
const DESCRIPTION =
  "Read thoughtful articles on positive mindset, personal growth, confidence, resilience, boundaries, and intentional living from Think Positive Always.";

export function ArticlesPage() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const page = pageParam(params.page);
  const { data: featured } = useArticles(FEATURED_QUERY);
  const { data: topics } = useTopics();
  const list = useArticles(articleListQuery(page ?? 1));
  // /articles/page/N exists only for real pages; anything else is a genuine 404.
  const outOfRange =
    page === null ||
    (params.page !== undefined && list.pagination && page > list.pagination.total_pages);
  if (outOfRange && !searchParams.get("topic")) return <NotFoundPage />;
  // Page 1 opens with the featured stories (a lead and up to three alongside).
  const leads = page === 1 ? (featured ?? []).slice(0, 4) : [];
  // Only offer filters for topics that have articles.
  const usedTopics = (topics ?? []).filter((t) => t.article_count > 0);
  // A compact link to /newsletter (no form) after the first group of articles: the
  // featured stories when they're shown, otherwise the article list.

  return (
    <>
      <Seo
        title={page > 1 ? `${TITLE} (Page ${page})` : TITLE}
        description={DESCRIPTION}
        path={routes.articlesPage(page)}
      />
      <PageHeader
        eyebrow="The journal"
        title="Articles"
        size="wide"
        description="Encouragement, perspective, and practical ideas for building a stronger mindset and a more intentional life."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Articles", href: routes.articles },
        ]}
      >
        {usedTopics.length > 0 && (
          // One swipeable row on phones (so the articles start on the first screen); wraps
          // from the small breakpoint up.
          <nav aria-label="Browse by topic" className="-mx-5 sm:mx-0">
            <ul className="flex [scrollbar-width:none] gap-2 overflow-x-auto px-5 pb-1 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
              {usedTopics.map((t) => (
                <li key={t.slug} className="shrink-0">
                  <Link
                    to={routes.topic(t.slug)}
                    className="inline-flex rounded-full border border-charcoal/15 bg-white/60 px-3.5 py-1.5 text-sm font-medium whitespace-nowrap text-ink transition-colors hover:border-sage-600 hover:text-sage-800"
                  >
                    {t.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </PageHeader>

      {leads.length > 0 && (
        <Section spacing="sm" size="wide" aria-labelledby="featured-heading">
          <h2 id="featured-heading" className="sr-only">
            Featured articles
          </h2>
          <LeadStories articles={leads} priority />
        </Section>
      )}
      {leads.length > 0 && <NewsletterPromo className="bg-ivory pb-12 sm:pb-16" />}

      <Section
        tone={leads.length > 0 ? "cream" : "ivory"}
        spacing="sm"
        size="wide"
        aria-labelledby="all-articles-heading"
      >
        <EditorialHeading
          id="all-articles-heading"
          title={page > 1 ? `Latest articles · Page ${page}` : "Latest articles"}
          description="Choose a topic to focus on what matters most to you right now."
        />
        <div className="mt-8">
          <ArticleFilter topics={usedTopics} page={page} />
        </div>
      </Section>
      {leads.length === 0 && <NewsletterPromo className="bg-ivory py-12 sm:py-16" />}
    </>
  );
}

import { Compass } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { TopicCard } from "@/components/topics/TopicCard";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes, topicGroupAnchor } from "@/config/navigation";
import { useTopics } from "@/hooks/useContent";
import { topicSlugOf, useNavigation } from "@/hooks/useNavigation";
import { breadcrumbJsonLd } from "@/utils/structuredData";

const TITLE = "Explore topics";
const DESCRIPTION =
  "Browse Think Positive Always by topic: mindset, wellbeing, relationships, career and personal growth.";
export const MORE_TOPICS = "More topics";

/**
 * The header's topic groups (Mindset, Wellbeing, …) as arranged in Admin › Navigation,
 * each with its published topics. Topics no group lists come after, under "More topics".
 * Only topics with published articles are shown.
 */
export function groupTopics(menu, topics) {
  const bySlug = new Map(topics.filter((t) => t.article_count > 0).map((t) => [t.slug, t]));
  const placed = new Set();
  const groups = [];
  for (const item of menu) {
    const slugs = (item.children ?? []).map((c) => topicSlugOf(c.href)).filter(Boolean);
    const list = slugs.filter((s) => bySlug.has(s) && !placed.has(s)).map((s) => bySlug.get(s));
    if (!list.length) continue;
    list.forEach((t) => placed.add(t.slug));
    groups.push({ label: item.label, anchor: topicGroupAnchor(item.label), topics: list });
  }
  const rest = [...bySlug.values()].filter((t) => !placed.has(t.slug));
  if (rest.length) {
    groups.push({ label: MORE_TOPICS, anchor: topicGroupAnchor(MORE_TOPICS), topics: rest });
  }
  return groups;
}

export function TopicsPage() {
  const { data: topics, isLoading, isError, retry } = useTopics();
  const { primary } = useNavigation();
  const { hash } = useLocation();
  const groups = topics ? groupTopics(primary, topics) : [];
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Topics", href: routes.topics },
  ];

  // Links such as /topics#wellbeing open at that group, also after in-app navigation.
  const ready = groups.length > 0;
  useEffect(() => {
    if (!ready || !hash) return undefined;
    const frame = requestAnimationFrame(() => {
      document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.({
        block: "start",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [hash, ready]);

  return (
    <>
      <Seo
        title={TITLE}
        description={DESCRIPTION}
        path={routes.topics}
        noIndex={Boolean(topics) && !ready}
        jsonLd={[
          breadcrumbJsonLd(crumbs),
          {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            name: TITLE,
            description: DESCRIPTION,
          },
        ]}
      />
      <PageHeader
        eyebrow="Explore"
        title={TITLE}
        description="Find encouragement for the part of life you are working on now."
        breadcrumbs={crumbs}
        size="wide"
      />
      <Section spacing="sm" size="wide" aria-label="Topics">
        {isLoading && <CardGridSkeleton count={6} />}
        {isError && <ErrorState onRetry={retry} />}
        {topics && !ready && (
          <EmptyState
            icon={Compass}
            headingLevel="h2"
            title="Topics are on their way"
            description="There are no topics with articles to show right now."
            action={<ButtonLink to={routes.articles}>Browse all articles</ButtonLink>}
          />
        )}
        {ready && (
          <>
            {groups.length > 1 && (
              <nav aria-label="Topic groups" className="-mx-1 mb-10 overflow-x-auto pb-1">
                <ul className="flex gap-2 px-1">
                  {groups.map((group) => (
                    <li key={group.anchor} className="shrink-0">
                      <Link
                        to={`${routes.topics}#${group.anchor}`}
                        className="inline-flex min-h-11 items-center rounded-full border border-charcoal/10 bg-ivory px-4 text-sm font-medium text-charcoal transition-colors hover:border-sage-600 hover:text-sage-800"
                      >
                        {group.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
            <div className="space-y-14">
              {groups.map((group) => (
                <section
                  key={group.anchor}
                  id={group.anchor}
                  aria-labelledby={`${group.anchor}-heading`}
                  className="scroll-mt-28"
                >
                  <h2 id={`${group.anchor}-heading`} className="text-3xl font-medium">
                    {group.label}
                  </h2>
                  <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {group.topics.map((topic) => (
                      <li key={topic.slug}>
                        <TopicCard topic={topic} compact showCount />
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </>
        )}
      </Section>
    </>
  );
}

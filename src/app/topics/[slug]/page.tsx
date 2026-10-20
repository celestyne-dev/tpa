import { ArrowRight, PenLine } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArticleGrid } from "@/components/articles/article-grid";
import { toCardData } from "@/components/articles/to-card-data";
import { TopicIcon } from "@/components/topics/topic-icon";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { JsonLd } from "@/components/ui/json-ld";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import { getArticles, getTopicBySlug, getTopics } from "@/lib/content";
import { buildMetadata } from "@/lib/seo";
import { breadcrumbJsonLd } from "@/lib/structured-data";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export async function generateStaticParams() {
  const topics = await getTopics();
  return topics.map((t) => ({ slug: t.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const topic = await getTopicBySlug(slug);
  if (!topic) return {};
  return buildMetadata({
    title: topic.seo?.title ?? `${topic.name} Articles & Resources`,
    description: topic.seo?.description ?? topic.description,
    path: routes.topic(topic.slug),
  });
}

export default async function TopicPage({ params }: Props) {
  const { slug } = await params;
  const topic = await getTopicBySlug(slug);
  if (!topic) notFound();

  const [articles, allTopics] = await Promise.all([
    getArticles({ topic: topic.slug }),
    getTopics(),
  ]);
  const otherTopics = allTopics.filter((t) => t.slug !== topic.slug);
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    { name: topic.name, href: routes.topic(topic.slug) },
  ];

  return (
    <>
      <PageHeader eyebrow="Topic" title={topic.name} description={topic.intro} breadcrumbs={crumbs}>
        <span className="inline-flex items-center gap-3 rounded-full bg-ivory/80 px-4 py-2 text-sm text-sage-800 shadow-soft">
          <TopicIcon name={topic.icon} className="size-4" />
          {articles.length} {articles.length === 1 ? "article" : "articles"}
        </span>
      </PageHeader>

      <Section aria-labelledby="topic-articles-heading">
        <SectionHeading id="topic-articles-heading" title={`Articles on ${topic.name}`} />
        <div className="mt-10">
          {articles.length > 0 ? (
            <ArticleGrid articles={articles.map(toCardData)} />
          ) : (
            <EmptyState
              icon={PenLine}
              title="New articles are being written"
              description={`We are preparing thoughtful articles on ${topic.name.toLowerCase()}. In the meantime, explore our latest writing.`}
              action={<ButtonLink href={routes.articles}>Browse all articles</ButtonLink>}
            />
          )}
        </div>
      </Section>

      <Section tone="cream" spacing="sm" aria-labelledby="other-topics-heading">
        <h2 id="other-topics-heading" className="text-2xl font-medium">
          Explore other topics
        </h2>
        <ul className="mt-6 flex flex-wrap gap-3">
          {otherTopics.map((t) => (
            <li key={t.slug}>
              <Link
                href={routes.topic(t.slug)}
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

      <JsonLd data={breadcrumbJsonLd(crumbs)} />
    </>
  );
}

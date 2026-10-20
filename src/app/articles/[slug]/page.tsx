import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArticleBody } from "@/components/articles/article-body";
import { ArticleGrid } from "@/components/articles/article-grid";
import { ArticleMeta } from "@/components/articles/article-meta";
import { toCardData } from "@/components/articles/to-card-data";
import { NewsletterPanel } from "@/components/newsletter/newsletter-panel";
import { Badge } from "@/components/ui/badge";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";
import { Container } from "@/components/ui/container";
import { ContentImage } from "@/components/ui/content-image";
import { Notice } from "@/components/ui/draft-notice";
import { JsonLd } from "@/components/ui/json-ld";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import {
  getArticleBySlug,
  getArticleSlugs,
  getRelatedArticles,
  getTopicBySlug,
} from "@/lib/content";
import { buildMetadata } from "@/lib/seo";
import { articleJsonLd, breadcrumbJsonLd } from "@/lib/structured-data";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = await getArticleSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) return {};
  const topic = await getTopicBySlug(article.topicSlug);
  return buildMetadata({
    title: article.seo?.title ?? article.title,
    description: article.seo?.description ?? article.excerpt,
    path: routes.article(article.slug),
    type: "article",
    publishedTime: article.publishedAt,
    modifiedTime: article.updatedAt,
    authors: [article.author.name],
    section: topic?.name,
    tags: article.tags,
    canonicalUrl: article.seo?.canonicalUrl ?? article.legacy?.canonicalUrl,
    noIndex: article.seo?.noIndex,
    image: article.seo?.ogImage,
  });
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) notFound();

  const [topic, related] = await Promise.all([
    getTopicBySlug(article.topicSlug),
    getRelatedArticles(article, 3),
  ]);

  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Articles", href: routes.articles },
    ...(topic ? [{ name: topic.name, href: routes.topic(topic.slug) }] : []),
    { name: article.title, href: routes.article(article.slug) },
  ];

  return (
    <>
      <article>
        <header className="bg-cream">
          <Container size="narrow" className="pt-10 pb-12 sm:pt-14">
            <Breadcrumbs items={crumbs} />
            <div className="mt-10 flex flex-wrap items-center gap-3">
              {topic && (
                <Link
                  href={routes.topic(topic.slug)}
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
            {article.subtitle && (
              <p className="mt-5 font-serif text-xl text-muted italic sm:text-2xl">
                {article.subtitle}
              </p>
            )}
            <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-charcoal/10 pt-6">
              <p className="text-sm font-medium text-charcoal">By {article.author.name}</p>
              <ArticleMeta
                publishedAt={article.publishedAt}
                readingTimeMinutes={article.readingTimeMinutes}
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
                sizes="(min-width: 1024px) 896px, 100vw"
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
          <ArticleBody blocks={article.body} />

          <footer className="mt-14 flex flex-col gap-6 border-t border-charcoal/10 pt-8 sm:flex-row sm:items-center sm:justify-between">
            {article.tags && article.tags.length > 0 && (
              <ul aria-label="Tags" className="flex flex-wrap gap-2">
                {article.tags.map((tag) => (
                  <li key={tag}>
                    <Badge tone="outline">{tag}</Badge>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href={routes.articles}
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
          <ArticleGrid articles={related.map(toCardData)} className="mt-10" />
        </Section>
      )}

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel />
      </Section>

      <JsonLd data={[articleJsonLd(article, topic ?? undefined), breadcrumbJsonLd(crumbs)]} />
    </>
  );
}

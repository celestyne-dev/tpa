import { articles as localArticles } from "@/data/articles";
import { estimateReadingTime } from "@/lib/reading-time";
import type { Article } from "@/types";

/**
 * Article repository. All page code reads articles through these async
 * functions so the local data source can be swapped for Supabase/CMS
 * queries without touching components or routes.
 */

export type ArticleWithMeta = Article & { readingTimeMinutes: number };

function withMeta(article: Article): ArticleWithMeta {
  return {
    ...article,
    readingTimeMinutes: article.readingTimeMinutes ?? estimateReadingTime(article.body),
  };
}

function published(): ArticleWithMeta[] {
  return localArticles
    .filter((a) => a.status === "published")
    .map(withMeta)
    .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
}

export async function getArticles(options: { topic?: string; limit?: number } = {}) {
  const list = published().filter(
    (a) =>
      !options.topic ||
      a.topicSlug === options.topic ||
      a.secondaryTopicSlugs?.includes(options.topic),
  );
  return options.limit ? list.slice(0, options.limit) : list;
}

export async function getFeaturedArticles(limit = 3) {
  return published()
    .filter((a) => a.featured)
    .slice(0, limit);
}

export async function getArticleBySlug(slug: string) {
  return published().find((a) => a.slug === slug) ?? null;
}

export async function getArticleSlugs() {
  return published().map((a) => a.slug);
}

/** Related = same primary topic first, then shared secondary topics, then recent. */
export async function getRelatedArticles(article: Article, limit = 3) {
  const others = published().filter((a) => a.id !== article.id);
  const score = (a: Article) => {
    if (a.topicSlug === article.topicSlug) return 3;
    const topicsA = [a.topicSlug, ...(a.secondaryTopicSlugs ?? [])];
    const topicsB = [article.topicSlug, ...(article.secondaryTopicSlugs ?? [])];
    return topicsA.some((t) => topicsB.includes(t)) ? 2 : 0;
  };
  return others
    .map((a, index) => ({ a, s: score(a), index }))
    .sort((x, y) => y.s - x.s || x.index - y.index)
    .slice(0, limit)
    .map(({ a }) => a);
}

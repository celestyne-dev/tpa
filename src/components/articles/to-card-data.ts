import type { ArticleWithMeta } from "@/lib/content/articles";
import { topicMap } from "@/lib/content/topics";
import type { ArticleCardData } from "./article-card";

export function toCardData(article: ArticleWithMeta): ArticleCardData {
  return {
    slug: article.slug,
    title: article.title,
    excerpt: article.excerpt,
    publishedAt: article.publishedAt,
    readingTimeMinutes: article.readingTimeMinutes,
    image: article.image,
    topicSlug: article.topicSlug,
    topicName: topicMap.get(article.topicSlug)?.name ?? "Articles",
    source: article.source,
  };
}

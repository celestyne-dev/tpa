import { getArticleBySlug, getArticleSlugs, getTopicBySlug } from "@/lib/content";
import { ogSize, renderOgImage } from "../../og-template";

export const size = ogSize;
export const contentType = "image/png";
export const alt = "Think Positive Always article";

export async function generateStaticParams() {
  const slugs = await getArticleSlugs();
  return slugs.map((slug) => ({ slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  const topic = article ? await getTopicBySlug(article.topicSlug) : null;
  return renderOgImage({
    eyebrow: topic?.name ?? "Articles",
    title: article?.title ?? "Think Positive Always",
  });
}

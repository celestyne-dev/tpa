import type { MetadataRoute } from "next";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { getArticles, getTopics } from "@/lib/content";

const staticRoutes: {
  path: string;
  priority: number;
  changeFrequency: "daily" | "weekly" | "monthly" | "yearly";
}[] = [
  { path: routes.home, priority: 1, changeFrequency: "weekly" },
  { path: routes.articles, priority: 0.9, changeFrequency: "daily" },
  { path: routes.shop, priority: 0.8, changeFrequency: "weekly" },
  { path: routes.freeResources, priority: 0.8, changeFrequency: "monthly" },
  { path: routes.newsletter, priority: 0.7, changeFrequency: "monthly" },
  { path: routes.partner, priority: 0.6, changeFrequency: "monthly" },
  { path: routes.about, priority: 0.6, changeFrequency: "monthly" },
  { path: routes.contact, priority: 0.5, changeFrequency: "yearly" },
  { path: routes.privacy, priority: 0.2, changeFrequency: "yearly" },
  { path: routes.terms, priority: 0.2, changeFrequency: "yearly" },
  { path: routes.affiliate, priority: 0.2, changeFrequency: "yearly" },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [articles, topics] = await Promise.all([getArticles(), getTopics()]);
  const url = (path: string) => new URL(path, siteConfig.url).toString();

  return [
    ...staticRoutes.map((r) => ({
      url: url(r.path),
      changeFrequency: r.changeFrequency,
      priority: r.priority,
    })),
    ...topics.map((t) => ({
      url: url(routes.topic(t.slug)),
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })),
    ...articles
      // Articles whose canonical points elsewhere should not be listed.
      .filter((a) => !a.seo?.canonicalUrl && !a.legacy?.canonicalUrl && !a.seo?.noIndex)
      .map((a) => ({
        url: url(routes.article(a.slug)),
        lastModified: new Date(a.updatedAt ?? a.publishedAt),
        changeFrequency: "monthly" as const,
        priority: 0.8,
      })),
  ];
}

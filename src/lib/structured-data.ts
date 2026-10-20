import { siteConfig } from "@/config/site";
import { socialLinks } from "@/config/social";
import { routes } from "@/config/navigation";
import { absoluteUrl } from "@/lib/utils";
import type { Article, Topic } from "@/types";

type JsonLd = Record<string, unknown>;

const url = (path: string) => absoluteUrl(path, siteConfig.url);

export function organizationJsonLd(): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: siteConfig.name,
    alternateName: siteConfig.shortName,
    url: siteConfig.url,
    description: siteConfig.description,
    ...(socialLinks.length > 0 && { sameAs: socialLinks.map((s) => s.url) }),
  };
}

export function websiteJsonLd(): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: siteConfig.name,
    url: siteConfig.url,
    inLanguage: siteConfig.language,
  };
}

export function articleJsonLd(article: Article, topic: Topic | undefined): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.excerpt,
    image: [url(article.image.src)],
    datePublished: article.publishedAt,
    dateModified: article.updatedAt ?? article.publishedAt,
    author: { "@type": "Organization", name: article.author.name, url: siteConfig.url },
    publisher: { "@type": "Organization", name: siteConfig.name, url: siteConfig.url },
    mainEntityOfPage: { "@type": "WebPage", "@id": url(routes.article(article.slug)) },
    ...(topic && { articleSection: topic.name }),
    ...(article.tags?.length && { keywords: article.tags.join(", ") }),
    inLanguage: siteConfig.language,
  };
}

export function breadcrumbJsonLd(items: { name: string; href: string }[]): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: url(item.href),
    })),
  };
}

/** Serialises JSON-LD safely for inline <script> tags. */
export function serializeJsonLd(data: JsonLd | JsonLd[]): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { absoluteUrl } from "./format";

const url = (path) => absoluteUrl(path, siteConfig.url);

export function organizationJsonLd(socialLinks = []) {
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

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: siteConfig.name,
    url: siteConfig.url,
    inLanguage: siteConfig.language,
  };
}

function imageObject(image) {
  return {
    "@type": "ImageObject",
    url: url(image.src),
    width: image.width,
    height: image.height,
    ...(image.caption && { caption: image.caption }),
  };
}

/** Person only for authors marked as real people; editorial bylines stay organisational. */
function authorEntity(article) {
  const profile = article.author_profile;
  if (profile?.is_person) {
    return {
      "@type": "Person",
      name: profile.name,
      ...(profile.bio && { description: profile.bio }),
      ...(profile.image?.src && { image: url(profile.image.src) }),
    };
  }
  return { "@type": "Organization", name: article.author.name, url: siteConfig.url };
}

export function articleJsonLd(article) {
  const images = [article.seo?.og_image, article.image].filter((i) => i?.src);
  return {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: article.title,
    description: article.seo?.description ?? article.excerpt,
    image: images.map(imageObject),
    datePublished: article.published_at,
    dateModified: article.updated_at ?? article.published_at,
    author: authorEntity(article),
    publisher: { "@type": "Organization", name: siteConfig.name, url: siteConfig.url },
    mainEntityOfPage: { "@type": "WebPage", "@id": url(routes.article(article.slug)) },
    ...(article.topic && { articleSection: article.topic.name }),
    ...(article.tags?.length && { keywords: article.tags.join(", ") }),
    inLanguage: siteConfig.language,
  };
}

export function breadcrumbJsonLd(items) {
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

/** Serialises JSON for inline <script> tags without allowing tag breakout. */
export function safeJson(data) {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

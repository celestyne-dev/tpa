import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { absoluteUrl } from "./format";

const url = (path) => absoluteUrl(path, siteConfig.url);

/** Organization entity from CMS settings (name, logo, social profiles). */
export function organizationJsonLd(site) {
  const socialLinks = site?.social_links ?? [];
  const logo = site?.seo?.organization_logo?.src ?? site?.branding?.logo?.src;
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: site?.name ?? siteConfig.name,
    alternateName: site?.short_name ?? siteConfig.shortName,
    url: siteConfig.url,
    description: site?.description ?? siteConfig.description,
    ...(logo && { logo: url(logo) }),
    ...(socialLinks.length > 0 && { sameAs: socialLinks.map((s) => s.url) }),
  };
}

export function websiteJsonLd(site) {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: site?.name ?? siteConfig.name,
    url: siteConfig.url,
    inLanguage: siteConfig.language,
  };
}

/** Site-wide entities, honouring the CMS switches (both on by default). */
export function siteJsonLd(site) {
  const out = [];
  if (site?.seo?.organization_schema !== false) out.push(organizationJsonLd(site));
  if (site?.seo?.website_schema !== false) out.push(websiteJsonLd(site));
  return out;
}

/** A CMS page: accurate modified time from its last publish (or shared content change). */
export function webPageJsonLd(page) {
  return {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: page.seo?.title || page.title,
    url: url(page.path),
    ...(page.seo?.description && { description: page.seo.description }),
    ...(page.published_at && { datePublished: page.published_at }),
    ...(page.updated_at && { dateModified: page.updated_at }),
    inLanguage: siteConfig.language,
    isPartOf: { "@type": "WebSite", url: siteConfig.url },
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

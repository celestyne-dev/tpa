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

/**
 * Product structured data with accurate offers only: an Offer is included per
 * real price when the product can be bought now. Coming-soon and free products
 * get no Offer. No ratings, reviews or stock counts are ever emitted.
 */
export function productJsonLd(product) {
  const image = product.seo?.og_image ?? product.cover;
  const offers =
    product.availability === "available"
      ? product.prices.map((price) => ({
          "@type": "Offer",
          price: price.amount,
          priceCurrency: price.currency,
          availability: "https://schema.org/InStock",
          url: url(routes.product(product.slug)),
          ...(price.promotion_ends_at && { priceValidUntil: price.promotion_ends_at.slice(0, 10) }),
        }))
      : [];
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.title,
    description: product.seo?.description || product.description,
    sku: product.id,
    url: url(routes.product(product.slug)),
    ...(image?.src && { image: [url(image.src)] }),
    brand: { "@type": "Brand", name: siteConfig.name },
    ...(product.categories?.[0] && { category: product.categories[0].name }),
    ...(offers.length && { offers: offers.length === 1 ? offers[0] : offers }),
  };
}

/**
 * Course structured data (schema.org/Course) for published courses only. Offers are real
 * prices from the course product; free courses are marked isAccessibleForFree. No ratings
 * or enrolment counts are emitted.
 */
export function courseJsonLd(course, { isoDuration } = {}) {
  const image = course.seo?.image ?? course.cover;
  const offers = course.is_free
    ? [{ "@type": "Offer", price: "0", priceCurrency: "USD", category: "Free" }]
    : course.availability === "available"
      ? (course.prices ?? []).map((price) => ({
          "@type": "Offer",
          price: price.amount,
          priceCurrency: price.currency,
          category: "Paid",
          availability: "https://schema.org/InStock",
          url: url(routes.course(course.slug)),
        }))
      : [];
  return {
    "@context": "https://schema.org",
    "@type": "Course",
    name: course.title,
    description: course.seo?.description || course.summary,
    url: url(routes.course(course.slug)),
    inLanguage: "en",
    isAccessibleForFree: Boolean(course.is_free),
    provider: { "@type": "Organization", name: siteConfig.name, sameAs: siteConfig.url },
    ...(image?.src && { image: [url(image.src)] }),
    ...(course.outcomes?.length && { teaches: course.outcomes }),
    ...(course.level && course.level !== "all_levels" && { educationalLevel: course.level }),
    ...(course.author?.is_person && {
      instructor: [{ "@type": "Person", name: course.author.name }],
    }),
    hasCourseInstance: [
      {
        "@type": "CourseInstance",
        courseMode: "online",
        ...(isoDuration &&
          course.total_minutes && {
            courseWorkload: isoDuration(course.total_minutes),
          }),
      },
    ],
    ...(offers.length && { offers }),
  };
}

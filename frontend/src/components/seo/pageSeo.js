import { breadcrumbJsonLd, webPageJsonLd } from "@/utils/structuredData";

/** Seo props for a resolved CMS page (title, description, social card, JSON-LD). */
export function cmsSeoProps(page, { isHome = false } = {}) {
  if (!page) return { path: isHome ? "/" : undefined };
  const seo = page.seo ?? {};
  const crumbs = page.breadcrumbs ?? [];
  const jsonLd = [webPageJsonLd(page)];
  if (crumbs.length > 2) {
    jsonLd.push(breadcrumbJsonLd(crumbs.map((c) => ({ name: c.name, href: c.path }))));
  }
  return {
    path: page.path,
    // The homepage's SEO title is the full document title; other pages get "| Site name".
    ...(isHome ? { fullTitle: seo.title || undefined } : { title: seo.title || page.title }),
    ...(seo.description && { description: seo.description }),
    ...(seo.og_image?.src && {
      image: {
        src: seo.og_image.src,
        width: seo.og_image.width,
        height: seo.og_image.height,
        alt: seo.og_image.alt || page.title,
      },
    }),
    socialTitle: seo.og_title || undefined,
    socialDescription: seo.og_description || undefined,
    canonicalUrl: seo.canonical_url || undefined,
    noIndex: Boolean(seo.noindex),
    jsonLd,
  };
}

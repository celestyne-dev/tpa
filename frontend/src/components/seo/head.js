import { siteConfig } from "@/config/site";
import { absoluteUrl } from "@/utils/format";
import { safeJson } from "@/utils/structuredData";

/** Builds a serialisable description of the document head for a page. */
export function buildHead({
  title,
  description = siteConfig.description,
  path = "/",
  image = siteConfig.defaultOgImage,
  type = "website",
  article,
  canonicalUrl,
  noIndex = false,
  jsonLd = [],
  defaults,
  siteName,
}) {
  // CMS-managed SEO defaults (GET /api/v1/site) take precedence over build-time config.
  const name = siteName || siteConfig.name;
  const defaultImage = defaults?.default_og_image
    ? { src: defaults.default_og_image, width: 1200, height: 630, alt: name }
    : siteConfig.defaultOgImage;
  if (description === siteConfig.description && defaults?.default_description) {
    description = defaults.default_description;
  }
  if (image === siteConfig.defaultOgImage) image = defaultImage;
  const fullTitle = title
    ? `${title} | ${name}`
    : defaults?.default_title || siteConfig.defaultTitle;
  const url = absoluteUrl(path, siteConfig.url);
  const imageUrl = absoluteUrl(image.src, siteConfig.url);
  let robots = "index, follow, max-image-preview:large";
  if (!siteConfig.allowIndexing) robots = "noindex, nofollow";
  else if (noIndex) robots = "noindex, follow";

  const meta = [
    { name: "description", content: description },
    { name: "robots", content: robots },
    { property: "og:title", content: title ?? name },
    { property: "og:description", content: description },
    { property: "og:url", content: url },
    { property: "og:site_name", content: name },
    { property: "og:locale", content: siteConfig.locale },
    { property: "og:type", content: type },
    { property: "og:image", content: imageUrl },
    { property: "og:image:width", content: String(image.width) },
    { property: "og:image:height", content: String(image.height) },
    { property: "og:image:alt", content: image.alt },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: title ?? name },
    { name: "twitter:description", content: description },
    { name: "twitter:image", content: imageUrl },
  ];
  if (type === "article" && article) {
    meta.push({ property: "article:published_time", content: article.publishedTime });
    if (article.modifiedTime)
      meta.push({ property: "article:modified_time", content: article.modifiedTime });
    if (article.section) meta.push({ property: "article:section", content: article.section });
    (article.authors ?? []).forEach((a) => meta.push({ property: "article:author", content: a }));
    (article.tags ?? []).forEach((t) => meta.push({ property: "article:tag", content: t }));
  }

  return {
    title: fullTitle,
    meta,
    links: [{ rel: "canonical", href: canonicalUrl ?? url }],
    jsonLd: Array.isArray(jsonLd) ? jsonLd : [jsonLd],
  };
}

const escapeAttr = (value) =>
  String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

const attrs = (obj) =>
  Object.entries(obj)
    .map(([k, v]) => `${k}="${escapeAttr(v)}"`)
    .join(" ");

/** Serialises a head description to HTML (used by the prerenderer). */
export function renderHeadToString(head) {
  return [
    `<title>${escapeAttr(head.title)}</title>`,
    ...head.meta.map((m) => `<meta data-seo ${attrs(m)} />`),
    ...head.links.map((l) => `<link data-seo ${attrs(l)} />`),
    ...head.jsonLd.map(
      (data) => `<script data-seo type="application/ld+json">${safeJson(data)}</script>`,
    ),
  ].join("\n    ");
}

/** Applies a head description to the live document (client navigation). */
export function applyHead(head, doc = document) {
  doc.title = head.title;
  doc.head.querySelectorAll("[data-seo]").forEach((el) => el.remove());
  const add = (tag, props, text) => {
    const el = doc.createElement(tag);
    el.setAttribute("data-seo", "");
    Object.entries(props).forEach(([k, v]) => el.setAttribute(k, v));
    if (text) el.textContent = text;
    doc.head.appendChild(el);
  };
  head.meta.forEach((m) => add("meta", m));
  head.links.forEach((l) => add("link", l));
  head.jsonLd.forEach((data) => add("script", { type: "application/ld+json" }, safeJson(data)));
}

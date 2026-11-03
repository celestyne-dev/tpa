/**
 * RSS 2.0 feed of the latest published, indexable articles: title, link, summary (the
 * article excerpt, never the full text), publication date, topic and byline.
 */
const xml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    // Characters XML 1.0 does not allow.
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");

export const FEED_LIMIT = 50;

export function buildFeed({ siteUrl, siteName, description, articles, articlePath }) {
  const items = [...articles]
    .sort((a, b) => (a.published_at < b.published_at ? 1 : -1))
    .slice(0, FEED_LIMIT);
  const latest = items[0]?.published_at;
  const body = items
    .map((a) => {
      const link = `${siteUrl}${articlePath(a.slug)}`;
      return [
        "    <item>",
        `      <title>${xml(a.title)}</title>`,
        `      <link>${xml(link)}</link>`,
        `      <guid isPermaLink="true">${xml(link)}</guid>`,
        `      <pubDate>${new Date(a.published_at).toUTCString()}</pubDate>`,
        a.excerpt ? `      <description>${xml(a.excerpt)}</description>` : null,
        a.topic?.name ? `      <category>${xml(a.topic.name)}</category>` : null,
        a.author?.name ? `      <dc:creator>${xml(a.author.name)}</dc:creator>` : null,
        "    </item>",
      ]
        .filter(Boolean)
        .join("\n");
    })
    .join("\n");
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">\n` +
    `  <channel>\n` +
    `    <title>${xml(siteName)}</title>\n` +
    `    <link>${xml(siteUrl)}/</link>\n` +
    `    <description>${xml(description)}</description>\n` +
    `    <language>en</language>\n` +
    `    <atom:link href="${xml(siteUrl)}/feed.xml" rel="self" type="application/rss+xml" />\n` +
    (latest ? `    <lastBuildDate>${new Date(latest).toUTCString()}</lastBuildDate>\n` : "") +
    (body ? `${body}\n` : "") +
    `  </channel>\n</rss>\n`
  );
}

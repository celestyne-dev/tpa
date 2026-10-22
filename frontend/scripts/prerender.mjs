/**
 * Build-time prerendering for crawlable HTML.
 *
 * 1. Loads the SSR bundle produced by `vite build --ssr`.
 * 2. Asks the Flask API (the authoritative content source) which topics and
 *    articles exist, so newly published content needs no frontend changes.
 * 3. Renders every public route to dist/<route>/index.html with its title,
 *    meta description, canonical URL, Open Graph tags, JSON-LD, full content
 *    and the serialised Redux state used for hydration.
 * 4. Writes dist/404.html, dist/sitemap.xml, dist/robots.txt and
 *    dist/prerender-manifest.json.
 */
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadEnv } from "vite";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(root, "dist");
const ssrEntry = path.join(root, ".ssr", "entry-server.js");

const mode = process.env.NODE_ENV === "development" ? "development" : "production";
const env = { ...loadEnv(mode, root, ""), ...process.env };
const apiUrl = (env.PRERENDER_API_URL || "http://127.0.0.1:5000/api/v1").replace(/\/$/, "");

const { render, createServerApi, staticRoutes, routes, siteConfig, safeJson } = await import(
  pathToFileURL(ssrEntry).href
);
const api = createServerApi(apiUrl);

function fail(message) {
  console.error(`\n✖ Prerender failed: ${message}\n`);
  process.exit(1);
}

async function checkApi() {
  try {
    const res = await fetch(`${apiUrl}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (error) {
    fail(
      `the Flask API is not reachable at ${apiUrl} (${error.message}).\n` +
        "  Start it first (see README: 'Production build') or set PRERENDER_API_URL.",
    );
  }
}

async function fetchAllArticles() {
  const all = [];
  for (let page = 1; ; page += 1) {
    const { data, meta } = await api.getArticles({ page, page_size: 50 });
    all.push(...data);
    if (!meta?.pagination?.has_next) return all;
  }
}

function injectTemplate(template, { head, html, state }) {
  const stateScript = state ? `<script>window.__TPA_STATE__=${safeJson(state)}</script>` : "";
  return template
    .replace("<!--app-head-->", head)
    .replace(
      '<div id="root"><!--app-html--></div>',
      `<div id="root"${state ? ' data-prerendered="true"' : ""}>${html}</div>`,
    )
    .replace("<!--app-state-->", stateScript);
}

function outputPath(route) {
  return route === "/"
    ? path.join(distDir, "index.html")
    : path.join(distDir, route.replace(/^\//, ""), "index.html");
}

const xmlEscape = (value) =>
  String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function buildSitemap(entries) {
  const body = entries
    .map((e) => {
      const parts = [`    <loc>${xmlEscape(new URL(e.path, siteConfig.url).toString())}</loc>`];
      if (e.lastmod) parts.push(`    <lastmod>${e.lastmod}</lastmod>`);
      if (e.changefreq) parts.push(`    <changefreq>${e.changefreq}</changefreq>`);
      if (e.priority !== undefined) parts.push(`    <priority>${e.priority}</priority>`);
      return `  <url>\n${parts.join("\n")}\n  </url>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`;
}

function buildRobots() {
  if (!siteConfig.allowIndexing) {
    // Previews, staging and local builds must never be indexed.
    return "User-agent: *\nDisallow: /\n";
  }
  return `User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin/\n\nSitemap: ${siteConfig.url}/sitemap.xml\n`;
}

await checkApi();

const template = await readFile(path.join(distDir, "index.html"), "utf8");
for (const marker of ["<!--app-head-->", "<!--app-html-->", "<!--app-state-->"]) {
  if (!template.includes(marker)) fail(`dist/index.html is missing the ${marker} marker.`);
}

const [topicsRes, articles] = await Promise.all([api.getTopics(), fetchAllArticles()]);
const topics = topicsRes.data;

const pages = [
  ...staticRoutes,
  ...topics.map((t) => ({ path: routes.topic(t.slug), priority: 0.7, changefreq: "weekly" })),
  ...articles.map((a) => ({
    path: routes.article(a.slug),
    priority: 0.8,
    changefreq: "monthly",
    lastmod: (a.updated_at ?? a.published_at).slice(0, 10),
    // Articles whose canonical points elsewhere are rendered but kept out of the sitemap.
    inSitemap: !a.canonical_url,
  })),
];

const manifest = [];
for (const page of pages) {
  const result = await render(page.path, api);
  if (result.status !== 200) fail(`${page.path} rendered with status ${result.status}.`);
  const file = outputPath(page.path);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, injectTemplate(template, result));
  manifest.push({ path: page.path, file: path.relative(distDir, file) });
}

const notFound = await render("/__tpa-not-found__", api);
if (notFound.status !== 404) fail("the not-found route did not report status 404.");
await writeFile(
  path.join(distDir, "404.html"),
  injectTemplate(template, { ...notFound, state: null }),
);

await writeFile(
  path.join(distDir, "sitemap.xml"),
  buildSitemap(pages.filter((p) => p.inSitemap !== false)),
);
await writeFile(path.join(distDir, "robots.txt"), buildRobots());
await writeFile(
  path.join(distDir, "prerender-manifest.json"),
  JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      siteUrl: siteConfig.url,
      indexing: siteConfig.allowIndexing,
      apiUrl,
      pages: manifest,
    },
    null,
    2,
  ) + "\n",
);
await rm(path.join(root, ".ssr"), { recursive: true, force: true });

console.log(
  `✓ Prerendered ${manifest.length} pages + 404.html from ${apiUrl}` +
    ` (indexing ${siteConfig.allowIndexing ? "ENABLED" : "disabled"}, site ${siteConfig.url})`,
);

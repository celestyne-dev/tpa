/**
 * Build-time prerendering for crawlable HTML.
 *
 * 1. Loads the SSR bundle produced by `vite build --ssr`.
 * 2. Asks the Flask API (the authoritative content source) which topics and
 *    articles exist, so newly published content needs no frontend changes.
 * 3. Renders every public route to dist/<route>/index.html with its title,
 *    meta description, canonical URL, Open Graph tags, JSON-LD, full content
 *    and the serialised Redux state used for hydration.
 *    Published CMS pages (GET /api/v1/pages) are rendered the same way.
 * 4. Writes dist/404.html, dist/admin/index.html (client-only admin shell),
 *    dist/sitemap.xml (from GET /api/v1/sitemap: only published, indexable,
 *    self-canonical URLs, with image entries), dist/robots.txt (AI training
 *    crawlers blocked unless approved), dist/feed.xml (RSS: article summaries),
 *    dist/redirects.json and dist/prerender-manifest.json (with the release id).
 * 5. Archive, topic and author listings get one prerendered page per page of
 *    articles (/articles/page/2, ...), linked with plain <a href> pagination.
 *
 * The page state is embedded as inert JSON (<script type="application/json">), never as
 * executable inline script, so the site works under a strict Content-Security-Policy.
 *
 * Drafts and private previews are never fetched: the public API only returns
 * published content.
 */
import { execFileSync } from "node:child_process";
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadEnv } from "vite";
import { buildFeed } from "./lib/feed.mjs";
import { buildRobots } from "./lib/robots.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(root, "dist");
const ssrEntry = path.join(root, ".ssr", "entry-server.js");

const mode = process.env.NODE_ENV === "development" ? "development" : "production";
const env = { ...loadEnv(mode, root, ""), ...process.env };
const apiUrl = (env.PRERENDER_API_URL || "http://127.0.0.1:5000/api/v1").replace(/\/$/, "");

const {
  render,
  createServerApi,
  staticRoutes,
  privateRoutes,
  policyPages,
  routes,
  siteConfig,
  configureSite,
  safeJson,
} = await import(pathToFileURL(ssrEntry).href);
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

/** The commit being built: TPA_RELEASE (set by CI/deploy), else git, else "unknown". */
function releaseId() {
  const fromEnv = (env.TPA_RELEASE || "").trim();
  if (fromEnv) return fromEnv.slice(0, 40).replace(/[^A-Za-z0-9._-]/g, "");
  try {
    return execFileSync("git", ["rev-parse", "--short=12", "HEAD"], {
      cwd: root,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "unknown";
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

const attr = (value) =>
  String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** CMS favicon (Admin › Branding) replaces the built-in /icon.svg links. */
function applyBranding(template, site) {
  const favicon = site?.branding?.favicon;
  if (!favicon) return template;
  const links = [
    `<link rel="icon" href="${attr(favicon.ico)}" sizes="48x48" />`,
    `<link rel="icon" type="image/png" sizes="32x32" href="${attr(favicon.png32)}" />`,
    `<link rel="apple-touch-icon" href="${attr(favicon.apple)}" />`,
  ].join("\n    ");
  return template
    .replace(/<link rel="icon"[^>]*>/g, "")
    .replace(/<link rel="apple-touch-icon"[^>]*>/g, "")
    .replace("<!--app-head-->", `${links}\n    <!--app-head-->`);
}

function buildManifest(site, base) {
  const favicon = site?.branding?.favicon;
  return {
    ...base,
    name: site?.name ?? base.name,
    short_name: site?.short_name ?? base.short_name,
    description: site?.tagline ?? base.description,
    icons: favicon
      ? [
          { src: favicon.png192, sizes: "192x192", type: "image/png" },
          { src: favicon.png512, sizes: "512x512", type: "image/png" },
        ]
      : base.icons,
  };
}

/**
 * Build-wide head tags: the release id (so "which build is live?" is answerable from any
 * page), the RSS feed, and preloads for the two primary font files.
 */
async function applyBuildHead(template, release) {
  const assets = await readdir(path.join(distDir, "assets")).catch(() => []);
  const fonts = ["inter-latin-wght-normal-", "fraunces-latin-opsz-normal-"]
    .map((prefix) => assets.find((f) => f.startsWith(prefix) && f.endsWith(".woff2")))
    .filter(Boolean);
  const tags = [
    `<meta name="tpa-build" content="${attr(release)}" />`,
    `<link rel="alternate" type="application/rss+xml" title="${attr(siteConfig.name)}" href="/feed.xml" />`,
    ...fonts.map(
      (f) =>
        `<link rel="preload" href="/assets/${attr(f)}" as="font" type="font/woff2" crossorigin />`,
    ),
  ].join("\n    ");
  return template.replace("<!--app-head-->", `${tags}\n    <!--app-head-->`);
}

function injectTemplate(template, { head, html, state }) {
  // Inert JSON (not executable): read by entry-client.jsx, allowed by a strict CSP.
  const stateScript = state
    ? `<script type="application/json" id="tpa-state">${safeJson(state)}</script>`
    : "";
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

const absolute = (value) => new URL(value, siteConfig.url).toString();

function buildSitemap(entries) {
  const body = entries
    .map((e) => {
      const parts = [`    <loc>${xmlEscape(absolute(e.path))}</loc>`];
      if (e.lastmod) parts.push(`    <lastmod>${e.lastmod.slice(0, 10)}</lastmod>`);
      if (e.changefreq) parts.push(`    <changefreq>${e.changefreq}</changefreq>`);
      if (e.priority !== undefined) parts.push(`    <priority>${e.priority}</priority>`);
      for (const image of e.images ?? []) {
        parts.push(
          `    <image:image>\n      <image:loc>${xmlEscape(absolute(image.loc))}</image:loc>\n    </image:image>`,
        );
      }
      return `  <url>\n${parts.join("\n")}\n  </url>`;
    })
    .join("\n");
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" ` +
    `xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n${body}\n</urlset>\n`
  );
}

await checkApi();

// CMS settings that affect every page: canonical address, indexing, favicon, manifest.
const site = (await api.getSite()).data;
configureSite(site);

const release = releaseId();
const template = await applyBuildHead(
  applyBranding(await readFile(path.join(distDir, "index.html"), "utf8"), site),
  release,
);
for (const marker of ["<!--app-head-->", "<!--app-html-->", "<!--app-state-->"]) {
  if (!template.includes(marker)) fail(`dist/index.html is missing the ${marker} marker.`);
}

const [
  topicsRes,
  articles,
  sitemapRes,
  redirectsRes,
  cmsPagesRes,
  productsRes,
  collectionsRes,
  coursesRes,
  authorsRes,
] = await Promise.all([
  api.getTopics(),
  fetchAllArticles(),
  api.getSitemap(),
  api.getRedirects(),
  api.getPages(),
  api.getProducts(),
  api.getCollections(),
  api.getCourses(),
  api.getAuthors(),
]);
const topics = topicsRes.data;
const authors = authorsRes.data;
const PAGE_SIZE = 12;
/** Paths for listing pages 2..N (page 1 is the listing's own URL). */
const extraPages = (count, pathFor) =>
  Array.from({ length: Math.max(0, Math.ceil(count / PAGE_SIZE) - 1) }, (_v, i) => ({
    path: pathFor(i + 2),
    priority: 0.3,
  }));
const staticPaths = new Set(staticRoutes.map((r) => r.path));
const cmsPaths = new Set(cmsPagesRes.data.map((p) => p.path));

const pages = [
  ...staticRoutes,
  // Published CMS pages only (the public API never lists drafts or archived pages).
  ...cmsPagesRes.data
    .filter((p) => !staticPaths.has(p.path))
    .map((p) => ({ path: p.path, priority: 0.6, changefreq: "monthly" })),
  ...topics.map((t) => ({ path: routes.topic(t.slug), priority: 0.7, changefreq: "weekly" })),
  // Crawlable pagination: every page of the archive, each topic and each author.
  ...extraPages(articles.length, (n) => routes.articlesPage(n)),
  ...topics.flatMap((t) => extraPages(t.article_count, (n) => routes.topicPage(t.slug, n))),
  ...authors.flatMap((a) => [
    { path: routes.author(a.slug), priority: 0.4 },
    ...extraPages(a.article_count, (n) => routes.authorPage(a.slug, n)),
  ]),
  // Published products and collections (drafts and archived products are never listed).
  ...productsRes.data.map((p) => ({ path: routes.product(p.slug) })),
  ...collectionsRes.data.map((c) => ({ path: routes.collection(c.slug) })),
  // Published course pages (marketing content and syllabus titles; never lesson content).
  ...coursesRes.data.map((c) => ({ path: routes.course(c.slug) })),
  // Policy pages not yet published in the CMS: their built-in drafts render with
  // "noindex" (a published one is rendered above, as a CMS page).
  ...policyPages.filter((p) => !cmsPaths.has(p.path)).map((p) => ({ path: p.path })),
  // Private customer pages: noindex shells; customer data only ever loads in the browser.
  ...privateRoutes.map((path) => ({ path, private: true })),
  ...articles.map((a) => ({
    path: routes.article(a.slug),
    priority: 0.8,
    changefreq: "monthly",
    lastmod: (a.updated_at ?? a.published_at).slice(0, 10),
  })),
];

const manifest = [];
for (const page of pages) {
  const result = await render(page.path, api);
  if (result.status !== 200) fail(`${page.path} rendered with status ${result.status}.`);
  // Private pages load in the browser (lazy chunk), so their own <Seo noIndex> isn't in the
  // static HTML: mark the shell itself as never indexable.
  if (page.private && !/name="robots"[^>]*noindex/.test(result.head)) {
    result.head += '\n    <meta name="robots" content="noindex, nofollow" />';
  }
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

// Admin SPA shell: rendered client-side only, never indexed.
await mkdir(path.join(distDir, "admin"), { recursive: true });
await writeFile(
  path.join(distDir, "admin", "index.html"),
  injectTemplate(template, {
    head: '<title>Admin | Think Positive Always</title>\n    <meta name="robots" content="noindex, nofollow" />',
    html: "",
    state: null,
  }),
);

// Learner and certificate shells: client-only (no lesson, progress or name is ever in the
// HTML). Nginx serves them for /learn/* and /certificates/*; the data loads in the browser.
for (const [dir, title] of [
  ["learn", "Learning"],
  ["certificates", "Certificate verification"],
]) {
  await mkdir(path.join(distDir, dir), { recursive: true });
  await writeFile(
    path.join(distDir, dir, "index.html"),
    injectTemplate(template, {
      head: `<title>${title} | Think Positive Always</title>\n    <meta name="robots" content="noindex, nofollow" />`,
      html: "",
      state: null,
    }),
  );
}

// The API decides what is indexable (noindex, external canonicals, drafts excluded).
await writeFile(path.join(distDir, "sitemap.xml"), buildSitemap(sitemapRes.data));
await writeFile(
  path.join(distDir, "redirects.json"),
  JSON.stringify(redirectsRes.data, null, 2) + "\n",
);
await writeFile(
  path.join(distDir, "robots.txt"),
  buildRobots({
    allowIndexing: siteConfig.allowIndexing,
    siteUrl: siteConfig.url,
    blockedTrainingCrawlers: site?.seo?.blocked_training_crawlers,
  }),
);
// RSS: summaries of published, indexable articles (the sitemap decides indexability).
const indexable = new Set(sitemapRes.data.filter((e) => e.type === "article").map((e) => e.path));
await writeFile(
  path.join(distDir, "feed.xml"),
  buildFeed({
    siteUrl: siteConfig.url,
    siteName: site?.name ?? siteConfig.name,
    description: site?.seo?.default_description || site?.tagline || siteConfig.description,
    articles: articles.filter((a) => indexable.has(routes.article(a.slug))),
    articlePath: routes.article,
  }),
);
const baseManifest = JSON.parse(await readFile(path.join(distDir, "manifest.webmanifest"), "utf8"));
await writeFile(
  path.join(distDir, "manifest.webmanifest"),
  JSON.stringify(buildManifest(site, baseManifest), null, 2) + "\n",
);
await writeFile(
  path.join(distDir, "prerender-manifest.json"),
  JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      release,
      siteUrl: siteConfig.url,
      indexing: siteConfig.allowIndexing,
      apiUrl,
      cmsPages: cmsPagesRes.data.map((p) => p.path),
      products: productsRes.data.map((p) => routes.product(p.slug)),
      courses: coursesRes.data.map((c) => routes.course(c.slug)),
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

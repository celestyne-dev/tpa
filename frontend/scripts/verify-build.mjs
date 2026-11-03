/**
 * Validates a finished production build (dist/) before it can be published:
 *
 * - every prerendered page: one <h1>, a canonical URL, the release id, valid JSON-LD,
 *   and no executable inline script (the page state is inert JSON, so a strict
 *   Content-Security-Policy can forbid inline scripts)
 * - crawlable pagination: listing pages 2..N exist, are self-canonical, and are linked
 *   with real <a href> links from the page before
 * - robots.txt: search engines and AI search crawlers allowed, AI training crawlers
 *   blocked unless approved, private paths closed, sitemap listed
 * - sitemap.xml and feed.xml: well formed, indexable URLs only, summaries not full text
 * - 404.html exists and is noindex
 *
 * Usage: node scripts/verify-build.mjs [distDir]   (exit 1 with a list of problems)
 */
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isAllowed, SEARCH_CRAWLERS } from "./lib/robots.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.resolve(process.argv[2] || path.join(root, "dist"));
const problems = [];
const fail = (where, message) => problems.push(`${where}: ${message}`);

const read = (file) => readFile(path.join(dist, file), "utf8");
const exists = (file) =>
  stat(path.join(dist, file)).then(
    () => true,
    () => false,
  );

const manifest = JSON.parse(await read("prerender-manifest.json"));
const siteUrl = manifest.siteUrl.replace(/\/$/, "");
if (!manifest.release || manifest.release === "unknown") fail("manifest", "no release id");

const SCRIPT = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
const INERT = /type="application\/(ld\+)?json"/;

function checkScripts(where, html) {
  let state = 0;
  for (const [, attrs, body] of html.matchAll(SCRIPT)) {
    if (/\bsrc=/.test(attrs)) continue;
    if (!INERT.test(attrs)) {
      fail(where, `inline executable <script ${attrs.trim()}> (breaks a strict CSP)`);
      continue;
    }
    try {
      JSON.parse(body);
    } catch {
      fail(where, `invalid JSON in <script ${attrs.trim()}>`);
    }
    if (attrs.includes('id="tpa-state"')) state += 1;
  }
  return state;
}

const pages = manifest.pages.map((p) => p.path);
for (const { path: route, file } of manifest.pages) {
  const html = await read(file);
  const where = route;
  const noindex = /name="robots" content="noindex/.test(html);
  checkScripts(where, html);
  if (!html.includes(`<meta name="tpa-build" content="${manifest.release}"`))
    fail(where, "missing the tpa-build release meta tag");
  if (noindex) continue; // private shells: no content to check
  const h1 = (html.match(/<h1[\s>]/g) ?? []).length;
  if (h1 !== 1) fail(where, `${h1} <h1> elements (expected exactly 1)`);
  const canonical = html.match(/<link data-seo rel="canonical" href="([^"]+)"/)?.[1];
  if (!canonical) fail(where, "no canonical link");
}

// Crawlable pagination: page N is self-canonical and linked from page N-1 with <a href>.
const paged = pages.filter((p) => /\/page\/\d+$/.test(p));
for (const route of paged) {
  const n = Number(route.split("/").pop());
  const base = route.replace(/\/page\/\d+$/, "");
  const html = await read(manifest.pages.find((p) => p.path === route).file);
  const canonical = html.match(/<link data-seo rel="canonical" href="([^"]+)"/)?.[1];
  if (canonical !== `${siteUrl}${route}`) fail(route, `canonical is ${canonical}, not itself`);
  if (/name="robots" content="noindex/.test(html)) fail(route, "pagination page is noindex");
  const previous = n === 2 ? base : `${base}/page/${n - 1}`;
  const prevFile = manifest.pages.find((p) => p.path === previous)?.file;
  if (!prevFile) fail(route, `previous page ${previous} was not prerendered`);
  else if (!(await read(prevFile)).includes(`href="${route}"`))
    fail(previous, `has no <a href="${route}"> link to the next page`);
}
if (paged.length === 0) fail("pagination", "no /page/N listing pages were prerendered");
if (!pages.some((p) => p.startsWith("/authors/"))) fail("authors", "no author page prerendered");

// robots.txt
const robots = await read("robots.txt");
if (manifest.indexing) {
  for (const bot of SEARCH_CRAWLERS) {
    if (!isAllowed(robots, bot, "/articles/example")) fail("robots.txt", `${bot} is blocked`);
    if (isAllowed(robots, bot, "/admin/")) fail("robots.txt", `${bot} may crawl /admin/`);
  }
  for (const bot of ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot"]) {
    if (isAllowed(robots, bot, "/articles/example"))
      fail("robots.txt", `${bot} (AI training) is not blocked by default`);
  }
  if (!robots.includes(`Sitemap: ${siteUrl}/sitemap.xml`)) fail("robots.txt", "no Sitemap line");
} else if (robots !== "User-agent: *\nDisallow: /\n") {
  fail("robots.txt", "a non-indexable build must disallow everything");
}

// sitemap.xml: indexable URLs only (no pagination, search, private or admin URLs).
const sitemap = await read("sitemap.xml");
if (!sitemap.startsWith("<?xml") || !sitemap.includes("<urlset")) fail("sitemap.xml", "malformed");
for (const bad of ["/page/", "/search", "/admin", "/account", "/cart", "/learn/"]) {
  if (sitemap.includes(`${siteUrl}${bad}`)) fail("sitemap.xml", `lists a ${bad} URL`);
}

// feed.xml: summaries of indexable articles only.
const feed = await read("feed.xml");
if (!feed.startsWith("<?xml") || !feed.includes('<rss version="2.0"'))
  fail("feed.xml", "malformed");
for (const [, link] of feed.matchAll(/<item>[\s\S]*?<link>([^<]+)<\/link>/g)) {
  if (!sitemap.includes(`<loc>${link}</loc>`)) fail("feed.xml", `${link} is not in the sitemap`);
}
for (const [, text] of feed.matchAll(/<description>([^<]*)<\/description>/g)) {
  if (text.length > 1200) fail("feed.xml", "an item description is longer than a summary");
}

// 404 page
if (!(await exists("404.html"))) fail("404.html", "missing");
else {
  const notFound = await read("404.html");
  checkScripts("404.html", notFound);
  if (!/name="robots" content="noindex/.test(notFound)) fail("404.html", "not noindex");
}

// Stray files that must never ship.
for (const name of await readdir(dist)) {
  if (name.startsWith(".env") || name.endsWith(".map")) fail(name, "must not be published");
}

if (problems.length > 0) {
  console.error(`✖ Build validation failed (${problems.length}):\n  - ${problems.join("\n  - ")}`);
  process.exit(1);
}
console.log(
  `✓ Build valid: ${pages.length} pages (${paged.length} pagination pages), release ${manifest.release}`,
);

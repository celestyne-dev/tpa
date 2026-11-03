import { describe, expect, it } from "vitest";
import { buildFeed } from "../../scripts/lib/feed.mjs";
import {
  DEFAULT_BLOCKED_TRAINING_CRAWLERS,
  SEARCH_CRAWLERS,
  buildRobots,
  isAllowed,
} from "../../scripts/lib/robots.mjs";

describe("robots.txt", () => {
  const robots = buildRobots({ allowIndexing: true, siteUrl: "https://e.com" });

  it("lets search engines and AI search crawlers read the public site only", () => {
    for (const bot of SEARCH_CRAWLERS) {
      expect(isAllowed(robots, bot, "/articles/a-story")).toBe(true);
      expect(isAllowed(robots, bot, "/admin/")).toBe(false);
      expect(isAllowed(robots, bot, "/api/v1/site")).toBe(false);
    }
  });

  it("blocks AI training crawlers until each one is approved", () => {
    for (const bot of DEFAULT_BLOCKED_TRAINING_CRAWLERS)
      expect(isAllowed(robots, bot, "/articles/a-story")).toBe(false);
    const approved = buildRobots({
      allowIndexing: true,
      siteUrl: "https://e.com",
      blockedTrainingCrawlers: ["GPTBot"],
    });
    expect(isAllowed(approved, "CCBot", "/articles/a-story")).toBe(true);
    expect(isAllowed(approved, "GPTBot", "/articles/a-story")).toBe(false);
  });

  it("never blocks a search crawler, even if listed by mistake", () => {
    const robotsWithMistake = buildRobots({
      allowIndexing: true,
      siteUrl: "https://e.com",
      blockedTrainingCrawlers: ["Googlebot", "OAI-SearchBot", "bad token"],
    });
    expect(isAllowed(robotsWithMistake, "Googlebot", "/")).toBe(true);
    expect(isAllowed(robotsWithMistake, "OAI-SearchBot", "/")).toBe(true);
    expect(robotsWithMistake).not.toContain("bad token");
  });

  it("closes everything on non-production builds and lists the sitemap otherwise", () => {
    expect(buildRobots({ allowIndexing: false })).toBe("User-agent: *\nDisallow: /\n");
    expect(robots.trim().endsWith("Sitemap: https://e.com/sitemap.xml")).toBe(true);
  });
});

describe("RSS feed", () => {
  it("lists summaries newest first, escaped", () => {
    const feed = buildFeed({
      siteUrl: "https://e.com",
      siteName: "TPA & Co",
      description: "Calm stories",
      articlePath: (slug) => `/articles/${slug}`,
      articles: [
        { slug: "old", title: "Old <one>", excerpt: "x & y", published_at: "2026-01-01T00:00:00Z" },
        { slug: "new", title: "New", excerpt: "Fresh", published_at: "2026-03-01T00:00:00Z" },
      ],
    });
    expect(feed.indexOf("/articles/new")).toBeLessThan(feed.indexOf("/articles/old"));
    expect(feed).toContain("<title>Old &lt;one&gt;</title>");
    expect(feed).toContain("<description>x &amp; y</description>");
    expect(feed).toContain('<atom:link href="https://e.com/feed.xml" rel="self"');
  });
});

import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { redirects } from "@/config/redirects";
import { footerNav, mainNav } from "@/config/navigation";
import { articles } from "@/data/articles";
import { products } from "@/data/products";
import { topics } from "@/data/topics";
import {
  getArticleBySlug,
  getArticles,
  getFeaturedArticles,
  getRelatedArticles,
} from "@/lib/content";

const slugPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const topicSlugs = new Set(topics.map((t) => t.slug));

describe("topics", () => {
  it("have unique, URL-safe slugs", () => {
    expect(new Set(topics.map((t) => t.slug)).size).toBe(topics.length);
    topics.forEach((t) => expect(t.slug).toMatch(slugPattern));
  });

  it("include the six homepage topics as featured", () => {
    expect(topics.filter((t) => t.featured)).toHaveLength(6);
  });
});

describe("articles", () => {
  it("have unique ids and URL-safe slugs", () => {
    expect(new Set(articles.map((a) => a.id)).size).toBe(articles.length);
    expect(new Set(articles.map((a) => a.slug)).size).toBe(articles.length);
    articles.forEach((a) => expect(a.slug).toMatch(slugPattern));
  });

  it("reference existing topics", () => {
    articles.forEach((a) => {
      expect(topicSlugs.has(a.topicSlug)).toBe(true);
      a.secondaryTopicSlugs?.forEach((s) => expect(topicSlugs.has(s)).toBe(true));
    });
  });

  it("have valid dates, alt text and existing images", () => {
    articles.forEach((a) => {
      expect(Number.isNaN(Date.parse(a.publishedAt))).toBe(false);
      expect(a.image.alt.length).toBeGreaterThan(10);
      if (a.image.src.startsWith("/")) {
        expect(existsSync(join(process.cwd(), "public", a.image.src))).toBe(true);
      }
    });
  });

  it("are clearly marked as sample content", () => {
    articles.forEach((a) => expect(["sample", "original", "migrated"]).toContain(a.source));
  });
});

describe("content repository", () => {
  it("returns published articles newest first", async () => {
    const list = await getArticles();
    const dates = list.map((a) => a.publishedAt);
    expect([...dates].sort().reverse()).toEqual(dates);
    list.forEach((a) => expect(a.readingTimeMinutes).toBeGreaterThan(0));
  });

  it("filters by topic, including secondary topics", async () => {
    const list = await getArticles({ topic: "emotional-well-being" });
    expect(list.length).toBeGreaterThan(0);
    list.forEach((a) =>
      expect([a.topicSlug, ...(a.secondaryTopicSlugs ?? [])]).toContain("emotional-well-being"),
    );
  });

  it("returns null for unknown slugs", async () => {
    expect(await getArticleBySlug("does-not-exist")).toBeNull();
  });

  it("returns featured and related articles without the current article", async () => {
    const featured = await getFeaturedArticles(3);
    expect(featured).toHaveLength(3);
    const first = featured[0]!;
    const related = await getRelatedArticles(first, 3);
    expect(related.map((a) => a.id)).not.toContain(first.id);
  });
});

describe("products", () => {
  it("are all upcoming and reference existing topics", () => {
    expect(products).toHaveLength(4);
    products.forEach((p) => {
      expect(p.availability).toBe("coming-soon");
      p.topicSlugs.forEach((s) => expect(topicSlugs.has(s)).toBe(true));
    });
  });
});

describe("navigation and redirects", () => {
  it("uses internal absolute paths only", () => {
    [...mainNav, ...footerNav.flatMap((g) => g.items)].forEach((item) => {
      expect(item.href.startsWith("/")).toBe(true);
      expect(item.href).not.toContain("#");
    });
  });

  it("defines well-formed redirects", () => {
    redirects.forEach((r) => {
      expect(r.source.startsWith("/")).toBe(true);
      expect(r.source).not.toBe(r.destination);
    });
  });
});

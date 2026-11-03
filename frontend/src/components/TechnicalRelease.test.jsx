import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { Pagination } from "@/components/ui/Pagination";
import { render as prerender } from "@/entry-server";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";
import { isSafeInlineHref, parseInlineLinks } from "@/utils/inlineLinks";
import { pageWindow } from "@/utils/pagination";
import {
  articleJsonLd,
  authorPageJsonLd,
  organizationJsonLd,
  webPageJsonLd,
  websiteJsonLd,
} from "@/utils/structuredData";

const inRouter = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

/** A fake API with `count` articles (fixtures repeated with unique slugs). */
function manyArticles(count) {
  const items = Array.from({ length: count }, (_v, i) => ({
    ...fx.articles[i % fx.articles.length],
    id: `m${i}`,
    slug: `article-${i + 1}`,
    title: `Article number ${i + 1}`,
  }));
  return createFakeApi({
    getArticles: vi.fn(async (params = {}) => {
      const size = params.page_size ?? 12;
      const page = params.page ?? 1;
      const list = params.featured ? items.slice(0, 1) : items;
      const totalPages = Math.max(1, Math.ceil(list.length / size));
      return {
        data: list.slice((page - 1) * size, page * size),
        meta: {
          pagination: {
            page,
            page_size: size,
            total: list.length,
            total_pages: totalPages,
            has_next: page < totalPages,
            has_prev: page > 1,
          },
        },
      };
    }),
  });
}

describe("crawlable pagination", () => {
  it("shows the first, last and nearby pages with gaps", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(5, 10)).toEqual([1, null, 4, 5, 6, null, 10]);
    expect(pageWindow(2, 3)).toEqual([1, 2, 3]);
  });

  it("renders real links with the current page marked", () => {
    inRouter(<Pagination page={2} totalPages={3} hrefFor={(p) => `/x/page/${p}`} />);
    const nav = screen.getByRole("navigation", { name: "Pagination" });
    expect(within(nav).getByRole("link", { name: /Newer/ })).toHaveAttribute("href", "/x/page/1");
    expect(within(nav).getByRole("link", { name: /Older/ })).toHaveAttribute("href", "/x/page/3");
    expect(within(nav).getByRole("link", { name: "Page 2" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders nothing for a single page", () => {
    const { container } = inRouter(<Pagination page={1} totalPages={1} hrefFor={() => "/"} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links the archive's pages with /articles/page/N and serves them", async () => {
    const api = manyArticles(30);
    const { unmount } = renderApp("/articles", { api });
    const nav = await screen.findByRole("navigation", { name: "Article pages" });
    expect(within(nav).getByRole("link", { name: "Page 2" })).toHaveAttribute(
      "href",
      "/articles/page/2",
    );
    expect(within(nav).getByRole("link", { name: "Page 3" })).toHaveAttribute(
      "href",
      "/articles/page/3",
    );
    unmount();
    renderApp("/articles/page/3", { api });
    expect(await screen.findByRole("link", { name: "Article number 25" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Page 1" })).toHaveAttribute("href", "/articles");
    await vi.waitFor(() =>
      expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
        "href",
        expect.stringMatching(/\/articles\/page\/3$/),
      ),
    );
  });

  it("prerenders page N with its own canonical and returns 404 past the last page", async () => {
    const api = manyArticles(30);
    const page2 = await prerender("/articles/page/2", api);
    expect(page2.status).toBe(200);
    expect(page2.head).toMatch(/rel="canonical" href="[^"]+\/articles\/page\/2"/);
    expect(page2.head).toContain("(Page 2)");
    expect(page2.html).toContain('href="/articles/page/3"');
    expect((await prerender("/articles/page/9", api)).status).toBe(404);
    expect((await prerender("/articles/page/0", api)).status).toBe(404);
    expect((await prerender("/articles/page/abc", api)).status).toBe(404);
    expect((await prerender("/topics/positive-mindset/page/7", createFakeApi())).status).toBe(404);
  });
});

describe("inline links and sources", () => {
  it("parses only safe targets", () => {
    expect(parseInlineLinks("See [a](/x) and [b](https://e.org)")).toEqual([
      { text: "See " },
      { label: "a", href: "/x" },
      { text: " and " },
      { label: "b", href: "https://e.org" },
    ]);
    for (const bad of ["javascript:alert(1)", "http://e.org", "//e.org", "data:x"])
      expect(isSafeInlineHref(bad)).toBe(false);
  });

  it("renders links in article text and leaves anything else as text", () => {
    inRouter(
      <ArticleBody
        blocks={[
          { type: "paragraph", text: "Read [our guide](/topics/confidence) today." },
          { type: "paragraph", text: "A [study](https://example.org/s) found this." },
          { type: "paragraph", text: "Never [this](javascript:alert(1))." },
          { type: "list", items: ["Write to [us](mailto:hi@example.com)"] },
          { type: "paragraph", uid: "lesson-1", text: "Lesson [text](/kept) stays as written." },
        ]}
        sponsoredLinks={[]}
      />,
    );
    expect(screen.getByRole("link", { name: "our guide" })).toHaveAttribute(
      "href",
      "/topics/confidence",
    );
    const external = screen.getByRole("link", { name: "study" });
    expect(external).toHaveAttribute("href", "https://example.org/s");
    expect(external.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText(/Never \[this\]\(javascript:alert\(1\)\)\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "us" })).toHaveAttribute(
      "href",
      "mailto:hi@example.com",
    );
    expect(screen.getByText("Lesson [text](/kept) stays as written.")).toBeInTheDocument();
  });

  it("marks paid links as sponsored", () => {
    inRouter(
      <ArticleBody
        blocks={[{ type: "paragraph", text: "Try [this tool](https://partner.example/x)." }]}
        sponsoredLinks={["https://partner.example/x"]}
      />,
    );
    expect(screen.getByRole("link", { name: "this tool" }).getAttribute("rel")).toContain(
      "sponsored",
    );
  });

  it("lists sources with publisher and access date", () => {
    inRouter(
      <ArticleBody
        blocks={[
          {
            type: "sources",
            items: [
              {
                title: "Sleep and mood",
                url: "https://example.org/study",
                publisher: "Example Journal",
                accessed: "2026-10-30",
              },
            ],
          },
        ]}
      />,
    );
    const section = screen.getByRole("region", { name: "Sources" });
    expect(within(section).getByRole("link", { name: "Sleep and mood" })).toHaveAttribute(
      "href",
      "https://example.org/study",
    );
    expect(section).toHaveTextContent("Example Journal");
    expect(section).toHaveTextContent("accessed October 30, 2026");
  });
});

describe("last updated", () => {
  it("shows a later material update only", () => {
    const { rerender } = render(
      <ArticleMeta
        publishedAt="2026-09-01T09:00:00Z"
        updatedAt="2026-10-15T09:00:00Z"
        readingTimeMinutes={3}
      />,
    );
    expect(screen.getByText(/Last updated/)).toHaveTextContent("Last updated October 15, 2026");
    rerender(<ArticleMeta publishedAt="2026-09-01T09:00:00Z" readingTimeMinutes={3} />);
    expect(screen.queryByText(/Last updated/)).not.toBeInTheDocument();
    rerender(
      <ArticleMeta
        publishedAt="2026-09-01T09:00:00Z"
        updatedAt="2026-09-01T15:00:00Z"
        readingTimeMinutes={3}
      />,
    );
    expect(screen.queryByText(/Last updated/)).not.toBeInTheDocument();
  });
});

describe("structured data", () => {
  it("links the organisation, website and pages by @id", () => {
    const org = organizationJsonLd({ ...fx.site, trust: {} });
    const site = websiteJsonLd(fx.site);
    expect(org["@id"]).toMatch(/\/#organization$/);
    expect(site.publisher).toEqual({ "@id": org["@id"] });
    expect(org.publishingPrinciples).toBeUndefined();
    const withPolicies = organizationJsonLd({
      ...fx.site,
      trust: {
        editorial_policy: { path: "/editorial-policy", title: "Editorial policy" },
        corrections_policy: { path: "/corrections-policy", title: "Corrections" },
      },
    });
    expect(withPolicies.publishingPrinciples).toMatch(/\/editorial-policy$/);
    expect(withPolicies.correctionsPolicy).toMatch(/\/corrections-policy$/);
    expect(webPageJsonLd({ title: "About", path: "/about" })["@type"]).toBe("AboutPage");
    expect(webPageJsonLd({ title: "Contact", path: "/contact" })["@type"]).toBe("ContactPage");
    expect(webPageJsonLd({ title: "Other", path: "/other" })["@type"]).toBe("WebPage");
  });

  it("dates, cites and attributes articles accurately", () => {
    const base = {
      ...fx.articleDetail,
      updated_at: "2026-11-01T00:00:00Z",
      body: [
        { type: "paragraph", text: "x" },
        { type: "sources", items: [{ title: "Study", url: "https://e.org/s", publisher: "J" }] },
      ],
    };
    const plain = articleJsonLd(base);
    // An ordinary save (updated_at) never becomes dateModified.
    expect(plain.dateModified).toBe(base.published_at);
    expect(plain.citation).toEqual([
      {
        "@type": "CreativeWork",
        name: "Study",
        url: "https://e.org/s",
        publisher: { "@type": "Organization", name: "J" },
      },
    ]);
    expect(plain.publisher["@id"]).toMatch(/\/#organization$/);
    const updated = articleJsonLd({ ...base, content_modified_at: "2026-10-20T00:00:00Z" });
    expect(updated.dateModified).toBe("2026-10-20T00:00:00Z");
    const person = articleJsonLd({
      ...base,
      author_profile: {
        slug: "jane",
        name: "Jane",
        bio: "Writer",
        is_person: true,
        has_page: true,
      },
    });
    expect(person.author).toMatchObject({
      "@type": "Person",
      url: expect.stringMatching(/\/authors\/jane$/),
    });
    const profile = authorPageJsonLd({ slug: "jane", name: "Jane", bio: "Writer" });
    expect(profile["@type"]).toBe("ProfilePage");
    expect(profile.mainEntity["@id"]).toBe(person.author["@id"]);
  });
});

describe("author pages", () => {
  const author = {
    slug: "jane-doe",
    name: "Jane Doe",
    bio: "Jane writes about resilience.",
    image: null,
    article_count: 2,
  };
  const api = () =>
    createFakeApi({
      getAuthor: vi.fn(async (slug) =>
        slug === "jane-doe"
          ? {
              data: { author, articles: fx.articles.slice(0, 2) },
              meta: {
                pagination: {
                  page: 1,
                  page_size: 12,
                  total: 2,
                  total_pages: 1,
                  has_next: false,
                  has_prev: false,
                },
              },
            }
          : Promise.reject(Object.assign(new Error("nf"), { status: 404 })),
      ),
    });

  it("shows the bio and the author's articles", async () => {
    renderApp("/authors/jane-doe", { api: api() });
    expect(await screen.findByRole("heading", { level: 1, name: "Jane Doe" })).toBeInTheDocument();
    expect(screen.getByText("Jane writes about resilience.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: fx.articles[0].title })).toBeInTheDocument();
  });

  it("is a 404 for anyone without a page", async () => {
    expect((await prerender("/authors/nobody", createFakeApi())).status).toBe(404);
  });

  it("links the byline only for authors with a page", async () => {
    const detail = {
      ...fx.articleDetail,
      author: { slug: "jane-doe", name: "Jane Doe", has_page: true },
    };
    const withPage = createFakeApi({
      getArticle: vi.fn(async () => ({ data: { article: detail, related: [] } })),
    });
    renderApp(`/articles/${detail.slug}`, { api: withPage });
    expect(await screen.findByRole("link", { name: "Jane Doe" })).toHaveAttribute(
      "href",
      "/authors/jane-doe",
    );
  });
});

describe("site search", () => {
  it("finds articles and announces the result count", async () => {
    const { api } = renderApp("/search?q=reframe");
    expect(await screen.findByText(/1 article found for “reframe”/)).toHaveAttribute(
      "aria-live",
      "polite",
    );
    const results = screen.getByRole("list", { name: "Search results" });
    expect(
      within(results).getByRole("link", { name: /Reframe a Negative Thought/ }),
    ).toHaveAttribute("href", "/articles/reframing-negative-thoughts");
    expect(within(results).getByText("Reframe", { selector: "mark" })).toBeInTheDocument();
    expect(api.search).toHaveBeenCalledWith({ q: "reframe", page: 1 });
  });

  it("is a plain GET form that works without JavaScript, and never indexed", async () => {
    const page = await prerender("/search", createFakeApi());
    expect(page.status).toBe(200);
    expect(page.html).toMatch(/<form[^>]*role="search"[^>]*action="\/search"[^>]*method="get"/);
    expect(page.html).toContain('name="q"');
    expect(page.head).toMatch(/name="robots" content="noindex/);
  });

  it("says when nothing matches", async () => {
    renderApp("/search?q=zzzz-nothing");
    expect(await screen.findByText(/No articles found for “zzzz-nothing”/)).toBeInTheDocument();
  });

  it("is linked from the header", async () => {
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Search articles" })).toHaveAttribute(
      "href",
      "/search",
    );
  });
});

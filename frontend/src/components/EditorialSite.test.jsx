import { render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ArticleSidebar } from "@/components/sidebar/ArticleSidebar";
import { createAppStore } from "@/store";
import * as fx from "@/test/fixtures";
import { createFakeApi, notFound, renderApp } from "@/test/utils";
import { listedResources } from "@/utils/resources";

const [a1, a2, a3] = fx.articles;

const section = (key, type, data, extra = {}) => ({
  key,
  type,
  variant: "list",
  design: {},
  devices: "all",
  data,
  ...extra,
});

/** The article sidebar as GET /articles/<slug> returns it (default order). */
function sidebar(overrides = {}) {
  const data = {
    popular: { heading: "Popular articles", articles: [a2, a3] },
    related: { heading: "Related articles", count: 4, show_images: true, articles: [a3] },
    newsletter: {
      eyebrow: "Daily newsletter",
      heading: "",
      description: "One thoughtful email each day.",
      show_learn_more: true,
      newsletter_name: "The Positive Reset",
      is_open: false,
    },
    picks: { heading: "Editor's Picks", articles: [a2] },
    topics: { heading: "Explore topics", topics: fx.topics },
    ...overrides,
  };
  return [
    section("popular", "popular_articles", data.popular, { variant: "numbered" }),
    section("related", "related_articles", data.related),
    section("newsletter", "newsletter_cta", data.newsletter, { variant: "compact" }),
    section("editors-picks", "featured_articles", data.picks),
    section("topics", "topics_grid", data.topics),
  ];
}

const author = {
  slug: "jane-doe",
  name: "Jane Doe",
  has_page: true,
};
const profile = {
  slug: "jane-doe",
  name: "Jane Doe",
  bio: "Jane writes about resilience.",
  image: null,
  is_person: true,
  has_page: true,
};

function articleApi({ sections = sidebar(), adjacent, site = fx.site, detail = {} } = {}) {
  return createFakeApi({
    getSite: vi.fn(async () => ({ data: site })),
    getArticle: vi.fn(async (slug) =>
      slug === fx.articleDetail.slug
        ? {
            data: {
              article: { ...fx.articleDetail, ...detail },
              related: [a2],
              adjacent: adjacent ?? { previous: a3, next: null },
              sidebar: sections,
            },
          }
        : notFound(),
    ),
  });
}

const openArticle = async (options) => {
  renderApp(`/articles/${fx.articleDetail.slug}`, { api: articleApi(options) });
  await screen.findByRole("heading", { level: 1, name: fx.articleDetail.title });
};

const sidebarRegion = () => screen.getByRole("complementary", { name: "More to read" });
const mainArticle = () => screen.getByRole("article", { name: fx.articleDetail.title });

describe("article page", () => {
  it("puts the article and the sidebar side by side on wide screens, sidebar after the article", async () => {
    await openArticle();
    const article = mainArticle();
    const aside = sidebarRegion();
    // One layout for every size: a two-column grid from lg, stacked (article first) below.
    const grid = article.parentElement;
    expect(grid).toBe(aside.parentElement);
    expect(grid.className).toMatch(/lg:grid-cols-\[minmax\(0,1fr\)_19rem\]/);
    expect(article.compareDocumentPosition(aside) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Tablets get two sidebar columns below the article; wide screens one beside it.
    expect(aside.className).toMatch(/md:grid-cols-2/);
    expect(aside.className).toMatch(/lg:grid-cols-1/);
    // Nothing sticks to the screen.
    expect(document.querySelector("aside .sticky, aside.sticky")).toBeNull();
  });

  it("keeps the article's reading structure: breadcrumbs, topic, title, byline, image, body", async () => {
    await openArticle({ detail: { author, author_profile: profile } });
    const article = mainArticle();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Positive Mindset" })).toHaveAttribute(
      "href",
      "/topics/positive-mindset",
    );
    expect(within(article).getByRole("link", { name: "Positive Mindset" })).toBeInTheDocument();
    expect(within(article).getByText(fx.articleDetail.subtitle)).toBeInTheDocument();
    const byline = within(article).getAllByRole("link", { name: "Jane Doe" })[0];
    expect(byline).toHaveAttribute("href", "/authors/jane-doe");
    expect(byline).toHaveAttribute("rel", "author");
    expect(
      within(article).getByRole("heading", { level: 2, name: "Notice the thought first" }),
    ).toBeInTheDocument();
    expect(within(article).getByRole("list", { name: "Tags" })).toBeInTheDocument();
    // The lead image is the only eager image (LCP); everything else is lazy.
    const eager = document.querySelectorAll('main img[loading="eager"]');
    expect(eager).toHaveLength(1);
  });

  it("offers share links, the author box, related articles and previous/next", async () => {
    await openArticle({ detail: { author, author_profile: profile } });
    const article = mainArticle();
    const share = within(article).getByRole("list", { name: "Share this article" });
    const facebook = within(share).getByRole("link", { name: /Share on Facebook/ });
    expect(facebook.getAttribute("href")).toContain(
      encodeURIComponent("/articles/reframing-negative-thoughts"),
    );
    expect(facebook).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(share).getByRole("button", { name: "Copy link" })).toBeInTheDocument();

    const about = within(article).getByRole("region", { name: "Jane Doe" });
    expect(within(about).getByText("Jane writes about resilience.")).toBeInTheDocument();
    expect(within(about).getByRole("link", { name: "More articles by Jane Doe" })).toHaveAttribute(
      "href",
      "/authors/jane-doe",
    );

    const related = within(article).getByRole("region", { name: "Related articles" });
    expect(within(related).getByRole("link", { name: a2.title })).toHaveAttribute(
      "href",
      `/articles/${a2.slug}`,
    );
    const nav = within(article).getByRole("navigation", { name: "More articles" });
    expect(within(nav).getByRole("link", { name: /Previous article/ })).toHaveAttribute(
      "href",
      `/articles/${a3.slug}`,
    );
    expect(within(nav).queryByRole("link", { name: /Next article/ })).not.toBeInTheDocument();
  });

  it("leaves the author box out for organisation bylines without a bio", async () => {
    await openArticle();
    expect(screen.queryByText("About the author")).not.toBeInTheDocument();
  });

  it("shows the sidebar sections in the editor's order, without raw visitor counts", async () => {
    await openArticle();
    const order = [...sidebarRegion().querySelectorAll("[data-sidebar-section]")].map(
      (s) => s.dataset.sidebarSection,
    );
    expect(order).toEqual([
      "popular_articles",
      "related_articles",
      "newsletter_cta",
      "featured_articles",
      "topics_grid",
    ]);
    const popular = within(sidebarRegion()).getByRole("region", { name: "Popular articles" });
    const list = within(popular).getByRole("list");
    expect(list.tagName).toBe("OL");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(popular.textContent).not.toMatch(/views|visitors/i);
    const topics = within(sidebarRegion()).getByRole("region", { name: "Explore topics" });
    expect(within(topics).getByRole("link", { name: "Personal Growth" })).toHaveAttribute(
      "href",
      "/topics/personal-growth",
    );
  });

  it("follows a reordered sidebar and leaves empty or hidden sections out", async () => {
    const [popular, related, newsletter, picks, topics] = sidebar({
      popular: { heading: "Popular articles", articles: [] },
      picks: { heading: "Editor's Picks", articles: [] },
    });
    await openArticle({ sections: [topics, related, popular, newsletter, picks] });
    const order = [...sidebarRegion().querySelectorAll("[data-sidebar-section]")].map(
      (s) => s.dataset.sidebarSection,
    );
    expect(order).toEqual(["topics_grid", "related_articles", "newsletter_cta"]);
    expect(screen.queryByRole("region", { name: "Popular articles" })).not.toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("has no sign-up form or invitation in the sidebar while sign-up is closed", async () => {
    await openArticle();
    const card = within(sidebarRegion()).getByRole("region", { name: "The Positive Reset" });
    expect(within(card).getByText("A Better Mindset. A Brighter Life.")).toBeInTheDocument();
    expect(
      within(card).getByText(/Sign-up for The Positive Reset isn.t available on the website/),
    ).toBeInTheDocument();
    expect(within(card).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /subscribe/i })).not.toBeInTheDocument();
  });

  it("shows the double opt-in form with the daily consent wording once sign-up is open", async () => {
    const openSite = {
      ...fx.site,
      newsletter: {
        ...fx.site.newsletter,
        is_open: true,
        consent_text: "Yes, email me The Positive Reset every day.",
        consent_version: "2026-11",
        preferences: [],
        default_preferences: ["weekly"],
      },
    };
    await openArticle({ site: openSite });
    const card = within(sidebarRegion()).getByRole("region", { name: "The Positive Reset" });
    const form = await within(card).findByRole("form", { name: /Subscribe to The Positive Reset/ });
    expect(within(form).getByLabelText(/Email address/)).toBeInTheDocument();
    expect(within(form).getByRole("checkbox", { name: /every day/ })).not.toBeChecked();
  });

  it("keeps the article's SEO: canonical, article metadata and structured data", async () => {
    await openArticle();
    const canonical = document.querySelector('link[rel="canonical"]');
    expect(canonical.href).toMatch(/\/articles\/reframing-negative-thoughts$/);
    expect(document.querySelector('meta[property="og:type"]').content).toBe("article");
    const types = [...document.querySelectorAll('head script[type="application/ld+json"]')].map(
      (s) => JSON.parse(s.textContent)["@type"],
    );
    expect(types).toEqual(["BlogPosting", "BreadcrumbList"]);
  });
});

describe("article sidebar (admin preview)", () => {
  it("explains empty sections instead of hiding them", () => {
    const store = createAppStore({ api: createFakeApi() });
    render(
      <Provider store={store}>
        <MemoryRouter>
          <ArticleSidebar
            preview
            sections={sidebar({ related: { heading: "Related articles", articles: [] } })}
          />
        </MemoryRouter>
      </Provider>,
    );
    const notes = screen.getAllByRole("note").map((n) => n.textContent);
    expect(notes.some((t) => /No related articles/.test(t))).toBe(true);
  });

  it("shows a sponsored booking only while it is live, marked as sponsored", () => {
    const now = Date.now();
    const creative = {
      id: 1,
      sponsor: "Calm Co",
      headline: "Calm Co journals",
      body: "",
      image: null,
      logo: null,
      link: { href: "https://calm.example/", label: "Visit Calm Co" },
      starts_at: new Date(now - 86_400_000).toISOString(),
      ends_at: new Date(now + 86_400_000).toISOString(),
    };
    const store = createAppStore({ api: createFakeApi() });
    const { rerender } = render(
      <Provider store={store}>
        <MemoryRouter>
          <ArticleSidebar
            sections={[
              section("ad", "sponsored_banner", { label: "Sponsored", creatives: [creative] }),
            ]}
          />
        </MemoryRouter>
      </Provider>,
    );
    const link = screen.getByRole("link", { name: "Visit Calm Co" });
    expect(link.getAttribute("rel")).toMatch(/sponsored/);
    expect(screen.getByText("Sponsored")).toBeInTheDocument();
    rerender(
      <Provider store={store}>
        <MemoryRouter>
          <ArticleSidebar
            sections={[section("ad", "sponsored_banner", { label: "Sponsored", creatives: [] })]}
          />
        </MemoryRouter>
      </Provider>,
    );
    expect(screen.queryByText("Calm Co journals")).not.toBeInTheDocument();
  });
});

describe("topic pages", () => {
  const many = Array.from({ length: 14 }, (_, i) => ({
    ...a1,
    id: `t${i}`,
    slug: `mindset-story-${i + 1}`,
    title: `Mindset story ${i + 1}`,
  }));
  const api = () =>
    createFakeApi({
      getArticles: vi.fn(async ({ topic, page = 1, page_size = 12 } = {}) => {
        const items = topic === "positive-mindset" ? many : [];
        const total_pages = Math.max(1, Math.ceil(items.length / page_size));
        return {
          data: items.slice((page - 1) * page_size, page * page_size),
          meta: {
            pagination: {
              page,
              page_size,
              total: items.length,
              total_pages,
              has_next: page < total_pages,
              has_prev: page > 1,
            },
          },
        };
      }),
    });

  it("opens with a featured story, then the latest in the topic, pagination and other topics", async () => {
    renderApp("/topics/positive-mindset", { api: api() });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Positive Mindset" }),
    ).toBeInTheDocument();
    const featured = await screen.findByRole("link", { name: "Mindset story 1" });
    expect(featured.closest("h3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Latest in Positive Mindset" }),
    ).toBeInTheDocument();
    const pages = screen.getByRole("navigation", { name: "Positive Mindset article pages" });
    expect(within(pages).getByRole("link", { name: "Page 2" })).toHaveAttribute(
      "href",
      "/topics/positive-mindset/page/2",
    );
    const others = screen.getByRole("list", { name: "Other topics" });
    expect(within(others).getByRole("link", { name: "Personal Growth" })).toBeInTheDocument();
    // Topics without articles aren't offered.
    expect(
      within(others).queryByRole("link", { name: "Emotional Well-being" }),
    ).not.toBeInTheDocument();
  });

  it("shows later pages as a plain grid and keeps the page in the title", async () => {
    renderApp("/topics/positive-mindset/page/2", { api: api() });
    expect(await screen.findByRole("link", { name: "Mindset story 13" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "More in Positive Mindset" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(document.title).toMatch(/Page 2/));
    expect(document.querySelector('link[rel="canonical"]').href).toMatch(
      /\/topics\/positive-mindset\/page\/2$/,
    );
  });

  it("has a clean empty state for a topic without articles", async () => {
    renderApp("/topics/emotional-well-being");
    expect(
      await screen.findByRole("heading", { name: "New articles are being written" }),
    ).toBeInTheDocument();
  });
});

describe("authors", () => {
  const authorApi = (list) =>
    createFakeApi({
      getAuthors: vi.fn(async () => ({ data: list })),
      getAuthor: vi.fn(async (slug) =>
        slug === "jane-doe"
          ? {
              data: { author: { ...profile, article_count: 2 }, articles: [a1, a2] },
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
          : notFound(),
      ),
    });

  it("lists the writers who have an author page", async () => {
    renderApp("/authors", {
      api: authorApi([
        { slug: "jane-doe", name: "Jane Doe", article_count: 2, bio: profile.bio, image: null },
      ]),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Authors" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Jane Doe" })).toHaveAttribute(
      "href",
      "/authors/jane-doe",
    );
    expect(screen.getByText("2 articles")).toBeInTheDocument();
  });

  it("says so plainly when no author has a page", async () => {
    renderApp("/authors", { api: authorApi([]) });
    expect(
      await screen.findByRole("heading", { name: "Author profiles aren't published yet" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Read their articles/ })).not.toBeInTheDocument();
  });

  it("shows an author's profile, articles and ProfilePage structured data", async () => {
    renderApp("/authors/jane-doe", { api: authorApi([]) });
    expect(await screen.findByRole("heading", { level: 1, name: "Jane Doe" })).toBeInTheDocument();
    expect(screen.getByText("Jane writes about resilience.")).toBeInTheDocument();
    expect(screen.getByText("2 published articles")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Articles by Jane Doe" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: a1.title })).toHaveAttribute(
      "href",
      `/articles/${a1.slug}`,
    );
    const types = [...document.querySelectorAll('head script[type="application/ld+json"]')].map(
      (s) => JSON.parse(s.textContent)["@type"],
    );
    expect(types).toEqual(["ProfilePage", "BreadcrumbList"]);
  });
});

describe("search", () => {
  it("lists results as article rows with the searched words highlighted", async () => {
    renderApp("/search?q=morning");
    const results = await screen.findByRole("list", { name: "Search results" });
    const link = within(results).getByRole("link", { name: a2.title });
    expect(link).toHaveAttribute("href", `/articles/${a2.slug}`);
    expect(link.querySelector("mark")).toHaveTextContent(/morning/i);
    expect(screen.getByText("1 article found for “morning”.")).toBeInTheDocument();
  });

  it("suggests topics before searching and when nothing matches", async () => {
    renderApp("/search");
    expect(await screen.findByRole("heading", { name: "Explore topics" })).toBeInTheDocument();
  });
});

describe("resources", () => {
  it("lists only resources visitors can get now in the library", () => {
    const list = listedResources([
      { slug: "paid", type: "workbook", availability: "available" },
      { slug: "free", type: "checklist", availability: "free" },
      { slug: "soon", type: "ebook", availability: "coming-soon" },
      { slug: "gone", type: "ebook", availability: "unavailable" },
      { slug: "bundle", type: "bundle", availability: "available" },
    ]);
    expect(list.map((p) => p.slug)).toEqual(["paid", "free"]);
  });
});

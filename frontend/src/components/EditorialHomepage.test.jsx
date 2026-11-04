import { render, screen, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { SectionList } from "@/components/sections/SectionList";
import { createAppStore } from "@/store";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";
import { availableFreeResources } from "@/utils/resources";

const [a1, a2, a3, ...more] = fx.articles;
const featuredTopics = fx.topics.filter((t) => t.featured);

const section = (key, type, variant, data, design = {}) => ({
  key,
  type,
  variant,
  design: { background: "ivory", spacing: "md", ...design },
  devices: "all",
  data,
});

const resources = [
  {
    slug: "morning-reset-checklist",
    title: "Morning Reset Checklist",
    description: "Five quiet steps for a calmer start.",
    type_label: "Checklist",
    is_free: true,
    cover: null,
    cover_theme: "sage",
  },
  {
    slug: "boundaries-workbook",
    title: "Boundaries Workbook",
    description: "Practise saying no with kindness.",
    type_label: "Workbook",
    is_free: false,
    cover: null,
    cover_theme: "gold",
  },
];

/** The editorial homepage as GET /pages/resolve?path=/ returns it (editorial defaults). */
function editorialPage(overrides = {}) {
  const data = {
    featured: { heading: "Featured stories", articles: [a1, a2, a3] },
    latest: {
      heading: "Latest articles",
      articles: more.length ? more : [a3],
      cta: { label: "View all articles", href: "/articles", external: false, style: "outline" },
    },
    topics: { heading: "Explore topics", topics: featuredTopics },
    picks: { heading: "Editor's Picks", articles: [a2] },
    popular: { heading: "Popular articles", articles: [a3, a1] },
    newsletter: {
      eyebrow: "Daily newsletter",
      heading: "",
      description: "One thoughtful email each day.",
      show_learn_more: true,
      newsletter_name: "The Positive Reset",
      is_open: false,
    },
    resources: { heading: "Free resources", resources },
    byTopic: {
      heading: "More to read by topic",
      groups: [{ topic: featuredTopics[0], articles: [a1] }],
    },
    ...overrides,
  };
  return {
    ...fx.homePage,
    sections: [
      section("featured", "featured_articles", "lead_with_side", data.featured),
      section("latest", "latest_articles", "grid_3", data.latest),
      section("topics", "topics_grid", "cards_3", data.topics, { background: "cream" }),
      section("editors-picks", "article_collection", "grid_4", data.picks),
      section("popular", "popular_articles", "numbered", data.popular),
      section("newsletter", "newsletter_cta", "panel", data.newsletter),
      section("resources", "resource_showcase", "cards_3", data.resources),
      section("by-topic", "topic_articles", "columns", data.byTopic),
      section("about", "brand_intro", "text_only", {
        eyebrow: "About us",
        heading: "About Think Positive Always",
        body: "Think Positive Always exists to help people develop a healthier mindset.",
        cta: null,
        media: null,
        stat_value: null,
      }),
    ],
  };
}

function apiFor(page, site = fx.site) {
  return createFakeApi({
    getPage: vi.fn(async () => ({ data: page })),
    getSite: vi.fn(async () => ({ data: site })),
  });
}

const sectionHeading = (name) => screen.queryByRole("heading", { level: 2, name });

describe("editorial homepage", () => {
  it("leads with a large story and smaller stories alongside, under one hidden page title", async () => {
    renderApp("/", { api: apiFor(editorialPage()) });
    const featured = await screen.findByRole("region", { name: "Featured stories" });
    // The editorial page opens with stories, so the h1 is the site name (visually hidden).
    expect(screen.getByRole("heading", { level: 1, name: "Think Positive Always" })).toHaveClass(
      "sr-only",
    );
    const titles = within(featured)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titles).toEqual([a1.title, a2.title, a3.title]);
    expect(within(featured).getByRole("link", { name: a1.title })).toHaveAttribute(
      "href",
      `/articles/${a1.slug}`,
    );
    // Only the lead image of the first section loads eagerly (the likely LCP image).
    const eager = featured.querySelectorAll('img[loading="eager"]');
    expect(eager.length).toBeLessThanOrEqual(1);
  });

  it("shows every section in order with real links and no placeholder copy", async () => {
    renderApp("/", { api: apiFor(editorialPage()) });
    await screen.findByRole("region", { name: "Featured stories" });
    const order = [...document.querySelectorAll("main [data-section]")].map(
      (s) => s.dataset.section,
    );
    expect(order).toEqual([
      "featured_articles",
      "latest_articles",
      "topics_grid",
      "article_collection",
      "popular_articles",
      "newsletter_cta",
      "resource_showcase",
      "topic_articles",
      "brand_intro",
    ]);
    expect(sectionHeading("Explore topics")).toBeInTheDocument();
    expect(sectionHeading("Editor's Picks")).toBeInTheDocument();
    // Popular: an ordered list (the large numbers are decorative).
    const popular = screen.getByRole("region", { name: "Popular articles" });
    const items = within(within(popular).getByRole("list")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(popular).getByRole("list").tagName).toBe("OL");
    // Articles by topic: one sub-heading per topic and a link to the topic page.
    const byTopic = screen.getByRole("region", { name: "More to read by topic" });
    expect(
      within(byTopic).getByRole("heading", { level: 3, name: featuredTopics[0].name }),
    ).toBeInTheDocument();
    expect(
      within(byTopic).getByRole("link", { name: `More in ${featuredTopics[0].name}` }),
    ).toHaveAttribute("href", `/topics/${featuredTopics[0].slug}`);
    expect(sectionHeading("About Think Positive Always")).toBeInTheDocument();
    expect(screen.queryByText(/coming soon|opening soon|on their way/i)).not.toBeInTheDocument();
  });

  it("shows published resources with their title, description and page link", async () => {
    renderApp("/", { api: apiFor(editorialPage()) });
    const region = await screen.findByRole("region", { name: "Free resources" });
    const cards = within(region).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    const first = within(cards[0]);
    expect(first.getByRole("link", { name: "Morning Reset Checklist" })).toHaveAttribute(
      "href",
      "/shop/morning-reset-checklist",
    );
    expect(first.getByText("Five quiet steps for a calmer start.")).toBeInTheDocument();
    expect(first.getByText("Free")).toBeInTheDocument();
    expect(within(cards[1]).queryByText("Free")).not.toBeInTheDocument();
  });

  it("leaves empty sections out of the website instead of showing placeholders", async () => {
    const page = editorialPage({
      latest: { heading: "Latest articles", articles: [] },
      picks: { heading: "Editor's Picks", articles: [] },
      popular: { heading: "Popular articles", articles: [] },
      resources: { heading: "Free resources", resources: [] },
      byTopic: { heading: "More to read by topic", groups: [] },
      topics: { heading: "Explore topics", topics: [] },
    });
    renderApp("/", { api: apiFor(page) });
    await screen.findByRole("region", { name: "Featured stories" });
    for (const name of [
      "Latest articles",
      "Editor's Picks",
      "Popular articles",
      "Free resources",
      "More to read by topic",
      "Explore topics",
    ]) {
      expect(sectionHeading(name)).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByText(/coming soon|on their way|check back/i)).not.toBeInTheDocument();
  });

  it("explains hidden empty sections in the admin preview", async () => {
    const page = editorialPage({
      picks: { heading: "Editor's Picks", articles: [] },
      resources: { heading: "Free resources", resources: [] },
    });
    const store = createAppStore({ api: apiFor(page) });
    render(
      <Provider store={store}>
        <MemoryRouter>
          <SectionList page={page} preview />
        </MemoryRouter>
      </Provider>,
    );
    const notes = screen.getAllByRole("note").map((n) => n.textContent);
    expect(notes.some((t) => /No published articles/.test(t))).toBe(true);
    expect(notes.some((t) => /No published resources/.test(t))).toBe(true);
    expect(notes.every((t) => /hidden on the website/.test(t))).toBe(true);
  });
});

describe("newsletter readiness", () => {
  it("shows no form and says so plainly while sign-up isn't ready", async () => {
    renderApp("/", { api: apiFor(editorialPage()) });
    const panel = (await screen.findByText("Daily newsletter")).closest("section");
    expect(
      within(panel).getByText(/Sign-up for The Positive Reset isn.t available on the website/),
    ).toBeInTheDocument();
    expect(within(panel).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /subscribe/i })).not.toBeInTheDocument();
    expect(within(panel).queryByText(/opening soon/i)).not.toBeInTheDocument();
  });

  it("shows the real double opt-in form once the backend reports sign-up as open", async () => {
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
    renderApp("/", { api: apiFor(editorialPage(), openSite) });
    const [form] = await screen.findAllByRole("form", { name: /Subscribe to The Positive Reset/ });
    expect(within(form).getByLabelText(/Email address/)).toBeInTheDocument();
    expect(within(form).getByRole("checkbox", { name: /every day/ })).not.toBeChecked(); // consent is never pre-ticked
    expect(screen.queryByText(/isn.t available on the website/)).not.toBeInTheDocument();
  });
});

describe("free resources and switched-off areas", () => {
  const product = (overrides) => ({
    id: overrides.slug,
    type: "checklist",
    type_label: "Checklist",
    title: overrides.slug,
    subtitle: "",
    description: "",
    is_free: true,
    availability: "free",
    prices: [],
    categories: [],
    formats: ["PDF"],
    cover: null,
    cover_theme: "sage",
    ...overrides,
  });

  it("lists only free resources visitors can get now", () => {
    const list = availableFreeResources([
      product({ slug: "free-now" }),
      product({ slug: "paid", is_free: false, availability: "available" }),
      product({ slug: "coming", availability: "coming-soon" }),
      product({ slug: "bundle", type: "bundle" }),
      product({ slug: "unavailable", availability: "unavailable" }),
    ]);
    expect(list.map((p) => p.slug)).toEqual(["free-now"]);
    expect(availableFreeResources(undefined)).toEqual([]);
  });

  it("has no coming-soon placeholders on the free resources page", async () => {
    renderApp("/free-resources");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Free Tools to Support Your Growth" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/coming soon|being prepared|in preparation/i),
    ).not.toBeInTheDocument();
  });

  it("hides the cart while the shop is switched off", async () => {
    renderApp("/", { api: apiFor(editorialPage(), { ...fx.site, features: { shop: false } }) });
    expect(await screen.findByRole("link", { name: "Search articles" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Cart/ })).not.toBeInTheDocument();
  });

  it("keeps the cart when the shop is on", async () => {
    renderApp("/", { api: apiFor(editorialPage(), { ...fx.site, features: { shop: true } }) });
    expect((await screen.findAllByRole("link", { name: /^Cart/ })).length).toBeGreaterThan(0);
  });
});

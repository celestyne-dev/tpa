import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";
import { shortExcerpt } from "@/utils/format";

const [a1, a2, a3, a4, a5] = fx.articles.concat(fx.articles).map((a, i) => ({
  ...a,
  slug: `${a.slug}-${i}`,
  title: `${a.title} (${i + 1})`,
}));

const section = (key, type, variant, data, design = {}) => ({
  key,
  type,
  variant,
  design: { background: "ivory", spacing: "sm", ...design },
  devices: "all",
  data,
});

const eightTopics = [
  "Positive Mindset",
  "Personal Growth",
  "Confidence & Self-Worth",
  "Resilience & Starting Over",
  "Relationships & Boundaries",
  "Habits & Intentional Living",
  "Motivation & Inspiration",
  "Emotional Well-being",
].map((name, i) => ({
  slug: name.toLowerCase().replace(/[^a-z]+/g, "-"),
  name,
  description: `${name} explained in one short sentence. A much longer second sentence that the homepage card should never show in full.`,
  icon: "sun",
  featured: i < 3,
  article_count: 1,
}));

/** The new editorial homepage as GET /pages/resolve?path=/ returns it (default layout). */
function homepage(overrides = {}) {
  const data = {
    featured: { heading: "Featured stories", articles: [a1, a2, a3] },
    latest: {
      heading: "Latest articles",
      articles: [a4, a5],
      cta: { label: "View all articles", href: "/articles", external: false, style: "outline" },
    },
    topics: {
      heading: "Explore by topic",
      description: "Find encouragement for the part of life you are working on now.",
      topics: eightTopics,
    },
    newsletter: {
      eyebrow: "Daily newsletter",
      heading: "",
      description: "One thoughtful email each day.",
      show_learn_more: true,
      newsletter_name: "The Positive Reset",
      is_open: false,
    },
    mostRead: { heading: "Most read", fallback: false, articles: [a4] },
    resources: {
      heading: "Resources for your growth",
      resources: [
        {
          slug: "morning-reset-checklist",
          title: "Morning Reset Checklist",
          description: "Five quiet steps.",
          type_label: "Checklist",
          is_free: true,
          cover: null,
          cover_theme: "sage",
        },
        {
          slug: "boundaries-workbook",
          title: "Boundaries Workbook",
          description: "Practise saying no.",
          type_label: "Workbook",
          is_free: false,
          cover: null,
          cover_theme: "gold",
        },
      ],
    },
    goodNews: { eyebrow: "Good news", heading: "Real stories of hope and change", articles: [] },
    reflection: { quote: "Small steps, taken consistently, change everything." },
    ...overrides,
  };
  return {
    ...fx.homePage,
    sections: [
      section("featured", "featured_articles", "lead_with_two", data.featured),
      section("latest", "latest_articles", "grid_3", data.latest),
      section("topics", "topics_grid", "compact_4", data.topics, { background: "cream" }),
      section("newsletter", "newsletter_cta", "panel", data.newsletter),
      section("most-read", "popular_articles", "grid_4", data.mostRead),
      section("resources", "resource_showcase", "cards_3", data.resources),
      section("good-news", "article_collection", "grid_3", data.goodNews),
      section("reflection", "quote", "minimal", data.reflection, { align: "center" }),
    ],
  };
}

const apiFor = (page, site = fx.site) =>
  createFakeApi({
    getPage: vi.fn(async () => ({ data: page })),
    getSite: vi.fn(async () => ({ data: site })),
    getTopics: vi.fn(async () => ({ data: eightTopics })),
  });

describe("editorial homepage sections", () => {
  it("opens with a lead story and two picture stories, one eager image only", async () => {
    renderApp("/", { api: apiFor(homepage()) });
    const featured = await screen.findByRole("region", { name: "Featured stories" });
    const titles = within(featured)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titles).toEqual([a1.title, a2.title, a3.title]);
    expect(featured.querySelectorAll('img[loading="eager"]').length).toBeLessThanOrEqual(1);
    for (const img of featured.querySelectorAll("img")) expect(img).toHaveAttribute("alt");
  });

  it("shows the sections in order and leaves the empty good-news picks out", async () => {
    renderApp("/", { api: apiFor(homepage()) });
    await screen.findByRole("region", { name: "Featured stories" });
    const order = [...document.querySelectorAll("main [data-section]")].map(
      (s) => s.dataset.section,
    );
    expect(order).toEqual([
      "featured_articles",
      "latest_articles",
      "topics_grid",
      "newsletter_cta",
      "popular_articles",
      "resource_showcase",
      "quote",
    ]);
    expect(screen.queryByText("Real stories of hope and change")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Reflection" })).toHaveTextContent(
      "Small steps, taken consistently, change everything.",
    );
  });

  it("lists the eight topics as compact cards with short excerpts", async () => {
    renderApp("/", { api: apiFor(homepage()) });
    const region = await screen.findByRole("region", { name: "Explore by topic" });
    const cards = within(region).getAllByRole("listitem");
    expect(cards).toHaveLength(8);
    expect(
      within(cards[3]).getByRole("link", { name: "Resilience & Starting Over" }),
    ).toHaveAttribute("href", "/topics/resilience-starting-over");
    expect(
      within(cards[0]).getByText("Positive Mindset explained in one short sentence."),
    ).toBeInTheDocument();
    expect(region).not.toHaveTextContent(/much longer second sentence/);
  });

  it("names the featured fallback honestly when there are no reading statistics", async () => {
    const page = homepage({
      mostRead: { heading: "Editor's picks", fallback: true, articles: [a5] },
    });
    renderApp("/", { api: apiFor(page) });
    expect(await screen.findByRole("region", { name: "Editor's picks" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Most read" })).not.toBeInTheDocument();
  });

  it("labels free and premium resources and links each to its own page", async () => {
    renderApp("/", { api: apiFor(homepage()) });
    const region = await screen.findByRole("region", { name: "Resources for your growth" });
    const [free, premium] = within(region).getAllByRole("listitem");
    expect(within(free).getByText("Free")).toBeInTheDocument();
    expect(within(free).getByText("Get it free")).toBeInTheDocument();
    expect(within(premium).getByText("Premium")).toBeInTheDocument();
    expect(within(premium).getByRole("link", { name: "Boundaries Workbook" })).toHaveAttribute(
      "href",
      "/shop/boundaries-workbook",
    );
    // No purchase actions on the homepage: prices and checkout live on the resource page.
    expect(within(region).queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps the collection-only newsletter form, consent and generic thank-you", async () => {
    const user = userEvent.setup();
    const consent = "Yes, send me The Positive Reset, the daily email newsletter.";
    const site = {
      ...fx.site,
      newsletter: {
        ...fx.site.newsletter,
        is_open: true,
        signup_mode: "collection_only",
        confirmation_email: false,
        consent_text: consent,
        consent_version: "2026-11-collection",
      },
    };
    const shopApi = {
      ...createFakeShopApi(),
      subscribe: vi.fn(async () => ({
        data: { status: "received", message: "Thank you." },
      })),
    };
    renderApp("/", { api: apiFor(homepage(), site), shopApi });
    const form = await screen.findByRole("form", { name: /Subscribe to The Positive Reset/ });
    const box = within(form).getByRole("checkbox", { name: consent });
    expect(box).not.toBeChecked();
    expect(within(form).queryByText(/email you to confirm/i)).not.toBeInTheDocument();
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(box);
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(shopApi.subscribe).toHaveBeenCalledTimes(1));
    expect(shopApi.subscribe.mock.calls[0][0]).toMatchObject({
      consent: true,
      consent_version: "2026-11-collection",
    });
    expect(await screen.findByText("Thank you for signing up.")).toBeInTheDocument();
    expect(screen.queryByText(/check your inbox/i)).not.toBeInTheDocument();
  });
});

describe("header navigation", () => {
  const siteWithMenu = (primary) => ({
    ...fx.site,
    navigation: { primary, mobile: [], footer: [], legal: [] },
  });
  const menu = [
    { label: "Home", url: "/" },
    { label: "Articles", url: "/articles" },
    {
      label: "Topics",
      url: null,
      children: [
        { label: "Positive Mindset", url: "/topics/positive-mindset" },
        { label: "Personal Growth", url: "/topics/personal-growth" },
      ],
    },
    { label: "Free Resources", url: "/free-resources" },
    { label: "Newsletter", url: "/newsletter" },
    { label: "About", url: "/about" },
  ];

  it("uses the logo as the home link and leaves Home out of the desktop menu", async () => {
    renderApp("/", { api: apiFor(homepage(), siteWithMenu(menu)) });
    const main = await screen.findByRole("navigation", { name: "Main" });
    await within(main).findByRole("link", { name: "Articles" });
    expect(within(main).queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Think Positive Always — home" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("keeps Home in the mobile menu", async () => {
    const user = userEvent.setup();
    renderApp("/", { api: apiFor(homepage(), siteWithMenu(menu)) });
    await user.click(await screen.findByRole("button", { name: /menu/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
  });

  it("shows the old default Free Resources link as Resources (the library), others as set", async () => {
    renderApp("/", { api: apiFor(homepage(), siteWithMenu(menu)) });
    const main = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(main).findByRole("link", { name: "Resources" })).toHaveAttribute(
      "href",
      "/resources",
    );
    expect(within(main).queryByRole("link", { name: "Free Resources" })).not.toBeInTheDocument();
  });

  it("leaves an editor's own resources label and link exactly as configured", async () => {
    const custom = menu.map((item) =>
      item.label === "Free Resources" ? { label: "Free tools", url: "/free-resources" } : item,
    );
    renderApp("/", { api: apiFor(homepage(), siteWithMenu(custom)) });
    const main = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(main).findByRole("link", { name: "Free tools" })).toHaveAttribute(
      "href",
      "/free-resources",
    );
  });

  it("lists every topic with articles under Topics, keyboard operable", async () => {
    const user = userEvent.setup();
    renderApp("/", { api: apiFor(homepage(), siteWithMenu(menu)) });
    const main = await screen.findByRole("navigation", { name: "Main" });
    const button = await within(main).findByRole("button", { name: "Topics" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    const list = document.getElementById(button.getAttribute("aria-controls"));
    await waitFor(() => expect(within(list).getAllByRole("link")).toHaveLength(8));
    const links = within(list)
      .getAllByRole("link")
      .map((a) => a.textContent);
    // The editor's links first, then the other topics in the site's order.
    expect(links.slice(0, 2)).toEqual(["Positive Mindset", "Personal Growth"]);
    expect(links).toContain("Emotional Well-being");
    for (const link of within(list).getAllByRole("link"))
      expect(link.getAttribute("href")).toMatch(/^\/topics\/[a-z-]+$/);
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
  });
});

describe("shortExcerpt", () => {
  it("keeps the first sentence and cuts long ones at a word", () => {
    expect(shortExcerpt("Reframe difficult moments. And much more.")).toBe(
      "Reframe difficult moments.",
    );
    expect(shortExcerpt("one two three four five six", 12)).toBe("one two…");
    expect(shortExcerpt("")).toBe("");
    expect(shortExcerpt(undefined)).toBe("");
  });
});

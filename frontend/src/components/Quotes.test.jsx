import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { QuoteCollectionsSection } from "@/components/sections/ArticleSections";
import { routes } from "@/config/navigation";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const image = { src: "/media/brave.jpg", alt: "A sunrise over hills", width: 1200, height: 800 };

const collection = {
  id: "90",
  content_type: "quotes",
  slug: "quotes-for-brave-mornings",
  title: "Quotes for Brave Mornings",
  excerpt: "Fifteen quotes on courage, with reflections.",
  topic: { slug: "confidence-self-worth", name: "Confidence" },
  topic_slug: "confidence-self-worth",
  author: { slug: "tpa", name: "Think Positive Always" },
  published_at: "2026-11-01T08:00:00Z",
  updated_at: "2026-11-01T08:00:00Z",
  reading_time_minutes: 4,
  image,
  body: [
    { type: "paragraph", text: "Why these quotes **matter** this week." },
    {
      type: "list",
      ordered: true,
      items: ["Courage is a habit — *Mary Daly*", "Start where you are — Arthur Ashe"],
    },
    { type: "image", image, caption: "Save this one", pin_description: "Brave morning quote" },
    { type: "list", ordered: true, start: 3, items: ["Begin anyway — Unknown"] },
    { type: "exercise", id: "reflection-5", title: "Try this", prompt: "Pick one quote." },
    { type: "key_points", title: "Key points", items: ["Start small"] },
  ],
};

function quotesApi() {
  const defaults = createFakeApi();
  return createFakeApi({
    getQuotes: vi.fn(async (params = {}) => ({
      data: params.featured ? [] : [collection],
      meta: {
        pagination: { page: 1, page_size: 12, total: 1, total_pages: 1 },
        topics: [{ slug: "confidence-self-worth", name: "Confidence", collection_count: 1 }],
      },
    })),
    getQuote: vi.fn(async (slug) =>
      slug === collection.slug
        ? {
            data: {
              collection,
              related_articles: fx.articles.slice(0, 2),
              related_collections: [],
            },
          }
        : defaults.getQuote(slug),
    ),
  });
}

describe("quote collection pages", () => {
  it("renders the numbered quotes, continued numbering, images and attributions", async () => {
    const { container } = renderApp(routes.quote(collection.slug), { api: quotesApi() });
    expect(await screen.findByRole("heading", { level: 1, name: collection.title })).toBeVisible();
    const lists = container.querySelectorAll("ol.quote-list");
    expect(lists).toHaveLength(2);
    expect(lists[0].hasAttribute("start")).toBe(false);
    expect(lists[1].getAttribute("start")).toBe("3"); // 1-2, image, then 3
    expect(within(lists[0]).getByText("Mary Daly").tagName).toBe("EM");
    expect(lists[0].querySelector("li span")).toHaveTextContent("— Mary Daly");
    expect(container.querySelector("p strong")).toHaveTextContent("matter");
    const pin = screen.getByRole("link", { name: /Save to Pinterest/ });
    const href = new URL(pin.getAttribute("href"));
    expect(href.hostname).toBe("www.pinterest.com");
    expect(href.searchParams.get("url")).toMatch(/\/quotes\/quotes-for-brave-mornings$/);
    expect(href.searchParams.get("media")).toMatch(/^https?:\/\/.+\/media\/brave\.jpg$/);
    expect(href.searchParams.get("description")).toBe("Brave morning quote");
    // The existing lesson blocks, read-only (no answer box on a public page).
    expect(screen.getByRole("heading", { name: "Try this" })).toBeVisible();
    expect(screen.getByText("Pick one quote.")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: /response|answer/i })).toBeNull();
    expect(screen.getByText("Start small")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Related articles" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Back to all quote collections/ })).toHaveAttribute(
      "href",
      "/quotes",
    );
  });

  it("lists collections with categories and links to /quotes/…", async () => {
    renderApp(routes.quotes, { api: quotesApi() });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Quote collections" }),
    ).toBeVisible();
    const card = await screen.findByRole("link", { name: collection.title });
    expect(card).toHaveAttribute("href", routes.quote(collection.slug));
    const categories = screen.getByRole("navigation", { name: "Quote categories" });
    expect(within(categories).getByRole("link", { name: "Confidence" })).toHaveAttribute(
      "href",
      "/quotes?topic=confidence-self-worth",
    );
    expect(screen.getByRole("search")).toBeVisible();
  });

  it("an unknown collection is a 404", async () => {
    renderApp("/quotes/not-a-collection", { api: quotesApi() });
    expect(
      await screen.findByRole("heading", { level: 1, name: "This page took a different path" }),
    ).toBeVisible();
  });
});

describe("quote collection cards", () => {
  it("cards link quote collections to /quotes and articles to /articles", () => {
    render(
      <MemoryRouter>
        <ArticleCard article={collection} />
        <ArticleCard article={fx.articles[0]} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: collection.title })).toHaveAttribute(
      "href",
      "/quotes/quotes-for-brave-mornings",
    );
    expect(screen.getByRole("link", { name: fx.articles[0].title })).toHaveAttribute(
      "href",
      `/articles/${fx.articles[0].slug}`,
    );
  });

  it("the homepage section shows its collections and hides when empty", () => {
    const section = (collections) => ({
      key: "q1",
      type: "quote_collections",
      variant: "carousel",
      design: {},
      data: { heading: "Words for the week", collections },
    });
    const { container, rerender } = render(
      <MemoryRouter>
        <QuoteCollectionsSection section={section([collection])} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Words for the week" })).toBeVisible();
    expect(screen.getByRole("link", { name: collection.title })).toHaveAttribute(
      "href",
      "/quotes/quotes-for-brave-mornings",
    );
    rerender(
      <MemoryRouter>
        <QuoteCollectionsSection section={section([])} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

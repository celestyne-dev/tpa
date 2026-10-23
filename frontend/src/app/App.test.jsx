import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import * as fx from "@/test/fixtures";
import { createFakeApi, preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

describe("homepage", () => {
  it("renders the hero and API-driven sections", async () => {
    const { api } = renderApp("/");
    expect(
      await screen.findByRole("heading", { level: 1, name: /A Better Mindset/ }),
    ).toBeInTheDocument();
    const topicsSection = screen.getByRole("region", { name: "Explore What Matters to You" });
    expect(within(topicsSection).getByRole("link", { name: "Positive Mindset" })).toHaveAttribute(
      "href",
      "/topics/positive-mindset",
    );
    // Only featured topics appear on the homepage.
    expect(
      within(topicsSection).queryByRole("link", { name: "Emotional Well-being" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "How to Reframe a Negative Thought" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Inspiration That Goes Beyond Words" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Let's Create Something Meaningful Together" }),
    ).toBeInTheDocument();
    // One resolved page request: the API already includes the featured articles and topics.
    expect(api.getPage).toHaveBeenCalledWith("/");
    expect(api.getArticles).not.toHaveBeenCalled();
    expect(api.getTopics).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(document.title).toBe(
        "Think Positive Always — Practical Inspiration for Personal Growth",
      ),
    );
  });

  it("shows product previews as coming soon with no purchase actions", async () => {
    const api = createFakeApi({
      getProducts: vi.fn(async () => ({
        data: fx.products,
        meta: { display_currencies: ["USD"] },
      })),
    });
    renderApp("/shop", { api });
    expect(await screen.findByRole("heading", { name: "Know Your Worth" })).toBeInTheDocument();
    expect(screen.getAllByText("Coming soon").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: /buy|add to cart|purchase/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument();
  });

  it("shows an honest newsletter coming-soon state and no email form", async () => {
    renderApp("/newsletter");
    expect(await screen.findByText("Sign-ups are opening soon.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("routing", () => {
  it("navigates from the header to the articles page", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    await user.click(within(nav).getByRole("link", { name: "Articles" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Articles" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Articles" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders a 404 page for unknown URLs", async () => {
    renderApp("/does-not-exist");
    expect(
      await screen.findByRole("heading", { name: "This page took a different path" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Page not found | Think Positive Always"));
    expect(document.querySelector('meta[name="robots"]').content).toMatch(/noindex/);
  });

  it("renders every static public route", async () => {
    const pages = {
      "/free-resources": "Free Tools to Support Your Growth",
      "/partner-with-us": "Partner With Think Positive Always",
      "/about": "Practical Inspiration for Real Life",
      "/contact": "Get in Touch",
      "/privacy-policy": "Privacy Policy",
      "/terms": "Terms of Use",
      "/affiliate-disclosure": "Affiliate Disclosure",
    };
    for (const [path, heading] of Object.entries(pages)) {
      const { unmount } = renderApp(path);
      expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
      unmount();
    }
  });
});

describe("articles", () => {
  it("lists articles and filters by topic", async () => {
    const user = userEvent.setup();
    const { api } = renderApp("/articles");
    expect(await screen.findByText("Showing all 3 articles")).toBeInTheDocument();
    const filters = screen.getByRole("group", { name: "Filter articles by topic" });
    // Topics without articles are not offered as filters.
    expect(
      within(filters).queryByRole("button", { name: "Emotional Well-being" }),
    ).not.toBeInTheDocument();

    await user.click(within(filters).getByRole("button", { name: "Personal Growth" }));
    expect(await screen.findByText("Showing 1 article in Personal Growth")).toBeInTheDocument();
    expect(within(filters).getByRole("button", { name: "Personal Growth" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(api.getArticles).toHaveBeenCalledWith(
      expect.objectContaining({ topic: "personal-growth" }),
    );
    expect(screen.getByRole("link", { name: "Why a Weekly Reflection Helps" })).toBeInTheDocument();
  });

  it("renders article details with metadata and structured data", async () => {
    renderApp("/articles/reframing-negative-thoughts");
    expect(
      await screen.findByRole("heading", { level: 1, name: "How to Reframe a Negative Thought" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Notice the thought first" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Sample editorial content")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Keep reading" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Illustration for reframing/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(document.title).toBe("How to Reframe a Negative Thought | Think Positive Always"),
    );
    const canonical = document.querySelector('link[rel="canonical"]');
    expect(canonical.href).toMatch(/\/articles\/reframing-negative-thoughts$/);
    const jsonLd = [...document.querySelectorAll('head script[type="application/ld+json"]')].map(
      (s) => JSON.parse(s.textContent),
    );
    expect(jsonLd.map((d) => d["@type"])).toEqual(["BlogPosting", "BreadcrumbList"]);
  });

  it("shows not-found for unknown article and topic slugs", async () => {
    const { unmount } = renderApp("/articles/unknown-article");
    expect(
      await screen.findByRole("heading", { name: "This page took a different path" }),
    ).toBeInTheDocument();
    unmount();
    renderApp("/topics/unknown-topic");
    expect(
      await screen.findByRole("heading", { name: "This page took a different path" }),
    ).toBeInTheDocument();
  });

  it("renders a topic page with its articles", async () => {
    renderApp("/topics/positive-mindset");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Positive Mindset" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "Designing an Intentional Morning" }),
    ).toBeInTheDocument();
  });
});

describe("API error handling", () => {
  it("shows a recoverable error state when the API is unavailable", async () => {
    const user = userEvent.setup();
    let fail = true;
    const api = createFakeApi();
    const working = api.getArticle;
    api.getArticle = async (slug) => {
      if (fail) throw new ApiError({ code: "network_error", message: "offline" });
      return working(slug);
    };
    renderApp("/articles/reframing-negative-thoughts", { api });
    expect(await screen.findByText("We couldn't load this article")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "How to Reframe a Negative Thought" }),
    ).toBeInTheDocument();
  });

  it("keeps the site shell usable when every request fails", async () => {
    const reject = async () => {
      throw new ApiError({ code: "network_error", message: "offline" });
    };
    const api = createFakeApi({
      getSite: reject,
      getTopics: reject,
      getArticles: reject,
      getProducts: reject,
      getPage: reject,
    });
    renderApp("/", { api });
    expect(await screen.findByText("We couldn't load the homepage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    // The shell keeps working with built-in navigation fallbacks.
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});

describe("mobile navigation", () => {
  it("opens, traps focus, closes on Escape and restores focus", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const trigger = screen.getByRole("button", { name: "Open menu" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Site navigation" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(document.body.style.overflow).toBe("hidden");

    const focusable = dialog.querySelectorAll("a[href], button");
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    expect(first).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab();
    expect(first).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes after choosing a destination", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Shop" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Tools for Your Growth Journey" }),
    ).toBeInTheDocument();
  });
});

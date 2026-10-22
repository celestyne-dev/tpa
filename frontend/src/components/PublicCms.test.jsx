import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render as prerender } from "@/entry-server";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const siteWith = (extra) =>
  createFakeApi({ getSite: async () => ({ data: { ...fx.site, ...extra } }) });

afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
});

describe("CMS pages", () => {
  it("renders a published landing page with SEO, structured data and device visibility", async () => {
    const { container } = renderApp("/spring-reset");
    expect(
      await screen.findByRole("heading", { level: 1, name: "A gentle spring reset" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read the articles/ })).toHaveAttribute(
      "href",
      "/articles",
    );
    // FAQ uses native disclosure widgets (keyboard accessible, readable without JS).
    expect(screen.getByText("How long does it take?").closest("details")).toBeInTheDocument();
    // "Mobile only" sections are hidden from md breakpoint up via CSS.
    expect(container.querySelector('[data-section="quote"]')).toHaveClass("md:hidden");
    await waitFor(() => expect(document.title).toBe("Spring Reset Guide | Think Positive Always"));
    const types = [...document.querySelectorAll('head script[type="application/ld+json"]')].map(
      (s) => JSON.parse(s.textContent)["@type"],
    );
    expect(types).toContain("WebPage");
    const page = [...document.querySelectorAll('head script[type="application/ld+json"]')]
      .map((s) => JSON.parse(s.textContent))
      .find((d) => d["@type"] === "WebPage");
    expect(page.dateModified).toBe("2026-10-22T11:00:00+00:00");
  });

  it("returns a real not-found page for unknown or invalid paths", async () => {
    const { api } = renderApp("/not-a-page");
    expect(
      await screen.findByRole("heading", { name: "This page took a different path" }),
    ).toBeInTheDocument();
    expect(api.getPage).toHaveBeenCalledWith("/not-a-page");
    const second = renderApp("/Weird_Path", { api: createFakeApi() });
    expect(
      screen.getAllByRole("heading", { name: "This page took a different path" }).length,
    ).toBeGreaterThan(0);
    expect(second.api.getPage).not.toHaveBeenCalled();
  });

  it("lets a published CMS page replace a built-in page", async () => {
    const api = siteWith({ cms_overrides: ["/about"] });
    api.getPage = vi.fn(async (path) =>
      path === "/about"
        ? { data: { ...fx.cmsPages["/spring-reset"], path: "/about", title: "About us" } }
        : { data: fx.homePage },
    );
    renderApp("/about", { api });
    expect(
      await screen.findByRole("heading", { level: 1, name: "A gentle spring reset" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Practical Inspiration for Real Life" }),
    ).toBeNull();
  });

  it("prerenders CMS pages to complete HTML", async () => {
    const result = await prerender("/spring-reset", createFakeApi());
    expect(result.status).toBe(200);
    expect(result.html).toContain("A gentle spring reset</h1>");
    expect(result.head).toContain("<title>Spring Reset Guide | Think Positive Always</title>");
    expect(result.head).toContain('"@type":"WebPage"');
    expect((await prerender("/not-published-yet", createFakeApi())).status).toBe(404);
    const home = await prerender("/", createFakeApi());
    expect(home.html).toContain("A Better Mindset.");
    expect(home.html).toContain("Let&#x27;s Create Something Meaningful Together");
  });
});

describe("site-wide CMS content", () => {
  const announcement = (extra = {}) => ({
    id: "1-1",
    message: "A new guided journal is coming soon.",
    cta: { label: "Join the newsletter", href: "/newsletter" },
    variant: "sage",
    dismissible: true,
    target: "all",
    paths: [],
    starts_at: null,
    ends_at: null,
    ...extra,
  });

  it("shows a dismissible announcement and remembers the dismissal", async () => {
    const user = userEvent.setup();
    const api = siteWith({
      announcements: [announcement()],
      generated_at: new Date().toISOString(),
    });
    const { unmount } = renderApp("/", { api });
    const banner = await screen.findByRole("region", { name: "Announcement" });
    expect(within(banner).getByRole("link", { name: /Join the newsletter/ })).toHaveAttribute(
      "href",
      "/newsletter",
    );
    await user.click(within(banner).getByRole("button", { name: "Dismiss announcement" }));
    expect(screen.queryByRole("region", { name: "Announcement" })).toBeNull();
    unmount();
    renderApp("/", { api });
    await screen.findByRole("heading", { level: 1, name: /A Better Mindset/ });
    expect(screen.queryByRole("region", { name: "Announcement" })).toBeNull();
  });

  it("only shows announcements on targeted pages and inside their dates", async () => {
    const past = new Date(Date.now() - 86_400_000).toISOString();
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const api = siteWith({
      generated_at: new Date().toISOString(),
      announcements: [
        announcement({ id: "2-1", message: "Ended already", ends_at: past }),
        announcement({ id: "3-1", message: "Not started", starts_at: future }),
        announcement({
          id: "4-1",
          message: "Articles only",
          target: "paths",
          paths: ["/articles"],
        }),
      ],
    });
    renderApp("/", { api });
    await screen.findByRole("heading", { level: 1, name: /A Better Mindset/ });
    expect(screen.queryByRole("region", { name: "Announcement" })).toBeNull();
    renderApp("/articles", { api: siteWith({ ...(await api.getSite()).data }) });
    expect(await screen.findByText("Articles only")).toBeInTheDocument();
  });

  it("renders the CMS header: dropdown groups, visibility and the header button", async () => {
    const user = userEvent.setup();
    const api = siteWith({
      header: { cta: { label: "Subscribe", href: "/newsletter" } },
      navigation: {
        primary: [
          { label: "Home", url: "/", external: false, open_in_new_tab: false, visibility: "all" },
          {
            label: "Explore",
            url: null,
            visibility: "all",
            children: [
              {
                label: "Articles",
                url: "/articles",
                external: false,
                open_in_new_tab: false,
                visibility: "all",
              },
            ],
          },
          {
            label: "Mobile only",
            url: "/about",
            external: false,
            open_in_new_tab: false,
            visibility: "mobile",
          },
        ],
        mobile: null,
        footer: [],
        legal: [],
      },
    });
    renderApp("/", { api });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    await waitFor(() =>
      expect(within(nav).getByRole("button", { name: "Explore" })).toBeInTheDocument(),
    );
    expect(within(nav).queryByRole("link", { name: "Mobile only" })).toBeNull();
    const toggle = within(nav).getByRole("button", { name: "Explore" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(nav).getByRole("link", { name: "Articles" })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
    expect(screen.getAllByRole("link", { name: "Subscribe" }).length).toBeGreaterThan(0);
  });

  it("renders the footer from settings (copyright template, legal links, promo, contact)", async () => {
    const api = siteWith({
      contact: { email: "hello@example.org", partnerships_email: null },
      footer: {
        text: "Encouragement for every season.",
        show_newsletter_link: false,
        newsletter_label: "",
        show_contact: true,
        show_social: true,
        copyright: "© {year} {site_name}. Made with care.",
        promo: {
          text: "A new journal is coming soon.",
          cta: { label: "Learn more", href: "/newsletter" },
        },
      },
      navigation: {
        primary: [],
        mobile: null,
        footer: [],
        legal: [
          { label: "Privacy", url: "/privacy-policy", external: false, open_in_new_tab: false },
        ],
      },
    });
    renderApp("/", { api });
    const footer = await screen.findByRole("contentinfo");
    await waitFor(() =>
      expect(within(footer).getByText("Encouragement for every season.")).toBeInTheDocument(),
    );
    expect(within(footer).getByText(/Made with care/)).toHaveTextContent(
      `© ${new Date().getFullYear()} Think Positive Always. Made with care.`,
    );
    expect(within(footer).getByRole("link", { name: "Privacy" })).toHaveAttribute(
      "href",
      "/privacy-policy",
    );
    expect(within(footer).getByText("A new journal is coming soon.")).toBeInTheDocument();
    expect(within(footer).getByRole("link", { name: /hello@example.org/ })).toHaveAttribute(
      "href",
      "mailto:hello@example.org",
    );
    expect(within(footer).queryByText(/Learn about The Positive Reset/)).toBeNull();
  });

  it("applies the approved branding presets and the CMS logo", async () => {
    const api = siteWith({
      branding: {
        palette: "evergreen",
        typography: "modern",
        button_shape: "rounded",
        image_style: "soft",
        show_wordmark: false,
        logo: { src: "/media/logo.png", width: 400, height: 120, alt: "" },
        logo_alt: null,
        favicon: null,
      },
    });
    const { container } = renderApp("/", { api });
    await waitFor(() =>
      expect(container.querySelector('[data-palette="evergreen"]')).toBeInTheDocument(),
    );
    const shell = container.querySelector('[data-palette="evergreen"]');
    expect(shell).toHaveAttribute("data-type", "modern");
    expect(shell).toHaveAttribute("data-buttons", "rounded");
    const home = screen.getAllByRole("link", { name: "Think Positive Always — home" })[0];
    expect(home.querySelector("img")).toHaveAttribute("src", "/media/logo.png");
  });
});

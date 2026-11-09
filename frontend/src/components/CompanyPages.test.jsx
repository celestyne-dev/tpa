import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const metric = (metric_type, value, platform, label) => ({
  metric_type,
  label,
  platform,
  value,
  period_label: "",
  source: `${platform} analytics`,
  measured_on: "2026-10-01",
});

const SOCIAL = metric("social_followers", 1200, "LinkedIn", "Social media followers");
const WEBSITE = metric("website_users", 900, "Website", "Website users");

const kit = (overrides = {}) => ({
  about: "Practical positivity.",
  editorial_focus: "Mindset and growth.",
  audience_summary: "",
  audience_geography: "",
  placements_intro: "",
  collaboration_guidelines: "",
  sponsorship_policies: "",
  content_categories: ["Mindset"],
  campaign_formats: [{ name: "Sponsored article", description: "A labelled article." }],
  contact_cta: { label: "Talk to us", href: "/partner-with-us" },
  brand_assets: [],
  placements: [],
  rate_card: [],
  metrics: [SOCIAL, WEBSITE],
  notes: ["", "Rates are indicative."],
  ...overrides,
});

function apiWith({ site = {}, mediaKit = null, page } = {}) {
  return createFakeApi({
    getSite: vi.fn(async () => ({ data: { ...fx.site, ...site } })),
    ...(mediaKit && { getMediaKit: vi.fn(async () => ({ data: mediaKit })) }),
    ...(page && { getPage: vi.fn(async () => ({ data: page })) }),
  });
}

/** Basic accessibility checks every company page must pass. */
function expectAccessibleBasics() {
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  for (const link of screen.getAllByRole("link")) {
    expect(link.textContent.trim() || link.getAttribute("aria-label"), link.outerHTML).toBeTruthy();
  }
  for (const img of document.querySelectorAll("main img")) {
    expect(img.hasAttribute("alt"), img.outerHTML).toBe(true);
  }
}

describe("About", () => {
  it("keeps its content in the new founder-led order, with CTA destinations", async () => {
    renderApp("/about");
    await screen.findByRole("heading", { level: 1, name: "Practical Inspiration for Real Life" });
    const order = [
      "From daily encouragement to a home for growth",
      "For anyone ready to grow",
      "Content you can trust",
      "Keep growing with us",
    ].map((name) => screen.getByRole("heading", { name }));
    for (let i = 1; i < order.length; i += 1) {
      expect(
        order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    expect(screen.getByRole("region", { name: "Our mission" })).toHaveTextContent(
      /Helping people develop a healthier mindset/,
    );
    for (const value of ["Honest encouragement", "Practical wisdom", "Inclusive by design"]) {
      expect(screen.getByRole("heading", { name: value })).toBeInTheDocument();
    }
    expect(screen.getByText(/not a substitute for professional medical/)).toBeInTheDocument();
    const articles = screen.getAllByRole("link", { name: /Read our articles/ });
    articles.forEach((a) => expect(a).toHaveAttribute("href", "/articles"));
    const newsletter = screen.getAllByRole("link", { name: /Join The Positive Reset/ });
    newsletter.forEach((a) => expect(a).toHaveAttribute("href", "/newsletter"));
    // No published media kit: no audience figures, nothing invented.
    expect(screen.queryByRole("region", { name: "The people we write for" })).toBeNull();
    expect(screen.queryByText(/Measured/)).toBeNull();
    expectAccessibleBasics();
  });

  it("shows verified community figures with their date and source when configured", async () => {
    renderApp("/about", { api: apiWith({ mediaKit: kit() }) });
    const region = await screen.findByRole("region", { name: "The people we write for" });
    expect(within(region).getByText("1,200")).toBeInTheDocument();
    expect(
      within(region).getByText(/Measured October 1, 2026\. Source: LinkedIn analytics\./),
    ).toBeInTheDocument();
  });
});

describe("Contact", () => {
  it("separates general, editorial and partnership contacts with addresses from Settings", async () => {
    renderApp("/contact", {
      api: apiWith({
        site: { contact: { email: "hello@example.com", partnerships_email: "brands@example.com" } },
      }),
    });
    const general = (await screen.findByRole("heading", { name: "General inquiries" })).closest(
      "li",
    );
    expect(within(general).getByRole("link", { name: /hello@example.com/ })).toHaveAttribute(
      "href",
      "mailto:hello@example.com",
    );
    const editorial = screen
      .getByRole("heading", { name: "Editorial feedback and corrections" })
      .closest("li");
    expect(within(editorial).getByRole("link", { name: /hello@example.com/ })).toHaveAttribute(
      "href",
      "mailto:hello@example.com?subject=Editorial%20feedback",
    );
    const partners = screen
      .getByRole("heading", { name: "Advertising and partnerships" })
      .closest("li");
    expect(within(partners).getByRole("link", { name: /brands@example.com/ })).toBeInTheDocument();
    expect(within(partners).getByRole("link", { name: /Partner with us/ })).toHaveAttribute(
      "href",
      "/partner-with-us",
    );
    const notice = screen.getByRole("complementary", { name: "Need urgent support?" });
    expect(notice).toHaveTextContent(/not a crisis or counselling service/);
    expect(document.querySelector("main form")).toBeNull();
    expectAccessibleBasics();
  });

  it("explains when no address is configured instead of inventing one", async () => {
    renderApp("/contact");
    await screen.findByRole("heading", { name: "General inquiries" });
    expect(screen.queryAllByRole("link", { name: /@/ })).toHaveLength(0);
    expect(screen.getAllByText(/will be published on this page shortly/).length).toBe(2);
  });
});

describe("Partner With Us", () => {
  it("keeps the inquiry form, and every inquiry button jumps straight to it", async () => {
    renderApp("/partner-with-us", { shopApi: createFakeShopApi() });
    await screen.findByRole("heading", { level: 1, name: "Partner With Think Positive Always" });
    const buttons = screen.getAllByRole("link", { name: /Make an inquiry/ });
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    buttons.forEach((b) => expect(b).toHaveAttribute("href", "#partnership-inquiry"));
    const form = document.getElementById("partnership-inquiry");
    expect(within(form).getByRole("button", { name: "Send inquiry" })).toBeInTheDocument();
    expect(within(form).getByRole("checkbox")).not.toBeChecked();
    for (const name of [
      "A community that values growth",
      "Ways we can work together",
      "Reasons to partner with us",
      "Partnerships built on shared values",
      "Media kit",
      "Ready to start a conversation?",
    ]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    // No verified figures: an honest note, and no figures section.
    expect(
      screen.getByText(/will be published in our media kit as dated measurements/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Measured audience figures" })).toBeNull();
    expectAccessibleBasics();
  });

  it("shows verified figures and links to the media kit once published", async () => {
    renderApp("/partner-with-us", {
      api: apiWith({ mediaKit: kit(), site: { media_kit_url: "https://cdn.example.com/kit.pdf" } }),
      shopApi: createFakeShopApi(),
    });
    expect(
      await screen.findByRole("heading", { name: "Measured audience figures" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View the Think Positive Always media kit/ }),
    ).toHaveAttribute("href", "/advertise");
    expect(
      screen.getByRole("link", { name: /Download the Think Positive Always media kit/ }),
    ).toHaveAttribute("href", "https://cdn.example.com/kit.pdf");
  });
});

describe("Advertise", () => {
  it("invites brands to ask for details while the media kit is being prepared", async () => {
    renderApp("/advertise");
    expect(
      await screen.findByRole("heading", { name: "Our media kit is being prepared" }),
    ).toBeInTheDocument();
    const links = screen.getAllByRole("link", {
      name: /Start a partnership inquiry|Partner with us/,
    });
    links.forEach((a) =>
      expect(a.getAttribute("href")).toBe("/partner-with-us#partnership-inquiry"),
    );
    expect(screen.queryByText(/Measured/)).toBeNull();
    expectAccessibleBasics();
  });

  it("splits verified social and website figures and offers the download", async () => {
    renderApp("/advertise", {
      api: apiWith({ mediaKit: kit(), site: { media_kit_url: "https://cdn.example.com/kit.pdf" } }),
    });
    const social = await screen.findByRole("heading", { name: "Social audience" });
    const website = screen.getByRole("heading", { name: "Website audience" });
    expect(social.parentElement).toHaveTextContent("1,200");
    expect(website.parentElement).toHaveTextContent("900");
    expect(screen.getAllByRole("link", { name: /Download the media kit/ })[0]).toHaveAttribute(
      "href",
      "https://cdn.example.com/kit.pdf",
    );
    expect(screen.getByRole("heading", { name: "Sponsored article" })).toBeInTheDocument();
    expectAccessibleBasics();
  });
});

const section = (key, type, variant, data, extra = {}) => ({
  key,
  type,
  variant,
  design: {},
  devices: "all",
  data,
  ...extra,
});

function cmsPage(path, title, sections) {
  return {
    ...fx.cmsPages["/spring-reset"],
    path,
    title,
    breadcrumbs: [
      { name: "Home", path: "/" },
      { name: title, path },
    ],
    sections,
  };
}

describe("company pages built in the CMS", () => {
  it("renders contact cards, a notice and a text-only story in the editor's order", async () => {
    const page = cmsPage("/contact", "Contact", [
      section("header", "page_header", "default", {
        eyebrow: "Contact",
        heading: "Say hello",
        intro: "",
        media: null,
      }),
      section("story", "image_text", "image_right", {
        eyebrow: "",
        heading: "Our story",
        body: "Text without a photo.",
        bullets: [],
        media: null,
      }),
      section("cards", "contact_cards", "cards_3", {
        heading: "Ways to reach us",
        intro: "",
        fallback: "Coming soon.",
        items: [
          {
            icon: "pen-line",
            title: "Corrections",
            text: "",
            email: "general",
            cta_label: "",
            cta_url: "",
          },
          {
            icon: "",
            title: "Partnerships",
            text: "",
            email: "none",
            cta_label: "Partner with us",
            cta_url: "/partner-with-us#partnership-inquiry",
          },
        ],
      }),
      section("notice", "notice_panel", "important", {
        heading: "Not a crisis service",
        body: "Please contact local emergency services.",
        cta: null,
      }),
      section(
        "mobile-only",
        "notice_panel",
        "calm",
        {
          heading: "Phones only",
          body: "Shown on phones.",
          cta: null,
        },
        { devices: "mobile" },
      ),
    ]);
    renderApp("/contact", {
      api: apiWith({
        site: {
          cms_overrides: ["/contact"],
          contact: { email: "hi@example.com", partnerships_email: "" },
        },
        page,
      }),
    });
    const title = await screen.findByRole("heading", { level: 1, name: "Say hello" });
    const story = screen.getByRole("heading", { name: "Our story" });
    const cards = screen.getByRole("heading", { name: "Ways to reach us" });
    const notice = screen.getByRole("heading", { name: "Not a crisis service" });
    for (const [a, b] of [
      [title, story],
      [story, cards],
      [cards, notice],
    ]) {
      expect(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    // A story without an image has no empty image frame.
    const storySection = story.closest("section");
    expect(storySection.querySelector(".bg-beige")).toBeNull();
    const corrections = screen.getByRole("heading", { name: "Corrections" }).closest("li");
    expect(within(corrections).getByRole("link", { name: /hi@example.com/ })).toHaveAttribute(
      "href",
      "mailto:hi@example.com",
    );
    const partnerships = screen.getByRole("heading", { name: "Partnerships" }).closest("li");
    expect(within(partnerships).queryByText("Coming soon.")).toBeNull();
    expect(within(partnerships).getByRole("link", { name: /Partner with us/ })).toHaveAttribute(
      "href",
      "/partner-with-us#partnership-inquiry",
    );
    expect(screen.getByRole("heading", { name: "Phones only" }).closest("section")).toHaveClass(
      "md:hidden",
    );
  });

  it("hides audience figures until verified ones exist, and anchors the inquiry form", async () => {
    const page = cmsPage("/partner-with-us", "Partner", [
      section("hero", "hero", "centered", {
        eyebrow: "",
        heading: "Work with us",
        highlight: "",
        body: "",
        media: null,
        primary_cta: {
          label: "Make an inquiry",
          href: "/partner-with-us#partnership-inquiry",
          external: false,
          style: "",
        },
        secondary_cta: null,
      }),
      section("none", "audience_metrics", "cards", { heading: "Nothing yet", metrics: [] }),
      section("figures", "audience_metrics", "cards", {
        heading: "Our audience",
        metrics: [SOCIAL],
      }),
      section("form", "partnership_inquiry", "panel", {
        heading: "Tell us about your organisation",
        description: "",
        collaboration_types: [],
        budget_ranges: [],
        privacy_notice_version: "1",
      }),
    ]);
    renderApp("/partner-with-us", {
      api: apiWith({ site: { cms_overrides: ["/partner-with-us"] }, page }),
      shopApi: createFakeShopApi(),
    });
    await screen.findByRole("heading", { level: 1, name: "Work with us" });
    // Same-page anchor: a plain link the browser scrolls with.
    expect(screen.getByRole("link", { name: /Make an inquiry/ })).toHaveAttribute(
      "href",
      "#partnership-inquiry",
    );
    expect(screen.queryByRole("heading", { name: "Nothing yet" })).toBeNull();
    const figures = screen.getByRole("region", { name: "Our audience" });
    expect(figures).toHaveTextContent(/Measured October 1, 2026\. Source: LinkedIn analytics\./);
    const form = document.getElementById("partnership-inquiry");
    await waitFor(() =>
      expect(within(form).getByRole("button", { name: "Send inquiry" })).toBeInTheDocument(),
    );
  });
});

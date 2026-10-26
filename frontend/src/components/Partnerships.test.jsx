import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { SponsoredLabel } from "@/components/articles/SponsoredLabel";
import { PartnershipInquiryForm } from "@/components/partnerships/PartnershipInquiryForm";
import { ShopApiContext } from "@/components/products/shopApiContext";
import { SectionList } from "@/components/sections/SectionList";
import { render as prerender } from "@/entry-server";
import { ApiError } from "@/services/apiClient";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

afterEach(() => {
  vi.useRealTimers();
});

const sponsorship = {
  label: "Sponsored Content",
  sponsor: "Calm Co",
  disclosure: "This article was produced in paid partnership with Calm Co.",
  links: ["https://calm.example.com/offer"],
};
const body = [
  { type: "paragraph", text: "Intro." },
  { type: "button", label: "Get the offer", href: "https://calm.example.com/offer" },
  { type: "button", label: "Further reading", href: "https://organic.example.org/study" },
];

const sponsoredApi = () =>
  createFakeApi({
    getArticle: vi.fn(async () => ({
      data: { article: { ...fx.articleDetail, sponsorship, body }, related: [] },
    })),
  });

describe("sponsored articles", () => {
  it("labels paid content near the title and marks only paid links sponsored", async () => {
    renderApp(`/articles/${fx.articleDetail.slug}`, { api: sponsoredApi() });
    const heading = await screen.findByRole("heading", { level: 1 });
    const label = screen.getByText("Sponsored Content");
    expect(heading.parentElement).toContainElement(label);
    expect(screen.getByText("Calm Co")).toBeInTheDocument();
    expect(screen.getByText(sponsorship.disclosure)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Get the offer/ })).toHaveAttribute(
      "rel",
      "sponsored noopener noreferrer",
    );
    expect(screen.getByRole("link", { name: /Further reading/ })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("prerendered HTML carries the same disclosure and rel attributes", async () => {
    const { html } = await prerender(`/articles/${fx.articleDetail.slug}`, sponsoredApi());
    expect(html).toContain("Sponsored Content");
    expect(html).toContain(sponsorship.disclosure);
    expect(html).toMatch(
      /href="https:\/\/calm\.example\.com\/offer"[^>]*rel="sponsored noopener noreferrer"|rel="sponsored noopener noreferrer"[^>]*href="https:\/\/calm\.example\.com\/offer"/,
    );
    expect(html).not.toMatch(/organic\.example\.org\/study"[^>]*rel="sponsored/);
  });

  it("organic articles show no sponsorship label", () => {
    const html = renderToString(
      <MemoryRouter>
        <SponsoredLabel sponsorship={null} />
        <ArticleBody blocks={body} />
      </MemoryRouter>,
    );
    expect(html).not.toContain("Sponsored");
    expect(html).not.toContain('rel="sponsored');
  });
});

const now = Date.now();
const creative = (overrides = {}) => ({
  id: 1,
  sponsor: "Calm Co",
  headline: "Breathe better",
  body: "A calmer week.",
  image: null,
  logo: null,
  link: { href: "https://calm.example.com/offer", label: "Learn more", sponsored: true },
  starts_at: new Date(now - 3600_000).toISOString(),
  ends_at: new Date(now + 3600_000).toISOString(),
  label: "Sponsored",
  ...overrides,
});
const section = (type, data, variant = "card") => ({
  key: `s-${type}`,
  type,
  variant,
  design: {},
  data,
});
const renderSections = (sections) =>
  render(
    <MemoryRouter>
      <SectionList page={{ title: "Test", sections }} />
    </MemoryRouter>,
  );

describe("partnership page-builder sections", () => {
  it("renders a live sponsored banner with its label and rel=sponsored", () => {
    renderSections([section("sponsored_banner", { label: "Sponsored", creatives: [creative()] })]);
    expect(screen.getByText("Sponsored")).toBeInTheDocument();
    expect(screen.getByText(/Paid partnership with/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Learn more/ })).toHaveAttribute(
      "rel",
      "sponsored noopener noreferrer",
    );
  });

  it("hides creatives whose booking window has ended once the page is live", () => {
    const expired = creative({
      starts_at: new Date(now - 7200_000).toISOString(),
      ends_at: new Date(now - 60_000).toISOString(),
    });
    renderSections([section("sponsored_banner", { label: "Sponsored", creatives: [expired] })]);
    expect(screen.queryByText("Breathe better")).not.toBeInTheDocument();
    renderSections([section("sponsored_banner", { label: "Sponsored", creatives: [] })]);
    expect(screen.queryByText("Paid partnership with")).not.toBeInTheDocument();
  });

  it("always shows the affiliate disclosure beside recommendations", () => {
    const data = {
      heading: "Picks",
      disclosure: "Some links are affiliate links; we may earn a commission at no extra cost.",
      links: [
        {
          id: 3,
          name: "Calm journal",
          merchant: "Bookshop",
          href: "/api/v1/go/calm-journal",
          note: "Daily use",
          sponsored: true,
        },
      ],
    };
    const { container } = renderSections([section("affiliate_recommendations", data, "cards")]);
    const block = container.querySelector('[data-section="affiliate_recommendations"]');
    expect(within(block).getByText(data.disclosure)).toBeInTheDocument();
    expect(within(block).getByRole("link", { name: /Calm journal/ })).toHaveAttribute(
      "rel",
      "sponsored",
    );
  });

  it("server-renders paid sections with labels and rel attributes for prerendering", () => {
    const html = renderToString(
      <MemoryRouter>
        <SectionList
          page={{
            title: "Test",
            sections: [
              section(
                "sponsor_logos",
                { heading: "Sponsors", label: "Sponsored", creatives: [creative()] },
                "strip",
              ),
              section(
                "brand_spotlight",
                { eyebrow: "Spotlight", label: "Sponsored", creatives: [creative()] },
                "split",
              ),
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(html.match(/rel="sponsored noopener noreferrer"/g)).toHaveLength(2);
    expect(html).toContain("Sponsored by");
  });

  it("shows audience measurements with source and date in the media kit block", () => {
    renderSections([
      section(
        "media_kit_summary",
        {
          heading: "Advertise",
          metrics: [
            {
              metric_type: "social_followers",
              label: "Social media followers",
              platform: "LinkedIn",
              value: 1200,
              source: "LinkedIn analytics",
              measured_on: "2026-10-01",
            },
          ],
        },
        "panel",
      ),
    ]);
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(
      screen.getByText(/Measured 2026-10-01\. Source: LinkedIn analytics\./),
    ).toBeInTheDocument();
  });
});

describe("partnership inquiry form", () => {
  const fill = async (user) => {
    await user.type(screen.getByLabelText("Organisation"), "Bright Org");
    await user.type(screen.getByLabelText("Your name"), "Sam Lee");
    await user.type(screen.getByLabelText("Business email"), "sam@bright.example.com");
    await user.type(screen.getByLabelText("Message"), "We'd like to sponsor a series.");
    await user.click(screen.getByLabelText(/I have read the privacy notice/));
  };
  const renderForm = (shopApi) =>
    render(
      <MemoryRouter>
        <ShopApiContext.Provider value={shopApi}>
          <PartnershipInquiryForm />
        </ShopApiContext.Provider>
      </MemoryRouter>,
    );

  it("confirms receipt only when the server stored the inquiry", async () => {
    const shopApi = {
      submitPartnershipInquiry: vi.fn(async () => ({
        data: {
          status: "received",
          message: "Thank you. Your inquiry has been received.",
          reference: "PI-00001",
        },
      })),
    };
    const user = userEvent.setup();
    renderForm(shopApi);
    await user.click(screen.getByRole("button", { name: "Send inquiry" }));
    expect(shopApi.submitPartnershipInquiry).not.toHaveBeenCalled(); // validated first
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Send inquiry" }));
    expect(await screen.findByRole("status")).toHaveTextContent("PI-00001");
    const sent = shopApi.submitPartnershipInquiry.mock.calls[0][0];
    expect(sent.privacy_consent).toBe(true);
    expect(sent.company_fax).toBe("");
  });

  it("never claims success when the inquiry wasn't confirmed or was rate limited", async () => {
    const user = userEvent.setup();
    const unconfirmed = {
      submitPartnershipInquiry: vi.fn(async () => ({ data: { status: "accepted" } })),
    };
    const { unmount } = renderForm(unconfirmed);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Send inquiry" }));
    expect(
      await screen.findByText(/couldn't confirm your inquiry was received/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    unmount();
    const limited = {
      submitPartnershipInquiry: vi.fn(() =>
        Promise.reject(new ApiError({ status: 429, code: "rate_limited", message: "Too many" })),
      ),
    };
    renderForm(limited);
    await fill(user);
    await act(() => user.click(screen.getByRole("button", { name: "Send inquiry" })));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many attempts/);
  });
});

describe("media kit page", () => {
  it("shows an honest notice before the media kit is published", async () => {
    renderApp("/advertise");
    expect(await screen.findByText("Our media kit is being prepared")).toBeInTheDocument();
  });

  it("shows published measurements with their source and date", async () => {
    const api = createFakeApi({
      getMediaKit: vi.fn(async () => ({
        data: {
          about: "Practical positivity.",
          editorial_focus: "",
          audience_summary: "",
          audience_geography: "",
          placements_intro: "",
          collaboration_guidelines: "",
          sponsorship_policies: "",
          content_categories: [],
          campaign_formats: [],
          contact_cta: { label: "Talk to us", href: "/partner-with-us" },
          show_rate_card: false,
          show_metrics: true,
          show_placements: true,
          brand_assets: [],
          placements: [],
          rate_card: [],
          metrics: [
            {
              metric_type: "social_followers",
              label: "Social media followers",
              platform: "LinkedIn",
              value: 1200,
              period_label: "",
              source: "LinkedIn analytics",
              measured_on: "2026-10-01",
            },
          ],
          notes: ["", "Rates are indicative."],
        },
      })),
    });
    renderApp("/advertise", { api });
    expect(await screen.findByText("Practical positivity.")).toBeInTheDocument();
    expect(screen.getByText(/Social media followers are not website visitors/)).toBeInTheDocument();
    expect(
      screen.getByText(/Measured 2026-10-01\. Source: LinkedIn analytics\./),
    ).toBeInTheDocument();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import copy from "@/data/company/companyPages.json";
import { ApiError } from "@/services/apiClient";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, notFound, renderApp } from "@/test/utils";

const KIT = {
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
};

const serverError = () =>
  Promise.reject(new ApiError({ status: 500, code: "server_error", message: "Server error" }));

function renderAdvertise(getMediaKit, options = {}) {
  const api = createFakeApi({ getMediaKit: vi.fn(getMediaKit) });
  renderApp("/advertise", { api, ...options });
  return api;
}

const ERROR_TEXT = new RegExp(copy.advertise.error.heading.replace(/'/g, "."));

describe("media kit loading states on /advertise", () => {
  it("shows a placeholder, not an error, while the media kit is loading", async () => {
    renderAdvertise(() => new Promise(() => {}));
    expect(
      await screen.findByRole("heading", { level: 1, name: copy.advertise.title }),
    ).toBeInTheDocument();
    expect(screen.getByText("Loading the media kit…")).toBeInTheDocument();
    expect(screen.queryByText(ERROR_TEXT)).toBeNull();
    expect(screen.queryByText(/couldn.t load/i)).toBeNull();
    expect(screen.queryByText(copy.advertise.pending.heading)).toBeNull();
  });

  it("treats a 404 as 'not published yet' and asks only once", async () => {
    const api = renderAdvertise(() => notFound("The media kit has not been published yet."));
    expect(
      await screen.findByRole("heading", { name: copy.advertise.pending.heading }),
    ).toBeInTheDocument();
    expect(screen.queryByText(ERROR_TEXT)).toBeNull();
    for (const item of copy.advertise.pending.items) {
      expect(screen.getByText(item)).toBeInTheDocument();
    }
    const inquiry = screen.getAllByRole("link", {
      name: /Start a partnership inquiry|Partner with us/,
    });
    inquiry.forEach((a) =>
      expect(a).toHaveAttribute("href", "/partner-with-us#partnership-inquiry"),
    );
    await waitFor(() => expect(api.getMediaKit).toHaveBeenCalledTimes(1));
  });

  it("does not ask again when the prerendered page already knows the kit isn't published", async () => {
    const api = renderAdvertise(() => notFound(), {
      preloadedState: { mediaKit: { data: null, status: "succeeded", error: null } },
    });
    expect(
      await screen.findByRole("heading", { name: copy.advertise.pending.heading }),
    ).toBeInTheDocument();
    expect(api.getMediaKit).not.toHaveBeenCalled();
  });

  it("shows a published media kit with verified, dated figures", async () => {
    renderAdvertise(async () => ({ data: KIT }));
    expect(await screen.findByText("Practical positivity.")).toBeInTheDocument();
    expect(
      screen.getByText(/Measured October 1, 2026\. Source: LinkedIn analytics\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(copy.advertise.pending.heading)).toBeNull();
    expect(screen.getByRole("link", { name: /Talk to us/ })).toHaveAttribute(
      "href",
      "/partner-with-us",
    );
  });

  it("explains a genuine error, keeps the page usable and can try again", async () => {
    const user = userEvent.setup();
    let calls = 0;
    const api = renderAdvertise(() => {
      calls += 1;
      return calls === 1 ? serverError() : Promise.resolve({ data: KIT });
    });
    expect(await screen.findByRole("heading", { name: ERROR_TEXT })).toBeInTheDocument();
    // The hero and the inquiry route stay available.
    expect(
      screen.getByRole("heading", { level: 1, name: copy.advertise.title }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Start a partnership inquiry/ }).length).toBe(1);
    await user.click(screen.getByRole("button", { name: copy.advertise.error.retry }));
    expect(await screen.findByText("Practical positivity.")).toBeInTheDocument();
    expect(api.getMediaKit).toHaveBeenCalledTimes(2);
  });

  it("loads the kit once for About, Partner With Us and Advertise in one visit", async () => {
    const user = userEvent.setup();
    const api = createFakeApi({ getMediaKit: vi.fn(async () => ({ data: KIT })) });
    renderApp("/about", { api, shopApi: createFakeShopApi() });
    await screen.findByRole("heading", { name: copy.about.community.heading });
    await user.click(
      within(document.querySelector("footer")).getByRole("link", { name: "Partner With Us" }),
    );
    await screen.findByRole("heading", { level: 1, name: copy.partner.title });
    expect(api.getMediaKit).toHaveBeenCalledTimes(1);
  });
});

/** Every string in a part of the shared copy. */
function texts(value) {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(texts);
  if (value && typeof value === "object") {
    return Object.entries(value)
      .filter(([key]) => !["icon", "key", "email", "href", "subject"].includes(key))
      .flatMap(([, v]) => texts(v));
  }
  return [];
}

const omit = (obj, keys) =>
  Object.fromEntries(Object.entries(obj).filter(([k]) => !keys.includes(k)));

const pageText = () => document.querySelector("main").textContent.replace(/\s+/g, " ");

describe("the built-in pages show the shared copy (the CMS templates use the same file)", () => {
  it("About", async () => {
    renderApp("/about", {
      api: createFakeApi({ getMediaKit: vi.fn(async () => ({ data: KIT })) }),
    });
    await screen.findByRole("heading", { name: copy.about.community.heading });
    const text = pageText();
    const shown = omit(copy.about, ["seo_title", "meta_description", "story"]);
    const { story } = copy.about;
    for (const value of texts(shown)) expect(text).toContain(value);
    // The community wording comes from Settings when set (the fixture sets it).
    expect(text).toContain(
      story.body.replace("{community}", fx.site.community.linkedin_followers_text),
    );
    expect(text).toContain(story.quote);
  });

  it("Contact", async () => {
    renderApp("/contact", {
      api: createFakeApi({
        getSite: vi.fn(async () => ({
          data: {
            ...fx.site,
            social_links: [
              {
                platform: "linkedin",
                label: "LinkedIn",
                url: "https://www.linkedin.com/company/x",
              },
            ],
          },
        })),
      }),
    });
    await screen.findByRole("heading", { name: copy.contact.cards[0].title });
    const text = pageText();
    const shown = omit(copy.contact, ["seo_title", "meta_description"]);
    for (const value of texts(shown)) expect(text).toContain(value);
  });

  it("Partner With Us (before the media kit is published)", async () => {
    renderApp("/partner-with-us", { shopApi: createFakeShopApi() });
    await screen.findByRole("heading", { level: 1, name: copy.partner.title });
    const text = pageText();
    const shown = omit(copy.partner, [
      "seo_title",
      "meta_description",
      "figures",
      "media_kit",
      "inquiry",
    ]);
    const { media_kit, inquiry } = copy.partner;
    // The form heading is used by the CMS template's form section; the built-in page
    // introduces the form with its steps instead.
    for (const value of [inquiry.eyebrow, inquiry.heading, ...inquiry.steps]) {
      expect(text).toContain(value);
    }
    for (const value of texts(shown)) expect(text).toContain(value);
    expect(text).toContain(media_kit.heading);
    expect(text).toContain(media_kit.pending);
  });

  it("Advertise (before the media kit is published)", async () => {
    renderAdvertise(() => notFound());
    await screen.findByRole("heading", { name: copy.advertise.pending.heading });
    const text = pageText();
    for (const value of [
      copy.advertise.eyebrow,
      copy.advertise.title,
      copy.advertise.intro,
      copy.advertise.inquiry_action,
      ...texts(copy.advertise.pending),
    ]) {
      expect(text).toContain(value);
    }
  });
});

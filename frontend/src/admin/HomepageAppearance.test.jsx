import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import * as fx from "@/test/fixtures";
import { SLOW_EDITOR_TEST_MS, createFakeApi, preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const outline = () => screen.getByRole("list", { name: "Page sections" });

async function openHomepage(adminApi) {
  renderApp("/admin/homepage", { adminApi });
  await screen.findByRole("list", { name: "Page sections" });
}

async function openQuote(user) {
  await user.click(within(outline()).getByRole("button", { name: /Edit section 2: Quote/ }));
  return screen.getByRole("group", { name: "Background" });
}

describe("homepage appearance in the editor", () => {
  it(
    "keeps a changed background and alignment after saving, reloading and publishing",
    async () => {
      const user = userEvent.setup();
      const adminApi = createFakeAdminApi();
      await openHomepage(adminApi);
      const background = await openQuote(user);
      await user.click(within(background).getByRole("radio", { name: "Deep sage" }));
      await user.selectOptions(screen.getByLabelText("Text alignment"), "left");
      await user.click(screen.getByRole("button", { name: "Save draft" }));
      await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalledTimes(1));
      const saved = adminApi.pages.saveDraft.mock.calls[0][1].sections;
      expect(saved.map((s) => s.section_type)).toEqual(["hero", "quote"]);
      expect(saved[1].design).toEqual({ background: "sage_dark", spacing: "md", align: "left" });
      // The other section and the quote's content are sent unchanged.
      expect(saved[0].design).toEqual({ background: "ivory", spacing: "lg", align: "left" });
      expect(saved[1].content.quote).toBe("Small steps count.");
      await screen.findByText("Draft saved. The website has not changed.");

      // Reload the editor (a browser refresh): the stored values are shown.
      cleanup();
      await openHomepage(adminApi);
      let group = await openQuote(user);
      expect(within(group).getByRole("radio", { name: "Deep sage" })).toBeChecked();
      expect(within(group).getByRole("radio", { name: "Ivory" })).not.toBeChecked();
      expect(screen.getByLabelText("Text alignment")).toHaveValue("left");

      // Publish: the published page keeps them, and the editor still shows them.
      await user.click(screen.getByRole("button", { name: "Publish" }));
      const dialog = await screen.findByRole("dialog", { name: "Publish the homepage?" });
      await user.click(within(dialog).getByRole("button", { name: "Publish" }));
      await waitFor(() => expect(adminApi.pages.publish).toHaveBeenCalledTimes(1));
      expect(adminApi.pages.saveDraft).toHaveBeenCalledTimes(1); // nothing unsaved to resend
      expect(
        await screen.findByText(/website updates when the queued rebuild/),
      ).toBeInTheDocument();
      group = screen.getByRole("group", { name: "Background" });
      expect(within(group).getByRole("radio", { name: "Deep sage" })).toBeChecked();
      const preview = await adminApi.pages.preview(1);
      expect(preview.data.page.sections[1].design).toMatchObject({
        background: "sage_dark",
        align: "left",
      });
    },
    SLOW_EDITOR_TEST_MS,
  );

  it("shows the value a section renders with when a design key isn't stored", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    const home = (await adminApi.pages.get(1)).data;
    // An older section that stored only its background: the website centres a quote
    // by default, so the editor must say "Centred", not the first option ("Left").
    await adminApi.pages.saveDraft(1, {
      lock_version: home.lock_version,
      sections: home.sections.map((s) =>
        s.section_type === "quote" ? { ...s, design: { background: "cream" } } : s,
      ),
    });
    await openHomepage(adminApi);
    const group = await openQuote(user);
    expect(within(group).getByRole("radio", { name: "Cream" })).toBeChecked();
    expect(screen.getByLabelText("Text alignment")).toHaveValue("center");
    expect(screen.getByLabelText("Section spacing")).toHaveValue("md");
  });
});

const card = (slug, title) => ({
  ...fx.articles[0],
  slug,
  title,
});

const resolved = (sections) => ({ ...fx.homePage, sections });
const section = (key, type, variant, data, design) => ({
  key,
  type,
  variant,
  design,
  devices: "all",
  data,
});

describe("homepage appearance on the website", () => {
  it("renders the stored background, card style and alignment", async () => {
    const page = resolved([
      section(
        "featured",
        "featured_articles",
        "grid_3",
        { heading: "Featured stories", articles: [card("one", "One"), card("two", "Two")] },
        { background: "sage_dark", spacing: "lg", card_style: "outline", align: "center" },
      ),
      section(
        "latest",
        "latest_articles",
        "grid_3",
        { heading: "Latest articles", articles: [card("three", "Three")] },
        { background: "beige", spacing: "sm", card_style: "flat", align: "left" },
      ),
    ]);
    renderApp("/", {
      api: createFakeApi({ getPage: vi.fn(async () => ({ data: page })) }),
    });
    const featured = await screen.findByRole("region", { name: "Featured stories" });
    expect(featured).toHaveClass("bg-sage-800", "section-dark", "py-20");
    const header = within(featured).getByRole("heading", { name: "Featured stories" });
    expect(header.closest(".border-b")).toHaveClass("text-center");
    const firstCard = within(featured).getByRole("link", { name: "One" }).closest(".card-outline");
    expect(firstCard).not.toBeNull();

    const latest = screen.getByRole("region", { name: "Latest articles" });
    expect(latest).toHaveClass("bg-beige", "py-12");
    expect(latest).not.toHaveClass("section-dark");
    expect(
      within(latest).getByRole("link", { name: "Three" }).closest(".surface-light"),
    ).toHaveClass("bg-cream");
  });

  it("puts the compact newsletter on the section's own background", async () => {
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
    const page = resolved([
      section(
        "newsletter",
        "newsletter_cta",
        "panel",
        {
          eyebrow: "Daily newsletter",
          heading: "",
          description: "One thoughtful email each day.",
          show_learn_more: true,
          show_first_name: true,
        },
        { background: "charcoal", spacing: "sm", width: "wide" },
      ),
    ]);
    renderApp("/", {
      api: createFakeApi({
        getPage: vi.fn(async () => ({ data: page })),
        getSite: vi.fn(async () => ({ data: site })),
      }),
    });
    const region = await screen.findByRole("region", { name: "The Positive Reset" });
    expect(region).toHaveClass("bg-charcoal", "section-dark");
    expect(region.querySelector("[data-newsletter-layout]")).toHaveAttribute(
      "data-newsletter-layout",
      "panel",
    );
    // One form, with every field the full form has; consent unticked and in full.
    const forms = within(region).getAllByRole("form", { name: /Subscribe to The Positive Reset/ });
    expect(forms).toHaveLength(1);
    expect(within(forms[0]).getByLabelText(/First name/)).toBeInTheDocument();
    expect(within(forms[0]).getByLabelText(/Email address/)).toBeInTheDocument();
    expect(within(forms[0]).getByRole("checkbox", { name: consent })).not.toBeChecked();
    expect(within(forms[0]).getByRole("button", { name: "Subscribe" })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: /What to expect/ })).toHaveAttribute(
      "href",
      "/newsletter",
    );
    expect(within(region).queryByText(/week/i)).not.toBeInTheDocument();
  });
});

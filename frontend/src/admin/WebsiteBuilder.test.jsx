import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { SLOW_EDITOR_TEST_MS, preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);
afterEach(() => vi.restoreAllMocks());

const outline = () => screen.getByRole("list", { name: "Page sections" });

async function openHomepage(options) {
  const utils = renderApp("/admin/homepage", options);
  expect(await screen.findByRole("heading", { level: 1, name: "Homepage" })).toBeInTheDocument();
  await screen.findByRole("list", { name: "Page sections" });
  return utils;
}

describe("website navigation and access", () => {
  it("shows the website tools to super admins", async () => {
    renderApp("/admin");
    const nav = await screen.findByRole("navigation", { name: /admin/i });
    for (const label of [
      "Homepage",
      "Pages",
      "Shared sections",
      "Navigation",
      "Footer",
      "Branding",
      "Announcements",
    ])
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
  });

  it("limits marketing managers to announcements and analysts to nothing", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "marketing_manager" }) });
    const nav = await screen.findByRole("navigation", { name: /admin/i });
    expect(within(nav).getByRole("link", { name: "Announcements" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Homepage" })).toBeInTheDocument();
    for (const label of ["Pages", "Branding", "Shared sections"])
      expect(within(nav).queryByRole("link", { name: label })).toBeNull();
  });

  it("blocks direct access without permission", async () => {
    renderApp("/admin/homepage", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });
});

describe("homepage builder", () => {
  it(
    "edits a section, warns about unsaved work and saves a draft",
    async () => {
      const user = userEvent.setup();
      const { adminApi } = await openHomepage();
      expect(screen.getByRole("status")).toHaveTextContent(/Live: the website shows this version/);
      const heading = screen.getByLabelText(/^Headline/);
      // Pasted, not typed: every keystroke re-renders the live page preview, which made this
      // test CPU-bound on slower machines. It checks the saved draft, not key handling.
      await user.clear(heading);
      await user.paste("Grow Through Every Season.");
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(/unsaved changes/i);
      await user.click(screen.getByRole("button", { name: "Save draft" }));
      await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalled());
      const [id, body] = adminApi.pages.saveDraft.mock.calls[0];
      expect(id).toBe(1);
      expect(body.lock_version).toBe(3);
      expect(body.sections[0]).toMatchObject({
        id: 1,
        section_type: "hero",
        content: expect.objectContaining({ heading: "Grow Through Every Season." }),
      });
      expect(
        await screen.findByText("Draft saved. The website has not changed."),
      ).toBeInTheDocument();
      expect(screen.queryByText("Unsaved changes")).toBeNull();
    },
    SLOW_EDITOR_TEST_MS,
  );

  it("reorders sections with buttons and the keyboard", async () => {
    const user = userEvent.setup();
    const { adminApi } = await openHomepage();
    await user.click(within(outline()).getByRole("button", { name: "Move Quote up" }));
    expect(await screen.findByText("Quote moved to position 1 of 2.")).toBeInTheDocument();
    const quoteItem = within(outline()).getByRole("button", { name: /Edit section 1: Quote/ });
    quoteItem.focus();
    await user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(
      within(outline()).getByRole("button", { name: /Edit section 2: Quote/ }),
    ).toBeInTheDocument();
    await user.click(within(outline()).getByRole("button", { name: "Move Hero down" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalled());
    expect(adminApi.pages.saveDraft.mock.calls[0][1].sections.map((s) => s.section_type)).toEqual([
      "quote",
      "hero",
    ]);
  });

  it("adds sections from the grouped picker and blocks a second hero", async () => {
    const user = userEvent.setup();
    await openHomepage();
    await user.click(screen.getByRole("button", { name: "Add section" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a section" });
    expect(within(dialog).getByRole("button", { name: /Hero banner/ })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: /^FAQ/ }));
    expect(screen.queryByRole("dialog", { name: "Add a section" })).toBeNull();
    expect(
      within(outline()).getByRole("button", { name: /Edit section 2: FAQ/ }), // inserted after the selected hero
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add question" })).toBeInTheDocument();
    // Shared sections can be inserted as linked sections.
    await user.click(screen.getByRole("button", { name: "Add section" }));
    const again = await screen.findByRole("dialog", { name: "Add a section" });
    await user.click(within(again).getByRole("tab", { name: /Shared sections/ }));
    await user.click(within(again).getByRole("button", { name: /Join the newsletter/ }));
    expect(screen.getByText(/Shared section: Join the newsletter/)).toBeInTheDocument();
  });

  it("shows server validation next to the field and flags the section", async () => {
    const user = userEvent.setup();
    await openHomepage();
    await user.clear(screen.getByLabelText(/^Headline/));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("This field is required.")).toBeInTheDocument();
    expect(within(outline()).getByText("1 issue")).toBeInTheDocument();
  });

  it("explains edit conflicts instead of overwriting newer work", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    await openHomepage({ adminApi });
    // Someone else saves meanwhile.
    await adminApi.pages.saveDraft(1, { lock_version: 3, page: { title: "Homepage" } });
    await user.type(screen.getByLabelText(/^Supporting text/), " More.");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    const dialog = await screen.findByRole("dialog", { name: "Someone else changed this page" });
    expect(within(dialog).getByText(/Ngozi saved/)).toBeInTheDocument();
  });

  it("publishes after confirmation and explains the rebuild", async () => {
    const user = userEvent.setup();
    const { adminApi } = await openHomepage();
    await user.type(screen.getByLabelText(/^Supporting text/), " More.");
    await user.click(screen.getByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish the homepage?" });
    expect(within(dialog).getByText(/Your changes are saved first/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(adminApi.pages.publish).toHaveBeenCalledWith(1, 4));
    expect(adminApi.pages.saveDraft).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByText(/website updates when the queued rebuild finishes/),
    ).toBeInTheDocument();
  });

  it("opens a private preview and offers a live device preview", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    await openHomepage();
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(open).toHaveBeenCalledWith("/admin/pages/1/preview", "_blank", "noopener");
    const frame = screen.getByTitle("Live preview (Desktop)");
    expect(frame).toHaveAttribute("src", "/admin/preview-frame/1");
    await user.click(screen.getByRole("button", { name: "Mobile" }));
    expect(screen.getByTitle("Live preview (Mobile)")).toHaveStyle({ width: "390px" });
  });

  it("chooses a section image from the media library", async () => {
    const user = userEvent.setup();
    const { adminApi } = await openHomepage();
    await user.click(screen.getByRole("button", { name: "Choose image" }));
    const picker = await screen.findByRole("dialog", { name: "Choose an image" });
    await user.click(await within(picker).findByRole("button", { name: "Select Calm lake" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalled());
    expect(adminApi.pages.saveDraft.mock.calls[0][1].sections[0].content.media).toBe(3);
  });

  it("applies approved design presets", async () => {
    const user = userEvent.setup();
    const { adminApi } = await openHomepage();
    await user.click(screen.getByRole("radio", { name: "Deep sage" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalled());
    expect(adminApi.pages.saveDraft.mock.calls[0][1].sections[0].design.background).toBe(
      "sage_dark",
    );
  });

  it("restores a revision into the draft", async () => {
    const user = userEvent.setup();
    const { adminApi } = await openHomepage();
    await user.click(screen.getByRole("tab", { name: "History" }));
    await user.click(await screen.findByRole("button", { name: "Restore revision 1" }));
    const dialog = await screen.findByRole("dialog", { name: "Restore revision #1?" });
    await user.click(within(dialog).getByRole("button", { name: "Restore into draft" }));
    await waitFor(() => expect(adminApi.pages.restoreRevision).toHaveBeenCalledWith(1, 10, 3));
    expect(await screen.findByText(/Revision #1 restored into the draft/)).toBeInTheDocument();
  });

  it("lets editors edit drafts but not publish the homepage", async () => {
    await openHomepage({ adminApi: createFakeAdminApi({ role: "editor" }) });
    expect(screen.getByRole("button", { name: "Save draft" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
  });

  it("is read-only for moderators", async () => {
    await openHomepage({ adminApi: createFakeAdminApi({ role: "moderator" }) });
    expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
    expect(screen.getByLabelText(/^Headline/)).toBeDisabled();
  });
});

describe("pages", () => {
  it("creates a page from a template", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/pages");
    await user.click(await screen.findByRole("button", { name: "Create page" }));
    const dialog = await screen.findByRole("dialog", { name: "Create a page" });
    await user.type(within(dialog).getByLabelText(/^Title/), "Spring Campaign");
    expect(within(dialog).getByLabelText(/Address/)).toHaveValue("spring-campaign");
    await user.click(
      await within(dialog).findByRole("radio", { name: /Coming-soon product page/ }),
    );
    await user.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(adminApi.pages.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Spring Campaign",
          slug: "spring-campaign",
          template: "coming_soon",
        }),
      ),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Spring Campaign" }),
    ).toBeInTheDocument();
  });

  it("lists pages with status and unpublished changes", async () => {
    renderApp("/admin/pages");
    const table = await screen.findByRole("table", { name: "Pages" });
    expect(within(table).getByRole("link", { name: "Homepage" })).toHaveAttribute(
      "href",
      "/admin/homepage",
    );
    expect(within(table).getByRole("link", { name: "Spring Reset" })).toHaveAttribute(
      "href",
      "/admin/pages/7",
    );
  });

  it("checks reserved addresses and edits page SEO", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/pages/7");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Spring Reset" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Page settings" }));
    const slug = screen.getByLabelText(/Address/);
    await user.clear(slug);
    await user.type(slug, "admin");
    expect(await screen.findByText(/reserved by the website/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "SEO" }));
    expect(await screen.findByText(/Add a meta description/)).toBeInTheDocument();
    await user.type(
      screen.getByLabelText(/Meta description/),
      "A short guide to a gentle spring reset.",
    );
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalled());
    expect(adminApi.pages.saveDraft.mock.calls[0][1].page.meta_description).toBe(
      "A short guide to a gentle spring reset.",
    );
  });
});

describe("shared content", () => {
  it("asks whether to update live pages when a shared section changes", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/shared-sections");
    await user.click(await screen.findByRole("button", { name: "Edit Join the newsletter" }));
    const dialog = await screen.findByRole("dialog", { name: /Edit shared section/ });
    const heading = await within(dialog).findByLabelText(/^Heading(?! size)/);
    await user.clear(heading);
    await user.type(heading, "Join us this spring");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    const ask = await screen.findByRole("dialog", { name: "Update the pages that use it?" });
    await user.click(within(ask).getByRole("button", { name: "Keep those pages unchanged" }));
    await waitFor(() =>
      expect(adminApi.shared.update).toHaveBeenCalledWith(
        5,
        expect.objectContaining({ propagate: false, lock_version: 2 }),
      ),
    );
    expect(await screen.findByText(/1 page\(s\) kept their previous version/)).toBeInTheDocument();
  });

  it("validates saved calls to action", async () => {
    const user = userEvent.setup();
    renderApp("/admin/shared-sections");
    await user.click(await screen.findByRole("tab", { name: "Calls to action" }));
    await user.click(await screen.findByRole("button", { name: "New call to action" }));
    const dialog = await screen.findByRole("dialog", { name: "New call to action" });
    await user.type(within(dialog).getByLabelText(/^Name/), "Bad");
    await user.type(within(dialog).getByLabelText(/^Button text/), "Go");
    await user.type(within(dialog).getByLabelText(/^Link/), "ftp://x");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/Use a site path starting with/)).toBeInTheDocument();
  });
});

describe("site-wide settings", () => {
  it("edits branding presets with a live preview", async () => {
    const user = userEvent.setup();
    const { adminApi, container } = renderApp("/admin/branding");
    const palette = await screen.findByLabelText("Colour palette");
    await user.selectOptions(palette, "evergreen");
    expect(container.querySelector('[data-palette="evergreen"]')).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save and publish" }));
    await waitFor(() =>
      expect(adminApi.settings.save).toHaveBeenCalledWith({ "branding.palette": "evergreen" }, [
        "Branding",
      ]),
    );
  });

  it("edits the footer settings", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/footer");
    const copyright = await screen.findByLabelText("Copyright line");
    await user.clear(copyright);
    await user.type(copyright, "© {{year} TPA");
    await user.click(screen.getByRole("button", { name: "Save and publish" }));
    await waitFor(() =>
      expect(adminApi.settings.save).toHaveBeenCalledWith({ "footer.copyright": "© {year} TPA" }, [
        "Footer",
      ]),
    );
  });

  it("edits navigation with dropdown groups, device visibility and link warnings", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/navigation");
    const header = await screen.findByRole("region", { name: "Header navigation" });
    expect(
      within(header).getByText(/old-page does not point to a published page/),
    ).toBeInTheDocument();
    await user.click(within(header).getByRole("button", { name: "Add dropdown group" }));
    const labels = within(header).getAllByLabelText("Label");
    await user.type(labels[labels.length - 1], "Explore");
    await user.selectOptions(within(header).getAllByLabelText("Show on")[0], "desktop");
    await user.click(within(header).getByRole("button", { name: "Save and publish" }));
    await waitFor(() => expect(adminApi.navigation.save).toHaveBeenCalled());
    const [key, items] = adminApi.navigation.save.mock.calls[0];
    expect(key).toBe("primary");
    expect(items[0].visibility).toBe("desktop");
    expect(items[2]).toMatchObject({ label: "Explore", link_type: "heading" });
  });

  it("manages announcements", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/announcements", {
      adminApi: createFakeAdminApi({ role: "marketing_manager" }),
    });
    const table = await screen.findByRole("table", { name: "Announcements" });
    expect(within(table).getByText("Live")).toBeInTheDocument();
    expect(within(table).getByText("Scheduled")).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: "Move Spring series up" }));
    await waitFor(() => expect(adminApi.announcements.reorder).toHaveBeenCalledWith([2, 1]));
    await user.click(screen.getByRole("button", { name: "New announcement" }));
    const dialog = await screen.findByRole("dialog", { name: "New announcement" });
    await user.type(within(dialog).getByLabelText(/^Internal name/), "Launch");
    await user.type(within(dialog).getByLabelText(/^Message/), "The journal is here.");
    await user.click(within(dialog).getByLabelText(/^Enabled/));
    await user.click(within(dialog).getByRole("button", { name: "Save and publish" }));
    await waitFor(() =>
      expect(adminApi.announcements.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Launch",
          message: "The journal is here.",
          is_enabled: true,
        }),
      ),
    );
  });
});

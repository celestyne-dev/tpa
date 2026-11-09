import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { parseEmphasis } from "@/components/legal/emphasis";
import { withAnchors } from "@/components/legal/legalAnchors";
import legalDocuments from "@/data/legal/legalDocuments.json";
import { createFakeAdminApi } from "@/test/adminFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);
afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
});

const plain = (text) => text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
const main = () => document.querySelector("main");

describe("built-in legal pages", () => {
  it.each([
    ["/privacy-policy", "privacy"],
    ["/terms", "terms"],
    ["/affiliate-disclosure", "affiliate"],
  ])("%s keeps its wording word for word", async (path, key) => {
    const doc = legalDocuments[key];
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: doc.title })).toBeInTheDocument();
    const text = main().textContent.replace(/\s+/g, " ");
    for (const block of doc.body) {
      for (const value of block.items ?? [block.text]) {
        expect(text).toContain(plain(value));
      }
    }
    expect(text).toContain(doc.notice.text);
  });

  it("has dates, a table of contents with working anchors, related links and contact", async () => {
    renderApp("/privacy-policy");
    await screen.findByRole("heading", { level: 1, name: "Privacy Policy" });
    expect(screen.getByText("Last updated").nextSibling).toHaveTextContent(/2026/);
    // Two copies of the contents (sidebar on desktop, collapsible on phones); same links.
    const tocs = screen.getAllByRole("navigation", { name: "Table of contents", hidden: true });
    expect(tocs).toHaveLength(2);
    const links = within(tocs[0])
      .getAllByRole("link", { hidden: true })
      .filter((a) => a.getAttribute("href").startsWith("#"));
    expect(links).toHaveLength(10);
    expect(links[0]).toHaveTextContent("1. Who we are");
    for (const link of links) {
      const id = link.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      expect(target, id).not.toBeNull();
      expect(target.tagName).toBe("H2");
      expect(target).toHaveTextContent(link.textContent);
    }
    const related = screen.getByRole("navigation", { name: "Related legal pages" });
    const names = within(related)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(names).toEqual(["Terms of Use", "Affiliate Disclosure"]);
    expect(within(main()).getAllByRole("link", { name: /contact/i }).length).toBeGreaterThan(0);
  });
});

describe("legal document helpers", () => {
  it("gives repeated headings unique anchors and nests level-3 headings", () => {
    const { blocks, toc } = withAnchors([
      { type: "heading", level: 2, text: "Cookies" },
      { type: "heading", level: 3, text: "Essential" },
      { type: "paragraph", text: "x" },
      { type: "heading", level: 2, text: "Cookies" },
    ]);
    expect(blocks.filter((b) => b.anchorId).map((b) => b.anchorId)).toEqual([
      "cookies",
      "essential",
      "cookies-2",
    ]);
    expect(toc.map((t) => t.id)).toEqual(["cookies", "cookies-2"]);
    expect(toc[0].children.map((c) => c.text)).toEqual(["Essential"]);
  });

  it("parses **bold** and *italic* as text, leaving stray markers alone", () => {
    expect(parseEmphasis("A **firm** and *soft* 2 * 3")).toEqual([
      { text: "A " },
      { strong: "firm" },
      { text: " and " },
      { em: "soft" },
      { text: " 2 * 3" },
    ]);
  });
});

const legalSection = (data, extra = {}) => ({
  key: "legal-document-1",
  type: "legal_document",
  variant: "default",
  design: {},
  devices: "all",
  data: {
    eyebrow: "Legal",
    heading: "",
    summary: "What we do with cookies.",
    effective_date: "2026-12-01",
    last_updated: "2026-11-09",
    notice_title: "",
    notice: "",
    show_toc: true,
    show_related: true,
    ...data,
  },
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

describe("legal documents managed in the CMS", () => {
  it("replaces the built-in page once published, with rich text, tables and anchors", async () => {
    const page = cmsPage("/privacy-policy", "Privacy Policy", [
      legalSection({
        body: [
          { type: "heading", level: 2, text: "1. Scope" },
          { type: "paragraph", text: "This applies to **everyone**, see [Terms](/terms)." },
          { type: "heading", level: 3, text: "1.1 Visitors" },
          { type: "list", ordered: true, items: ["First *step*", "Second"] },
          { type: "heading", level: 2, text: "2. Cookies we use" },
          {
            type: "table",
            header_row: true,
            rows: [
              ["Name", "Purpose"],
              ["session", "Keeps you signed in"],
            ],
          },
        ],
      }),
    ]);
    const api = createFakeApi({
      getSite: async () => ({ data: { ...fx.site, cms_overrides: ["/privacy-policy"] } }),
      getPage: vi.fn(async () => ({ data: page })),
    });
    renderApp("/privacy-policy", { api });
    // The built-in page shows until the site settings arrive and name the CMS override.
    await screen.findByText("everyone");
    const title = screen.getByRole("heading", { level: 1, name: "Privacy Policy" });
    const doc = title.closest("[data-legal-document]");
    expect(within(doc).getByText("everyone").tagName).toBe("STRONG");
    expect(within(doc).getByText("step").tagName).toBe("EM");
    expect(within(doc).getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(within(doc).getByRole("columnheader", { name: "Purpose" })).toBeInTheDocument();
    expect(doc.querySelector(".prose-legal ol li")).toHaveTextContent("First step");
    expect(within(doc).getByText("Effective date")).toBeInTheDocument();
    const [toc] = screen.getAllByRole("navigation", { name: "Table of contents", hidden: true });
    expect(
      within(toc)
        .getAllByRole("link", { hidden: true })
        .map((a) => a.getAttribute("href"))
        .filter((href) => href.startsWith("#")),
    ).toEqual(["#1-scope", "#1-1-visitors", "#2-cookies-we-use"]);
    expect(document.getElementById("1-1-visitors").tagName).toBe("H3");
  });

  it("follows section order and device visibility, and can hide the contents", async () => {
    const page = cmsPage("/cookie-notes", "Cookie notes", [
      {
        key: "rich-text-1",
        type: "rich_text",
        variant: "narrow",
        design: {},
        devices: "all",
        data: { heading: "Before the document", body: [{ type: "paragraph", text: "Intro." }] },
      },
      legalSection(
        {
          show_toc: false,
          show_related: false,
          body: [
            { type: "heading", level: 2, text: "One" },
            { type: "heading", level: 2, text: "Two" },
          ],
        },
        { devices: "desktop" },
      ),
    ]);
    renderApp("/cookie-notes", {
      api: createFakeApi({ getPage: vi.fn(async () => ({ data: page })) }),
    });
    const intro = await screen.findByRole("heading", { name: "Before the document" });
    const title = screen.getByRole("heading", { level: 1, name: "Cookie notes" });
    expect(intro.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(title.closest('[data-section="legal_document"]')).toHaveClass("hidden", "md:block");
    expect(screen.queryByRole("navigation", { name: "Table of contents" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Related legal pages" })).toBeNull();
  });
});

describe("page builder autosave", () => {
  it("saves the draft a few seconds after an edit, without publishing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const adminApi = createFakeAdminApi();
    renderApp("/admin/pages/7", { adminApi });
    await screen.findByRole("heading", { level: 1, name: "Spring Reset" });
    const heading = screen.getByLabelText(/^Headline/);
    await user.clear(heading);
    await user.type(heading, "Autosaved heading");
    expect(adminApi.pages.saveDraft).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(9000));
    await waitFor(() => expect(adminApi.pages.saveDraft).toHaveBeenCalledTimes(1));
    const [, body] = adminApi.pages.saveDraft.mock.calls[0];
    expect(body.sections[0].content.heading).toBe("Autosaved heading");
    expect(adminApi.pages.publish).not.toHaveBeenCalled();
    expect(await screen.findByText("Draft saved automatically")).toBeInTheDocument();
    // The editor keeps the typed value, and nothing is pending any more.
    expect(heading).toHaveValue("Autosaved heading");
    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(adminApi.pages.saveDraft).toHaveBeenCalledTimes(1);
  });
});

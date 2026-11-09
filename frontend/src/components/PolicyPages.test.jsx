import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { beacon } from "@/analytics/pageViews";
import { policyPages } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import legalDocuments from "@/data/legal/legalDocuments.json";
import { STORAGE_KEY } from "@/privacy/choices";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const main = () => document.querySelector("main");
const footer = () => document.querySelector("footer");
const robots = () => document.querySelector('meta[name="robots"]')?.getAttribute("content");
const canonical = () => document.querySelector('link[rel="canonical"]')?.getAttribute("href");
const plain = (text) => text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/\*\*/g, "");

const withSite = (extra) =>
  createFakeApi({ getSite: vi.fn(async () => ({ data: { ...fx.site, ...extra } })) });

let send;
beforeEach(() => {
  send = vi.spyOn(beacon, "send").mockReturnValue(true);
});
afterEach(() => {
  window.localStorage.clear();
  siteConfig.allowIndexing = false;
});

describe("built-in policy pages (drafts)", () => {
  it.each(policyPages.map((p) => [p.path, p.key]))(
    "%s shows the draft with dates, contents, related links and contact, never indexed",
    async (path, key) => {
      siteConfig.allowIndexing = true;
      const doc = legalDocuments[key];
      renderApp(path);
      const title = await screen.findByRole("heading", { level: 1, name: doc.title });
      const header = title.closest("header");
      expect(within(header).getByText("Effective date").nextSibling).toHaveTextContent(
        "Pending legal review",
      );
      expect(within(header).getByText("Last updated").nextSibling).toHaveTextContent("2026");
      expect(within(header).getByText(doc.summary)).toBeInTheDocument();
      expect(within(main()).getByText("Draft — pending legal review")).toBeInTheDocument();
      // Every heading is in the contents and every contents link has its target.
      const [toc] = screen.getAllByRole("navigation", { name: "Table of contents", hidden: true });
      const anchors = within(toc)
        .getAllByRole("link", { hidden: true })
        .map((a) => a.getAttribute("href"))
        .filter((href) => href.startsWith("#"));
      const headings = doc.body.filter((b) => b.type === "heading" && b.level === 2);
      expect(anchors).toHaveLength(headings.length);
      for (const href of anchors) expect(document.getElementById(href.slice(1))).not.toBeNull();
      // The wording is the shared draft, word for word.
      const text = main().textContent.replace(/\s+/g, " ");
      for (const block of doc.body) {
        for (const value of block.items ?? (block.text ? [block.text] : [])) {
          expect(text).toContain(plain(value));
        }
      }
      // Related legal pages: the published ones only (no other policy drafts).
      const related = screen.getByRole("navigation", { name: "Related legal pages" });
      const hrefs = within(related)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href"));
      expect(hrefs).toEqual(["/privacy-policy", "/terms", "/affiliate-disclosure"]);
      expect(within(main()).getAllByRole("link", { name: /contact/i }).length).toBeGreaterThan(0);
      await waitFor(() => expect(robots()).toBe("noindex, follow"));
      expect(canonical()).toMatch(new RegExp(`${path}$`));
      expect(document.title).toContain(doc.seo_title);
    },
  );

  it.each([
    ["/privacy-policy", "privacy"],
    ["/terms", "terms"],
    ["/affiliate-disclosure", "affiliate"],
  ])(
    "%s keeps its wording but, pending review, is noindex and not in effect",
    async (path, key) => {
      siteConfig.allowIndexing = true;
      const doc = legalDocuments[key];
      renderApp(path);
      const title = await screen.findByRole("heading", { level: 1, name: doc.title });
      const header = title.closest("header");
      expect(within(header).getByText("Effective date").nextSibling).toHaveTextContent(
        "Pending legal review",
      );
      expect(within(main()).getByText("Draft — pending legal review")).toBeInTheDocument();
      expect(main().textContent).toContain(doc.notice.text);
      await waitFor(() => expect(robots()).toBe("noindex, follow"));
      expect(document.querySelector("[data-review]")).toHaveAttribute("data-review", "pending");
    },
  );

  it("a CMS legal document pending review says so even with its notice removed", async () => {
    siteConfig.allowIndexing = true;
    const page = {
      ...fx.cmsPages["/spring-reset"],
      path: "/house-rules",
      title: "House rules",
      seo: { ...fx.cmsPages["/spring-reset"].seo, noindex: true },
      sections: [
        {
          key: "legal-document-1",
          type: "legal_document",
          variant: "default",
          design: {},
          devices: "all",
          data: {
            eyebrow: "Legal",
            heading: "",
            summary: "",
            effective_date: "2027-01-01",
            last_updated: "2026-12-01",
            notice_title: "",
            notice: "",
            review_status: "pending_review",
            body: [
              { type: "heading", level: 2, text: "1. One" },
              { type: "heading", level: 2, text: "2. Two" },
            ],
            show_toc: true,
            show_related: false,
          },
        },
      ],
    };
    renderApp("/house-rules", {
      api: createFakeApi({ getPage: vi.fn(async () => ({ data: page })) }),
    });
    await screen.findByRole("heading", { level: 1, name: "House rules" });
    expect(screen.getByText("Draft — pending legal review")).toBeInTheDocument();
    // The planned date is not shown as if it were in effect.
    expect(screen.getByText("Effective date").nextSibling).toHaveTextContent(
      "Pending legal review",
    );
    expect(screen.queryByText(/January 1, 2027/)).toBeNull();
    await waitFor(() => expect(robots()).toBe("noindex, follow"));
  });

  it("the footer links a policy only once its CMS page is published", async () => {
    renderApp("/disclaimer", { api: withSite({ cms_overrides: [] }) });
    await screen.findByRole("heading", { level: 1, name: "Disclaimer" });
    const legal = within(footer()).getByRole("navigation", { name: "Legal" });
    expect(within(legal).queryByRole("link", { name: "Disclaimer" })).toBeNull();
    expect(within(legal).getByRole("link", { name: "Privacy Policy" })).toBeInTheDocument();
  });

  it("a published Editorial Policy is linked once, not again as a trust link", async () => {
    const editorial = { path: "/editorial-policy", title: "Editorial Policy" };
    renderApp("/about", {
      api: withSite({
        cms_overrides: ["/editorial-policy"],
        trust: { editorial_policy: editorial, corrections_policy: editorial },
      }),
    });
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() =>
      expect(within(footer()).getAllByRole("link", { name: "Editorial Policy" })).toHaveLength(1),
    );
    const links = within(footer())
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(links.filter((href) => href === "/editorial-policy")).toHaveLength(1);
  });

  it("a published CMS page replaces the draft at the same address", async () => {
    const page = {
      ...fx.cmsPages["/spring-reset"],
      path: "/disclaimer",
      title: "Disclaimer",
      seo: { ...fx.cmsPages["/spring-reset"].seo, noindex: true },
      breadcrumbs: [
        { name: "Home", path: "/" },
        { name: "Disclaimer", path: "/disclaimer" },
      ],
      sections: [
        {
          key: "legal-document-1",
          type: "legal_document",
          variant: "default",
          design: {},
          devices: "all",
          data: {
            eyebrow: "Legal",
            heading: "",
            summary: "Reviewed wording.",
            effective_date: "2027-01-01",
            last_updated: "2026-12-01",
            notice_title: "",
            notice: "",
            body: [
              { type: "heading", level: 2, text: "1. Reviewed" },
              { type: "heading", level: 2, text: "2. Also reviewed" },
            ],
            show_toc: true,
            show_related: true,
          },
        },
      ],
    };
    const api = createFakeApi({
      getSite: vi.fn(async () => ({ data: { ...fx.site, cms_overrides: ["/disclaimer"] } })),
      getPage: vi.fn(async () => ({ data: page })),
    });
    renderApp("/disclaimer", { api });
    await screen.findByText("Reviewed wording.");
    expect(screen.queryByText("Pending legal review")).toBeNull();
    expect(screen.getByText("Effective date").nextSibling).toHaveTextContent("2027");
    const legal = within(footer()).getByRole("navigation", { name: "Legal" });
    expect(within(legal).getByRole("link", { name: "Disclaimer" })).toHaveAttribute(
      "href",
      "/disclaimer",
    );
  });
});

const objectionSite = () =>
  withSite({ privacy: { ...fx.site.privacy, statistics_mode: "objection" } });

const sentPaths = () => send.mock.calls.map(([, body]) => JSON.parse(body));

describe("cookie settings", () => {
  it("objection mode: no notice, visits count, and switching off stops them", async () => {
    const user = userEvent.setup();
    renderApp("/about", { api: objectionSite() });
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(sentPaths().map((b) => b.path)).toEqual(["/about"]));
    expect(sentPaths()[0].consent).toBeUndefined();
    expect(screen.queryByRole("region", { name: "Cookie notice" })).toBeNull();

    const open = within(footer()).getByRole("button", { name: "Cookie settings" });
    await user.click(open);
    const dialog = screen.getByRole("dialog", { name: "Cookie settings" });
    expect(within(dialog).getByText("Always on")).toBeInTheDocument();
    const stats = within(dialog).getByRole("switch", { name: "Usage statistics" });
    expect(stats).toBeChecked();
    expect(within(dialog).getByRole("link", { name: /Cookie Policy/ })).toHaveAttribute(
      "href",
      "/cookie-policy",
    );
    // Keyboard: Escape closes and focus returns to the footer button.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(open).toHaveFocus();

    await user.keyboard("{Enter}");
    const again = screen.getByRole("dialog", { name: "Cookie settings" });
    await user.click(within(again).getByRole("switch", { name: "Usage statistics" }));
    await user.click(within(again).getByRole("button", { name: "Save choices" }));
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY))).toMatchObject({
      statistics: false,
      version: fx.site.privacy.version,
    });
    expect(screen.getByText("Usage statistics are off.")).toHaveAttribute("role", "status");

    await user.click(within(footer()).getByRole("link", { name: "Contact" }));
    await screen.findByRole("heading", { level: 1 });
    expect(sentPaths().map((b) => b.path)).toEqual(["/about"]);
  });

  const consentSite = (version = fx.site.privacy.version) =>
    withSite({ privacy: { ...fx.site.privacy, statistics_mode: "consent", version } });

  it("consent mode: nothing is counted until the visitor accepts", async () => {
    const user = userEvent.setup();
    renderApp("/about", { api: consentSite() });
    const notice = await screen.findByRole("region", { name: "Cookie notice" });
    expect(within(notice).getByText("May we count your visit?")).toBeInTheDocument();
    // Accept and Reject are equally prominent.
    const accept = within(notice).getByRole("button", { name: "Accept" });
    const reject = within(notice).getByRole("button", { name: "Reject" });
    expect(accept.className).toBe(reject.className);
    expect(send).not.toHaveBeenCalled();

    await user.click(accept);
    expect(screen.queryByRole("region", { name: "Cookie notice" })).toBeNull();
    await waitFor(() => expect(sentPaths()).toHaveLength(1));
    // The landing page is counted with its first-load details and the consent flag.
    expect(sentPaths()[0]).toMatchObject({ path: "/about", spa: false, consent: true });

    await user.click(within(footer()).getByRole("link", { name: "Contact" }));
    await waitFor(() => expect(sentPaths()).toHaveLength(2));
    expect(sentPaths()[1]).toMatchObject({ path: "/contact", spa: true, consent: true });
  });

  it("consent mode: rejecting, then withdrawing after accepting, stops counting", async () => {
    const user = userEvent.setup();
    renderApp("/about", { api: consentSite() });
    const notice = await screen.findByRole("region", { name: "Cookie notice" });
    await user.click(within(notice).getByRole("button", { name: "Reject" }));
    await user.click(within(footer()).getByRole("link", { name: "Contact" }));
    await screen.findByRole("heading", { level: 1 });
    expect(send).not.toHaveBeenCalled();

    // Change of mind: switch statistics on in the panel.
    await user.click(within(footer()).getByRole("button", { name: "Cookie settings" }));
    let dialog = screen.getByRole("dialog");
    const stats = within(dialog).getByRole("switch", { name: "Usage statistics" });
    expect(stats).not.toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Accept optional" }));
    await waitFor(() => expect(sentPaths().map((b) => b.path)).toEqual(["/contact"]));

    // Withdraw: nothing more is sent.
    await user.click(within(footer()).getByRole("button", { name: "Cookie settings" }));
    dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reject optional" }));
    await user.click(within(footer()).getByRole("link", { name: "About" }));
    await screen.findByRole("heading", { level: 1 });
    expect(sentPaths().map((b) => b.path)).toEqual(["/contact"]);
  });

  it("consent mode: a new consent version asks again", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: "2026-01-01", statistics: true }),
    );
    renderApp("/about", { api: consentSite("2026-11-09") });
    expect(await screen.findByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it("by default nothing is counted before consent, and Cookie settings stay available", async () => {
    renderApp("/about");
    const notice = await screen.findByRole("region", { name: "Cookie notice" });
    expect(within(notice).getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(within(footer()).getByRole("button", { name: "Cookie settings" })).toBeInTheDocument();
    await screen.findByRole("heading", { level: 1 });
    expect(send).not.toHaveBeenCalled();
  });

  it("an earlier refusal is respected: not asked again, nothing counted", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: "2026-01-01", statistics: false }),
    );
    renderApp("/about");
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() =>
      expect(within(footer()).getByRole("button", { name: "Cookie settings" })).toBeVisible(),
    );
    expect(screen.queryByRole("region", { name: "Cookie notice" })).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it("consent mode: a visitor who already chose is not asked again", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: fx.site.privacy.version, statistics: true }),
    );
    renderApp("/about", { api: consentSite() });
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(sentPaths()).toHaveLength(1));
    expect(screen.queryByRole("region", { name: "Cookie notice" })).toBeNull();
  });

  it("the notice's Customise button opens the panel, which traps focus", async () => {
    const user = userEvent.setup();
    renderApp("/about", { api: consentSite() });
    const notice = await screen.findByRole("region", { name: "Cookie notice" });
    await user.click(within(notice).getByRole("button", { name: "Customise" }));
    const dialog = screen.getByRole("dialog", { name: "Cookie settings" });
    expect(within(dialog).getByRole("button", { name: "Save choices" })).toHaveFocus();
    // Tab stays inside the dialog.
    for (let i = 0; i < 8; i += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await user.click(within(dialog).getByRole("button", { name: "Save choices" }));
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)).statistics).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("choices made in another tab apply here too", async () => {
    renderApp("/about", { api: objectionSite() });
    await waitFor(() => expect(sentPaths()).toHaveLength(1));
    act(() => {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ version: fx.site.privacy.version, statistics: false }),
      );
      window.dispatchEvent(new StorageEvent("storage", { key: STORAGE_KEY }));
    });
    await userEvent
      .setup()
      .click(within(footer()).getByRole("button", { name: "Cookie settings" }));
    expect(screen.getByRole("switch", { name: "Usage statistics" })).not.toBeChecked();
  });

  it("without optional technologies there is no Cookie settings link or notice", async () => {
    const privacy = { ...fx.site.privacy, categories: [fx.site.privacy.categories[0]] };
    renderApp("/about", { api: withSite({ privacy: { ...privacy, statistics_mode: "consent" } }) });
    await screen.findByRole("heading", { level: 1 });
    expect(within(footer()).queryByRole("button", { name: "Cookie settings" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Cookie notice" })).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });
});

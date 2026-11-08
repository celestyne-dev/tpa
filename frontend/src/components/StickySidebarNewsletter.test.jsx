import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArticleSidebar, STICKY_OFFSET, stickyTop } from "@/components/sidebar/ArticleSidebar";
import { ApiError } from "@/services/apiClient";
import { createAppStore } from "@/store";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, notFound, renderApp } from "@/test/utils";

const [, a2, a3] = fx.articles;
const CONSENT = "Yes, email me The Positive Reset every day. I can unsubscribe at any time.";

const section = (key, type, data, extra = {}) => ({
  key,
  type,
  variant: "list",
  design: {},
  devices: "all",
  data,
  ...extra,
});

const newsletterSection = (extra = {}) =>
  section(
    "newsletter",
    "newsletter_cta",
    {
      eyebrow: "Daily newsletter",
      heading: "",
      description: "One thoughtful email each day.",
      show_learn_more: true,
      newsletter_name: "The Positive Reset",
    },
    extra,
  );

const sidebar = () => [
  section("popular", "popular_articles", { heading: "Popular articles", articles: [a2] }),
  newsletterSection(),
  section("related", "related_articles", { heading: "Related articles", articles: [a3] }),
];

const siteWith = (isOpen) => ({
  ...fx.site,
  newsletter: {
    ...fx.site.newsletter,
    is_open: isOpen,
    consent_text: isOpen ? CONSENT : "",
    consent_version: isOpen ? "2026-11" : "",
  },
});

function shop(live = true, overrides = {}) {
  return {
    ...createFakeShopApi(),
    newsletterStatus: vi.fn(async () => ({
      data: {
        name: "The Positive Reset",
        tagline: "A Better Mindset. A Brighter Life.",
        signup_open: live,
        consent_text: live ? CONSENT : "",
        consent_version: live ? "2026-11" : "",
      },
    })),
    subscribe: vi.fn(async () => ({
      data: {
        status: "check_email",
        message: "Thank you. Please check your inbox for an email from us to continue.",
      },
    })),
    ...overrides,
  };
}

function openArticle({ open = true, live = open, sections = sidebar(), shopApi } = {}) {
  const api = createFakeApi({
    getSite: vi.fn(async () => ({ data: siteWith(open) })),
    getArticle: vi.fn(async (slug) =>
      slug === fx.articleDetail.slug
        ? {
            data: {
              article: fx.articleDetail,
              related: [],
              adjacent: { previous: null, next: null },
              sidebar: sections,
            },
          }
        : notFound(),
    ),
  });
  const shopApiUsed = shopApi ?? shop(live);
  renderApp(`/articles/${fx.articleDetail.slug}`, { api, shopApi: shopApiUsed });
  return shopApiUsed;
}

const endPanel = () => document.querySelector('[data-newsletter="article-end"]');
const sidebarNewsletter = () => document.querySelector('[data-sidebar-section="newsletter_cta"]');

// ---- sticky sidebar ---------------------------------------------------------------------

describe("stickyTop", () => {
  const blocks = (...heights) => {
    let top = 0;
    return heights.map((height) => {
      const block = { top, height };
      top += height + 40;
      return block;
    });
  };

  it("sticks the whole sidebar below the header when it fits the screen", () => {
    expect(stickyTop(blocks(200, 200), 900)).toBe(STICKY_OFFSET);
  });

  it("lets a tall sidebar scroll, then keeps the sections at its end in view", () => {
    // 5 × 280px with 40px gaps on a 768px screen: 640px available below the header.
    const top = stickyTop(blocks(280, 280, 280, 280, 280), 768);
    // The last two sections (960px down) stick; nothing is cut off at the bottom.
    expect(top).toBe(STICKY_OFFSET - 960);
    expect(1560 + top).toBeLessThanOrEqual(768 - 24);
  });

  it("doesn't stick at all when even the last section is taller than the screen", () => {
    expect(stickyTop(blocks(300, 900), 768)).toBeNull();
  });

  it("ignores sections hidden at this width", () => {
    expect(stickyTop([{ top: 0, height: 0 }], 900)).toBeNull();
    expect(stickyTop([...blocks(200), { top: 240, height: 0 }], 900)).toBe(STICKY_OFFSET);
  });
});

describe("sticky article sidebar", () => {
  afterEach(() => vi.restoreAllMocks());

  /** Pretend to be a 1440 × 768 desktop where each sidebar section is 280px tall. */
  function desktop(wide = true) {
    vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
      matches: wide && query.includes("1024"),
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function rect() {
      // Where things are on screen at the top of the page, moved by the sticky offset.
      const inner = this.closest?.("[data-sticky]");
      const shift = Number.parseInt(inner?.style.top || "0", 10);
      const block = this.closest?.("[data-sidebar-section]");
      if (!block) return { top: shift, bottom: shift, height: 0, left: 0, right: 0, width: 0 };
      const index = [...block.parentElement.children].indexOf(block);
      const top = index * 320 + shift;
      return { top, bottom: top + 280, height: 280, left: 0, right: 0, width: 300 };
    });
  }

  function renderSidebar(sections) {
    const store = createAppStore({ api: createFakeApi() });
    render(
      <Provider store={store}>
        <MemoryRouter>
          <button type="button">Article</button>
          <ArticleSidebar sections={sections} />
        </MemoryRouter>
      </Provider>,
    );
    return document.querySelector("aside [data-sticky]");
  }

  const five = () =>
    ["popular", "related", "picks", "latest", "more"].map((key, i) =>
      section(key, "article_collection", {
        heading: `Section ${i + 1}`,
        articles: [{ ...a2, slug: `story-${key}`, title: `Story ${key}` }],
      }),
    );

  it("sticks on desktop below the header, keeping the sections at its end in view", async () => {
    desktop();
    const inner = renderSidebar(five());
    await waitFor(() => expect(inner).toHaveAttribute("data-sticky", "true"));
    expect(inner).toHaveClass("lg:sticky");
    expect(inner.style.top).toBe(`${STICKY_OFFSET - 960}px`);
    // The column it sticks in is the aside, which ends with the article layout.
    expect(inner.parentElement.tagName).toBe("ASIDE");
  });

  it("scrolls normally on phones and tablets, where the sidebar sits below the article", async () => {
    desktop(false);
    const inner = renderSidebar(five());
    await act(() => new Promise((r) => requestAnimationFrame(r)));
    expect(inner).toHaveAttribute("data-sticky", "false");
    expect(inner).not.toHaveClass("lg:sticky");
    expect(inner.getAttribute("style")).toBeNull();
    // Tablets: two columns below the article; phones: one.
    expect(inner.className).toMatch(/md:grid-cols-2/);
  });

  it("returns to its normal place when keyboard focus reaches a link scrolled off screen", async () => {
    desktop();
    const inner = renderSidebar(five());
    await waitFor(() => expect(inner).toHaveAttribute("data-sticky", "true"));
    // The first section has scrolled away above the header while stuck.
    act(() => screen.getByRole("link", { name: "Story popular" }).focus());
    expect(inner).toHaveAttribute("data-sticky", "false");
    expect(inner.style.top).toBe("");
    // Leaving the sidebar puts it back.
    act(() => screen.getByRole("button", { name: "Article" }).focus());
    expect(inner).toHaveAttribute("data-sticky", "true");
    // A link that is in view while stuck doesn't move anything.
    act(() => screen.getByRole("link", { name: "Story more" }).focus());
    expect(inner).toHaveAttribute("data-sticky", "true");
  });

  it("keeps the editor's order and labels while sticky", async () => {
    desktop();
    const inner = renderSidebar(five());
    await waitFor(() => expect(inner).toHaveAttribute("data-sticky", "true"));
    const headings = within(inner)
      .getAllByRole("heading", { level: 2 })
      .map((h) => h.textContent);
    expect(headings).toEqual(["Section 1", "Section 2", "Section 3", "Section 4", "Section 5"]);
  });
});

// ---- newsletter placements ---------------------------------------------------------------

describe("newsletter on article pages", () => {
  it("shows nothing at the end of the article, and no form anywhere, while sign-up is closed", async () => {
    openArticle({ open: false });
    await screen.findByRole("heading", { level: 1, name: fx.articleDetail.title });
    expect(endPanel()).toBeNull();
    expect(screen.queryByRole("form", { name: /Subscribe/ })).not.toBeInTheDocument();
    expect(
      within(sidebarNewsletter()).getByText(/isn.t available on the website at the moment/),
    ).toBeInTheDocument();
  });

  it("puts one form per screen size: end of article below lg, the sidebar on wide screens", async () => {
    openArticle();
    await screen.findByRole("heading", { level: 1, name: fx.articleDetail.title });
    await waitFor(() => expect(endPanel()).not.toBeNull());
    const panel = endPanel();
    expect(
      within(panel).getByRole("heading", { name: /Get The Positive Reset every day/ }),
    ).toBeInTheDocument();
    expect(within(panel).getByText("A Better Mindset. A Brighter Life.")).toBeInTheDocument();
    // The end-of-article form is for phones and tablets...
    const endForm = within(panel).getByRole("form", { name: /Subscribe to The Positive Reset/ });
    expect(endForm.parentElement).toHaveClass("lg:hidden");
    // ...and the sidebar's for wide screens only (it sits below the article otherwise).
    expect(sidebarNewsletter()).toHaveClass("hidden", "lg:block");
    expect(
      within(sidebarNewsletter()).getByRole("form", { name: /Subscribe/ }),
    ).toBeInTheDocument();
  });

  it("takes wide-screen readers from the end of the article to the sidebar form", async () => {
    const user = userEvent.setup();
    openArticle();
    const button = await screen.findByRole("button", { name: "Sign up for The Positive Reset" });
    expect(button.parentElement).toHaveClass("hidden", "lg:block");
    await user.click(button);
    expect(document.activeElement).toHaveAttribute("id", "sidebar-newsletter-email");
    expect(sidebarNewsletter()).toContainElement(document.activeElement);
  });

  it("shows the end-of-article form on every screen when the sidebar has no newsletter", async () => {
    openArticle({ sections: sidebar().filter((s) => s.type !== "newsletter_cta") });
    await waitFor(() => expect(endPanel()).not.toBeNull());
    const form = within(endPanel()).getByRole("form", { name: /Subscribe/ });
    expect(form.parentElement).not.toHaveClass("lg:hidden");
    expect(screen.queryByRole("button", { name: /Sign up for/ })).not.toBeInTheDocument();
  });

  it("follows the live readiness check when the prerendered page is out of date", async () => {
    // Prerendered closed, but the backend now reports sign-ups open: the form appears.
    openArticle({ open: false, live: true });
    await waitFor(() => expect(endPanel()).not.toBeNull());
    expect(screen.queryByText(/isn.t available on the website/)).not.toBeInTheDocument();
  });

  it("never shows a form the backend says is closed, even if the page said open", async () => {
    openArticle({ open: true, live: false });
    await screen.findByRole("heading", { level: 1, name: fx.articleDetail.title });
    await waitFor(() =>
      expect(screen.queryByRole("form", { name: /Subscribe/ })).not.toBeInTheDocument(),
    );
    expect(endPanel()).toBeNull();
    expect(
      within(sidebarNewsletter()).getByText(/isn.t available on the website at the moment/),
    ).toBeInTheDocument();
  });
});

describe("subscribing", () => {
  async function endForm(shopApi) {
    openArticle({
      shopApi,
      sections: sidebar().filter((s) => s.type !== "newsletter_cta"),
    });
    await waitFor(() => expect(endPanel()).not.toBeNull());
    return within(endPanel()).getByRole("form", { name: /Subscribe/ });
  }

  it("requires a valid email and unticked-by-default consent, focusing the first problem", async () => {
    const user = userEvent.setup();
    const shopApi = shop();
    const form = await endForm(shopApi);
    const consent = within(form).getByRole("checkbox", { name: CONSENT });
    expect(consent).not.toBeChecked();
    expect(consent).toBeRequired();
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    const email = within(form).getByLabelText(/Email address/);
    await waitFor(() => expect(email).toHaveFocus());
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription("Enter a valid email address.");
    await user.type(email, "reader@example.com");
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(consent).toHaveFocus());
    expect(consent).toHaveAccessibleDescription(/tick the box/);
    expect(shopApi.subscribe).not.toHaveBeenCalled();
  });

  it("submits with the live consent version, shows progress, then a focused confirmation", async () => {
    const user = userEvent.setup();
    let finish;
    const shopApi = shop(true, {
      subscribe: vi.fn(
        () =>
          new Promise((resolve) => {
            finish = () => resolve({ data: { status: "check_email", message: "Thank you." } });
          }),
      ),
    });
    const form = await endForm(shopApi);
    await user.type(within(form).getByLabelText(/First name/), "Ada");
    await user.type(within(form).getByLabelText(/Email address/), " reader@example.com ");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    const busy = within(form).getByRole("button", { name: "Subscribing…" });
    expect(busy).toBeDisabled();
    expect(form).toHaveAttribute("aria-busy", "true");
    await user.click(busy); // a second click while sending does nothing
    expect(shopApi.subscribe).toHaveBeenCalledTimes(1);
    expect(shopApi.subscribe.mock.calls[0][0]).toMatchObject({
      email: "reader@example.com",
      first_name: "Ada",
      consent: true,
      consent_version: "2026-11",
      source: "article",
      source_detail: `/articles/${fx.articleDetail.slug}`,
    });
    await act(async () => finish());
    const done = await within(endPanel()).findByRole("status");
    expect(done).toHaveTextContent("Almost there — check your inbox.");
    // Existing subscribers get the same answer (nothing is revealed) and a note by email.
    expect(done).toHaveTextContent(/Already subscribed\? We.ll send you a short note/);
    await waitFor(() => expect(done).toHaveFocus());
  });

  it("asks again with the new wording when the consent text changed meanwhile", async () => {
    const user = userEvent.setup();
    const NEW = "Yes, email me The Positive Reset daily (updated wording).";
    let version = "2026-11";
    const shopApi = shop(true, {
      newsletterStatus: vi.fn(async () => ({
        data: {
          signup_open: true,
          consent_text: version === "2026-11" ? CONSENT : NEW,
          consent_version: version,
        },
      })),
      subscribe: vi.fn(async () => {
        version = "2026-12";
        throw new ApiError({
          status: 409,
          code: "conflict",
          message: "Our consent wording has just been updated. Please review it and try again.",
          details: { code: "consent_changed" },
        });
      }),
    });
    const form = await endForm(shopApi);
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/consent wording/);
    const fresh = await within(form).findByRole("checkbox", { name: NEW });
    expect(fresh).not.toBeChecked();
  });

  it("switches to the closed state if the backend has closed sign-ups", async () => {
    const user = userEvent.setup();
    let open = true;
    const shopApi = shop(true, {
      newsletterStatus: vi.fn(async () => ({
        data: {
          signup_open: open,
          consent_text: open ? CONSENT : "",
          consent_version: open ? "2026-11" : "",
        },
      })),
      subscribe: vi.fn(async () => {
        open = false;
        throw new ApiError({
          status: 409,
          code: "conflict",
          message: "Newsletter sign-ups are not open yet.",
        });
      }),
    });
    const form = await endForm(shopApi);
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(endPanel()).toBeNull());
    expect(screen.queryByRole("form", { name: /Subscribe/ })).not.toBeInTheDocument();
  });

  it("explains server errors and keeps what the reader typed", async () => {
    const user = userEvent.setup();
    const shopApi = shop(true, {
      subscribe: vi.fn(async () => {
        throw new ApiError({ status: 500, code: "server_error", message: "boom" });
      }),
    });
    const form = await endForm(shopApi);
    const email = within(form).getByLabelText(/Email address/);
    await user.type(email, "reader@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/Something went wrong/);
    expect(email).toHaveValue("reader@example.com");
    expect(within(form).getByRole("button", { name: "Subscribe" })).toBeEnabled();
  });

  it("shows field errors from the backend next to the field", async () => {
    const user = userEvent.setup();
    const shopApi = shop(true, {
      subscribe: vi.fn(async () => {
        throw new ApiError({
          status: 400,
          code: "validation_error",
          message: "Please check the form.",
          details: { email: ["Enter a valid email address."] },
        });
      }),
    });
    const form = await endForm(shopApi);
    const email = within(form).getByLabelText(/Email address/);
    await user.type(email, "reader@example.co");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(email).toHaveAttribute("aria-invalid", "true"));
    await waitFor(() => expect(email).toHaveFocus());
  });
});

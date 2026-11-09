import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeShopApi } from "@/test/commerceFake";
import { createFakeAdminApi } from "@/test/adminFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, preloadAdminApp, renderApp, tickAll } from "@/test/utils";

beforeAll(async () => {
  await preloadAdminApp();
});

const COLLECTION_CONSENT =
  "Yes, send me The Positive Reset, the daily email newsletter from Think Positive Always. " +
  "Think Positive Always will store my email address (and first name, if I give it) to send " +
  "me this newsletter, using an email service provider. I can unsubscribe at any time.";

const collectingSite = {
  ...fx.site,
  newsletter: {
    ...fx.site.newsletter,
    is_open: true,
    signup_mode: "collection_only",
    confirmation_email: false,
    consent_text: COLLECTION_CONSENT,
    consent_version: "2026-11-collection",
  },
};

function collectingShop(overrides = {}) {
  return {
    ...createFakeShopApi(),
    newsletterStatus: vi.fn(async () => ({
      data: {
        name: "The Positive Reset",
        signup_open: true,
        signup_mode: "collection_only",
        confirmation_email: false,
        consent_text: COLLECTION_CONSENT,
        consent_version: "2026-11-collection",
      },
    })),
    subscribe: vi.fn(async () => ({
      data: {
        status: "received",
        message: "Thank you. Your sign-up for The Positive Reset has been received.",
      },
    })),
    ...overrides,
  };
}

const renderNewsletterPage = (shopApi = collectingShop()) => {
  renderApp("/newsletter", {
    api: createFakeApi({ getSite: vi.fn(async () => ({ data: collectingSite })) }),
    shopApi,
  });
  return shopApi;
};

describe("collection-only sign-up", () => {
  it("shows the collection consent wording, unticked, and promises no confirmation email", async () => {
    renderNewsletterPage();
    const [form] = await screen.findAllByRole("form", { name: /Subscribe to The Positive Reset/ });
    const consent = within(form).getByRole("checkbox", { name: COLLECTION_CONSENT });
    expect(consent).not.toBeChecked();
    expect(within(form).getByLabelText(/First name/)).toBeInTheDocument();
    expect(within(form).queryByText(/email you to confirm/i)).not.toBeInTheDocument();
    expect(within(form).getByText(/link to unsubscribe at any time/)).toBeInTheDocument();
  });

  it("requires consent and a valid email before sending anything", async () => {
    const user = userEvent.setup();
    const shopApi = renderNewsletterPage();
    const [form] = await screen.findAllByRole("form", { name: /Subscribe/ });
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    expect(within(form).getByText(/tick the box/)).toBeInTheDocument();
    expect(shopApi.subscribe).not.toHaveBeenCalled();
  });

  it("records the shown consent version and thanks the reader without mentioning an inbox", async () => {
    const user = userEvent.setup();
    const shopApi = renderNewsletterPage();
    const [form] = await screen.findAllByRole("form", { name: /Subscribe/ });
    await user.type(within(form).getByLabelText(/First name/), "Ada");
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await tickAll(user, form);
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(shopApi.subscribe).toHaveBeenCalledTimes(1));
    expect(shopApi.subscribe.mock.calls[0][0]).toMatchObject({
      email: "reader@example.com",
      first_name: "Ada",
      consent: true,
      consent_version: "2026-11-collection",
      source: "newsletter_page",
    });
    const done = await screen.findByText("Thank you for signing up.");
    const status = done.closest('[role="status"]');
    expect(status).toHaveTextContent(/sign-up for The Positive Reset has been received/);
    // Nothing about inboxes, confirmation links or "already subscribed".
    expect(status).not.toHaveTextContent(/inbox|confirmation|already subscribed/i);
    await waitFor(() => expect(status).toHaveFocus());
  });
});

describe("collection-only in the admin", () => {
  function adminWithCollected() {
    const adminApi = createFakeAdminApi({ role: "newsletter_manager" });
    const collected = {
      id: 2,
      email: "collected@example.com",
      first_name: "Ada",
      status: "collected",
      marketable: false,
      verified: false,
      verification: "website_signup_no_confirmation_email_sent",
      source: "article",
      preferences: ["weekly"],
      tags: [],
      consent_at: "2026-11-08T10:00:00.000Z",
      confirmed_at: null,
    };
    adminApi.subscribers.list = vi.fn(async () => ({
      data: [collected],
      meta: { total: 1, status_counts: { collected: 1 } },
    }));
    adminApi.subscribers.get = vi.fn(async () => ({
      data: {
        ...collected,
        consent: {
          at: collected.consent_at,
          text: COLLECTION_CONSENT,
          version: "2026-11-collection",
          ip_hash_recorded: true,
          source: "article",
          source_detail: "/articles/a-story",
          confirmation_sent_at: null,
          confirmed_at: null,
        },
        interests: [],
        unsubscribe_reason: "",
        import_batch: "",
        suppressed: null,
        activity: [],
        messages: {},
      },
    }));
    return adminApi;
  }

  it("labels collected sign-ups as not verified and offers the provider export", async () => {
    renderApp("/admin/subscribers", { adminApi: adminWithCollected() });
    expect(await screen.findByRole("link", { name: "collected@example.com" })).toBeInTheDocument();
    expect(screen.getAllByText("Collected (not verified)").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /All contacts with consent/ })).toHaveAttribute(
      "href",
      "/api/v1/admin/subscribers/export/provider?",
    );
    expect(screen.getByRole("link", { name: /Verified \(double opt-in\) only/ })).toHaveAttribute(
      "href",
      "/api/v1/admin/subscribers/export/provider?verified_only=1",
    );
  });

  it("shows on the subscriber page that no confirmation email was sent", async () => {
    renderApp("/admin/subscribers/2", { adminApi: adminWithCollected() });
    expect(
      await screen.findByText("Not verified: collected on the website, no confirmation email sent"),
    ).toBeInTheDocument();
    expect(screen.getByText("Never sent")).toBeInTheDocument();
    expect(screen.getByText("2026-11-collection")).toBeInTheDocument();
  });

  it("hides the provider export from people without export permission", async () => {
    renderApp("/admin/subscribers", {
      adminApi: createFakeAdminApi({ role: "marketing_manager" }),
    });
    await screen.findByRole("link", { name: "reader@example.com" });
    expect(screen.queryByRole("link", { name: /All contacts with consent/ })).toBeNull();
  });
});

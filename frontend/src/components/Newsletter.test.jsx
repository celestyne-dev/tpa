import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { redirectTo } from "@/commerce/hooks";
import { ApiError } from "@/services/apiClient";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeAdminApi } from "@/test/adminFake";
import { createFakeApi, preloadAdminApp, preloadCommerce, renderApp } from "@/test/utils";

beforeAll(async () => {
  await preloadCommerce();
  await preloadAdminApp();
});

const CONSENT = "Yes, email me The Positive Reset. I can unsubscribe at any time.";
const openSite = {
  ...fx.site,
  newsletter: {
    ...fx.site.newsletter,
    is_open: true,
    consent_text: CONSENT,
    consent_version: "2026-10",
    preferences: [],
    default_preferences: ["weekly"],
  },
};

function newsletterShop(overrides = {}) {
  const ok = (data) => Promise.resolve({ data });
  return {
    ...createFakeShopApi(),
    newsletterStatus: vi.fn(() =>
      ok({ signup_open: true, consent_text: CONSENT, consent_version: "2026-10" }),
    ),
    subscribe: vi.fn(() => ok({ status: "check_email", message: "Thank you." })),
    confirmSubscription: vi.fn(() => ok({ status: "subscribed", preferences_token: "m.1.sig" })),
    unsubscribe: vi.fn(() => ok({ status: "unsubscribed", email: "r•••@example.com" })),
    claimLeadMagnet: vi.fn(() => ok({ status: "check_email", message: "Thank you." })),
    leadMagnetAccess: vi.fn(() =>
      ok({
        lead_magnet: { slug: "worksheet", title: "Reflection worksheet", description: "" },
        files: [{ id: "f1", title: "Worksheet", format: "PDF", size_bytes: 2048 }],
        downloads_remaining: 9,
      }),
    ),
    leadMagnetDownload: vi.fn(() => ok({ url: "/api/v1/lead-magnets/download/x" })),
    ...overrides,
  };
}

const withHash = (hash) => window.history.replaceState(null, "", `/${hash}`);

describe("public signup", () => {
  it("shows an honest coming-soon notice and no form while sending is not configured", async () => {
    renderApp("/newsletter");
    expect(await screen.findByText("Sign-ups are opening soon.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /Subscribe/ })).not.toBeInTheDocument();
  });

  it("validates accessibly, records the shown consent and confirms by email", async () => {
    const user = userEvent.setup();
    const shopApi = newsletterShop();
    renderApp("/newsletter", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: openSite })) }),
      shopApi,
    });
    const form = (
      await screen.findAllByRole("form", { name: /Subscribe to The Positive Reset/ })
    )[0];
    const consent = within(form).getByRole("checkbox", { name: CONSENT });
    expect(consent).not.toBeChecked(); // never pre-ticked
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    const email = within(form).getByLabelText(/Email address/);
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(within(form).getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(within(form).getByText(/tick the box/)).toBeInTheDocument();
    expect(shopApi.subscribe).not.toHaveBeenCalled();
    await user.type(email, "reader@example.com");
    await user.click(consent);
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(shopApi.subscribe).toHaveBeenCalled());
    const body = shopApi.subscribe.mock.calls[0][0];
    expect(body).toMatchObject({
      email: "reader@example.com",
      consent: true,
      consent_version: "2026-10",
      source: "newsletter_page",
      website: "",
    });
    expect(await screen.findByText("Almost there — check your inbox.")).toBeInTheDocument();
  });

  it("explains rate limits in plain language", async () => {
    const user = userEvent.setup();
    const shopApi = newsletterShop({
      subscribe: vi.fn(() =>
        Promise.reject(new ApiError({ status: 429, code: "rate_limited", message: "Too many" })),
      ),
    });
    renderApp("/newsletter", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: openSite })) }),
      shopApi,
    });
    const form = (await screen.findAllByRole("form", { name: /Subscribe/ }))[0];
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/Too many attempts/);
  });
});

describe("signed newsletter links", () => {
  it("confirms only after a click", async () => {
    const user = userEvent.setup();
    const shopApi = newsletterShop();
    withHash("#token=pid.1.123.sig");
    renderApp("/newsletter/confirm", { shopApi });
    const button = await screen.findByRole("button", { name: "Confirm my subscription" });
    expect(shopApi.confirmSubscription).not.toHaveBeenCalled();
    await user.click(button);
    expect(shopApi.confirmSubscription).toHaveBeenCalledWith("pid.1.123.sig");
    expect(await screen.findByText(/you're subscribed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose what you receive" })).toHaveAttribute(
      "href",
      "/newsletter/preferences#token=m.1.sig",
    );
  });

  it("unsubscribes with one action", async () => {
    const user = userEvent.setup();
    const shopApi = newsletterShop();
    withHash("#token=m.1.sig");
    renderApp("/newsletter/unsubscribe", { shopApi });
    await user.click(await screen.findByRole("button", { name: "Unsubscribe" }));
    expect(shopApi.unsubscribe).toHaveBeenCalledWith("m.1.sig", { reason: "" });
    expect(await screen.findByText(/won't receive The Positive Reset/)).toBeInTheDocument();
  });

  it("downloads a free resource through a short-lived link", async () => {
    const user = userEvent.setup();
    const go = vi.spyOn(redirectTo, "go").mockImplementation(() => {});
    const shopApi = newsletterShop();
    withHash("#token=claim-token");
    renderApp("/resources/access", { shopApi });
    await user.click(await screen.findByRole("button", { name: /Download/ }));
    expect(shopApi.leadMagnetDownload).toHaveBeenCalledWith("claim-token", "f1");
    expect(go).toHaveBeenCalledWith("/api/v1/lead-magnets/download/x");
    go.mockRestore();
  });

  it("offers a new link when the old one expired", async () => {
    const shopApi = newsletterShop({
      leadMagnetAccess: vi.fn(() =>
        Promise.reject(
          new ApiError({
            status: 410,
            code: "link_expired",
            message: "This download link has expired. Request a new one below.",
            details: { slug: "worksheet" },
          }),
        ),
      ),
      leadMagnet: vi.fn(() =>
        Promise.resolve({
          data: {
            slug: "worksheet",
            title: "Reflection worksheet",
            available: true,
            newsletter_optin: "optional",
            formats: ["PDF"],
          },
        }),
      ),
    });
    withHash("#token=old");
    renderApp("/resources/access", { shopApi });
    expect(await screen.findByText(/has expired/)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Email me the free resource" }),
    ).toBeInTheDocument();
  });
});

describe("newsletter admin", () => {
  it("shows the newsletter section only to roles that can use it", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Subscribers" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Newsletters" })).not.toBeInTheDocument();
  });

  it("lets a Marketing Manager draft but not approve, send or change sending settings", async () => {
    renderApp("/admin/newsletters/7", {
      adminApi: createFakeAdminApi({ role: "marketing_manager" }),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Weekly #1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send a test to me" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve for sending" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Send now/ })).not.toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Email Settings" })).not.toBeInTheDocument();
    expect(await screen.findByText(/Test mode — email reaches only/)).toBeInTheDocument();
  });

  it("lets a Newsletter Manager approve and previews without sending", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: "newsletter_manager" });
    renderApp("/admin/newsletters/7", { adminApi });
    await user.click(await screen.findByRole("button", { name: "Preview" }));
    expect(await screen.findByTitle("Email preview")).toHaveAttribute("sandbox", "");
    expect(adminApi.newsletters.action).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Approve for sending" }));
    await waitFor(() =>
      expect(adminApi.newsletters.action).toHaveBeenCalledWith(7, "approve", undefined),
    );
    expect(await screen.findByRole("button", { name: /Send now/ })).toBeInTheDocument();
  });

  it("lists subscribers with their consent status", async () => {
    renderApp("/admin/subscribers", {
      adminApi: createFakeAdminApi({ role: "newsletter_manager" }),
    });
    expect(await screen.findByRole("link", { name: "reader@example.com" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Export matching subscribers/ })).toBeInTheDocument();
  });
});

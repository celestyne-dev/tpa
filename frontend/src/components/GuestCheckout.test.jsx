import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cartStore } from "@/commerce/cartStore";
import { guestOrders } from "@/commerce/guestOrders";
import { redirectTo } from "@/commerce/hooks";
import { createFakeShopApi, customerProfile, guestOrderFor } from "@/test/commerceFake";
import { preloadAdminApp, preloadCommerce, renderApp } from "@/test/utils";

const CALM = "a1a1a1a1a1a1a1a1";
const ORDER = "order0000000000000000000000000001";
const ORDER_TOKEN = "guest-order-token-0000000000000000000000000";
const ACCESS_TOKEN = "valid-access-token-000000000000000000000000";

beforeAll(async () => {
  await preloadCommerce();
  await preloadAdminApp();
});
beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.spyOn(redirectTo, "go").mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("guest checkout", () => {
  it("buys with an email address only and keeps the order token in this tab", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi();
    renderApp("/checkout", { shopApi });
    const pay = await screen.findByRole("button", { name: /Pay USD 15.00/ });
    await user.click(screen.getByRole("checkbox", { name: /terms of sale/ }));
    expect(pay).toBeDisabled(); // no email yet
    await user.type(screen.getByLabelText(/Email address/), "not-an-email");
    expect(pay).toBeDisabled();
    await user.clear(screen.getByLabelText(/Email address/));
    await user.type(screen.getByLabelText(/Email address/), "  buyer@example.com ");
    await user.type(screen.getByLabelText(/Name/), "Ama");
    expect(pay).toBeEnabled();
    await user.click(pay);
    await waitFor(() =>
      expect(redirectTo.go).toHaveBeenCalledWith("https://checkout.paystack.com/guest-usd"),
    );
    const body = shopApi.guestCheckout.mock.calls[0][0];
    expect(body).toMatchObject({
      email: "buyer@example.com",
      name: "Ama",
      items: [CALM],
      currency: "USD",
      expected_total_minor: 1500,
      accept_terms: true,
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f]{32}$/);
    expect(shopApi.checkout).not.toHaveBeenCalled();
    expect(guestOrders.token(ORDER)).toBe(ORDER_TOKEN);
    expect(window.localStorage.getItem(`tpa-guest-order:${ORDER}`)).toBeNull();
  });

  it("lets shoppers log in instead and then checks out with their account", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi();
    renderApp("/checkout", { shopApi });
    await user.click(await screen.findByRole("radio", { name: /Log in/ }));
    expect(screen.queryByLabelText(/Email address/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create an account" })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Email/), "reader@example.com");
    await user.type(screen.getByLabelText(/^Password/), "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText(/Receipt and download instructions go to/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /terms of sale/ }));
    await user.click(screen.getByRole("button", { name: /Pay USD 15.00/ }));
    await waitFor(() => expect(shopApi.checkout).toHaveBeenCalled());
    expect(shopApi.guestCheckout).not.toHaveBeenCalled();
  });

  it("offers creating an account from the checkout", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    renderApp("/checkout");
    await user.click(await screen.findByRole("radio", { name: /Log in/ }));
    await user.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("button", { name: /Create account/ })).toBeInTheDocument();
  });
});

describe("guest order status", () => {
  it("confirms the payment from the server and offers downloads on the page", async () => {
    const user = userEvent.setup();
    guestOrders.save(ORDER, ORDER_TOKEN);
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi();
    shopApi.verifyGuestOrder.mockResolvedValueOnce({
      data: { outcome: "pending", order: guestOrderFor("awaiting_payment") },
    });
    renderApp(`/checkout/complete?order=${ORDER}&guest=1`, { shopApi });
    expect(
      await screen.findByRole("heading", { name: "Waiting for payment confirmation" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/we'll also email b•••@example.com/)).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Payment confirmed" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(shopApi.verifyGuestOrder).toHaveBeenCalledWith(ORDER, ORDER_TOKEN);
    expect(shopApi.verifyOrder).not.toHaveBeenCalled();
    expect(screen.getByText("b•••@example.com")).toBeInTheDocument();
    expect(cartStore.getSnapshot()).toEqual([]);
    await user.click(
      screen.getByRole("button", { name: "Download Workbook latest version (PDF)" }),
    );
    expect(shopApi.guestOrderDownload).toHaveBeenCalledWith(ORDER, ORDER_TOKEN, 7, 22);
    await waitFor(() => expect(redirectTo.go).toHaveBeenCalledWith("/api/v1/downloads/guest-22"));
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("doesn't need an account and explains what to do without the tab's token", async () => {
    const shopApi = createFakeShopApi();
    renderApp(`/checkout/complete?order=${ORDER}&guest=1`, { shopApi });
    expect(await screen.findByText(/started in another browser or tab/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get a new download link" })).toHaveAttribute(
      "href",
      "/purchases",
    );
    expect(shopApi.verifyGuestOrder).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Log in" })).not.toBeInTheDocument();
  });

  it("retries a failed guest payment with the order token", async () => {
    const user = userEvent.setup();
    guestOrders.save(ORDER, ORDER_TOKEN);
    const shopApi = createFakeShopApi();
    shopApi.verifyGuestOrder.mockResolvedValue({
      data: { outcome: "failed", order: guestOrderFor("failed") },
    });
    renderApp(`/checkout/complete?order=${ORDER}&guest=1`, { shopApi });
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(shopApi.retryGuestOrder).toHaveBeenCalledWith(ORDER, ORDER_TOKEN);
    await waitFor(() =>
      expect(redirectTo.go).toHaveBeenCalledWith("https://checkout.paystack.com/retry"),
    );
  });
});

describe("guest purchases page", () => {
  it("opens the emailed link, removes the token from the address bar and downloads", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", `/purchases#token=${ACCESS_TOKEN}`);
    const shopApi = createFakeShopApi();
    renderApp("/purchases", { shopApi });
    expect(await screen.findByText("Calm Mornings Workbook", { selector: "a" })).toBeVisible();
    expect(window.location.hash).toBe("");
    expect(shopApi.guestLibrary).toHaveBeenCalledWith(ACCESS_TOKEN);
    const orders = screen.getByRole("region", { name: "Orders" });
    expect(within(orders).getByText("TPA-261023-ABCDEF")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Download Workbook version you received (PDF)" }),
    );
    expect(shopApi.guestLibraryDownload).toHaveBeenCalledWith(ACCESS_TOKEN, 7, 21);
    await waitFor(() => expect(redirectTo.go).toHaveBeenCalledWith("/api/v1/downloads/guest-21"));
  });

  it("asks for a new link when the link has expired, with a generic answer", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/purchases#token=expired-token-0000000000000000000000");
    const shopApi = createFakeShopApi();
    renderApp("/purchases", { shopApi });
    expect(await screen.findByText(/expired or was replaced/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Email address used at checkout/), "buyer@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByText(/If purchases were made with guest checkout/)).toBeVisible();
    expect(shopApi.requestGuestAccess).toHaveBeenCalledWith("buyer@example.com");
  });

  it("shows the recovery form without a link", async () => {
    renderApp("/purchases");
    expect(await screen.findByRole("heading", { name: "Your purchases" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Email me a link" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in to your library" })).toBeInTheDocument();
  });
});

describe("claiming guest purchases", () => {
  it("tells unconfirmed accounts that guest purchases appear after confirming", async () => {
    const shopApi = createFakeShopApi({ customer: customerProfile({ email_verified: false }) });
    shopApi.library.mockResolvedValueOnce({ data: [] });
    renderApp("/account/library", { shopApi });
    expect(await screen.findByText("Bought something without an account?")).toBeVisible();
    expect(screen.getByRole("button", { name: "Send a new confirmation link" })).toBeVisible();
  });

  it("doesn't show the note once the email is confirmed", async () => {
    renderApp("/account/library", {
      shopApi: createFakeShopApi({ customer: customerProfile() }),
    });
    await screen.findByRole("heading", { level: 1, name: "Your library" });
    expect(screen.queryByText("Bought something without an account?")).not.toBeInTheDocument();
  });
});

describe("header account and cart controls", () => {
  it("have tooltips that match their accessible names", async () => {
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    renderApp("/");
    const account = await screen.findByRole("button", { name: "Log in or create an account" });
    expect(account).toHaveTextContent("Log in");
    const cart = screen.getByRole("link", { name: "Cart, 1 item" });
    expect(cart).toHaveTextContent("Cart");
    const user = userEvent.setup();
    await user.click(account);
    expect(screen.getByRole("link", { name: "Find a guest purchase" })).toHaveAttribute(
      "href",
      "/purchases",
    );
  });

  it("labels the signed-in account menu", async () => {
    // A readable CSRF cookie means a session may exist, so the header confirms it.
    document.cookie = "tpa_customer_csrf=test-token; path=/";
    try {
      renderApp("/", { shopApi: createFakeShopApi({ customer: customerProfile() }) });
      const account = await screen.findByRole("button", { name: "Account menu" });
      expect(account).toHaveTextContent("Account");
    } finally {
      document.cookie = "tpa_customer_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    }
  });
});

describe("admin sign-in page", () => {
  it("sends an administrator who is already signed in to the dashboard", async () => {
    renderApp("/admin/login");
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Admin sign in" })).not.toBeInTheDocument();
  });

  it("honours a safe next path and ignores unsafe ones", async () => {
    const first = renderApp("/admin/login?next=%2Fadmin%2Farticles");
    expect(await screen.findByRole("heading", { level: 1, name: "Articles" })).toBeVisible();
    first.unmount();
    renderApp("/admin/login?next=https%3A%2F%2Fevil.example%2Fadmin");
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  });
});

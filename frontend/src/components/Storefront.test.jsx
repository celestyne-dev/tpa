import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { redirectTo } from "@/commerce/hooks";
import { cartStore } from "@/commerce/cartStore";
import { ApiError } from "@/services/apiClient";
import { createFakeShopApi, customerProfile, orderFor } from "@/test/commerceFake";
import { preloadCommerce, renderApp } from "@/test/utils";

const CALM = "a1a1a1a1a1a1a1a1";
const SOON = "b2b2b2b2b2b2b2b2";

beforeAll(preloadCommerce);
beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(redirectTo, "go").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("shop", () => {
  it("lists products with explicit currency prices and honest coming-soon cards", async () => {
    renderApp("/shop");
    const calm = await screen.findByRole("heading", { name: "Calm Mornings Workbook" });
    const card = calm.closest("li");
    expect(within(card).getByText("USD 15.00")).toBeInTheDocument();
    const soon = screen.getByRole("heading", { name: "The Power of Starting Again" }).closest("li");
    expect(within(soon).getByText("Coming soon")).toBeInTheDocument();
    expect(within(soon).queryByText(/USD|KES/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Gratitude Worksheet" }).closest("li"),
    ).toHaveTextContent("Free");
    expect(screen.queryByText(/rating|reviews?/i)).not.toBeInTheDocument();
  });

  it("filters, searches, sorts and switches the display currency without conversion", async () => {
    const user = userEvent.setup();
    renderApp("/shop");
    await screen.findByRole("heading", { name: "Calm Mornings Workbook" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Category" }), "journals");
    expect(screen.getByText("1 product")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Deep Reset Journal" })).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Category" }), "");
    await user.type(screen.getByRole("searchbox", { name: "Search products" }), "starting");
    expect(screen.getByText("1 product")).toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Search products" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Sort by" }), "price_asc");
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles.indexOf("Deep Reset Journal")).toBeLessThan(
      titles.indexOf("Calm Mornings Workbook"),
    );
    await user.click(screen.getAllByRole("button", { name: "KES" })[0]);
    const calm = screen.getByRole("heading", { name: "Calm Mornings Workbook" }).closest("li");
    expect(within(calm).getByText("KES 1,950.00")).toBeInTheDocument();
    const usdOnly = screen.getByRole("heading", { name: "Deep Reset Journal" }).closest("li");
    expect(within(usdOnly).getByText(/Not priced in KES \(available in USD\)/)).toBeInTheDocument();
  });
});

describe("product page", () => {
  it("shows details, real file formats, structured data and buy actions for products on sale", async () => {
    const user = userEvent.setup();
    renderApp("/shop/calm-mornings-workbook");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Calm Mornings Workbook" }),
    ).toBeInTheDocument();
    expect(screen.getByText("USD 15.00")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument(); // real page count entered by the editor
    expect(screen.getByText("Is it printable?")).toBeInTheDocument();
    const ld = [...document.head.querySelectorAll('script[type="application/ld+json"]')]
      .map((s) => JSON.parse(s.textContent))
      .flat();
    const product = ld.find((d) => d["@type"] === "Product");
    expect(product.offers.map((o) => `${o.priceCurrency} ${o.price}`)).toEqual([
      "USD 15.00",
      "KES 1950.00",
    ]);
    expect(JSON.stringify(ld)).not.toMatch(/aggregateRating|review/i);
    expect(ld.some((d) => d["@type"] === "BreadcrumbList")).toBe(true);

    await user.click(screen.getByRole("button", { name: /Add to cart/ }));
    expect(cartStore.getSnapshot().map((i) => i.id)).toEqual([CALM]);
    expect(screen.getByRole("link", { name: "Cart, 1 item" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /In your cart/ })).toBeInTheDocument();
  });

  it("never offers purchase for coming-soon products and has no Offer data", async () => {
    renderApp("/shop/the-power-of-starting-again");
    expect(
      await screen.findByRole("heading", { level: 1, name: "The Power of Starting Again" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add to cart|buy now/i })).not.toBeInTheDocument();
    expect(screen.getByText(/can't be bought yet/)).toBeInTheDocument();
    const ld = [...document.head.querySelectorAll('script[type="application/ld+json"]')]
      .map((s) => JSON.parse(s.textContent))
      .flat();
    expect(ld.find((d) => d["@type"] === "Product").offers).toBeUndefined();
  });

  it("returns the real 404 page for unknown products", async () => {
    renderApp("/shop/no-such-product");
    expect(
      await screen.findByRole("heading", { level: 1, name: "This page took a different path" }),
    ).toBeInTheDocument();
  });

  it("free products are claimed into the library after signing in", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    shopApi.claimFree.mockRejectedValueOnce(
      new ApiError({ status: 401, code: "customer_auth_required", message: "Please sign in." }),
    );
    renderApp("/shop/gratitude-worksheet", { shopApi });
    await user.click(await screen.findByRole("button", { name: /Get it free/ }));
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });
});

describe("cart and checkout", () => {
  it("quotes the cart on the server, removes items and respects closed checkout", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    cartStore.add({ id: SOON, slug: "the-power-of-starting-again", title: "Soon" });
    const shopApi = createFakeShopApi({ open: false });
    renderApp("/cart", { shopApi });
    expect(await screen.findByText("Coming soon — not available to buy yet.")).toBeInTheDocument();
    expect(shopApi.quote).toHaveBeenCalledWith([CALM, SOON], "USD");
    expect(screen.getByText("Checkout isn't open")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue to checkout" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "Remove The Power of Starting Again" }));
    await waitFor(() => expect(shopApi.quote).toHaveBeenLastCalledWith([CALM], "USD"));
    expect(cartStore.getSnapshot()).toHaveLength(1);
  });

  it("asks guests to sign in before paying", async () => {
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    renderApp("/checkout");
    expect(await screen.findByRole("tab", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pay USD 15.00/ })).toBeDisabled();
  });

  it("sends the server total and an idempotency key, then hands off to Paystack", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    renderApp("/checkout", { shopApi });
    expect(
      await screen.findByText("Test mode — no real money will be charged"),
    ).toBeInTheDocument();
    const pay = await screen.findByRole("button", { name: /Pay USD 15.00/ });
    expect(pay).toBeDisabled(); // terms not accepted yet
    await user.click(screen.getByRole("checkbox", { name: /terms of sale/ }));
    await user.click(pay);
    await waitFor(() =>
      expect(redirectTo.go).toHaveBeenCalledWith("https://checkout.paystack.com/test-usd"),
    );
    const body = shopApi.checkout.mock.calls[0][0];
    expect(body).toMatchObject({
      items: [CALM],
      currency: "USD",
      expected_total_minor: 1500,
      accept_terms: true,
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f]{32}$/);
  });

  it("shows the new total when the price changed instead of charging it", async () => {
    const user = userEvent.setup();
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    shopApi.checkout.mockRejectedValueOnce(
      new ApiError({
        status: 409,
        code: "conflict",
        message: "The price has changed since you opened your cart.",
        details: { code: "price_changed" },
      }),
    );
    renderApp("/checkout", { shopApi });
    await user.click(await screen.findByRole("checkbox", { name: /terms of sale/ }));
    await user.click(screen.getByRole("button", { name: /Pay USD 15.00/ }));
    expect(await screen.findByText(/price has changed/)).toBeInTheDocument();
    expect(redirectTo.go).not.toHaveBeenCalled();
  });

  it("requires a confirmed email before paying", async () => {
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi({ customer: customerProfile({ email_verified: false }) });
    renderApp("/checkout", { shopApi });
    expect(
      await screen.findByRole("button", { name: "Resend confirmation email" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pay USD 15.00/ })).toBeDisabled();
  });
});

describe("payment result", () => {
  it("only shows success once the server reports the order as paid", async () => {
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    shopApi.verifyOrder.mockResolvedValueOnce({
      data: { outcome: "pending", order: orderFor("awaiting_payment") },
    });
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    renderApp("/checkout/complete?order=order0000000000000000000000000001", { shopApi });
    expect(
      await screen.findByRole("heading", { name: "Waiting for payment confirmation" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Payment confirmed")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Payment confirmed" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(cartStore.getSnapshot()).toEqual([]);
    expect(screen.getByRole("link", { name: "Go to your library" })).toBeInTheDocument();
  });

  it("offers a retry after a failed payment", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    shopApi.verifyOrder.mockResolvedValue({
      data: { outcome: "failed", order: orderFor("failed") },
    });
    renderApp("/checkout/complete?order=order0000000000000000000000000001", { shopApi });
    expect(
      await screen.findByRole("heading", { name: "The payment didn't go through" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Paystack said: Declined/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(redirectTo.go).toHaveBeenCalledWith("https://checkout.paystack.com/retry"),
    );
  });
});

describe("customer account", () => {
  it("signs in from the old address, returning to the requested page", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    // The Batch 05 address still works: it redirects to /login and keeps ?next=.
    renderApp("/account/login?next=/account/orders", { shopApi });
    await user.type(await screen.findByLabelText(/Email/), "reader@example.com");
    await user.type(screen.getByLabelText(/^Password/), "wrong-password-123");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("The email or password is incorrect.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/^Password/));
    await user.type(screen.getByLabelText(/^Password/), "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Orders & receipts" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Order TPA-261023-ABCDEF")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View receipt" }));
    expect(await screen.findByText("Receipt R-261023-ABCDEF")).toBeInTheDocument();
  });

  it("does not follow external or admin 'next' links after sign-in", async () => {
    const user = userEvent.setup();
    renderApp("/login?next=//evil.example", { shopApi: createFakeShopApi() });
    await user.type(await screen.findByLabelText(/Email/), "reader@example.com");
    await user.type(screen.getByLabelText(/^Password/), "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: /Hello|Your account/ }),
    ).toBeInTheDocument();
  });

  it("redirects guests from the library to sign in", async () => {
    renderApp("/account/library", { shopApi: createFakeShopApi() });
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });

  it("downloads through a short-lived authorisation (latest and originally purchased versions)", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    renderApp("/account/library", { shopApi });
    const latest = await screen.findByRole("button", { name: /Download Workbook latest version/ });
    expect(screen.getByRole("button", { name: /version you received/ })).toBeInTheDocument();
    await user.click(latest);
    await waitFor(() => expect(redirectTo.go).toHaveBeenCalledWith("/api/v1/downloads/token-22"));
    expect(shopApi.authorizeDownload).toHaveBeenCalledWith(7, 22);
  });

  it("explains refused downloads", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    shopApi.authorizeDownload.mockRejectedValueOnce(
      new ApiError({
        status: 403,
        code: "not_entitled",
        message: "Access to this item has ended.",
      }),
    );
    renderApp("/account/library", { shopApi });
    await user.click(
      await screen.findByRole("button", { name: /Download Workbook latest version/ }),
    );
    expect(await screen.findByText("Access to this item has ended.")).toBeInTheDocument();
    expect(redirectTo.go).not.toHaveBeenCalled();
  });
});

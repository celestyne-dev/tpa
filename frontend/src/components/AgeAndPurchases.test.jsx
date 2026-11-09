import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cartStore } from "@/commerce/cartStore";
import { redirectTo } from "@/commerce/hooks";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { confirmAge, createFakeApi, preloadCommerce, renderApp } from "@/test/utils";

const CALM = "a1a1a1a1a1a1a1a1";
const AGE = "I confirm that I am 18 or older.";
const AGE_ERROR = "Please confirm that you are 18 or older.";

beforeAll(preloadCommerce);
afterEach(() => {
  cartStore.clear?.();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

const closedShop = () =>
  createFakeApi({
    getSite: vi.fn(async () => ({
      data: { ...fx.site, shop: { ...fx.site.shop, purchases_open: false } },
    })),
  });

describe("while no payment provider is connected", () => {
  it("a product page offers no way into checkout", async () => {
    renderApp("/shop/calm-mornings-workbook", { api: closedShop() });
    await screen.findByRole("heading", { level: 1, name: "Calm Mornings Workbook" });
    expect(await screen.findByText("Purchases aren't open yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Buy now/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Add to cart/ })).toBeNull();
    expect(screen.getByText(/No payment is taken/)).toBeInTheDocument();
  });

  it("free products stay available", async () => {
    renderApp("/shop/gratitude-worksheet", { api: closedShop() });
    expect(await screen.findByRole("button", { name: /Get it free/ })).toBeInTheDocument();
    expect(screen.queryByText("Purchases aren't open yet")).toBeNull();
  });

  it("a paid course offers no Add to cart", async () => {
    renderApp("/courses/resilience-course", { api: closedShop() });
    await screen.findByRole("heading", { level: 1, name: "Resilience Course" });
    expect(await screen.findByText("Purchases aren't open yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add to cart/ })).toBeNull();
  });
});

describe("18+ confirmation", () => {
  it("newsletter sign-up asks for it, without a date of birth", async () => {
    const user = userEvent.setup();
    const site = {
      ...fx.site,
      newsletter: {
        ...fx.site.newsletter,
        is_open: true,
        signup_mode: "collection_only",
        confirmation_email: false,
        consent_text: "Yes, send me The Positive Reset.",
        consent_version: "2026-11-collection",
      },
    };
    const shopApi = {
      ...createFakeShopApi(),
      subscribe: vi.fn(async () => ({ data: { status: "received", message: "Thanks." } })),
    };
    renderApp("/newsletter", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: site })) }),
      shopApi,
    });
    const form = await screen.findByRole("form", { name: /Subscribe to The Positive Reset/ });
    const age = within(form).getByRole("checkbox", { name: AGE });
    expect(age).not.toBeChecked();
    expect(age).toBeRequired();
    expect(within(form).queryByLabelText(/birth/i)).toBeNull();
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("checkbox", { name: /The Positive Reset/ }));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    expect(await within(form).findByText(AGE_ERROR)).toBeInTheDocument();
    await waitFor(() => expect(age).toHaveFocus());
    expect(shopApi.subscribe).not.toHaveBeenCalled();
    await user.click(age);
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(shopApi.subscribe).toHaveBeenCalledTimes(1));
    expect(shopApi.subscribe.mock.calls[0][0]).toMatchObject({
      consent: true,
      age_confirmed: true,
    });
  });

  it("registration asks for it and sends it", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    renderApp("/register", { shopApi });
    await screen.findByRole("heading", { name: "Create your account" });
    await user.type(screen.getByLabelText(/Your name/), "Ada Reader");
    await user.type(screen.getByLabelText(/^Email/), "ada@example.com");
    await user.type(screen.getByLabelText(/^Password\*?$/), "Correct-Horse-Battery-9");
    await user.type(screen.getByLabelText(/^Confirm password/), "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("checkbox", { name: /I agree/ }));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText(AGE_ERROR)).toBeInTheDocument();
    expect(shopApi.register).not.toHaveBeenCalled();
    await confirmAge(user, document.body);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(shopApi.register).toHaveBeenCalled());
    expect(shopApi.register.mock.calls[0][0]).toMatchObject({ age_confirmed: true });
  });

  it("checkout can't start until it is ticked", async () => {
    const user = userEvent.setup();
    vi.spyOn(redirectTo, "go").mockImplementation(() => {});
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    renderApp("/checkout", { shopApi });
    const pay = await screen.findByRole("button", { name: /Pay USD 15.00/ });
    await user.click(screen.getByRole("checkbox", { name: /terms of sale/ }));
    expect(pay).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: AGE }));
    expect(pay).toBeEnabled();
    await user.click(pay);
    await waitFor(() => expect(shopApi.checkout).toHaveBeenCalled());
    expect(shopApi.checkout.mock.calls[0][0]).toMatchObject({
      accept_terms: true,
      age_confirmed: true,
    });
  });
});

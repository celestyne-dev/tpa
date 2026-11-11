import { render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cartStore } from "@/commerce/cartStore";
import { usdEstimate } from "@/commerce/currency";
import { redirectTo } from "@/commerce/hooks";
import { PriceTag } from "@/components/products/PriceTag";
import { createAppStore } from "@/store";
import { fetchSite } from "@/store/slices/siteSlice";
import { createFakeAdminApi } from "@/test/adminFake";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, preloadAdminApp, preloadCommerce, renderApp } from "@/test/utils";

const CALM = "a1a1a1a1a1a1a1a1";
const RATE = { from: "KES", to: "USD", kes_per_usd: "129.50", updated_at: "2026-11-11T06:00:00Z" };

const siteWith = (shop) => ({ ...fx.site, shop: { ...fx.site.shop, ...shop } });
const apiWith = (shop) => createFakeApi({ getSite: vi.fn(async () => ({ data: siteWith(shop) })) });

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

describe("approximate US dollar amounts", () => {
  it("converts KES for display only, and only with a valid rate", () => {
    expect(usdEstimate(195000, "KES", RATE)).toBe("US$15.06");
    expect(usdEstimate(195000, "USD", RATE)).toBeNull(); // only KES amounts get an estimate
    expect(usdEstimate(195000, "KES", null)).toBeNull();
    expect(usdEstimate(195000, "KES", { kes_per_usd: "abc" })).toBeNull();
    expect(usdEstimate(195000, "KES", { kes_per_usd: "0" })).toBeNull();
    expect(usdEstimate(0, "KES", RATE)).toBeNull();
  });

  async function priceTag(shop) {
    const store = createAppStore({ api: apiWith(shop) });
    await store.dispatch(fetchSite());
    const product = { availability: "available", prices: [price()] };
    return render(
      <Provider store={store}>
        <MemoryRouter>
          <PriceTag product={product} currency="KES" />
        </MemoryRouter>
      </Provider>,
    );
  }
  const price = () => ({
    amount_minor: 195000,
    currency: "KES",
    amount: "1950.00",
    formatted: "KES 1,950.00",
  });

  it("shows the KES price with a clearly approximate USD amount", async () => {
    await priceTag({ display_currencies: ["KES"], usd_estimate: RATE });
    expect(screen.getByText("KES 1,950.00")).toBeInTheDocument();
    const estimate = document.querySelector("[data-usd-estimate]");
    expect(estimate).toHaveTextContent("≈ approximately US$15.06 (approx.)");
    // Never the KES number with a dollar sign.
    expect(document.body).not.toHaveTextContent("$1,950");
  });

  it("shows KES only without a rate", async () => {
    await priceTag({ display_currencies: ["KES"], usd_estimate: null });
    expect(screen.getByText("KES 1,950.00")).toBeInTheDocument();
    expect(document.querySelector("[data-usd-estimate]")).toBeNull();
    expect(document.body).not.toHaveTextContent("US$");
  });
});

describe("checkout in KES", () => {
  it("states the final KES charge, with the estimate beside it", async () => {
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    renderApp("/checkout", {
      api: apiWith({ display_currencies: ["KES"], usd_estimate: RATE }),
      shopApi: createFakeShopApi(),
    });
    const pay = await screen.findByRole("button", { name: /Pay KES 1,950.00/ });
    expect(pay).toBeInTheDocument();
    const payment = screen.getByRole("region", { name: /Payment/ });
    expect(payment).toHaveTextContent("You'll be charged KES 1,950.00");
    expect(payment).toHaveTextContent("US$15.06 (approx.)");
    expect(screen.getAllByText(/US dollar amounts are approximate/).length).toBeGreaterThan(0);
  });

  it("offers only account checkout when guest checkout is switched off", async () => {
    cartStore.add({ id: CALM, slug: "calm-mornings-workbook", title: "Calm" });
    const shopApi = createFakeShopApi();
    renderApp("/checkout", {
      api: apiWith({ display_currencies: ["KES"], guest_checkout: false }),
      shopApi,
    });
    expect(await screen.findByText(/Please log in or create an account to buy/)).toBeVisible();
    expect(screen.queryByRole("radio", { name: /Continue as guest/ })).toBeNull();
    expect(screen.queryByLabelText(/Email address \*/)).toBeNull();
    expect(screen.getByRole("button", { name: /Pay KES/ })).toBeDisabled();
    expect(shopApi.guestCheckout).not.toHaveBeenCalled();
  });
});

describe("Settings › Shop", () => {
  it("shows when the display exchange rate was last updated", async () => {
    const adminApi = createFakeAdminApi();
    const get = adminApi.settings.get;
    adminApi.settings.get = vi.fn(async (groups) => {
      const res = await get(groups);
      return {
        ...res,
        data: {
          groups: [
            ...res.data.groups,
            {
              name: "Shop",
              settings: [
                {
                  key: "shop.usd_rate",
                  label: "Kenyan shillings per US dollar (display only)",
                  type: "exchange_rate",
                  max_length: 12,
                  help: "Used only to show approximate USD amounts; never used to charge.",
                  value: "129.50",
                  is_default: false,
                  updated_at: "2026-11-11T06:00:00Z",
                },
              ],
            },
          ],
        },
      };
    });
    renderApp("/admin/settings", { adminApi });
    const field = await screen.findByLabelText(/Kenyan shillings per US dollar/);
    expect(field).toHaveValue("129.50");
    expect(field).toHaveAttribute("inputmode", "decimal");
    await waitFor(() => expect(screen.getByText(/Last updated/)).toBeInTheDocument());
  });
});

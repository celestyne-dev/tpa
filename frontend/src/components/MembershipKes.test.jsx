import { screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { ACTIVE_SUB, membershipShopApi, openMembershipContentApi } from "@/test/membershipFake";
import { createFakeApi, preloadCommerce, renderApp } from "@/test/utils";
import { yearlySaving } from "@/pages/MembershipPage";

beforeAll(preloadCommerce);

const CSRF = "tpa_customer_csrf";
const RATE = { from: "KES", to: "USD", kes_per_usd: "130", updated_at: "2026-11-11T06:00:00Z" };
const kes = (minor) => ({
  amount_minor: minor,
  currency: "KES",
  amount: (minor / 100).toFixed(2),
  formatted: `KES ${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
});

/** The published plan in KES (KES 650 a month, KES 6,500 a year), with a USD rate. */
function kesContentApi() {
  const open = openMembershipContentApi();
  return {
    getSite: vi.fn(async () => ({
      data: {
        ...fx.site,
        shop: { ...fx.site.shop, display_currencies: ["KES"], usd_estimate: RATE },
      },
    })),
    getMemberships: vi.fn(async () => {
      const { data } = await open.getMemberships();
      return {
        data: {
          ...data,
          plans: data.plans.map((p) => ({
            ...p,
            prices: p.prices.map((x) => ({
              ...x,
              price: kes(x.interval === "month" ? 65000 : 650000),
            })),
          })),
        },
      };
    }),
  };
}

afterEach(() => {
  document.cookie = `${CSRF}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  vi.restoreAllMocks();
});

describe("membership page in KES", () => {
  it("computes the yearly saving from the CMS prices", () => {
    expect(
      yearlySaving([
        { interval: "month", price: kes(65000) },
        { interval: "year", price: kes(650000) },
      ]),
    ).toEqual({ percent: 16.7, amount: "KES 1,300", currency: "KES" });
    expect(
      yearlySaving([
        { interval: "month", price: kes(65000) },
        { interval: "year", price: kes(780000) },
      ]),
    ).toBeNull();
  });

  it("shows KES prices, approximate USD, the saving and the billing terms", async () => {
    renderApp("/membership", { api: createFakeApi(kesContentApi()) });
    const prices = await screen.findByRole("list", { name: "Positive Circle prices" });
    expect(within(prices).getByText("KES 650.00")).toBeInTheDocument();
    expect(within(prices).getByText("KES 6,500.00")).toBeInTheDocument();
    // 65000 / 130 = 500 cents; 650000 / 130 = 5000 cents: estimates, labelled as such.
    expect(prices).toHaveTextContent("US$5.00 (approx.)");
    expect(prices).toHaveTextContent("US$50.00 (approx.)");
    expect(prices).not.toHaveTextContent("US$650");
    expect(
      within(prices).getByText("Save KES 1,300 a year (about 16.7%) compared with monthly"),
    ).toBeInTheDocument();
    expect(within(prices).getByText(/Renews automatically every month/)).toBeInTheDocument();
    const terms = screen.getByRole("region", { name: "How billing works" });
    expect(terms).toHaveTextContent("You are charged in Kenyan shillings (KES)");
    expect(terms).toHaveTextContent("M-Pesa can't be used for automatic renewals");
    expect(terms).toHaveTextContent("Cancel any time from your account");
    expect(within(terms).getByRole("link", { name: "refund policy" })).toHaveAttribute(
      "href",
      "/refund-policy",
    );
  });
});

describe("membership dashboard", () => {
  const view = (subscription) => {
    document.cookie = `${CSRF}=test-token; path=/`;
    return renderApp("/account/membership", {
      api: createFakeApi(kesContentApi()),
      shopApi: {
        ...createFakeShopApi({ customer: customerProfile() }),
        ...membershipShopApi({ subscription }),
      },
    });
  };

  it("shows the renewal date when Paystack has confirmed card renewal", async () => {
    view({
      ...ACTIVE_SUB,
      price: kes(65000),
      renewal: "automatic",
      renews_on: ACTIVE_SUB.current_period_end,
    });
    const line = await screen.findByText(/Renews automatically on/);
    expect(line).toHaveTextContent("by card for KES 650.00");
    expect(document.body).toHaveTextContent("US$5.00 (approx.)");
  });

  it("says when renewal is still being confirmed", async () => {
    view({ ...ACTIVE_SUB, price: kes(65000), renewal: "setting_up", renews_on: null });
    expect(await screen.findByText(/Paystack is confirming automatic renewal/)).toBeVisible();
    expect(screen.queryByText(/Renews automatically on/)).toBeNull();
  });

  it("explains clearly when automatic renewal couldn't be set up", async () => {
    view({
      ...ACTIVE_SUB,
      price: kes(65000),
      renewal: "unavailable",
      cancel_at_period_end: true,
      can_cancel: false,
    });
    expect(await screen.findByText("Automatic renewal couldn't be set up")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "join again with a debit or credit card" }),
    ).toHaveAttribute("href", "/membership");
    expect(screen.queryByText("Your membership is cancelled")).toBeNull();
  });
});

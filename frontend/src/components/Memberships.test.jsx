import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { plannedModules } from "@/admin/navigation";
import { redirectTo } from "@/commerce/hooks";
import { ApiError } from "@/services/apiClient";
import { createFakeAdminApi } from "@/test/adminFake";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import {
  ACTIVE_SUB,
  BILLING,
  membershipContentApi,
  membershipShopApi,
  openMembershipContentApi,
} from "@/test/membershipFake";
import { createFakeApi, preloadAdminApp, preloadCommerce, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);
beforeAll(preloadCommerce);

const CSRF = "tpa_customer_csrf";
const signIn = () => {
  document.cookie = `${CSRF}=test-token; path=/`;
};
afterEach(() => {
  document.cookie = `${CSRF}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  vi.restoreAllMocks();
});
const member = (options) => ({
  ...createFakeShopApi({ customer: customerProfile() }),
  ...membershipShopApi(options),
});

const EDITOR = "/admin/membership-plans/plan1";

describe("membership plans admin", () => {
  it("is a real Learning section for permitted roles; Analytics stays planned", async () => {
    renderApp("/admin/membership-plans");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Membership plans" }),
    ).toBeVisible();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).getByRole("link", { name: "Membership plans" })).toHaveAttribute(
      "href",
      "/admin/membership-plans",
    );
    expect(plannedModules.map((m) => m.label)).toEqual(["Analytics"]);
    const table = await screen.findByRole("table", { name: "Membership plans" });
    expect(within(table).getByRole("link", { name: /Positive Circle/ })).toHaveAttribute(
      "href",
      EDITOR,
    );
    expect(within(table).getByText("USD 9.99")).toBeInTheDocument();
    expect(screen.getByText(/only possible in Paystack test mode/)).toBeInTheDocument();
  });

  it("hides the section from roles without memberships.view and blocks the route", async () => {
    renderApp("/admin/membership-plans", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeVisible();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Membership plans" })).toBeNull();
  });

  it("creates a draft plan", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/membership-plans");
    await user.click(await screen.findByRole("button", { name: /New plan/ }));
    const dialog = await screen.findByRole("dialog", { name: "New membership plan" });
    await user.type(within(dialog).getByLabelText(/Plan name/), "Inner Circle");
    await user.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(adminApi.memberships.create).toHaveBeenCalledWith({ name: "Inner Circle" }),
    );
  });

  it("edits content with the lock version and shows validation errors", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDITOR);
    const name = await screen.findByLabelText(/^Name/);
    await user.clear(name);
    await user.click(screen.getByRole("button", { name: "Save content" }));
    expect(await screen.findByText("name: This field is required.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^Name/), "Positive Circle Plus");
    const benefits = screen.getByLabelText(/Benefits/);
    await user.type(benefits, "{enter}Member-only workbooks");
    await user.click(screen.getByRole("button", { name: "Save content" }));
    await waitFor(() =>
      expect(adminApi.memberships.update).toHaveBeenLastCalledWith("plan1", {
        name: "Positive Circle Plus",
        tagline: "Calmer days, together",
        description: "Members read every premium guide.",
        benefits: ["All premium guides", "Member-only workbooks"],
        tier_rank: 1,
        slug: "positive-circle",
        lock_version: 3,
      }),
    );
    expect(await screen.findByText("Plan saved.")).toBeInTheDocument();
  });

  it("adds prices through the server and reports invalid amounts", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDITOR);
    const yearly = await screen.findByRole("form", { name: "Yearly price" });
    await user.type(within(yearly).getByLabelText(/New yearly price/), "abc");
    await user.click(within(yearly).getByRole("button", { name: "Set price" }));
    expect(await screen.findByText("amount: Enter an amount such as 9.99.")).toBeInTheDocument();
    const input = within(yearly).getByLabelText(/New yearly price/);
    await user.clear(input);
    await user.type(input, "99.00");
    await user.click(within(yearly).getByRole("button", { name: "Set price" }));
    await waitFor(() =>
      expect(adminApi.memberships.addPrice).toHaveBeenLastCalledWith("plan1", {
        interval: "year",
        amount: "99.00",
        currency: "USD",
        lock_version: 3,
      }),
    );
    expect(
      await within(await screen.findByRole("form", { name: "Yearly price" })).findByText(
        "USD 99.00",
      ),
    ).toBeInTheDocument();
    // The monthly price can be replaced but is never edited in place.
    const monthly = screen.getByRole("form", { name: "Monthly price" });
    expect(within(monthly).getByRole("button", { name: "Replace price" })).toBeInTheDocument();
  });

  it("chooses eligible courses and resources, then publishes", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDITOR);
    const courses = await screen.findByRole("group", { name: "Courses" });
    await user.click(within(courses).getByLabelText(/Calm Foundations/));
    await user.click(screen.getByRole("button", { name: /Save included items \(2\)/ }));
    await waitFor(() =>
      expect(adminApi.memberships.setAccess).toHaveBeenCalledWith("plan1", {
        product_ids: ["p-guide", "p-course"],
        lock_version: 3,
      }),
    );
    expect(await screen.findByText("Included courses and resources saved.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() =>
      expect(adminApi.memberships.setStatus).toHaveBeenCalledWith("plan1", {
        status: "published",
        lock_version: 4,
      }),
    );
    expect(await screen.findByText("Plan published.")).toBeInTheDocument();
  });

  it("syncs prices with Paystack test plans using the lock version", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDITOR);
    const section = await screen.findByRole("region", { name: "Paystack plans (test mode)" });
    expect(within(section).getByText("No Paystack plans are linked yet.")).toBeInTheDocument();
    await user.click(within(section).getByRole("button", { name: "Sync with Paystack (test)" }));
    await waitFor(() =>
      expect(adminApi.memberships.providerSync).toHaveBeenCalledWith("plan1", { lock_version: 3 }),
    );
    const linked = await within(section).findByRole("list", { name: "Linked Paystack plans" });
    expect(within(linked).getByText("PLN_month")).toBeInTheDocument();
  });

  it("shows status errors from the server", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.memberships.setStatus.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: "validation_error",
          message: "This plan isn't ready.",
          details: { readiness: ["Add a monthly or yearly price."] },
        }),
      ),
    );
    renderApp(EDITOR, { adminApi });
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    const line = await screen.findByText("Add a monthly or yearly price.");
    expect(line.closest("[role=alert]")).toHaveFocus();
  });

  it("is read-only for view-only roles and hides publishing from managers", async () => {
    renderApp(EDITOR, { adminApi: createFakeAdminApi({ role: "customer_support" }) });
    expect(await screen.findByLabelText(/^Name/)).toBeDisabled();
    expect(screen.getByText("Your role can view this plan but not change it.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Set price" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Save included items/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sync with Paystack (test)" })).toBeNull();
  });

  it("lets product managers edit but not publish", async () => {
    renderApp(EDITOR, { adminApi: createFakeAdminApi({ role: "product_manager" }) });
    expect(await screen.findByLabelText(/^Name/)).not.toBeDisabled();
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save content" })).toBeInTheDocument();
  });
});

describe("public membership page", () => {
  it("shows CMS plans, prices, benefits and included items with billing coming soon", async () => {
    renderApp("/membership");
    expect(await screen.findByRole("heading", { level: 2, name: "Positive Circle" })).toBeVisible();
    const prices = screen.getByRole("list", { name: "Positive Circle prices" });
    expect(within(prices).getByText("USD 10.00")).toBeInTheDocument();
    expect(within(prices).getByText("USD 100.00")).toBeInTheDocument();
    expect(within(prices).getByText("Save 17% compared with monthly")).toBeInTheDocument();
    expect(screen.getByText("Member-only workbooks")).toBeInTheDocument();
    expect(screen.getByText("New resources every month.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Calm Foundations" })).toHaveAttribute(
      "href",
      "/courses/calm-foundations",
    );
    expect(screen.getByRole("link", { name: "Calm Guide" })).toHaveAttribute(
      "href",
      "/shop/calm-guide",
    );
    const join = screen.getByRole("button", { name: "Coming soon" });
    expect(join).toBeDisabled();
    expect(join).toHaveAccessibleDescription(BILLING.message);
    expect(screen.getByText("Joining opens soon")).toBeInTheDocument();
  });

  it("shows a coming-soon state when no plan is published", async () => {
    renderApp("/membership", {
      api: createFakeApi(membershipContentApi({ plans: [], billing: BILLING })),
    });
    expect(await screen.findByText("Membership is coming soon")).toBeVisible();
  });

  it("offers a retry when plans can't be loaded", async () => {
    renderApp("/membership", {
      api: createFakeApi({
        getMemberships: vi.fn(() =>
          Promise.reject(new ApiError({ status: 500, code: "http_error", message: "Down" })),
        ),
      }),
    });
    expect(await screen.findByText("We couldn't load the membership plans")).toBeVisible();
  });
});

describe("joining in test mode", () => {
  it("sends signed-out visitors to log in first", async () => {
    const user = userEvent.setup();
    renderApp("/membership", { api: createFakeApi(openMembershipContentApi()) });
    await user.click(await screen.findByRole("button", { name: "Join monthly · USD 10.00" }));
    expect(await screen.findByRole("heading", { level: 1, name: /log in/i })).toBeVisible();
  });

  it("starts checkout with the server-checked price and redirects to Paystack", async () => {
    const user = userEvent.setup();
    const go = vi.spyOn(redirectTo, "go").mockImplementation(() => {});
    signIn();
    const shopApi = member();
    renderApp("/membership", { api: createFakeApi(openMembershipContentApi()), shopApi });
    expect(screen.queryByText("Joining opens soon")).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Join yearly · USD 100.00" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("https://checkout.paystack.com/test-sub1"));
    const body = shopApi.membershipCheckout.mock.calls[0][0];
    expect(body).toMatchObject({
      price_id: "price-year",
      expected_amount_minor: 10000,
      currency: "USD",
      accept_terms: true,
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f]{32}$/);
  });

  it("explains a price change from the server", async () => {
    const user = userEvent.setup();
    signIn();
    const shopApi = member();
    shopApi.membershipCheckout.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 409,
          code: "conflict",
          message: "The price changed.",
          details: { code: "price_changed" },
        }),
      ),
    );
    renderApp("/membership", { api: createFakeApi(openMembershipContentApi()), shopApi });
    await user.click(await screen.findByRole("button", { name: "Join monthly · USD 10.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This price has just changed");
  });
});

describe("account membership page", () => {
  it("never treats the Paystack return as payment: it verifies with the server", async () => {
    signIn();
    const shopApi = member({ paidAfter: 1 });
    renderApp("/account/membership?subscription=sub1", { shopApi });
    expect(
      await screen.findByText("Payment confirmed. Welcome to the membership!"),
    ).toBeInTheDocument();
    expect(shopApi.verifyMembership).toHaveBeenCalledWith("sub1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Calm Guide" })).toBeInTheDocument();
    expect(screen.getByText(/Membership activated/)).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Account" });
    expect(within(nav).getByRole("link", { name: "Membership" })).toHaveAttribute(
      "href",
      "/account/membership",
    );
  });

  it("shows a pending membership with no access and a way back to payment", async () => {
    signIn();
    renderApp("/account/membership", { shopApi: member() });
    expect(await screen.findByText("Waiting for payment confirmation")).toBeInTheDocument();
    expect(screen.getByText(/You won't get access before then/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue to payment" })).toHaveAttribute(
      "href",
      "https://checkout.paystack.com/test-sub1",
    );
    expect(screen.queryByRole("region", { name: "Included with your membership" })).toBeNull();
  });

  it("invites non-members to see the plans", async () => {
    signIn();
    renderApp("/account/membership", { shopApi: member({ subscription: null }) });
    expect(await screen.findByText("You're not a member yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See membership plans" })).toHaveAttribute(
      "href",
      "/membership",
    );
  });

  it("cancels at period end, resumes, and opens the Paystack card page", async () => {
    const user = userEvent.setup();
    const go = vi.spyOn(redirectTo, "go").mockImplementation(() => {});
    signIn();
    const shopApi = member({ subscription: ACTIVE_SUB });
    renderApp("/account/membership", { shopApi });
    const manage = await screen.findByRole("region", { name: "Manage membership" });
    await user.click(within(manage).getByRole("button", { name: "Update payment method" }));
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith("https://paystack.com/manage/subscriptions/sub1"),
    );
    expect(shopApi.membershipPaymentMethod).toHaveBeenCalledWith("sub1");

    await user.click(within(manage).getByRole("button", { name: "Cancel membership" }));
    const confirm = screen.getByRole("group", { name: "Confirm cancellation" });
    expect(confirm).toHaveTextContent("you keep access until");
    await user.click(within(confirm).getByRole("button", { name: "Yes, cancel at period end" }));
    expect(shopApi.cancelMembership).toHaveBeenCalledWith("sub1");
    expect(await screen.findByText("Your membership is cancelled")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Resume membership" }));
    expect(shopApi.resumeMembership).toHaveBeenCalledWith("sub1");
    expect(await screen.findByRole("button", { name: "Cancel membership" })).toBeInTheDocument();
  });

  it("explains a past-due membership and shows billing history", async () => {
    signIn();
    renderApp("/account/membership", {
      shopApi: member({ subscription: { ...ACTIVE_SUB, status: "past_due" } }),
    });
    expect(await screen.findByText("Your renewal payment didn't go through")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Billing periods" })).toBeInTheDocument();
  });

  it("shows server errors from management actions", async () => {
    const user = userEvent.setup();
    signIn();
    const shopApi = member({ subscription: ACTIVE_SUB });
    shopApi.cancelMembership.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 409,
          code: "conflict",
          message: "x",
          details: { code: "subscription_not_linked" },
        }),
      ),
    );
    renderApp("/account/membership", { shopApi });
    await user.click(await screen.findByRole("button", { name: "Cancel membership" }));
    await user.click(screen.getByRole("button", { name: "Yes, cancel at period end" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("still being set up with Paystack");
  });

  it("shows the current period for active members", async () => {
    signIn();
    renderApp("/account/membership", { shopApi: member({ subscription: ACTIVE_SUB }) });
    expect(await screen.findByText(/Current period:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View your receipt in Orders" })).toBeInTheDocument();
  });
});

describe("membership operations admin", () => {
  it("lists subscribers with filters and links to the detail page", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/membership-subscriptions");
    const table = await screen.findByRole("table", { name: "Subscribers" });
    expect(within(table).getByRole("link", { name: "member@example.com" })).toHaveAttribute(
      "href",
      "/admin/membership-subscriptions/sub1",
    );
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).getByRole("link", { name: "Membership subscribers" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Membership reports" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Show"), "payment_problem");
    await waitFor(() =>
      expect(adminApi.memberships.subscriptions).toHaveBeenLastCalledWith({
        flag: "payment_problem",
        page: 1,
      }),
    );
  });

  it("cancels with a reason and the lock version, and reconciles with Paystack", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/membership-subscriptions/sub1");
    expect(
      await screen.findByRole("heading", { level: 1, name: "member@example.com" }),
    ).toBeVisible();
    expect(screen.getByText("R-1001", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Refunds need the refund permission/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reconcile with Paystack" }));
    await waitFor(() =>
      expect(adminApi.memberships.reconcile).toHaveBeenCalledWith("sub1", { lock_version: 4 }),
    );
    expect(await screen.findByText(/No changes were needed/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel membership" }));
    const dialog = await screen.findByRole("dialog", { name: "Cancel membership" });
    const submit = within(dialog).getByRole("button", { name: "Cancel membership" });
    expect(submit).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Reason/), "Asked by phone");
    await user.click(submit);
    await waitFor(() =>
      expect(adminApi.memberships.cancelSubscription).toHaveBeenCalledWith("sub1", {
        lock_version: 5,
        reason: "Asked by phone",
        immediate: false,
      }),
    );
  });

  it("keeps view-only and unrelated roles away from subscriber actions", async () => {
    renderApp("/admin/membership-reports", {
      adminApi: createFakeAdminApi({ role: "product_manager" }),
    });
    expect(await screen.findByText("You don't have access to this area")).toBeVisible();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Membership subscribers" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "Membership reports" })).toBeNull();
  });

  it("shows reports from verified records with honest empty trends", async () => {
    renderApp("/admin/membership-reports", {
      adminApi: createFakeAdminApi({ role: "finance_manager" }),
    });
    expect(await screen.findByText("Paid subscribers")).toBeInTheDocument();
    expect(screen.getByText("2 monthly · 1 yearly")).toBeInTheDocument();
    expect(screen.getByText("USD 29.97")).toBeInTheDocument();
    expect(screen.getByText("USD 26.97")).toBeInTheDocument();
    expect(screen.getAllByText("test mode").length).toBeGreaterThan(0);
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
  });

  it("grants and revokes complimentary memberships with reasons", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "prompt").mockReturnValue("Ended early");
    const { adminApi } = renderApp("/admin/membership-grants");
    const table = await screen.findByRole("table", { name: "Complimentary memberships" });
    expect(within(table).getByText("Podcast guest")).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(adminApi.memberships.revokeGrant).toHaveBeenCalledWith("g1", {
        reason: "Ended early",
      }),
    );
  });

  it("shows billing status, grace period and links on the plans page", async () => {
    renderApp("/admin/membership-plans");
    const billing = await screen.findByRole("region", { name: "Membership billing" });
    expect(within(billing).getByText("3 days")).toBeInTheDocument();
    expect(within(billing).getByRole("link", { name: "Subscribers" })).toBeInTheDocument();
    expect(within(billing).getByRole("link", { name: "Reports" })).toBeInTheDocument();
  });
});

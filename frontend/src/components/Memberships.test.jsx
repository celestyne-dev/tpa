import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { plannedModules } from "@/admin/navigation";
import { ApiError } from "@/services/apiClient";
import { createFakeAdminApi } from "@/test/adminFake";
import { BILLING, membershipContentApi } from "@/test/membershipFake";
import { createFakeApi, preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

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
    expect(screen.getByText(/Subscription billing isn't open yet/)).toBeInTheDocument();
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

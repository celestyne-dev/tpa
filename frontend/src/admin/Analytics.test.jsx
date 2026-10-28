import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { beacon, shouldTrack, trackPageView } from "@/analytics/pageViews";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);
afterEach(() => vi.restoreAllMocks());

/** Overview is the default tab (Batch 11.5): open a module tab first. */
async function openTab(name) {
  await userEvent.setup().click(await screen.findByRole("tab", { name }));
}

describe("analytics dashboard", () => {
  it("shows real report data with honest visitor and session notes", async () => {
    const { adminApi } = renderApp("/admin/analytics");
    await openTab("Website");
    expect(await screen.findByRole("heading", { level: 1, name: "Analytics" })).toBeVisible();
    const overview = await screen.findByRole("region", { name: "Traffic overview" });
    expect(within(overview).getByText("1,234")).toBeInTheDocument();
    expect(within(overview).getByText("Daily visitors (sum)")).toBeInTheDocument();
    const articles = screen.getByRole("region", { name: "Popular articles" });
    expect(within(articles).getByText("Calm mornings")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Top content categories" })).toHaveTextContent(
      "Positive Mindset",
    );
    expect(screen.getByRole("region", { name: "Traffic sources" })).toHaveTextContent(
      "Search engines",
    );
    expect(screen.getByRole("region", { name: "Campaign performance" })).toHaveTextContent(
      "newsletter / email",
    );
    expect(screen.getByText(/Not measured: without cookies/)).toBeInTheDocument();
    expect(adminApi.traffic).toHaveBeenCalledWith({ range: "30d" });
  });

  it("filters by preset, custom dates and grouping, with an empty state", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await openTab("Website");
    await screen.findByRole("region", { name: "Traffic overview" });
    await user.selectOptions(screen.getByLabelText("Date range"), "7d");
    await waitFor(() => expect(adminApi.traffic).toHaveBeenLastCalledWith({ range: "7d" }));
    await user.selectOptions(screen.getByLabelText("Group by"), "week");
    await waitFor(() =>
      expect(adminApi.traffic).toHaveBeenLastCalledWith({ range: "7d", granularity: "week" }),
    );
    await user.selectOptions(screen.getByLabelText("Date range"), "custom");
    await user.type(screen.getByLabelText("From"), "2020-01-01");
    expect(await screen.findByText("No page views in this period")).toBeInTheDocument();
  });

  it("is only available with analytics.view", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "customer_support" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeVisible();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Analytics" })).toBeNull();
  });
});

describe("commerce analytics", () => {
  it("shows per-currency KPIs, products and limits for finance roles", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "finance_manager" }) });
    await openTab("Commerce");
    // Finance has no analytics.view: Commerce first (Membership is the other tab).
    const kes = await screen.findByRole("region", { name: "Sales in KES" });
    expect(within(kes).getByText("KES 15.00")).toBeInTheDocument(); // net, never mixed with USD
    const usd = screen.getByRole("region", { name: "Sales in USD" });
    expect(within(usd).getByText("USD 42.00")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Website" })).toBeNull();
    expect(screen.getByRole("region", { name: "Best-selling products" })).toHaveTextContent(
      "Calm Guide",
    );
    expect(screen.getByRole("region", { name: "Products with no sales" })).toHaveTextContent(
      "Never Sold Pack",
    );
    expect(screen.getByText(/Purchase conversion rate: unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
      "href",
      "/api/v1/admin/analytics/commerce/export?range=30d&mode=live",
    );
  });

  it("switches tabs and filters by payment mode with an empty state", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await user.click(await screen.findByRole("tab", { name: "Commerce" }));
    await screen.findByRole("region", { name: "Sales in USD" });
    await user.selectOptions(screen.getByLabelText("Payment mode"), "test");
    await waitFor(() =>
      expect(adminApi.commerceAnalytics).toHaveBeenLastCalledWith({ range: "30d", mode: "test" }),
    );
    expect(await screen.findByText("No sales or orders in this period")).toBeInTheDocument();
  });

  it("hides commerce from analytics-only roles", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    await openTab("Website");
    await screen.findByRole("region", { name: "Traffic overview" });
    expect(screen.queryByRole("tab", { name: "Commerce" })).toBeNull();
  });
});

describe("learning analytics", () => {
  it("shows learning KPIs, courses, assessments and grading for permitted staff", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await user.click(await screen.findByRole("tab", { name: "Learning" }));
    const overview = await screen.findByRole("region", { name: "Learning overview" });
    expect(within(overview).getByText("4 / 2")).toBeInTheDocument();
    expect(within(overview).getByText("40%")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Course performance" })).toHaveTextContent(
      "Calm Foundations",
    );
    expect(screen.getByRole("region", { name: "Assessment performance" })).toHaveTextContent(
      "Timed assessments",
    );
    expect(screen.getByRole("region", { name: "Assignments and grading" })).toHaveTextContent(
      "Waiting for grading now",
    );
    expect(screen.getByText(/Choose a course to see lesson progress/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Course"), "5");
    await waitFor(() =>
      expect(adminApi.learningAnalytics).toHaveBeenLastCalledWith({ range: "30d", course: "5" }),
    );
    const lessons = await screen.findByRole("region", { name: "Lesson progress" });
    expect(within(lessons).getByText("Lesson 2")).toBeInTheDocument();
    // Website and Commerce tabs are still there.
    expect(screen.getByRole("tab", { name: "Website" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Commerce" })).toBeInTheDocument();
  });

  it("filters by date with an empty state", async () => {
    const user = userEvent.setup();
    renderApp("/admin/analytics");
    await user.click(await screen.findByRole("tab", { name: "Learning" }));
    await screen.findByRole("region", { name: "Learning overview" });
    await user.selectOptions(screen.getByLabelText("Time period"), "custom");
    await user.type(screen.getByLabelText("First day"), "2020-01-01");
    expect(await screen.findByText("No enrollments yet")).toBeInTheDocument();
  });

  it("is hidden without the course reports permission", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "finance_manager" }) });
    await openTab("Commerce");
    await screen.findByRole("region", { name: "Sales in USD" });
    expect(screen.queryByRole("tab", { name: "Learning" })).toBeNull();
  });
});

describe("membership and audience analytics", () => {
  it("shows membership KPIs with realised revenue separate from MRR estimates", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await user.click(await screen.findByRole("tab", { name: "Membership" }));
    const overview = await screen.findByRole("region", { name: "Membership overview" });
    expect(within(overview).getByText("Not counted as paid")).toBeInTheDocument();
    expect(within(overview).getByText("USD 19.98")).toBeInTheDocument(); // MRR estimate
    expect(screen.getByRole("region", { name: "Realised membership revenue" })).toHaveTextContent(
      "USD 26.97",
    );
    expect(screen.getByRole("region", { name: "Recurring revenue estimate" })).toHaveTextContent(
      "USD 239.76",
    );
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Plan"), "plan1");
    await waitFor(() =>
      expect(adminApi.membershipAnalytics).toHaveBeenLastCalledWith({
        range: "90d",
        plan: "plan1",
      }),
    );
  });

  it("shows audience growth and campaigns without inventing opens or clicks", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await user.click(await screen.findByRole("tab", { name: "Audience" }));
    const overview = await screen.findByRole("region", { name: "Audience overview" });
    expect(within(overview).getByText("120")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Campaigns" })).toHaveTextContent("October letter");
    expect(screen.getByRole("region", { name: "Lead magnets" })).toHaveTextContent("Calm Kit");
    expect(screen.getByText(/Opens and clicks: not measured/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Campaign"), "camp1");
    await waitFor(() =>
      expect(adminApi.audienceAnalytics).toHaveBeenLastCalledWith({
        range: "30d",
        campaign: "camp1",
      }),
    );
    await user.selectOptions(screen.getByLabelText("Audience period"), "custom");
    await user.type(screen.getByLabelText("Audience from"), "2020-01-01");
    expect(await screen.findByText("No newsletter contacts yet")).toBeInTheDocument();
  });

  it("shows each tab only with its permission", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "finance_manager" }) });
    expect(await screen.findByRole("tab", { name: "Membership" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Audience" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Learning" })).toBeNull();
  });
});

describe("unified overview", () => {
  it("is the default tab with period comparisons, point-in-time labels and exports", async () => {
    const { adminApi } = renderApp("/admin/analytics");
    const website = await screen.findByRole("region", { name: "Website" });
    expect(within(website).getByText("1,234")).toBeInTheDocument();
    expect(website).toHaveTextContent("50.1% increase vs previous period"); // 1,234 vs 822
    const commerce = screen.getByRole("region", { name: "Commerce (live payments)" });
    expect(within(commerce).getByText("Verified revenue (USD)")).toBeInTheDocument();
    expect(within(commerce).getByText("Verified revenue (KES)")).toBeInTheDocument(); // separate
    expect(within(commerce).getByText("Test-mode payments")).toBeInTheDocument();
    const membership = screen.getByRole("region", { name: "Membership" });
    expect(within(membership).getAllByText("Right now").length).toBeGreaterThan(0);
    expect(within(membership).getByText("Estimate, not revenue")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Analytics health" })).toHaveTextContent(
      "Days waiting for rollup",
    );
    const exportsBar = screen.getByRole("region", { name: "Exports" });
    expect(within(exportsBar).getByRole("link", { name: "Overview" })).toHaveAttribute(
      "href",
      "/api/v1/admin/analytics/export?report=overview&range=30d",
    );
    expect(adminApi.analyticsOverview).toHaveBeenCalledWith({ range: "30d" });
  });

  it("uses the shared date presets and the sales mode filter", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/analytics");
    await screen.findByRole("region", { name: "Website" });
    const period = screen.getByLabelText("Overview period");
    expect(
      within(period)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Last 7 days", "Last 30 days", "Last 90 days", "Last 365 days", "Custom range"]);
    await user.selectOptions(period, "7d");
    await user.selectOptions(screen.getByLabelText("Sales mode"), "test");
    await waitFor(() =>
      expect(adminApi.analyticsOverview).toHaveBeenLastCalledWith({ range: "7d", mode: "test" }),
    );
  });

  it("only shows the sections a role may see", async () => {
    renderApp("/admin/analytics", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    await screen.findByRole("region", { name: "Website" });
    expect(screen.queryByRole("region", { name: /Commerce/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "Membership" })).toBeNull(); // no finance.export
  });
});

describe("page-view beacon", () => {
  it("sends path, UTM search and referrer on first load, nothing private", () => {
    const send = vi.spyOn(beacon, "send").mockReturnValue(true);
    trackPageView({ pathname: "/articles/calm", search: "?utm_source=x", spa: false });
    const [url, body] = send.mock.calls[0];
    expect(url).toBe("/api/v1/analytics/collect");
    expect(JSON.parse(body)).toMatchObject({
      path: "/articles/calm",
      search: "?utm_source=x",
      spa: false,
    });
    trackPageView({ pathname: "/topics/x", search: "?utm_source=x", spa: true });
    expect(JSON.parse(send.mock.calls[1][1])).toMatchObject({
      search: "",
      referrer: "",
      spa: true,
    });
    expect(trackPageView({ pathname: "/account/orders", search: "", spa: true })).toBe(false);
    expect(shouldTrack("/admin/articles")).toBe(false);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("respects Global Privacy Control and automated browsers", () => {
    const send = vi.spyOn(beacon, "send").mockReturnValue(true);
    Object.defineProperty(navigator, "globalPrivacyControl", { value: true, configurable: true });
    expect(trackPageView({ pathname: "/", search: "", spa: false })).toBe(false);
    delete navigator.globalPrivacyControl;
    Object.defineProperty(navigator, "webdriver", { value: true, configurable: true });
    expect(trackPageView({ pathname: "/", search: "", spa: false })).toBe(false);
    delete navigator.webdriver;
    expect(send).not.toHaveBeenCalled();
  });
});

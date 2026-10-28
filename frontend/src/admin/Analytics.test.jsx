import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { beacon, shouldTrack, trackPageView } from "@/analytics/pageViews";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);
afterEach(() => vi.restoreAllMocks());

describe("analytics dashboard", () => {
  it("shows real report data with honest visitor and session notes", async () => {
    const { adminApi } = renderApp("/admin/analytics");
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

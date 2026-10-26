import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import { createFakeAdminApi, makeArticle, manualSave } from "@/test/adminFake";
import { SLOW_EDITOR_TEST_MS, preloadAdminApp, renderApp } from "@/test/utils";
import { safeNextPath } from "./components/safeNextPath";

beforeAll(preloadAdminApp);

describe("admin authentication", () => {
  it("redirects anonymous visitors to the login page and back after signing in", async () => {
    const user = userEvent.setup();
    renderApp("/admin/articles", { adminApi: createFakeAdminApi({ role: null }) });
    expect(await screen.findByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Email/), "editor@example.org");
    await user.type(screen.getByLabelText(/Password/), "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Articles" })).toBeInTheDocument();
  });

  it("shows a generic error for invalid credentials", async () => {
    const user = userEvent.setup();
    renderApp("/admin/login", { adminApi: createFakeAdminApi({ role: null }) });
    await user.type(await screen.findByLabelText(/Email/), "editor@example.org");
    await user.type(screen.getByLabelText(/Password/), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByLabelText(/Password/)).toHaveValue("");
  });

  it("shows a loading state while the session is checked", async () => {
    const adminApi = createFakeAdminApi();
    let resolve;
    adminApi.auth.me = vi.fn(() => new Promise((r) => (resolve = r)));
    renderApp("/admin", { adminApi });
    expect(
      await screen.findByRole("status", { name: "Checking your session" }),
    ).toBeInTheDocument();
    resolve({
      data: {
        user: {
          id: 1,
          email: "a@b.c",
          display_name: "A",
          roles: ["analyst"],
          permissions: ["dashboard.view"],
        },
      },
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("only accepts internal admin paths as the post-login destination", () => {
    expect(safeNextPath("/admin/articles?page=2")).toBe("/admin/articles?page=2");
    expect(safeNextPath("https://evil.example")).toBe("/admin");
    expect(safeNextPath("//evil.example/admin")).toBe("/admin");
    expect(safeNextPath("/articles")).toBe("/admin");
    expect(safeNextPath("/admin/login")).toBe("/admin");
    expect(safeNextPath(null)).toBe("/admin");
  });

  it("signs out and returns to the login page", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(adminApi.auth.logout).toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();
  });

  it("returns to login when the session expires", async () => {
    const { store } = renderApp("/admin");
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    act(() => {
      store.dispatch({ type: "auth/sessionExpired" });
    });
    expect(await screen.findByText("Your session has ended")).toBeInTheDocument();
  });
});

describe("dashboard and role-aware navigation", () => {
  it("renders real totals and the audit feed for super admins", async () => {
    renderApp("/admin");
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    const totals = screen.getByRole("region", { name: "Content totals" });
    expect(within(totals).getByText("6")).toBeInTheDocument();
    expect(within(totals).getByText("8")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent admin activity" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).getByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("hides administration links from analysts and blocks direct access", async () => {
    renderApp("/admin/settings", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Articles" })).toBeInTheDocument();
  });

  it("lists planned modules without links", async () => {
    const user = userEvent.setup();
    renderApp("/admin");
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    await user.click(within(nav).getByRole("button", { name: "Planned modules" }));
    const planned = within(nav).getByRole("list", { name: /Planned modules/ });
    expect(within(planned).getByText("Courses")).toBeInTheDocument();
    // The newsletter shipped in Batch 06: it is a real section now.
    expect(within(planned).queryByText("Newsletter")).not.toBeInTheDocument();
    // Commerce shipped in Batch 05: it is a real section now, not a planned module.
    expect(within(planned).queryByText("Digital products")).not.toBeInTheDocument();
    expect(within(planned).queryAllByRole("link")).toHaveLength(0);
  });

  it("shows an error state when the dashboard API fails", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.dashboard = vi.fn(() =>
      Promise.reject(new ApiError({ status: 500, message: "boom" })),
    );
    renderApp("/admin", { adminApi });
    expect(await screen.findByText("We couldn't load the dashboard")).toBeInTheDocument();
  });
});

describe("articles", () => {
  it("lists articles and filters by status", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/articles");
    expect(await screen.findByRole("link", { name: "Finding Calm" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quiet Confidence" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "published");
    await waitFor(() =>
      expect(adminApi.articles.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "published" }),
      ),
    );
    expect(await screen.findByRole("link", { name: "Quiet Confidence" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Finding Calm" })).not.toBeInTheDocument();
  });

  it(
    "edits a draft with the block editor and saves structured content",
    async () => {
      const user = userEvent.setup();
      const { adminApi } = renderApp("/admin/articles/7/edit");
      const title = await screen.findByLabelText(/^Title/);
      // Pasted, not typed key by key: the test checks the saved structure, and per-key
      // re-renders of the full editor made it CPU-bound on slower machines.
      await user.clear(title);
      await user.paste("Finding Calm Today");
      await user.click(screen.getByRole("button", { name: "Callout" }));
      await user.click(screen.getByLabelText("Callout text"));
      await user.paste("Breathe slowly.");
      await user.click(screen.getByRole("button", { name: "Divider" }));
      await user.click(screen.getByRole("button", { name: "Save changes" }));
      await waitFor(() => expect(manualSave(adminApi.articles.update)).toBeDefined());
      const [, payload] = manualSave(adminApi.articles.update);
      expect(payload.title).toBe("Finding Calm Today");
      expect(payload.body).toEqual([
        { type: "paragraph", text: "Hello world." },
        { type: "callout", tone: "info", text: "Breathe slowly." },
        { type: "divider" },
      ]);
      expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
    },
    SLOW_EDITOR_TEST_MS,
  );

  it("offers publishing controls to editors and publishes the article", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/articles/7/edit", {
      adminApi: createFakeAdminApi({ role: "editor" }),
    });
    await user.click(await screen.findByRole("button", { name: "Publish now" }));
    await waitFor(() => expect(adminApi.articles.publish).toHaveBeenCalledWith("7", null));
    expect(await screen.findByText(/site rebuild has been queued/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unpublish" })).toBeInTheDocument();
  });

  it("gives moderators take-down controls but not publishing or editing", async () => {
    const adminApi = createFakeAdminApi({
      role: "moderator",
      article: makeArticle({ status: "published", is_public: true }),
    });
    renderApp("/admin/articles/7/edit", { adminApi });
    expect(await screen.findByRole("button", { name: "Unpublish" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.getByText("You have read-only access to this article.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Title/)).toBeDisabled();
  });

  it("shows server validation messages next to fields", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.articles.update = vi.fn(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: "validation_error",
          message: "One or more parameters are invalid.",
          details: { title: ["HTML is not allowed. Use plain text."] },
        }),
      ),
    );
    renderApp("/admin/articles/7/edit", { adminApi });
    const title = await screen.findByLabelText(/^Title/);
    await user.type(title, " <b>");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("HTML is not allowed. Use plain text.")).toBeInTheDocument();
  });
});

describe("settings", () => {
  it("edits and saves only changed settings", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/settings");
    const email = await screen.findByLabelText("Contact email");
    await user.type(email, "hello@example.org");
    await user.click(screen.getByRole("button", { name: "Save and publish" }));
    await waitFor(() =>
      expect(adminApi.settings.save).toHaveBeenCalledWith(
        { "contact.email": "hello@example.org" },
        null,
      ),
    );
    expect(await screen.findByText(/website updates after the queued rebuild/)).toBeInTheDocument();
  });
});

describe("public site is unaffected", () => {
  it("still renders the public homepage alongside the admin routes", async () => {
    renderApp("/");
    expect(
      await screen.findByRole("heading", { level: 1, name: /A Better Mindset/ }),
    ).toBeInTheDocument();
    // Let the homepage's API-driven sections finish loading inside the test.
    const topics = await screen.findByRole("region", { name: "Explore What Matters to You" });
    expect(within(topics).getByRole("link", { name: "Positive Mindset" })).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "How to Reframe a Negative Thought" }),
    ).toBeInTheDocument();
    expect((await screen.findAllByText("Know Your Worth")).length).toBeGreaterThan(0);
  });
});

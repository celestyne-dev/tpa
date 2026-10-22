import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createFakeAdminApi, makeArticle, ROLE_PERMS } from "@/test/adminFake";
import { renderApp } from "@/test/utils";

describe("roles & permissions navigation", () => {
  it("lists Roles & Permissions under Administration for super admins only", async () => {
    const { unmount } = renderApp("/admin");
    const nav = await screen.findByRole("navigation", { name: /admin/i });
    expect(within(nav).getByRole("link", { name: "Roles & Permissions" })).toHaveAttribute(
      "href",
      "/admin/roles",
    );
    unmount();
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(screen.queryByRole("link", { name: "Roles & Permissions" })).not.toBeInTheDocument();
  });

  it("blocks direct access for roles without permission", async () => {
    renderApp("/admin/roles/new", { adminApi: createFakeAdminApi({ role: "editor" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });
});

describe("roles list", () => {
  it("shows types, user counts and inactive roles, with a New role action", async () => {
    renderApp("/admin/roles");
    const table = await screen.findByRole("table", { name: "Roles" });
    const writer = within(table).getByRole("link", { name: "Content Writer" }).closest("tr");
    expect(within(writer).getByText("Template")).toBeInTheDocument();
    const old = within(table).getByRole("link", { name: "Old Reviewers" }).closest("tr");
    expect(within(old).getByText("inactive")).toBeInTheDocument();
    const superRow = within(table).getByRole("link", { name: "Super Admin" }).closest("tr");
    expect(within(superRow).getByText("All")).toBeInTheDocument();
    expect(within(superRow).getByText("Built-in")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New role" })).toBeInTheDocument();
  });

  it("is read-only for administrators who can view users but not manage roles", async () => {
    renderApp("/admin/roles", { adminApi: createFakeAdminApi({ role: "administrator" }) });
    expect(await screen.findByText(/Only a super administrator can change them/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "New role" })).not.toBeInTheDocument();
  });
});

describe("role editor", () => {
  it("creates a role from grouped checkboxes and locks sensitive or unavailable permissions", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/roles/new");
    await user.type(await screen.findByLabelText(/Role name/), "Guest Reviewer");

    const products = screen.getByRole("group", { name: "Digital products" });
    expect(within(products).getByRole("checkbox", { name: /View products/ })).toBeDisabled();
    expect(within(products).getByText("Module not available yet")).toBeInTheDocument();
    const admin = screen.getByRole("group", { name: "Users, roles & audit" });
    expect(within(admin).getByRole("checkbox", { name: /Manage roles/ })).toBeDisabled();
    expect(within(admin).getByText("Super Admin only")).toBeInTheDocument();

    const articles = screen.getByRole("group", { name: "Articles" });
    await user.click(within(articles).getByRole("checkbox", { name: /View all articles/ }));
    await user.click(within(articles).getByRole("checkbox", { name: /Edit own drafts/ }));
    const summary = screen.getByRole("region", { name: /Effective permissions/ });
    expect(within(summary).getByText("2 permissions")).toBeInTheDocument();
    expect(within(summary).getByText("Edit own drafts")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create role" }));
    await waitFor(() =>
      expect(adminApi.roles.create).toHaveBeenCalledWith({
        label: "Guest Reviewer",
        description: "",
        permissions: ["articles.edit_own", "articles.view"],
      }),
    );
  });

  it("selects every assignable permission in a group at once", async () => {
    const user = userEvent.setup();
    renderApp("/admin/roles/new");
    const articles = await screen.findByRole("group", { name: "Articles" });
    await user.click(within(articles).getByRole("button", { name: "Select all available" }));
    expect(
      within(screen.getByRole("region", { name: /Effective permissions/ })).getByText(
        "5 permissions",
      ),
    ).toBeInTheDocument();
  });

  it("shows built-in roles as protected and read-only", async () => {
    renderApp("/admin/roles/2");
    expect(await screen.findByText(/Built-in role. It is protected/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Role name/)).toBeDisabled();
    for (const box of within(screen.getByRole("group", { name: "Articles" })).getAllByRole(
      "checkbox",
    ))
      expect(box).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete role" })).not.toBeInTheDocument();
  });

  it("marks permissions planned for a future-module template", async () => {
    renderApp("/admin/roles/6");
    expect(await screen.findByText("Planned for this template")).toBeInTheDocument();
    expect(screen.getByText("Unlocks when its module ships")).toBeInTheDocument();
  });

  it("deactivates a custom role and allows deleting roles nobody holds", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/roles/5");
    await user.click(await screen.findByRole("checkbox", { name: /Active/ }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(adminApi.roles.update).toHaveBeenCalledWith(
        "5",
        expect.objectContaining({ is_active: false }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Delete role" }));
    const dialog = await screen.findByRole("dialog", { name: /Delete the Content Writer role/ });
    await user.click(within(dialog).getByRole("button", { name: "Delete role" }));
    await waitFor(() => expect(adminApi.roles.remove).toHaveBeenCalledWith("5"));
  });
});

describe("assigning multiple roles", () => {
  it("previews effective permissions while choosing roles", async () => {
    const user = userEvent.setup();
    renderApp("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Edit Ngozi Writer" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit administrator" });
    const preview = within(dialog).getByTestId("effective-preview");
    const editorCount = ROLE_PERMS.editor.length;
    expect(preview).toHaveTextContent(`Effective permissions: ${editorCount}`);
    await user.click(within(dialog).getByRole("checkbox", { name: /Analyst/ }));
    // Analyst adds analytics.view (its other permissions overlap with Editor's).
    expect(preview).toHaveTextContent(`Effective permissions: ${editorCount + 1}`);
    await user.click(within(dialog).getByRole("checkbox", { name: /Super Admin/ }));
    expect(preview).toHaveTextContent("all permissions (Super Admin)");
    // Inactive roles cannot be newly assigned, so they are not offered.
    expect(within(dialog).queryByRole("checkbox", { name: /Old Reviewers/ })).toBeNull();
    expect(within(dialog).getByText("Role templates")).toBeInTheDocument();
  });

  it("hides account creation and role changes from users without roles.assign", async () => {
    const user = userEvent.setup();
    renderApp("/admin/users", { adminApi: createFakeAdminApi({ role: "administrator" }) });
    await screen.findByRole("table", { name: "Administrators" });
    expect(screen.queryByRole("button", { name: "Invite user" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Ngozi Writer" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit administrator" });
    expect(within(dialog).queryByRole("group", { name: "Roles" })).not.toBeInTheDocument();
  });

  it("is view-only for users without users.manage", async () => {
    const adminApi = createFakeAdminApi({ role: "analyst" });
    adminApi.auth.me.mockResolvedValue({
      data: {
        user: {
          id: 5,
          email: "viewer@example.org",
          display_name: "Viewer",
          roles: ["viewer"],
          permissions: ["users.view"],
        },
      },
    });
    renderApp("/admin/users", { adminApi });
    await screen.findByRole("table", { name: "Administrators" });
    expect(screen.getByRole("button", { name: "View details for Ngozi Writer" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Edit Ngozi Writer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Disable/ })).not.toBeInTheDocument();
  });
});

describe("article ownership and review", () => {
  it("lets writers submit their own draft for review but not publish it", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({
      role: "content_writer",
      article: makeArticle({ created_by: { id: 1, display_name: "Test writer" } }),
    });
    renderApp("/admin/articles/7/edit", { adminApi });
    const submit = await screen.findByRole("button", { name: "Submit for review" });
    expect(screen.queryByRole("button", { name: "Publish now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Title/)).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(adminApi.articles.submit).toHaveBeenCalledWith("7"));
    // Already submitted: the action disappears and the review state is shown.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Submit for review" })).not.toBeInTheDocument(),
    );
    expect(screen.getAllByText(/Submitted for review/).length).toBeGreaterThan(0);
  });

  it("makes other people's articles read-only for edit-own users", async () => {
    const adminApi = createFakeAdminApi({
      role: "content_writer",
      article: makeArticle({ created_by: { id: 99, display_name: "Someone else" } }),
    });
    renderApp("/admin/articles/7/edit", { adminApi });
    expect(
      await screen.findByText("You can only edit your own articles while they are drafts."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Title/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("lets editors approve submitted articles", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({
      role: "editor",
      article: makeArticle({ review_status: "submitted", submitted_at: "2026-10-21T09:00:00Z" }),
    });
    renderApp("/admin/articles/7/edit", { adminApi });
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(adminApi.articles.approve).toHaveBeenCalledWith("7"));
    expect(await screen.findByText(/^Approved/)).toBeInTheDocument();
  });

  it("deletes a never-published draft after confirmation", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/articles/7/edit");
    await user.click(await screen.findByRole("button", { name: "Delete permanently" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this article permanently?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete article" }));
    await waitFor(() => expect(adminApi.articles.remove).toHaveBeenCalledWith("7"));
    expect(await screen.findByRole("heading", { level: 1, name: "Articles" })).toBeInTheDocument();
  });
});

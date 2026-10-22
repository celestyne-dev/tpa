import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import { createFakeAdminApi, VALID_TOKEN } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const PASSWORD = "Correct-Horse-Battery-9";

async function signIn(user) {
  await user.type(await screen.findByLabelText(/Email/), "editor@example.org");
  await user.type(screen.getByLabelText(/Password/), PASSWORD);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("direct /admin access", () => {
  it("opens the dashboard directly for an authenticated session (e.g. after a reload)", async () => {
    const { adminApi } = renderApp("/admin");
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(adminApi.auth.me).toHaveBeenCalledTimes(1);
  });

  it("sends anonymous visitors to the login page and back to /admin", async () => {
    const user = userEvent.setup();
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: null }) });
    expect(await screen.findByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();
    await signIn(user);
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows access denied when the requested page is not permitted after login", async () => {
    const user = userEvent.setup();
    renderApp("/admin/users", { adminApi: createFakeAdminApi({ role: null }) });
    await signIn(user); // the fake signs in as an editor
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });

  it("ignores external return URLs", async () => {
    const user = userEvent.setup();
    renderApp("/admin/login?next=https%3A%2F%2Fevil.example%2Fadmin", {
      adminApi: createFakeAdminApi({ role: null }),
    });
    await signIn(user);
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("lands roles without dashboard access on their first permitted area", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "pages_only" }) });
    expect(await screen.findByRole("heading", { level: 1, name: "Pages" })).toBeInTheDocument();
  });
});

describe("users and invitations", () => {
  it("lists administrators with role indicators and status, and filters", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/users");
    const table = await screen.findByRole("table", { name: "Administrators" });
    expect(within(table).getByText("Ngozi Writer")).toBeInTheDocument();
    expect(within(table).getByText("Super Admin")).toBeInTheDocument();
    expect(within(table).getByText("disabled")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Account status"), "disabled");
    await waitFor(() =>
      expect(adminApi.users.list).toHaveBeenLastCalledWith({ status: "disabled" }),
    );
    expect(await screen.findByText("Old Analyst")).toBeInTheDocument();
    expect(screen.queryByText("Ngozi Writer")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Account status"), "");
    await user.type(screen.getByLabelText("Search users"), "ngozi");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(adminApi.users.list).toHaveBeenLastCalledWith({ q: "ngozi" }));
  });

  it("invites a user and explains how the link was delivered", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Invite user" }));
    const dialog = screen.getByRole("dialog", { name: "Invite administrator" });
    await user.type(within(dialog).getByLabelText(/Email/), "new@example.org");
    await user.click(within(dialog).getByLabelText(/Moderator/));
    await user.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    await waitFor(() =>
      expect(adminApi.invitations.create).toHaveBeenCalledWith({
        email: "new@example.org",
        display_name: "",
        roles: ["editor", "moderator"],
      }),
    );
    expect(
      await screen.findByText(/link was written to the Flask server terminal/),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Invitations" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("shows server errors such as unconfigured email", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.invitations.create = vi.fn(() =>
      Promise.reject(
        new ApiError({
          status: 503,
          code: "email_not_configured",
          message: "Email delivery is not configured.",
        }),
      ),
    );
    renderApp("/admin/users", { adminApi });
    await user.click(await screen.findByRole("button", { name: "Invite user" }));
    const dialog = screen.getByRole("dialog", { name: "Invite administrator" });
    await user.type(within(dialog).getByLabelText(/Email/), "new@example.org");
    await user.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Email delivery is not configured.",
    );
  });

  it("creates a user with an initial password and validation messages", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.users.create = vi.fn(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: "validation_error",
          message: "Invalid",
          details: { password: ["Use at least 12 characters."] },
        }),
      ),
    );
    renderApp("/admin/users", { adminApi });
    await user.click(await screen.findByRole("button", { name: "Create user" }));
    const dialog = screen.getByRole("dialog", { name: "Create administrator" });
    await user.type(within(dialog).getByLabelText(/Email/), "a@example.org");
    await user.type(within(dialog).getByLabelText(/Display name/), "A");
    await user.type(within(dialog).getByLabelText(/Initial password/), "short");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("Use at least 12 characters.")).toBeInTheDocument();
  });

  it("confirms before disabling an account", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Disable Ngozi Writer" }));
    const confirm = screen.getByRole("dialog", { name: "Disable Ngozi Writer?" });
    await user.click(within(confirm).getByRole("button", { name: "Cancel" }));
    expect(adminApi.users.update).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Disable Ngozi Writer" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Disable account" }),
    );
    await waitFor(() =>
      expect(adminApi.users.update).toHaveBeenCalledWith(2, { status: "disabled" }),
    );
    expect(await screen.findByText("Account disabled.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reactivate Old Analyst" })).toBeInTheDocument();
    // Administrators cannot disable their own account (Site Owner is the signed-in user).
    expect(screen.queryByRole("button", { name: "Disable Site Owner" })).not.toBeInTheDocument();
  });

  it("edits roles and sends password reset links", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Edit Ngozi Writer" }));
    const dialog = screen.getByRole("dialog", { name: "Edit administrator" });
    await user.click(within(dialog).getByLabelText(/Analyst/));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(adminApi.users.update).toHaveBeenCalledWith(2, {
        display_name: "Ngozi Writer",
        roles: ["editor", "analyst"],
      }),
    );

    await user.click(
      screen.getByRole("button", { name: "Send password reset link to Ngozi Writer" }),
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Send reset link" }),
    );
    await waitFor(() => expect(adminApi.users.sendPasswordReset).toHaveBeenCalledWith(2));
  });

  it("shows user details with effective permissions and activity", async () => {
    const user = userEvent.setup();
    renderApp("/admin/users");
    await user.click(await screen.findByRole("button", { name: "View details for Ngozi Writer" }));
    const dialog = await screen.findByRole("dialog", { name: "Administrator details" });
    // Server-resolved permissions, shown with catalogue labels.
    expect(await within(dialog).findByText("Edit any article")).toBeInTheDocument();
    expect(within(dialog).getByText("topics.manage")).toBeInTheDocument();
    expect(within(dialog).getByText("auth.login")).toBeInTheDocument();
    expect(within(dialog).queryByText("View users")).not.toBeInTheDocument();
  });

  it("revokes pending invitations after confirmation", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/users");
    await user.click(await screen.findByRole("tab", { name: "Invitations" }));
    await user.click(
      await screen.findByRole("button", { name: "Revoke invitation for pending@example.org" }),
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke invitation" }),
    );
    await waitFor(() => expect(adminApi.invitations.revoke).toHaveBeenCalledWith(11));
  });
});

describe("account activation and password reset links", () => {
  it("activates an invitation and signs the new administrator in", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(`/admin/activate#token=${VALID_TOKEN}`, {
      adminApi: createFakeAdminApi({ role: null }),
    });
    expect(await screen.findByText("invitee@example.org")).toBeInTheDocument();
    expect(adminApi.auth.verifyInvitation).toHaveBeenCalledWith(VALID_TOKEN);
    expect(screen.queryByText(VALID_TOKEN)).not.toBeInTheDocument();
    const name = screen.getByLabelText(/Your name/);
    expect(name).toHaveValue("Invitee");
    await user.type(screen.getByLabelText(/^New password/), "Fresh-Invitee-Pass-42");
    await user.type(screen.getByLabelText(/Confirm password/), "Fresh-Invitee-Pass-4");
    expect(screen.getByText("The passwords do not match.")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Confirm password/), "2");
    await user.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(adminApi.auth.acceptInvitation).toHaveBeenCalledWith({
      token: VALID_TOKEN,
      password: "Fresh-Invitee-Pass-42",
      display_name: "Invitee",
    });
  });

  it("rejects invalid or expired links without showing a form", async () => {
    renderApp("/admin/activate#token=expired-token-value-000000000", {
      adminApi: createFakeAdminApi({ role: null }),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /invalid, has already been used, or has expired/,
    );
    expect(screen.queryByLabelText(/New password/)).not.toBeInTheDocument();
  });

  it("handles a missing token", async () => {
    renderApp("/admin/activate", { adminApi: createFakeAdminApi({ role: null }) });
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/);
  });

  it("completes a password reset", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(`/admin/reset-password#token=${VALID_TOKEN}`, {
      adminApi: createFakeAdminApi({ role: null }),
    });
    expect(await screen.findByText("writer@example.org")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^New password/), "Brand-New-Secure-Pass-7");
    await user.type(screen.getByLabelText(/Confirm password/), "Brand-New-Secure-Pass-7");
    await user.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByText(/Your password has been changed/)).toBeInTheDocument();
    expect(adminApi.auth.completePasswordReset).toHaveBeenCalledWith({
      token: VALID_TOKEN,
      password: "Brand-New-Secure-Pass-7",
    });
  });
});

describe("granular permissions in the interface", () => {
  it("hides taxonomy editing from moderators and shows it to editors", async () => {
    const { unmount } = renderApp("/admin/topics", {
      adminApi: createFakeAdminApi({ role: "moderator" }),
    });
    expect(await screen.findByText("Positive Mindset")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New topic" })).not.toBeInTheDocument();
    unmount();
    renderApp("/admin/topics", { adminApi: createFakeAdminApi({ role: "editor" }) });
    expect(await screen.findByRole("button", { name: "New topic" })).toBeInTheDocument();
  });

  it("shows content analytics only to roles with analytics access", async () => {
    const { unmount } = renderApp("/admin", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByRole("heading", { name: "Content insights" })).toBeInTheDocument();
    unmount();
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(screen.queryByRole("heading", { name: "Content insights" })).not.toBeInTheDocument();
  });
});

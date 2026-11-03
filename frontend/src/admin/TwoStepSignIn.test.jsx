import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { adminUser, createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

async function signIn(user, email) {
  await user.type(await screen.findByLabelText(/Email/), email);
  await user.type(screen.getByLabelText(/Password/), "Correct-Horse-Battery-9");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("two-step sign-in", () => {
  it("asks enrolled staff for a code before signing in", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: null });
    renderApp("/admin/articles", { adminApi });
    await signIn(user, "mfa@example.org");

    const code = await screen.findByLabelText(/Verification code/);
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await user.type(code, "000000");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code isn't valid");

    await user.type(screen.getByLabelText(/Verification code/), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Articles" })).toBeInTheDocument();
    expect(adminApi.auth.verifyMfa).toHaveBeenLastCalledWith({
      mfa_token: "challenge-token",
      code: "123456",
    });
  });

  it("lets staff go back to the password step", async () => {
    const user = userEvent.setup();
    renderApp("/admin/login", { adminApi: createFakeAdminApi({ role: null }) });
    await signIn(user, "mfa@example.org");
    await user.click(await screen.findByRole("button", { name: "Start again" }));
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
  });

  it("sets up an authenticator app and shows the recovery codes once", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/account", { adminApi });
    const section = await screen.findByRole("region", { name: "Two-step sign-in" });
    await user.click(within(section).getByRole("button", { name: "Set up two-step sign-in" }));
    expect(await within(section).findByText(/ABCD EFGH/)).toBeInTheDocument();
    expect(
      within(section).getByRole("link", { name: /open the authenticator app/ }),
    ).toHaveAttribute("href", expect.stringMatching(/^otpauth:\/\/totp\//));
    await user.type(within(section).getByLabelText("Code from the app"), "123456");
    await user.click(within(section).getByRole("button", { name: "Turn on" }));
    const codes = await within(section).findByRole("list", { name: "Recovery codes" });
    expect(within(codes).getAllByRole("listitem")).toHaveLength(10);
    expect(adminApi.auth.mfaEnable).toHaveBeenCalledWith("123456");
    await user.click(within(section).getByRole("button", { name: "I've saved them" }));
    expect(within(section).queryByRole("list", { name: "Recovery codes" })).not.toBeInTheDocument();
  });

  it("sends staff who must enrol to their account page", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.auth.me = vi.fn(async () => ({
      data: { user: { ...adminUser("super_admin"), mfa_required: true, mfa_enabled: false } },
    }));
    adminApi.auth.mfaStatus = vi.fn(async () => ({
      data: { enabled: false, enabled_at: null, recovery_codes_left: 0, required: true },
    }));
    renderApp("/admin/articles", { adminApi });
    expect(await screen.findByText(/requires two-step sign-in/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Articles" })).not.toBeInTheDocument();
  });
});

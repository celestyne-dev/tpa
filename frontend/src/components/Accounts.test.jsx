import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { safeNext } from "@/commerce/hooks";
import { legacyTarget } from "@/routes/legacyTarget";
import { ApiError } from "@/services/apiClient";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import { preloadCommerce, renderApp } from "@/test/utils";

beforeAll(preloadCommerce);

const CSRF = "tpa_customer_csrf";
const setSessionCookie = () => {
  document.cookie = `${CSRF}=test-token; path=/`;
};
afterEach(() => {
  document.cookie = `${CSRF}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  window.location.hash = "";
});

const openNewsletter = (api) => {
  api.newsletterStatus = vi.fn(() =>
    Promise.resolve({
      data: {
        name: "The Positive Reset",
        signup_open: true,
        consent_text: "Yes, send me The Positive Reset newsletter.",
        consent_version: "v1",
      },
    }),
  );
  return api;
};

describe("safe redirects", () => {
  it.each([
    ["//evil.example", "/account"],
    ["/\\evil.example", "/account"],
    ["https://evil.example", "/account"],
    ["/%2F%2Fevil.example", "/account"],
    ["/admin/users", "/account"],
    ["/api/v1/account/me", "/account"],
    ["/login?next=/x", "/account"],
    ["/shop/calm\n", "/account"],
    ["/shop/calm-mornings-workbook", "/shop/calm-mornings-workbook"],
    ["/checkout?currency=USD", "/checkout?currency=USD"],
  ])("safeNext(%j) → %j", (value, expected) => {
    expect(safeNext(value)).toBe(expected);
  });

  it("maps old account addresses, keeping next and the token", () => {
    expect(legacyTarget("/account/login", "?next=/checkout", "")).toBe("/login?next=/checkout");
    expect(legacyTarget("/account/reset-password", "", "#token=abc")).toBe(
      "/reset-password#token=abc",
    );
    expect(legacyTarget("/account/reset-password", "", "")).toBe("/forgot-password");
    expect(legacyTarget("/account/verify-email", "", "#token=t")).toBe("/verify-email#token=t");
  });
});

describe("registration", () => {
  it("validates the form and only sends newsletter consent when ticked", async () => {
    const user = userEvent.setup();
    const shopApi = openNewsletter(createFakeShopApi());
    renderApp("/register?next=/account", { shopApi });
    await screen.findByRole("heading", { name: "Create your account" });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Enter your name.")).toBeInTheDocument();
    expect(shopApi.register).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/Your name/), "Ada Reader");
    await user.type(screen.getByLabelText(/^Email/), "ada@example.com");
    await user.type(screen.getByLabelText(/^Password\*?$/), "short");
    const rules = screen.getByRole("list", { name: "Password requirements" });
    expect(within(rules).getByText(/At least 12 characters/)).toHaveTextContent("(not met yet)");
    await user.clear(screen.getByLabelText(/^Password\*?$/));
    await user.type(screen.getByLabelText(/^Password\*?$/), "Correct-Horse-Battery-9");
    expect(within(rules).getByText(/At least 12 characters/)).toHaveTextContent("(met)");
    await user.type(screen.getByLabelText(/^Confirm password/), "Correct-Horse-Battery-8");
    await user.click(screen.getByRole("checkbox", { name: /I agree/ }));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("The passwords don't match.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^Confirm password/));
    await user.type(screen.getByLabelText(/^Confirm password/), "Correct-Horse-Battery-9");
    const optIn = screen.getByRole("checkbox", { name: /Positive Reset newsletter/ });
    expect(optIn).not.toBeChecked(); // explicit, never pre-ticked
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(shopApi.register).toHaveBeenCalled());
    expect(shopApi.register.mock.calls[0][0]).toMatchObject({
      display_name: "Ada Reader",
      password_confirm: "Correct-Horse-Battery-9",
      newsletter_opt_in: false,
      accept_terms: true,
    });
    expect(await screen.findByText(/Welcome! Your account is ready/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Please confirm your email address" }),
    ).toBeVisible();
  });

  it("hides the newsletter option while sign-ups are closed", async () => {
    renderApp("/register", { shopApi: createFakeShopApi() });
    await screen.findByRole("heading", { name: "Create your account" });
    expect(screen.queryByRole("checkbox", { name: /newsletter/i })).toBeNull();
  });
});

describe("log in", () => {
  it("shows and hides the password and sends the keep-me-signed-in choice", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    renderApp("/login?next=/account/orders", { shopApi });
    const password = await screen.findByLabelText(/^Password/);
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    await user.type(screen.getByLabelText(/^Email/), "ada@example.com");
    await user.type(password, "Correct-Horse-Battery-9");
    await user.click(screen.getByRole("checkbox", { name: /Keep me signed in/ }));
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(shopApi.login).toHaveBeenCalled());
    expect(shopApi.login.mock.calls[0][0]).toMatchObject({ remember: true });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Orders & receipts" }),
    ).toBeVisible();
  });

  it("explains rate limits and ended sessions", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    shopApi.login.mockRejectedValueOnce(
      new ApiError({ status: 429, code: "rate_limited", message: "Too many requests" }),
    );
    renderApp("/login?reason=expired", { shopApi });
    expect(await screen.findByText(/Your session has ended/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Email/), "ada@example.com");
    await user.type(screen.getByLabelText(/^Password/), "whatever-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many attempts/);
  });

  it("sends people whose session ended back to log in with a notice", async () => {
    setSessionCookie(); // a stale session: the cookie is there but the API says no
    renderApp("/account/orders", { shopApi: createFakeShopApi() });
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.getByText(/Your session has ended/)).toBeInTheDocument();
  });
});

describe("password recovery and email confirmation", () => {
  it("never says whether an account exists and allows resending", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    renderApp("/forgot-password", { shopApi });
    await user.type(await screen.findByLabelText(/^Email/), "who@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If an account exists for that email/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send the link again" }));
    await waitFor(() => expect(shopApi.requestPasswordReset).toHaveBeenCalledTimes(2));
  });

  it("resets with a token and returns to log in", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    window.location.hash = "#token=reset-token-0123456789abcdef";
    renderApp("/reset-password", { shopApi });
    await user.type(await screen.findByLabelText(/^New password/), "Brand-New-Passw0rd!");
    await user.type(screen.getByLabelText(/^Confirm new password/), "Brand-New-Passw0rd!");
    await user.click(screen.getByRole("button", { name: "Save new password" }));
    await waitFor(() =>
      expect(shopApi.completePasswordReset).toHaveBeenCalledWith(
        "reset-token-0123456789abcdef",
        "Brand-New-Passw0rd!",
      ),
    );
    expect(await screen.findByText(/Your password has been changed/)).toBeInTheDocument();
  });

  it("explains expired reset links and missing tokens", async () => {
    renderApp("/reset-password", { shopApi: createFakeShopApi() });
    expect(await screen.findByText(/Open the reset link from your email/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("confirms an address with a click and offers a new link otherwise", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    renderApp("/verify-email", { shopApi });
    await user.type(await screen.findByLabelText(/^Email/), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send a new confirmation link" }));
    expect(await screen.findByText(/If that address has an account/)).toBeInTheDocument();
    expect(shopApi.requestVerification).toHaveBeenCalledWith("ada@example.com");
  });

  it("keeps the token when an old reset address is opened", async () => {
    window.location.hash = "#token=reset-token-0123456789abcdef";
    renderApp("/account/reset-password#token=reset-token-0123456789abcdef", {
      shopApi: createFakeShopApi(),
    });
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeVisible();
    expect(screen.getByLabelText(/^New password/)).toBeInTheDocument();
  });
});

describe("header account navigation", () => {
  it("offers log in and create account to signed-out visitors", async () => {
    const user = userEvent.setup();
    const shopApi = createFakeShopApi();
    renderApp("/shop", { shopApi });
    const menu = await screen.findByRole("button", { name: "Log in or create an account" });
    await user.click(menu);
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/login?next=%2Fshop",
    );
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(shopApi.me).not.toHaveBeenCalled(); // no session cookie: nothing to confirm
  });

  it("shows my account and log out once the session is confirmed", async () => {
    const user = userEvent.setup();
    setSessionCookie();
    const shopApi = createFakeShopApi({ customer: customerProfile({ display_name: "Ada" }) });
    renderApp("/", { shopApi });
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My account" })).toHaveAttribute("href", "/account");
    await user.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(shopApi.logout).toHaveBeenCalled());
    expect(
      await screen.findByRole("button", { name: "Log in or create an account" }),
    ).toBeVisible();
  });

  it("lists account options in the mobile menu", async () => {
    const user = userEvent.setup();
    setSessionCookie();
    renderApp("/", { shopApi: createFakeShopApi({ customer: customerProfile() }) });
    await user.click(await screen.findByRole("button", { name: "Open menu" }));
    const nav = await screen.findByRole("navigation", { name: "Account" });
    expect(within(nav).getByRole("link", { name: "My library" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });
});

describe("account dashboard and settings", () => {
  it("shows real profile, library, order and newsletter details", async () => {
    setSessionCookie();
    const shopApi = createFakeShopApi({
      customer: customerProfile({ display_name: "Ada", email_verified: false }),
    });
    renderApp("/account", { shopApi });
    expect(await screen.findByRole("heading", { level: 1, name: "Hello, Ada" })).toBeVisible();
    expect(await screen.findByText("Calm Mornings Workbook")).toBeInTheDocument();
    expect(await screen.findByText("TPA-261023-ABCDEF")).toBeInTheDocument();
    expect(await screen.findByText(/You're not subscribed/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Please confirm your email address" }),
    ).toBeVisible();
  });

  it("asks for the password before exporting and a confirmation before deleting", async () => {
    const user = userEvent.setup();
    setSessionCookie();
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    renderApp("/account/settings", { shopApi });
    const exportForm = (await screen.findByRole("heading", { name: "Your data" })).closest("form");
    await user.type(within(exportForm).getByLabelText(/^Your password/), "Correct-Horse-Battery-9");
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    await user.click(within(exportForm).getByRole("button", { name: "Download my data" }));
    await waitFor(() => expect(shopApi.exportData).toHaveBeenCalledWith("Correct-Horse-Battery-9"));
    const deleteForm = screen.getByRole("heading", { name: "Delete account" }).closest("form");
    await user.type(
      within(deleteForm).getByLabelText(/^Confirm with your password/),
      "pw-value-123",
    );
    await user.click(within(deleteForm).getByRole("button", { name: "Delete my account" }));
    expect(await within(deleteForm).findByRole("alert")).toHaveTextContent(/tick the box/);
    expect(shopApi.deleteAccount).not.toHaveBeenCalled();
  });

  it("subscribes to the newsletter only with explicit consent", async () => {
    const user = userEvent.setup();
    setSessionCookie();
    const shopApi = createFakeShopApi({ customer: customerProfile() });
    renderApp("/account/settings", { shopApi });
    const subscribe = await screen.findByRole("button", { name: "Subscribe" });
    expect(subscribe).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Positive Reset newsletter/ }));
    await user.click(subscribe);
    await waitFor(() => expect(shopApi.subscribeFromAccount).toHaveBeenCalledWith("v1"));
    expect(await screen.findByText(/Check your inbox and confirm/)).toBeInTheDocument();
  });
});

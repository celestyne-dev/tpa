import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const CONSENT =
  "Yes, send me The Positive Reset, the daily email newsletter from Think Positive Always. " +
  "I can unsubscribe at any time.";

const collectingSite = {
  ...fx.site,
  newsletter: {
    ...fx.site.newsletter,
    is_open: true,
    signup_mode: "collection_only",
    confirmation_email: false,
    consent_text: CONSENT,
    consent_version: "2026-11-collection",
  },
};

function renderPage(site = collectingSite) {
  const shopApi = {
    ...createFakeShopApi(),
    subscribe: vi.fn(async () => ({
      data: { status: "received", message: "Your sign-up has been received." },
    })),
  };
  renderApp("/newsletter", {
    api: createFakeApi({ getSite: vi.fn(async () => ({ data: site })) }),
    shopApi,
  });
  return shopApi;
}

describe("The Positive Reset page", () => {
  it("has one hero form, the four daily themes, an illustrative example and a closing invitation", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { level: 1, name: "The Positive Reset" }),
    ).toBeInTheDocument();
    expect(screen.getByText("A Better Mindset. A Brighter Life.")).toBeInTheDocument();
    // Exactly one sign-up form on the page (the footer form is hidden here).
    const forms = screen.getAllByRole("form", { name: /Subscribe to The Positive Reset/ });
    expect(forms).toHaveLength(1);
    const [form] = forms;
    expect(within(form).getByLabelText(/First name/)).not.toBeRequired();
    expect(within(form).getByLabelText(/Email address/)).toBeRequired();
    expect(within(form).getByRole("checkbox", { name: CONSENT })).not.toBeChecked();

    const receive = screen.getByRole("region", { name: "What You'll Receive" });
    for (const title of [
      "Daily Encouragement",
      "Mindset & Wellbeing",
      "Personal Growth",
      "Practical Wisdom",
    ]) {
      expect(within(receive).getByRole("heading", { name: title })).toBeInTheDocument();
    }
    const glimpse = screen.getByRole("region", { name: "A Glimpse Into Your Daily Reset" });
    expect(within(glimpse).getByText(/illustrative, not a past issue/)).toBeInTheDocument();
    expect(within(glimpse).getByText("Example of the format")).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Start your daily reset" })).toBeInTheDocument();
    expect(document.querySelector("main").textContent).not.toMatch(/week/i);
  });

  it("takes keyboard users from the closing invitation straight to the email field", async () => {
    const user = userEvent.setup();
    Element.prototype.scrollIntoView ??= () => {};
    renderPage();
    const link = await screen.findByRole("link", { name: /Subscribe to The Positive Reset/ });
    link.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText(/Email address/)).toHaveFocus();
  });

  it("keeps collection-only sign-up: the shown consent version, no inbox promises", async () => {
    const user = userEvent.setup();
    const shopApi = renderPage();
    const form = await screen.findByRole("form", { name: /Subscribe to The Positive Reset/ });
    await user.type(within(form).getByLabelText(/Email address/), "reader@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(shopApi.subscribe).toHaveBeenCalledTimes(1));
    expect(shopApi.subscribe.mock.calls[0][0]).toMatchObject({
      consent: true,
      consent_version: "2026-11-collection",
      source: "newsletter_page",
    });
    const status = (await screen.findByText("Thank you for signing up.")).closest(
      '[role="status"]',
    );
    expect(status).not.toHaveTextContent(/inbox|confirmation/i);
  });

  it("shows no form and no subscribe link while sign-up is closed", async () => {
    renderPage({ ...fx.site, newsletter: { ...fx.site.newsletter, is_open: false } });
    expect(
      await screen.findByText(/isn.t available on the website at the moment/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /Subscribe/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Subscribe to/ })).not.toBeInTheDocument();
  });
});

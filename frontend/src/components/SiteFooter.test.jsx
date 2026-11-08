import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createFakeShopApi } from "@/test/commerceFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const link = (label, url) => ({ label, url, external: false, open_in_new_tab: false });

// Sign-up open (collection-only), and CMS footer menus as Admin › Navigation saves them.
const site = {
  ...fx.site,
  newsletter: {
    ...fx.site.newsletter,
    is_open: true,
    signup_mode: "collection_only",
    confirmation_email: false,
    consent_text: "Yes, send me The Positive Reset, the daily email newsletter.",
    consent_version: "2026-11-collection",
  },
  footer: {
    text: "Encouragement for every season.",
    show_newsletter_link: true,
    newsletter_label: "Learn about The Positive Reset", // the old default, unedited
    show_contact: false,
    show_social: false,
    copyright: "© {year} {site_name}. All rights reserved.",
    promo: null,
  },
  navigation: {
    ...fx.site.navigation,
    footer: [
      { title: "Explore", items: [link("Articles", "/articles"), link("Search", "/search")] },
      {
        title: "Resources",
        items: [
          link("Resource Library", "/resources"),
          link("The Positive Reset Newsletter", "/newsletter"),
        ],
      },
      { title: "Company", items: [link("About", "/about"), link("Contact", "/contact")] },
      { title: "Legal", items: [link("Privacy Policy", "/privacy-policy")] },
    ],
    legal: [link("Staff login", "/admin/login")],
  },
};

function renderAt(path, footerOverrides = {}) {
  renderApp(path, {
    api: createFakeApi({
      getSite: vi.fn(async () => ({
        data: { ...site, footer: { ...site.footer, ...footerOverrides } },
      })),
    }),
    shopApi: createFakeShopApi(),
  });
}

async function footerOf(path, overrides) {
  renderAt(path, overrides);
  const footer = await screen.findByRole("contentinfo");
  await waitFor(() =>
    expect(within(footer).getByText("Encouragement for every season.")).toBeInTheDocument(),
  );
  return footer;
}

/** What a reader sees in the footer: its text and every link with its address. */
function snapshot(footer) {
  const links = within(footer)
    .getAllByRole("link")
    .map((a) => `${a.textContent}|${a.getAttribute("href")}`);
  return { text: footer.textContent, links };
}

describe("the global footer", () => {
  it("is the same on every public page, with an invitation instead of a form", async () => {
    const pages = ["/", "/articles", "/resources", "/newsletter", "/about", "/contact"];
    const seen = [];
    for (const path of pages) {
      const footer = await footerOf(path);
      expect(within(footer).queryByRole("form")).toBeNull();
      expect(within(footer).queryByRole("textbox")).toBeNull();
      expect(within(footer).queryByRole("checkbox")).toBeNull();
      seen.push(snapshot(footer));
      cleanup();
    }
    for (const other of seen.slice(1)) expect(other).toEqual(seen[0]);
  });

  it("invites readers to /newsletter, keeps CMS columns and legal links, and avoids repeats", async () => {
    const footer = await footerOf("/resources");
    const invitation = footer.querySelector("[data-footer-newsletter]");
    expect(within(invitation).getByText("The Positive Reset")).toBeInTheDocument();
    expect(within(invitation).getByText("A little encouragement, every day.")).toBeInTheDocument();
    expect(
      within(invitation).getByRole("link", { name: /Explore the Newsletter/ }),
    ).toHaveAttribute("href", "/newsletter");
    // Only one link to /newsletter: the CMS column link is left out while the invitation shows.
    const toNewsletter = within(footer)
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href") === "/newsletter");
    expect(toNewsletter).toHaveLength(1);
    for (const title of ["Explore", "Resources", "Company", "Legal"]) {
      expect(within(footer).getByRole("navigation", { name: title })).toBeInTheDocument();
    }
    expect(within(footer).getByRole("link", { name: "Resource Library" })).toHaveAttribute(
      "href",
      "/resources",
    );
    expect(within(footer).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy-policy",
    );
    expect(within(footer).getByRole("link", { name: "Staff login" })).toHaveAttribute(
      "href",
      "/admin/login",
    );
    expect(within(footer).getByText(/All rights reserved/)).toBeInTheDocument();
  });

  it("follows the footer settings: custom button text, or no invitation at all", async () => {
    let footer = await footerOf("/about", { newsletter_label: "Read The Positive Reset" });
    expect(within(footer).getByRole("link", { name: /Read The Positive Reset/ })).toHaveAttribute(
      "href",
      "/newsletter",
    );
    cleanup();
    footer = await footerOf("/about", { show_newsletter_link: false });
    expect(footer.querySelector("[data-footer-newsletter]")).toBeNull();
    // With the invitation off, the CMS column link to the newsletter is shown again.
    expect(
      within(footer).getByRole("link", { name: "The Positive Reset Newsletter" }),
    ).toHaveAttribute("href", "/newsletter");
  });

  it("leaves exactly one sign-up form on /newsletter", async () => {
    renderAt("/newsletter");
    await screen.findByRole("heading", { level: 1, name: "The Positive Reset" });
    expect(screen.getAllByRole("form", { name: /Subscribe to The Positive Reset/ })).toHaveLength(
      1,
    );
  });
});

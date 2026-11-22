import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AnnouncementBar } from "./AnnouncementBar";

const STORAGE_KEY = "tpa:dismissed-announcements";
const DAY = 86_400_000;

const announcement = (extra = {}) => ({
  id: "1-1",
  message: "The Daily Reflection Journal is here: thirty quiet minutes with yourself.",
  cta: { label: "Get it free", href: "/shop/the-daily-reflection-journal" },
  variant: "sage",
  dismissible: true,
  target: "all",
  paths: [],
  starts_at: null,
  ends_at: null,
  ...extra,
});

const site = (announcements, extra = {}) => ({
  announcements,
  generated_at: new Date().toISOString(),
  ...extra,
});

function renderBar(s, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AnnouncementBar site={s} />
    </MemoryRouter>,
  );
}

const banner = () => screen.queryByRole("region", { name: "Announcement" });

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("announcement banner", () => {
  it("shows the message with a button-style link to the CMS destination", () => {
    renderBar(site([announcement()]));
    const bar = banner();
    expect(bar).toHaveTextContent(/The Daily Reflection Journal is here/);
    const cta = within(bar).getByRole("link", { name: "Get it free" });
    expect(cta).toHaveAttribute("href", "/shop/the-daily-reflection-journal");
    expect(cta).not.toHaveAttribute("target");
    expect(cta).toHaveClass("rounded-full", "bg-cream", "text-sage-800");
    expect(cta).toHaveClass("focus-visible:outline-2");
    expect(cta.querySelector("svg")).not.toBeNull(); // the arrow
  });

  it("opens https links in a new tab safely, without changing the address", () => {
    renderBar(
      site([
        announcement({ cta: { label: "Read on LinkedIn", href: "https://www.linkedin.com/" } }),
      ]),
    );
    const cta = within(banner()).getByRole("link", { name: /Read on LinkedIn/ });
    expect(cta).toHaveAttribute("href", "https://www.linkedin.com/");
    expect(cta).toHaveAttribute("target", "_blank");
    expect(cta).toHaveAttribute("rel", "noopener noreferrer");
    expect(cta).toHaveTextContent("(opens in a new tab)");
  });

  it("shows an announcement without a button", () => {
    renderBar(site([announcement({ cta: null })]));
    expect(banner()).toHaveTextContent(/Daily Reflection Journal/);
    expect(within(banner()).queryByRole("link")).toBeNull();
  });

  it("shows the optional label only when one is set, outside the message", () => {
    const { unmount } = renderBar(site([announcement()]));
    expect(within(banner()).queryByText("What's new")).toBeNull();
    unmount();
    renderBar(site([announcement()], { announcement_label: "What's new" }));
    const label = within(banner()).getByText("What's new");
    expect(label).toHaveClass("uppercase", "tracking-[0.16em]");
    expect(label.textContent).toBe("What's new");
  });

  it("dismisses with a 44px keyboard-accessible button and remembers it", async () => {
    const user = userEvent.setup();
    const { unmount } = renderBar(site([announcement()]));
    const close = within(banner()).getByRole("button", { name: "Dismiss announcement" });
    expect(close).toHaveClass("size-11", "focus-visible:outline-2");
    close.focus();
    await user.keyboard("{Enter}");
    expect(banner()).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY))).toEqual(["1-1"]);
    unmount();
    renderBar(site([announcement()]));
    expect(banner()).toBeNull();
  });

  it("shows an updated announcement again after an earlier version was dismissed", () => {
    // Stored by readers who closed revision 1 (the format existing readers already have).
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(["1-1"]));
    renderBar(site([announcement({ id: "1-2", message: "Now with a printable edition." })]));
    expect(banner()).toHaveTextContent("Now with a printable edition.");
  });

  it("has no dismiss button when the CMS makes it non-dismissible", () => {
    renderBar(site([announcement({ dismissible: false })]));
    expect(banner()).toBeInTheDocument();
    expect(within(banner()).queryByRole("button")).toBeNull();
  });

  it("follows homepage, all-page and selected-page targeting", () => {
    const home = announcement({ id: "2-1", target: "home", message: "Home only" });
    const { unmount } = renderBar(site([home]), "/articles");
    expect(banner()).toBeNull();
    unmount();
    const r2 = renderBar(site([home]), "/");
    expect(banner()).toHaveTextContent("Home only");
    r2.unmount();
    const paths = announcement({
      id: "3-1",
      target: "paths",
      paths: ["/quotes"],
      message: "Quotes",
    });
    const r3 = renderBar(site([paths]), "/");
    expect(banner()).toBeNull();
    r3.unmount();
    const r4 = renderBar(site([paths]), "/quotes");
    expect(banner()).toHaveTextContent("Quotes");
    r4.unmount();
    renderBar(site([announcement({ target: "all" })]), "/topics/mindset");
    expect(banner()).toBeInTheDocument();
  });

  it("hides scheduled and expired announcements, and renders nothing without one", () => {
    const future = new Date(Date.now() + DAY).toISOString();
    const past = new Date(Date.now() - DAY).toISOString();
    const { container, unmount } = renderBar(
      site([
        announcement({ id: "4-1", starts_at: future, message: "Not yet" }),
        announcement({ id: "5-1", ends_at: past, message: "Over" }),
      ]),
    );
    expect(banner()).toBeNull();
    expect(container).toBeEmptyDOMElement(); // no empty gap above the header
    unmount();
    const empty = renderBar(site([]));
    expect(empty.container).toBeEmptyDOMElement();
  });

  it.each([
    ["sage", "bg-sage-800", "bg-cream"],
    ["charcoal", "bg-charcoal", "bg-cream"],
    ["gold", "bg-gold-100", "bg-sage-800"],
    ["ivory", "bg-cream", "bg-sage-800"],
  ])("gives the %s variant a contrasting button", (variant, bar, button) => {
    renderBar(site([announcement({ variant })]));
    expect(banner()).toHaveClass(bar);
    expect(within(banner()).getByRole("link", { name: "Get it free" })).toHaveClass(button);
  });

  it("keeps long messages whole: no fixed height and no truncation", () => {
    const long = "A gentle reminder: ".repeat(10).trim();
    renderBar(site([announcement({ message: long })]));
    const bar = banner();
    expect(bar).toHaveTextContent(long);
    expect(bar.innerHTML).not.toMatch(/[\s"](h-\d|h-\[|max-h-|line-clamp-|truncate)/);
  });

  it("prerenders the banner with a placeholder where the dismiss button appears", () => {
    const html = renderToString(
      <MemoryRouter>
        <AnnouncementBar site={site([announcement()], { announcement_label: "What's new" })} />
      </MemoryRouter>,
    );
    expect(html).toContain("The Daily Reflection Journal is here");
    expect(html).toContain("What&#x27;s new");
    expect(html).toContain('href="/shop/the-daily-reflection-journal"');
    // The button needs the browser (it uses storage); a same-size placeholder keeps the
    // bar from shifting when it is added after hydration.
    expect(html).not.toContain("Dismiss announcement");
    expect(html).toMatch(/aria-hidden="true" class="-mr-2 size-11 shrink-0"/);
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { footerNav, mainNav } from "@/config/navigation";
import { liveLinks, topicSlugOf } from "@/hooks/useNavigation";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const LIVE = new Set(fx.topics.map((t) => t.slug));
const footer = () => document.querySelector("footer");
const footerTopicHrefs = () =>
  within(footer())
    .getAllByRole("link")
    .map((a) => a.getAttribute("href"))
    .filter((href) => href.startsWith("/topics/"));

describe("topic link helpers", () => {
  it("reads the slug of topic links only", () => {
    expect(topicSlugOf("/topics/personal-growth")).toBe("personal-growth");
    expect(topicSlugOf("/topics/personal-growth/page/2")).toBe("personal-growth");
    expect(topicSlugOf("/topics/personal-growth?ref=nav#top")).toBe("personal-growth");
    expect(topicSlugOf("/articles/personal-growth")).toBeNull();
    expect(topicSlugOf(null)).toBeNull();
  });

  it("drops links to unpublished topics once the topic list is known", () => {
    const items = [
      { label: "Articles", href: "/articles" },
      { label: "Mindset", href: "/topics/positive-mindset" },
      { label: "Typo", href: "/topics/elationships-and-connection" },
    ];
    expect(liveLinks(items, undefined)).toBe(items);
    expect(liveLinks(items, fx.topics).map((i) => i.label)).toEqual(["Articles", "Mindset"]);
  });

  it("the built-in menus hardcode no topic slugs", () => {
    const hrefs = [...mainNav, ...footerNav.flatMap((g) => g.items)].map((i) => i.href);
    expect(hrefs.filter((href) => href?.startsWith("/topics/"))).toEqual([]);
  });
});

describe("topic links in the site menus", () => {
  it("the built-in footer links only published topics with articles", async () => {
    const api = createFakeApi({
      getSite: vi.fn(async () => ({ data: { ...fx.site, navigation: undefined } })),
    });
    renderApp("/about", { api });
    await screen.findByRole("navigation", { name: "Topics we write about" });
    await waitFor(() => expect(footerTopicHrefs().length).toBeGreaterThan(0));
    for (const href of footerTopicHrefs()) expect(LIVE.has(topicSlugOf(href))).toBe(true);
    expect(footerTopicHrefs()).not.toContain("/topics/emotional-well-being"); // no articles
  });

  it("leaves out a saved footer link to a topic that does not exist", async () => {
    const api = createFakeApi({
      getSite: vi.fn(async () => ({
        data: {
          ...fx.site,
          navigation: {
            ...fx.site.navigation,
            footer: [
              {
                title: "Explore",
                items: [
                  { label: "Articles", url: "/articles" },
                  { label: "Personal Growth", url: "/topics/personal-growth" },
                  { label: "Relationships", url: "/topics/elationships-and-connection" },
                ],
              },
            ],
          },
        },
      })),
    });
    renderApp("/about", { api });
    // The About page loads the topic list; the footer then checks its topic links against it.
    await screen.findByRole("navigation", { name: "Topics we write about" });
    await waitFor(() =>
      expect(within(footer()).queryByRole("link", { name: "Relationships" })).toBeNull(),
    );
    expect(within(footer()).getByRole("link", { name: "Personal Growth" })).toHaveAttribute(
      "href",
      "/topics/personal-growth",
    );
  });

  it("the About page topic chips link only to real topic pages", async () => {
    renderApp("/about");
    const nav = await screen.findByRole("navigation", { name: "Topics we write about" });
    const hrefs = within(nav)
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(fx.topics.map((t) => `/topics/${t.slug}`));
  });
});

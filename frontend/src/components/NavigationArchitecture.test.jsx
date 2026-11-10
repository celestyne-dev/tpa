import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { byline } from "@/components/articles/ArticleCard";
import { groupIsActive } from "@/components/layout/NavDropdown";
import { resourceLinks } from "@/components/products/ResourcesNav";
import { SectionList } from "@/components/sections/SectionList";
import { routes, topicGroupAnchor } from "@/config/navigation";
import { groupTopics, MORE_TOPICS } from "@/pages/TopicsPage";
import { routeTable } from "@/routes/routeConfig";
import { createAppStore } from "@/store";
import { createFakeAdminApi } from "@/test/adminFake";
import * as fx from "@/test/fixtures";
import { createFakeApi, renderApp } from "@/test/utils";

const link = (label, url, extra = {}) => ({ label, url, ...extra });
const href = (label, h) => ({ label, href: h });

// Batch 14: the content-first header menu, as the server sends it.
const groupedMenu = [
  {
    label: "Mindset",
    url: null,
    children: [
      link("Positive Mindset", "/topics/positive-mindset"),
      link("All articles", "/articles"),
    ],
  },
  {
    label: "Career & Growth",
    url: null,
    children: [
      link("Personal Growth", "/topics/personal-growth"),
      link("All articles", "/articles"),
    ],
  },
  {
    label: "Resources",
    url: null,
    children: [
      link("All Resources", "/resources"),
      link("Free Downloads", "/free-resources"),
      link("My Library", "/account/library"),
    ],
  },
  link("Newsletter", "/newsletter"),
];

const siteWith = (primary) => ({
  ...fx.site,
  navigation: { primary, mobile: [], footer: [], legal: [] },
});

describe("navigation helpers", () => {
  it("anchors topic groups like the server", () => {
    expect(topicGroupAnchor("Career & Growth")).toBe("career-growth");
    expect(routes.topicGroup("Wellbeing")).toBe("/topics#wellbeing");
  });

  it("marks a group current on its pages and below them, never for All articles alone", () => {
    const mindset = [href("Positive", "/topics/positive-mindset"), href("All", "/articles")];
    expect(groupIsActive(mindset, "/topics/positive-mindset")).toBe(true);
    expect(groupIsActive(mindset, "/topics/positive-mindset/page/2")).toBe(true);
    expect(groupIsActive(mindset, "/articles")).toBe(false);
    expect(groupIsActive(mindset, "/articles/some-story")).toBe(false);
    const resources = [href("All", "/resources"), href("Premium", "/shop")];
    expect(groupIsActive(resources, "/shop/calm-workbook")).toBe(true);
    expect(groupIsActive(resources, "/shopping")).toBe(false);
    expect(groupIsActive([{ ...href("Out", "https://x.example"), external: true }], "/")).toBe(
      false,
    );
  });

  it("groups topics as in the menu, then the rest, leaving out topics without articles", () => {
    const menu = [
      { label: "Mindset", children: [href("Positive", "/topics/positive-mindset")] },
      { label: "Empty", children: [href("Calm", "/topics/emotional-well-being")] },
      { label: "Resources", children: [href("All", "/resources")] },
    ];
    const groups = groupTopics(menu, fx.topics);
    expect(groups.map((g) => g.label)).toEqual(["Mindset", MORE_TOPICS]);
    expect(groups[0].anchor).toBe("mindset");
    expect(groups[1].topics.map((t) => t.slug)).toEqual(["personal-growth"]);
  });

  it("the resources strip follows the Resources menu, with a fallback", () => {
    const menu = [
      {
        label: "Resources",
        children: [href("All", "/resources"), href("Free", "/free-resources")],
      },
    ];
    expect(resourceLinks(menu).map((l) => l.label)).toEqual(["All", "Free"]);
    expect(resourceLinks([]).map((l) => l.href)).toEqual([
      "/resources",
      "/free-resources",
      "/account/library",
    ]);
  });

  it("names the writer on cards, but not the site-name fallback", () => {
    expect(byline({ author: { slug: "jane", name: "Jane Doe" } })).toBe("Jane Doe");
    expect(byline({ author: { slug: "tpa", name: "Think Positive Always" } })).toBeNull();
    expect(byline({})).toBeNull();
  });

  it("serves /topics before /topics/:slug and prerenders it with the topics", () => {
    const route = routeTable.find((r) => r.path === "/topics");
    expect(route).toBeTruthy();
    expect(route.load()).toHaveLength(1);
  });
});

describe("content-first header", () => {
  it("shows several topic groups exactly as arranged, each ending with All articles", async () => {
    const user = userEvent.setup();
    renderApp("/", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: siteWith(groupedMenu) })) }),
    });
    const main = await screen.findByRole("navigation", { name: "Main" });
    const button = await within(main).findByRole("button", { name: "Mindset" });
    await user.click(button);
    const list = document.getElementById(button.getAttribute("aria-controls"));
    // Not expanded with every other topic: only the editor's links.
    await waitFor(() =>
      expect(
        within(list)
          .getAllByRole("link")
          .map((a) => a.textContent),
      ).toEqual(["Positive Mindset", "All articles"]),
    );
    // The Newsletter link is the header button on wide screens.
    expect(within(main).queryByRole("link", { name: "Newsletter" })).toBeNull();
  });

  it("marks the group of the current topic", async () => {
    renderApp("/topics/positive-mindset", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: siteWith(groupedMenu) })) }),
    });
    const main = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(main).findByRole("button", { name: "Mindset" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(within(main).getByRole("button", { name: "Resources" })).not.toHaveAttribute(
      "data-active",
    );
  });
});

describe("/topics", () => {
  it("lists the topic groups with anchors, jump links and structured data", async () => {
    renderApp("/topics", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: siteWith(groupedMenu) })) }),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Explore topics" })).toBeVisible();
    const mindset = await screen.findByRole("region", { name: "Mindset" });
    expect(mindset).toHaveAttribute("id", "mindset");
    expect(within(mindset).getByRole("link", { name: "Positive Mindset" })).toHaveAttribute(
      "href",
      "/topics/positive-mindset",
    );
    expect(screen.getByRole("region", { name: "Career & Growth" })).toHaveAttribute(
      "id",
      "career-growth",
    );
    // A topic with no articles is not shown.
    expect(screen.queryByRole("link", { name: /Emotional Well-being/ })).toBeNull();
    const jump = screen.getByRole("navigation", { name: "Topic groups" });
    expect(within(jump).getByRole("link", { name: "Career & Growth" })).toHaveAttribute(
      "href",
      "/topics#career-growth",
    );
    await waitFor(() => {
      const ld = [...document.head.querySelectorAll('script[type="application/ld+json"]')].map(
        (s) => s.textContent,
      );
      expect(ld.some((t) => t.includes("CollectionPage"))).toBe(true);
    });
  });
});

describe("resources", () => {
  it("links the resources pages from the library, following the menu", async () => {
    renderApp("/resources", {
      api: createFakeApi({ getSite: vi.fn(async () => ({ data: siteWith(groupedMenu) })) }),
    });
    const strip = await screen.findByRole("navigation", { name: "Resource pages" });
    const links = within(strip).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual([
      "All Resources",
      "Free Downloads",
      "My Library",
    ]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });

  it("shows affiliate recommendations with image, category and merchant, never as downloads", () => {
    const data = {
      heading: "Books",
      disclosure: "Some links are affiliate links.",
      links: [
        {
          id: 1,
          name: "The Calm Book",
          merchant: "Bookshop",
          category: "Book",
          note: "Short, kind chapters.",
          href: "/api/v1/go/the-calm-book",
          sponsored: true,
          image: { src: "/media/calm.webp", width: 600, height: 800, alt: "The Calm Book cover" },
        },
      ],
    };
    render(
      <MemoryRouter>
        <SectionList
          page={{
            title: "Recommended",
            sections: [
              { key: "b", type: "affiliate_recommendations", variant: "cards", design: {}, data },
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Book")).toBeInTheDocument();
    expect(screen.getByText("From Bookshop")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The Calm Book cover" })).toBeInTheDocument();
    const anchor = screen.getByRole("link", { name: /The Calm Book/ });
    expect(anchor).toHaveAttribute("href", "/api/v1/go/the-calm-book");
    expect(anchor).not.toHaveAttribute("download");
    expect(screen.getByText(data.disclosure)).toBeInTheDocument();
  });

  it("hides an empty digital products section on the website, explains it in previews", () => {
    const page = {
      title: "Home",
      sections: [
        {
          key: "p",
          type: "product_previews",
          variant: "grid",
          design: {},
          data: { heading: "Digital products", products: [] },
        },
      ],
    };
    const store = createAppStore({ api: createFakeApi() });
    const view = (preview) =>
      render(
        <Provider store={store}>
          <MemoryRouter>
            <SectionList page={page} preview={preview} />
          </MemoryRouter>
        </Provider>,
      );
    const { container, unmount } = view(false);
    expect(container.querySelector('[data-section="product_previews"]')).toBeNull();
    unmount();
    view(true);
    expect(screen.getByRole("note")).toHaveTextContent("No published products to show yet.");
  });
});

describe("Admin › Navigation", () => {
  it("loads the recommended structure into the editor without saving it", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    const recommended = [
      {
        label: "Mindset",
        link_type: "heading",
        url: null,
        open_in_new_tab: false,
        is_visible: true,
        visibility: "all",
        children: [
          {
            label: "Positive Mindset",
            link_type: "internal",
            url: "/topics/positive-mindset",
            open_in_new_tab: false,
            is_visible: true,
            visibility: "all",
          },
        ],
      },
    ];
    const list = adminApi.navigation.list;
    adminApi.navigation.list = vi.fn(async () => {
      const res = await list();
      return {
        ...res,
        data: res.data.map((m) => (m.key === "primary" ? { ...m, recommended } : m)),
      };
    });
    renderApp("/admin/navigation", { adminApi });
    const header = await screen.findByRole("region", { name: "Header navigation" });
    await user.click(within(header).getByRole("button", { name: "Use the recommended structure" }));
    expect(within(header).getByRole("status")).toHaveTextContent("nothing changes");
    expect(adminApi.navigation.save).not.toHaveBeenCalled();
    expect(within(header).getAllByLabelText("Label")[0]).toHaveValue("Mindset");
    expect(
      within(header).queryByRole("button", { name: "Use the recommended structure" }),
    ).toBeNull();
    await user.click(within(header).getByRole("button", { name: "Save and publish" }));
    await waitFor(() => expect(adminApi.navigation.save).toHaveBeenCalled());
    const [, items] = adminApi.navigation.save.mock.calls[0];
    expect(items[0]).toMatchObject({ label: "Mindset", link_type: "heading" });
  });
});

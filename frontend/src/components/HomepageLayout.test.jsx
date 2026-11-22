import { render, screen, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { SectionList } from "@/components/sections/SectionList";
import { createAppStore } from "@/store";
import * as fx from "@/test/fixtures";
import { formatDate } from "@/utils/format";

const [a1, a2, a3] = fx.articles;

const section = (key, type, variant, data, design = {}) => ({
  key,
  type,
  variant,
  design: { background: "ivory", spacing: "md", ...design },
  devices: "all",
  data,
});

/** A homepage shaped like TPA's: split hero, "Start here" grid and the topic explorer. */
function page(path = "/") {
  return {
    path,
    title: path === "/" ? "Homepage" : "About",
    sections: [
      section("hero", "hero", "split", {
        eyebrow: "Think Positive Always",
        heading: "A Better Mindset.",
        highlight: "A Brighter Life.",
        body: "Practical, encouraging reading for real life.",
        primary_cta: { label: "Start reading", href: "/articles", external: false },
        secondary_cta: { label: "Explore topics", href: "/topics", external: false },
        media: null,
      }),
      section("start-here", "featured_articles", "grid_3", {
        heading: "Start here",
        description: "Our most helpful stories.",
        articles: [a1, a2, a3],
      }),
      section(
        "topics",
        "topics_grid",
        "cards_4",
        { heading: "What's on your heart today?", topics: fx.topics },
        { background: "cream" },
      ),
      section("more", "latest_articles", "grid_3", { heading: "Latest", articles: [a2] }),
    ],
  };
}

function renderPage(p) {
  return render(
    <Provider store={createAppStore()}>
      <MemoryRouter>
        <main>
          <SectionList page={p} />
        </main>
      </MemoryRouter>
    </Provider>,
  );
}

const shells = () => [...document.querySelectorAll("main [data-section]")];

describe("compact homepage layout", () => {
  it("gives homepage sections the compact rhythm and one content width", () => {
    renderPage(page("/"));
    for (const shell of shells()) {
      expect(shell).toHaveClass("home-section");
      expect(shell.className).not.toMatch(/\bpy-16\b|\bsm:py-24\b|\blg:py-28\b/);
    }
    // The background is exposed so consecutive same-coloured sections share one gap.
    expect(shells().map((s) => s.dataset.bg)).toEqual(["ivory", "ivory", "cream", "ivory"]);
    for (const shell of shells()) {
      expect(shell.querySelector(".max-w-\\[75rem\\]")).not.toBeNull();
    }
  });

  it("keeps other pages that use the same sections exactly as before", () => {
    renderPage(page("/about"));
    for (const shell of shells()) {
      expect(shell).not.toHaveClass("home-section");
      expect(shell).not.toHaveAttribute("data-bg");
    }
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveClass("lg:text-7xl");
    const grid = screen.getByRole("region", { name: "Start here" });
    expect(within(grid).getAllByRole("heading", { level: 3 })[0]).not.toHaveClass("line-clamp-3");
    expect(within(grid).getByText(formatDate(a1.published_at))).toBeInTheDocument();
  });

  it("uses a smaller hero heading and keeps its message and buttons", () => {
    renderPage(page("/"));
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("A Better Mindset. A Brighter Life.");
    expect(h1).toHaveClass("lg:text-[3.5rem]", "text-balance");
    expect(h1).not.toHaveClass("lg:text-7xl");
    expect(screen.getByRole("link", { name: "Start reading" })).toHaveAttribute(
      "href",
      "/articles",
    );
    expect(screen.getByRole("link", { name: "Explore topics" })).toHaveAttribute("href", "/topics");
  });

  it("shows short article cards with every link, author, date and reading time", () => {
    renderPage(page("/"));
    const grid = screen.getByRole("region", { name: "Start here" });
    const cards = within(grid).getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    const first = within(cards[0]);
    const title = first.getByRole("heading", { level: 3, name: a1.title });
    expect(title).toHaveClass("line-clamp-3");
    expect(first.getByRole("link", { name: a1.title })).toHaveAttribute(
      "href",
      `/articles/${a1.slug}`,
    );
    // The excerpt stays in the page (two lines from tablets up; phones show the title row).
    expect(first.getByText(a1.excerpt)).toHaveClass("sm:line-clamp-2");
    expect(first.getByText(formatDate(a1.published_at, "short"))).toBeInTheDocument();
    expect(first.getByText(`${a1.reading_time_minutes} min read`)).toBeInTheDocument();
    // No fixed heights: cards grow with their content and fill the row.
    for (const card of cards) expect(card.innerHTML).not.toMatch(/\bh-\[\d/);
  });

  it("keeps every topic, its icon and its link in compact cards", () => {
    renderPage(page("/"));
    const region = screen.getByRole("region", { name: "What's on your heart today?" });
    const cards = within(region).getAllByRole("listitem");
    expect(cards).toHaveLength(fx.topics.length);
    for (const [i, topic] of fx.topics.entries()) {
      const card = within(cards[i]);
      expect(card.getByRole("link", { name: topic.name })).toHaveAttribute(
        "href",
        `/topics/${topic.slug}`,
      );
      expect(cards[i].querySelector("svg")).not.toBeNull();
    }
    // Four columns on desktops, two on phones and tablets.
    expect(within(region).getByRole("list")).toHaveClass("grid-cols-2", "lg:grid-cols-4");
  });
});

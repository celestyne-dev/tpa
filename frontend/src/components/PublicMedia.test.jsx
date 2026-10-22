import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";

const optimised = {
  src: "/media/abc/v1/calm-1280.jpg",
  srcset: "/media/abc/v1/calm-640.jpg 640w, /media/abc/v1/calm-1280.jpg 1280w",
  sources: {
    "image/webp": "/media/abc/v1/calm-320.webp 320w, /media/abc/v1/calm-640.webp 640w",
    "image/avif": "/media/abc/v1/calm-320.avif 320w",
  },
  alt: "A calm lake",
  width: 1600,
  height: 1000,
  placeholder: "#7a8f9c",
  focal: [0.25, 0.75],
};

describe("ContentImage", () => {
  it("renders <picture> with AVIF first, WebP next and a responsive fallback", () => {
    const { container } = render(<ContentImage image={optimised} sizes={IMAGE_SIZES.card} />);
    const sources = container.querySelectorAll("source");
    expect([...sources].map((s) => s.getAttribute("type"))).toEqual(["image/avif", "image/webp"]);
    expect(sources[1].getAttribute("sizes")).toBe(IMAGE_SIZES.card);
    const img = screen.getByRole("img", { name: "A calm lake" });
    expect(img).toHaveAttribute("width", "1600");
    expect(img).toHaveAttribute("height", "1000");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img.getAttribute("srcset")).toContain("640w");
    expect(img.style.backgroundColor).toBe("rgb(122, 143, 156)");
  });

  it("loads the main (LCP) image eagerly with high priority and focal cropping", () => {
    render(<ContentImage image={optimised} priority fill />);
    const img = screen.getByRole("img", { name: "A calm lake" });
    expect(img).toHaveAttribute("loading", "eager");
    expect(img).toHaveAttribute("fetchpriority", "high");
    expect(img.style.objectPosition).toBe("25% 75%");
  });

  it("renders built-in images as a plain <img> and degrades gracefully", () => {
    const { container, rerender } = render(
      <ContentImage image={{ src: "/images/a.svg", alt: "Built-in", width: 1600, height: 1000 }} />,
    );
    expect(container.querySelector("picture")).toBeNull();
    expect(screen.getByRole("img", { name: "Built-in" })).not.toHaveAttribute("srcset");
    rerender(<ContentImage image={null} />);
    expect(screen.getByRole("img", { name: "Image unavailable" })).toBeInTheDocument();
  });
});

describe("ArticleBody Batch 03 blocks", () => {
  const blocks = [
    { type: "pullquote", text: "Small steps count.", cite: "TPA" },
    { type: "image", media_id: 1, caption: "Morning", align: "wide", image: optimised },
    {
      type: "gallery",
      columns: 2,
      items: [
        { media_id: 1, image: optimised },
        { media_id: 2, image: { ...optimised, alt: "Second" } },
      ],
    },
    { type: "video", provider: "youtube", video_id: "dQw4w9WgXcQ", title: "A short talk" },
    { type: "button", label: "Read more", href: "/topics/confidence", style: "primary" },
    {
      type: "cta",
      title: "Join us",
      button_label: "Subscribe",
      button_href: "https://example.org",
    },
    {
      type: "related",
      articles: [{ slug: "quiet-confidence", title: "Quiet Confidence", image: optimised }],
    },
    {
      type: "table",
      header_row: true,
      caption: "Plan",
      rows: [
        ["Habit", "Minutes"],
        ["Walk", "20"],
      ],
    },
  ];

  it("renders accessible markup for every new block", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ArticleBody blocks={blocks} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Small steps count/)).toBeInTheDocument();
    expect(screen.getByText("Morning")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "A calm lake" }).length).toBeGreaterThan(1);
    expect(screen.getByRole("link", { name: /Read more/ })).toHaveAttribute(
      "href",
      "/topics/confidence",
    );
    expect(screen.getByRole("link", { name: /Subscribe/ })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(screen.getByRole("link", { name: "Quiet Confidence" })).toHaveAttribute(
      "href",
      "/articles/quiet-confidence",
    );
    const table = screen.getByRole("table", { name: "Plan" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((th) => th.textContent),
    ).toEqual(["Habit", "Minutes"]);
    // Videos load nothing from the provider until the reader presses play.
    expect(container.querySelector("iframe")).toBeNull();
    await user.click(screen.getByRole("button", { name: /Play video: A short talk/ }));
    const iframe = container.querySelector("iframe");
    expect(iframe.getAttribute("src")).toContain("youtube-nocookie.com/embed/dQw4w9WgXcQ");
    expect(iframe).toHaveAttribute("title", "A short talk");
  });
});

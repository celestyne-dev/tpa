import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { READER_THEMES } from "@/components/courses/reader/readerPrefs";
import {
  anchorFromSelection,
  normalize,
  rangeForAnchor,
  textIndex,
} from "@/components/courses/reader/textAnchors";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import { createCourseShopApi } from "@/test/courseFake";
import { preloadCommerce, renderApp } from "@/test/utils";

beforeAll(preloadCommerce);

const CSRF = "tpa_customer_csrf";
const signIn = () => {
  document.cookie = `${CSRF}=test-token; path=/`;
};
afterEach(() => {
  document.cookie = `${CSRF}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  window.getSelection()?.removeAllRanges();
});

function learner(options) {
  return { ...createFakeShopApi({ customer: customerProfile() }), ...createCourseShopApi(options) };
}

async function openLesson(options = {}) {
  signIn();
  const shopApi = learner({ enrolled: true, ...options });
  const view = renderApp("/learn/calm-foundations/notice-the-pause", { shopApi });
  await screen.findByRole("heading", { level: 1, name: "Notice the pause" });
  return { shopApi, ...view };
}

function select(element, text) {
  const node = [...element.childNodes].find((n) => n.nodeType === 3 && n.nodeValue.includes(text));
  const start = node.nodeValue.indexOf(text);
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, start + text.length);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

describe("premium lesson reader", () => {
  it("shows the course outline, module progress, a table of contents and lesson navigation", async () => {
    await openLesson();
    const outlines = screen.getAllByRole("navigation", { name: "Course outline" });
    expect(outlines.length).toBeGreaterThan(0);
    const current = within(outlines[0]).getByRole("link", { name: /Notice the pause/ });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Module progress: 0 of 2 lessons")).toBeInTheDocument();
    const toc = screen.getAllByRole("navigation", { name: "In this lesson" })[0];
    expect(within(toc).getByRole("link", { name: "Try it" })).toHaveAttribute(
      "href",
      "#section-h2",
    );
    expect(document.getElementById("section-h2")).toHaveTextContent("Try it");
    expect(screen.getByRole("link", { name: /Next lesson: Breathe/ })).toHaveAttribute(
      "href",
      "/learn/calm-foundations/breathe",
    );
    // Every block can be pointed at by notes, highlights and the reading position.
    expect(document.querySelectorAll("article [data-block-uid]").length).toBeGreaterThan(5);
  });

  it("saves bookmarks and checklist ticks to the learner's account", async () => {
    const user = userEvent.setup();
    const { shopApi } = await openLesson({ study: { checklist: ["i2"] } });
    expect(screen.getByRole("checkbox", { name: "Curtains open" })).toBeChecked();
    expect(screen.getByText(/1 of 2 done/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Phone away" }));
    await waitFor(() =>
      expect(shopApi.setChecklistItem).toHaveBeenCalledWith(
        "calm-foundations",
        "notice-the-pause",
        "i1",
        true,
      ),
    );
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Phone away" })).toBeChecked());

    const bookmark = screen.getByRole("button", { name: /Save lesson/ });
    expect(bookmark).toHaveAttribute("aria-pressed", "false");
    await user.click(bookmark);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Saved/ })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(shopApi.setBookmark).toHaveBeenCalledWith("calm-foundations", "notice-the-pause", true);
  });

  it("writes private notes with autosave and clear status", async () => {
    const user = userEvent.setup();
    const { shopApi } = await openLesson();
    const toggle = screen.getByRole("button", { name: /^Notes/ });
    await user.click(toggle);
    const panel = screen.getByRole("complementary", { name: /Notes & highlights/ });
    await user.type(within(panel).getByLabelText("New note on this lesson"), "Pause first");
    expect(within(panel).getByText("Unsaved changes")).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByText("Saved")).toBeInTheDocument(), {
      timeout: 3000,
    });
    expect(shopApi.createNote).toHaveBeenCalledWith("calm-foundations", "notice-the-pause", {
      body: "Pause first",
    });
    expect(within(panel).getByRole("heading", { name: "Notes (1)" })).toBeInTheDocument();
    // Escape closes the panel and focus returns to the toggle.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: /Notes & highlights/ })).toBeNull();
    expect(toggle).toHaveFocus();
  });

  it("highlights selected text using a stable anchor and offers a passage note", async () => {
    const user = userEvent.setup();
    const { shopApi } = await openLesson();
    const paragraph = document.querySelector('[data-block-uid="p1"]');
    select(paragraph, "notice three things");
    const toolbar = await screen.findByRole("toolbar", { name: /selected text/ });
    await user.click(within(toolbar).getByRole("button", { name: "Highlight in green" }));
    await waitFor(() => expect(shopApi.createHighlight).toHaveBeenCalled());
    const [, , body] = shopApi.createHighlight.mock.calls[0];
    expect(body).toEqual({
      color: "green",
      anchor: {
        block: "p1",
        quote: "notice three things",
        prefix: "Breathe in slowly and ",
        suffix: ".",
        start: 22,
      },
    });
    expect(await screen.findByText("Highlighted in green.")).toBeInTheDocument();

    select(paragraph, "Breathe in slowly");
    await user.click(await screen.findByRole("button", { name: "Add note" }));
    const panel = screen.getByRole("complementary", { name: /Notes & highlights/ });
    expect(within(panel).getByText("“Breathe in slowly”")).toBeInTheDocument();
    expect(within(panel).getByLabelText("Note on this passage")).toHaveFocus();
  });

  it("refuses selections across blocks or on interactive parts", async () => {
    await openLesson();
    const start = document.querySelector('[data-block-uid="p1"]').firstChild;
    const end = document.querySelector('[data-block-uid="k1"] li').firstChild;
    const range = document.createRange();
    range.setStart(start, 0);
    range.setEnd(end, 3);
    window.getSelection().addRange(range);
    act(() => {
      document.dispatchEvent(new Event("selectionchange"));
    });
    expect(await screen.findByText("Select text within one paragraph or block.")).toBeVisible();
  });

  it("returns the reader to the last meaningful position", async () => {
    const user = userEvent.setup();
    await openLesson({ study: { position: { block: "k1", percent: 40 } } });
    expect(await screen.findByText("We've taken you back to where you left off.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start from the top" }));
    expect(screen.queryByText("We've taken you back to where you left off.")).toBeNull();
  });

  it("lists highlights and notes in the panel, including orphaned excerpts", async () => {
    const user = userEvent.setup();
    const { shopApi } = await openLesson({
      study: {
        highlights: [
          {
            id: "hx",
            color: "yellow",
            status: "orphaned",
            anchor: { block: "gone1", quote: "An old sentence." },
          },
        ],
      },
    });
    await user.click(screen.getByRole("button", { name: /^Notes/ }));
    const panel = screen.getByRole("complementary", { name: /Notes & highlights/ });
    expect(within(panel).getByText(/this passage changed in a later version/)).toBeVisible();
    await user.selectOptions(within(panel).getByLabelText("Highlight colour"), "blue");
    expect(shopApi.updateHighlight).toHaveBeenCalledWith("hx", "blue");
    await user.click(within(panel).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(shopApi.deleteHighlight).toHaveBeenCalledWith("hx"));
  });
});

describe("study notebook and search", () => {
  it("filters notes, highlights, bookmarks and checklists and offers exports", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learner({ enrolled: true });
    renderApp("/account/learning/notebook", { shopApi });
    expect(await screen.findByRole("heading", { level: 1, name: "Study notebook" })).toBeVisible();
    expect(await screen.findByText("Try this before breakfast.")).toBeVisible();
    expect(screen.getByText(/Excerpt hidden while you can't open this course/)).toBeVisible();
    expect(screen.getByRole("link", { name: /Text file/ })).toHaveAttribute(
      "href",
      "/api/v1/account/study/export?format=txt",
    );
    await user.selectOptions(screen.getByLabelText("Course"), "calm-foundations");
    await waitFor(() =>
      expect(shopApi.notebook).toHaveBeenLastCalledWith({ course: "calm-foundations" }),
    );
    expect(screen.getByRole("link", { name: /PDF/ })).toHaveAttribute(
      "href",
      "/api/v1/account/study/export?format=pdf&course=calm-foundations",
    );

    await user.click(screen.getByRole("tab", { name: /Highlights/ }));
    expect(screen.getByRole("tab", { name: /Highlights/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getAllByRole("link", { name: "Notice the pause" })[0]).toHaveAttribute(
      "href",
      "/learn/calm-foundations/notice-the-pause?highlight=hl1",
    );
    expect(screen.getByText(/the lesson text has changed/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /Bookmarks/ }));
    expect(screen.getByText(/Access ended/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /Checklists/ }));
    expect(screen.getByText("Before bed: 1 of 2 ticked")).toBeVisible();

    await user.type(screen.getByLabelText("Search your notebook"), "breakfast");
    await waitFor(() =>
      expect(shopApi.notebook).toHaveBeenLastCalledWith({
        course: "calm-foundations",
        q: "breakfast",
      }),
    );
  });

  it("searches courses the learner can open, marking the matches", async () => {
    signIn();
    const shopApi = learner({ enrolled: true });
    renderApp("/learn/search?q=notice", { shopApi });
    expect(await screen.findByRole("heading", { level: 1, name: "Search courses" })).toBeVisible();
    const link = await screen.findByRole("link", { name: "Notice the pause" });
    expect(link).toHaveAttribute("href", "/learn/calm-foundations/notice-the-pause");
    expect(shopApi.searchLearning).toHaveBeenCalledWith("notice");
    expect(document.querySelectorAll("mark").length).toBeGreaterThan(0);
  });

  it("links My learning to search and the notebook", async () => {
    signIn();
    renderApp("/account/learning", { shopApi: learner({ enrolled: true }) });
    expect(await screen.findByRole("search")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /notebook/i }).length).toBeGreaterThan(0);
  });
});

// ---- units -------------------------------------------------------------------------------

describe("text anchors", () => {
  it("measures normalised text, skips interactive parts and round-trips selections", () => {
    const root = document.createElement("article");
    root.innerHTML = `
      <section data-block-uid="e1" data-highlightable>
        <h3>Try   it</h3><p>Write down
        three things.</p><div data-study-ignore><label>Your notes</label></div>
      </section>
      <ul data-block-uid="l1" data-highlightable><li>One</li><li>Two</li></ul>`;
    document.body.append(root);
    expect(textIndex(root.querySelector('[data-block-uid="e1"]')).text).toBe(
      "Try it Write down three things.",
    );
    expect(textIndex(root.querySelector('[data-block-uid="l1"]')).text).toBe("One Two");
    const p = root.querySelector("p").firstChild;
    const range = document.createRange();
    range.setStart(p, 0);
    range.setEnd(p, p.nodeValue.indexOf("things") + 6);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    const { anchor } = anchorFromSelection(selection, root);
    expect(anchor).toMatchObject({
      block: "e1",
      quote: "Write down three things",
      prefix: "Try it ",
    });
    const found = rangeForAnchor(root, anchor);
    expect(normalize(found.toString())).toBe("Write down three things");
    root.remove();
  });
});

describe("reading themes", () => {
  const luminance = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a, b) => {
    const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
    return (x + 0.05) / (y + 0.05);
  };

  it.each(Object.keys(READER_THEMES))("keeps strong contrast in the %s theme", (name) => {
    const theme = {
      "--color-sage-700": "#45593c",
      "--color-charcoal": "#24221f",
      ...READER_THEMES[name],
    };
    for (const bg of ["--color-ivory", "--color-white"]) {
      expect(contrast(theme["--color-ink"], theme[bg])).toBeGreaterThanOrEqual(7);
      expect(contrast(theme["--color-muted"], theme[bg])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme["--color-sage-700"], theme[bg])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme["--color-charcoal"], theme[bg])).toBeGreaterThanOrEqual(7);
    }
  });
});

describe("selection helpers", () => {
  it("ignores collapsed selections", () => {
    const root = document.createElement("article");
    document.body.append(root);
    fireEvent.mouseUp(root);
    expect(anchorFromSelection(window.getSelection(), root)).toBeNull();
    root.remove();
  });
});

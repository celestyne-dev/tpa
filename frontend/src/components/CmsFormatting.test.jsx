import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { BlockEditor, continuedStart } from "@/admin/components/BlockEditor";
import { cleanBlocks } from "@/admin/components/blocks";
import { htmlToInline } from "@/admin/components/inlineFormatting";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { parseInline, stripInlineLinks } from "@/utils/inlineLinks";

const renderBody = (blocks) =>
  render(
    <MemoryRouter>
      <ArticleBody blocks={blocks} />
    </MemoryRouter>,
  );

describe("bold and italic in articles", () => {
  it("parses emphasis and links without touching ordinary asterisks or snake_case", () => {
    expect(parseInline("a **b** *c* _d_ snake_case 2*3*4 5 * 6")).toEqual([
      { text: "a " },
      { strong: [{ text: "b" }] },
      { text: " " },
      { em: [{ text: "c" }] },
      { text: " " },
      { em: [{ text: "d" }] },
      { text: " snake_case 2*3*4 5 * 6" },
    ]);
    expect(stripInlineLinks("**[Calm](/topics/calm)** *now*")).toBe("Calm now");
  });

  it("renders bold, italic and links as elements, never as HTML", () => {
    const { container } = renderBody([
      {
        type: "paragraph",
        text: "Be **kind** to *yourself*, read [**this**](/articles) <b>raw</b>.",
      },
      { type: "list", ordered: false, items: ["**Bold item**", "_Italic item_"] },
    ]);
    expect(container.querySelector("p strong")).toHaveTextContent("kind");
    expect(container.querySelector("p em")).toHaveTextContent("yourself");
    expect(screen.getByRole("link", { name: "this" }).querySelector("strong")).not.toBeNull();
    expect(container.querySelector("p b")).toBeNull(); // typed HTML stays text
    expect(container.querySelector("p")).toHaveTextContent("<b>raw</b>");
    expect(container.querySelector("li strong")).toHaveTextContent("Bold item");
    expect(container.querySelector("li em")).toHaveTextContent("Italic item");
  });

  it("keeps bold, italic and links pasted from Google Docs or Word", () => {
    const docs =
      '<b style="font-weight:normal" id="docs-internal-guid-1"><p><span>Start </span>' +
      '<span style="font-weight:700">strong</span><span> and </span>' +
      '<span style="font-style:italic">soft</span> <a href="https://example.org/x">link</a>' +
      ' <a href="javascript:alert(1)">bad</a></p></b>';
    expect(htmlToInline(docs)).toBe(
      "Start **strong** and *soft* [link](https://example.org/x) bad",
    );
    expect(htmlToInline("<ul><li><strong>One</strong></li><li><em>Two</em></li></ul>")).toBe(
      "**One**\n*Two*",
    );
  });

  it("wraps the selection with Ctrl/⌘+B in the editor", () => {
    let latest;
    function Harness() {
      const [blocks, setBlocks] = useState([{ type: "paragraph", text: "make me bold" }]);
      latest = blocks;
      return <BlockEditor blocks={blocks} onChange={setBlocks} />;
    }
    render(<Harness />);
    const field = screen.getByLabelText("Paragraph 1 text");
    field.setSelectionRange(8, 12);
    fireEvent.keyDown(field, { key: "b", ctrlKey: true });
    expect(latest[0].text).toBe("make me **bold**");
    field.setSelectionRange(0, 4);
    fireEvent.keyDown(field, { key: "i", metaKey: true });
    expect(latest[0].text).toBe("*make* me **bold**");
  });
});

describe("numbered lists that continue", () => {
  it("renders the saved start number and leaves other lists at 1", () => {
    const { container } = renderBody([
      { type: "list", ordered: true, items: ["One", "Two"] },
      { type: "paragraph", text: "A pause." },
      { type: "list", ordered: true, start: 11, items: ["Eleven"] },
      { type: "list", ordered: true, items: ["Fresh"] },
    ]);
    const lists = container.querySelectorAll("ol");
    expect(lists[0].hasAttribute("start")).toBe(false);
    expect(lists[1].getAttribute("start")).toBe("11");
    expect(lists[2].hasAttribute("start")).toBe(false);
  });

  it("offers to continue from the previous numbered list, only when asked", async () => {
    const user = userEvent.setup();
    let latest;
    const ten = Array.from({ length: 10 }, (_, i) => `Item ${i + 1}`);
    function Harness() {
      const [blocks, setBlocks] = useState([
        { type: "list", ordered: true, items: ten },
        { type: "paragraph", text: "Between the lists." },
        { type: "list", ordered: true, items: ["Next"] },
      ]);
      latest = blocks;
      return <BlockEditor blocks={blocks} onChange={setBlocks} />;
    }
    render(<Harness />);
    expect(latest[2].start).toBeUndefined(); // not continued automatically
    expect(screen.getByLabelText("List 3 starts at")).toHaveValue(1);
    await user.click(screen.getByRole("button", { name: "Continue numbering from 11" }));
    expect(latest[2].start).toBe(11);
    expect(screen.getByLabelText("List 3 starts at")).toHaveValue(11);
    expect(screen.queryByRole("button", { name: /Continue numbering/ })).toBeNull();
    // The saved payload keeps the start only on the continued numbered list.
    const saved = cleanBlocks(latest);
    expect(saved[2].start).toBe(11);
    expect("start" in saved[0]).toBe(false);
    expect(continuedStart([{ type: "list", ordered: true, start: 11, items: ["a", "b"] }])).toBe(
      13,
    );
  });
});

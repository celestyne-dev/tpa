export const BLOCK_TEMPLATES = {
  paragraph: { label: "Paragraph", make: () => ({ type: "paragraph", text: "" }) },
  heading: { label: "Heading", make: () => ({ type: "heading", text: "", level: 2 }) },
  bulleted: { label: "Bulleted list", make: () => ({ type: "list", ordered: false, items: [""] }) },
  numbered: { label: "Numbered list", make: () => ({ type: "list", ordered: true, items: [""] }) },
  quote: { label: "Quote", make: () => ({ type: "quote", text: "", cite: "" }) },
  callout: {
    label: "Callout",
    make: () => ({ type: "callout", tone: "info", title: "", text: "" }),
  },
  divider: { label: "Divider", make: () => ({ type: "divider" }) },
};

export function blockLabel(block) {
  if (block.type === "list") return block.ordered ? "Numbered list" : "Bulleted list";
  return BLOCK_TEMPLATES[block.type]?.label ?? block.type;
}

/** Removes empty optional fields so the payload matches the API's block rules. */
export function cleanBlocks(blocks) {
  return blocks.map((block) => {
    const out = { ...block };
    if (out.type === "list") out.items = out.items.map((i) => i.trim()).filter(Boolean);
    ["cite", "title"].forEach((k) => {
      if (k in out && !String(out[k]).trim()) delete out[k];
    });
    return out;
  });
}

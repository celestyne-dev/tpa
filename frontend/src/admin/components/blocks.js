export const BLOCK_TEMPLATES = {
  paragraph: { label: "Paragraph", make: () => ({ type: "paragraph", text: "" }) },
  heading: { label: "Heading", make: () => ({ type: "heading", text: "", level: 2 }) },
  bulleted: { label: "Bulleted list", make: () => ({ type: "list", ordered: false, items: [""] }) },
  numbered: { label: "Numbered list", make: () => ({ type: "list", ordered: true, items: [""] }) },
  quote: { label: "Quote", make: () => ({ type: "quote", text: "", cite: "" }) },
  pullquote: { label: "Pull quote", make: () => ({ type: "pullquote", text: "", cite: "" }) },
  callout: {
    label: "Callout",
    make: () => ({ type: "callout", tone: "info", title: "", text: "" }),
  },
  image: {
    label: "Image",
    make: () => ({ type: "image", media_id: null, caption: "", alt: "", align: "center" }),
  },
  gallery: {
    label: "Gallery",
    make: () => ({ type: "gallery", items: [], columns: 3, caption: "" }),
  },
  video: { label: "Video", make: () => ({ type: "video", url: "", title: "", caption: "" }) },
  button: {
    label: "Button",
    make: () => ({ type: "button", label: "", href: "", style: "primary", align: "left" }),
  },
  cta: {
    label: "Call to action",
    make: () => ({ type: "cta", title: "", text: "", button_label: "", button_href: "" }),
  },
  related: {
    label: "Related articles",
    make: () => ({ type: "related", title: "", article_ids: [] }),
  },
  resource: {
    label: "Resource",
    make: () => ({
      type: "resource",
      title: "",
      description: "",
      href: "",
      label: "",
      kind: "resource",
    }),
  },
  table: {
    label: "Table",
    make: () => ({
      type: "table",
      caption: "",
      header_row: true,
      rows: [
        ["", ""],
        ["", ""],
      ],
    }),
  },
  divider: { label: "Divider", make: () => ({ type: "divider" }) },
};

export function blockLabel(block) {
  if (block.type === "list") return block.ordered ? "Numbered list" : "Bulleted list";
  return BLOCK_TEMPLATES[block.type]?.label ?? block.type;
}

export function videoUrl(block) {
  if (block.url) return block.url;
  if (block.provider === "youtube" && block.video_id)
    return `https://www.youtube.com/watch?v=${block.video_id}`;
  if (block.provider === "vimeo" && block.video_id) return `https://vimeo.com/${block.video_id}`;
  return "";
}

const OPTIONAL_TEXT = ["cite", "title", "caption", "alt", "text", "description", "label"];
const REQUIRED_TEXT = {
  paragraph: ["text"],
  heading: ["text"],
  quote: ["text"],
  pullquote: ["text"],
  callout: ["text"],
};

/** Removes empty optional fields so the payload matches the API's block rules. */
export function cleanBlocks(blocks) {
  return blocks.map((block) => {
    const out = { ...block };
    if (out.type === "list") out.items = out.items.map((i) => i.trim()).filter(Boolean);
    OPTIONAL_TEXT.forEach((k) => {
      if (REQUIRED_TEXT[out.type]?.includes(k)) return;
      if (k in out && !String(out[k] ?? "").trim()) delete out[k];
    });
    if (out.type === "video") {
      if (out.url) {
        delete out.provider;
        delete out.video_id;
      } else delete out.url;
    }
    if (out.type === "resource" && !out.media_id) delete out.media_id;
    if (out.type === "gallery")
      out.items = out.items.map(({ media_id, caption, alt }) => ({
        media_id,
        ...(caption?.trim() && { caption }),
        ...(alt?.trim() && { alt }),
      }));
    return out;
  });
}

/** Word count and reading time computed like the API (225 words per minute). */
export function countWords(blocks) {
  let words = 0;
  const count = (text) => (text ? String(text).trim().split(/\s+/).filter(Boolean).length : 0);
  for (const block of blocks) {
    if (block.type === "list") block.items.forEach((i) => (words += count(i)));
    else if (block.type === "table") block.rows.flat().forEach((c) => (words += count(c)));
    else if (["paragraph", "heading", "quote", "pullquote", "callout"].includes(block.type)) {
      words += count(block.text);
      if (block.type === "callout") words += count(block.title);
    }
  }
  return words;
}

export const readingMinutes = (words) => Math.max(1, Math.round(words / 225));

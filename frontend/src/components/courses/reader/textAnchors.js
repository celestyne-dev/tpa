/**
 * Text anchors for highlights and passage notes (mirrors app/services/courses/anchors.py).
 *
 * Each lesson block is rendered with ``data-block-uid``. A passage is identified by the
 * block, the exact quote and up to 32 characters of text before/after it, measured on
 * whitespace-normalised text. Interactive parts of a block (exercise answer boxes,
 * buttons) carry ``data-study-ignore`` and are left out, so the text matches what the
 * server stores. Highlights are painted with the CSS Custom Highlight API, which never
 * changes the lesson's DOM or content.
 */

export const CONTEXT = 32;

/** Escapes a value for an attribute selector (CSS.escape where available). */
export const cssEscape = (value) =>
  typeof CSS !== "undefined" && CSS.escape
    ? CSS.escape(value)
    : String(value).replace(/["\\\][]/g, "\\$&");

/** The rendered element of a lesson block. */
export const blockElement = (root, uid) =>
  root?.querySelector(`[data-block-uid="${cssEscape(uid)}"]`) ?? null;
export const COLORS = ["yellow", "green", "blue", "pink"];
export const COLOR_LABELS = { yellow: "Yellow", green: "Green", blue: "Blue", pink: "Pink" };

export const normalize = (text) =>
  String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();

const BREAK_TAGS = new Set(["LI", "P", "H2", "H3", "H4", "DT", "DD", "LABEL", "FIGCAPTION"]);

function breakParent(node) {
  let el = node.parentElement;
  while (el && !BREAK_TAGS.has(el.tagName) && !el.hasAttribute("data-block-uid")) {
    el = el.parentElement;
  }
  return el;
}

/**
 * The normalised text of an element and, for every character, the DOM position it came
 * from (so offsets can be turned back into a Range).
 */
export function textIndex(root) {
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */, {
    acceptNode: (node) =>
      node.parentElement?.closest("[data-study-ignore]") ? 2 /* REJECT */ : 1 /* ACCEPT */,
  });
  let text = "";
  const chars = [];
  let lastSpace = true;
  let lastParent = null;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = breakParent(node);
    if (lastParent && parent !== lastParent && !lastSpace) {
      text += " ";
      chars.push({ node, offset: 0 });
      lastSpace = true;
    }
    lastParent = parent;
    const value = node.nodeValue ?? "";
    for (let i = 0; i < value.length; i += 1) {
      if (/\s/.test(value[i])) {
        if (lastSpace) continue;
        text += " ";
        lastSpace = true;
      } else {
        text += value[i];
        lastSpace = false;
      }
      chars.push({ node, offset: i });
    }
  }
  if (text.endsWith(" ")) {
    text = text.slice(0, -1);
    chars.pop();
  }
  return { text, chars };
}

function occurrences(text, quote) {
  const out = [];
  let at = text.indexOf(quote);
  while (at !== -1) {
    out.push(at);
    at = text.indexOf(quote, at + 1);
  }
  return out;
}

function score(text, start, quote, prefix = "", suffix = "") {
  const before = text.slice(Math.max(0, start - CONTEXT), start);
  const after = text.slice(start + quote.length, start + quote.length + CONTEXT);
  let a = 0;
  while (a < Math.min(before.length, prefix.length) && before.at(-1 - a) === prefix.at(-1 - a))
    a += 1;
  let b = 0;
  while (b < Math.min(after.length, suffix.length) && after[b] === suffix[b]) b += 1;
  return a + b;
}

function toRange(doc, chars, start, end) {
  const first = chars[start];
  const last = chars[end - 1];
  if (!first || !last) return null;
  const range = doc.createRange();
  range.setStart(first.node, first.offset);
  range.setEnd(last.node, last.offset + 1);
  return range;
}

/** A DOM Range for a saved anchor inside ``root`` (the lesson article), or null. */
export function rangeForAnchor(root, anchor) {
  if (!anchor?.quote || !anchor.block) return null;
  const block = blockElement(root, anchor.block);
  if (!block) return null;
  const { text, chars } = textIndex(block);
  const starts = occurrences(text, anchor.quote);
  if (!starts.length) return null;
  const best = starts
    .map((s) => [score(text, s, anchor.quote, anchor.prefix, anchor.suffix), s])
    .sort((x, y) => y[0] - x[0])[0][1];
  return toRange(root.ownerDocument, chars, best, best + anchor.quote.length);
}

function charIndex(chars, container, offset) {
  // Index of the first character at or after the boundary point (container, offset).
  if (container.nodeType === 3) {
    let last = -1;
    for (let i = 0; i < chars.length; i += 1) {
      if (chars[i].node !== container) continue;
      if (chars[i].offset >= offset) return i;
      last = i;
    }
    if (last >= 0) return last + 1;
  }
  const doc = container.ownerDocument ?? container;
  const point = doc.createRange();
  point.setStart(container, offset);
  for (let i = 0; i < chars.length; i += 1) {
    const probe = doc.createRange();
    probe.setStart(chars[i].node, chars[i].offset);
    if (point.compareBoundaryPoints(0 /* START_TO_START */, probe) <= 0) return i;
  }
  return chars.length;
}

/**
 * Turn the current selection into an anchor. Returns {anchor} or {error} (a selection
 * outside the lesson text, or across several blocks).
 */
export function anchorFromSelection(selection, root) {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) return null;
  const startEl =
    range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
  const endEl =
    range.endContainer.nodeType === 1 ? range.endContainer : range.endContainer.parentElement;
  const block = startEl?.closest("[data-block-uid]");
  if (!block || block !== endEl?.closest("[data-block-uid]")) {
    return { error: "Select text within one paragraph or block." };
  }
  if (!block.hasAttribute("data-highlightable") || startEl.closest("[data-study-ignore]")) {
    return { error: "This part of the lesson can't be highlighted." };
  }
  const { text, chars } = textIndex(block);
  let start = charIndex(chars, range.startContainer, range.startOffset);
  let end = charIndex(chars, range.endContainer, range.endOffset);
  while (start < end && text[start] === " ") start += 1;
  while (end > start && text[end - 1] === " ") end -= 1;
  const quote = text.slice(start, end);
  if (!quote) return null;
  if (quote.length > 1000) return { error: "Choose a shorter passage (up to 1,000 characters)." };
  return {
    anchor: {
      block: block.getAttribute("data-block-uid"),
      quote,
      prefix: text.slice(Math.max(0, start - CONTEXT), start),
      suffix: text.slice(end, end + CONTEXT),
      start,
    },
    rect: range.getBoundingClientRect?.(),
  };
}

export const supportsHighlights = () =>
  typeof CSS !== "undefined" && "highlights" in CSS && typeof globalThis.Highlight === "function";

/** Paint highlights (grouped by colour) and an optional focused passage. */
export function paintHighlights(root, highlights, focusId) {
  if (!supportsHighlights() || !root) return () => {};
  const groups = Object.fromEntries(COLORS.map((c) => [c, []]));
  const focus = [];
  for (const item of highlights) {
    if (item.status === "orphaned" || !item.anchor || item.anchor.hidden) continue;
    const range = rangeForAnchor(root, item.anchor);
    if (!range) continue;
    groups[item.color]?.push(range);
    if (item.id === focusId) focus.push(range);
  }
  const names = [];
  for (const [color, ranges] of Object.entries(groups)) {
    const name = `tpa-hl-${color}`;
    CSS.highlights.set(name, new globalThis.Highlight(...ranges));
    names.push(name);
  }
  CSS.highlights.set("tpa-hl-focus", new globalThis.Highlight(...focus));
  names.push("tpa-hl-focus");
  return () => names.forEach((name) => CSS.highlights.delete(name));
}

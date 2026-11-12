import { isSafeInlineHref } from "@/utils/inlineLinks";

/**
 * Inline formatting in the plain-text block fields: **bold**, *italic* and [label](href).
 * Formatting pasted from Google Docs, Word or a web page is converted to those markers
 * (instead of being dropped by the textarea), and Ctrl/⌘+B / Ctrl/⌘+I wrap the selection.
 * Only text is produced; pasted HTML is read, never inserted.
 */

const BLOCK_TAGS = new Set(["P", "DIV", "LI", "H1", "H2", "H3", "H4", "H5", "H6", "TR", "BR"]);

function weightIsBold(style) {
  const weight = style?.fontWeight;
  if (!weight) return null;
  if (weight === "bold" || weight === "bolder") return true;
  const n = Number(weight);
  return Number.isFinite(n) ? n >= 600 : weight !== "normal" ? null : false;
}

/** Wrap text in markers, keeping surrounding spaces outside them ("** a **" never). */
function wrap(text, marker) {
  const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
  return match[2] ? `${match[1]}${marker}${match[2]}${marker}${match[3]}` : text;
}

function convert(node, inherited = { bold: false, italic: false }) {
  if (node.nodeType === 3) return node.textContent.replace(/\s+/g, " ");
  if (node.nodeType !== 1) return "";
  const tag = node.tagName;
  if (tag === "BR") return "\n";
  if (tag === "STYLE" || tag === "SCRIPT") return "";
  const bold =
    weightIsBold(node.style) ?? (tag === "B" || tag === "STRONG" ? true : inherited.bold);
  const italic =
    node.style?.fontStyle === "italic" || tag === "I" || tag === "EM"
      ? true
      : node.style?.fontStyle === "normal"
        ? false
        : inherited.italic;
  let text = [...node.childNodes].map((child) => convert(child, { bold, italic })).join("");
  if (tag === "A") {
    const href = node.getAttribute("href") ?? "";
    if (isSafeInlineHref(href) && text.trim() && !/[[\]\n]/.test(text))
      text = `[${text.trim()}](${href})`;
  }
  // Apply a mark where it starts (not again on every nested element).
  if (bold && !inherited.bold)
    text = text
      .split("\n")
      .map((t) => wrap(t, "**"))
      .join("\n");
  if (italic && !inherited.italic)
    text = text
      .split("\n")
      .map((t) => wrap(t, "*"))
      .join("\n");
  return BLOCK_TAGS.has(tag) ? `${text}\n` : text;
}

/** Pasted HTML as text with **bold**, *italic* and [label](href) markers. */
export function htmlToInline(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return convert(doc.body)
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function replaceSelection(target, insert, onValue) {
  const { selectionStart: start, selectionEnd: end, value } = target;
  onValue(value.slice(0, start) + insert + value.slice(end));
  const caret = start + insert.length;
  requestAnimationFrame(() => target.setSelectionRange?.(caret, caret));
}

/** onPaste / onKeyDown props for a block textarea; onValue receives the new text. */
export function inlineFormattingProps(onValue) {
  return {
    onPaste(event) {
      const html = event.clipboardData?.getData("text/html");
      if (!html || !/<(b|strong|i|em|a)[\s>]|font-weight|font-style/i.test(html)) return;
      const text = htmlToInline(html);
      if (!text) return;
      event.preventDefault();
      replaceSelection(event.target, text, onValue);
    },
    onKeyDown(event) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key !== "b" && key !== "i") return;
      const { selectionStart: start, selectionEnd: end, value } = event.target;
      if (start === end) return;
      event.preventDefault();
      replaceSelection(
        event.target,
        wrap(value.slice(start, end), key === "b" ? "**" : "*"),
        onValue,
      );
    },
  };
}

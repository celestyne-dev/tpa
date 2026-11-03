/**
 * Inline links in article text, written by editors as [label](href).
 *
 * Mirrors backend/app/cms/blocks.py: only site paths, https URLs and mailto: addresses
 * become links; anything else (javascript:, data:, http:, //host) stays plain text. The
 * text is split into strings and link parts, so nothing is ever rendered as HTML.
 */
const INLINE_LINK = /\[([^[\]\n]{1,200})\]\(([^()\s]{1,500})\)/g;

export function isSafeInlineHref(href) {
  if (typeof href !== "string") return false;
  if (href.startsWith("/")) return !href.startsWith("//") && !href.includes("\\");
  if (/^https:\/\/[^\s/]+/i.test(href)) return true;
  return /^mailto:[^@\s/?#]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$/.test(href);
}

/** [{ text } | { label, href }] parts of a text field, in order. */
export function parseInlineLinks(text) {
  const value = String(text ?? "");
  const parts = [];
  let last = 0;
  for (const match of value.matchAll(INLINE_LINK)) {
    const [whole, label, href] = match;
    if (!isSafeInlineHref(href)) continue;
    if (match.index > last) parts.push({ text: value.slice(last, match.index) });
    parts.push({ label, href });
    last = match.index + whole.length;
  }
  if (last < value.length) parts.push({ text: value.slice(last) });
  return parts;
}

/** The text as read aloud or indexed: [label](href) becomes label. */
export function stripInlineLinks(text) {
  return String(text ?? "").replace(INLINE_LINK, (_whole, label) => label);
}

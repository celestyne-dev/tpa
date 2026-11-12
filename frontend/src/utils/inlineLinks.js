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

// Inline emphasis: **bold** and *italic* (or _italic_, but not snake_case). Mirrors
// backend/app/cms/blocks.py. Parsed into parts and rendered as <strong>/<em> elements.
const BOLD = /\*\*(?=\S)([^\n]*?\S)\*\*/g;
const ITALIC =
  /(?<![*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\w])|(?<!\w)_(?=\S)([^_\n]*?\S)_(?!\w)/g;
const MAX_DEPTH = 4;

function nextMatch(pattern, value, from, accept) {
  pattern.lastIndex = from;
  let match;
  while ((match = pattern.exec(value))) {
    if (!accept || accept(match)) return match;
    pattern.lastIndex = match.index + 1;
  }
  return null;
}

/**
 * Text with links and emphasis as a tree of parts: { text } | { href, children } |
 * { strong: children } | { em: children }. Plain strings only, never HTML.
 */
export function parseInline(text, depth = 0) {
  const value = String(text ?? "");
  if (depth > MAX_DEPTH) return value ? [{ text: value }] : [];
  const parts = [];
  let pos = 0;
  while (pos < value.length) {
    const found = [
      ["link", nextMatch(INLINE_LINK, value, pos, (m) => isSafeInlineHref(m[2]))],
      ["strong", nextMatch(BOLD, value, pos)],
      ["em", nextMatch(ITALIC, value, pos)],
    ]
      .filter(([, m]) => m)
      .sort((a, b) => a[1].index - b[1].index);
    if (!found.length) break;
    const [kind, match] = found[0];
    if (match.index > pos) parts.push({ text: value.slice(pos, match.index) });
    if (kind === "link")
      parts.push({ href: match[2], label: match[1], children: parseInline(match[1], depth + 1) });
    else parts.push({ [kind]: parseInline(match[1] ?? match[2], depth + 1) });
    pos = match.index + match[0].length;
  }
  if (pos < value.length) parts.push({ text: value.slice(pos) });
  return parts;
}

/** The text as read aloud or indexed: [label](href) becomes label, emphasis markers go. */
export function stripInlineLinks(text) {
  return String(text ?? "")
    .replace(INLINE_LINK, (_whole, label) => label)
    .replace(BOLD, (_whole, inner) => inner)
    .replace(ITALIC, (_whole, star, underscore) => star ?? underscore);
}

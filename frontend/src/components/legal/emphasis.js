/**
 * Emphasis inside a text field, written by editors as **bold** or *italic*. The text is
 * split into strings and <strong>/<em> elements (never parsed as HTML). Unpaired markers
 * stay as written.
 */
const EMPHASIS = /(\*\*([^*\n]+?)\*\*|\*([^*\n]+?)\*)/g;

export function parseEmphasis(text) {
  const value = String(text ?? "");
  const parts = [];
  let last = 0;
  for (const match of value.matchAll(EMPHASIS)) {
    if (match.index > last) parts.push({ text: value.slice(last, match.index) });
    parts.push(match[2] ? { strong: match[2] } : { em: match[3] });
    last = match.index + match[0].length;
  }
  if (last < value.length) parts.push({ text: value.slice(last) });
  return parts;
}

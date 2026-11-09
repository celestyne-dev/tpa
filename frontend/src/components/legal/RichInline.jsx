import { Link } from "react-router";
import { parseInlineLinks } from "@/utils/inlineLinks";

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

function Emphasis({ text }) {
  return parseEmphasis(text).map((part, i) => {
    if (part.strong) return <strong key={i}>{part.strong}</strong>;
    if (part.em) return <em key={i}>{part.em}</em>;
    return part.text;
  });
}

/** Text with inline [label](href) links and **bold** / *italic* emphasis. */
export function RichInline({ text }) {
  return parseInlineLinks(text).map((part, i) => {
    if (!part.href) return <Emphasis key={i} text={part.text} />;
    if (part.href.startsWith("/"))
      return (
        <Link key={i} to={part.href}>
          {part.label}
        </Link>
      );
    return (
      <a
        key={i}
        href={part.href}
        rel={part.href.startsWith("mailto:") ? undefined : "noopener noreferrer"}
      >
        {part.label}
      </a>
    );
  });
}

import { Link } from "react-router";
import { parseInlineLinks } from "@/utils/inlineLinks";
import { parseEmphasis } from "./emphasis";

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

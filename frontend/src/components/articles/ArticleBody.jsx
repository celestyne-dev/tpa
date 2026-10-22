import { Info, Lightbulb, TriangleAlert } from "lucide-react";
import { cn, slugify } from "@/utils/format";

const calloutStyles = {
  info: { icon: Info, className: "border-sage-200 bg-sage-50" },
  tip: { icon: Lightbulb, className: "border-gold-300 bg-gold-100/60" },
  warning: { icon: TriangleAlert, className: "border-red-200 bg-red-50" },
};

/** Renders structured article blocks as semantic HTML (text only, no raw HTML injection). */
export function ArticleBody({ blocks }) {
  return (
    <div className="prose-tpa">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "paragraph":
            return <p key={index}>{block.text}</p>;
          case "heading": {
            const Heading = block.level === 3 ? "h3" : "h2";
            return (
              <Heading key={index} id={block.id ?? slugify(block.text)}>
                {block.text}
              </Heading>
            );
          }
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={index}>
                {block.items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </List>
            );
          }
          case "quote":
            return (
              <blockquote key={index}>
                <p>{block.text}</p>
                {block.cite && (
                  <footer className="mt-3 font-sans text-base text-muted not-italic">
                    — {block.cite}
                  </footer>
                )}
              </blockquote>
            );
          case "callout": {
            const style = calloutStyles[block.tone] ?? calloutStyles.info;
            const Icon = style.icon;
            return (
              <aside
                key={index}
                className={cn("flex gap-4 rounded-2xl border p-5 text-base", style.className)}
              >
                <Icon aria-hidden className="mt-1 size-5 shrink-0 text-charcoal" />
                <div>
                  {block.title && <p className="font-semibold text-charcoal">{block.title}</p>}
                  <p className={block.title ? "mt-1" : undefined}>{block.text}</p>
                </div>
              </aside>
            );
          }
          case "divider":
            return <hr key={index} className="mx-auto w-24 border-t-2 border-gold-300" />;
          default:
            return null;
        }
      })}
    </div>
  );
}

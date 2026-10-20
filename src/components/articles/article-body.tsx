import { slugify } from "@/lib/utils";
import type { ArticleBlock } from "@/types";

/** Renders structured article blocks as semantic HTML (no raw HTML injection). */
export function ArticleBody({ blocks }: { blocks: ArticleBlock[] }) {
  return (
    <div className="prose-tpa">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "paragraph":
            return <p key={index}>{block.text}</p>;
          case "heading":
            return (
              <h2 key={index} id={block.id ?? slugify(block.text)}>
                {block.text}
              </h2>
            );
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={index}>
                {block.items.map((item) => (
                  <li key={item}>{item}</li>
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
        }
      })}
    </div>
  );
}

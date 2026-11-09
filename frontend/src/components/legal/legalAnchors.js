import { routes } from "@/config/navigation";
import { slugify } from "@/utils/format";

/** The legal pages, used when the CMS footer has no "Legal" column to take them from. */
export const DEFAULT_LEGAL_LINKS = [
  { label: "Privacy Policy", href: routes.privacy },
  { label: "Terms of Use", href: routes.terms },
  { label: "Affiliate Disclosure", href: routes.affiliate },
];

/**
 * Gives every heading a unique, stable anchor (from its text, or the id an editor set) and
 * returns the table of contents built from them: level-2 headings, with level-3 headings
 * nested underneath.
 */
export function withAnchors(blocks = []) {
  const used = new Map();
  const toc = [];
  const out = blocks.map((block) => {
    if (block.type !== "heading") return block;
    const base = block.anchorId || block.id || slugify(block.text) || "section";
    const count = used.get(base) ?? 0;
    used.set(base, count + 1);
    const anchorId = count ? `${base}-${count + 1}` : base;
    const entry = { id: anchorId, text: block.text, children: [] };
    if (block.level === 3 && toc.length) toc[toc.length - 1].children.push(entry);
    else toc.push(entry);
    return { ...block, anchorId };
  });
  return { blocks: out, toc };
}

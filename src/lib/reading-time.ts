import type { ArticleBlock } from "@/types";

const WORDS_PER_MINUTE = 225;

export function countWords(blocks: ArticleBlock[]): number {
  return blocks.reduce((total, block) => {
    const text = block.type === "list" ? block.items.join(" ") : block.text;
    return total + text.trim().split(/\s+/).filter(Boolean).length;
  }, 0);
}

export function estimateReadingTime(blocks: ArticleBlock[]): number {
  return Math.max(1, Math.round(countWords(blocks) / WORDS_PER_MINUTE));
}

import { createContext, useContext } from "react";
import { isDark } from "./design";

/**
 * Per-section rendering context: design tokens, heading level, image priority, whether
 * this is an admin preview (empty sections then explain themselves instead of
 * disappearing) and `compact`: the homepage's tighter editorial rhythm (smaller hero,
 * shorter cards, less padding). Other pages that use the same sections are unchanged.
 */
export const SectionContext = createContext({
  dark: false,
  design: {},
  level: 2,
  first: false,
  preview: false,
  compact: false,
});
export const useSectionContext = () => useContext(SectionContext);

export function sectionContextValue(
  section,
  { level = 2, first = false, preview = false, compact = false } = {},
) {
  const design = section.design ?? {};
  return { design, dark: isDark(design.background), level, first, preview, compact };
}

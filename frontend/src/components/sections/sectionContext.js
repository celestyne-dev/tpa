import { createContext, useContext } from "react";
import { isDark } from "./design";

/**
 * Per-section rendering context: design tokens, heading level, image priority and
 * whether this is an admin preview (empty sections then explain themselves instead of
 * disappearing).
 */
export const SectionContext = createContext({
  dark: false,
  design: {},
  level: 2,
  first: false,
  preview: false,
});
export const useSectionContext = () => useContext(SectionContext);

export function sectionContextValue(section, { level = 2, first = false, preview = false } = {}) {
  const design = section.design ?? {};
  return { design, dark: isDark(design.background), level, first, preview };
}

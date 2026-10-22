import { createContext, useContext } from "react";
import { isDark } from "./design";

/** Per-section rendering context: design tokens, heading level and image priority. */
export const SectionContext = createContext({ dark: false, design: {}, level: 2, first: false });
export const useSectionContext = () => useContext(SectionContext);

export function sectionContextValue(section, { level = 2, first = false } = {}) {
  const design = section.design ?? {};
  return { design, dark: isDark(design.background), level, first };
}

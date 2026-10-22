import { SECTION_COMPONENTS, TITLE_SECTIONS } from "./registry";
import { SectionContext, sectionContextValue } from "./sectionContext";

/**
 * Renders a resolved CMS page's sections in order. The first hero or page
 * header becomes the page's h1; when there is none, a visually hidden h1 with
 * the page title keeps the heading outline valid. Only the first section may
 * load its image eagerly (the likely LCP element).
 */
export function SectionList({ page, preview = false }) {
  const sections = page?.sections ?? [];
  const titleIndex = sections.findIndex((s) => TITLE_SECTIONS.has(s.type));
  return (
    <>
      {titleIndex === -1 && page?.title && <h1 className="sr-only">{page.title}</h1>}
      {sections.map((section, index) => {
        const Component = SECTION_COMPONENTS[section.type];
        if (!Component) return null;
        const value = sectionContextValue(section, {
          level: index === titleIndex ? 1 : 2,
          first: index === 0,
        });
        return (
          <SectionContext.Provider key={section.key} value={value}>
            {preview && section.preview_note && (
              <p className="bg-gold-100 px-5 py-2 text-center text-sm text-charcoal" role="note">
                {section.preview_note}
              </p>
            )}
            <Component section={section} page={page} />
          </SectionContext.Provider>
        );
      })}
    </>
  );
}

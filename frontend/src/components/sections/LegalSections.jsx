import { LegalDocument } from "@/components/legal/LegalDocument";
import { DEVICES } from "./design";
import { useSectionContext } from "./sectionContext";

/**
 * CMS "Legal document" section: the same layout as the built-in legal pages, so a policy
 * moved into the CMS looks exactly as before. Breadcrumbs follow the page's place in the
 * site; the title falls back to the page title.
 */
export function LegalDocumentSection({ section, page }) {
  const { data } = section;
  const { level } = useSectionContext();
  const title = data.heading || page?.title || "";
  const path = page?.path;
  const breadcrumbs = (page?.breadcrumbs ?? []).length
    ? page.breadcrumbs.map((c) => ({ name: c.name, href: c.path }))
    : undefined;
  return (
    <section
      data-section="legal_document"
      className={DEVICES[section.devices ?? "all"] || undefined}
    >
      <LegalDocument
        title={title}
        eyebrow={data.eyebrow ?? "Legal"}
        summary={data.summary}
        effectiveDate={data.effective_date}
        lastUpdated={data.last_updated}
        notice={data.notice ? { title: data.notice_title, text: data.notice } : null}
        blocks={data.body ?? []}
        path={path}
        breadcrumbs={breadcrumbs}
        headingLevel={level}
        showToc={data.show_toc !== false}
        showRelated={data.show_related !== false}
      />
    </section>
  );
}

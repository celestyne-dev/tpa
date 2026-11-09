import { Seo } from "@/components/seo/Seo";
import { webPageJsonLd } from "@/utils/structuredData";
import { LegalDocument } from "./LegalDocument";

/**
 * The built-in legal pages. Their wording lives in data/legal/legalDocuments.json (kept
 * identical to the CMS "Legal document" templates in backend/app/cms/legal_documents.json,
 * which a backend test checks), so publishing a CMS page created from a legal template
 * reproduces the page exactly and then lets editors manage it in the CMS.
 */
export function LegalPage({ doc, draft = false }) {
  // Pending legal review (every document until it is approved): readable, but not indexed,
  // not in the sitemap and not presented as in effect.
  const pending = draft || doc.review_status === "pending_review";
  return (
    <>
      <Seo
        title={doc.seo_title ?? doc.title}
        description={doc.meta_description ?? doc.summary}
        path={doc.path}
        noIndex={pending}
        jsonLd={pending ? undefined : webPageJsonLd({ title: doc.title, path: doc.path })}
      />
      <LegalDocument
        title={doc.title}
        summary={doc.summary}
        effectiveDate={doc.effective_date}
        lastUpdated={doc.last_updated}
        notice={doc.notice}
        blocks={doc.body}
        path={doc.path}
        pendingReview={pending}
      />
    </>
  );
}

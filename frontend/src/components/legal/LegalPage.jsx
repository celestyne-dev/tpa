import { Seo } from "@/components/seo/Seo";
import legalDocuments from "@/data/legal/legalDocuments.json";
import { webPageJsonLd } from "@/utils/structuredData";
import { LegalDocument } from "./LegalDocument";

/**
 * The built-in legal pages. Their wording lives in data/legal/legalDocuments.json (kept
 * identical to the CMS "Legal document" templates in backend/app/cms/legal_documents.json,
 * which a backend test checks), so publishing a CMS page created from a legal template
 * reproduces the page exactly and then lets editors manage it in the CMS.
 */
export function LegalPage({ doc }) {
  return (
    <>
      <Seo
        title={doc.title}
        description={doc.meta_description ?? doc.summary}
        path={doc.path}
        jsonLd={webPageJsonLd({ title: doc.title, path: doc.path })}
      />
      <LegalDocument
        title={doc.title}
        summary={doc.summary}
        effectiveDate={doc.effective_date}
        lastUpdated={doc.last_updated}
        notice={doc.notice}
        blocks={doc.body}
        path={doc.path}
      />
    </>
  );
}

export const legalDocs = legalDocuments;

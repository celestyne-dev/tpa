import { LegalPage } from "@/components/legal/LegalPage";
import legalDocs from "@/data/legal/legalDocuments.json";

export function TermsPage() {
  return <LegalPage doc={legalDocs.terms} />;
}

import { LegalPage, legalDocs } from "@/components/legal/LegalPage";

export function TermsPage() {
  return <LegalPage doc={legalDocs.terms} />;
}

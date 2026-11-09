import { LegalPage } from "@/components/legal/LegalPage";
import legalDocs from "@/data/legal/legalDocuments.json";

export function AffiliateDisclosurePage() {
  return <LegalPage doc={legalDocs.affiliate} />;
}

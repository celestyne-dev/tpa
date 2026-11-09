import { LegalPage } from "@/components/legal/LegalPage";
import legalDocs from "@/data/legal/legalDocuments.json";

export function PrivacyPolicyPage() {
  return <LegalPage doc={legalDocs.privacy} />;
}

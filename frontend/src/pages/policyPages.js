import { createElement } from "react";
import { LegalPage } from "@/components/legal/LegalPage";
import legalDocs from "@/data/legal/legalDocuments.json";

/**
 * A built-in policy page (Cookie Policy, Editorial Policy, …): the draft wording from
 * data/legal/legalDocuments.json, shown with "noindex" until the matching CMS template is
 * reviewed and published at the same address, which then replaces this page.
 */
export function policyPage(key) {
  const doc = legalDocs[key];
  function BuiltInPolicyPage() {
    return createElement(LegalPage, { doc, draft: true });
  }
  BuiltInPolicyPage.displayName = `PolicyPage(${key})`;
  return BuiltInPolicyPage;
}

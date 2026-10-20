import type { Metadata } from "next";
import { ContactSentence, LegalPage } from "@/components/legal/legal-page";
import { routes } from "@/config/navigation";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Affiliate Disclosure",
  description:
    "How Think Positive Always discloses affiliate links, sponsored content, and brand partnerships.",
  path: routes.affiliate,
});

export default function AffiliateDisclosurePage() {
  return (
    <LegalPage
      title="Affiliate Disclosure"
      path={routes.affiliate}
      description="Our commitment to transparency about affiliate links and sponsored content."
      lastUpdated="2026-10-20"
    >
      <h2>Our approach</h2>
      <p>
        Think Positive Always may, in the future, include affiliate links and sponsored content. We
        want you to always know when a commercial relationship exists, so you can make informed
        decisions.
      </p>

      <h2>Affiliate links</h2>
      <p>
        Some links on this website may be affiliate links. If you click an affiliate link and make a
        purchase, we may earn a commission at no additional cost to you. We will only recommend
        products or services we believe may be genuinely useful to our readers.
      </p>

      <h2>Sponsored content and partnerships</h2>
      <p>
        When content is sponsored or created in partnership with a brand, it will be clearly
        labelled. Sponsorship does not guarantee a positive review, and our editorial opinions
        remain our own.
      </p>

      <h2>Current status</h2>
      <p>
        At the time of this draft, the website does not contain affiliate links or sponsored
        content. This disclosure will be kept up to date as these programmes begin.
      </p>

      <h2>Regulatory guidance</h2>
      <p>
        We aim to follow applicable disclosure guidance, including the U.S. Federal Trade
        Commission&apos;s guidance on endorsements and testimonials.
      </p>

      <h2>Questions</h2>
      <ContactSentence />
    </LegalPage>
  );
}

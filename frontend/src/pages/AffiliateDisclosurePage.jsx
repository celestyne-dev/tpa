import { ContactSentence, LegalPage } from "@/components/legal/LegalPage";
import { routes } from "@/config/navigation";

export function AffiliateDisclosurePage() {
  return (
    <LegalPage
      title="Affiliate Disclosure"
      path={routes.affiliate}
      description="Our commitment to transparency about affiliate links and sponsored content."
      metaDescription="How Think Positive Always discloses affiliate links, sponsored content, and brand partnerships."
      lastUpdated="2026-10-26"
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

      <h2>Where you will see disclosures</h2>
      <p>
        Pages with affiliate recommendations show a disclosure next to those recommendations, and
        sponsored articles, banners and newsletter editions are labelled “Sponsored” with the
        sponsor’s name. Paid and affiliate links are marked as sponsored links for search engines.
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

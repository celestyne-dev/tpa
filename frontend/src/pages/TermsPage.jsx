import { ContactSentence, LegalPage } from "@/components/legal/LegalPage";
import { routes } from "@/config/navigation";

export function TermsPage() {
  return (
    <LegalPage
      title="Terms of Use"
      path={routes.terms}
      description="The terms that apply when you use this website and its content."
      metaDescription="The terms that apply when you use the Think Positive Always website and content."
      lastUpdated="2026-10-20"
    >
      <h2>1. Acceptance of these terms</h2>
      <p>
        By accessing or using the Think Positive Always website, you agree to these Terms of Use. If
        you do not agree, please do not use the website.
      </p>

      <h2>2. Educational and inspirational content</h2>
      <p>
        Content on this website is provided for general informational, educational, and
        inspirational purposes only. It is not medical, psychological, legal, financial, or other
        professional advice, and it is not a substitute for care from a qualified professional. If
        you are experiencing a crisis or are concerned about your mental health, please contact a
        licensed professional or your local emergency services.
      </p>

      <h2>3. Intellectual property</h2>
      <p>
        Unless otherwise stated, the content on this website, including text, graphics, logos, and
        design, belongs to Think Positive Always and is protected by applicable intellectual
        property laws. You may share links to our content and quote brief excerpts with clear
        attribution. Please do not reproduce, republish, or sell our content without written
        permission.
      </p>

      <h2>4. Acceptable use</h2>
      <ul>
        <li>Do not use the website in any way that is unlawful or harmful.</li>
        <li>Do not attempt to disrupt, damage, or gain unauthorised access to the website.</li>
        <li>Do not use automated means to copy content at scale without permission.</li>
      </ul>

      <h2>5. Digital products and services</h2>
      <p>
        Digital products, accounts, and paid services are not yet available. Specific terms for
        purchases, downloads, licensing, and refunds will be published before these features launch.
      </p>

      <h2>6. Third-party links</h2>
      <p>
        The website may link to third-party websites. We are not responsible for the content,
        policies, or practices of those websites.
      </p>

      <h2>7. Disclaimer and limitation of liability</h2>
      <p>
        The website is provided on an &quot;as is&quot; and &quot;as available&quot; basis. To the
        fullest extent permitted by law, we make no warranties about the website and are not liable
        for losses arising from your use of it.
      </p>

      <h2>8. Changes</h2>
      <p>
        We may update these terms from time to time. Continued use of the website after changes are
        posted means you accept the updated terms.
      </p>

      <h2>9. Contact</h2>
      <ContactSentence />
    </LegalPage>
  );
}

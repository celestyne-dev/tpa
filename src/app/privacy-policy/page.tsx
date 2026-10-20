import type { Metadata } from "next";
import { ContactSentence, LegalPage } from "@/components/legal/legal-page";
import { routes } from "@/config/navigation";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Privacy Policy",
  description: "How Think Positive Always handles information when you visit and use this website.",
  path: routes.privacy,
});

export default function PrivacyPolicyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      path={routes.privacy}
      description="How we handle information when you visit and use this website."
      lastUpdated="2026-10-20"
    >
      <h2>1. Who we are</h2>
      <p>
        This website is operated by Think Positive Always (&quot;Think Positive Always&quot;,
        &quot;we&quot;, &quot;us&quot;). Full legal entity and contact details will be added to this
        policy before commercial services launch.
      </p>

      <h2>2. Information we collect today</h2>
      <p>
        At this stage, the website does not offer accounts, purchases, contact forms, or newsletter
        sign-ups, and we do not ask you to submit personal information through the site.
      </p>
      <p>
        Like most websites, our hosting provider may automatically process limited technical
        information when you visit, such as your IP address, browser type, device information, and
        the pages you request. This is used to deliver the website securely and reliably.
      </p>

      <h2>3. Information we may collect in the future</h2>
      <p>As we introduce new features, we may collect:</p>
      <ul>
        <li>Your email address if you subscribe to our newsletter.</li>
        <li>Account details if you create a customer account.</li>
        <li>
          Order information for digital product purchases. Payment details will be handled by a
          verified third-party payment provider; we do not intend to store full card details.
        </li>
        <li>Messages you choose to send us.</li>
        <li>Website usage analytics to help us improve content and performance.</li>
      </ul>
      <p>This policy will be updated to describe each feature before it goes live.</p>

      <h2>4. Cookies</h2>
      <p>
        The website does not currently use advertising or analytics cookies. If we introduce cookies
        or similar technologies, we will update this policy and, where required, request your
        consent.
      </p>

      <h2>5. How we use information</h2>
      <ul>
        <li>To operate, secure, and maintain the website.</li>
        <li>To provide services you request, such as newsletters or downloads, once available.</li>
        <li>To understand how the website is used so we can improve it.</li>
        <li>To comply with legal obligations.</li>
      </ul>

      <h2>6. Sharing information</h2>
      <p>
        We do not sell personal information. We may share information with service providers who
        help us operate the website (for example, hosting, email, or payment providers), only as
        needed to provide their services.
      </p>

      <h2>7. Your rights</h2>
      <p>
        Depending on where you live, you may have rights to access, correct, delete, or restrict the
        use of your personal information. Details on how to exercise these rights will be provided
        here once contact channels are published.
      </p>

      <h2>8. Children</h2>
      <p>
        This website is intended for adults and is not directed at children under 13. We do not
        knowingly collect personal information from children.
      </p>

      <h2>9. Changes to this policy</h2>
      <p>
        We will update this policy as the website develops. The &quot;Last updated&quot; date above
        shows when it was last revised.
      </p>

      <h2>10. Contact</h2>
      <ContactSentence />
    </LegalPage>
  );
}

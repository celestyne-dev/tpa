import { ArrowRight, Handshake, Mail, MessageCircle } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { buttonStyles } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/draft-notice";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { socialLinks } from "@/config/social";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Contact Think Positive Always",
  description:
    "Find the best way to get in touch with Think Positive Always for general questions, partnerships, and collaborations.",
  path: routes.contact,
});

export default function ContactPage() {
  const { email, partnershipsEmail } = siteConfig.contact;
  const hasDirectContact = Boolean(email) || socialLinks.length > 0;

  return (
    <>
      <PageHeader
        eyebrow="Contact"
        title="Get in Touch"
        description="We would love to hear from you. Here are the best ways to reach Think Positive Always."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Contact", href: routes.contact },
        ]}
      />

      <Section>
        <div className="grid gap-8 lg:grid-cols-3">
          <Card className="flex flex-col p-8 lg:col-span-2">
            <span className="grid size-12 place-items-center rounded-xl bg-sage-100 text-sage-700">
              <MessageCircle aria-hidden className="size-5" />
            </span>
            <h2 className="mt-6 text-3xl font-medium">General inquiries</h2>

            {email && (
              <div className="mt-5">
                <p className="text-muted">For questions, feedback, or support, email us at:</p>
                <a
                  href={`mailto:${email}`}
                  className={buttonStyles({ className: "mt-5", variant: "primary" })}
                >
                  <Mail aria-hidden />
                  {email}
                </a>
              </div>
            )}

            {socialLinks.length > 0 && (
              <div className="mt-8">
                <h3 className="font-sans text-sm font-semibold tracking-[0.14em] text-charcoal uppercase">
                  Connect on social media
                </h3>
                <ul className="mt-4 flex flex-wrap gap-3">
                  {socialLinks.map((link) => (
                    <li key={link.platform}>
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={buttonStyles({ variant: "outline", size: "sm" })}
                      >
                        {link.label}
                        <span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!hasDirectContact && (
              <div className="mt-6">
                <Notice title="Contact details coming soon">
                  We are setting up dedicated contact channels for the new website. They will be
                  published on this page shortly. Thank you for your patience.
                </Notice>
              </div>
            )}
          </Card>

          <Card tone="cream" className="flex flex-col p-8">
            <span className="grid size-12 place-items-center rounded-xl bg-ivory text-sage-700">
              <Handshake aria-hidden className="size-5" />
            </span>
            <h2 className="mt-6 text-2xl font-medium">Brands &amp; partnerships</h2>
            <p className="mt-3 flex-1 text-muted">
              Interested in collaborating with Think Positive Always? Learn about partnership
              formats and how to make an inquiry.
            </p>
            {partnershipsEmail && partnershipsEmail !== email && (
              <a
                href={`mailto:${partnershipsEmail}`}
                className="mt-4 font-medium text-sage-700 underline underline-offset-4"
              >
                {partnershipsEmail}
              </a>
            )}
            <Link
              href={routes.partner}
              className={buttonStyles({ variant: "outline", className: "mt-6 self-start" })}
            >
              Partner with us
              <ArrowRight aria-hidden />
            </Link>
          </Card>
        </div>
      </Section>

      <Section tone="cream" size="narrow" spacing="sm" aria-labelledby="support-heading">
        <h2 id="support-heading" className="text-2xl font-medium">
          Need urgent support?
        </h2>
        <p className="mt-3 text-muted">
          Think Positive Always is not a crisis or counselling service. If you are in immediate
          danger or need urgent emotional support, please contact your local emergency services or a
          licensed mental health professional. In the United States, you can call or text 988 to
          reach the 988 Suicide &amp; Crisis Lifeline.
        </p>
      </Section>
    </>
  );
}

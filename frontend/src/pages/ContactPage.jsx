import { ArrowRight, Handshake, Mail, MessageCircle } from "lucide-react";
import { Link } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { Skeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useSite } from "@/hooks/useContent";
import { webPageJsonLd } from "@/utils/structuredData";

export function ContactPage() {
  const { data: site, isLoading } = useSite();
  const email = site?.contact?.email;
  const partnershipsEmail = site?.contact?.partnerships_email;
  const socialLinks = site?.social_links ?? [];
  const hasDirectContact = Boolean(email) || socialLinks.length > 0;

  return (
    <>
      <Seo
        title="Contact Think Positive Always"
        description="Find the best way to get in touch with Think Positive Always for general questions, partnerships, and collaborations."
        path={routes.contact}
        jsonLd={webPageJsonLd({ title: "Contact Think Positive Always", path: routes.contact })}
      />
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
          <div className="flex flex-col rounded-[1.75rem] border border-charcoal/10 bg-white/60 p-7 sm:p-10 lg:col-span-2">
            <span className="grid size-12 place-items-center rounded-full bg-sage-100 text-sage-700">
              <MessageCircle aria-hidden className="size-5" />
            </span>
            <h2 className="mt-6 text-3xl font-medium">General inquiries</h2>

            {isLoading && <Skeleton className="mt-6 h-12 w-64" />}

            {email && (
              <div className="mt-5">
                <p className="text-muted">For questions, feedback, or support, email us at:</p>
                <a href={`mailto:${email}`} className={buttonStyles({ className: "mt-5" })}>
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

            {!isLoading && !hasDirectContact && (
              <div className="mt-6">
                <Notice title="Contact details coming soon">
                  We are setting up dedicated contact channels for the new website. They will be
                  published on this page shortly. Thank you for your patience.
                </Notice>
              </div>
            )}
          </div>

          <div className="flex flex-col rounded-[1.75rem] bg-sage-800 p-7 text-ivory sm:p-10">
            <span className="grid size-12 place-items-center rounded-full bg-ivory/10 text-gold-300">
              <Handshake aria-hidden className="size-5" />
            </span>
            <h2 className="mt-6 text-2xl font-medium text-ivory">Brands &amp; partnerships</h2>
            <p className="mt-3 flex-1 text-sage-100">
              Interested in collaborating with Think Positive Always? Learn about partnership
              formats and how to make an inquiry.
            </p>
            {partnershipsEmail && partnershipsEmail !== email && (
              <a
                href={`mailto:${partnershipsEmail}`}
                className="mt-4 font-medium break-all text-gold-300 underline underline-offset-4"
              >
                {partnershipsEmail}
              </a>
            )}
            <Link
              to={routes.partner}
              className={buttonStyles({ variant: "light", className: "mt-6 self-start" })}
            >
              Partner with us
              <ArrowRight aria-hidden />
            </Link>
          </div>
        </div>
        <aside
          aria-labelledby="support-heading"
          className="mt-8 rounded-[1.75rem] border border-charcoal/10 border-l-4 border-l-gold-400 bg-cream p-7 sm:p-10"
        >
          <h2 id="support-heading" className="text-2xl font-medium">
            Need urgent support?
          </h2>
          <p className="mt-3 max-w-3xl text-muted">
            Think Positive Always is not a crisis or counselling service. If you are in immediate
            danger or need urgent emotional support, please contact your local emergency services or
            a licensed mental health professional. In the United States, you can call or text 988 to
            reach the 988 Suicide &amp; Crisis Lifeline.
          </p>
        </aside>
      </Section>
    </>
  );
}

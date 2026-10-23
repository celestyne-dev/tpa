import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { Seo } from "@/components/seo/Seo";
import { IconFeature } from "@/components/ui/IconFeature";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { newsletterInside } from "@/data/marketing";

export function NewsletterPage() {
  return (
    <>
      <Seo
        title="The Positive Reset — Weekly Newsletter"
        description="The Positive Reset is Think Positive Always' weekly email: one thoughtful message to help you reset your mindset, find perspective, and keep moving forward."
        path={routes.newsletter}
      />
      <PageHeader
        eyebrow="Weekly newsletter"
        title={siteConfig.newsletterName}
        description="One thoughtful email each week to help you reset your mindset, find perspective, and keep moving forward."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Newsletter", href: routes.newsletter },
        ]}
      />

      <Section aria-labelledby="inside-heading">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.5fr] lg:gap-20">
          <div>
            <SectionHeading
              id="inside-heading"
              title="What you will find inside"
              description="Each issue is short enough to read over a cup of coffee, and meaningful enough to stay with you through the week."
            />
            <dl className="mt-10 grid grid-cols-2 gap-6 border-t border-charcoal/10 pt-8">
              <div>
                <dt className="text-sm text-muted">Cadence</dt>
                <dd className="mt-1 font-serif text-2xl text-charcoal">Once a week</dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Cost</dt>
                <dd className="mt-1 font-serif text-2xl text-charcoal">Free</dd>
              </div>
            </dl>
          </div>
          <ul className="grid gap-10 sm:grid-cols-2">
            {newsletterInside.map((item) => (
              <li key={item.title}>
                <IconFeature icon={item.icon} title={item.title} className="flex-col">
                  {item.text}
                </IconFeature>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section spacing="sm" size="wide" aria-label="Subscription status">
        <NewsletterPanel showLearnMore={false} source="newsletter_page" />
      </Section>

      <Section tone="cream" size="narrow" aria-labelledby="promise-heading">
        <h2 id="promise-heading" className="text-3xl font-medium">
          Our promise to readers
        </h2>
        <ul className="prose-legal mt-6">
          <li>We will only send what we said we would send: one thoughtful email each week.</li>
          <li>We will never sell your email address.</li>
          <li>Every email will include a simple way to unsubscribe.</li>
        </ul>
      </Section>
    </>
  );
}

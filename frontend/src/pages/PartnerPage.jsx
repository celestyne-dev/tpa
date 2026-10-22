import { FileText, Mail, Users } from "lucide-react";
import { Seo } from "@/components/seo/Seo";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Card } from "@/components/ui/Card";
import { IconFeature } from "@/components/ui/IconFeature";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { brandAlignment, partnershipFormats } from "@/data/marketing";
import { useSite } from "@/hooks/useContent";

export function PartnerPage() {
  const { data: site } = useSite();
  const email = site?.contact?.partnerships_email;
  const linkedin = site?.social_links?.find((s) => s.platform === "linkedin");
  const mediaKitUrl = site?.media_kit_url;

  return (
    <>
      <Seo
        title="Partner With Us — Brand Partnerships & Collaborations"
        description="Collaborate with Think Positive Always on sponsored content, brand storytelling, newsletter sponsorships, and purpose-driven campaigns for a personal growth audience."
        path={routes.partner}
      />
      <PageHeader
        eyebrow="Partnerships"
        title="Partner With Think Positive Always"
        description="We collaborate with brands, organisations, and publishers who share our belief that encouragement and practical tools can help people live better lives."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Partner With Us", href: routes.partner },
        ]}
      />

      <Section aria-labelledby="audience-heading">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
          <div>
            <SectionHeading
              id="audience-heading"
              eyebrow="Our audience"
              title="A community that values growth"
            />
            <div className="mt-6 space-y-5 text-lg text-muted">
              <p>
                Think Positive Always speaks to an international, primarily English-speaking
                audience, including readers across the United States. Our community is made up of
                adults of all genders who are interested in mindset, confidence, resilience,
                relationships, and intentional living.
              </p>
              <p>
                They come to us for encouragement and practical perspective, which is why we only
                partner on messages we believe will be genuinely useful to them.
              </p>
            </div>
          </div>
          <Card tone="cream" className="p-8 sm:p-10">
            <span className="grid size-12 place-items-center rounded-xl bg-sage-700 text-ivory">
              <Users aria-hidden className="size-5" />
            </span>
            <p className="mt-6 font-serif text-6xl font-medium text-charcoal">
              {site?.community?.linkedin_followers_label ?? "280,000+"}
            </p>
            <p className="mt-3 text-lg text-muted">
              followers on LinkedIn, alongside audiences on other social platforms.
            </p>
            <p className="mt-6 text-sm text-muted">
              Detailed, verified audience insights will be shared directly with prospective partners
              on request.
            </p>
          </Card>
        </div>
      </Section>

      <Section tone="cream" aria-labelledby="formats-heading">
        <SectionHeading
          id="formats-heading"
          eyebrow="Campaign formats"
          title="Ways we can work together"
          description="Every collaboration is shaped around shared goals. These are some of the formats we can explore."
        />
        <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {partnershipFormats.map((f) => (
            <li key={f.title}>
              <Card className="h-full p-7">
                <IconFeature icon={f.icon} title={f.title} className="flex-col">
                  {f.text}
                </IconFeature>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section aria-labelledby="alignment-heading">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-20">
          <SectionHeading
            id="alignment-heading"
            eyebrow="Brand alignment"
            title="Partnerships built on shared values"
            description="Our readers' trust comes first. We look for partners whose work fits naturally with what Think Positive Always stands for."
          />
          <ul className="space-y-4">
            {brandAlignment.map((item) => (
              <li key={item} className="flex gap-4 rounded-2xl bg-sage-50 p-5">
                <span aria-hidden className="mt-2.5 size-2 shrink-0 rounded-full bg-gold-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section tone="beige" aria-labelledby="media-kit-heading">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <span className="grid size-12 place-items-center rounded-xl bg-ivory text-sage-700">
              <FileText aria-hidden className="size-5" />
            </span>
            <h2 id="media-kit-heading" className="mt-6 text-3xl font-medium sm:text-4xl">
              Media kit
            </h2>
            {mediaKitUrl ? (
              <p className="mt-4 text-lg text-muted">
                <a
                  href={mediaKitUrl}
                  className="font-medium text-sage-700 underline underline-offset-4"
                >
                  Download the Think Positive Always media kit
                </a>
              </p>
            ) : (
              <p className="mt-4 text-lg text-muted">
                Our media kit is being prepared. It will include an overview of the brand, our
                content focus, audience information, and partnership formats. Until it is published,
                we are happy to share relevant details directly with prospective partners.
              </p>
            )}
          </div>

          <div className="rounded-[var(--radius-card)] bg-ivory p-8 shadow-soft sm:p-10">
            <h2 className="text-2xl font-medium">How to make an inquiry</h2>
            <ol className="mt-5 list-decimal space-y-3 pl-5 text-ink marker:text-sage-700">
              <li>Introduce your brand or organisation and what you do.</li>
              <li>Describe the campaign or collaboration you have in mind.</li>
              <li>Share your goals, preferred timeline, and any key requirements.</li>
            </ol>
            {email ? (
              <a
                href={`mailto:${email}?subject=${encodeURIComponent("Partnership inquiry")}`}
                className={buttonStyles({ className: "mt-8" })}
              >
                <Mail aria-hidden />
                Email {email}
              </a>
            ) : linkedin ? (
              <p className="mt-8 text-muted">
                Please send your inquiry via{" "}
                <a
                  href={linkedin.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-sage-700 underline underline-offset-4"
                >
                  Think Positive Always on LinkedIn
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
                .
              </p>
            ) : (
              <div className="mt-8">
                <Notice title="Inquiry channel coming soon">
                  A dedicated partnerships contact will be published here shortly. Thank you for
                  your interest. Please check back soon.
                </Notice>
              </div>
            )}
          </div>
        </div>
      </Section>
    </>
  );
}

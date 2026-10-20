import {
  FileText,
  Handshake,
  Megaphone,
  Newspaper,
  PenTool,
  Mail,
  Users,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import { buttonStyles } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/draft-notice";
import { IconFeature } from "@/components/ui/icon-feature";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { socialLinks } from "@/config/social";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Partner With Us — Brand Partnerships & Collaborations",
  description:
    "Collaborate with Think Positive Always on sponsored content, brand storytelling, newsletter sponsorships, and purpose-driven campaigns for a personal growth audience.",
  path: routes.partner,
});

const formats = [
  {
    icon: PenTool,
    title: "Sponsored content",
    text: "Thoughtful articles and posts that share your message in a way that genuinely serves our readers.",
  },
  {
    icon: Sparkles,
    title: "Brand storytelling",
    text: "Collaborative stories that connect your brand's purpose with themes of growth, resilience, and well-being.",
  },
  {
    icon: Megaphone,
    title: "Digital campaigns",
    text: "Multi-channel campaigns designed around a shared goal, from awareness to community engagement.",
  },
  {
    icon: Newspaper,
    title: "Newsletter sponsorships",
    text: "Placement in The Positive Reset, our weekly email, once the newsletter has launched.",
  },
  {
    icon: Handshake,
    title: "Resource partnerships",
    text: "Co-created guides, challenges, or tools that offer real value to people investing in their growth.",
  },
];

const alignment = [
  "Products, services, or causes that support well-being, growth, learning, or positive change.",
  "A commitment to honest claims and respectful, inclusive messaging.",
  "Respect for our audience: no misleading offers, pressure tactics, or harmful products.",
  "Willingness to clearly disclose sponsored and affiliate relationships.",
];

export default function PartnerPage() {
  const linkedin = socialLinks.find((s) => s.platform === "linkedin");
  const email = siteConfig.contact.partnershipsEmail;

  return (
    <>
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
              {siteConfig.community.linkedinFollowersLabel}
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
          {formats.map((f) => (
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
          <div>
            <SectionHeading
              id="alignment-heading"
              eyebrow="Brand alignment"
              title="Partnerships built on shared values"
              description="Our readers' trust comes first. We look for partners whose work fits naturally with what Think Positive Always stands for."
            />
          </div>
          <ul className="space-y-4">
            {alignment.map((item) => (
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
            {siteConfig.mediaKitUrl ? (
              <p className="mt-4 text-lg text-muted">
                <a
                  href={siteConfig.mediaKitUrl}
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
                <Mail aria-hidden className="size-4" />
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

import { ArrowRight, Check, Download, FileText, Mail, Users } from "lucide-react";
import {
  ActionLink,
  CompanyHero,
  CtaBand,
  IconCard,
  MetricCards,
} from "@/components/company/CompanyUI";
import { useHashScroll } from "@/components/company/useHashScroll";
import { PartnershipInquiryForm } from "@/components/partnerships/PartnershipInquiryForm";
import { formatMeasurement } from "@/components/partnerships/partnershipOptions";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import {
  brandAlignment,
  metricsNote,
  partnerAudience,
  partnerIntro,
  partnerReasons,
  partnershipFormats,
} from "@/data/companyPages";
import { useMediaKit, useSite } from "@/hooks/useContent";
import { formatDate } from "@/utils/format";

const FORM_ID = "partnership-inquiry";

/**
 * The built-in Partner With Us page. The inquiry form is the shared PartnershipInquiryForm
 * (validation, privacy consent, spam protection and the partnerships API unchanged); every
 * "Make an inquiry" button jumps to it. Audience figures appear only as verified, dated
 * measurements from the media kit. The "Partner With Us page" template builds the same page
 * in the Page Builder.
 */
export function PartnerPage() {
  const { data: site } = useSite();
  const email = site?.contact?.partnerships_email;
  const mediaKitUrl = site?.media_kit_url;
  const { data: kit } = useMediaKit();
  const metrics = kit?.metrics ?? [];
  const social = metrics.find((m) => m.metric_type === "social_followers");
  useHashScroll(FORM_ID);

  return (
    <>
      <Seo
        title="Partner With Us — Brand Partnerships & Collaborations"
        description="Collaborate with Think Positive Always on sponsored content, brand storytelling, newsletter sponsorships, and purpose-driven campaigns for a personal growth audience."
        path={routes.partner}
      />
      <CompanyHero
        eyebrow="Partnerships"
        title="Partner With Think Positive Always"
        intro={partnerIntro}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Partner With Us", href: routes.partner },
        ]}
        actions={
          <>
            <ActionLink href={`#${FORM_ID}`}>
              Make an inquiry
              <ArrowRight aria-hidden />
            </ActionLink>
            <ActionLink href={routes.advertise} variant="outline">
              See the media kit
            </ActionLink>
          </>
        }
        aside={
          <div className="rounded-[1.75rem] bg-sage-800 p-7 text-ivory sm:p-9">
            <span
              aria-hidden
              className="grid size-11 place-items-center rounded-full bg-ivory/10 text-gold-300"
            >
              <Users className="size-5" />
            </span>
            {social ? (
              <>
                <p className="mt-6 font-serif text-5xl font-medium text-ivory">
                  {formatMeasurement(social)}
                </p>
                <p className="mt-2 text-lg text-sage-100">
                  {social.platform} followers (social media, not website visitors).
                </p>
                <p className="mt-2 text-sm text-sage-100">
                  Measured {formatDate(social.measured_on)}. Source: {social.source}.
                </p>
              </>
            ) : (
              <p className="mt-6 text-lg text-sage-100">
                Audience figures will be published in our media kit as dated measurements with their
                source.
              </p>
            )}
          </div>
        }
      />

      <section aria-labelledby="audience-heading" className="bg-ivory py-16 sm:py-20">
        <Container
          size="wide"
          className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] lg:gap-16"
        >
          <SectionHeading
            id="audience-heading"
            eyebrow="Our audience"
            title="A community that values growth"
          />
          <div className="space-y-5 text-lg text-muted">
            {partnerAudience.map((p) => (
              <p key={p.slice(0, 32)}>{p}</p>
            ))}
          </div>
        </Container>
      </section>

      <section
        aria-labelledby="formats-heading"
        className="border-y border-charcoal/[0.08] bg-cream py-16 sm:py-20"
      >
        <Container size="wide">
          <SectionHeading
            id="formats-heading"
            eyebrow="Campaign formats"
            title="Ways we can work together"
            description="Every collaboration is shaped around shared goals. These are some of the formats we can explore."
          />
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {partnershipFormats.map((f) => (
              <IconCard key={f.title} icon={f.icon} title={f.title}>
                {f.text}
              </IconCard>
            ))}
          </ul>
        </Container>
      </section>

      <section aria-labelledby="reasons-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <SectionHeading
            id="reasons-heading"
            eyebrow="Why Think Positive Always"
            title="Reasons to partner with us"
          />
          <ul className="mt-10 grid gap-5 md:grid-cols-3">
            {partnerReasons.map((r) => (
              <IconCard key={r.title} icon={r.icon} title={r.title} tone="cream">
                {r.text}
              </IconCard>
            ))}
          </ul>
        </Container>
      </section>

      <section
        aria-labelledby="alignment-heading"
        className="border-y border-charcoal/[0.08] bg-cream py-16 sm:py-20"
      >
        <Container size="wide" className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <SectionHeading
            id="alignment-heading"
            eyebrow="Brand alignment"
            title="Partnerships built on shared values"
            description="Our readers' trust comes first. We look for partners whose work fits naturally with what Think Positive Always stands for."
          />
          <ul className="space-y-3">
            {brandAlignment.map((item) => (
              <li
                key={item}
                className="flex gap-4 rounded-2xl border border-charcoal/10 bg-ivory p-5"
              >
                <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-sage-700" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Container>
      </section>

      {metrics.length > 0 && (
        <section aria-labelledby="figures-heading" className="bg-ivory py-16 sm:py-20">
          <Container size="wide">
            <SectionHeading
              id="figures-heading"
              eyebrow="Audience"
              title="Measured audience figures"
              description={metricsNote}
            />
            <MetricCards metrics={metrics.slice(0, 4)} className="mt-10" />
          </Container>
        </section>
      )}

      <section aria-labelledby="media-kit-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <div className="flex flex-col gap-6 rounded-[1.75rem] border border-charcoal/10 bg-beige/60 p-7 sm:p-10 md:flex-row md:items-center md:justify-between">
            <div className="flex gap-5">
              <span
                aria-hidden
                className="grid size-12 shrink-0 place-items-center rounded-full bg-ivory text-sage-700"
              >
                <FileText className="size-5" />
              </span>
              <div>
                <h2 id="media-kit-heading" className="text-2xl font-medium sm:text-3xl">
                  Media kit
                </h2>
                <p className="mt-2 max-w-xl text-muted">
                  {kit || mediaKitUrl
                    ? "An overview of the brand, our content focus, audience information and partnership formats."
                    : "Our media kit is being prepared. It will include an overview of the brand, our content focus, audience information, and partnership formats. Until it is published, we are happy to share relevant details directly with prospective partners."}
                </p>
              </div>
            </div>
            {(kit || mediaKitUrl) && (
              <div className="flex shrink-0 flex-wrap gap-3">
                {kit && (
                  <ActionLink href={routes.advertise}>
                    View the Think Positive Always media kit
                    <ArrowRight aria-hidden />
                  </ActionLink>
                )}
                {mediaKitUrl && (
                  <ActionLink href={mediaKitUrl} variant="outline">
                    <Download aria-hidden />
                    Download the Think Positive Always media kit
                  </ActionLink>
                )}
              </div>
            )}
          </div>
        </Container>
      </section>

      <section
        id={FORM_ID}
        aria-labelledby="inquiry-heading"
        className="scroll-mt-24 border-t border-charcoal/[0.08] bg-cream py-16 sm:py-20"
      >
        <Container
          size="wide"
          className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:gap-16"
        >
          <div>
            <SectionHeading
              id="inquiry-heading"
              eyebrow="Get in touch"
              title="How to make an inquiry"
            />
            <ol className="mt-6 list-decimal space-y-3 pl-5 text-lg text-ink marker:text-sage-700">
              <li>Introduce your brand or organisation and what you do.</li>
              <li>Describe the campaign or collaboration you have in mind.</li>
              <li>Share your goals, preferred timeline, and any key requirements.</li>
            </ol>
            {email && (
              <p className="mt-8 text-muted">
                Prefer email?{" "}
                <a
                  href={`mailto:${email}?subject=${encodeURIComponent("Partnership inquiry")}`}
                  className="inline-flex items-center gap-1 font-medium break-all text-sage-700 underline underline-offset-4"
                >
                  <Mail aria-hidden className="size-4 shrink-0" />
                  {email}
                </a>
              </p>
            )}
          </div>
          <div className="rounded-[1.75rem] border border-charcoal/10 bg-ivory p-6 shadow-soft sm:p-10">
            <PartnershipInquiryForm />
          </div>
        </Container>
      </section>

      <section aria-labelledby="partner-cta-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <CtaBand
            id="partner-cta-heading"
            title="Ready to start a conversation?"
            actions={
              <ActionLink href={`#${FORM_ID}`} variant="light">
                Make an inquiry
                <ArrowRight aria-hidden />
              </ActionLink>
            }
          >
            Tell us about your organisation and the collaboration you have in mind.
          </CtaBand>
        </Container>
      </section>
    </>
  );
}

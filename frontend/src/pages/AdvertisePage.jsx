import { ArrowRight, BarChart3, Check, Download, FileText, Globe, Mail, Users } from "lucide-react";
import {
  ActionLink,
  CompanyHero,
  CtaBand,
  IconCard,
  MetricCards,
} from "@/components/company/CompanyUI";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { PageLoading } from "@/components/ui/PageLoading";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { byGroup, metricsNote } from "@/data/companyPages";
import { useMediaKit, useSite } from "@/hooks/useContent";
import { cn } from "@/utils/format";

const PRICING = {
  fixed_fee: "Fixed fee",
  per_placement: "Per placement",
  package: "Package",
  cpm: "Per 1,000 measured impressions",
};

function Prose({ text }) {
  return text
    .split(/\n{2,}/)
    .filter(Boolean)
    .map((p) => (
      <p key={p.slice(0, 40)} className="mt-4 text-lg text-muted first:mt-0">
        {p}
      </p>
    ));
}

const INQUIRY = `${routes.partner}#partnership-inquiry`;

function Band({ id, tone = "ivory", children, className }) {
  return (
    <section
      aria-labelledby={id}
      className={cn(
        "py-16 sm:py-20",
        tone === "cream" ? "border-y border-charcoal/[0.08] bg-cream" : "bg-ivory",
        className,
      )}
    >
      <Container size="wide">{children}</Container>
    </section>
  );
}

function MetricGroup({ icon: Icon, title, metrics }) {
  if (!metrics.length) return null;
  return (
    <div className="mt-10">
      <h3 className="flex items-center gap-2 text-xl font-medium">
        <Icon aria-hidden className="size-5 text-sage-700" />
        {title}
      </h3>
      <MetricCards metrics={metrics} className="mt-5" />
    </div>
  );
}

/**
 * The built-in media kit page. All of its content comes from Partnerships › Media kit
 * (text, formats, placements, rate card, brand assets) and Partnerships › Audience metrics
 * (verified figures, each with its measurement date and source); nothing is shown that
 * hasn't been entered there. Until the media kit is published, a short page invites brands
 * to ask for details.
 */
export function AdvertisePage() {
  const { data: kit, isLoading, isNotFound } = useMediaKit();
  const { data: site } = useSite();
  const email = site?.contact?.partnerships_email;
  const downloadUrl = site?.media_kit_url;
  if (isLoading) return <PageLoading />;

  const hero = (
    <CompanyHero
      eyebrow="Media kit"
      title="Advertise with Think Positive Always"
      intro="Sponsorships, newsletter partnerships and brand collaborations for a personal growth audience."
      breadcrumbs={[
        { name: "Home", href: routes.home },
        { name: "Advertise", href: routes.advertise },
      ]}
      actions={
        <>
          <ActionLink href={INQUIRY}>
            Start a partnership inquiry
            <ArrowRight aria-hidden />
          </ActionLink>
          {downloadUrl && (
            <ActionLink href={downloadUrl} variant="outline">
              <Download aria-hidden />
              Download the media kit
            </ActionLink>
          )}
        </>
      }
    />
  );

  if (!kit) {
    return (
      <>
        <Seo
          title="Advertise"
          description="Our media kit is being prepared."
          path={routes.advertise}
          noIndex
        />
        {hero}
        <Band id="kit-pending-heading">
          <div className="grid gap-8 rounded-[1.75rem] border border-charcoal/10 bg-cream p-7 sm:p-10 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:items-center lg:gap-14">
            <div>
              <span
                aria-hidden
                className="grid size-12 place-items-center rounded-full bg-sage-800 text-gold-300"
              >
                <FileText className="size-5" />
              </span>
              <h2 id="kit-pending-heading" className="mt-5 text-3xl font-medium">
                {isNotFound ? "Our media kit is being prepared" : "We couldn't load the media kit"}
              </h2>
              <p className="mt-3 text-lg text-muted">
                In the meantime, tell us about your organisation and we&apos;ll share relevant
                details directly.
              </p>
              <ul className="mt-6 space-y-2">
                {[
                  "An overview of the brand",
                  "Our content focus",
                  "Audience information",
                  "Partnership formats",
                ].map((item) => (
                  <li key={item} className="flex gap-3">
                    <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-sage-700" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-col items-start gap-4 rounded-[var(--radius-card)] bg-ivory p-6 sm:p-8">
              <p className="font-medium text-charcoal">Request information</p>
              <ActionLink href={INQUIRY}>
                Partner with us
                <ArrowRight aria-hidden />
              </ActionLink>
              {email && (
                <a
                  href={`mailto:${email}?subject=${encodeURIComponent("Media kit request")}`}
                  className="inline-flex items-center gap-2 font-medium break-all text-sage-700 underline underline-offset-4"
                >
                  <Mail aria-hidden className="size-4 shrink-0" />
                  {email}
                </a>
              )}
            </div>
          </div>
        </Band>
      </>
    );
  }

  const social = byGroup(kit.metrics, "social");
  const website = byGroup(kit.metrics, "website");
  const other = kit.metrics.filter((m) => !social.includes(m) && !website.includes(m));
  return (
    <>
      <Seo
        title="Advertise — Media Kit"
        description="Audience, editorial focus, placements and partnership formats at Think Positive Always."
        path={routes.advertise}
      />
      {hero}
      {(kit.about || kit.editorial_focus) && (
        <Band id="about-heading">
          <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
            {kit.about && (
              <div>
                <SectionHeading id="about-heading" eyebrow="About" title="Who we are" />
                <div className="mt-6">
                  <Prose text={kit.about} />
                </div>
              </div>
            )}
            {kit.editorial_focus && (
              <div>
                <SectionHeading
                  id={kit.about ? undefined : "about-heading"}
                  eyebrow="Editorial"
                  title="What we publish"
                />
                <div className="mt-6">
                  <Prose text={kit.editorial_focus} />
                </div>
                {kit.content_categories.length > 0 && (
                  <ul className="mt-6 flex flex-wrap gap-2">
                    {kit.content_categories.map((c) => (
                      <li
                        key={c}
                        className="rounded-full border border-charcoal/10 bg-sage-50 px-3.5 py-1.5 text-sm"
                      >
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </Band>
      )}
      {(kit.audience_summary || kit.metrics.length > 0) && (
        <Band id="audience-heading" tone="cream">
          <SectionHeading
            id="audience-heading"
            eyebrow="Audience"
            title="Our readers"
            description={kit.audience_geography || undefined}
          />
          {kit.audience_summary && (
            <div className="mt-6 max-w-3xl">
              <Prose text={kit.audience_summary} />
            </div>
          )}
          {kit.metrics.length > 0 && (
            <>
              <p className="mt-8 flex items-start gap-2 text-sm text-muted">
                <BarChart3 aria-hidden className="mt-0.5 size-4 shrink-0" />
                {metricsNote}
              </p>
              <MetricGroup icon={Users} title="Social audience" metrics={social} />
              <MetricGroup icon={Globe} title="Website audience" metrics={website} />
              <MetricGroup icon={BarChart3} title="Other measurements" metrics={other} />
            </>
          )}
        </Band>
      )}
      {(kit.placements.length > 0 || kit.campaign_formats.length > 0) && (
        <Band id="formats-heading">
          <SectionHeading
            id="formats-heading"
            eyebrow="Opportunities"
            title="Placements and formats"
          />
          {kit.placements_intro && (
            <div className="mt-6 max-w-3xl">
              <Prose text={kit.placements_intro} />
            </div>
          )}
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {kit.campaign_formats.map((f) => (
              <IconCard key={f.name} title={f.name}>
                {f.description}
              </IconCard>
            ))}
            {kit.placements.map((p) => (
              <IconCard key={`${p.type}-${p.name}`} title={p.name}>
                {[p.channel, p.dimensions, (p.formats ?? []).join(", ")]
                  .filter(Boolean)
                  .join(" · ")}
              </IconCard>
            ))}
          </ul>
        </Band>
      )}
      {kit.rate_card.length > 0 && (
        <Band id="rates-heading" tone="cream">
          <SectionHeading
            id="rates-heading"
            eyebrow="Rate card"
            title="Indicative rates"
            description="Rates are indicative and shown in their own currency. Final terms are agreed in writing for each campaign."
          />
          <div className="mt-8 overflow-x-auto rounded-[var(--radius-card)] border border-charcoal/10 bg-ivory">
            <table className="w-full min-w-[32rem] text-left">
              <caption className="sr-only">Indicative rates</caption>
              <thead>
                <tr className="border-b border-charcoal/10 text-sm text-muted">
                  <th className="px-5 py-3 font-medium">Offer</th>
                  <th className="px-5 py-3 font-medium">Pricing</th>
                  <th className="px-5 py-3 font-medium">Indicative rate</th>
                </tr>
              </thead>
              <tbody>
                {kit.rate_card.map((r) => (
                  <tr
                    key={`${r.name}-${r.price}`}
                    className="border-b border-charcoal/5 last:border-0"
                  >
                    <td className="px-5 py-3">
                      {r.name}
                      {(r.placement || r.description) && (
                        <span className="block text-sm text-muted">
                          {[r.placement, r.description].filter(Boolean).join(" — ")}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">{PRICING[r.pricing_model] ?? r.pricing_model}</td>
                    <td className="px-5 py-3">
                      {r.price}
                      {r.unit_label && <span className="text-muted"> {r.unit_label}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Band>
      )}
      {(kit.collaboration_guidelines || kit.sponsorship_policies) && (
        <Band id="policies-heading">
          <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
            {kit.collaboration_guidelines && (
              <div>
                <SectionHeading
                  id="policies-heading"
                  eyebrow="Guidelines"
                  title="How we collaborate"
                />
                <div className="mt-6">
                  <Prose text={kit.collaboration_guidelines} />
                </div>
              </div>
            )}
            {kit.sponsorship_policies && (
              <div>
                <SectionHeading
                  id={kit.collaboration_guidelines ? undefined : "policies-heading"}
                  eyebrow="Transparency"
                  title="Sponsorship and disclosure"
                />
                <div className="mt-6">
                  <Prose text={kit.sponsorship_policies} />
                </div>
              </div>
            )}
          </div>
        </Band>
      )}
      {kit.brand_assets.length > 0 && (
        <Band id="assets-heading" tone="cream">
          <SectionHeading id="assets-heading" eyebrow="Brand assets" title="Logos and imagery" />
          <ul className="mt-8 grid grid-cols-2 gap-5 sm:grid-cols-4">
            {kit.brand_assets.map((a) => (
              <li key={a.src}>
                <a
                  href={a.src}
                  className="block rounded-2xl border border-charcoal/10 bg-ivory p-4"
                >
                  <img
                    src={a.src}
                    alt={a.alt || "Brand asset"}
                    loading="lazy"
                    className="mx-auto max-h-24"
                  />
                </a>
              </li>
            ))}
          </ul>
        </Band>
      )}
      <Band id="advertise-cta-heading">
        <CtaBand
          id="advertise-cta-heading"
          title="Let's talk about a partnership"
          actions={
            <>
              <ActionLink href={kit.contact_cta?.href || INQUIRY} variant="light">
                {kit.contact_cta?.label || "Start a partnership conversation"}
                <ArrowRight aria-hidden />
              </ActionLink>
              {downloadUrl && (
                <ActionLink href={downloadUrl} variant="outlineLight">
                  <Download aria-hidden />
                  Download the media kit
                </ActionLink>
              )}
            </>
          }
        >
          {kit.notes?.[1]}
        </CtaBand>
      </Band>
    </>
  );
}

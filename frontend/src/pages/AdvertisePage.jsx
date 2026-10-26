import { ArrowRight, BarChart3, FileText } from "lucide-react";
import { Link } from "react-router";
import { formatMeasurement } from "@/components/partnerships/partnershipOptions";
import { Seo } from "@/components/seo/Seo";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { PageLoading } from "@/components/ui/PageLoading";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { useMediaKit } from "@/hooks/useContent";

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

/** Audience measurements are always shown with platform, source and measurement date. */
export function MeasurementList({ metrics }) {
  if (!metrics?.length) return null;
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {metrics.map((m) => (
        <li key={`${m.metric_type}-${m.platform}-${m.measured_on}`}>
          <Card className="h-full p-6">
            <p className="font-serif text-4xl font-medium text-charcoal">{formatMeasurement(m)}</p>
            <p className="mt-2 font-medium">
              {m.label} · {m.platform}
            </p>
            <p className="mt-2 text-sm text-muted">
              Measured {m.measured_on}
              {m.period_label ? ` (${m.period_label})` : ""}. Source: {m.source}.
            </p>
          </Card>
        </li>
      ))}
    </ul>
  );
}

export function AdvertisePage() {
  const { data: kit, isLoading, isNotFound } = useMediaKit();
  if (isLoading) return <PageLoading />;
  const header = (
    <PageHeader
      eyebrow="Media kit"
      title="Advertise with Think Positive Always"
      description="Sponsorships, newsletter partnerships and brand collaborations for a personal growth audience."
      breadcrumbs={[
        { name: "Home", href: routes.home },
        { name: "Advertise", href: routes.advertise },
      ]}
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
        {header}
        <Section>
          <Notice
            title={
              isNotFound ? "Our media kit is being prepared" : "We couldn't load the media kit"
            }
          >
            In the meantime, tell us about your organisation and we&apos;ll share relevant details
            directly.{" "}
            <Link to={routes.partner} className="font-medium underline underline-offset-4">
              Partner with us
            </Link>
          </Notice>
        </Section>
      </>
    );
  }
  return (
    <>
      <Seo
        title="Advertise — Media Kit"
        description="Audience, editorial focus, placements and partnership formats at Think Positive Always."
        path={routes.advertise}
      />
      {header}
      {(kit.about || kit.editorial_focus) && (
        <Section aria-labelledby="about-heading">
          <div className="grid gap-12 lg:grid-cols-2">
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
                <SectionHeading eyebrow="Editorial" title="What we publish" />
                <div className="mt-6">
                  <Prose text={kit.editorial_focus} />
                </div>
                {kit.content_categories.length > 0 && (
                  <ul className="mt-6 flex flex-wrap gap-2">
                    {kit.content_categories.map((c) => (
                      <li key={c} className="rounded-full bg-sage-50 px-3 py-1 text-sm">
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </Section>
      )}
      {(kit.audience_summary || kit.metrics.length > 0) && (
        <Section tone="cream" aria-labelledby="audience-heading">
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
            <div className="mt-10">
              <h3 className="flex items-center gap-2 text-lg font-medium">
                <BarChart3 aria-hidden className="size-5" /> Measured audience figures
              </h3>
              <p className="mt-1 text-sm text-muted">
                Each figure is a measurement taken on the date shown, not a live count. Social media
                followers are not website visitors.
              </p>
              <div className="mt-6">
                <MeasurementList metrics={kit.metrics} />
              </div>
            </div>
          )}
        </Section>
      )}
      {(kit.placements.length > 0 || kit.campaign_formats.length > 0) && (
        <Section aria-labelledby="formats-heading">
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
          <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {kit.campaign_formats.map((f) => (
              <li key={f.name}>
                <Card className="h-full p-6">
                  <h3 className="text-lg font-medium">{f.name}</h3>
                  {f.description && <p className="mt-2 text-muted">{f.description}</p>}
                </Card>
              </li>
            ))}
            {kit.placements.map((p) => (
              <li key={`${p.type}-${p.name}`}>
                <Card className="h-full p-6">
                  <h3 className="text-lg font-medium">{p.name}</h3>
                  <p className="mt-2 text-sm text-muted">
                    {[p.channel, p.dimensions, (p.formats ?? []).join(", ")]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {kit.rate_card.length > 0 && (
        <Section tone="beige" aria-labelledby="rates-heading">
          <SectionHeading
            id="rates-heading"
            eyebrow="Rate card"
            title="Indicative rates"
            description="Rates are indicative and shown in their own currency. Final terms are agreed in writing for each campaign."
          />
          <div className="mt-8 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left">
              <caption className="sr-only">Indicative rates</caption>
              <thead>
                <tr className="border-b border-charcoal/10 text-sm text-muted">
                  <th className="py-2 pr-4 font-medium">Offer</th>
                  <th className="py-2 pr-4 font-medium">Pricing</th>
                  <th className="py-2 font-medium">Indicative rate</th>
                </tr>
              </thead>
              <tbody>
                {kit.rate_card.map((r) => (
                  <tr key={`${r.name}-${r.price}`} className="border-b border-charcoal/5">
                    <td className="py-3 pr-4">
                      {r.name}
                      {(r.placement || r.description) && (
                        <span className="block text-sm text-muted">
                          {[r.placement, r.description].filter(Boolean).join(" — ")}
                        </span>
                      )}
                    </td>
                    <td className="py-3 pr-4">{PRICING[r.pricing_model] ?? r.pricing_model}</td>
                    <td className="py-3">
                      {r.price}
                      {r.unit_label && <span className="text-muted"> {r.unit_label}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
      {(kit.collaboration_guidelines || kit.sponsorship_policies) && (
        <Section aria-labelledby="policies-heading">
          <div className="grid gap-12 lg:grid-cols-2">
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
                <SectionHeading eyebrow="Transparency" title="Sponsorship and disclosure" />
                <div className="mt-6">
                  <Prose text={kit.sponsorship_policies} />
                </div>
              </div>
            )}
          </div>
        </Section>
      )}
      {kit.brand_assets.length > 0 && (
        <Section tone="cream" aria-labelledby="assets-heading">
          <SectionHeading id="assets-heading" eyebrow="Brand assets" title="Logos and imagery" />
          <ul className="mt-8 grid grid-cols-2 gap-6 sm:grid-cols-4">
            {kit.brand_assets.map((a) => (
              <li key={a.src}>
                <a href={a.src} className="block rounded-2xl bg-ivory p-4">
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
        </Section>
      )}
      <Section tone="beige">
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <FileText aria-hidden className="size-6 text-sage-700" />
            <p className="text-lg">{kit.notes?.[1]}</p>
          </div>
          <Link to={kit.contact_cta.href} className={buttonStyles()}>
            {kit.contact_cta.label} <ArrowRight aria-hidden />
          </Link>
        </div>
      </Section>
    </>
  );
}

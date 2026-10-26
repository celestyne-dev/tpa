import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { PartnershipInquiryForm } from "@/components/partnerships/PartnershipInquiryForm";
import {
  formatMeasurement,
  liveOnly,
  sponsoredRel,
} from "@/components/partnerships/partnershipOptions";
import { ContentImage } from "@/components/ui/ContentImage";
import { useNow } from "@/hooks/useNow";
import { cn } from "@/utils/format";
import { CtaButton, Eyebrow, Heading, SectionHeader, SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

/** Paid links always carry rel="sponsored" (plus noopener/noreferrer when external). */
function SponsoredAnchor({ href, className, children, ...rest }) {
  return (
    <a href={href} rel={sponsoredRel(href)} className={className} {...rest}>
      {children}
    </a>
  );
}

function DisclosureLabel({ text, className }) {
  const { dark } = useSectionContext();
  return (
    <span
      className={cn(
        "inline-block rounded-full px-3 py-1 text-xs font-semibold tracking-wide uppercase",
        dark ? "bg-ivory/15 text-ivory" : "bg-gold-100 text-charcoal",
        className,
      )}
    >
      {text || "Sponsored"}
    </span>
  );
}

export function SponsorLogosSection({ section }) {
  const { data, key } = section;
  const creatives = liveOnly(data.creatives, useNow());
  if (!creatives.length) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Sponsors">
      <div className="flex flex-col items-center gap-6 text-center">
        <div className="flex items-center gap-3">
          {data.heading && (
            <h2 id={id} className="text-lg font-medium">
              {data.heading}
            </h2>
          )}
          <DisclosureLabel text={data.label} />
        </div>
        <ul className="flex flex-wrap items-center justify-center gap-x-10 gap-y-6">
          {creatives.map((c) => {
            const logo = c.logo || c.image;
            const content = logo ? (
              <img
                src={logo.src}
                alt={c.sponsor}
                loading="lazy"
                className="max-h-12 w-auto object-contain"
              />
            ) : (
              <span className="font-medium">{c.sponsor}</span>
            );
            return (
              <li key={c.id}>
                {c.link ? (
                  <SponsoredAnchor href={c.link.href} aria-label={`${c.sponsor} (sponsor)`}>
                    {content}
                  </SponsoredAnchor>
                ) : (
                  content
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </SectionShell>
  );
}

export function SponsoredBannerSection({ section }) {
  const { data, key, variant } = section;
  const [creative] = liveOnly(data.creatives, useNow());
  if (!creative) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={id} width="wide">
      <div
        className={cn(
          "grid items-center gap-8 rounded-[2rem] bg-ivory p-6 shadow-soft sm:p-10",
          creative.image && "md:grid-cols-[1fr_1.2fr]",
          variant === "banner" && "rounded-none bg-transparent p-0 shadow-none",
        )}
      >
        {creative.image && (
          <div className="relative aspect-[16/9] overflow-hidden rounded-2xl">
            <ContentImage
              image={creative.image}
              fill
              sizes="(min-width: 768px) 480px, 100vw"
              className="object-cover"
            />
          </div>
        )}
        <div>
          <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <DisclosureLabel text={data.label} />
            <span>
              Paid partnership with{" "}
              <span className="font-medium text-charcoal">{creative.sponsor}</span>
            </span>
          </p>
          <h2 id={id} className="mt-4 text-2xl font-medium sm:text-3xl">
            {creative.headline || creative.sponsor}
          </h2>
          {creative.body && <p className="mt-3 text-lg text-muted">{creative.body}</p>}
          {creative.link && (
            <SponsoredAnchor
              href={creative.link.href}
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-sage-700 px-6 py-3 font-semibold text-ivory hover:bg-sage-800"
            >
              {creative.link.label} <ArrowRight aria-hidden className="size-4" />
            </SponsoredAnchor>
          )}
        </div>
      </div>
    </SectionShell>
  );
}

export function BrandSpotlightSection({ section }) {
  const { data, key } = section;
  const [creative] = liveOnly(data.creatives, useNow());
  if (!creative) return null;
  const id = `${key}-heading`;
  const image = creative.image || creative.logo;
  return (
    <SectionShell section={section} labelledBy={id}>
      <div className={cn("grid items-center gap-10", image && "lg:grid-cols-2")}>
        <div>
          <Eyebrow>{data.eyebrow}</Eyebrow>
          <Heading id={id}>{creative.headline || creative.sponsor}</Heading>
          <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted">
            <DisclosureLabel text={data.label} />
            <span>
              Sponsored by <span className="font-medium text-charcoal">{creative.sponsor}</span>
            </span>
          </p>
          {creative.body && <p className="mt-5 text-lg text-muted">{creative.body}</p>}
          {creative.link && (
            <SponsoredAnchor
              href={creative.link.href}
              className="mt-8 inline-flex items-center gap-2 font-semibold text-sage-700 underline underline-offset-4"
            >
              {creative.link.label} <ArrowRight aria-hidden className="size-4" />
            </SponsoredAnchor>
          )}
        </div>
        {image && (
          <div className="relative aspect-[4/3] overflow-hidden rounded-[var(--radius-card)] bg-beige">
            <ContentImage
              image={image}
              fill
              sizes="(min-width: 1024px) 520px, 100vw"
              className="object-cover"
            />
          </div>
        )}
      </div>
    </SectionShell>
  );
}

export function AffiliateRecommendationsSection({ section }) {
  const { data, key, variant } = section;
  if (!data.links?.length) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader id={id} data={data} />
      {/* The disclosure sits right beside the recommendations, never only in the footer. */}
      <p
        className="mt-4 max-w-2xl rounded-2xl bg-sage-50 p-4 text-sm text-charcoal"
        data-affiliate-disclosure="true"
      >
        {data.disclosure}
      </p>
      <ul className={cn("mt-8 grid gap-4", variant === "cards" && "sm:grid-cols-2 lg:grid-cols-3")}>
        {data.links.map((link) => (
          <li key={link.id} className="rounded-2xl bg-ivory p-6 shadow-soft">
            <p className="font-medium">{link.name}</p>
            {link.merchant && <p className="text-sm text-muted">{link.merchant}</p>}
            {link.note && <p className="mt-3 text-muted">{link.note}</p>}
            <SponsoredAnchor
              href={link.href}
              className="mt-4 inline-flex items-center gap-2 font-semibold text-sage-700 underline underline-offset-4"
            >
              View <span className="sr-only">{link.name}</span> (affiliate link)
              <ArrowRight aria-hidden className="size-4" />
            </SponsoredAnchor>
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}

export function MediaKitSummarySection({ section }) {
  const { data, key } = section;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader id={id} data={data} />
      {data.metrics?.length > 0 && (
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.metrics.map((m) => (
            <li
              key={`${m.metric_type}-${m.platform}-${m.measured_on}`}
              className="rounded-2xl bg-ivory p-6"
            >
              <p className="font-serif text-3xl font-medium">{formatMeasurement(m)}</p>
              <p className="mt-1 font-medium">
                {m.label} · {m.platform}
              </p>
              <p className="mt-1 text-xs text-muted">
                Measured {m.measured_on}. Source: {m.source}.
              </p>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-8">
        {data.cta ? (
          <CtaButton cta={data.cta} arrow />
        ) : (
          <Link
            to="/advertise"
            className="inline-flex items-center gap-2 font-semibold text-sage-700 underline underline-offset-4"
          >
            View the media kit <ArrowRight aria-hidden className="size-4" />
          </Link>
        )}
      </div>
    </SectionShell>
  );
}

export function PartnershipInquirySection({ section }) {
  const { data, key } = section;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader id={id} data={data} />
      <PartnershipInquiryForm className="mt-8" />
    </SectionShell>
  );
}

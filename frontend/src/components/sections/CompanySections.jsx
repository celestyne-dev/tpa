import { Info, TriangleAlert } from "lucide-react";
import { ContactCard, MetricCards, NoticePanel } from "@/components/company/CompanyUI";
import { useSite } from "@/hooks/useContent";
import { cn } from "@/utils/format";
import { SECTION_ICONS } from "./icons";
import { CtaButton, Paragraphs, SectionHeader, SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

/**
 * "Contact cards": one card per way to get in touch. Addresses come from Settings › Contact
 * (general or partnerships), never typed into the page, so they stay correct everywhere.
 */
export function ContactCardsSection({ section }) {
  const { data, variant, key } = section;
  const { data: site } = useSite();
  const emails = {
    general: site?.contact?.email || null,
    partnerships: site?.contact?.partnerships_email || site?.contact?.email || null,
  };
  const id = `${key}-heading`;
  const header = { ...data, description: data.intro };
  return (
    <SectionShell
      section={section}
      labelledBy={data.heading ? id : undefined}
      label="Contact"
      width="wide"
    >
      <SectionHeader id={id} data={header} className="mb-10" />
      <ul className={cn("grid gap-5", variant === "cards_2" ? "md:grid-cols-2" : "md:grid-cols-3")}>
        {(data.items ?? []).map((item, index) => (
          <ContactCard
            key={`${item.title}-${index}`}
            icon={SECTION_ICONS[item.icon]}
            title={item.title}
            text={item.text}
            email={item.email && item.email !== "none" ? emails[item.email] : null}
            action={
              item.cta_label && item.cta_url ? { label: item.cta_label, href: item.cta_url } : null
            }
            fallback={data.fallback}
          />
        ))}
      </ul>
    </SectionShell>
  );
}

/**
 * "Verified audience figures": published, verified measurements from Partnerships ›
 * Audience metrics, each with its date and source. Nothing renders until there is one (the
 * editor's preview explains why the section is empty).
 */
export function AudienceMetricsSection({ section }) {
  const { data, key } = section;
  const { preview } = useSectionContext();
  const id = `${key}-heading`;
  const metrics = data.metrics ?? [];
  if (!metrics.length) {
    if (!preview) return null;
    return (
      <SectionShell section={section} label="Audience figures">
        <p className="rounded-xl border border-dashed border-charcoal/20 p-5 text-sm text-muted">
          No verified, public audience figures yet: this section stays hidden on the website until a
          measurement is added under Partnerships › Audience metrics.
        </p>
      </SectionShell>
    );
  }
  return (
    <SectionShell
      section={section}
      labelledBy={data.heading ? id : undefined}
      label="Audience figures"
      width="wide"
    >
      <SectionHeader id={id} data={data} />
      <MetricCards metrics={metrics} className="mt-10" />
    </SectionShell>
  );
}

/** "Notice": a clearly separated message, for example that this is not a crisis service. */
export function NoticePanelSection({ section }) {
  const { data, variant, key } = section;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={id} width="wide">
      <NoticePanel
        id={id}
        icon={variant === "calm" ? Info : TriangleAlert}
        title={data.heading}
        tone={variant === "calm" ? "calm" : "important"}
        action={data.cta ? <CtaButton cta={data.cta} fallback="outline" /> : null}
      >
        <Paragraphs text={data.body} className="text-base" tone="text-ink" />
      </NoticePanel>
    </SectionShell>
  );
}

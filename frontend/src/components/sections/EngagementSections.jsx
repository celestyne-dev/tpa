import { Check, Mail } from "lucide-react";
import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { ProductCard } from "@/components/products/ProductCard";
import { LinkedinMark } from "@/components/home/LinkedinMark";
import { ContentImage } from "@/components/ui/ContentImage";
import { cn } from "@/utils/format";
import { ASPECT, BACKGROUNDS, isDark } from "./design";
import { CtaButton, Eyebrow, Heading, Paragraphs, SectionHeader, SectionShell } from "./primitives";
import { SectionContext, useSectionContext } from "./sectionContext";

/** Mission / brand introduction with an optional verified community figure or image. */
export function BrandIntroSection({ section }) {
  const { data, variant, key } = section;
  const { design } = useSectionContext();
  const id = `${key}-heading`;
  const aside =
    variant === "with_stat" && data.stat_value ? (
      <figure className="relative rounded-[2rem] bg-ivory p-8 shadow-soft sm:p-10">
        <span className="grid size-12 place-items-center rounded-xl bg-sage-700 text-ivory">
          <LinkedinMark className="size-5" />
        </span>
        <p className="mt-6 font-serif text-6xl font-medium text-charcoal sm:text-7xl">
          {data.stat_value}
        </p>
        {data.stat_caption && (
          <figcaption className="mt-3 text-lg text-muted">{data.stat_caption}</figcaption>
        )}
        <div aria-hidden className="absolute top-8 right-8 h-16 w-16 rounded-full bg-gold-100" />
      </figure>
    ) : variant === "with_image" && data.media ? (
      <div
        className={cn(
          "relative overflow-hidden rounded-[var(--radius-card)] bg-beige",
          ASPECT[design.aspect_ratio ?? "landscape"],
        )}
      >
        <ContentImage
          image={data.media}
          fill
          sizes="(min-width: 1024px) 480px, 100vw"
          className="object-cover"
        />
      </div>
    ) : null;
  return (
    <SectionShell section={section} labelledBy={id}>
      <div
        className={cn("grid gap-12", aside && "lg:grid-cols-[1.3fr_1fr] lg:items-center lg:gap-20")}
      >
        <div className={cn(!aside && "max-w-3xl")}>
          <Eyebrow>{data.eyebrow}</Eyebrow>
          <Heading id={id}>{data.heading}</Heading>
          <Paragraphs text={data.body} className="mt-6" />
          {data.cta && <CtaButton cta={data.cta} fallback="outline" className="mt-8" />}
        </div>
        {aside}
      </div>
    </SectionShell>
  );
}

/**
 * The Positive Reset panel. Until a real provider is connected it shows an honest
 * "opening soon" notice and never collects email addresses.
 */
export function NewsletterSection({ section }) {
  const { data, variant } = section;
  const { level } = useSectionContext();
  return (
    <SectionShell section={section} label="Newsletter" width={section.design?.width ?? "wide"}>
      <NewsletterPanel
        headingLevel={level === 1 ? "h1" : "h2"}
        title={data.heading}
        eyebrow={data.eyebrow}
        description={data.description}
        showLearnMore={data.show_learn_more !== false}
        className={variant === "compact" ? "py-10 sm:py-12" : undefined}
      />
    </SectionShell>
  );
}

/** Honest coming-soon previews of planned products (no prices, no purchase buttons). */
export function ProductsSection({ section }) {
  const { data, key } = section;
  const { dark } = useSectionContext();
  const id = `${key}-heading`;
  const products = data.products ?? [];
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader
        id={id}
        data={data}
        action={data.cta && <CtaButton cta={data.cta} fallback="outline" arrow />}
      />
      <ul
        className={cn(
          "mt-12 grid gap-8 sm:grid-cols-2",
          products.length >= 4 ? "lg:grid-cols-4" : "lg:grid-cols-3",
        )}
      >
        {products.map((product) => (
          <li key={product.id}>
            <ProductCard product={product} />
          </li>
        ))}
      </ul>
      {data.footnote && (
        <p className={cn("mt-8 text-center text-sm", dark ? "text-sand" : "text-muted")}>
          {data.footnote}
        </p>
      )}
    </SectionShell>
  );
}

export function PromoBannerSection({ section }) {
  const { data, variant, key } = section;
  const context = useSectionContext();
  const { design } = context;
  const id = `${key}-heading`;
  const background = design.background ?? "sage_dark";
  const inner = (
    <div className={cn("grid items-center gap-10", data.media && "lg:grid-cols-[1.2fr_1fr]")}>
      <div>
        <Eyebrow>{data.eyebrow}</Eyebrow>
        <Heading id={id}>{data.heading}</Heading>
        <Paragraphs text={data.body} className="mt-5" />
        {data.cta && (
          <CtaButton cta={data.cta} style={design.button_style} size="lg" arrow className="mt-8" />
        )}
      </div>
      {data.media && (
        <div className="relative aspect-[4/3] overflow-hidden rounded-[var(--radius-card)]">
          <ContentImage
            image={data.media}
            fill
            sizes="(min-width: 1024px) 480px, 100vw"
            className="object-cover"
          />
        </div>
      )}
    </div>
  );
  if (variant === "card") {
    // The card carries the chosen colour; the section around it stays light.
    return (
      <SectionShell
        section={{ ...section, design: { ...design, background: "ivory" } }}
        labelledBy={id}
        width="wide"
      >
        <SectionContext.Provider value={{ ...context, dark: isDark(background) }}>
          <div
            className={cn("rounded-[2rem] px-6 py-12 sm:px-12 sm:py-16", BACKGROUNDS[background])}
          >
            {inner}
          </div>
        </SectionContext.Provider>
      </SectionShell>
    );
  }
  return (
    <SectionShell section={section} labelledBy={id} width="wide">
      {inner}
    </SectionShell>
  );
}

export function CtaSection({ section }) {
  const { data, variant, key } = section;
  const id = `${key}-heading`;
  const buttons = (
    <div
      className={cn(
        "mt-10 flex flex-col gap-3 sm:flex-row",
        variant !== "banner" && "justify-center",
      )}
    >
      <CtaButton cta={data.primary_cta} size="lg" arrow />
      <CtaButton cta={data.secondary_cta} size="lg" fallback="outline" />
    </div>
  );
  if (variant === "banner") {
    return (
      <SectionShell section={section} labelledBy={id} width={section.design?.width ?? "wide"}>
        <div className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl">
            <Heading id={id}>{data.heading}</Heading>
            <Paragraphs text={data.body} className="mt-4" />
          </div>
          <div className="[&>div]:mt-0">{buttons}</div>
        </div>
      </SectionShell>
    );
  }
  return (
    <SectionShell section={section} labelledBy={id} containerClassName="text-center">
      <div aria-hidden className="mx-auto mb-8 flex items-center justify-center gap-3">
        <span className="h-px w-12 bg-gold-400" />
        <span className="size-2 rounded-full bg-gold-400" />
        <span className="h-px w-12 bg-gold-400" />
      </div>
      <Heading id={id} defaultSizeClass="text-4xl sm:text-5xl">
        {data.heading}
      </Heading>
      <Paragraphs text={data.body} className="mx-auto mt-6 max-w-xl" />
      {buttons}
    </SectionShell>
  );
}

export function PartnershipSection({ section }) {
  const { data, variant, key } = section;
  const context = useSectionContext();
  const id = `${key}-heading`;
  const dark = variant !== "light";
  const shell = {
    ...section,
    design: { ...section.design, background: dark ? "charcoal" : "cream" },
  };
  return (
    <SectionContext.Provider value={{ ...context, dark, design: shell.design }}>
      <SectionShell section={shell} labelledBy={id}>
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
          <div>
            <Eyebrow>{data.eyebrow}</Eyebrow>
            <Heading id={id} defaultSizeClass="text-3xl sm:text-4xl lg:text-5xl">
              {data.heading}
            </Heading>
            <Paragraphs text={data.body} className="mt-6" tone={dark ? "text-sand" : undefined} />
            {data.cta && (
              <CtaButton cta={data.cta} fallback="light" size="lg" arrow className="mt-9" />
            )}
          </div>
          {data.items?.length > 0 && (
            <div
              className={cn(
                "rounded-[2rem] p-8 sm:p-10",
                dark ? "border border-ivory/10 bg-ivory/[0.04]" : "bg-ivory shadow-soft",
              )}
            >
              {data.list_heading && (
                <h3
                  className={cn(
                    "font-sans text-sm font-semibold tracking-[0.14em] uppercase",
                    dark ? "text-ivory" : "text-charcoal",
                  )}
                >
                  {data.list_heading}
                </h3>
              )}
              <ul className={cn("mt-6 divide-y", dark ? "divide-ivory/10" : "divide-charcoal/10")}>
                {data.items.map((item) => (
                  <li
                    key={item}
                    className={cn(
                      "flex items-center gap-4 py-4 font-serif text-xl",
                      dark ? "text-ivory" : "text-charcoal",
                    )}
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gold-400/20 text-gold-500">
                      <Check aria-hidden className={cn("size-4", dark && "text-gold-300")} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </SectionShell>
    </SectionContext.Provider>
  );
}

/** Contact email addresses from Settings. There is deliberately no form. */
export function ContactDetailsSection({ section }) {
  const { data, key } = section;
  const { dark } = useSectionContext();
  const id = `${key}-heading`;
  const emails = [
    data.email && { label: "General enquiries", value: data.email },
    data.partnerships_email && { label: "Partnerships", value: data.partnerships_email },
  ].filter(Boolean);
  return (
    <SectionShell section={section} labelledBy={id}>
      <Heading id={id}>{data.heading}</Heading>
      <Paragraphs text={data.body} className="mt-5" />
      {emails.length > 0 ? (
        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {emails.map((e) => (
            <li
              key={e.label}
              className={cn(
                "flex items-start gap-4 rounded-2xl p-6",
                dark ? "bg-ivory/[0.06]" : "bg-ivory shadow-soft",
              )}
            >
              <Mail
                aria-hidden
                className={cn("mt-1 size-5 shrink-0", dark ? "text-gold-300" : "text-sage-700")}
              />
              <span>
                <span className={cn("block text-sm", dark ? "text-sand" : "text-muted")}>
                  {e.label}
                </span>
                <a
                  href={`mailto:${e.value}`}
                  className="font-medium break-all underline-offset-4 hover:underline"
                >
                  {e.value}
                </a>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={cn("mt-8", dark ? "text-sand" : "text-muted")}>
          Contact details will be published here soon.
        </p>
      )}
      {data.note && (
        <p className={cn("mt-6 text-sm", dark ? "text-sand" : "text-muted")}>{data.note}</p>
      )}
    </SectionShell>
  );
}

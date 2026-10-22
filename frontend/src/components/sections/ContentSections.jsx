import {
  BookOpen,
  CalendarCheck,
  Compass,
  Footprints,
  Gem,
  Handshake,
  HeartHandshake,
  Leaf,
  Lightbulb,
  MailCheck,
  NotebookPen,
  Quote,
  ShieldCheck,
  Sparkles,
  Sprout,
  Sun,
  Sunrise,
} from "lucide-react";
import { Link } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { cn } from "@/utils/format";
import { ASPECT, cardClass } from "./design";
import { CtaButton, Eyebrow, Heading, Paragraphs, SectionHeader, SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

// Approved icon names (mirrors FEATURE_ICONS in backend/app/cms/sections.py).
const ICONS = {
  "heart-handshake": HeartHandshake,
  compass: Compass,
  "notebook-pen": NotebookPen,
  footprints: Footprints,
  sun: Sun,
  sprout: Sprout,
  gem: Gem,
  sunrise: Sunrise,
  leaf: Leaf,
  lightbulb: Lightbulb,
  "book-open": BookOpen,
  "shield-check": ShieldCheck,
  sparkles: Sparkles,
  handshake: Handshake,
  "mail-check": MailCheck,
  "calendar-check": CalendarCheck,
};

function SmartLink({ href, className, children }) {
  if (href?.startsWith("https://")) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

export function QuoteSection({ section }) {
  const { data, variant } = section;
  const { design, dark } = useSectionContext();
  const centered = design.align !== "left";
  const quote = (
    <figure className={cn("mx-auto max-w-3xl", centered && "text-center")}>
      <Quote
        aria-hidden
        className={cn("size-8", centered && "mx-auto", dark ? "text-gold-300" : "text-gold-400")}
      />
      <blockquote
        className={cn(
          "mt-5 font-serif leading-snug italic",
          variant === "large" ? "text-3xl sm:text-5xl" : "text-2xl sm:text-3xl",
          dark ? "text-ivory" : "text-charcoal",
        )}
      >
        <p>{data.quote}</p>
      </blockquote>
      {data.attribution && (
        <figcaption className={cn("mt-6", dark ? "text-sand" : "text-muted")}>
          <span className="font-medium">{data.attribution}</span>
          {data.attribution_role && <span>, {data.attribution_role}</span>}
        </figcaption>
      )}
    </figure>
  );
  return (
    <SectionShell section={section} label="Quote">
      {variant === "highlighted" ? (
        <div
          className={cn(
            "rounded-[2rem] border-l-4 border-gold-400 p-8 sm:p-12",
            cardClass("soft", dark),
          )}
        >
          {quote}
        </div>
      ) : (
        quote
      )}
    </SectionShell>
  );
}

export function MessageSection({ section }) {
  const { data, variant, key } = section;
  const id = `${key}-heading`;
  const banner = variant === "banner";
  return (
    <SectionShell section={section} labelledBy={id} width={banner ? "wide" : "narrow"}>
      <div
        className={cn(
          banner
            ? "flex flex-col gap-6 md:flex-row md:items-center md:justify-between"
            : "text-center",
        )}
      >
        <div className={cn(!banner && "mx-auto max-w-2xl")}>
          <Eyebrow>{data.eyebrow}</Eyebrow>
          <Heading id={id} className="font-serif italic">
            {data.message}
          </Heading>
          <Paragraphs text={data.body} className="mt-5" />
        </div>
        {data.cta && <CtaButton cta={data.cta} size="lg" arrow className={cn(!banner && "mt-8")} />}
      </div>
    </SectionShell>
  );
}

export function ImageTextSection({ section }) {
  const { data, variant, key } = section;
  const { design, dark } = useSectionContext();
  const id = `${key}-heading`;
  const imageRight = variant === "image_right";
  return (
    <SectionShell section={section} labelledBy={id}>
      <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <div
          className={cn(
            "relative overflow-hidden rounded-[var(--radius-card)] bg-beige",
            ASPECT[design.aspect_ratio ?? "landscape"],
            imageRight && "lg:order-2",
          )}
        >
          {data.media && (
            <ContentImage
              image={data.media}
              fill
              sizes="(min-width: 1024px) 560px, 100vw"
              className="object-cover"
            />
          )}
        </div>
        <div>
          <Eyebrow>{data.eyebrow}</Eyebrow>
          <Heading id={id}>{data.heading}</Heading>
          <Paragraphs text={data.body} className="mt-6" />
          {data.bullets?.length > 0 && (
            <ul className="mt-6 space-y-3">
              {data.bullets.map((b) => (
                <li key={b} className="flex gap-3">
                  <span aria-hidden className="mt-2.5 size-2 shrink-0 rounded-full bg-gold-400" />
                  <span className={dark ? "text-sand" : "text-ink"}>{b}</span>
                </li>
              ))}
            </ul>
          )}
          {(data.primary_cta || data.secondary_cta) && (
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <CtaButton cta={data.primary_cta} arrow />
              <CtaButton cta={data.secondary_cta} fallback="outline" />
            </div>
          )}
        </div>
      </div>
    </SectionShell>
  );
}

export function RichTextSection({ section }) {
  const { data, variant, key } = section;
  const id = `${key}-heading`;
  return (
    <SectionShell
      section={section}
      labelledBy={data.heading ? id : undefined}
      label="Content"
      width={variant === "narrow" ? "narrow" : "default"}
    >
      {data.heading && (
        <Heading id={id} className="mb-8">
          {data.heading}
        </Heading>
      )}
      <ArticleBody blocks={data.body ?? []} />
    </SectionShell>
  );
}

export function FeatureListSection({ section }) {
  const { data, variant, key } = section;
  const { design, dark } = useSectionContext();
  const id = `${key}-heading`;
  const items = (
    <ul
      className={cn(
        "grid gap-10 sm:grid-cols-2",
        variant === "grid_3" && "lg:grid-cols-3",
        variant === "grid_4" && "lg:grid-cols-4",
        variant !== "sticky_intro" && "mt-12",
      )}
    >
      {(data.items ?? []).map((item) => {
        const Icon = ICONS[item.icon] ?? Sun;
        return (
          <li
            key={item.title}
            className={cn("rounded-[var(--radius-card)] p-7", cardClass(design.card_style, dark))}
          >
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-sage-100 text-sage-700">
              <Icon aria-hidden className="size-5" />
            </span>
            <h3 className={cn("mt-5 font-serif text-xl font-medium", dark && "text-ivory")}>
              {item.title}
            </h3>
            {item.text && (
              <div className={cn("mt-2", dark ? "text-sand" : "text-muted")}>{item.text}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
  const quote = data.quote && (
    <blockquote
      className={cn(
        "mt-10 border-l-4 border-gold-400 pl-6 font-serif text-2xl leading-snug italic",
        dark ? "text-ivory" : "text-charcoal",
      )}
    >
      {data.quote}
    </blockquote>
  );
  if (variant === "sticky_intro") {
    return (
      <SectionShell section={section} labelledBy={id}>
        <div className="grid gap-14 lg:grid-cols-[1fr_1.4fr] lg:gap-20">
          <div className="lg:sticky lg:top-32 lg:self-start">
            <Eyebrow>{data.eyebrow}</Eyebrow>
            <Heading id={id}>{data.heading}</Heading>
            {data.description && (
              <p className={cn("mt-5 text-lg", dark ? "text-sand" : "text-muted")}>
                {data.description}
              </p>
            )}
            {quote}
          </div>
          {items}
        </div>
      </SectionShell>
    );
  }
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader id={id} data={data} />
      {quote}
      {items}
    </SectionShell>
  );
}

/** Native <details> keeps the FAQ keyboard-accessible and readable without JavaScript. */
export function FaqSection({ section }) {
  const { data, variant, key } = section;
  const { dark } = useSectionContext();
  const id = `${key}-heading`;
  const list = (
    <div
      className={cn(
        "divide-y border-y",
        dark ? "divide-ivory/10 border-ivory/10" : "divide-charcoal/10 border-charcoal/10",
      )}
    >
      {(data.items ?? []).map((item) => (
        <details key={item.question} className="group py-5">
          <summary
            className={cn(
              "flex cursor-pointer list-none items-start justify-between gap-6 font-serif text-xl font-medium [&::-webkit-details-marker]:hidden",
              dark ? "text-ivory" : "text-charcoal",
            )}
          >
            {item.question}
            <span
              aria-hidden
              className="mt-1 text-2xl leading-none text-gold-500 transition-transform group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <Paragraphs text={item.answer} className="mt-4 text-base" />
        </details>
      ))}
    </div>
  );
  const intro = (
    <div>
      <Eyebrow>{data.eyebrow}</Eyebrow>
      {data.heading && <Heading id={id}>{data.heading}</Heading>}
      <Paragraphs text={data.intro} className="mt-4" />
    </div>
  );
  return (
    <SectionShell
      section={section}
      labelledBy={data.heading ? id : undefined}
      label="Frequently asked questions"
      width={variant === "two_column" ? "default" : section.design?.width}
    >
      {variant === "two_column" ? (
        <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr] lg:gap-16">
          {intro}
          {list}
        </div>
      ) : (
        <>
          {intro}
          <div className="mt-10">{list}</div>
        </>
      )}
    </SectionShell>
  );
}

export function ResourceListSection({ section }) {
  const { data, variant, key } = section;
  const { design, dark } = useSectionContext();
  const id = `${key}-heading`;
  const items = data.items ?? [];
  return (
    <SectionShell section={section} labelledBy={id}>
      <SectionHeader id={id} data={data} />
      <ul
        className={cn(
          "mt-12 grid gap-8",
          variant === "list" ? "" : "sm:grid-cols-2 lg:grid-cols-3",
        )}
      >
        {items.map((item) => (
          <li
            key={item.title}
            className={cn(
              "flex flex-col overflow-hidden rounded-[var(--radius-card)]",
              cardClass(design.card_style, dark),
              variant === "list" && "sm:flex-row",
            )}
          >
            {item.media && (
              <div
                className={cn(
                  "relative shrink-0 bg-beige",
                  ASPECT[design.aspect_ratio ?? "landscape"],
                  variant === "list" && "sm:w-64",
                )}
              >
                <ContentImage
                  image={item.media}
                  fill
                  sizes={IMAGE_SIZES.card}
                  className="object-cover"
                />
              </div>
            )}
            <div className="flex flex-1 flex-col p-6 sm:p-7">
              <h3 className={cn("text-2xl font-medium", dark && "text-ivory")}>{item.title}</h3>
              {item.description && (
                <p className={cn("mt-3 flex-1", dark ? "text-sand" : "text-muted")}>
                  {item.description}
                </p>
              )}
              <SmartLink
                href={item.url}
                className={cn(
                  "mt-5 inline-flex font-semibold underline-offset-4 hover:underline",
                  dark ? "text-gold-300" : "text-sage-700",
                )}
              >
                {item.link_label || "Learn more"}
                <span className="sr-only">: {item.title}</span>
              </SmartLink>
            </div>
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}

export function AuthorIntroSection({ section }) {
  const { data, variant, key } = section;
  const { dark } = useSectionContext();
  const id = `${key}-heading`;
  const author = data.author;
  if (!author) return null;
  return (
    <SectionShell section={section} labelledBy={id} width="narrow">
      <div
        className={cn(
          "flex flex-col gap-8",
          variant === "split" ? "sm:flex-row sm:items-center" : "items-center text-center",
          variant === "card" && cn("rounded-[2rem] p-8 sm:p-12", cardClass("soft", dark)),
        )}
      >
        {author.image && (
          <div className="relative size-32 shrink-0 overflow-hidden rounded-full bg-beige sm:size-40">
            <ContentImage image={author.image} fill sizes="160px" className="object-cover" />
          </div>
        )}
        <div>
          <Eyebrow>{data.eyebrow}</Eyebrow>
          <Heading id={id} size="small">
            {author.name}
          </Heading>
          {author.bio && (
            <p className={cn("mt-4 text-lg", dark ? "text-sand" : "text-muted")}>{author.bio}</p>
          )}
          <Paragraphs text={data.body} className="mt-4" />
          {data.cta && <CtaButton cta={data.cta} fallback="outline" className="mt-6" />}
        </div>
      </div>
    </SectionShell>
  );
}

export function TestimonialsSection({ section }) {
  const { data, variant, key } = section;
  const { design, dark } = useSectionContext();
  const id = `${key}-heading`;
  const columns = {
    cards_3: "md:grid-cols-2 lg:grid-cols-3",
    cards_2: "md:grid-cols-2",
    single: "",
  }[variant];
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Testimonials">
      <SectionHeader id={id} data={data} />
      <ul
        className={cn(
          "grid gap-8",
          columns,
          (data.heading || data.eyebrow) && "mt-12",
          variant === "single" && "mx-auto max-w-3xl",
        )}
      >
        {(data.items ?? []).map((item) => (
          <li key={`${item.name}-${item.quote.slice(0, 20)}`}>
            <figure
              className={cn(
                "flex h-full flex-col rounded-[var(--radius-card)] p-7 sm:p-8",
                cardClass(design.card_style, dark),
              )}
            >
              <blockquote
                className={cn(
                  "flex-1 font-serif leading-snug",
                  variant === "single" ? "text-2xl" : "text-xl",
                  dark ? "text-ivory" : "text-charcoal",
                )}
              >
                <p>“{item.quote}”</p>
              </blockquote>
              <figcaption className="mt-6 flex items-center gap-4">
                {item.media && (
                  <span className="relative size-12 shrink-0 overflow-hidden rounded-full bg-beige">
                    <ContentImage image={item.media} fill sizes="48px" className="object-cover" />
                  </span>
                )}
                <span>
                  <span className={cn("block font-medium", dark ? "text-ivory" : "text-charcoal")}>
                    {item.name}
                  </span>
                  {item.role && (
                    <span className={cn("block text-sm", dark ? "text-sand" : "text-muted")}>
                      {item.role}
                    </span>
                  )}
                </span>
              </figcaption>
            </figure>
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}

export function StatisticsSection({ section }) {
  const { data, variant, key } = section;
  const { design, dark } = useSectionContext();
  const id = `${key}-heading`;
  const items = data.items ?? [];
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Key figures">
      <SectionHeader id={id} data={data} />
      <dl
        className={cn(
          "grid gap-8 sm:grid-cols-2",
          items.length >= 3 && "lg:grid-cols-3",
          items.length === 4 && "lg:grid-cols-4",
          (data.heading || data.eyebrow) && "mt-12",
        )}
      >
        {items.map((item) => (
          <div
            key={item.label}
            className={cn(
              "flex flex-col-reverse",
              design.align === "center" && "items-center text-center",
              variant === "cards" &&
                cn("rounded-[var(--radius-card)] p-7", cardClass("soft", dark)),
            )}
          >
            <dt className={cn("mt-2 text-lg", dark ? "text-sand" : "text-muted")}>{item.label}</dt>
            <dd
              className={cn(
                "font-serif text-5xl font-medium",
                dark ? "text-ivory" : "text-charcoal",
              )}
            >
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
      {data.footnote && (
        <p
          className={cn(
            "mt-8 text-sm",
            dark ? "text-sand" : "text-muted",
            design.align === "center" && "text-center",
          )}
        >
          {data.footnote}
        </p>
      )}
    </SectionShell>
  );
}

import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { cn } from "@/utils/format";
import { BACKGROUNDS, DEVICES, HEADING_SIZE, SPACING } from "./design";
import { HeroArt } from "./HeroArt";
import { CtaButton, Eyebrow } from "./primitives";
import { useSectionContext } from "./sectionContext";

const HERO_SIZE = {
  small: "text-4xl sm:text-5xl",
  default: "text-[2.75rem] leading-[1.05] sm:text-6xl lg:text-7xl",
  large: "text-5xl leading-[1.02] sm:text-7xl lg:text-8xl",
};

function HeroText({ data, centered, light }) {
  const { level } = useSectionContext();
  const Tag = level === 1 ? "h1" : "h2";
  const { design } = useSectionContext();
  return (
    <div className={cn(centered && "mx-auto max-w-3xl text-center")}>
      {data.eyebrow && (
        <p
          className={cn(
            "inline-flex items-center gap-3 text-sm font-semibold tracking-[0.16em] uppercase",
            light ? "text-gold-300" : "text-sage-700",
          )}
        >
          <span aria-hidden className="h-px w-10 bg-gold-400" />
          {data.eyebrow}
          {centered && <span aria-hidden className="h-px w-10 bg-gold-400" />}
        </p>
      )}
      <Tag
        className={cn(
          "mt-6 font-medium",
          HERO_SIZE[design.heading_size ?? "default"],
          light && "text-ivory",
        )}
      >
        {data.heading}
        {data.highlight && (
          <>
            {" "}
            <span className={cn("block italic", light ? "text-gold-300" : "text-sage-700")}>
              {data.highlight}
            </span>
          </>
        )}
      </Tag>
      {data.body && (
        <p
          className={cn(
            "mt-7 text-lg sm:text-xl",
            centered ? "mx-auto max-w-2xl" : "max-w-xl",
            light ? "text-sage-100" : "text-muted",
          )}
        >
          {data.body}
        </p>
      )}
      {(data.primary_cta || data.secondary_cta) && (
        <div
          className={cn(
            "mt-10 flex flex-col gap-3 sm:flex-row sm:items-center",
            centered && "justify-center",
          )}
        >
          <CtaButton cta={data.primary_cta} size="lg" arrow style={light ? "light" : undefined} />
          <CtaButton cta={data.secondary_cta} size="lg" fallback="outline" />
        </div>
      )}
    </div>
  );
}

/** Hero banner: split (text + illustration/image), centred, or full-width image. */
export function HeroSection({ section }) {
  const { data, variant } = section;
  const { design, dark, first } = useSectionContext();
  const background = design.background ?? "ivory";
  const base = cn(
    "relative overflow-hidden",
    BACKGROUNDS[background],
    DEVICES[section.devices ?? "all"],
  );

  if (variant === "full_width" && data.media) {
    return (
      <section className={cn(base, "isolate")} data-section="hero">
        <div className="absolute inset-0 -z-10">
          <ContentImage
            image={data.media}
            fill
            priority={first}
            sizes={IMAGE_SIZES.full}
            className="object-cover"
          />
          <div aria-hidden className="absolute inset-0 bg-charcoal/60" />
        </div>
        <Container
          size="wide"
          className={cn("relative", SPACING[design.spacing ?? "lg"], "lg:py-36")}
        >
          <HeroText data={data} centered={design.align === "center"} light />
        </Container>
      </section>
    );
  }

  if (variant === "centered") {
    return (
      <section className={base} data-section="hero">
        <Container size="wide" className={cn("relative", SPACING[design.spacing ?? "lg"])}>
          <HeroText data={data} centered light={dark} />
        </Container>
      </section>
    );
  }

  return (
    <section className={base} data-section="hero">
      {!dark && (
        <div
          aria-hidden
          className="pointer-events-none absolute top-0 right-0 h-full w-1/2 bg-gradient-to-l from-cream to-transparent"
        />
      )}
      <Container
        size="wide"
        className="relative grid items-center gap-12 py-16 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:py-28"
      >
        <HeroText data={data} centered={false} light={dark} />
        <div className="mx-auto w-full max-w-md lg:max-w-none">
          {data.media ? (
            <div className="relative aspect-[13/14] overflow-hidden rounded-t-[999px] rounded-b-[2rem] bg-beige">
              <ContentImage
                image={data.media}
                fill
                priority={first}
                sizes="(min-width: 1024px) 560px, 90vw"
                className="object-cover"
              />
            </div>
          ) : (
            <HeroArt />
          )}
        </div>
      </Container>
    </section>
  );
}

/** Title area for interior pages (with breadcrumbs for sub-pages). */
export function PageHeaderSection({ section, page }) {
  const { data, variant } = section;
  const { design, dark, first, level } = useSectionContext();
  const Tag = level === 1 ? "h1" : "h2";
  const centered = variant === "centered";
  const crumbs = (page?.breadcrumbs ?? []).length > 2 ? page.breadcrumbs : null;
  return (
    <header
      data-section="page_header"
      className={cn(
        "relative overflow-hidden border-b border-charcoal/[0.06]",
        BACKGROUNDS[design.background ?? "cream"],
        DEVICES[section.devices ?? "all"],
      )}
    >
      {!dark && (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-sage-100/80 blur-3xl"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-32 -left-16 size-72 rounded-full bg-gold-100/70 blur-3xl"
          />
        </>
      )}
      <Container
        className={cn(
          "relative",
          SPACING[design.spacing ?? "md"],
          variant === "with_image" && data.media && "grid items-center gap-10 lg:grid-cols-2",
        )}
      >
        <div className={cn(centered ? "mx-auto max-w-3xl text-center" : "max-w-3xl")}>
          {crumbs && (
            <Breadcrumbs
              items={crumbs.map((c) => ({ name: c.name, href: c.path }))}
              className={cn("mb-8", centered && "flex justify-center")}
            />
          )}
          <Eyebrow className="mb-4">{data.eyebrow}</Eyebrow>
          <Tag
            className={cn(
              "font-medium",
              design.heading_size
                ? HEADING_SIZE[design.heading_size]
                : "text-4xl sm:text-5xl lg:text-[3.5rem]",
              dark && "text-ivory",
            )}
          >
            {data.heading}
          </Tag>
          {data.intro && (
            <p className={cn("mt-5 text-lg sm:text-xl", dark ? "text-sage-100" : "text-muted")}>
              {data.intro}
            </p>
          )}
        </div>
        {variant === "with_image" && data.media && (
          <div className="relative aspect-[4/3] overflow-hidden rounded-[var(--radius-card)] bg-beige">
            <ContentImage
              image={data.media}
              fill
              priority={first}
              sizes="(min-width: 1024px) 560px, 100vw"
              className="object-cover"
            />
          </div>
        )}
      </Container>
    </header>
  );
}

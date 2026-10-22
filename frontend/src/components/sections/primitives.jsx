import { ArrowRight, ArrowUpRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Container } from "@/components/ui/Container";
import { cn } from "@/utils/format";
import { BACKGROUNDS, buttonVariant, DEVICES, HEADING_SIZE, SPACING } from "./design";
import { useSectionContext } from "./sectionContext";

/**
 * Section heading. `size` forces a preset; `defaultSizeClass` is a section's own
 * original size, used until an editor picks a heading size in Appearance.
 */
export function Heading({ id, className, children, size, defaultSizeClass }) {
  const { level, design, dark } = useSectionContext();
  const Tag = level === 1 ? "h1" : "h2";
  const preset = size ?? design.heading_size;
  return (
    <Tag
      id={id}
      className={cn(
        "font-medium",
        preset || !defaultSizeClass ? HEADING_SIZE[preset ?? "default"] : defaultSizeClass,
        dark && "text-ivory",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function Eyebrow({ children, className }) {
  const { dark } = useSectionContext();
  if (!children) return null;
  return (
    <p
      className={cn(
        "mb-3 text-sm font-semibold tracking-[0.14em] uppercase",
        dark ? "text-gold-300" : "text-sage-700",
        className,
      )}
    >
      {children}
    </p>
  );
}

/** Plain text with paragraphs separated by blank lines (never HTML). */
export function Paragraphs({ text, className, paragraphClassName, tone }) {
  const { dark } = useSectionContext();
  const parts = (text ?? "").split(/\n\s*\n/).filter((p) => p.trim());
  if (parts.length === 0) return null;
  return (
    <div
      className={cn(
        "space-y-5 text-lg",
        tone ?? (dark ? "text-sage-100" : "text-muted"),
        className,
      )}
    >
      {parts.map((p, i) => (
        <p key={i} className={paragraphClassName}>
          {p}
        </p>
      ))}
    </div>
  );
}

/** A CMS button: internal links use the router, external ones open safely. */
export function CtaButton({ cta, fallback = "primary", size, arrow = false, className, style }) {
  const { dark } = useSectionContext();
  if (!cta?.href || !cta?.label) return null;
  const variant = buttonVariant(style ?? cta.style, dark, fallback);
  const icon = arrow && <ArrowRight aria-hidden />;
  if (cta.external) {
    return (
      <a
        href={cta.href}
        target="_blank"
        rel="noopener noreferrer"
        className={buttonStyles({ variant, size, className })}
      >
        {cta.label}
        <ArrowUpRight aria-hidden />
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }
  return (
    <ButtonLink to={cta.href} variant={variant} size={size} className={className}>
      {cta.label}
      {icon}
    </ButtonLink>
  );
}

/** Section wrapper: approved background, spacing, width and device visibility. */
export function SectionShell({
  section,
  children,
  className,
  containerClassName,
  width,
  labelledBy,
  label,
}) {
  const design = section.design ?? {};
  const background = design.background ?? "ivory";
  return (
    <section
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : label}
      data-section={section.type}
      className={cn(
        BACKGROUNDS[background] ?? BACKGROUNDS.ivory,
        SPACING[design.spacing ?? "md"],
        DEVICES[section.devices ?? "all"],
        className,
      )}
    >
      <Container size={width ?? design.width ?? "default"} className={containerClassName}>
        {children}
      </Container>
    </section>
  );
}

/** Eyebrow + heading + description (+ optional link button) used by most sections. */
export function SectionHeader({ id, data, action, className }) {
  const { design, dark } = useSectionContext();
  const centered = design.align === "center";
  if (!data.heading && !data.eyebrow && !data.description) return null;
  return (
    <div
      className={cn(
        "flex flex-col gap-6",
        action && !centered && "md:flex-row md:items-end md:justify-between",
        centered && "items-center text-center",
        className,
      )}
    >
      <div className={cn("max-w-2xl", centered && "mx-auto")}>
        <Eyebrow>{data.eyebrow}</Eyebrow>
        {data.heading && <Heading id={id}>{data.heading}</Heading>}
        {data.description && (
          <p className={cn("mt-4 text-lg", dark ? "text-sand" : "text-muted")}>
            {data.description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

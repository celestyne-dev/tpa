import { ArrowRight, Mail } from "lucide-react";
import { Link } from "react-router";
import { formatMeasurement } from "@/components/partnerships/partnershipOptions";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Container } from "@/components/ui/Container";
import { cn, formatDate } from "@/utils/format";

/**
 * Building blocks shared by the company pages (About, Contact, Partner With Us, Advertise)
 * and by the matching CMS sections, so a page moved into the Page Builder looks the same.
 */

/** A link or button-styled link: in-page anchors (#id) scroll, site paths use the router. */
export function ActionLink({ href, children, variant = "primary", className, onClick }) {
  const styles = buttonStyles({ variant, className });
  if (!href) return null;
  if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("https://")) {
    return (
      <a href={href} className={styles} onClick={onClick}>
        {children}
      </a>
    );
  }
  return (
    <Link to={href} className={styles}>
      {children}
    </Link>
  );
}

/** The opening of a company page: breadcrumbs, label, serif title on a gold rule, actions. */
export function CompanyHero({ eyebrow, title, intro, breadcrumbs, actions, aside, className }) {
  return (
    <header className={cn("border-b border-charcoal/[0.08] bg-cream", className)}>
      <Container size="wide" className="py-10 sm:py-14 lg:py-16">
        {breadcrumbs && <Breadcrumbs items={breadcrumbs} className="mb-8" />}
        <div
          className={cn(
            aside && "grid gap-10 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-center",
          )}
        >
          <div className="max-w-3xl min-w-0">
            {eyebrow && (
              <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
                {eyebrow}
              </p>
            )}
            <h1 className="text-4xl leading-[1.08] font-medium text-balance sm:text-5xl lg:text-[3.5rem]">
              {title}
            </h1>
            <div aria-hidden className="mt-5 h-0.5 w-14 rounded-full bg-gold-400" />
            {intro && <p className="mt-5 max-w-2xl text-lg text-muted sm:text-xl">{intro}</p>}
            {actions && <div className="mt-8 flex flex-wrap gap-3">{actions}</div>}
          </div>
          {aside && <div className="min-w-0">{aside}</div>}
        </div>
      </Container>
    </header>
  );
}

/** Icon card used for values, editorial principles, formats and reasons. */
export function IconCard({ icon: Icon, title, children, tone = "light", as: Tag = "li" }) {
  return (
    <Tag
      className={cn(
        "h-full rounded-[var(--radius-card)] border p-6 sm:p-7",
        tone === "cream" ? "border-charcoal/10 bg-cream" : "border-charcoal/10 bg-white/60",
      )}
    >
      {Icon && (
        <span
          aria-hidden
          className="grid size-11 place-items-center rounded-full bg-sage-800 text-gold-300"
        >
          <Icon className="size-5" />
        </span>
      )}
      <h3 className={cn("text-xl font-medium", Icon && "mt-5")}>{title}</h3>
      {children && <div className="mt-2 text-muted">{children}</div>}
    </Tag>
  );
}

const measuredLine = (m) =>
  `Measured ${formatDate(m.measured_on)}${m.period_label ? ` (${m.period_label})` : ""}` +
  (m.source ? `. Source: ${m.source}.` : ".");

/** Verified audience figures: each with its platform, measurement date and source. */
export function MetricCards({ metrics, className }) {
  if (!metrics?.length) return null;
  return (
    <ul className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}>
      {metrics.map((m) => (
        <li
          key={`${m.metric_type}-${m.platform}-${m.measured_on}`}
          className="flex h-full flex-col rounded-[var(--radius-card)] border border-charcoal/10 bg-ivory p-6"
        >
          <p className="font-serif text-4xl font-medium text-charcoal">{formatMeasurement(m)}</p>
          <p className="mt-2 font-medium text-charcoal">
            {m.label}
            {m.platform ? ` · ${m.platform}` : ""}
          </p>
          <p className="mt-auto pt-3 text-sm text-muted">{measuredLine(m)}</p>
        </li>
      ))}
    </ul>
  );
}

/** One way to get in touch: heading, description, email address and an optional action. */
export function ContactCard({ icon: Icon, title, text, email, subject, action, fallback }) {
  const mailto =
    email && `mailto:${email}${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`;
  return (
    <li className="flex h-full flex-col rounded-[var(--radius-card)] border border-charcoal/10 bg-white/60 p-6 sm:p-7">
      {Icon && (
        <span
          aria-hidden
          className="grid size-11 place-items-center rounded-full bg-sage-100 text-sage-700"
        >
          <Icon className="size-5" />
        </span>
      )}
      <h2 className={cn("text-2xl font-medium", Icon && "mt-5")}>{title}</h2>
      {text && <p className="mt-2 text-muted">{text}</p>}
      <div className="mt-auto flex flex-col items-start gap-3 pt-6">
        {email ? (
          <a
            href={mailto}
            className="inline-flex max-w-full items-center gap-2 font-medium break-all text-sage-700 underline underline-offset-4 hover:text-sage-800"
          >
            <Mail aria-hidden className="size-4 shrink-0" />
            {email}
          </a>
        ) : (
          !action && fallback && <p className="text-sm text-muted">{fallback}</p>
        )}
        {action && (
          <ActionLink href={action.href} variant="outline">
            {action.label}
            <ArrowRight aria-hidden />
          </ActionLink>
        )}
      </div>
    </li>
  );
}

/** A clearly separated notice, e.g. that the site is not an emergency service. */
export function NoticePanel({ id, icon: Icon, title, children, tone = "important", action }) {
  return (
    <aside
      aria-labelledby={id}
      className={cn(
        "flex flex-col gap-4 rounded-[var(--radius-card)] border border-l-4 p-6 sm:flex-row sm:gap-6 sm:p-8",
        tone === "important"
          ? "border-gold-300 border-l-gold-500 bg-gold-100/50"
          : "border-sage-200 border-l-sage-600 bg-sage-50",
      )}
    >
      {Icon && (
        <span
          aria-hidden
          className="grid size-11 shrink-0 place-items-center rounded-full bg-ivory text-gold-700"
        >
          <Icon className="size-5" />
        </span>
      )}
      <div className="min-w-0">
        <h2 id={id} className="text-2xl font-medium">
          {title}
        </h2>
        <div className="mt-2 max-w-3xl space-y-3 text-ink">{children}</div>
        {action && <div className="mt-5">{action}</div>}
      </div>
    </aside>
  );
}

/** Closing invitation on a deep-green panel. */
export function CtaBand({ id, title, children, actions }) {
  return (
    <div className="rounded-[1.75rem] bg-sage-800 px-6 py-10 text-center sm:px-12 sm:py-12">
      <h2 id={id} className="text-3xl font-medium text-balance text-ivory sm:text-4xl">
        {title}
      </h2>
      {children && <div className="mx-auto mt-3 max-w-2xl text-lg text-sage-100">{children}</div>}
      {actions && <div className="mt-7 flex flex-wrap justify-center gap-3">{actions}</div>}
    </div>
  );
}

/** Splits text on blank lines into paragraphs. */
export function Paras({ text, className }) {
  return String(text ?? "")
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => (
      <p key={p.slice(0, 48)} className={className}>
        {p}
      </p>
    ));
}

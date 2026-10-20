import type { ReactNode } from "react";
import { Breadcrumbs, type BreadcrumbItem } from "./breadcrumbs";
import { Container } from "./container";

interface PageHeaderProps {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  children?: ReactNode;
}

/** Consistent page header for interior pages. */
export function PageHeader({
  eyebrow,
  title,
  description,
  breadcrumbs,
  children,
}: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden border-b border-charcoal/[0.06] bg-cream">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-sage-100/80 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-32 -left-16 size-72 rounded-full bg-gold-100/70 blur-3xl"
      />
      <Container className="relative py-14 sm:py-20">
        {breadcrumbs && <Breadcrumbs items={breadcrumbs} className="mb-8" />}
        <div className="max-w-3xl">
          {eyebrow && (
            <p className="mb-4 text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
              {eyebrow}
            </p>
          )}
          <h1 className="text-4xl font-medium sm:text-5xl lg:text-[3.5rem]">{title}</h1>
          {description && <p className="mt-5 text-lg text-muted sm:text-xl">{description}</p>}
          {children && <div className="mt-8">{children}</div>}
        </div>
      </Container>
    </header>
  );
}

import { cn } from "@/utils/format";
import { Breadcrumbs } from "./Breadcrumbs";
import { Container } from "./Container";

/**
 * The masthead of every interior page (archives, topics, authors, search, resources,
 * newsletter, about…): breadcrumbs, a small label, the serif page title on a short gold
 * rule and an introduction. `media` (a portrait or icon) sits beside the title on wider
 * screens; `children` (counts, a search box, actions) go underneath. `size` matches the
 * page's content width (editorial listings use "wide").
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  breadcrumbs,
  media,
  children,
  size = "default",
  className,
}) {
  return (
    <header className={cn("border-b border-charcoal/[0.08] bg-cream", className)}>
      <Container size={size} className="py-10 sm:py-14">
        {breadcrumbs && <Breadcrumbs items={breadcrumbs} className="mb-8" />}
        <div className={cn(media && "flex flex-col gap-6 sm:flex-row sm:items-center sm:gap-8")}>
          {media && <div className="shrink-0">{media}</div>}
          <div className="max-w-3xl min-w-0">
            {eyebrow && (
              <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
                {eyebrow}
              </p>
            )}
            <h1 className="text-4xl leading-[1.1] font-medium text-balance sm:text-5xl lg:text-[3.25rem]">
              {title}
            </h1>
            <div aria-hidden className="mt-5 h-0.5 w-14 rounded-full bg-gold-400" />
            {description && (
              <div className="mt-5 text-lg text-muted sm:text-xl [&_p+p]:mt-3">{description}</div>
            )}
          </div>
        </div>
        {children && <div className="mt-8">{children}</div>}
      </Container>
    </header>
  );
}

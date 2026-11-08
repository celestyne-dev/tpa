import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { cn } from "@/utils/format";

const SIZES = {
  sm: "text-xl sm:text-2xl",
  md: "text-2xl sm:text-3xl",
};

/**
 * The publication's section heading: a serif title on a thin rule, an optional small
 * label above it, a "view all" link on the right and a short description underneath.
 * The homepage builder's EditorialHeader uses the same look, so every page reads as one
 * publication.
 */
export function EditorialHeading({
  id,
  title,
  eyebrow,
  description,
  action,
  as: Heading = "h2",
  size = "md",
  className,
}) {
  return (
    <div className={cn("border-b border-charcoal/10 pb-4", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-2 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
              {eyebrow}
            </p>
          )}
          <Heading id={id} className={cn("font-medium text-balance", SIZES[size] ?? SIZES.md)}>
            {title}
          </Heading>
        </div>
        {action && (
          <Link
            to={action.to}
            aria-label={action.ariaLabel}
            className="inline-flex shrink-0 items-center gap-1.5 text-sm font-semibold text-sage-700 underline-offset-4 hover:underline"
          >
            {action.label}
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        )}
      </div>
      {description && <p className="mt-2 max-w-2xl text-muted">{description}</p>}
    </div>
  );
}

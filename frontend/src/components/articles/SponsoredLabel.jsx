import { cn } from "@/utils/format";

/**
 * The visible disclosure for paid content: "Sponsored Content" with the sponsor's name,
 * plus the disclosure text when there's room. Rendered from the same data in the browser
 * and in prerendered HTML.
 */
export function SponsoredLabel({ sponsorship, compact = false, className }) {
  if (!sponsorship) return null;
  return (
    <div className={cn("not-prose", className)} data-sponsored="true">
      <p className="inline-flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded-full bg-gold-100 px-3 py-1 font-semibold tracking-wide text-charcoal uppercase">
          {sponsorship.label || "Sponsored Content"}
        </span>
        {sponsorship.sponsor && (
          <span className="text-muted">
            {compact ? "" : "In partnership with "}
            <span className="font-medium text-charcoal">{sponsorship.sponsor}</span>
          </span>
        )}
      </p>
      {!compact && sponsorship.disclosure && (
        <p className="mt-2 max-w-2xl text-sm text-muted">{sponsorship.disclosure}</p>
      )}
    </div>
  );
}

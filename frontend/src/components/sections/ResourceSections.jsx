import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { ProductCover } from "@/components/products/ProductCover";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { EditorialHeader, EmptyPreviewNote } from "./ArticleSections";
import { SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

const CARD_TONE = { soft: "white", outline: "outline", flat: "flat" };

/**
 * A published resource: its cover (or the designed brand cover), type, Free or Premium,
 * title, description and a link to its page (where the price, currency and purchase
 * rules apply). The whole card is one link; there is no purchase button here.
 */
export function ResourceCard({
  resource,
  tone = "white",
  headingLevel: Heading = "h3",
  compact = false,
}) {
  return (
    <Card
      interactive
      tone={tone}
      className={cn(
        "group flex h-full overflow-hidden",
        // Homepage phones: the cover beside the text instead of above it.
        compact ? "flex-row sm:flex-col" : "flex-col",
      )}
    >
      <div
        className={cn(
          "bg-beige/60",
          compact
            ? "w-24 shrink-0 p-3 sm:w-auto sm:px-8 sm:pt-6 sm:pb-5"
            : "px-10 pt-8 pb-6 sm:px-12",
        )}
      >
        <ProductCover
          product={{ ...resource, format: resource.type_label }}
          className={cn(
            "mx-auto transition-transform duration-500 group-hover:-translate-y-1 motion-reduce:group-hover:translate-y-0",
            compact ? "sm:max-w-[8.5rem]" : "max-w-[11rem]",
          )}
          sizes={compact ? "(max-width: 639px) 72px, 136px" : "176px"}
        />
      </div>
      <div className={cn("flex min-w-0 flex-1 flex-col", compact ? "p-4 sm:p-5" : "p-6 sm:p-7")}>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
            {resource.type_label}
          </p>
          {resource.is_free ? (
            <Badge tone="sage">Free</Badge>
          ) : (
            // Paid resources reach the homepage only while the shop is switched on.
            <Badge tone="gold">Premium</Badge>
          )}
        </div>
        <Heading
          className={cn(
            "font-medium text-balance",
            compact ? "mt-2 text-lg leading-snug lg:text-xl" : "mt-3 text-xl sm:text-2xl",
          )}
        >
          <Link
            to={routes.product(resource.slug)}
            className="group-hover:text-sage-800 after:absolute after:inset-0 after:rounded-[var(--radius-card)] focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-offset-2 focus-visible:after:outline-sage-600"
          >
            {resource.title}
          </Link>
        </Heading>
        {resource.description && (
          <p
            className={cn(
              "flex-1 text-muted",
              compact ? "mt-2 line-clamp-2 text-[0.9375rem]" : "mt-3 line-clamp-3",
            )}
          >
            {resource.description}
          </p>
        )}
        <p
          aria-hidden
          className={cn(
            "inline-flex items-center gap-1.5 text-sm font-semibold text-sage-700",
            compact ? "mt-4" : "mt-5",
          )}
        >
          {resource.is_free ? "Get it free" : "See details and price"}
          <ArrowRight className="size-4" />
        </p>
      </div>
    </Card>
  );
}

/** Published, available resources (never drafts or "coming soon" items). Hidden when empty. */
export function ResourceShowcaseSection({ section }) {
  const { data, variant, key, design } = section;
  const { preview, compact } = useSectionContext();
  const resources = data.resources ?? [];
  if (resources.length === 0 && !preview) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Resources">
      <EditorialHeader id={id} data={data} />
      <div className={compact ? "mt-6" : "mt-8"}>
        {resources.length === 0 ? (
          <EmptyPreviewNote>
            No published resources are available to visitors at the moment.
          </EmptyPreviewNote>
        ) : (
          <ul
            className={cn(
              "grid sm:grid-cols-2",
              compact ? "gap-5 lg:gap-6" : "gap-8",
              variant === "cards_4" ? "lg:grid-cols-4" : "lg:grid-cols-3",
            )}
          >
            {resources.map((resource) => (
              <li key={resource.slug}>
                <ResourceCard
                  resource={resource}
                  tone={CARD_TONE[design?.card_style ?? "soft"]}
                  compact={compact}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </SectionShell>
  );
}

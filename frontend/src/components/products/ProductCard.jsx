import { Check } from "lucide-react";
import { Link } from "react-router";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { routes } from "@/config/navigation";
import { availabilityLabel } from "@/commerce/currency";
import { PriceTag } from "./PriceTag";
import { ProductCover } from "./ProductCover";

/**
 * Catalogue card. Coming-soon products are honest previews (no price, no purchase
 * action); products on sale show their price in the display currency.
 */
export function ProductCard({
  product,
  currency,
  showHighlights = false,
  showPrice = true,
  headingLevel: Heading = "h3",
}) {
  const href = product.slug ? routes.product(product.slug) : null;
  return (
    <Card tone="white" className="group relative flex h-full flex-col overflow-hidden">
      <div className="bg-cream px-8 pt-8 pb-7">
        <ProductCover product={product} className="mx-auto max-w-[14rem]" />
      </div>
      <div className="flex flex-1 flex-col p-6 sm:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={product.availability === "coming-soon" ? "gold" : "sage"}>
            {availabilityLabel[product.availability] ?? "Coming soon"}
          </Badge>
          <Badge tone="outline">{product.format}</Badge>
        </div>
        <Heading className="mt-4 text-2xl font-medium">
          {href ? (
            <Link
              to={href}
              className="after:absolute after:inset-0 hover:text-sage-800 focus-visible:outline-none"
            >
              {product.title}
            </Link>
          ) : (
            product.title
          )}
        </Heading>
        {product.subtitle && (
          <p className="mt-1 text-sm font-medium text-sage-700">{product.subtitle}</p>
        )}
        <p className="mt-3 text-muted">{product.description}</p>
        {showHighlights && product.highlights?.length > 0 && (
          <div className="mt-5">
            <p className="text-sm font-semibold text-charcoal">
              {product.availability === "coming-soon" ? "Planned inside" : "Inside"}
            </p>
            <ul className="mt-2 space-y-2 text-[0.95rem]">
              {product.highlights.map((h) => (
                <li key={h} className="flex gap-2.5">
                  <Check aria-hidden className="mt-1 size-4 shrink-0 text-sage-600" />
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {showPrice && currency && (
          <PriceTag product={product} currency={currency} className="mt-auto pt-5" />
        )}
      </div>
    </Card>
  );
}

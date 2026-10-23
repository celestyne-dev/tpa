import { priceIn } from "@/commerce/currency";
import { cn } from "@/utils/format";

/**
 * The price in the shopper's display currency, always with its ISO code
 * (e.g. "USD 12.00"). Never converts: shows a note when there is no price in
 * that currency.
 */
export function PriceTag({ product, currency, size = "md", className }) {
  if (product.availability === "free") {
    return <p className={cn("font-semibold text-sage-800", className)}>Free</p>;
  }
  if (product.availability !== "available") return null;
  const price = priceIn(product, currency);
  if (!price) {
    const others = product.prices.map((p) => p.currency).join(", ");
    return (
      <p className={cn("text-sm text-muted", className)}>
        {others ? `Not priced in ${currency} (available in ${others})` : "Price coming soon"}
      </p>
    );
  }
  return (
    <p className={cn("flex flex-wrap items-baseline gap-x-2", className)}>
      <span
        className={cn(
          "font-semibold text-charcoal",
          size === "lg" ? "text-2xl sm:text-3xl" : "text-lg",
        )}
      >
        {price.formatted}
      </span>
      {price.compare_at && (
        <span className="text-sm text-muted line-through">
          <span className="sr-only">Was </span>
          {price.compare_at.formatted}
        </span>
      )}
      {price.promotional && (
        <span className="text-xs font-semibold tracking-wide text-gold-700 uppercase">Offer</span>
      )}
    </p>
  );
}

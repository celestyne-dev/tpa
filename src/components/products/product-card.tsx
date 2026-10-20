import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { ProductPreview } from "@/types";
import { ProductCover } from "./product-cover";

const availabilityLabel: Record<ProductPreview["availability"], string> = {
  "coming-soon": "Coming soon",
  available: "Available",
  retired: "No longer available",
};

/** Preview card for planned products. No pricing or purchase actions until checkout exists. */
export function ProductCard({
  product,
  showHighlights = false,
  headingLevel: Heading = "h3",
}: {
  product: ProductPreview;
  showHighlights?: boolean;
  headingLevel?: "h2" | "h3";
}) {
  return (
    <Card tone="white" className="flex h-full flex-col overflow-hidden">
      <div className="bg-cream px-8 pt-8 pb-7">
        <ProductCover product={product} className="mx-auto max-w-[14rem]" />
      </div>
      <div className="flex flex-1 flex-col p-6 sm:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="gold">{availabilityLabel[product.availability]}</Badge>
          <Badge tone="outline">{product.format}</Badge>
        </div>
        <Heading className="mt-4 text-2xl font-medium">{product.title}</Heading>
        <p className="mt-1 text-sm font-medium text-sage-700">{product.subtitle}</p>
        <p className="mt-3 text-muted">{product.description}</p>
        {showHighlights && (
          <div className="mt-5">
            <p className="text-sm font-semibold text-charcoal">Planned inside</p>
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
      </div>
    </Card>
  );
}

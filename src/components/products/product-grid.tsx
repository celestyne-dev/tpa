import type { ProductPreview } from "@/types";
import { ProductCard } from "./product-card";

export function ProductGrid({
  products,
  showHighlights,
  headingLevel,
}: {
  products: ProductPreview[];
  showHighlights?: boolean;
  headingLevel?: "h2" | "h3";
}) {
  return (
    <ul className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
      {products.map((product) => (
        <li key={product.id}>
          <ProductCard
            product={product}
            showHighlights={showHighlights}
            headingLevel={headingLevel}
          />
        </li>
      ))}
    </ul>
  );
}

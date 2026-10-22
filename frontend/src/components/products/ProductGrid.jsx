import { ErrorState } from "@/components/ui/ErrorState";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { useProducts } from "@/hooks/useContent";
import { ProductCard } from "./ProductCard";

/** Upcoming product previews loaded from the API, with loading and error states. */
export function ProductGrid({ showHighlights, headingLevel }) {
  const { data: products, isLoading, isError, retry } = useProducts();
  if (isLoading) return <CardGridSkeleton count={4} className="lg:grid-cols-4" />;
  if (isError) return <ErrorState onRetry={retry} title="We couldn't load the product previews" />;
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

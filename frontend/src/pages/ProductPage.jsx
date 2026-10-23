import { useParams } from "react-router";
import { ProductDetail } from "@/components/products/ProductDetail";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { ErrorState } from "@/components/ui/ErrorState";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useProduct } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { NotFoundPage } from "./NotFoundPage";

export function ProductPage() {
  const { productSlug } = useParams();
  const { data: product, isLoading, isNotFound, isError, retry } = useProduct(productSlug);
  const { currency, setCurrency, currencies } = useDisplayCurrency();

  if (isNotFound) return <NotFoundPage />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Product unavailable" path={routes.product(productSlug)} noIndex />
        <ErrorState title="We couldn't load this product" onRetry={retry} />
      </Container>
    );
  if (isLoading || !product) return <ArticleSkeleton />;
  return (
    <ProductDetail
      product={product}
      currency={currency}
      currencies={currencies}
      onCurrency={setCurrency}
    />
  );
}

import { useParams } from "react-router";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { ProductCard } from "@/components/products/ProductCard";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useCollection } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { breadcrumbJsonLd } from "@/utils/structuredData";
import { NotFoundPage } from "./NotFoundPage";

export function CollectionPage() {
  const { slug } = useParams();
  const { data: collection, isLoading, isNotFound, isError, retry } = useCollection(slug);
  const { currency, setCurrency, currencies } = useDisplayCurrency();
  if (isNotFound) return <NotFoundPage />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Collection unavailable" path={routes.collection(slug)} noIndex />
        <ErrorState title="We couldn't load this collection" onRetry={retry} />
      </Container>
    );
  if (isLoading || !collection) return <CardGridSkeleton count={3} className="py-20" />;
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Shop", href: routes.shop },
    { name: collection.name, href: routes.collection(collection.slug) },
  ];
  return (
    <>
      <Seo
        title={collection.seo?.title ?? collection.name}
        description={collection.seo?.description ?? collection.description}
        path={routes.collection(collection.slug)}
        jsonLd={[breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader
        eyebrow="Collection"
        title={collection.name}
        description={collection.description}
        breadcrumbs={crumbs}
      />
      <Section aria-label={`Products in ${collection.name}`}>
        <div className="flex justify-end">
          <CurrencySwitcher currency={currency} currencies={currencies} onChange={setCurrency} />
        </div>
        <ul className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {collection.products.map((product) => (
            <li key={product.id}>
              <ProductCard product={product} currency={currency} showHighlights />
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

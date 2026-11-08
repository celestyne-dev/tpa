import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { ProductCard } from "@/components/products/ProductCard";
import { Seo } from "@/components/seo/Seo";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { EditorialHeading } from "@/components/ui/EditorialHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { LATEST_QUERY } from "@/data/queries";
import { useArticles, useProducts } from "@/hooks/useContent";
import { availableFreeResources } from "@/utils/resources";

export function FreeResourcesPage() {
  const { data: articles, isLoading, isError, retry } = useArticles(LATEST_QUERY);
  const products = useProducts();
  const resources = availableFreeResources(products.data);
  return (
    <>
      <Seo
        title="Free Personal Growth Resources"
        description="Discover the free reflection sheets, mindset exercises, and downloadable guides Think Positive Always is preparing, plus free articles you can read today."
        path={routes.freeResources}
      />
      <PageHeader
        eyebrow="Free resources"
        title="Free Tools to Support Your Growth"
        description="Practical, encouraging resources you can use at your own pace, alongside free articles you can read today."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Free Resources", href: routes.freeResources },
        ]}
      />

      {products.isLoading && !products.data && (
        <Section>
          <CardGridSkeleton count={3} />
        </Section>
      )}
      {resources.length > 0 && (
        <Section aria-labelledby="free-resources-heading">
          <EditorialHeading
            id="free-resources-heading"
            eyebrow="Free to download"
            title="Free resources"
            description="Each resource opens on its own page with what's included and how to get it."
            action={{ to: routes.resources, label: "Resource library" }}
          />
          <ul className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {resources.map((product) => (
              <li key={product.id}>
                <ProductCard product={product} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section tone="cream" aria-labelledby="read-now-heading">
        <EditorialHeading
          id="read-now-heading"
          eyebrow="Available now"
          title="Start with our free articles"
          description="Every article on Think Positive Always is free to read."
          action={{ to: routes.articles, label: "All articles" }}
        />
        <div className="mt-10">
          {isLoading && <CardGridSkeleton count={3} />}
          {isError && <ErrorState onRetry={retry} />}
          {articles && <ArticleGrid articles={articles} />}
        </div>
      </Section>
    </>
  );
}

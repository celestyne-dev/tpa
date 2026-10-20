import { ArrowRight } from "lucide-react";
import { routes } from "@/config/navigation";
import { ProductGrid } from "@/components/products/product-grid";
import { ButtonLink } from "@/components/ui/button";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import type { ProductPreview } from "@/types";

export function ProductsSection({ products }: { products: ProductPreview[] }) {
  return (
    <Section aria-labelledby="products-heading">
      <SectionHeading
        id="products-heading"
        eyebrow="Coming soon to the shop"
        title="Resources for Your Personal Growth Journey"
        description="Thoughtfully created guides and practical tools to help you take the next step."
        action={
          <ButtonLink href={routes.shop} variant="outline">
            Visit the shop
            <ArrowRight aria-hidden />
          </ButtonLink>
        }
      />
      <div className="mt-12">
        <ProductGrid products={products} />
      </div>
      <p className="mt-8 text-center text-sm text-muted">
        These titles are in development and not yet available to purchase.
      </p>
    </Section>
  );
}

import { ArrowRight } from "lucide-react";
import { ProductGrid } from "@/components/products/ProductGrid";
import { ButtonLink } from "@/components/ui/Button";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";

export function ProductsSection() {
  return (
    <Section aria-labelledby="products-heading">
      <SectionHeading
        id="products-heading"
        eyebrow="Coming soon to the shop"
        title="Resources for Your Personal Growth Journey"
        description="Thoughtfully created guides and practical tools to help you take the next step."
        action={
          <ButtonLink to={routes.shop} variant="outline">
            Visit the shop
            <ArrowRight aria-hidden />
          </ButtonLink>
        }
      />
      <div className="mt-12">
        <ProductGrid />
      </div>
      <p className="mt-8 text-center text-sm text-muted">
        These titles are in development and not yet available to purchase.
      </p>
    </Section>
  );
}

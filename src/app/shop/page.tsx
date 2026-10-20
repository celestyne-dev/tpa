import { BookOpen, Download, ShieldCheck, Sparkles } from "lucide-react";
import type { Metadata } from "next";
import { NewsletterPanel } from "@/components/newsletter/newsletter-panel";
import { ProductGrid } from "@/components/products/product-grid";
import { Notice } from "@/components/ui/draft-notice";
import { IconFeature } from "@/components/ui/icon-feature";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import { getProductPreviews } from "@/lib/content";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Shop — eBooks, Workbooks & Personal Growth Guides",
  description:
    "Preview upcoming Think Positive Always eBooks and workbooks on starting over, positive mindset, self-worth, and resilience. Coming soon.",
  path: routes.shop,
});

export default async function ShopPage() {
  const products = await getProductPreviews();
  return (
    <>
      <PageHeader
        eyebrow="The shop"
        title="Tools for Your Growth Journey"
        description="Original eBooks and workbooks designed to help you reflect, build confidence, and take meaningful steps forward. Our first titles are in development."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Shop", href: routes.shop },
        ]}
      />

      <Section aria-labelledby="catalog-heading">
        <SectionHeading
          id="catalog-heading"
          eyebrow="Upcoming titles"
          title="Coming soon"
          description="A preview of the first collection we are creating. Details may change as each title is finalised."
        />
        <div className="mt-8 max-w-3xl">
          <Notice title="The shop is not open yet">
            These products are not yet available to purchase, and no orders or payments are being
            accepted. Secure checkout and instant digital downloads will be introduced when the
            first titles launch.
          </Notice>
        </div>
        <div className="mt-12">
          <ProductGrid products={products} showHighlights headingLevel="h3" />
        </div>
      </Section>

      <Section tone="cream" aria-labelledby="shop-promise-heading">
        <SectionHeading
          id="shop-promise-heading"
          title="What to expect from our resources"
          align="center"
        />
        <ul className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <li>
            <IconFeature icon={BookOpen} title="Thoughtfully written" className="flex-col">
              Original content created with care, combining encouragement with practical guidance.
            </IconFeature>
          </li>
          <li>
            <IconFeature icon={Sparkles} title="Built for action" className="flex-col">
              Prompts, exercises, and reflections that help you apply what you read.
            </IconFeature>
          </li>
          <li>
            <IconFeature icon={Download} title="Digital delivery" className="flex-col">
              Planned as downloadable digital products you can use on your own schedule.
            </IconFeature>
          </li>
          <li>
            <IconFeature icon={ShieldCheck} title="Secure checkout" className="flex-col">
              Purchases will be processed through a verified payment provider when the shop opens.
            </IconFeature>
          </li>
        </ul>
      </Section>

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel description="Want to know when our first titles launch? The Positive Reset will share news about new resources once sign-ups open." />
      </Section>
    </>
  );
}

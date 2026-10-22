import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { ProductGrid } from "@/components/products/ProductGrid";
import { Seo } from "@/components/seo/Seo";
import { IconFeature } from "@/components/ui/IconFeature";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { shopPromise } from "@/data/marketing";

export function ShopPage() {
  return (
    <>
      <Seo
        title="Shop — eBooks, Workbooks & Personal Growth Guides"
        description="Preview upcoming Think Positive Always eBooks and workbooks on starting over, positive mindset, self-worth, and resilience. Coming soon."
        path={routes.shop}
      />
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
          <ProductGrid showHighlights />
        </div>
      </Section>

      <Section tone="cream" aria-labelledby="shop-promise-heading">
        <SectionHeading
          id="shop-promise-heading"
          title="What to expect from our resources"
          align="center"
        />
        <ul className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {shopPromise.map((item) => (
            <li key={item.title}>
              <IconFeature icon={item.icon} title={item.title} className="flex-col">
                {item.text}
              </IconFeature>
            </li>
          ))}
        </ul>
      </Section>

      <Section spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel description="Want to know when our first titles launch? The Positive Reset will share news about new resources once sign-ups open." />
      </Section>
    </>
  );
}

import { Check, FileText } from "lucide-react";
import { Link } from "react-router";
import { availabilityLabel } from "@/commerce/currency";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { Seo } from "@/components/seo/Seo";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import { breadcrumbJsonLd, productJsonLd } from "@/utils/structuredData";
import { CurrencySwitcher } from "./CurrencySwitcher";
import { PriceTag } from "./PriceTag";
import { ProductActions } from "./ProductActions";
import { ProductCard } from "./ProductCard";
import { ProductCover } from "./ProductCover";

const languageNames = {
  en: "English",
  "en-GB": "English (UK)",
  "en-US": "English (US)",
  sw: "Kiswahili",
};

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Public product detail. Also used by the admin's private draft preview
 * (`preview`: no SEO tags, no purchase actions).
 */
export function ProductDetail({ product, currency, currencies, onCurrency, preview = false }) {
  const setCurrency = onCurrency;
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Shop", href: routes.shop },
    { name: product.title, href: routes.product(product.slug) },
  ];
  const details = [
    ["Format", product.formats.length ? product.formats.join(", ") : product.format],
    ["Type", product.type_label],
    ["Language", languageNames[product.language] ?? product.language],
    product.edition && ["Edition", product.edition],
    product.page_count && ["Pages", String(product.page_count)],
    product.categories.length && ["Category", product.categories.map((c) => c.name).join(", ")],
  ].filter(Boolean);
  const priceCurrencies = product.prices.map((p) => p.currency);
  const switchable = currencies.filter((c) => priceCurrencies.includes(c));

  return (
    <>
      {!preview && (
        <Seo
          title={product.seo?.title ?? product.title}
          description={product.seo?.description ?? product.description}
          path={routes.product(product.slug)}
          noIndex={product.seo?.no_index}
          image={product.seo?.og_image ?? undefined}
          type="product"
          jsonLd={[productJsonLd(product), breadcrumbJsonLd(crumbs)]}
        />
      )}
      <article>
        <header className="bg-cream">
          <Container size="wide" className="pt-10 pb-14 sm:pt-14">
            <Breadcrumbs items={crumbs} />
            <div className="mt-10 grid items-start gap-12 lg:grid-cols-[minmax(0,22rem)_1fr] lg:gap-16">
              <div className="mx-auto w-full max-w-[18rem] lg:max-w-none">
                <ProductCover product={product} priority />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={product.availability === "coming-soon" ? "gold" : "sage"}>
                    {availabilityLabel[product.availability]}
                  </Badge>
                  <Badge tone="outline">{product.type_label}</Badge>
                </div>
                <h1 className="mt-5 text-4xl font-medium text-balance sm:text-5xl">
                  {product.title}
                </h1>
                {product.subtitle && (
                  <p className="mt-3 text-xl text-sage-700">{product.subtitle}</p>
                )}
                <p className="mt-5 max-w-2xl text-lg text-muted">{product.description}</p>
                {product.author && (
                  <p className="mt-4 text-sm text-muted">
                    By <span className="font-medium text-charcoal">{product.author.name}</span>
                  </p>
                )}
                <div className="mt-8 space-y-5 border-t border-charcoal/10 pt-6">
                  {product.availability === "available" && (
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <PriceTag product={product} currency={currency} size="lg" />
                      <CurrencySwitcher
                        currency={currency}
                        currencies={switchable}
                        onChange={setCurrency}
                      />
                    </div>
                  )}
                  {product.availability === "free" && <PriceTag product={product} />}
                  {preview ? (
                    <p className="text-sm text-muted">
                      Purchase buttons are hidden in the preview.
                    </p>
                  ) : (
                    <ProductActions product={product} currency={currency} />
                  )}
                </div>
              </div>
            </div>
          </Container>
        </header>

        <Container size="wide" className="grid gap-14 py-16 lg:grid-cols-[1fr_20rem] lg:gap-20">
          <div className="min-w-0">
            {product.body?.length > 0 && <ArticleBody blocks={product.body} />}
            {product.benefits.length > 0 && (
              <section aria-labelledby="benefits-heading" className="mt-12">
                <h2 id="benefits-heading" className="text-2xl font-medium">
                  {product.availability === "coming-soon"
                    ? "What it will help with"
                    : "What it helps with"}
                </h2>
                <ul className="mt-5 space-y-3">
                  {product.benefits.map((benefit) => (
                    <li key={benefit} className="flex gap-3">
                      <Check aria-hidden className="mt-1 size-5 shrink-0 text-sage-600" />
                      <span>{benefit}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {product.included.length > 0 && (
              <section aria-labelledby="included-heading" className="mt-12">
                <h2 id="included-heading" className="text-2xl font-medium">
                  What's included
                </h2>
                <ul className="mt-5 grid gap-4 sm:grid-cols-2">
                  {product.included.map((item) => (
                    <li
                      key={item.title}
                      className="rounded-2xl border border-charcoal/10 bg-white p-5"
                    >
                      <p className="font-medium">{item.title}</p>
                      {item.format && (
                        <p className="text-xs tracking-wide text-sage-700 uppercase">
                          {item.format}
                        </p>
                      )}
                      {item.description && (
                        <p className="mt-2 text-sm text-muted">{item.description}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {product.bundle_items?.length > 0 && (
              <section aria-labelledby="bundle-heading" className="mt-12">
                <h2 id="bundle-heading" className="text-2xl font-medium">
                  In this bundle
                </h2>
                <ul className="mt-5 space-y-2">
                  {product.bundle_items.map((item) => (
                    <li key={item.title} className="flex gap-3">
                      <Check aria-hidden className="mt-1 size-5 shrink-0 text-sage-600" />
                      {item.slug ? (
                        <Link
                          to={routes.product(item.slug)}
                          className="underline underline-offset-4"
                        >
                          {item.title}
                        </Link>
                      ) : (
                        <span>{item.title}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {product.sample_text && (
              <section
                aria-labelledby="sample-heading"
                className="mt-12 rounded-2xl bg-cream p-6 sm:p-8"
              >
                <h2 id="sample-heading" className="text-2xl font-medium">
                  A short sample
                </h2>
                <div className="mt-4 space-y-4 font-serif text-lg leading-relaxed whitespace-pre-line">
                  {product.sample_text}
                </div>
              </section>
            )}
            {product.gallery.length > 0 && (
              <section aria-label="Preview pages" className="mt-12 grid gap-4 sm:grid-cols-2">
                {product.gallery.map((image) => (
                  <ContentImage
                    key={image.src}
                    image={image}
                    sizes="(min-width: 768px) 360px, 100vw"
                  />
                ))}
              </section>
            )}
            {product.faq.length > 0 && (
              <section aria-labelledby="faq-heading" className="mt-12">
                <h2 id="faq-heading" className="text-2xl font-medium">
                  Questions
                </h2>
                <div className="mt-4 divide-y divide-charcoal/10 border-y border-charcoal/10">
                  {product.faq.map((item) => (
                    <details key={item.question} className="group py-4">
                      <summary className="cursor-pointer list-none font-medium marker:hidden">
                        {item.question}
                      </summary>
                      <p className="mt-3 whitespace-pre-line text-muted">{item.answer}</p>
                    </details>
                  ))}
                </div>
              </section>
            )}
          </div>
          <aside className="space-y-8">
            <section
              aria-labelledby="details-heading"
              className="rounded-2xl border border-charcoal/10 bg-white p-6"
            >
              <h2 id="details-heading" className="text-lg font-medium">
                Details
              </h2>
              <dl className="mt-4 space-y-3 text-sm">
                {details.map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <dt className="text-muted">{label}</dt>
                    <dd className="text-right font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
            {product.files.length > 0 && (
              <section
                aria-labelledby="files-heading"
                className="rounded-2xl border border-charcoal/10 bg-white p-6"
              >
                <h2 id="files-heading" className="text-lg font-medium">
                  Files you receive
                </h2>
                <ul className="mt-4 space-y-3 text-sm">
                  {product.files.map((file) => (
                    <li key={file.title} className="flex gap-3">
                      <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-600" />
                      <span>
                        <span className="font-medium">{file.title}</span>
                        <span className="block text-muted">
                          {file.format} · {formatSize(file.size_bytes)}
                          {file.description ? ` · ${file.description}` : ""}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {product.audience && (
              <section aria-labelledby="audience-heading">
                <h2 id="audience-heading" className="text-lg font-medium">
                  Who it's for
                </h2>
                <p className="mt-2 whitespace-pre-line text-muted">{product.audience}</p>
              </section>
            )}
          </aside>
        </Container>
      </article>

      {product.related?.length > 0 && (
        <Section tone="cream" aria-labelledby="related-heading">
          <SectionHeading id="related-heading" title="You may also like" />
          <ul className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {product.related.map((item) => (
              <li key={item.id}>
                <ProductCard product={item} currency={currency} />
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

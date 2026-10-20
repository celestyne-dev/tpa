import { toCardData } from "@/components/articles/to-card-data";
import { BrandIntro } from "@/components/home/brand-intro";
import { FeaturedArticles } from "@/components/home/featured-articles";
import { FinalCta } from "@/components/home/final-cta";
import { Hero } from "@/components/home/hero";
import { PartnershipsSection } from "@/components/home/partnerships-section";
import { ProductsSection } from "@/components/home/products-section";
import { TopicsSection } from "@/components/home/topics-section";
import { WhyTpa } from "@/components/home/why-tpa";
import { NewsletterPanel } from "@/components/newsletter/newsletter-panel";
import { Section } from "@/components/ui/section";
import { getFeaturedArticles, getFeaturedTopics, getProductPreviews } from "@/lib/content";

export default async function HomePage() {
  const [topics, featured, products] = await Promise.all([
    getFeaturedTopics(),
    getFeaturedArticles(3),
    getProductPreviews(),
  ]);

  return (
    <>
      <Hero />
      <BrandIntro />
      <TopicsSection topics={topics} />
      <FeaturedArticles articles={featured.map(toCardData)} />
      <ProductsSection products={products} />
      <Section tone="ivory" spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel />
      </Section>
      <WhyTpa />
      <PartnershipsSection />
      <FinalCta />
    </>
  );
}

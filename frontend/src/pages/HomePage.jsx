import { BrandIntro } from "@/components/home/BrandIntro";
import { FeaturedArticles } from "@/components/home/FeaturedArticles";
import { FinalCta } from "@/components/home/FinalCta";
import { Hero } from "@/components/home/Hero";
import { PartnershipsSection } from "@/components/home/PartnershipsSection";
import { ProductsSection } from "@/components/home/ProductsSection";
import { TopicsSection } from "@/components/home/TopicsSection";
import { WhyTpa } from "@/components/home/WhyTpa";
import { NewsletterPanel } from "@/components/newsletter/NewsletterPanel";
import { Seo } from "@/components/seo/Seo";
import { Section } from "@/components/ui/Section";
import { useSite } from "@/hooks/useContent";

export function HomePage() {
  const { data: site } = useSite();
  return (
    <>
      <Seo path="/" />
      <Hero />
      <BrandIntro followersLabel={site?.community?.linkedin_followers_label} />
      <TopicsSection />
      <FeaturedArticles />
      <ProductsSection />
      <Section tone="ivory" spacing="sm" size="wide" aria-label="Newsletter">
        <NewsletterPanel />
      </Section>
      <WhyTpa />
      <PartnershipsSection />
      <FinalCta />
    </>
  );
}

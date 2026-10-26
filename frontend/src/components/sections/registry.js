import {
  ArticleCollectionSection,
  FeaturedArticlesSection,
  LatestArticlesSection,
  TopicsSection,
} from "./ArticleSections";
import {
  AuthorIntroSection,
  FaqSection,
  FeatureListSection,
  ImageTextSection,
  MessageSection,
  QuoteSection,
  ResourceListSection,
  RichTextSection,
  StatisticsSection,
  TestimonialsSection,
} from "./ContentSections";
import {
  BrandIntroSection,
  ContactDetailsSection,
  CtaSection,
  NewsletterSection,
  LeadMagnetSection,
  PartnershipSection,
  ProductsSection,
  PromoBannerSection,
} from "./EngagementSections";
import { HeroSection, PageHeaderSection } from "./IntroSections";
import {
  AffiliateRecommendationsSection,
  BrandSpotlightSection,
  MediaKitSummarySection,
  PartnershipInquirySection,
  SponsorLogosSection,
  SponsoredBannerSection,
} from "./PartnershipSections";

/**
 * Approved section components, keyed by section type (mirrors SECTION_TYPES in
 * backend/app/cms/sections.py). The CMS can only choose from these: it never
 * supplies markup or code. Unknown types are skipped, so an older frontend
 * build never breaks on a newer section type.
 */
export const SECTION_COMPONENTS = {
  hero: HeroSection,
  page_header: PageHeaderSection,
  brand_intro: BrandIntroSection,
  featured_articles: FeaturedArticlesSection,
  latest_articles: LatestArticlesSection,
  article_collection: ArticleCollectionSection,
  topics_grid: TopicsSection,
  quote: QuoteSection,
  inspirational_message: MessageSection,
  image_text: ImageTextSection,
  newsletter_cta: NewsletterSection,
  lead_magnet_signup: LeadMagnetSection,
  product_previews: ProductsSection,
  promo_banner: PromoBannerSection,
  call_to_action: CtaSection,
  testimonials: TestimonialsSection,
  statistics: StatisticsSection,
  faq: FaqSection,
  rich_text: RichTextSection,
  feature_list: FeatureListSection,
  partnership_cta: PartnershipSection,
  author_intro: AuthorIntroSection,
  resource_list: ResourceListSection,
  contact_details: ContactDetailsSection,
  sponsor_logos: SponsorLogosSection,
  sponsored_banner: SponsoredBannerSection,
  brand_spotlight: BrandSpotlightSection,
  affiliate_recommendations: AffiliateRecommendationsSection,
  media_kit_summary: MediaKitSummarySection,
  partnership_inquiry: PartnershipInquirySection,
};

/** Section types that provide the page's main heading (h1). */
export const TITLE_SECTIONS = new Set(["hero", "page_header"]);

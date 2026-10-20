/**
 * Core content types. These mirror the shape the future CMS / database
 * (Batch 02+) will return, so pages can switch from local data to queries
 * without changing component contracts.
 */

export type ISODateString = string;

export interface ImageAsset {
  /** Path under /public or an absolute URL from future storage. */
  src: string;
  alt: string;
  width: number;
  height: number;
}

export type TopicIconName =
  "sun" | "sprout" | "gem" | "sunrise" | "heart-handshake" | "calendar-check" | "flame" | "leaf";

export interface Topic {
  slug: string;
  name: string;
  /** One-line summary used on cards. */
  description: string;
  /** Longer introduction used on the topic page. */
  intro: string;
  icon: TopicIconName;
  /** Topics flagged as featured appear on the homepage. */
  featured: boolean;
  seo?: SeoOverrides;
}

export interface Author {
  slug: string;
  name: string;
}

/**
 * Article body is stored as structured blocks rather than raw HTML so it can
 * be rendered safely and later mapped to/from a rich-text CMS format.
 */
export type ArticleBlock =
  | { type: "paragraph"; text: string }
  | { type: "heading"; text: string; id?: string }
  | { type: "list"; ordered?: boolean; items: string[] }
  | { type: "quote"; text: string; cite?: string };

/** Origin of an article — distinguishes sample content from real/migrated content. */
export type ArticleSource = "sample" | "original" | "migrated";

export interface ArticleLegacy {
  /** Path on the previous website, e.g. "/2023/05/some-post/". */
  originalPath?: string;
  /** Full original URL, if known. */
  originalUrl?: string;
  /** Canonical URL to preserve (if content should keep pointing elsewhere). */
  canonicalUrl?: string;
  importedAt?: ISODateString;
}

export interface SeoOverrides {
  title?: string;
  description?: string;
  canonicalUrl?: string;
  noIndex?: boolean;
  ogImage?: ImageAsset;
}

export type PublicationStatus = "draft" | "published" | "archived";

export interface Article {
  /** Stable identifier (will become the database primary key). */
  id: string;
  /** URL slug. Preserve original slugs when migrating. */
  slug: string;
  title: string;
  subtitle?: string;
  excerpt: string;
  topicSlug: Topic["slug"];
  /** Optional secondary topics for cross-linking. */
  secondaryTopicSlugs?: Topic["slug"][];
  tags?: string[];
  author: Author;
  publishedAt: ISODateString;
  updatedAt?: ISODateString;
  status: PublicationStatus;
  featured: boolean;
  /** Minutes; computed from body when omitted. */
  readingTimeMinutes?: number;
  image: ImageAsset;
  body: ArticleBlock[];
  source: ArticleSource;
  legacy?: ArticleLegacy;
  seo?: SeoOverrides;
}

export type ProductFormat = "eBook" | "Workbook" | "Journal" | "Planner" | "Guide" | "Course";

export type ProductAvailability = "coming-soon" | "available" | "retired";

export interface ProductPreview {
  id: string;
  slug: string;
  title: string;
  subtitle: string;
  description: string;
  format: ProductFormat;
  availability: ProductAvailability;
  topicSlugs: Topic["slug"][];
  /** What the reader can expect inside — planned contents, not claims. */
  highlights: string[];
  /** Visual theme for the designed cover placeholder until real artwork exists. */
  coverTheme: "sage" | "olive" | "gold" | "charcoal";
  image?: ImageAsset;
}

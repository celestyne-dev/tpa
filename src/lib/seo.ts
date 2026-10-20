import type { Metadata } from "next";
import { siteConfig } from "@/config/site";
import { env } from "@/lib/env";
import type { ImageAsset } from "@/types";

interface PageMetadataInput {
  title: string;
  description: string;
  /** Path relative to the site root, e.g. "/about". */
  path: string;
  image?: ImageAsset;
  type?: "website" | "article";
  publishedTime?: string;
  modifiedTime?: string;
  authors?: string[];
  section?: string;
  tags?: string[];
  /** Overrides the computed canonical (e.g. preserved legacy canonical). */
  canonicalUrl?: string;
  noIndex?: boolean;
}

/** Builds consistent per-page metadata: title, description, canonical, OG and Twitter. */
export function buildMetadata({
  title,
  description,
  path,
  image,
  type = "website",
  publishedTime,
  modifiedTime,
  authors,
  section,
  tags,
  canonicalUrl,
  noIndex,
}: PageMetadataInput): Metadata {
  const canonical = canonicalUrl ?? path;
  const images = image
    ? [{ url: image.src, width: image.width, height: image.height, alt: image.alt }]
    : undefined;

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      title,
      description,
      url: path,
      siteName: siteConfig.name,
      locale: siteConfig.locale,
      type,
      ...(images && { images }),
      ...(type === "article" && { publishedTime, modifiedTime, authors, section, tags }),
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      ...(images && { images: images.map((i) => i.url) }),
    },
    ...(noIndex && { robots: { index: false, follow: true } }),
  };
}

export const isIndexable = env.allowIndexing;

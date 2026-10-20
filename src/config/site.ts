import { env } from "@/lib/env";

/**
 * Site identity. Only verified facts belong here — never invent contact
 * details, addresses, founding dates or audience numbers.
 */
export const siteConfig = {
  name: "Think Positive Always",
  shortName: "TPA",
  url: env.siteUrl,
  locale: "en_US",
  language: "en",
  tagline:
    "Practical inspiration for a stronger mindset, more confidence, and intentional personal growth.",
  description:
    "Think Positive Always offers practical encouragement, mindset insights, personal growth articles and thoughtful resources to help you build confidence and grow through every season of life.",
  mission:
    "Helping people develop a healthier mindset, navigate life's challenges, build confidence, and move forward through encouragement, thoughtful content, and useful personal development tools.",
  keywords: [
    "positive mindset",
    "personal growth",
    "personal development",
    "confidence",
    "self-worth",
    "resilience",
    "motivation",
    "intentional living",
    "emotional well-being",
  ],
  /** Verified community figure. Refers to LinkedIn followers only. */
  community: {
    linkedinFollowersLabel: "280,000+",
    linkedinFollowersText: "more than 280,000 people who follow Think Positive Always on LinkedIn",
  },
  newsletter: {
    name: "The Positive Reset",
    cadence: "weekly",
    /** Flip to true only when a real subscription provider is integrated. */
    isOpen: false,
  },
  contact: {
    email: env.contactEmail,
    partnershipsEmail: env.partnershipsEmail ?? env.contactEmail,
  },
  /** Media kit is not yet created. Set a URL here once it exists. */
  mediaKitUrl: undefined as string | undefined,
  themeColor: "#f7f2e8",
} as const;

export type SiteConfig = typeof siteConfig;

/**
 * Build-time public configuration. Only VITE_* values are available here and
 * they are embedded in the bundle — never place secrets in them.
 * Business settings (contact, social links, newsletter status) come from the
 * Flask API (GET /api/v1/site).
 */
const env = import.meta.env;

function normaliseOrigin(value) {
  try {
    return value ? new URL(value).origin : undefined;
  } catch {
    return undefined;
  }
}

export const siteConfig = {
  name: "Think Positive Always",
  shortName: "TPA",
  url: normaliseOrigin(env.VITE_SITE_URL) ?? "http://localhost:5173",
  allowIndexing: env.VITE_ALLOW_INDEXING === "true",
  apiBaseUrl: env.VITE_API_BASE_URL || "/api/v1",
  locale: "en_US",
  language: "en",
  defaultTitle: "Think Positive Always — Practical Inspiration for Personal Growth",
  tagline:
    "Practical inspiration for a stronger mindset, more confidence, and intentional personal growth.",
  description:
    "Think Positive Always offers practical encouragement, mindset insights, personal growth articles and thoughtful resources to help you build confidence and grow through every season of life.",
  defaultOgImage: {
    src: "/og/default.png",
    width: 1200,
    height: 630,
    alt: "Think Positive Always",
  },
  newsletterName: "The Positive Reset",
};

/**
 * Centralised, typed access to public environment variables.
 * Every value is optional: the site must build and run without any of them.
 */

const DEV_FALLBACK_URL = "http://localhost:3000";

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function normaliseUrl(value: string | undefined): string | undefined {
  const raw = clean(value);
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    return url.origin;
  } catch {
    return undefined;
  }
}

function normaliseEmail(value: string | undefined): string | undefined {
  const raw = clean(value);
  return raw && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw) ? raw : undefined;
}

export const env = {
  siteUrl: normaliseUrl(process.env.NEXT_PUBLIC_SITE_URL) ?? DEV_FALLBACK_URL,
  allowIndexing: process.env.NEXT_PUBLIC_ALLOW_INDEXING === "true",
  contactEmail: normaliseEmail(process.env.NEXT_PUBLIC_CONTACT_EMAIL),
  partnershipsEmail: normaliseEmail(process.env.NEXT_PUBLIC_PARTNERSHIPS_EMAIL),
  social: {
    linkedin: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_LINKEDIN),
    instagram: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_INSTAGRAM),
    facebook: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_FACEBOOK),
    x: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_X),
    youtube: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_YOUTUBE),
    tiktok: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_TIKTOK),
    pinterest: normaliseSocial(process.env.NEXT_PUBLIC_SOCIAL_PINTEREST),
  },
} as const;

function normaliseSocial(value: string | undefined): string | undefined {
  const raw = clean(value);
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

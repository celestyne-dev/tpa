/**
 * Legacy URL → new URL mapping for the future article migration.
 *
 * Add one entry per moved URL. These are consumed by next.config.ts and
 * emitted as HTTP 308 (permanent) redirects, preserving SEO signals.
 *
 * Example:
 *   { source: "/2023/05/how-to-start-again", destination: "/articles/how-to-start-again", permanent: true }
 *
 * Kept free of path aliases so next.config.ts can import it directly.
 */
export interface RedirectRule {
  source: string;
  destination: string;
  permanent: boolean;
}

export const redirects: RedirectRule[] = [];

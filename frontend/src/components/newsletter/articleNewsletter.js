/** The sidebar form's email field, so the end-of-article panel can move focus to it. */
export const SIDEBAR_NEWSLETTER_EMAIL_ID = "sidebar-newsletter-email";

/**
 * Whether the article sidebar shows The Positive Reset form on wide screens: a newsletter
 * section that isn't phone-only and isn't offering a free resource instead.
 */
export function sidebarHasNewsletterForm(sections) {
  return (sections ?? []).some(
    (s) => s.type === "newsletter_cta" && s.devices !== "mobile" && !s.data?.lead_magnet?.available,
  );
}

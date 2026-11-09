/**
 * Copy for the built-in company pages, read from data/company/companyPages.json. The CMS
 * page templates (backend/app/cms/templates.py) are built from an identical copy of that
 * file (backend/app/cms/company_pages.json) and a backend test checks the two match, so a
 * page created from a template starts with exactly the wording the built-in page shows.
 * Nothing here states figures, achievements or biography details: audience figures come
 * only from verified, dated measurements (Partnerships › Audience metrics).
 */
import { SECTION_ICONS } from "@/components/sections/icons";
import copy from "./company/companyPages.json";

const withIcons = (items) => items.map((item) => ({ ...item, icon: SECTION_ICONS[item.icon] }));

export const about = {
  ...copy.about,
  values: { ...copy.about.values, items: withIcons(copy.about.values.items) },
  editorial: { ...copy.about.editorial, items: withIcons(copy.about.editorial.items) },
};

export const contact = { ...copy.contact, cards: withIcons(copy.contact.cards) };

export const partner = {
  ...copy.partner,
  formats: { ...copy.partner.formats, items: withIcons(copy.partner.formats.items) },
  reasons: { ...copy.partner.reasons, items: withIcons(copy.partner.reasons.items) },
};

export const advertise = copy.advertise;

/** The About story with the community wording from Settings (or the default). */
export const aboutStory = (community) =>
  about.story.body.replace("{community}", community || about.story.community_default);

export const METRIC_GROUPS = {
  social: ["social_followers"],
  website: ["website_users", "website_pageviews"],
  newsletter: ["newsletter_subscribers", "email_open_rate"],
};

export const byGroup = (metrics, group) =>
  (metrics ?? []).filter((m) => !group || METRIC_GROUPS[group]?.includes(m.metric_type));

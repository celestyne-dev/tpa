import { label } from "../../components/partnerships/formValues";

const opts = (values) => values.map((v) => ({ value: v, label: label(v) }));

export const PARTNER_STATUSES = opts(["prospect", "active", "inactive", "archived"]);
export const PARTNERSHIP_TYPES = opts([
  "sponsorship",
  "advertising",
  "affiliate",
  "content_collaboration",
  "newsletter_sponsorship",
  "event",
  "other",
]);
export const INQUIRY_STATUSES = opts(["new", "reviewed", "declined", "spam"]);
export const PLACEMENT_TYPES = opts([
  "homepage_sponsor",
  "article_sponsor",
  "in_article_banner",
  "sidebar",
  "footer_promotion",
  "newsletter_sponsor",
  "sponsored_article",
  "brand_spotlight",
  "landing_page",
]);
export const CHANNELS = opts(["website", "newsletter", "social", "other"]);
export const PRICING_MODELS = opts(["fixed_fee", "per_placement", "package", "cpm"]);
export const ACCOUNT_STATUSES = opts([
  "not_applied",
  "applied",
  "approved",
  "rejected",
  "paused",
  "closed",
]);
export const COMMISSION_STATUSES = opts(["reported", "approved", "paid", "reversed"]);
export const METRIC_TYPES = [
  { value: "social_followers", label: "Social media followers" },
  { value: "newsletter_subscribers", label: "Newsletter subscribers (confirmed)" },
  { value: "website_users", label: "Website users" },
  { value: "website_pageviews", label: "Website page views" },
  { value: "email_open_rate", label: "Email open rate (%)" },
  { value: "other", label: "Other" },
];

export const toOptions = (rows, text = (r) => r.name) =>
  (rows ?? []).map((r) => ({ value: String(r.id), label: text(r) }));

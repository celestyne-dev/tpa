export const COLLABORATION_TYPES = [
  { value: "sponsorship", label: "Sponsorship" },
  { value: "advertising", label: "Advertising" },
  { value: "affiliate", label: "Affiliate partnership" },
  { value: "content_collaboration", label: "Content collaboration" },
  { value: "newsletter_sponsorship", label: "Newsletter sponsorship" },
  { value: "event", label: "Event" },
  { value: "other", label: "Something else" },
];

export const BUDGET_RANGES = [
  { value: "", label: "Prefer not to say" },
  { value: "under_1000", label: "Under 1,000 (USD or equivalent)" },
  { value: "1000_5000", label: "1,000 – 5,000" },
  { value: "5000_15000", label: "5,000 – 15,000" },
  { value: "15000_plus", label: "15,000 or more" },
  { value: "not_sure", label: "Not sure yet" },
];

export const PRIVACY_NOTICE =
  "We use these details only to reply to your inquiry and to manage a possible partnership. " +
  "They are seen by our partnerships team, never sold or added to mailing lists. See our " +
  "privacy policy for how long we keep them and how to ask us to delete them.";

/** Format integer minor units with their currency, never converting between currencies. */
export function formatMinor(minor, currency) {
  if (minor == null) return "—";
  const digits = ["JPY", "KRW", "UGX", "RWF"].includes(currency) ? 0 : 2;
  const amount = (minor / 10 ** digits).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${currency} ${amount}`;
}

/** "1,200" for counts; percentages keep one decimal. */
export function formatMeasurement(metric) {
  if (metric.metric_type === "email_open_rate") return `${metric.value.toFixed(1)}%`;
  return Math.round(metric.value).toLocaleString("en-US");
}

/** Paid links: rel="sponsored" plus noopener/noreferrer for external targets. */
export function sponsoredRel(href = "") {
  return /^https?:\/\//i.test(href) ? "sponsored noopener noreferrer" : "sponsored";
}

/**
 * Creatives the server rendered as live (approved, inside their dates). After hydration the
 * browser also hides any whose window has passed, until the next static rebuild.
 */
export function liveOnly(creatives, now) {
  const list = creatives ?? [];
  if (now == null) return list;
  return list.filter(
    (c) =>
      (!c.starts_at || Date.parse(c.starts_at) <= now) &&
      (!c.ends_at || now < Date.parse(c.ends_at)),
  );
}

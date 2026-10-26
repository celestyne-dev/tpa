export const SUBSCRIBER_STATUS = {
  pending: "Awaiting confirmation",
  subscribed: "Subscribed",
  unsubscribed: "Unsubscribed",
  bounced: "Bounced",
  complained: "Complained",
  quarantined: "Quarantined (not mailed)",
};

export const SIGNUP_SOURCES = {
  homepage: "Homepage",
  footer: "Footer",
  newsletter_page: "Newsletter page",
  article: "Article",
  page_section: "Page section",
  lead_magnet: "Free resource",
  resource_page: "Resource page",
  account: "Account registration or settings",
  import: "Import",
  admin: "Admin",
  other: "Other",
};

export const PREFERENCES = {
  weekly: "Weekly edition",
  daily: "Daily encouragement",
  reflection: "Weekly reflection",
  resources: "Free resources",
  products: "New digital products",
};

export const CAMPAIGN_STATUS = {
  draft: "Draft",
  approved: "Approved",
  scheduled: "Scheduled",
  sending: "Sending",
  sent: "Sent",
  cancelled: "Cancelled",
};

export const MESSAGE_STATUS = {
  queued: "Queued",
  sending: "Sending",
  accepted: "Accepted by provider",
  delivered: "Delivered (confirmed)",
  bounced: "Bounced",
  complained: "Complaint",
  failed: "Failed",
  unknown: "Unknown (interrupted)",
  cancelled: "Cancelled",
  suppressed: "Suppressed",
  skipped: "Skipped (test mode)",
};

/** Block types the email renderer supports (keys of BLOCK_TEMPLATES). */
export const EMAIL_BLOCKS = [
  "paragraph",
  "heading",
  "bulleted",
  "numbered",
  "quote",
  "callout",
  "image",
  "button",
  "cta",
  "divider",
];

export const SEGMENT_FIELDS = {
  source: { label: "Signup source", ops: { in: "is one of", not_in: "is not one of" } },
  preference: { label: "Preference", ops: { has: "includes", not_has: "does not include" } },
  interest: { label: "Interest", ops: { has: "includes", not_has: "does not include" } },
  tag: { label: "Tag", ops: { has: "has", not_has: "does not have" } },
  confirmed: { label: "Confirmed", ops: { after: "on or after", before: "before" } },
  consent: { label: "Consent given", ops: { after: "on or after", before: "before" } },
  engaged: {
    label: "Engaged (confirmed, updated preferences or claimed a resource)",
    ops: { within_days: "within the last N days", not_within_days: "not within N days" },
  },
  purchased_product: {
    label: "Bought product (id)",
    ops: { has: "bought", not_has: "did not buy" },
  },
};

export const MODE_LABELS = {
  disabled: "Sending is disabled — nothing will be sent.",
  test: "Test mode — email reaches only the configured test recipients.",
  live: "Live — approved campaigns go to real subscribers.",
};

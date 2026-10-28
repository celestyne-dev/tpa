import { vi } from "vitest";

const MEASUREMENT = {
  visitors:
    "Estimated per day from a salted hash that changes daily (no cookies). A person visiting on several days is counted once per day, so ranges show the sum of daily visitors, not unique people.",
  sessions: "Not measured: without cookies, sessions can't be identified reliably.",
  exclusions: "Bots, automated browsers, admin and account pages are not counted.",
};
const TRACKING = {
  enabled: true,
  respects_do_not_track: true,
  raw_retention_days: 90,
  aggregate_retention_days: 760,
  pending_rollup_days: 0,
};

export const TRAFFIC = {
  range: { from: "2026-10-22", to: "2026-10-28", granularity: "day" },
  has_data: true,
  totals: { views: 1234, visitors_daily_sum: 456, days_with_data: 7, average_daily_views: 176.3 },
  series: [
    { period: "2026-10-27", views: 200, visitors: 80 },
    { period: "2026-10-28", views: 1034, visitors: 376 },
  ],
  pages: [{ path: "/articles/calm-mornings", page_type: "article", views: 600, visitors: 200 }],
  page_types: [{ page_type: "article", views: 900, visitors: 300 }],
  articles: [
    {
      id: 1,
      title: "Calm mornings",
      slug: "calm-mornings",
      topic: "Positive Mindset",
      views: 600,
      visitors: 200,
    },
  ],
  categories: [
    {
      topic: "Positive Mindset",
      slug: "positive-mindset",
      views: 650,
      article_views: 600,
      topic_page_views: 50,
    },
  ],
  sources: [
    { source: "search", views: 700, visitors: 300 },
    { source: "campaign", views: 34, visitors: 20 },
  ],
  referrers: [{ host: "google.com", views: 700, visitors: 300 }],
  campaigns: [
    { campaign: "spring", utm_source: "newsletter", utm_medium: "email", views: 34, visitors: 20 },
  ],
  measurement: MEASUREMENT,
  tracking: TRACKING,
};

export function trafficFake() {
  return vi.fn((params = {}) =>
    Promise.resolve({
      data:
        params.date_from === "2020-01-01"
          ? {
              ...TRAFFIC,
              has_data: false,
              totals: {
                views: 0,
                visitors_daily_sum: 0,
                days_with_data: 0,
                average_daily_views: 0,
              },
              series: [],
              pages: [],
              articles: [],
              categories: [],
              sources: [],
              referrers: [],
              campaigns: [],
            }
          : TRAFFIC,
    }),
  );
}

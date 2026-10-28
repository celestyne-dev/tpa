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

const usd = (m) => ({
  amount_minor: m,
  currency: "USD",
  amount: (m / 100).toFixed(2),
  formatted: `USD ${(m / 100).toFixed(2)}`,
});
const kes = (m) => ({
  amount_minor: m,
  currency: "KES",
  amount: (m / 100).toFixed(2),
  formatted: `KES ${(m / 100).toFixed(2)}`,
});

export const COMMERCE = {
  range: { from: "2026-09-29", to: "2026-10-28", granularity: "day" },
  filters: { mode: "live", currency: null },
  has_data: true,
  currencies: [
    {
      currency: "KES",
      verified_sales: 1,
      gross: kes(2000),
      refunds: kes(500),
      refund_count: 1,
      net: kes(1500),
      orders: 1,
      average_order_value: kes(2000),
    },
    {
      currency: "USD",
      verified_sales: 3,
      gross: usd(9100),
      refunds: usd(4900),
      refund_count: 1,
      net: usd(4200),
      orders: 3,
      average_order_value: usd(3033),
    },
  ],
  order_statuses: { paid: 4, failed: 1 },
  modes: [
    { mode: "live", currency: "USD", verified_sales: 3, gross: usd(9100) },
    { mode: "test", currency: "USD", verified_sales: 1, gross: usd(1500) },
  ],
  series: [
    {
      currency: "USD",
      points: [
        { period: "2026-10-27", gross: usd(9100), refunds: usd(4900), net: usd(4200), orders: 3 },
      ],
    },
  ],
  products: [
    {
      product_id: 1,
      title: "Calm Guide",
      product_type: "guide",
      type_label: "Guide",
      group: "resource",
      currency: "USD",
      units: 3,
      orders: 3,
      revenue: usd(4200),
      refunds: usd(0),
      refund_count: 0,
    },
  ],
  groups: [{ group: "course", currency: "USD", units: 1, orders: 1, revenue: usd(4900) }],
  product_types: [
    { product_type: "guide", type_label: "Guide", currency: "USD", units: 3, revenue: usd(4200) },
  ],
  categories: [{ category: "Wellbeing", currency: "USD", units: 3, revenue: usd(4200) }],
  refunds_by_product: [],
  unattributed_refunds: [usd(4900)],
  unsold_products: [{ product_id: 9, title: "Never Sold Pack", type_label: "Resource pack" }],
  conversion: {
    available: false,
    reason: "No page views were measured in this period.",
    purchase_conversion: {
      available: false,
      reason: "Orders are not linked to visitors or sessions.",
    },
  },
  notes: ["Gross = Paystack-verified charges."],
};

export function commerceFake() {
  return vi.fn((params = {}) =>
    Promise.resolve({
      data:
        params.mode === "test"
          ? {
              ...COMMERCE,
              filters: { mode: "test", currency: null },
              has_data: false,
              currencies: [],
              series: [],
              products: [],
            }
          : COMMERCE,
    }),
  );
}

const byType = (attempts, passed, failed, avg) => ({
  attempts,
  participants: attempts,
  passed,
  failed,
  expired: 0,
  average_percent: avg,
  pass_rate: passed + failed ? Math.round((1000 * passed) / (passed + failed)) / 10 : null,
});

export const LEARNING = {
  range: { from: "2026-09-29", to: "2026-10-28", granularity: "day" },
  course: null,
  has_data: true,
  course_options: [{ id: 5, title: "Calm Foundations", status: "published" }],
  current: {
    enrollments: 5,
    revoked: 1,
    started: 4,
    completed: 2,
    unfinished: 2,
    not_started: 1,
    completion_rate: 40,
    completion_rate_of_started: 50,
    average_progress: 59.8,
    by_access: { free: 2, purchase: 1, membership: 1, manual: 1 },
  },
  period: {
    new_enrollments: 4,
    new_by_access: { free: 2, purchase: 1, membership: 1, manual: 0 },
    starts: 3,
    completions: 1,
    active_learners: 3,
  },
  trend: [{ period: "2026-10-28", enrollments: 4, starts: 3, completions: 1 }],
  courses: [
    {
      id: 5,
      title: "Calm Foundations",
      status: "published",
      enrollments: 5,
      started: 4,
      completed: 2,
      completion_rate: 40,
      average_progress: 59.8,
      new_enrollments: 4,
      completions_in_range: 1,
      assignment_submissions: 3,
      assessment_participants: 3,
      average_best_score: 80,
    },
  ],
  lessons: null,
  assessments: {
    by_type: {
      quiz: byType(3, 1, 2, 66.7),
      timed: byType(1, 1, 0, 80),
      practice: byType(1, 0, 1, 40),
      ungraded: byType(1, 0, 0, null),
    },
    items: [],
    note: "Attempts submitted in the range.",
  },
  assignments: {
    available: true,
    submitted: 3,
    submitted_late: 1,
    graded: 2,
    changes_requested_in_range: 1,
    passed: 1,
    failed: 1,
    pass_rate: 50,
    average_percent: 62.5,
    pending_grading: 1,
    awaiting_resubmission: 1,
    completed_or_graded: 1,
  },
  definitions: {
    started: "At least one lesson viewed, or completed.",
    active_learners: "This is a minimum.",
  },
};

export function learningFake() {
  return vi.fn((params = {}) => {
    if (params.date_from === "2020-01-01")
      return Promise.resolve({ data: { ...LEARNING, has_data: false } });
    if (params.course)
      return Promise.resolve({
        data: {
          ...LEARNING,
          course: { id: 5, title: "Calm Foundations" },
          lessons: {
            started_learners: 4,
            items: [
              {
                lesson_id: 1,
                title: "Lesson 1",
                viewed: 3,
                completed: 3,
                completion_rate_of_started: 75,
                unfinished_stopped_here: 1,
              },
              {
                lesson_id: 2,
                title: "Lesson 2",
                viewed: 2,
                completed: 1,
                completion_rate_of_started: 25,
                unfinished_stopped_here: 1,
              },
            ],
            unfinished_before_first_completion: 0,
          },
        },
      });
    return Promise.resolve({ data: LEARNING });
  });
}

export const MEMBERSHIP_ANALYTICS = {
  range: { from: "2026-07-31", to: "2026-10-28" },
  has_data: true,
  current: {
    paid_subscribers: 3,
    active: 2,
    past_due: 1,
    grace: 0,
    pending_checkout: 0,
    cancelling: 1,
    monthly: 2,
    yearly: 1,
    complimentary: 1,
  },
  period: {
    new_subscriptions: 2,
    renewals: 1,
    cancellations_requested: 1,
    ended: { payment_failed: 1 },
    abandoned_checkouts: 0,
  },
  revenue: [{ mode: "live", count: 3, amount: usd(2997) }],
  refunds: [{ mode: "live", count: 1, amount: usd(300) }],
  net_revenue: [{ mode: "live", amount: usd(2697) }],
  trend: [
    { month: "2026-10", active_at_start: 0, new: 2, renewals: 1, ended: 1, churn_rate: null },
  ],
  access: {
    entitlements: 4,
    members_with_access: 3,
    complimentary_entitlements: 1,
    by_product_type: [],
    course_enrollments: 2,
  },
  plan: null,
  plan_options: [{ id: "plan1", name: "Positive Circle", status: "published" }],
  by_plan: [
    { plan_id: "plan1", plan: "Positive Circle", interval: "month", mode: "live", paid_members: 2 },
  ],
  revenue_by_plan: [
    {
      plan: "Positive Circle",
      mode: "live",
      payments: 3,
      gross: usd(2997),
      refunds: usd(300),
      net: usd(2697),
    },
  ],
  recurring_estimate: [{ mode: "live", subscriptions: 2, mrr: usd(1998), arr: usd(23976) }],
  recurring_at_risk: [],
  complimentary_by_plan: [{ plan: "Positive Circle", members: 1 }],
  definitions: { mrr: "Estimate, not revenue." },
};

export const AUDIENCE = {
  range: { from: "2026-09-29", to: "2026-10-28", granularity: "day" },
  has_data: true,
  current: {
    subscribed: 120,
    pending: 4,
    unsubscribed: 6,
    bounced_or_complained: 1,
    quarantined: 0,
  },
  period: {
    signups: 14,
    new_subscriptions: 12,
    unsubscriptions: 2,
    net_growth: 10,
    campaigns_sent: 1,
  },
  trend: [
    {
      period: "2026-10-28",
      signups: 14,
      new_subscriptions: 12,
      unsubscriptions: 2,
      net_growth: 10,
    },
  ],
  sources: [{ source: "lead_magnet", new_subscriptions: 7, subscribed_now: 40 }],
  campaign: null,
  campaign_options: [{ id: "camp1", name: "October letter" }],
  campaigns: [
    {
      id: "camp1",
      name: "October letter",
      send_mode: "live",
      completed_at: "2026-10-27T10:00:00Z",
      eligible: 120,
      accepted: 118,
      delivered_confirmed: 0,
      bounced: 0,
      complained: 0,
      failed: 2,
      suppressed: 0,
      skipped_test_mode: 0,
    },
  ],
  engagement: {
    delivery_feedback_recorded: false,
    opens: null,
    clicks: null,
    explanation: "Opens and clicks are not tracked.",
  },
  lead_magnets: [{ slug: "calm-kit", title: "Calm Kit", claims: 9, confirmed_subscribers: 7 }],
  definitions: { subscribed: "Contacts whose status is subscribed now." },
};

export function membershipAnalyticsFake() {
  return vi.fn(() => Promise.resolve({ data: MEMBERSHIP_ANALYTICS }));
}

export function audienceFake() {
  return vi.fn((params = {}) =>
    Promise.resolve({
      data: params.date_from === "2020-01-01" ? { ...AUDIENCE, has_data: false } : AUDIENCE,
    }),
  );
}

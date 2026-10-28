import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

/** Batch 10.1 permissions (mirrors backend/app/auth/permissions.py). */
export const MEMBERSHIP_PERMS = [
  "memberships.view",
  "memberships.manage",
  "memberships.publish",
  "memberships.manage_subscriptions",
  "memberships.view_reports",
];

const NOW = "2026-10-28T10:00:00.000Z";
const ok = (data) => Promise.resolve({ data });
const fail = (status, code, message, details) =>
  Promise.reject(new ApiError({ status, code, message, details }));
const usd = (amount_minor) => ({
  amount_minor,
  currency: "USD",
  amount: (amount_minor / 100).toFixed(2),
  formatted: `USD ${(amount_minor / 100).toFixed(2)}`,
});
export const BILLING = {
  available: false,
  status: "coming_soon",
  message: "Paid memberships are coming soon. No payments are being taken yet.",
};

const price = (id, interval, amount, extra = {}) => ({
  id,
  interval,
  status: "active",
  price: usd(amount),
  created_at: NOW,
  shown_at: null,
  retired_at: null,
  ...extra,
});

export const ELIGIBLE = [
  {
    product_id: "p-guide",
    title: "Calm Guide",
    type: "guide",
    type_label: "Guide",
    kind: "resource",
    status: "published",
    slug: "calm-guide",
    course: null,
  },
  {
    product_id: "p-course",
    title: "Calm Foundations Access",
    type: "course",
    type_label: "Online course",
    kind: "course",
    status: "published",
    slug: "calm-foundations-access",
    course: { slug: "calm-foundations", title: "Calm Foundations" },
  },
];

export function makePlan(overrides = {}) {
  return {
    id: "plan1",
    slug: "positive-circle",
    name: "Positive Circle",
    tagline: "Calmer days, together",
    tier_rank: 1,
    status: "draft",
    prices: { month: price("pm1", "month", 999) },
    included_count: 1,
    published_at: null,
    updated_at: NOW,
    lock_version: 3,
    description: "Members read every premium guide.",
    benefits: ["All premium guides"],
    first_published_at: null,
    archived_at: null,
    price_history: [price("pm1", "month", 999)],
    included: [{ ...ELIGIBLE[0], problem: null }],
    readiness: [],
    billing: BILLING,
    provider_plans: [],
    ...overrides,
  };
}

/** Public content API: the published plans and the billing status. */
export function membershipContentApi(data = null) {
  return {
    getMemberships: vi.fn(async () => ({
      data: data ?? {
        billing: BILLING,
        plans: [
          {
            slug: "positive-circle",
            name: "Positive Circle",
            tagline: "Calmer days, together",
            description: "Members read every premium guide.\n\nNew resources every month.",
            benefits: ["All premium guides", "Member-only workbooks"],
            tier_rank: 1,
            prices: [
              { interval: "month", price: usd(1000) },
              { interval: "year", price: usd(10000) },
            ],
            included: ELIGIBLE.map(({ product_id: _p, status: _s, ...rest }) => rest),
          },
        ],
      },
    })),
  };
}

/** Admin API: plans with lock_version checks, like the backend. */
export const ADMIN_SUB = {
  id: "sub1",
  status: "active",
  test_mode: true,
  customer: {
    id: 7,
    public_id: "cus1",
    email: "member@example.com",
    name: "Mia",
    status: "active",
  },
  plan: { id: "plan1", name: "Positive Circle" },
  interval: "month",
  price: usd(999),
  current_period_start: NOW,
  current_period_end: "2026-11-28T10:00:00.000Z",
  access_until: "2026-11-28T10:00:00.000Z",
  cancel_at_period_end: false,
  past_due_since: null,
  activated_at: NOW,
  ended_at: null,
  end_reason: null,
  created_at: NOW,
  next: { type: "renewal", at: "2026-11-28T10:00:00.000Z" },
};

export const REPORT = {
  range: { from: "2026-10-01", to: "2026-10-31" },
  generated_at: NOW,
  has_data: true,
  current: {
    paid_subscribers: 3,
    active: 2,
    past_due: 1,
    grace: 0,
    pending_checkout: 1,
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
  revenue: [{ mode: "test", count: 3, amount: usd(2997) }],
  refunds: [{ mode: "test", count: 1, amount: usd(300) }],
  net_revenue: [{ mode: "test", amount: usd(2697) }],
  trend: [
    { month: "2026-10", active_at_start: 0, new: 2, renewals: 1, ended: 1, churn_rate: null },
  ],
  access: {
    entitlements: 4,
    members_with_access: 3,
    complimentary_entitlements: 1,
    by_product_type: [{ type: "guide", count: 4 }],
    course_enrollments: 2,
  },
  notes: ["Revenue counts only payments verified with Paystack; pending checkouts are excluded."],
};

function subscriptionAdminFake() {
  let sub = {
    ...ADMIN_SUB,
    lock_version: 4,
    provider: { name: "paystack", mode: "test", linked: true, subscription_code: "SUB_1" },
    cancel_requested_at: null,
    last_reconciled_at: null,
    grace: { days: 3, max_extension_until: "2026-12-28T10:00:00.000Z" },
    periods: [
      {
        sequence: 1,
        status: "paid",
        period_start: NOW,
        period_end: "2026-11-28T10:00:00.000Z",
        amount: usd(999),
        order_number: "TPA-1001",
      },
    ],
    orders: [
      {
        id: 11,
        number: "TPA-1001",
        status: "paid",
        total: usd(999),
        refunded: usd(0),
        paid_at: NOW,
        needs_review: false,
        review_reason: null,
        receipt_number: "R-1001",
        refunds: [],
      },
    ],
    events: [
      {
        id: 2,
        type: "activated",
        from_status: "pending",
        to_status: "active",
        source: "webhook",
        details: {},
        created_at: NOW,
      },
      {
        id: 1,
        type: "checkout_started",
        from_status: null,
        to_status: "pending",
        source: "customer",
        details: {},
        created_at: NOW,
      },
    ],
    grants: [],
    can: { manage: true, cancel: true, extend_grace: false, reconcile: true, refund: false },
  };
  const locked = (body) =>
    body.lock_version !== sub.lock_version
      ? fail(409, "conflict", "This membership changed since you opened it.", {
          code: "edit_conflict",
        })
      : null;
  return {
    overview: vi.fn(() =>
      ok({
        billing: BILLING,
        billing_mode: "disabled",
        grace_days: 3,
        max_grace_extension_days: 30,
        live_billing: false,
        provider_mode: "test",
        counts: { active: 2, past_due: 1, grace: 0, pending: 1 },
        period_count: 3,
      }),
    ),
    inclusion: vi.fn(() => ok([{ id: "plan1", name: "Positive Circle", status: "published" }])),
    subscriptions: vi.fn(() => Promise.resolve({ data: [ADMIN_SUB], meta: { total: 1 } })),
    subscription: vi.fn(() => ok(sub)),
    reconcile: vi.fn((_id, body) => {
      const conflict = locked(body);
      if (conflict) return conflict;
      sub = { ...sub, lock_version: sub.lock_version + 1, last_reconciled_at: NOW };
      return ok({
        subscription: sub,
        result: {
          changes: {},
          provider: { status: "active", next_payment_at: sub.current_period_end },
        },
      });
    }),
    cancelSubscription: vi.fn((_id, body) => {
      const conflict = locked(body);
      if (conflict) return conflict;
      if (!body.reason || body.reason.trim().length < 3)
        return fail(400, "validation_error", "Some fields need attention.", {
          reason: ["Give a reason (3–500 characters)."],
        });
      sub = {
        ...sub,
        lock_version: sub.lock_version + 1,
        cancel_at_period_end: true,
        next: { type: "cancellation", at: sub.access_until },
        can: { ...sub.can, cancel: !body.immediate },
        ...(body.immediate ? { status: "ended" } : {}),
      };
      return ok({ subscription: sub });
    }),
    extendGrace: vi.fn(() =>
      fail(409, "conflict", "Only memberships with a failed renewal.", { code: "not_past_due" }),
    ),
    grants: vi.fn(() =>
      Promise.resolve({
        data: [
          {
            id: "g1",
            status: "active",
            customer: { public_id: "cus2", email: "guest@example.com" },
            plan: { id: "plan1", name: "Positive Circle" },
            starts_at: NOW,
            expires_at: "2026-12-01T00:00:00.000Z",
            reason: "Podcast guest",
            granted_by: "Ada Admin",
            revoked_by: null,
            revoke_reason: null,
          },
        ],
        meta: { total: 1 },
      }),
    ),
    createGrant: vi.fn(() => ok({ id: "g2" })),
    revokeGrant: vi.fn(() => ok({ id: "g1", status: "revoked" })),
    reports: vi.fn(() => ok(REPORT)),
  };
}

export function createMembershipAdminFake() {
  let plan = makePlan();
  const bump = (patch) => {
    plan = { ...plan, ...patch, lock_version: plan.lock_version + 1 };
    return ok(plan);
  };
  const locked = (body) =>
    body.lock_version !== plan.lock_version
      ? fail(409, "edit_conflict", "Someone else changed this plan.")
      : null;
  return {
    memberships: {
      list: vi.fn(() => ok([plan])),
      get: vi.fn(() => ok(plan)),
      create: vi.fn((body) => ok(makePlan({ id: "plan2", name: body.name, prices: {} }))),
      update: vi.fn((_id, body) => {
        const conflict = locked(body);
        if (conflict) return conflict;
        if (!body.name?.trim())
          return fail(400, "validation_error", "Some fields need attention.", {
            name: ["This field is required."],
          });
        const { lock_version: _l, ...rest } = body;
        return bump(rest);
      }),
      setStatus: vi.fn((_id, body) => {
        const conflict = locked(body);
        if (conflict) return conflict;
        return bump({ status: body.status, published_at: NOW });
      }),
      addPrice: vi.fn((_id, body) => {
        const conflict = locked(body);
        if (conflict) return conflict;
        if (!/^\d+(\.\d{1,2})?$/.test(body.amount))
          return fail(400, "validation_error", "The price needs attention.", {
            amount: ["Enter an amount such as 9.99."],
          });
        const added = price(`p-${body.interval}-2`, body.interval, Math.round(body.amount * 100));
        return bump({
          prices: { ...plan.prices, [body.interval]: added },
          price_history: [added, ...plan.price_history],
        });
      }),
      removePrice: vi.fn(() => bump({})),
      setAccess: vi.fn((_id, body) => {
        const conflict = locked(body);
        if (conflict) return conflict;
        return bump({
          included: ELIGIBLE.filter((e) => body.product_ids.includes(e.product_id)).map((e) => ({
            ...e,
            problem: null,
          })),
        });
      }),
      eligibleProducts: vi.fn(() => ok(ELIGIBLE)),
      ...subscriptionAdminFake(),
      providerSync: vi.fn((_id, body) => {
        const conflict = locked(body);
        if (conflict) return conflict;
        return bump({
          provider_plans: Object.values(plan.prices).map((p) => ({
            price_id: p.id,
            interval: p.interval,
            mode: "test",
            plan_code: `PLN_${p.interval}`,
            verified_at: NOW,
          })),
        });
      }),
    },
  };
}

export const OPEN_BILLING = {
  available: true,
  status: "test",
  message: "Test mode: memberships use Paystack test payments; no real money is taken.",
};

/** Public plans with test-mode billing open (prices carry ids for checkout). */
export function openMembershipContentApi() {
  const api = membershipContentApi();
  return {
    getMemberships: vi.fn(async () => {
      const { data } = await api.getMemberships();
      return {
        data: {
          billing: OPEN_BILLING,
          plans: data.plans.map((p) => ({
            ...p,
            prices: p.prices.map((x) => ({ ...x, id: `price-${x.interval}` })),
          })),
        },
      };
    }),
  };
}

const SUB = {
  id: "sub1",
  status: "pending",
  test_mode: true,
  plan: { name: "Positive Circle", slug: "positive-circle" },
  interval: "month",
  price: usd(1000),
  current_period_start: null,
  current_period_end: null,
  access_until: null,
  activated_at: null,
  created_at: NOW,
  checkout_url: "https://checkout.paystack.com/test-sub1",
  receipt_order: null,
  cancel_at_period_end: false,
  past_due_since: null,
  can_cancel: false,
  can_resume: false,
  can_update_payment_method: false,
  linked: false,
};

export const ACTIVE_SUB = {
  ...SUB,
  status: "active",
  current_period_start: NOW,
  current_period_end: "2026-11-28T10:00:00.000Z",
  access_until: "2026-11-28T10:00:00.000Z",
  activated_at: NOW,
  checkout_url: null,
  receipt_order: "o1",
  can_cancel: true,
  can_update_payment_method: true,
  linked: true,
};

/** Customer membership endpoints. `paidAfter` verify calls report the payment as confirmed. */
export function membershipShopApi({ subscription = SUB, paidAfter = 1 } = {}) {
  let current = subscription;
  let verifies = 0;
  const view = () => ({
    subscription: current,
    included: current?.status === "active" ? [ELIGIBLE[0]] : [],
    events: current
      ? [
          { type: "checkout_started", created_at: NOW },
          ...(current.status === "active" ? [{ type: "activated", created_at: NOW }] : []),
        ]
      : [],
    periods:
      current && current.status !== "pending"
        ? [
            {
              sequence: 1,
              status: "paid",
              period_start: NOW,
              period_end: "2026-11-28T10:00:00.000Z",
              amount: usd(1000),
              order: "o1",
            },
          ]
        : [],
    history: [],
    billing: OPEN_BILLING,
  });
  return {
    membership: vi.fn(() => ok(view())),
    membershipCheckout: vi.fn(() =>
      ok({ subscription: SUB, checkout_url: SUB.checkout_url, resumed: false }),
    ),
    cancelMembership: vi.fn(() => {
      current = { ...current, cancel_at_period_end: true, can_cancel: false, can_resume: true };
      return ok(view());
    }),
    resumeMembership: vi.fn(() => {
      current = { ...current, cancel_at_period_end: false, can_cancel: true, can_resume: false };
      return ok(view());
    }),
    membershipPaymentMethod: vi.fn(() =>
      ok({ url: "https://paystack.com/manage/subscriptions/sub1" }),
    ),
    verifyMembership: vi.fn(() => {
      verifies += 1;
      if (current && verifies >= paidAfter) current = ACTIVE_SUB;
      return ok({ outcome: current?.status === "active" ? "paid" : "pending", ...view() });
    }),
  };
}

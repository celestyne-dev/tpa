import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

/** Batch 10.1 permissions (mirrors backend/app/auth/permissions.py). */
export const MEMBERSHIP_PERMS = ["memberships.view", "memberships.manage", "memberships.publish"];

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
    history: [],
    billing: OPEN_BILLING,
  });
  return {
    membership: vi.fn(() => ok(view())),
    membershipCheckout: vi.fn(() =>
      ok({ subscription: SUB, checkout_url: SUB.checkout_url, resumed: false }),
    ),
    verifyMembership: vi.fn(() => {
      verifies += 1;
      if (current && verifies >= paidAfter) current = ACTIVE_SUB;
      return ok({ outcome: current?.status === "active" ? "paid" : "pending", ...view() });
    }),
  };
}

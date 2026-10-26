import { vi } from "vitest";

export const PARTNERSHIP_PERMS = [
  "partnerships.view",
  "partnerships.manage",
  "sponsorships.view",
  "sponsorships.manage",
  "sponsorships.approve",
  "advertising.view",
  "advertising.manage_inventory",
  "advertising.manage_bookings",
  "media_kit.manage",
  "affiliates.view",
  "affiliates.manage",
  "affiliates.manage_links",
  "partnership_finance.view",
  "partnership_finance.manage",
  "partnership_reports.export",
];

export const PARTNERSHIP_ROLES = {
  partnerships_manager: [
    "dashboard.view",
    "partnerships.view",
    "partnerships.manage",
    "sponsorships.view",
    "sponsorships.manage",
    "advertising.view",
    "advertising.manage_inventory",
    "advertising.manage_bookings",
    "media_kit.manage",
    "articles.view",
    "media.view",
  ],
  finance_manager: [
    "dashboard.view",
    "partnerships.view",
    "sponsorships.view",
    "advertising.view",
    "affiliates.view",
    "partnership_finance.view",
    "partnership_finance.manage",
    "partnership_reports.export",
  ],
};

const ok = (data, meta) => Promise.resolve({ data, meta });

/** In-memory partnership admin endpoints (only what the screens read). */
export function createPartnershipAdminFake() {
  const partners = [
    {
      id: 1,
      name: "Calm Co",
      partnership_type: "sponsorship",
      status: "active",
      owner: null,
      updated_at: "2026-10-20T10:00:00Z",
    },
  ];
  return {
    partners: {
      list: vi.fn(() => ok(partners, { total: 1 })),
      get: vi.fn(() => ok({ ...partners[0], contacts: [], description: "", internal_notes: "" })),
      create: vi.fn((body) => ok({ id: 2, ...body })),
      update: vi.fn((id, body) => ok({ id, ...body })),
    },
    partnershipInquiries: { list: vi.fn(() => ok([])), update: vi.fn(() => ok({})) },
    partnershipOptions: vi.fn(() => ok({ users: [], partners, campaigns: [], placements: [] })),
    opportunities: {
      list: vi.fn(() => ok([])),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      move: vi.fn(),
      interact: vi.fn(),
    },
    sponsorshipCampaigns: {
      list: vi.fn(() => ok([])),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      move: vi.fn(),
    },
    adPlacements: { list: vi.fn(() => ok([])), create: vi.fn(), update: vi.fn() },
    rateCards: { list: vi.fn(() => ok([])), create: vi.fn(), update: vi.fn() },
    adBookings: {
      list: vi.fn(() => ok([])),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      move: vi.fn(),
      conflicts: vi.fn(),
    },
    partnershipFinance: { list: vi.fn(() => ok([])), create: vi.fn() },
    partnershipReports: {
      get: vi.fn(() =>
        ok({
          by_currency: [
            {
              currency: "KES",
              pipeline_expected_minor: 0,
              contracted_minor: 5000000,
              completed_value_minor: 0,
              invoiced_minor: 5000000,
              received_verified_minor: 2000000,
              received_unverified_minor: 0,
              outstanding_minor: 3000000,
              affiliate_reported_minor: 0,
              affiliate_paid_minor: 0,
            },
            {
              currency: "USD",
              pipeline_expected_minor: 900000,
              contracted_minor: 0,
              completed_value_minor: 0,
              invoiced_minor: 0,
              received_verified_minor: 0,
              received_unverified_minor: 0,
              outstanding_minor: 0,
              affiliate_reported_minor: 1250,
              affiliate_paid_minor: 0,
            },
          ],
          campaigns_by_status: {},
          bookings_by_state: {},
          booking_utilization: [],
          notes: ["Pipeline values are expectations, not revenue."],
        }),
      ),
      exportUrl: () => "/api/v1/admin/partnership-reports/export",
    },
    articleSponsorship: {
      get: vi.fn(() => ok(null)),
      save: vi.fn(),
      remove: vi.fn(),
      approve: vi.fn(),
    },
    affiliatePrograms: { list: vi.fn(() => ok([])), create: vi.fn(), update: vi.fn() },
    affiliateLinks: { list: vi.fn(() => ok([])), create: vi.fn(), update: vi.fn() },
    affiliateClicks: vi.fn(() => ok([])),
    affiliateCommissions: {
      list: vi.fn(() => ok([])),
      create: vi.fn(),
      setStatus: vi.fn(),
      importCsv: vi.fn(),
    },
    affiliateDisclosure: {
      get: vi.fn(() => ok({ text: "Some links are affiliate links." })),
      update: vi.fn(),
    },
    mediaKit: { get: vi.fn(), save: vi.fn(), publish: vi.fn() },
    audienceMetrics: {
      list: vi.fn(() => ok([])),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    },
  };
}

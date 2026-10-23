import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

// Mirrors the Batch 06 permissions in backend/app/auth/permissions.py.
export const NEWSLETTER_EDITING = [
  "newsletters.view",
  "newsletters.create",
  "newsletters.edit",
  "newsletters.reports",
];
export const NEWSLETTER_PERMS = [
  ...NEWSLETTER_EDITING,
  "newsletters.publish",
  "newsletters.send",
  "newsletters.schedule",
  "email_templates.manage",
  "email_automations.manage",
  "lead_magnets.manage",
  "subscribers.view",
  "subscribers.manage",
  "subscribers.export",
  "email_settings.manage",
];

const ok = (data, meta) => Promise.resolve({ data, meta });
const forbidden = () =>
  Promise.reject(new ApiError({ status: 403, code: "forbidden", message: "Not allowed." }));

export function makeCampaign(overrides = {}) {
  return {
    id: 7,
    public_id: "c7",
    name: "Weekly #1",
    subject: "Starting again",
    preheader: "",
    from_name: "",
    reply_to: "",
    template_key: "weekly_edition",
    blocks: [{ type: "paragraph", text: "Hello {{first_name}}." }],
    article_ids: [],
    product_ids: [],
    ctas: [],
    segment_id: null,
    segment: null,
    status: "draft",
    scheduled_at: null,
    approved_at: null,
    queued_at: null,
    completed_at: null,
    cancelled_at: null,
    send_mode: null,
    eligible_count: null,
    updated_at: "2026-10-23T10:00:00.000Z",
    lock_version: 1,
    ...overrides,
  };
}

export function createNewsletterAdminFake(getUser) {
  const has = (perm) => getUser()?.permissions?.includes(perm);
  let campaign = makeCampaign();
  return {
    newsletters: {
      list: vi.fn(() =>
        has("newsletters.view")
          ? ok([campaign], {
              total: 1,
              sending_mode: "test",
              readiness: { checks: [], test_ready: true, live_ready: false },
            })
          : forbidden(),
      ),
      get: vi.fn(() => ok(campaign)),
      create: vi.fn((body) => {
        campaign = makeCampaign({ id: 8, name: body.name ?? "Untitled campaign" });
        return ok(campaign);
      }),
      update: vi.fn((id, body) => {
        campaign = {
          ...campaign,
          ...body,
          lock_version: campaign.lock_version + 1,
          status: "draft",
        };
        return ok(campaign);
      }),
      action: vi.fn((id, action, body) => {
        if (action === "approve") campaign = { ...campaign, status: "approved" };
        if (action === "send") campaign = { ...campaign, status: "sending" };
        if (action === "test")
          return ok({ campaign, status: "accepted", error: null, to: getUser().email, ...body });
        return ok({ campaign });
      }),
      preview: vi.fn(() =>
        ok({ subject: campaign.subject, html: "<p>Hello friend.</p>", text: "Hello friend." }),
      ),
      report: vi.fn(() => ok({ notes: [] })),
      messages: vi.fn(() => ok([], { total: 0 })),
      retryMessage: vi.fn(),
      remove: vi.fn(),
    },
    segments: { list: vi.fn(() => ok([])), preview: vi.fn(() => ok({ count: 0 })) },
    subscriberTags: { list: vi.fn(() => ok([])) },
    emailTemplates: { list: vi.fn(() => ok([])), addStarters: vi.fn(() => ok({})) },
    subscribers: {
      list: vi.fn(() =>
        has("subscribers.view")
          ? ok(
              [
                {
                  id: 1,
                  email: "reader@example.com",
                  first_name: "Ada",
                  status: "subscribed",
                  marketable: true,
                  source: "footer",
                  preferences: ["weekly"],
                  tags: [],
                  consent_at: "2026-10-20T10:00:00.000Z",
                  confirmed_at: "2026-10-20T10:05:00.000Z",
                },
              ],
              { total: 1, status_counts: { subscribed: 1 } },
            )
          : forbidden(),
      ),
      exportUrl: () => "/api/v1/admin/subscribers/export",
    },
    emailSettings: { get: vi.fn(() => (has("email_settings.manage") ? ok({}) : forbidden())) },
  };
}

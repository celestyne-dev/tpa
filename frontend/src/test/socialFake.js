import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

const ok = (data, meta) => Promise.resolve({ data, meta });

export function makeSocialAccount(platform, overrides = {}) {
  const label = platform === "pinterest" ? "Pinterest" : "Instagram";
  return {
    platform,
    label,
    setup: { ready: true, missing: [] },
    redirect_uri: `https://thinkpositivealways.com/admin/integrations/${platform}/callback`,
    scopes_requested:
      platform === "pinterest"
        ? ["user_accounts:read", "boards:read", "boards:write", "pins:read", "pins:write"]
        : ["instagram_basic", "instagram_content_publish"],
    connected: true,
    account: {
      status: "connected",
      external_id: "1",
      username: "thinkpositivealways",
      account_type: "BUSINESS",
      profile_url: `https://www.${platform}.com/thinkpositivealways/`,
      scopes: [],
      missing_scopes: [],
      // Instagram's Unified Login token does not expire; Pinterest's is renewed monthly.
      access_expires_at: platform === "pinterest" ? "2026-12-15T08:00:00+00:00" : null,
      refresh_expires_at: null,
      last_error: null,
      connected_at: "2026-11-15T08:00:00+00:00",
      connected_by: "Grace Admin",
    },
    ...overrides,
  };
}

export const disconnected = (platform, overrides = {}) =>
  makeSocialAccount(platform, { connected: false, account: null, ...overrides });

export function makeSocialPost(overrides = {}) {
  return {
    id: 1,
    platform: "pinterest",
    status: "scheduled",
    media_asset: { id: 3, title: "Sunrise", url: "/media/sunrise.jpg", alt_text: "Sunrise" },
    article: null,
    title: "30 quotes about confidence",
    text: "Save these for later.",
    alt_text: null,
    destination_url: "https://thinkpositivealways.com/quotes/confidence",
    board_id: "b1",
    board_name: "Quotes",
    scheduled_at: "2026-11-20T09:00:00+00:00",
    published_at: null,
    next_attempt_at: null,
    external_id: null,
    external_url: null,
    attempts: 0,
    last_error: null,
    created_by: "Grace Admin",
    created_at: "2026-11-15T08:00:00+00:00",
    can_cancel: true,
    can_retry: false,
    ...overrides,
  };
}

/** Social publishing admin API (Pinterest and Instagram are never contacted in tests). */
export function createSocialAdminFake() {
  const state = {
    accounts: [makeSocialAccount("pinterest"), makeSocialAccount("instagram")],
    posts: [
      makeSocialPost(),
      makeSocialPost({
        id: 2,
        status: "published",
        can_cancel: false,
        published_at: "2026-11-10T09:00:00+00:00",
        external_id: "p9",
        external_url: "https://www.pinterest.com/pin/p9/",
      }),
      makeSocialPost({
        id: 3,
        platform: "instagram",
        status: "failed",
        can_cancel: false,
        can_retry: true,
        board_name: null,
        destination_url: null,
        last_error: "Instagram could not process the image.",
      }),
    ],
    published: new Set(),
  };
  const views = {
    queue: ["scheduled", "publishing", "checking"],
    published: ["published"],
    failed: ["failed", "cancelled"],
  };
  return {
    socialState: state,
    social: {
      accounts: vi.fn(() => ok(state.accounts)),
      connect: vi.fn((platform) =>
        ok({ authorize_url: `https://www.${platform}.com/oauth/?state=signed-state` }),
      ),
      callback: vi.fn((platform, body) =>
        body.state === "signed-state"
          ? ok(makeSocialAccount(platform))
          : Promise.reject(
              new ApiError({
                status: 400,
                code: "validation_error",
                message: "The connection request is invalid. Start again.",
              }),
            ),
      ),
      disconnect: vi.fn((platform) => {
        state.accounts = state.accounts.map((a) =>
          a.platform === platform ? disconnected(platform) : a,
        );
        return ok(disconnected(platform));
      }),
      boards: vi.fn(() =>
        ok([
          { id: "b1", name: "Quotes", privacy: "PUBLIC" },
          { id: "b2", name: "Mindset", privacy: "PUBLIC" },
        ]),
      ),
      posts: vi.fn((params = {}) => {
        const rows = state.posts.filter(
          (p) =>
            (!params.view || views[params.view].includes(p.status)) &&
            (!params.media_asset_id || p.media_asset.id === params.media_asset_id),
        );
        return ok(rows, { total: rows.length, page: 1, page_size: 50 });
      }),
      createPost: vi.fn((body) => {
        const key = `${body.platform}:${body.media_asset_id}`;
        if (state.published.has(key) && !body.allow_repeat) {
          return Promise.reject(
            new ApiError({
              status: 409,
              code: "conflict",
              message: "This image has already been published here.",
              details: { allow_repeat: ["Already published."] },
            }),
          );
        }
        if (!body.scheduled_at) state.published.add(key);
        const post = makeSocialPost({
          id: state.posts.length + 1,
          platform: body.platform,
          status: body.scheduled_at ? "scheduled" : "published",
          title: body.title,
          text: body.text,
          scheduled_at: body.scheduled_at ?? "2026-11-15T08:00:00+00:00",
          external_url: body.scheduled_at ? null : "https://www.pinterest.com/pin/p10/",
        });
        state.posts = [...state.posts, post];
        return ok(post);
      }),
      retryPost: vi.fn((id) => {
        state.posts = state.posts.map((p) =>
          p.id === id ? { ...p, status: "published", can_retry: false, last_error: null } : p,
        );
        return ok(state.posts.find((p) => p.id === id));
      }),
      cancelPost: vi.fn((id) => {
        state.posts = state.posts.map((p) =>
          p.id === id ? { ...p, status: "cancelled", can_cancel: false } : p,
        );
        return ok(state.posts.find((p) => p.id === id));
      }),
      instagramMedia: vi.fn(() =>
        ok({
          username: "thinkpositivealways",
          after: null,
          items: [
            {
              id: "1790001",
              media_type: "IMAGE",
              supported: true,
              preview_url: "https://scontent.cdninstagram.com/one.jpg",
              caption: "Start small. Keep going.",
              permalink: "https://www.instagram.com/p/AAA111/",
              timestamp: "2026-10-01T08:00:00+0000",
              username: "thinkpositivealways",
              imported: false,
              media_asset_id: null,
            },
            {
              id: "1790002",
              media_type: "VIDEO",
              supported: false,
              preview_url: null,
              caption: "A reel",
              permalink: "https://www.instagram.com/p/BBB222/",
              timestamp: "2026-10-02T08:00:00+0000",
              username: "thinkpositivealways",
              imported: false,
              media_asset_id: null,
            },
          ],
        }),
      ),
      importInstagram: vi.fn(() => ok({ id: 77, duplicate: false })),
    },
  };
}

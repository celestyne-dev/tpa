import axios from "axios";
import { siteConfig } from "@/config/site";
import { toApiError } from "./apiClient";

/**
 * Admin API client. Authentication uses HttpOnly cookies set by Flask; this
 * client never sees or stores tokens. For CSRF protection it copies the
 * readable csrf_* cookie into the X-CSRF-TOKEN header on mutations, and it
 * transparently refreshes an expired session once before giving up.
 */

const SAFE = new Set(["get", "head", "options"]);
const REFRESH_URL = "/auth/refresh";
const LOGOUT_URL = "/auth/logout";
// These endpoints authenticate with the refresh cookie, so they send its CSRF value.
const REFRESH_CSRF_URLS = new Set([REFRESH_URL, LOGOUT_URL]);
const NO_RETRY = new Set(["/auth/login", LOGOUT_URL, REFRESH_URL]);
// Token-link endpoints (invitation activation, password reset) never use the session.
const isTokenFlow = (url = "") =>
  url.startsWith("/auth/invitation/") || url.startsWith("/auth/password-reset/");
const skipRefresh = (url) => NO_RETRY.has(url) || isTokenFlow(url);

export function readCookie(name) {
  if (typeof document === "undefined") return "";
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

export function createAdminApi({ baseURL = `${siteConfig.apiBaseUrl}/admin`, adapter } = {}) {
  const client = axios.create({
    baseURL,
    ...(adapter && { adapter }),
    timeout: 15000,
    withCredentials: true,
    headers: { Accept: "application/json" },
  });
  let refreshing = null;
  let onSessionExpired = () => {};

  client.interceptors.request.use((config) => {
    if (!SAFE.has((config.method ?? "get").toLowerCase())) {
      const cookie = REFRESH_CSRF_URLS.has(config.url) ? "csrf_refresh_token" : "csrf_access_token";
      const token = readCookie(cookie);
      if (token) config.headers["X-CSRF-TOKEN"] = token;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const apiError = toApiError(error);
      const original = error.config;
      const canRefresh =
        apiError.status === 401 &&
        ["token_expired", "authentication_required"].includes(apiError.code) &&
        original &&
        !original._retried &&
        !skipRefresh(original.url);
      if (!canRefresh) {
        if (apiError.status === 401 && original && !skipRefresh(original.url)) onSessionExpired();
        return Promise.reject(apiError);
      }
      original._retried = true;
      try {
        refreshing ??= client.post(REFRESH_URL).finally(() => {
          refreshing = null;
        });
        await refreshing;
      } catch {
        onSessionExpired();
        return Promise.reject(apiError);
      }
      return client(original);
    },
  );

  const data = (promise) => promise.then((res) => res.data);
  const get = (url, params) => data(client.get(url, { params }));
  const post = (url, body) => data(client.post(url, body ?? {}));
  const patch = (url, body) => data(client.patch(url, body));
  const put = (url, body) => data(client.put(url, body));
  const del = (url) => data(client.delete(url));
  const upload = (url, file, fields = {}, onProgress) => {
    const form = new FormData();
    form.append("file", file);
    Object.entries(fields).forEach(([k, v]) => v != null && v !== "" && form.append(k, v));
    return data(
      client.post(url, form, {
        timeout: 120000,
        onUploadProgress: (event) =>
          onProgress?.(event.total ? Math.round((event.loaded / event.total) * 100) : null),
      }),
    );
  };

  const collection = (name) => ({
    list: (params) => get(`/${name}`, params),
    get: (id) => get(`/${name}/${id}`),
    create: (body) => post(`/${name}`, body),
    update: (id, body) => patch(`/${name}/${id}`, body),
    remove: (id) => del(`/${name}/${id}`),
    reassign: (id, targetId) => post(`/${name}/${id}/reassign`, { target_id: targetId }),
  });

  return {
    onSessionExpired(handler) {
      onSessionExpired = handler;
    },
    auth: {
      me: () => get("/auth/me"),
      login: (credentials) => post("/auth/login", credentials),
      logout: () => post(LOGOUT_URL),
      changePassword: (body) => post("/auth/change-password", body),
      verifyInvitation: (token) => post("/auth/invitation/verify", { token }),
      acceptInvitation: (body) => post("/auth/invitation/accept", body),
      verifyPasswordReset: (token) => post("/auth/password-reset/verify", { token }),
      completePasswordReset: (body) => post("/auth/password-reset/complete", body),
    },
    analytics: () => get("/analytics"),
    dashboard: () => get("/dashboard"),
    articles: {
      ...collection("articles"),
      publish: (id, publishedAt = null) =>
        post(`/articles/${id}/publish`, { published_at: publishedAt }),
      unpublish: (id) => post(`/articles/${id}/unpublish`),
      archive: (id) => post(`/articles/${id}/archive`),
      restore: (id) => post(`/articles/${id}/restore`),
      submit: (id) => post(`/articles/${id}/submit`),
      approve: (id) => post(`/articles/${id}/approve`),
      publishChanges: (id, lockVersion) =>
        post(`/articles/${id}/publish-changes`, { lock_version: lockVersion ?? null }),
      discardChanges: (id) => post(`/articles/${id}/discard-changes`),
      revisions: (id) => get(`/articles/${id}/revisions`),
      revision: (id, revisionId) => get(`/articles/${id}/revisions/${revisionId}`),
      compareRevisions: (id, from, to) => get(`/articles/${id}/revisions/compare`, { from, to }),
      restoreRevision: (id, revisionId, lockVersion) =>
        post(`/articles/${id}/revisions/${revisionId}/restore`, {
          lock_version: lockVersion ?? null,
        }),
      seoChecks: (id) => get(`/articles/${id}/seo-checks`),
      slugCheck: (slug, exclude) => get("/articles/slug-check", { slug, exclude }),
      preview: (id) => get(`/articles/${id}/preview`),
    },
    topics: collection("topics"),
    tags: collection("tags"),
    authors: collection("authors"),
    media: {
      list: (params) => get("/media", params),
      get: (id) => get(`/media/${id}`),
      stats: () => get("/media/stats"),
      upload: (file, fields, onProgress) => upload("/media", file, fields, onProgress),
      update: (id, body) => patch(`/media/${id}`, body),
      replace: (id, file, onProgress) => upload(`/media/${id}/replace`, file, {}, onProgress),
      archive: (id) => post(`/media/${id}/archive`),
      restore: (id) => post(`/media/${id}/restore`),
      remove: (id) => del(`/media/${id}`),
    },
    publishing: {
      status: () => get("/publishing/status"),
      jobs: (params) => get("/publishing/jobs", params),
      request: () => post("/publishing/jobs"),
      retry: (id) => post(`/publishing/jobs/${id}/retry`),
      cancel: (id) => post(`/publishing/jobs/${id}/cancel`),
    },
    seo: { overview: () => get("/seo/overview") },
    redirects: {
      list: (params) => get("/redirects", params),
      create: (body) => post("/redirects", body),
      update: (id, body) => patch(`/redirects/${id}`, body),
      remove: (id) => del(`/redirects/${id}`),
      import: (csv, dryRun) => post("/redirects/import", { csv, dry_run: dryRun }),
      exportUrl: () => `${baseURL}/redirects/export`,
    },
    pages: {
      list: (params) => get("/pages", params),
      get: (id) => get(`/pages/${id}`),
      homepage: () => get("/homepage"),
      create: (body) => post("/pages", body),
      update: (id, body) => patch(`/pages/${id}`, body),
      saveDraft: (id, body) => put(`/pages/${id}/draft`, body),
      publish: (id, lockVersion) => post(`/pages/${id}/publish`, { lock_version: lockVersion }),
      schedule: (id, scheduledAt, lockVersion) =>
        post(`/pages/${id}/schedule`, { scheduled_at: scheduledAt, lock_version: lockVersion }),
      unschedule: (id) => del(`/pages/${id}/schedule`),
      unpublish: (id) => post(`/pages/${id}/unpublish`),
      archive: (id) => post(`/pages/${id}/archive`),
      restore: (id) => post(`/pages/${id}/restore`),
      discard: (id) => post(`/pages/${id}/discard`),
      duplicate: (id) => post(`/pages/${id}/duplicate`),
      preview: (id, body) =>
        body ? post(`/pages/${id}/preview`, body) : get(`/pages/${id}/preview`),
      seoChecks: (id) => get(`/pages/${id}/seo-checks`),
      revisions: (id) => get(`/pages/${id}/revisions`),
      revision: (id, revisionId) => get(`/pages/${id}/revisions/${revisionId}`),
      restoreRevision: (id, revisionId, lockVersion) =>
        post(`/pages/${id}/revisions/${revisionId}/restore`, { lock_version: lockVersion }),
      slugCheck: (params) => get("/pages/slug-check", params),
      templates: () => get("/page-templates"),
      sectionTypes: () => get("/section-types"),
      shareSection: (id, sectionId, name) =>
        post(`/pages/${id}/sections/${sectionId}/share`, { name }),
      updateSection: (pageId, sectionId, body) =>
        patch(`/pages/${pageId}/sections/${sectionId}`, body),
      reorder: (pageId, order) => put(`/pages/${pageId}/sections/order`, { order }),
    },
    shared: {
      list: () => get("/shared-sections"),
      get: (id) => get(`/shared-sections/${id}`),
      create: (body) => post("/shared-sections", body),
      update: (id, body) => put(`/shared-sections/${id}`, body),
      remove: (id) => del(`/shared-sections/${id}`),
    },
    ctas: {
      list: () => get("/ctas"),
      create: (body) => post("/ctas", body),
      update: (id, body) => patch(`/ctas/${id}`, body),
      remove: (id) => del(`/ctas/${id}`),
    },
    announcements: {
      list: () => get("/announcements"),
      create: (body) => post("/announcements", body),
      update: (id, body) => patch(`/announcements/${id}`, body),
      remove: (id) => del(`/announcements/${id}`),
      reorder: (order) => put("/announcements/order", { order }),
    },
    linkOptions: (q) => get("/link-options", { q }),
    builderOptions: () => get("/builder-options"),
    navigation: {
      list: () => get("/navigation"),
      save: (key, items) => put(`/navigation/${key}`, { items }),
    },
    settings: {
      get: (groups) => get("/settings", groups ? { groups: groups.join(",") } : undefined),
      save: (values, groups) =>
        patch(groups ? `/settings?groups=${encodeURIComponent(groups.join(","))}` : "/settings", {
          values,
        }),
    },
    users: {
      list: (params) => get("/users", params),
      get: (id) => get(`/users/${id}`),
      create: (body) => post("/users", body),
      update: (id, body) => patch(`/users/${id}`, body),
      resetPassword: (id, password) => post(`/users/${id}/password`, { password }),
      sendPasswordReset: (id) => post(`/users/${id}/password-reset`),
      roles: () => get("/roles", { include_inactive: true }),
      permissions: () => get("/permissions"),
    },
    roles: {
      list: () => get("/roles", { include_inactive: true }),
      get: (id) => get(`/roles/${id}`),
      create: (body) => post("/roles", body),
      update: (id, body) => patch(`/roles/${id}`, body),
      remove: (id) => del(`/roles/${id}`),
      permissions: () => get("/permissions"),
    },
    invitations: {
      list: (params) => get("/invitations", params),
      create: (body) => post("/invitations", body),
      revoke: (id) => post(`/invitations/${id}/revoke`),
      resend: (id) => post(`/invitations/${id}/resend`),
    },
    audit: { list: (params) => get("/audit-log", params) },
    products: {
      list: (params) => get("/products", params),
      options: () => get("/products/options"),
      get: (id) => get(`/products/${id}`),
      create: (body) => post("/products", body),
      update: (id, body) => patch(`/products/${id}`, body),
      action: (id, action) => post(`/products/${id}/${action}`),
      preview: (id) => get(`/products/${id}/preview`),
      revisions: (id) => get(`/products/${id}/revisions`),
      restoreRevision: (id, revisionId) => post(`/products/${id}/revisions/${revisionId}/restore`),
      setPrice: (id, body) => post(`/products/${id}/prices`, body),
      removePrice: (id, priceId) => del(`/products/${id}/prices/${priceId}`),
      setBundleItems: (id, productIds) =>
        put(`/products/${id}/bundle-items`, { product_ids: productIds }),
      files: (id) => get(`/products/${id}/files`),
      uploadFile: (id, file, fields, onProgress) =>
        upload(`/products/${id}/files`, file, fields, onProgress),
      uploadVersion: (id, fileId, file, fields, onProgress) =>
        upload(`/products/${id}/files/${fileId}/versions`, file, fields, onProgress),
      updateFile: (id, fileId, body) => patch(`/products/${id}/files/${fileId}`, body),
      fileDownloadUrl: (id, fileId, versionId) =>
        `${baseURL}/products/${id}/files/${fileId}/versions/${versionId}/download`,
    },
    productCategories: collection("product-categories"),
    productCollections: collection("product-collections"),
    orders: {
      list: (params) => get("/orders", params),
      get: (id) => get(`/orders/${id}`),
      verify: (id) => post(`/orders/${id}/verify`),
      cancel: (id) => post(`/orders/${id}/cancel`),
      resendReceipt: (id) => post(`/orders/${id}/resend-receipt`),
      addNote: (id, note) => post(`/orders/${id}/notes`, { note }),
      refund: (id, body) => post(`/orders/${id}/refunds`, body),
      refundAction: (id, refundId, action, body) =>
        post(`/orders/${id}/refunds/${refundId}/${action}`, body),
      exportUrl: (params = {}) =>
        `${baseURL}/orders/export?${new URLSearchParams(params).toString()}`,
    },
    customers: {
      list: (params) => get("/customers", params),
      get: (id) => get(`/customers/${id}`),
      update: (id, body) => patch(`/customers/${id}`, body),
      support: (id, action) => post(`/customers/${id}/${action}`),
      anonymise: (id) => post(`/customers/${id}/anonymise`, { confirm: true }),
      grant: (id, body) => post(`/customers/${id}/entitlements`, body),
    },
    entitlements: {
      list: (params) => get("/entitlements", params),
      action: (id, action, reason) => post(`/entitlements/${id}/${action}`, { reason }),
    },
    downloads: { list: (params) => get("/downloads", params) },
    reports: {
      revenue: (params) => get("/reports/revenue", params),
      revenueExportUrl: (params = {}) =>
        `${baseURL}/reports/revenue/export?${new URLSearchParams(params).toString()}`,
    },
    payments: {
      settings: () => get("/payments/settings"),
      update: (body) => patch("/payments/settings", body),
      attest: (body) => put("/payments/attestation", body),
      events: (params) => get("/payments/events", params),
      reprocess: (id) => post(`/payments/events/${id}/reprocess`),
    },
    subscribers: {
      list: (params) => get("/subscribers", params),
      get: (id) => get(`/subscribers/${id}`),
      setTags: (id, tags) => put(`/subscribers/${id}/tags`, { tags }),
      action: (id, action, body) => post(`/subscribers/${id}/${action}`, body),
      bulkTag: (body) => post("/subscribers/bulk-tag", body),
      import: (body) => post("/subscribers/import", body),
      exportUrl: (params = {}) =>
        `${baseURL}/subscribers/export?${new URLSearchParams(params).toString()}`,
    },
    subscriberTags: {
      list: () => get("/subscriber-tags"),
      create: (body) => post("/subscriber-tags", body),
      update: (id, body) => patch(`/subscriber-tags/${id}`, body),
      remove: (id) => del(`/subscriber-tags/${id}`),
    },
    segments: {
      list: () => get("/subscriber-segments"),
      create: (body) => post("/subscriber-segments", body),
      update: (id, body) => patch(`/subscriber-segments/${id}`, body),
      remove: (id) => del(`/subscriber-segments/${id}`),
      preview: (rules) => post("/subscriber-segments/preview", { rules }),
    },
    suppressions: {
      list: (params) => get("/email-suppressions", params),
      add: (body) => post("/email-suppressions", body),
      remove: (id) => del(`/email-suppressions/${id}`),
    },
    newsletters: {
      list: (params) => get("/newsletters", params),
      get: (id) => get(`/newsletters/${id}`),
      create: (body) => post("/newsletters", body),
      update: (id, body) => patch(`/newsletters/${id}`, body),
      remove: (id) => del(`/newsletters/${id}`),
      action: (id, action, body) => post(`/newsletters/${id}/${action}`, body),
      preview: (id, body) => post(`/newsletters/${id}/preview`, body),
      report: (id) => get(`/newsletters/${id}/report`),
      messages: (id, params) => get(`/newsletters/${id}/messages`, params),
      retryMessage: (messageId) => post(`/email-messages/${messageId}/retry`),
    },
    emailTemplates: {
      list: () => get("/email-templates"),
      create: (body) => post("/email-templates", body),
      update: (id, body) => patch(`/email-templates/${id}`, body),
      remove: (id) => del(`/email-templates/${id}`),
      addStarters: () => post("/email-templates/starters"),
    },
    emailAutomations: {
      list: () => get("/email-automations"),
      get: (id) => get(`/email-automations/${id}`),
      update: (id, body) => patch(`/email-automations/${id}`, body),
      replaceSteps: (id, steps) => put(`/email-automations/${id}/steps`, { steps }),
    },
    leadMagnets: {
      list: () => get("/lead-magnets"),
      create: (body) => post("/lead-magnets", body),
      update: (id, body) => patch(`/lead-magnets/${id}`, body),
      remove: (id) => del(`/lead-magnets/${id}`),
    },
    partners: {
      list: (params) => get("/partners", params),
      get: (id) => get(`/partners/${id}`),
      create: (body) => post("/partners", body),
      update: (id, body) => put(`/partners/${id}`, body),
    },
    partnershipInquiries: {
      list: (params) => get("/partnership-inquiries", params),
      update: (id, body) => put(`/partnership-inquiries/${id}`, body),
    },
    opportunities: {
      list: (params) => get("/opportunities", params),
      get: (id) => get(`/opportunities/${id}`),
      create: (body) => post("/opportunities", body),
      update: (id, body) => put(`/opportunities/${id}`, body),
      move: (id, body) => post(`/opportunities/${id}/stage`, body),
      interact: (id, body) => post(`/opportunities/${id}/interactions`, body),
    },
    sponsorshipCampaigns: {
      list: (params) => get("/sponsorship-campaigns", params),
      get: (id) => get(`/sponsorship-campaigns/${id}`),
      create: (body) => post("/sponsorship-campaigns", body),
      update: (id, body) => put(`/sponsorship-campaigns/${id}`, body),
      move: (id, status) => post(`/sponsorship-campaigns/${id}/status`, { status }),
    },
    partnershipOptions: () => get("/partnership-options"),
    adPlacements: {
      list: () => get("/ad-placements"),
      create: (body) => post("/ad-placements", body),
      update: (id, body) => put(`/ad-placements/${id}`, body),
    },
    rateCards: {
      list: () => get("/rate-cards"),
      create: (body) => post("/rate-cards", body),
      update: (id, body) => put(`/rate-cards/${id}`, body),
    },
    adBookings: {
      list: (params) => get("/ad-bookings", params),
      get: (id) => get(`/ad-bookings/${id}`),
      create: (body) => post("/ad-bookings", body),
      update: (id, body) => put(`/ad-bookings/${id}`, body),
      move: (id, status) => post(`/ad-bookings/${id}/status`, { status }),
      conflicts: (body) => post("/ad-bookings/conflicts", body),
    },
    partnershipFinance: {
      list: (params) => get("/partnership-finance", params),
      create: (body) => post("/partnership-finance", body),
    },
    partnershipReports: {
      get: (params) => get("/partnership-reports", params),
      exportUrl: (params = {}) => {
        const query = new URLSearchParams(
          Object.entries(params).filter(([, v]) => v != null && v !== ""),
        ).toString();
        return `${baseURL}/partnership-reports/export${query ? `?${query}` : ""}`;
      },
    },
    articleSponsorship: {
      get: (articleId) => get(`/articles/${articleId}/sponsorship`),
      save: (articleId, body) => put(`/articles/${articleId}/sponsorship`, body),
      remove: (articleId) => del(`/articles/${articleId}/sponsorship`),
      approve: (articleId) => post(`/articles/${articleId}/sponsorship/approve`),
    },
    affiliatePrograms: {
      list: () => get("/affiliate-programs"),
      create: (body) => post("/affiliate-programs", body),
      update: (id, body) => put(`/affiliate-programs/${id}`, body),
    },
    affiliateLinks: {
      list: (params) => get("/affiliate-links", params),
      create: (body) => post("/affiliate-links", body),
      update: (id, body) => put(`/affiliate-links/${id}`, body),
    },
    affiliateClicks: (params) => get("/affiliate-clicks", params),
    affiliateCommissions: {
      list: (params) => get("/affiliate-commissions", params),
      create: (body) => post("/affiliate-commissions", body),
      setStatus: (id, status) => post(`/affiliate-commissions/${id}/status`, { status }),
      importCsv: (file, programId) =>
        upload("/affiliate-commissions/import", file, { program_id: programId }),
    },
    affiliateDisclosure: {
      get: () => get("/affiliate-disclosure"),
      update: (text) => put("/affiliate-disclosure", { text }),
    },
    mediaKit: {
      get: () => get("/media-kit"),
      save: (body) => put("/media-kit", body),
      publish: () => post("/media-kit/publish"),
    },
    audienceMetrics: {
      list: () => get("/audience-metrics"),
      create: (body) => post("/audience-metrics", body),
      update: (id, body) => put(`/audience-metrics/${id}`, body),
      remove: (id) => del(`/audience-metrics/${id}`),
    },
    emailSettings: {
      get: () => get("/email-settings"),
      update: (body) => patch("/email-settings", body),
      attest: (body) => put("/email-settings/attestation", body),
    },
  };
}

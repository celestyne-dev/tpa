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
        !NO_RETRY.has(original.url);
      if (!canRefresh) {
        if (apiError.status === 401 && original && !NO_RETRY.has(original.url)) onSessionExpired();
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
    },
    dashboard: () => get("/dashboard"),
    articles: {
      ...collection("articles"),
      publish: (id, publishedAt = null) =>
        post(`/articles/${id}/publish`, { published_at: publishedAt }),
      unpublish: (id) => post(`/articles/${id}/unpublish`),
      archive: (id) => post(`/articles/${id}/archive`),
      restore: (id) => post(`/articles/${id}/restore`),
      preview: (id) => get(`/articles/${id}/preview`),
    },
    topics: collection("topics"),
    tags: collection("tags"),
    authors: collection("authors"),
    media: { list: () => get("/media") },
    publishing: { status: () => get("/publishing/status") },
    pages: {
      list: () => get("/pages"),
      get: (id) => get(`/pages/${id}`),
      update: (id, body) => patch(`/pages/${id}`, body),
      sectionTypes: () => get("/section-types"),
      updateSection: (pageId, sectionId, body) =>
        patch(`/pages/${pageId}/sections/${sectionId}`, body),
      reorder: (pageId, order) => put(`/pages/${pageId}/sections/order`, { order }),
    },
    navigation: {
      list: () => get("/navigation"),
      save: (key, items) => put(`/navigation/${key}`, { items }),
    },
    settings: {
      get: () => get("/settings"),
      save: (values) => patch("/settings", { values }),
    },
    users: {
      list: () => get("/users"),
      create: (body) => post("/users", body),
      update: (id, body) => patch(`/users/${id}`, body),
      resetPassword: (id, password) => post(`/users/${id}/password`, { password }),
      roles: () => get("/roles"),
    },
    audit: { list: (params) => get("/audit-log", params) },
  };
}

import axios from "axios";
import { siteConfig } from "@/config/site";
import { readCookie } from "./adminApi";
import { toApiError } from "./apiClient";

/**
 * Storefront API for customers: cart quotes, checkout, account, library and
 * downloads. Customer sessions are HttpOnly cookies set by Flask (separate from
 * the admin session); mutations echo the readable `tpa_customer_csrf` cookie in
 * the `X-Customer-CSRF` header. Prices always come from the server.
 */
export function createShopApi({ baseURL = siteConfig.apiBaseUrl, adapter } = {}) {
  const client = axios.create({
    baseURL,
    ...(adapter && { adapter }),
    timeout: 20000,
    withCredentials: true,
    headers: { Accept: "application/json" },
  });
  client.interceptors.request.use((config) => {
    if (!["get", "head", "options"].includes((config.method ?? "get").toLowerCase())) {
      config.headers["X-Customer-CSRF"] = readCookie("tpa_customer_csrf");
    }
    return config;
  });
  client.interceptors.response.use(
    (response) => response,
    (error) => Promise.reject(toApiError(error)),
  );
  const get = (url, params) => client.get(url, { params }).then((r) => r.data);
  const post = (url, body = {}) => client.post(url, body).then((r) => r.data);
  const patch = (url, body = {}) => client.patch(url, body).then((r) => r.data);
  const enc = encodeURIComponent;
  const guestPost = (url, token, body = {}) =>
    client.post(url, body, { headers: { "X-Guest-Order-Token": token } }).then((r) => r.data);
  return {
    status: () => get("/shop/status"),
    quote: (items, currency) =>
      post("/cart/quote", { items: items.map((product_id) => ({ product_id })), currency }),
    me: () => get("/account/me"),
    register: (body) => post("/account/register", body),
    login: (body) => post("/account/login", body),
    logout: () => post("/account/logout"),
    updateProfile: (body) => patch("/account/me", body),
    changePassword: (body) => post("/account/password", body),
    verifyEmail: (token) => post("/account/verify-email", { token }),
    resendVerification: () => post("/account/verify-email/resend"),
    requestVerification: (email) => post("/account/verify-email/request", { email }),
    accountNewsletter: () => get("/account/newsletter"),
    subscribeFromAccount: (consentVersion) =>
      post("/account/newsletter", { consent: true, consent_version: consentVersion }),
    requestPasswordReset: (email) => post("/account/password-reset", { email }),
    completePasswordReset: (token, password) =>
      post("/account/password-reset/complete", { token, password }),
    exportData: (password) => post("/account/export", { password }),
    deleteAccount: (password) => post("/account/delete", { password }),
    orders: () => get("/account/orders"),
    order: (id) => get(`/account/orders/${enc(id)}`),
    library: () => get("/account/library"),
    authorizeDownload: (entitlementId, versionId) =>
      post(`/account/library/${entitlementId}/downloads`, { version_id: versionId }),
    claimFree: (productId) => post("/account/free-claims", { product_id: productId }),
    checkout: (body) => post("/checkout", body),
    checkoutOrder: (id) => get(`/checkout/orders/${enc(id)}`),
    verifyOrder: (id) => post(`/checkout/orders/${enc(id)}/verify`),
    retryOrder: (id) => post(`/checkout/orders/${enc(id)}/retry`),
    cancelOrder: (id) => post(`/checkout/orders/${enc(id)}/cancel`),
    // Guest checkout: no session. The order token (kept by this browser) opens one order;
    // emailed access links carry their token in the body, never in a URL.
    guestCheckout: (body) => post("/checkout/guest", body),
    guestOrder: (id, token) =>
      client
        .get(`/checkout/guest-orders/${enc(id)}`, { headers: { "X-Guest-Order-Token": token } })
        .then((r) => r.data),
    verifyGuestOrder: (id, token) => guestPost(`/checkout/guest-orders/${enc(id)}/verify`, token),
    retryGuestOrder: (id, token) => guestPost(`/checkout/guest-orders/${enc(id)}/retry`, token),
    cancelGuestOrder: (id, token) => guestPost(`/checkout/guest-orders/${enc(id)}/cancel`, token),
    guestOrderDownload: (id, token, entitlementId, versionId) =>
      guestPost(`/checkout/guest-orders/${enc(id)}/downloads`, token, {
        entitlement_id: entitlementId,
        version_id: versionId,
      }),
    requestGuestAccess: (email) => post("/guest/access-request", { email }),
    guestLibrary: (token) => post("/guest/library", { token }),
    guestLibraryDownload: (token, entitlementId, versionId) =>
      post("/guest/library/downloads", {
        token,
        entitlement_id: entitlementId,
        version_id: versionId,
      }),
    // The Positive Reset newsletter and free resources (cookieless; signed links).
    newsletterStatus: () => get("/newsletter/status"),
    subscribe: (body) => post("/newsletter/subscribe", body),
    confirmSubscription: (token) => post("/newsletter/confirm", { token }),
    newsletterPreferences: (token) => post("/newsletter/preferences", { token }),
    updateNewsletterPreferences: (token, body) =>
      client.put("/newsletter/preferences", { ...body, token }).then((r) => r.data),
    unsubscribe: (token, body = {}) => post("/newsletter/unsubscribe", { ...body, token }),
    eraseSubscription: (token) => post("/newsletter/erase", { token }),
    leadMagnet: (slug) => get(`/lead-magnets/${enc(slug)}`),
    claimLeadMagnet: (slug, body) => post(`/lead-magnets/${enc(slug)}/claim`, body),
    leadMagnetAccess: (token) => post("/lead-magnets/access", { token }),
    leadMagnetDownload: (token, fileId) =>
      post("/lead-magnets/access/download", { token, file_id: fileId }),
    // Partnerships (cookieless): the inquiry form and the published media kit.
    submitPartnershipInquiry: (body) => post("/partnership-inquiries", body),
    mediaKit: () => get("/media-kit"),
  };
}

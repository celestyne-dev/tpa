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
    membership: () => get("/account/membership"),
    membershipCheckout: (body) => post("/account/membership/checkout", body),
    verifyMembership: (subscriptionId) =>
      post("/account/membership/verify", { subscription_id: subscriptionId }),
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
    // Text-based courses: learner area (signed-in customers with a confirmed email).
    learning: () => get("/account/learning"),
    learningStatus: (slug) => get(`/account/learning/${enc(slug)}/status`),
    enroll: (slug) => post(`/account/learning/${enc(slug)}/enroll`),
    learningCourse: (slug) => get(`/account/learning/${enc(slug)}`),
    learningLesson: (slug, lesson) => get(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}`),
    completeLesson: (slug, lesson) =>
      post(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/complete`),
    saveExercise: (slug, lesson, exercise, body) =>
      client
        .put(
          `/account/learning/${enc(slug)}/lessons/${enc(lesson)}/exercises/${enc(exercise)}`,
          body,
        )
        .then((r) => r.data),
    learningAssessment: (slug, id) => get(`/account/learning/${enc(slug)}/assessments/${id}`),
    submitAttempt: (slug, id, answers) =>
      post(`/account/learning/${enc(slug)}/assessments/${id}/attempts`, { answers }),
    // Batch 09.2: started (drawn, shuffled or timed) attempts and attempt history.
    startAttempt: (slug, id) =>
      post(`/account/learning/${enc(slug)}/assessments/${id}/attempts/start`),
    attempt: (slug, id, attemptId) =>
      get(`/account/learning/${enc(slug)}/assessments/${id}/attempts/${attemptId}`),
    saveAttemptAnswers: (slug, id, attemptId, answers) =>
      client
        .put(`/account/learning/${enc(slug)}/assessments/${id}/attempts/${attemptId}`, { answers })
        .then((r) => r.data),
    submitStartedAttempt: (slug, id, attemptId, answers) =>
      post(`/account/learning/${enc(slug)}/assessments/${id}/attempts/${attemptId}/submit`, {
        answers,
      }),
    assessmentHistory: (slug) => get(`/account/learning/${enc(slug)}/assessment-history`),
    // Batch 09.2: written assignments (drafts, supporting documents, submissions, feedback).
    assignments: (slug) => get(`/account/learning/${enc(slug)}/assignments`),
    assignment: (slug, id) => get(`/account/learning/${enc(slug)}/assignments/${enc(id)}`),
    saveAssignmentDraft: (slug, id, body) =>
      client
        .put(`/account/learning/${enc(slug)}/assignments/${enc(id)}/draft`, body)
        .then((r) => r.data),
    submitAssignment: (slug, id, body) =>
      post(`/account/learning/${enc(slug)}/assignments/${enc(id)}/submit`, body),
    uploadAssignmentFile: (slug, id, file) => {
      const form = new FormData();
      form.append("file", file);
      return client
        .post(`/account/learning/${enc(slug)}/assignments/${enc(id)}/files`, form, {
          timeout: 120000,
        })
        .then((r) => r.data);
    },
    removeAssignmentFile: (fileId) =>
      client.delete(`/account/assignment-files/${enc(fileId)}`).then((r) => r.data),
    assignmentFileUrl: (fileId) => `${baseURL}/account/assignment-files/${enc(fileId)}/download`,
    requestCertificate: (slug, name) =>
      post(`/account/learning/${enc(slug)}/certificate`, { name }),
    certificatePdfUrl: (code) => `${baseURL}/account/certificates/${enc(code)}/pdf`,
    verifyCertificate: (code) => get(`/certificates/${enc(code)}`),
    previewLesson: (slug, lesson) => get(`/courses/${enc(slug)}/preview/${enc(lesson)}`),
    // Batch 09.1 study tools (private to the signed-in learner).
    searchLearning: (q) => get("/learning/search", { q }),
    createNote: (slug, lesson, body) =>
      post(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/notes`, body),
    updateNote: (id, body) => patch(`/account/study/notes/${enc(id)}`, body),
    deleteNote: (id) => client.delete(`/account/study/notes/${enc(id)}`).then((r) => r.data),
    createHighlight: (slug, lesson, body) =>
      post(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/highlights`, body),
    updateHighlight: (id, color) => patch(`/account/study/highlights/${enc(id)}`, { color }),
    deleteHighlight: (id) =>
      client.delete(`/account/study/highlights/${enc(id)}`).then((r) => r.data),
    setBookmark: (slug, lesson, bookmarked) =>
      client
        .put(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/bookmark`, { bookmarked })
        .then((r) => r.data),
    setChecklistItem: (slug, lesson, itemId, checked) =>
      client
        .put(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/checklist/${enc(itemId)}`, {
          checked,
        })
        .then((r) => r.data),
    savePosition: (slug, lesson, body) =>
      client
        .put(`/account/learning/${enc(slug)}/lessons/${enc(lesson)}/position`, body)
        .then((r) => r.data),
    /** Last-chance save when the page is hidden or closed (survives navigation). */
    savePositionOnExit: (slug, lesson, body) => {
      if (typeof fetch !== "function") return;
      fetch(`${baseURL}/account/learning/${enc(slug)}/lessons/${enc(lesson)}/position`, {
        method: "PUT",
        keepalive: true,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Customer-CSRF": readCookie("tpa_customer_csrf"),
        },
        body: JSON.stringify(body),
      }).catch(() => {});
    },
    notebook: (params) => get("/account/study/notebook", params),
    notebookExportUrl: (format, course) =>
      `${baseURL}/account/study/export?format=${enc(format)}${course ? `&course=${enc(course)}` : ""}`,
    readingPreferences: () => get("/account/study/preferences"),
    saveReadingPreferences: (body) =>
      client.put("/account/study/preferences", body).then((r) => r.data),
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

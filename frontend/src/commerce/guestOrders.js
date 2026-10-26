/**
 * Order tokens for guest checkout, kept in this tab's session storage (never in a URL or a
 * cookie). A token opens one order for a limited time; the emailed access link is the way
 * back in from another device or after the tab is closed.
 */
const PREFIX = "tpa-guest-order:";

export const guestOrders = {
  save(orderId, token) {
    try {
      window.sessionStorage.setItem(PREFIX + orderId, token);
    } catch {
      // Storage unavailable (private mode): the emailed link still works.
    }
  },
  token(orderId) {
    try {
      return window.sessionStorage.getItem(PREFIX + orderId) ?? "";
    } catch {
      return "";
    }
  },
  forget(orderId) {
    try {
      window.sessionStorage.removeItem(PREFIX + orderId);
    } catch {
      // nothing to clean up
    }
  },
};

export const ORDER_STATUS = {
  pending: "Pending",
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  failed: "Failed",
  cancelled: "Cancelled",
  partially_refunded: "Partially refunded",
  refunded: "Refunded",
};

export const REFUND_STATUS = {
  manual_review: "Awaiting manual refund",
  pending_provider: "Waiting for Paystack",
  processed: "Refunded",
  failed: "Failed",
  rejected: "Cancelled",
};

export const EMAIL_STATUS = {
  sent: "Sent",
  development_console: "Not sent (development log only)",
  memory: "Not sent (test outbox)",
  not_configured: "Not sent (email not configured)",
  failed: "Delivery failed",
};

export function newRequestKey() {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

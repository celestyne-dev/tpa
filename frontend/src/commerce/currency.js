/**
 * The shopper's display currency (a per-browser preference). Prices are never
 * converted: a product simply shows the price set for that currency, if any.
 *
 * Batch 16: TPA charges in KES only. When Settings › Shop has a valid rate, KES prices
 * also show an approximate US dollar amount (usdEstimate). It is display-only: orders
 * and Paystack charges always use the KES amount.
 */
const KEY = "tpa:currency";
const EVENT = "tpa:currency-changed";

export const currencyStore = {
  read() {
    try {
      return window.localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(code) {
    try {
      window.localStorage.setItem(KEY, code);
    } catch {
      // ignore: the choice lasts until the page reloads
    }
    window.dispatchEvent(new Event(EVENT));
  },
  subscribe(callback) {
    window.addEventListener(EVENT, callback);
    window.addEventListener("storage", callback);
    return () => {
      window.removeEventListener(EVENT, callback);
      window.removeEventListener("storage", callback);
    };
  },
};

export function priceIn(product, currency) {
  return product?.prices?.find((p) => p.currency === currency) ?? null;
}

export const availabilityLabel = {
  "coming-soon": "Coming soon",
  available: "Available now",
  free: "Free",
  unavailable: "Not available",
};

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  currencyDisplay: "narrowSymbol",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * The approximate US dollar amount for a KES amount, e.g. "US$15.06", or null when there
 * is no valid rate, the amount isn't in KES, or it isn't a positive whole number of cents.
 * `estimate` is the site's shop.usd_estimate ({ kes_per_usd: "129.50", … }).
 */
export function usdEstimate(amountMinor, currency, estimate) {
  if (currency !== "KES" || !estimate) return null;
  const rate = Number(estimate.kes_per_usd);
  if (!Number.isFinite(rate) || rate <= 0) return null;
  if (!Number.isInteger(amountMinor) || amountMinor <= 0) return null;
  // KES and USD both have 2 minor-unit digits: cents = KES cents / (KES per USD).
  const cents = Math.round(amountMinor / rate);
  if (cents <= 0) return null;
  return `US${USD.format(cents / 100)}`;
}

/**
 * The shopper's display currency (a per-browser preference). Prices are never
 * converted: a product simply shows the price set for that currency, if any.
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

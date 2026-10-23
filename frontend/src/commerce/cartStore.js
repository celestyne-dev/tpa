/**
 * The shopping cart: a list of product ids kept in this browser (localStorage).
 * It never holds prices; the server quotes every cart. Reads are hydration-safe
 * through useSyncExternalStore (the server snapshot is always an empty cart).
 */
const KEY = "tpa:cart";
const EVENT = "tpa:cart-changed";
const MAX_ITEMS = 20;
const EMPTY = [];
let cachedRaw = null;
let cachedItems = EMPTY;

function read() {
  let raw = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  if (raw === cachedRaw) return cachedItems;
  cachedRaw = raw;
  try {
    const parsed = JSON.parse(raw ?? "[]");
    cachedItems = Array.isArray(parsed)
      ? parsed.filter((i) => i && typeof i.id === "string" && /^[0-9a-f]{16}$/.test(i.id))
      : EMPTY;
  } catch {
    cachedItems = EMPTY;
  }
  return cachedItems;
}

function write(items) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
  } catch {
    // Private mode or storage disabled: the cart lasts for this page only.
    cachedRaw = JSON.stringify(items);
    cachedItems = items;
  }
  window.dispatchEvent(new Event(EVENT));
}

export const cartStore = {
  getSnapshot: () => (typeof window === "undefined" ? EMPTY : read()),
  getServerSnapshot: () => EMPTY,
  subscribe(callback) {
    const onStorage = (event) => {
      if (event.key === null || event.key === KEY) callback();
    };
    window.addEventListener(EVENT, callback);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT, callback);
      window.removeEventListener("storage", onStorage);
    };
  },
  /** Adds a product once (a digital licence has no meaningful quantity). */
  add(product) {
    const items = read();
    if (items.some((i) => i.id === product.id)) return false;
    write([...items, { id: product.id, slug: product.slug, title: product.title }]);
    return true;
  },
  remove(id) {
    write(read().filter((i) => i.id !== id));
  },
  removeMany(ids) {
    const drop = new Set(ids);
    write(read().filter((i) => !drop.has(i.id)));
  },
  clear() {
    write([]);
  },
};

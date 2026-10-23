// Kept separate so tests can load the chunk up front (like the admin chunk).
export const loadCommerce = () => import("@/commerce/pages");

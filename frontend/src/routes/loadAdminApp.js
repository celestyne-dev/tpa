// The admin area is a separate, lazily loaded chunk that is never prerendered.
// Kept in its own module so tests can load the chunk up front (see preloadAdminApp).
export const loadAdminApp = () => import("@/admin/AdminApp");

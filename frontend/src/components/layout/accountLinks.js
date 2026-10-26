import { routes } from "@/config/navigation";

export const accountLinks = [
  { to: routes.account, label: "My account" },
  { to: routes.accountLibrary, label: "My library" },
  { to: routes.accountOrders, label: "Orders" },
  { to: routes.accountSettings, label: "Settings" },
];

const AUTH_PAGES = new Set([
  routes.signIn,
  routes.register,
  routes.forgotPassword,
  routes.resetPassword,
  routes.verifyEmail,
]);

/** "Log in" link that brings people back to the page they were on (same-site paths only). */
export function signInHref(current) {
  const path = (current || "").split("?")[0];
  if (!current || current === routes.home || AUTH_PAGES.has(path)) return routes.signIn;
  return `${routes.signIn}?next=${encodeURIComponent(current)}`;
}

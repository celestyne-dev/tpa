import { legacyAuthRoutes, routes } from "@/config/navigation";

/** Where a Batch 05 account address now lives (keeping ?next= and the #token fragment). */
export function legacyTarget(pathname, search = "", hash = "") {
  let target = legacyAuthRoutes[pathname] ?? routes.signIn;
  // The old reset page doubled as "forgot password" when it had no token.
  if (target === routes.resetPassword && !hash.includes("token=")) target = routes.forgotPassword;
  return `${target}${search}${hash}`;
}

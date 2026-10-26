import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useDispatch, useSelector } from "react-redux";
import { readCookie } from "@/services/adminApi";
import { useShopApi } from "@/components/products/shopApiContext";
import { customerSignedOut, fetchCustomer, selectCustomer } from "@/store/slices/customerSlice";
import { Status } from "@/store/status";

/** Readable companion of the HttpOnly customer session cookie (set and cleared together). */
export const CUSTOMER_CSRF_COOKIE = "tpa_customer_csrf";

const subscribe = () => () => {};

/**
 * Confirmed customer sign-in state for navigation.
 *
 * - "unknown" while prerendering and hydrating, so the HTML always matches;
 * - "signed_out" when the browser holds no customer session (no request needed);
 * - otherwise "signed_in"/"signed_out" as confirmed by GET /account/me.
 */
export function useAccountStatus() {
  const dispatch = useDispatch();
  const hydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const entry = useSelector(selectCustomer);
  const hasSessionCookie = hydrated && Boolean(readCookie(CUSTOMER_CSRF_COOKIE));
  useEffect(() => {
    if (hasSessionCookie && entry.status === Status.idle) dispatch(fetchCustomer());
  }, [dispatch, hasSessionCookie, entry.status]);

  let status = "unknown";
  if (entry.status === Status.succeeded) status = entry.profile ? "signed_in" : "signed_out";
  else if (hydrated && !hasSessionCookie) status = "signed_out";
  return { status, customer: status === "signed_in" ? entry.profile : null };
}

/** Sign out on the server, forget the profile locally, then run `after`. */
export function useSignOut() {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  return useCallback(
    async (after) => {
      try {
        await shopApi.logout();
      } finally {
        dispatch(customerSignedOut());
        after?.();
      }
    },
    [shopApi, dispatch],
  );
}

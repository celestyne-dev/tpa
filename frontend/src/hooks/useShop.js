import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useDispatch, useSelector } from "react-redux";
import { cartStore } from "@/commerce/cartStore";
import { currencyStore } from "@/commerce/currency";
import { fetchCustomer, selectCustomer } from "@/store/slices/customerSlice";
import { selectSite } from "@/store/slices/siteSlice";
import { Status } from "@/store/status";

/** Cart items in this browser ([] during prerendering and hydration). */
export function useCart() {
  return useSyncExternalStore(
    cartStore.subscribe,
    cartStore.getSnapshot,
    cartStore.getServerSnapshot,
  );
}

const noStored = () => null;

/** The display currency: the shopper's choice if offered, otherwise the first CMS currency. */
export function useDisplayCurrency() {
  const site = useSelector(selectSite)?.data;
  const currencies = site?.shop?.display_currencies?.length
    ? site.shop.display_currencies
    : ["USD"];
  const stored = useSyncExternalStore(currencyStore.subscribe, currencyStore.read, noStored);
  const currency = stored && currencies.includes(stored) ? stored : currencies[0];
  const setCurrency = useCallback((code) => currencyStore.set(code), []);
  return { currency, setCurrency, currencies };
}

/** The signed-in customer, loaded in the browser only. */
export function useCustomer({ load = true } = {}) {
  const dispatch = useDispatch();
  const state = useSelector(selectCustomer);
  useEffect(() => {
    if (load) dispatch(fetchCustomer());
  }, [dispatch, load]);
  const refresh = useCallback(() => dispatch(fetchCustomer({ force: true })), [dispatch]);
  return {
    customer: state.profile,
    isLoading: state.status === Status.idle || state.status === Status.loading,
    isSignedIn: Boolean(state.profile),
    error: state.error,
    refresh,
  };
}

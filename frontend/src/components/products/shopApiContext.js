import { createContext, useContext } from "react";
import { createShopApi } from "@/services/shopApi";

let fallback;

/** The customer API (tests provide a fake through the App's provider). */
export const ShopApiContext = createContext(null);

export function useShopApi() {
  const api = useContext(ShopApiContext);
  if (api) return api;
  fallback ??= createShopApi();
  return fallback;
}

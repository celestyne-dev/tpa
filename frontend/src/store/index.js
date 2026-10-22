import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { createAdminApi } from "@/services/adminApi";
import { createContentApi } from "@/services/contentApi";
import articles from "./slices/articlesSlice";
import auth, { sessionExpired } from "./slices/authSlice";
import pages from "./slices/pagesSlice";
import products from "./slices/productsSlice";
import site from "./slices/siteSlice";
import topics from "./slices/topicsSlice";

/**
 * Redux holds shared state: public server content (prerendered, serialised
 * into the HTML and hydrated) and the admin session profile. Local UI state
 * and individual admin screens' data stay in components.
 */
export const rootReducer = combineReducers({ site, topics, articles, products, pages, auth });

export function createAppStore({
  preloadedState,
  api = createContentApi(),
  adminApi = createAdminApi(),
} = {}) {
  const store = configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefault) => getDefault({ thunk: { extraArgument: { api, adminApi } } }),
  });
  adminApi.onSessionExpired?.(() => store.dispatch(sessionExpired()));
  return store;
}

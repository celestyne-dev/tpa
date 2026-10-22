import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { createContentApi } from "@/services/contentApi";
import articles from "./slices/articlesSlice";
import products from "./slices/productsSlice";
import site from "./slices/siteSlice";
import topics from "./slices/topicsSlice";

/**
 * Redux holds shared server content (site settings, topics, articles,
 * products) so it can be prerendered, serialised into the HTML and hydrated.
 * Purely local UI state (menus, filters) stays in components.
 */
export const rootReducer = combineReducers({ site, topics, articles, products });

export function createAppStore({ preloadedState, api = createContentApi() } = {}) {
  return configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefault) => getDefault({ thunk: { extraArgument: { api } } }),
  });
}

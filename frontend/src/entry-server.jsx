import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router";
import { App } from "./app/App";
import { renderHeadToString } from "./components/seo/head";
import { createHeadCollector } from "./components/seo/headContext";
import { getRouteLoaders } from "./routes/routeConfig";
import { createApiClient } from "./services/apiClient";
import { createContentApi } from "./services/contentApi";
import { createAppStore } from "./store";

export { routeTable } from "./routes/routeConfig";
export { staticRoutes, routes } from "./config/navigation";
export { siteConfig } from "./config/site";
export { safeJson } from "./utils/structuredData";

export function createServerApi(baseURL) {
  return createContentApi(createApiClient({ baseURL, timeout: 15000 }));
}

/**
 * Renders one URL to static HTML. Data is loaded from the Flask API first so
 * the markup contains the full content. Returns 404 status for unknown pages
 * and throws on API failures other than 404 (so a build never ships pages
 * with missing content).
 */
export async function render(url, api) {
  const store = createAppStore({ api });
  const pathname = new URL(url, "http://prerender.local").pathname;
  const results = await Promise.all(
    getRouteLoaders(pathname).map((thunk) => store.dispatch(thunk)),
  );

  for (const result of results) {
    const error = result.error && result.payload;
    if (error && error.status !== 404) {
      throw new Error(`API request failed while rendering ${url}: ${error.code} ${error.message}`);
    }
  }

  const headCollector = createHeadCollector();
  const html = renderToString(
    <StaticRouter location={url}>
      <App store={store} headCollector={headCollector} />
    </StaticRouter>,
  );

  return {
    html,
    head: headCollector.head ? renderHeadToString(headCollector.head) : "",
    status: headCollector.status,
    state: store.getState(),
  };
}

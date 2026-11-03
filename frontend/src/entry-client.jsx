import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/fraunces/opsz-italic.css";
import "@fontsource-variable/inter/index.css";
import "./assets/styles/globals.css";

import { StrictMode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./app/App";
import { configureSite } from "./config/site";
import { createAdminApi } from "./services/adminApi";
import { createShopApi } from "./services/shopApi";
import { createAppStore } from "./store";

const container = document.getElementById("root");

/**
 * The prerendered page's data, from <script type="application/json" id="tpa-state">
 * (inert JSON, so the Content-Security-Policy can forbid inline scripts).
 */
function readPreloadedState() {
  const element = document.getElementById("tpa-state");
  if (!element) return undefined;
  try {
    return JSON.parse(element.textContent);
  } catch {
    return undefined;
  } finally {
    element.remove();
  }
}

const preloadedState = readPreloadedState();
if (preloadedState?.site?.data) configureSite(preloadedState.site.data);
const adminApi = createAdminApi();
const shopApi = createShopApi();
const store = createAppStore({ preloadedState, adminApi, shopApi });

const app = (
  <StrictMode>
    <BrowserRouter>
      <App store={store} adminApi={adminApi} shopApi={shopApi} />
    </BrowserRouter>
  </StrictMode>
);

// Prerendered pages are hydrated; the dev server and the 404 fallback render fresh.
if (preloadedState && container.dataset.prerendered === "true") {
  hydrateRoot(container, app);
} else {
  createRoot(container).render(app);
}

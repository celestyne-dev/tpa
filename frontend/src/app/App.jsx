import { Provider } from "react-redux";
import { AdminApiContext } from "@/admin/adminApiContext";
import { ShopApiContext } from "@/components/products/shopApiContext";
import { HeadContext } from "@/components/seo/headContext";
import { AppRoutes } from "@/routes/AppRoutes";
import { createAdminApi } from "@/services/adminApi";

const defaultAdminApi = createAdminApi();

/** Application root shared by the browser entry, the prerenderer and tests. */
export function App({ store, adminApi = defaultAdminApi, shopApi = null, headCollector = null }) {
  return (
    <HeadContext.Provider value={headCollector}>
      <AdminApiContext.Provider value={adminApi}>
        <ShopApiContext.Provider value={shopApi}>
          <Provider store={store}>
            <AppRoutes />
          </Provider>
        </ShopApiContext.Provider>
      </AdminApiContext.Provider>
    </HeadContext.Provider>
  );
}

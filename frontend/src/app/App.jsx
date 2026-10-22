import { Provider } from "react-redux";
import { HeadContext } from "@/components/seo/headContext";
import { AppRoutes } from "@/routes/AppRoutes";

/** Application root shared by the browser entry, the prerenderer and tests. */
export function App({ store, headCollector = null }) {
  return (
    <HeadContext.Provider value={headCollector}>
      <Provider store={store}>
        <AppRoutes />
      </Provider>
    </HeadContext.Provider>
  );
}

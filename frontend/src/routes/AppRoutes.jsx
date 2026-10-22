import { Route, Routes } from "react-router";
import { RootLayout } from "@/components/layout/RootLayout";
import { routeTable } from "./routeConfig";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<RootLayout />}>
        {routeTable.map(({ path, Component }) => (
          <Route key={path} path={path} element={<Component />} />
        ))}
      </Route>
    </Routes>
  );
}

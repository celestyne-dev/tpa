import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { RootLayout } from "@/components/layout/RootLayout";
import { routeTable } from "./routeConfig";

// The admin area is a separate, lazily loaded chunk that is never prerendered.
const AdminApp = lazy(() => import("@/admin/AdminApp"));

function AdminFallback() {
  return (
    <div role="status" className="p-10 text-center text-muted">
      Loading admin…
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/admin/*"
        element={
          <Suspense fallback={<AdminFallback />}>
            <AdminApp />
          </Suspense>
        }
      />
      <Route element={<RootLayout />}>
        {routeTable.map(({ path, Component }) => (
          <Route key={path} path={path} element={<Component />} />
        ))}
      </Route>
    </Routes>
  );
}

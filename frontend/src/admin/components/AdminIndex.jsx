import { Navigate } from "react-router";
import { usePermissions } from "../hooks/usePermissions";
import { adminSections } from "../navigation";
import { DashboardPage } from "../pages/DashboardPage";
import { Forbidden } from "./Guards";

/** /admin: the dashboard when permitted, otherwise the first area the user may open. */
export function AdminIndex() {
  const { can } = usePermissions();
  if (can("dashboard.view")) return <DashboardPage />;
  const first = adminSections
    .flatMap((section) => section.items)
    .find((item) => item.to !== "/admin" && can(item.permission));
  return first ? <Navigate to={first.to} replace /> : <Forbidden />;
}

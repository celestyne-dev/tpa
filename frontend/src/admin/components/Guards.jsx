import { ShieldAlert } from "lucide-react";
import { useSelector } from "react-redux";
import { Navigate, useLocation } from "react-router";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { selectAuth } from "@/store/slices/authSlice";
import { usePermissions } from "../hooks/usePermissions";

export function SessionLoading() {
  return (
    <div
      role="status"
      aria-label="Checking your session"
      className="mx-auto max-w-md space-y-3 p-10"
    >
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <span className="sr-only">Checking your session…</span>
    </div>
  );
}

export function RequireAuth({ children }) {
  const { status } = useSelector(selectAuth);
  const location = useLocation();
  if (status === "idle" || status === "loading") return <SessionLoading />;
  if (status !== "authenticated") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/admin/login?next=${next}`} replace />;
  }
  return children;
}

export function Forbidden() {
  return (
    <EmptyState
      icon={ShieldAlert}
      title="You don't have access to this area"
      description="Your role does not include permission for this page. Ask a super administrator if you need access."
    />
  );
}

export function RequirePermission({ permission, children }) {
  const { can } = usePermissions();
  return can(permission) ? children : <Forbidden />;
}

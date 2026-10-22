import { KeyRound, Lock, Plus } from "lucide-react";
import { Link } from "react-router";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { RoleKindBadge } from "../components/RoleBadges";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

export function RolesPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const roles = useAdminQuery(() => api.roles.list(), []);
  const canManage = can("roles.manage");

  return (
    <>
      <AdminPageHeader
        title="Roles & Permissions"
        description="Roles bundle permissions. People can hold several roles; they receive every permission of their active roles."
        breadcrumbs={[{ label: "Roles & Permissions" }]}
        actions={
          canManage && (
            <ButtonLink to="/admin/roles/new" size="sm">
              <Plus aria-hidden />
              New role
            </ButtonLink>
          )
        }
      />
      <div className="mb-4 grid gap-3 text-sm sm:grid-cols-3">
        <p className="rounded-xl border border-charcoal/10 bg-white p-4">
          <span className="font-semibold">Built-in roles</span> (Super Admin, Editor, Moderator,
          Analyst) are protected and cannot be edited, deactivated or deleted.
        </p>
        <p className="rounded-xl border border-charcoal/10 bg-white p-4">
          <span className="font-semibold">Templates</span> are ready-made starting points. Edit them
          freely; modules that are not built yet stay locked.
        </p>
        <p className="rounded-xl border border-charcoal/10 bg-white p-4">
          <Lock aria-hidden className="mr-1 inline size-3.5" />
          <span className="font-semibold">Sensitive permissions</span> (role management, payment
          configuration, security settings) remain with Super Admin only.
        </p>
      </div>
      {!canManage && (
        <p className="mb-4 rounded-lg bg-beige px-4 py-2 text-sm">
          You can view roles. Only a super administrator can change them.
        </p>
      )}
      {roles.error ? (
        <ErrorState title="We couldn't load roles" onRetry={roles.reload} />
      ) : (
        <DataTable
          caption="Roles"
          rows={roles.data}
          loading={roles.loading}
          empty={{ icon: KeyRound, title: "No roles yet" }}
          columns={[
            {
              key: "role",
              header: "Role",
              render: (r) => (
                <div className="min-w-0">
                  <Link
                    to={`/admin/roles/${r.id}`}
                    className="font-medium text-charcoal hover:text-sage-700"
                  >
                    {r.label}
                  </Link>
                  <p className="max-w-md text-xs text-muted">{r.description}</p>
                </div>
              ),
            },
            { key: "kind", header: "Type", render: (r) => <RoleKindBadge kind={r.kind} /> },
            {
              key: "permissions",
              header: "Permissions",
              render: (r) => (r.grants_all ? "All" : r.permissions.length),
            },
            { key: "users", header: "Users", render: (r) => r.user_count },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.is_active ? "active" : "inactive"} />,
            },
          ]}
        />
      )}
    </>
  );
}

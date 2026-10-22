import { Link } from "react-router";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SettingsForm } from "../components/SettingsForm";
import { usePermissions } from "../hooks/usePermissions";

export function FooterPage() {
  const { can } = usePermissions();
  return (
    <>
      <AdminPageHeader
        title="Footer"
        description="Footer text, newsletter link, contact details, copyright line and an optional promotion."
        breadcrumbs={[{ label: "Footer" }]}
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {[
          ["Footer columns and legal links", "/admin/navigation", "navigation.manage"],
          ["Social links and contact email", "/admin/settings", "settings.manage"],
          ["Logo for dark backgrounds", "/admin/branding", "branding.manage"],
        ].map(([label, to, perm]) => (
          <div key={label} className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm">
            <p className="font-medium text-charcoal">{label}</p>
            {can(perm) ? (
              <Link to={to} className="mt-1 inline-block text-sage-700 underline">
                Edit
              </Link>
            ) : (
              <p className="mt-1 text-muted">Managed by another role.</p>
            )}
          </div>
        ))}
      </div>
      <SettingsForm groups={["Footer"]} />
    </>
  );
}

import { Link } from "react-router";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SettingsForm } from "../components/SettingsForm";
import { usePermissions } from "../hooks/usePermissions";

// Groups with their own screens (Branding, Footer, Navigation).
const DEDICATED = ["Branding", "Footer", "Header"];

export function SettingsPage() {
  const { can } = usePermissions();
  return (
    <>
      <AdminPageHeader
        title="Site settings"
        description="Contact details, social links, newsletter status, SEO defaults and technical settings."
        breadcrumbs={[{ label: "Settings" }]}
      />
      <p className="mb-4 text-sm text-muted">
        Logos and styles are in{" "}
        {can("branding.manage") ? (
          <Link className="underline" to="/admin/branding">
            Branding
          </Link>
        ) : (
          "Branding"
        )}
        ; footer text in{" "}
        {can("settings.manage") ? (
          <Link className="underline" to="/admin/footer">
            Footer
          </Link>
        ) : (
          "Footer"
        )}
        . Server configuration and secrets are never editable here.
      </p>
      <SettingsForm exclude={DEDICATED} />
    </>
  );
}

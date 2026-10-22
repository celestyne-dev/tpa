import { LayoutTemplate } from "lucide-react";
import { Link } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";

export function PagesPage() {
  const api = useAdminApi();
  const { data, loading, error, reload } = useAdminQuery(() => api.pages.list(), []);
  return (
    <>
      <AdminPageHeader
        title="Pages"
        description="CMS page records and their structured sections."
        breadcrumbs={[{ label: "Pages" }]}
      />
      <p className="mb-4 rounded-lg bg-gold-100/60 px-4 py-3 text-sm text-ink">
        Section configuration is stored and validated here. The public pages still render their
        approved designs from code; connecting sections to the live pages arrives with the page
        builder (Batch 04).
      </p>
      {error ? (
        <ErrorState title="We couldn't load pages" onRetry={reload} />
      ) : (
        <DataTable
          caption="Pages"
          rows={data}
          loading={loading}
          empty={{
            icon: LayoutTemplate,
            title: "No pages yet",
            description:
              "Run `flask --app wsgi cms seed-defaults` to create the homepage section configuration.",
          }}
          columns={[
            {
              key: "title",
              header: "Page",
              render: (p) => (
                <div>
                  <Link to={`/admin/pages/${p.id}`} className="font-medium hover:text-sage-700">
                    {p.title}
                  </Link>
                  <p className="text-xs text-muted">/{p.slug === "home" ? "" : p.slug}</p>
                </div>
              ),
            },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
            { key: "section_count", header: "Sections" },
            {
              key: "rendered",
              header: "Live rendering",
              render: (p) => (p.rendered_publicly ? "Connected" : "Not yet connected"),
            },
            { key: "updated", header: "Updated", render: (p) => formatDateTime(p.updated_at) },
          ]}
        />
      )}
    </>
  );
}

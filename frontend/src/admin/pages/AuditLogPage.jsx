import { ScrollText } from "lucide-react";
import { useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { SelectField } from "../components/Fields";
import { Pagination } from "../components/Pagination";
import { useAdminQuery } from "../hooks/useAdminQuery";

const RESOURCE_OPTIONS = [
  "",
  "article",
  "topic",
  "tag",
  "author",
  "user",
  "role",
  "auth",
  "site_settings",
  "navigation_menu",
  "page",
  "page_section",
].map((v) => ({ value: v, label: v ? v.replaceAll("_", " ") : "All resources" }));

function summarise(details) {
  if (!details || !Object.keys(details).length) return "—";
  return Object.entries(details)
    .slice(0, 4)
    .map(([k, v]) =>
      v && typeof v === "object" && "to" in v
        ? `${k} → ${JSON.stringify(v.to)}`
        : `${k}: ${typeof v === "object" ? "…" : v}`,
    )
    .join(" · ");
}

export function AuditLogPage() {
  const api = useAdminApi();
  const [resource, setResource] = useState("");
  const [page, setPage] = useState(1);
  const { data, meta, loading, error, reload } = useAdminQuery(
    () => api.audit.list({ resource_type: resource || undefined, page, page_size: 25 }),
    [resource, page],
  );
  return (
    <>
      <AdminPageHeader
        title="Audit log"
        description="Important administrative actions. Secrets are never recorded."
        breadcrumbs={[{ label: "Audit log" }]}
      />
      <div className="mb-4 max-w-xs">
        <SelectField
          label="Resource"
          options={RESOURCE_OPTIONS}
          value={resource}
          onChange={(e) => {
            setResource(e.target.value);
            setPage(1);
          }}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load the audit log" onRetry={reload} />
      ) : (
        <DataTable
          caption="Audit log entries"
          rows={data}
          loading={loading}
          empty={{
            icon: ScrollText,
            title: "No entries",
            description: "Administrative actions will appear here.",
          }}
          columns={[
            {
              key: "when",
              header: "When",
              render: (e) => <time dateTime={e.created_at}>{formatDateTime(e.created_at)}</time>,
            },
            {
              key: "action",
              header: "Action",
              render: (e) => <span className="font-mono text-xs">{e.action}</span>,
            },
            {
              key: "actor",
              header: "By",
              render: (e) => e.actor?.display_name ?? "System / anonymous",
            },
            {
              key: "resource",
              header: "Resource",
              render: (e) => `${e.resource_type}${e.resource_id ? ` #${e.resource_id}` : ""}`,
            },
            {
              key: "details",
              header: "Details",
              render: (e) => <span className="text-xs text-muted">{summarise(e.details)}</span>,
            },
          ]}
        />
      )}
      <Pagination pagination={meta?.pagination} onPage={setPage} />
    </>
  );
}

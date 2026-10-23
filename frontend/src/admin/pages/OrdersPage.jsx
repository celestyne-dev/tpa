import { Download, ShoppingBag } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { ORDER_STATUS } from "../components/commerceLabels";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/Fields";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

export function OrdersPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({
    q: "",
    status: "",
    mode: "",
    date_from: "",
    date_to: "",
    needs_review: "",
  });
  const [page, setPage] = useState(1);
  const params = Object.fromEntries(Object.entries({ ...filters, page }).filter(([, v]) => v));
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.orders.list(params),
    [JSON.stringify(params)],
  );
  const set = (patch) => {
    setPage(1);
    setFilters({ ...filters, ...patch });
  };
  const total = meta?.total ?? 0;
  return (
    <>
      <AdminPageHeader
        title="Orders"
        description="Every checkout, its verified payment status and the download access it granted. Test-mode orders are labelled."
        breadcrumbs={[{ label: "Orders" }]}
        actions={
          can("orders.export") && (
            <a
              href={api.orders.exportUrl(params)}
              className="inline-flex items-center gap-2 rounded-full border border-charcoal/20 px-4 py-2 text-sm"
            >
              <Download aria-hidden className="size-4" /> Export CSV
            </a>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <TextField
          className="lg:col-span-2"
          label="Search (order, email, reference)"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
          options={[
            { value: "", label: "Any" },
            ...Object.entries(ORDER_STATUS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <SelectField
          label="Mode"
          value={filters.mode}
          onChange={(e) => set({ mode: e.target.value })}
          options={[
            { value: "", label: "Live and test" },
            { value: "live", label: "Live" },
            { value: "test", label: "Test" },
          ]}
        />
        <TextField
          type="date"
          label="From"
          value={filters.date_from}
          onChange={(e) => set({ date_from: e.target.value })}
        />
        <TextField
          type="date"
          label="To"
          value={filters.date_to}
          onChange={(e) => set({ date_to: e.target.value })}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load orders" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Orders"
            rows={data}
            loading={loading}
            empty={{ icon: ShoppingBag, title: "No orders found" }}
            columns={[
              {
                key: "number",
                header: "Order",
                render: (o) => (
                  <div>
                    <Link to={`/admin/orders/${o.id}`} className="font-medium hover:underline">
                      {o.number}
                    </Link>
                    {o.needs_review && (
                      <span className="ml-2 text-xs font-semibold text-red-800">Needs review</span>
                    )}
                    <p className="text-xs text-muted">{o.email}</p>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (o) => <StatusBadge status={ORDER_STATUS[o.status] ?? o.status} />,
              },
              { key: "mode", header: "Mode", render: (o) => (o.mode === "test" ? "Test" : "Live") },
              { key: "total", header: "Total", render: (o) => o.total.formatted },
              { key: "created", header: "Created", render: (o) => formatDateTime(o.created_at) },
            ]}
          />
          <Pagination
            pagination={{
              page,
              page_size: 25,
              total,
              total_pages: Math.max(1, Math.ceil(total / 25)),
              has_next: page * 25 < total,
              has_prev: page > 1,
            }}
            onPage={setPage}
          />
        </>
      )}
    </>
  );
}

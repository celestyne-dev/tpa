import { BadgeCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

function Entitlements() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ q: "", status: "" });
  const [acting, setActing] = useState(null);
  const [reason, setReason] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () => api.entitlements.list(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))),
    [filters.q, filters.status],
  );
  const submit = async () => {
    try {
      await api.entitlements.action(acting.item.id, acting.action, reason);
      notify(
        acting.action === "revoke"
          ? "Access revoked. New downloads are blocked immediately."
          : "Access restored.",
      );
      setActing(null);
      setReason("");
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <TextField
          label="Customer email"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          options={[
            { value: "", label: "Any" },
            { value: "active", label: "Active" },
            { value: "revoked", label: "Revoked" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load access records" onRetry={reload} />
      ) : (
        <DataTable
          caption="Download entitlements"
          rows={data}
          loading={loading}
          empty={{ icon: BadgeCheck, title: "No access records" }}
          columns={[
            {
              key: "customer",
              header: "Customer",
              render: (e) => (
                <Link className="underline" to={`/admin/customers/${e.customer.id}`}>
                  {e.customer.email}
                </Link>
              ),
            },
            { key: "product", header: "Product", render: (e) => e.product.title },
            {
              key: "source",
              header: "Source",
              render: (e) => (e.order_number ? `${e.source} · ${e.order_number}` : e.source),
            },
            { key: "status", header: "Status", render: (e) => <StatusBadge status={e.status} /> },
            {
              key: "downloads",
              header: "Downloads",
              render: (e) =>
                `${e.download_count}${e.download_limit ? ` / ${e.download_limit}` : ""}`,
            },
            { key: "granted", header: "Granted", render: (e) => formatDateTime(e.granted_at) },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              render: (e) =>
                can("entitlements.manage") && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setActing({ item: e, action: e.status === "active" ? "revoke" : "restore" })
                    }
                  >
                    {e.status === "active" ? "Revoke" : "Restore"}
                  </Button>
                ),
            },
          ]}
        />
      )}
      {acting && (
        <Modal
          open
          title={
            acting.action === "revoke" ? "Revoke download access?" : "Restore download access?"
          }
          onClose={() => setActing(null)}
          footer={
            <>
              <Button variant="outline" onClick={() => setActing(null)}>
                Cancel
              </Button>
              <Button onClick={submit} disabled={!reason.trim()}>
                {acting.action === "revoke" ? "Revoke" : "Restore"}
              </Button>
            </>
          }
        >
          <p className="mb-3 text-sm text-muted">
            {acting.item.product.title} for {acting.item.customer.email}. Bundle access also applies
            to the products inside the bundle.
          </p>
          <TextField
            label="Reason (recorded in the history)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Modal>
      )}
    </>
  );
}

const DENIAL_LABELS = {
  entitlement_revoked: "Access revoked or refunded",
  entitlement_expired: "Access period ended",
  limit_reached: "Download limit reached",
  link_expired: "Link expired",
  link_used_up: "Link used up",
  session_mismatch: "Not signed in to the owning account",
  version_not_allowed: "Version not available to this buyer",
};

function DownloadSummary({ productId, onProduct }) {
  const api = useAdminApi();
  const { data } = useAdminQuery(() => api.downloads.summary({ days: 30 }), []);
  if (!data) return null;
  return (
    <section aria-labelledby="download-summary" className="mb-6 space-y-4">
      <h2 id="download-summary" className="text-lg font-medium">
        Last {data.days} days
      </h2>
      <dl className="grid gap-3 sm:grid-cols-3">
        {[
          ["Downloads served", data.served],
          ["Links issued", data.authorized],
          ["Requests refused", data.denied],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-charcoal/10 bg-white p-4">
            <dt className="text-sm text-muted">{label}</dt>
            <dd className="mt-1 text-2xl font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-charcoal/10 bg-white p-4">
          <h3 className="text-sm font-medium">Most downloaded</h3>
          {data.top_resources.length ? (
            <ol className="mt-2 space-y-1 text-sm">
              {data.top_resources.map((r) => (
                <li key={r.product_id} className="flex justify-between gap-2">
                  <button
                    type="button"
                    className={`text-left hover:underline ${productId === String(r.product_id) ? "font-medium" : ""}`}
                    onClick={() => onProduct(String(r.product_id))}
                  >
                    {r.title}
                  </button>
                  <span className="text-muted">{r.downloads}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-sm text-muted">No downloads in this period.</p>
          )}
        </div>
        <div className="rounded-xl border border-charcoal/10 bg-white p-4">
          <h3 className="text-sm font-medium">Why requests were refused</h3>
          {data.denial_reasons.length ? (
            <ul className="mt-2 space-y-1 text-sm">
              {data.denial_reasons.map((r) => (
                <li key={r.reason} className="flex justify-between gap-2">
                  <span>{DENIAL_LABELS[r.reason] ?? r.reason}</span>
                  <span className="text-muted">{r.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted">Nothing was refused in this period.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function Downloads() {
  const api = useAdminApi();
  const [status, setStatus] = useState("");
  const [productId, setProductId] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () =>
      api.downloads.list({
        ...(status && { status }),
        ...(productId && { product_id: productId }),
      }),
    [status, productId],
  );
  return (
    <>
      <DownloadSummary productId={productId} onProduct={setProductId} />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <SelectField
          className="max-w-xs"
          label="Result"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={[
            { value: "", label: "Any" },
            { value: "served", label: "Served" },
            { value: "authorized", label: "Authorised" },
            { value: "denied", label: "Denied" },
          ]}
        />
        {productId && (
          <button type="button" className="mb-2 text-sm underline" onClick={() => setProductId("")}>
            Show all resources
          </button>
        )}
      </div>
      {error ? (
        <ErrorState title="We couldn't load download activity" onRetry={reload} />
      ) : (
        <DataTable
          caption="Download activity"
          rows={data}
          loading={loading}
          empty={{ icon: BadgeCheck, title: "No downloads yet" }}
          columns={[
            { key: "at", header: "When", render: (d) => formatDateTime(d.at) },
            { key: "product", header: "Product", render: (d) => d.product ?? "—" },
            { key: "file", header: "File", render: (d) => d.file ?? "—" },
            { key: "status", header: "Result", render: (d) => <StatusBadge status={d.status} /> },
            {
              key: "reason",
              header: "Reason",
              render: (d) => (d.reason ? (DENIAL_LABELS[d.reason] ?? d.reason) : "—"),
            },
            { key: "ip", header: "IP", render: (d) => d.ip_address ?? "—" },
          ]}
        />
      )}
    </>
  );
}

export function EntitlementsPage() {
  const { can } = usePermissions();
  const tabs = [
    can("entitlements.view") && ["access", "Access"],
    can("downloads.audit") && ["downloads", "Download activity"],
  ].filter(Boolean);
  const [tab, setTab] = useState(tabs[0]?.[0] ?? "access");
  return (
    <>
      <AdminPageHeader
        title="Download Entitlements"
        description="Who can download what, why, and every download attempt (allowed or refused)."
        breadcrumbs={[{ label: "Download Entitlements" }]}
      />
      <div
        role="tablist"
        aria-label="Views"
        className="mb-5 flex gap-1 border-b border-charcoal/10"
      >
        {tabs.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              tab === key ? "border-sage-700" : "border-transparent text-muted",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "access" ? <Entitlements /> : <Downloads />}
    </>
  );
}

import { Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { EMAIL_STATUS, ORDER_STATUS } from "../components/commerceLabels";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Pagination } from "../components/Pagination";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";

export function CustomersPage() {
  const api = useAdminApi();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.customers.list({ q, page }),
    [q, page],
  );
  const total = meta?.total ?? 0;
  return (
    <>
      <AdminPageHeader
        title="Customers"
        description="Customer accounts are separate from administrators and never grant admin access."
        breadcrumbs={[{ label: "Customers" }]}
      />
      <TextField
        className="mb-4 max-w-sm"
        label="Search by email or name"
        value={q}
        onChange={(e) => {
          setPage(1);
          setQ(e.target.value);
        }}
      />
      {error ? (
        <ErrorState title="We couldn't load customers" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Customers"
            rows={data}
            loading={loading}
            empty={{ icon: Users, title: "No customers yet" }}
            columns={[
              {
                key: "email",
                header: "Customer",
                render: (c) => (
                  <div>
                    <Link to={`/admin/customers/${c.id}`} className="font-medium hover:underline">
                      {c.email}
                    </Link>
                    <p className="text-xs text-muted">{c.display_name}</p>
                  </div>
                ),
              },
              { key: "status", header: "Status", render: (c) => <StatusBadge status={c.status} /> },
              {
                key: "verified",
                header: "Email",
                render: (c) => (c.email_verified ? "Confirmed" : "Not confirmed"),
              },
              { key: "orders", header: "Paid orders", render: (c) => c.paid_orders },
              { key: "created", header: "Joined", render: (c) => formatDateTime(c.created_at) },
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

export function CustomerDetailPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const {
    data: customer,
    error,
    loading,
    reload,
    setData,
  } = useAdminQuery(() => api.customers.get(id), [id]);
  const options = useAdminQuery(
    () => api.products.options().catch(() => ({ data: { products: [] } })),
    [],
  );
  const [notes, setNotes] = useState(null);
  const [grant, setGrant] = useState({ product_id: "", reason: "" });
  const [confirmDelete, setConfirmDelete] = useState(false);
  if (error) return <ErrorState title="We couldn't load this customer" onRetry={reload} />;
  if (loading || !customer)
    return (
      <p role="status" className="text-muted">
        Loading customer…
      </p>
    );
  const can = customer.can;
  const run = async (fn, message) => {
    try {
      const res = await fn();
      if (res?.data?.email) setData(res.data);
      else reload();
      notify(typeof message === "function" ? message(res) : message);
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const active = customer.status === "active";
  // Guest-checkout buyer records (no password, can't sign in) can be disabled too.
  const enabled = active || customer.status === "guest";
  return (
    <>
      <AdminPageHeader
        title={customer.email}
        breadcrumbs={[{ label: "Customers", to: "/admin/customers" }, { label: customer.email }]}
        description={`Joined ${formatDateTime(customer.created_at)} · last sign-in ${customer.last_login_at ? formatDateTime(customer.last_login_at) : "never"}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {can.support && active && (
              <>
                <Button
                  variant="outline"
                  onClick={() =>
                    run(
                      () => api.customers.support(customer.id, "resend-verification"),
                      (res) =>
                        `Verification email: ${EMAIL_STATUS[res.data.delivery] ?? res.data.delivery}.`,
                    )
                  }
                >
                  Resend verification
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    run(
                      () => api.customers.support(customer.id, "password-reset"),
                      (res) =>
                        `Reset email: ${EMAIL_STATUS[res.data.delivery] ?? res.data.delivery}.`,
                    )
                  }
                >
                  Send password reset
                </Button>
              </>
            )}
            {can.manage && customer.status !== "deleted" && (
              <Button
                variant="outline"
                onClick={() =>
                  run(
                    () =>
                      api.customers.update(customer.id, {
                        status: enabled ? "disabled" : "active",
                      }),
                    enabled ? "Account disabled and signed out." : "Account reactivated.",
                  )
                }
              >
                {enabled ? "Disable account" : "Reactivate"}
              </Button>
            )}
          </div>
        }
      />
      <div className="mb-5 flex flex-wrap gap-2">
        <StatusBadge status={customer.status} />
        <StatusBadge status={customer.email_verified ? "email confirmed" : "email not confirmed"} />
        {customer.is_test_account && <StatusBadge status="test account" />}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Support</h2>
          {can.manage && customer.status !== "deleted" && (
            <CheckboxField
              className="mt-3"
              label="Test account"
              hint="May use checkout while payments are in test mode (no real money)."
              checked={customer.is_test_account}
              onChange={(e) =>
                run(
                  () => api.customers.update(customer.id, { is_test_account: e.target.checked }),
                  "Saved.",
                )
              }
            />
          )}
          {(can.support || can.manage) && customer.status !== "deleted" && (
            <div className="mt-4 space-y-2">
              <TextAreaField
                label="Support notes (internal)"
                rows={4}
                value={notes ?? customer.support_notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <Button
                size="sm"
                disabled={notes === null}
                onClick={() =>
                  run(
                    () => api.customers.update(customer.id, { support_notes: notes }),
                    "Notes saved.",
                  ).then(() => setNotes(null))
                }
              >
                Save notes
              </Button>
            </div>
          )}
          {can.manage && customer.status !== "deleted" && (
            <Button
              size="sm"
              variant="outline"
              className="mt-5 border-red-700 text-red-800"
              onClick={() => setConfirmDelete(true)}
            >
              Delete & anonymise account
            </Button>
          )}
        </section>
        {customer.orders && (
          <section className="rounded-xl border border-charcoal/10 bg-white p-5">
            <h2 className="text-lg font-medium">Orders</h2>
            {customer.orders.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No orders.</p>
            ) : (
              <ul className="mt-3 space-y-1 text-sm">
                {customer.orders.map((o) => (
                  <li key={o.id}>
                    <Link to={`/admin/orders/${o.id}`} className="underline">
                      {o.number}
                    </Link>{" "}
                    · {ORDER_STATUS[o.status] ?? o.status} · {o.total.formatted}
                    {o.mode === "test" ? " · test" : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
        {customer.entitlements && (
          <section className="rounded-xl border border-charcoal/10 bg-white p-5">
            <h2 className="text-lg font-medium">Library access</h2>
            <ul className="mt-3 space-y-1 text-sm">
              {customer.entitlements.length === 0 && <li className="text-muted">None.</li>}
              {customer.entitlements.map((e) => (
                <li key={e.id}>
                  {e.product.title} · {e.source} · <StatusBadge status={e.status} /> ·{" "}
                  {e.download_count} download(s)
                </li>
              ))}
            </ul>
            {can.entitlements && customer.status === "active" && (
              <form
                className="mt-4 grid gap-2"
                onSubmit={(ev) => {
                  ev.preventDefault();
                  run(
                    () =>
                      api.customers.grant(customer.id, {
                        product_id: Number(grant.product_id),
                        reason: grant.reason,
                      }),
                    "Access granted.",
                  ).then(() => setGrant({ product_id: "", reason: "" }));
                }}
              >
                <SelectField
                  label="Grant access to a product"
                  value={grant.product_id}
                  onChange={(e) => setGrant({ ...grant, product_id: e.target.value })}
                  options={[
                    { value: "", label: "Choose…" },
                    ...(options.data?.products ?? []).map((p) => ({ value: p.id, label: p.title })),
                  ]}
                />
                <TextField
                  label="Reason"
                  value={grant.reason}
                  onChange={(e) => setGrant({ ...grant, reason: e.target.value })}
                />
                <Button
                  type="submit"
                  size="sm"
                  disabled={!grant.product_id || !grant.reason.trim()}
                >
                  Grant access
                </Button>
              </form>
            )}
          </section>
        )}
        {customer.downloads && (
          <section className="rounded-xl border border-charcoal/10 bg-white p-5">
            <h2 className="text-lg font-medium">Recent download activity</h2>
            <ul className="mt-3 space-y-1 text-sm">
              {customer.downloads.length === 0 && <li className="text-muted">None.</li>}
              {customer.downloads.map((d) => (
                <li key={d.id}>
                  {formatDateTime(d.at)} · {d.product ?? "—"} · {d.file ?? ""} · {d.status}
                  {d.reason ? ` (${d.reason})` : ""}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
      <ConfirmDialog
        open={confirmDelete}
        tone="danger"
        title="Delete and anonymise this account?"
        message="Personal details are removed, sessions end and library access is revoked. Orders and payment records are kept for accounting. This cannot be undone."
        confirmLabel="Delete account"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() =>
          run(() => api.customers.anonymise(customer.id), "Account anonymised.").then(() =>
            setConfirmDelete(false),
          )
        }
      />
    </>
  );
}

import { Gift, Plus } from "lucide-react";
import { useState } from "react";
import { newKey } from "@/commerce/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDate } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

function GrantForm({ plans, onClose, onSaved }) {
  const api = useAdminApi();
  const [form, setForm] = useState({
    customer_id: "",
    plan_id: plans[0]?.id ?? "",
    expires_at: "",
    reason: "",
  });
  const [key] = useState(newKey);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.memberships.createGrant({ ...form, idempotency_key: key });
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  return (
    <Modal
      open
      title="Grant complimentary membership"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="grant-form" disabled={busy}>
            Grant access
          </Button>
        </>
      }
    >
      <form id="grant-form" onSubmit={submit} className="space-y-3">
        <ErrorSummary error={error} />
        <p className="text-sm text-muted">
          Gives the plan&apos;s included courses and resources until the expiry date. It is not a
          payment and isn&apos;t counted as a paid subscriber or revenue.
        </p>
        <TextField
          label="Customer ID"
          hint="From the customer's page in Customers."
          required
          value={form.customer_id}
          onChange={(e) => set({ customer_id: e.target.value })}
        />
        <SelectField
          label="Plan"
          value={form.plan_id}
          onChange={(e) => set({ plan_id: e.target.value })}
          options={plans.map((p) => ({ value: p.id, label: p.name }))}
        />
        <TextField
          label="Access until"
          type="date"
          required
          value={form.expires_at}
          onChange={(e) => set({ expires_at: e.target.value })}
        />
        <TextAreaField
          label="Reason (kept in the audit log)"
          required
          value={form.reason}
          onChange={(e) => set({ reason: e.target.value })}
        />
      </form>
    </Modal>
  );
}

/** Complimentary memberships: expiry, reason, who granted and who revoked. */
export function MembershipGrantsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const canManage = can("memberships.manage_subscriptions");
  const [status, setStatus] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () => api.memberships.grants(status ? { status } : undefined),
    [status],
  );
  const plans = useAdminQuery(() => api.memberships.list(), []);
  const [creating, setCreating] = useState(false);
  const revoke = async (grant) => {
    const reason = window.prompt("Why is this complimentary access being revoked?");
    if (!reason) return;
    try {
      await api.memberships.revokeGrant(grant.id, { reason });
      notify("Complimentary access revoked.");
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const published = (plans.data ?? []).filter((p) => p.status === "published");
  return (
    <>
      <AdminPageHeader
        title="Complimentary memberships"
        description="Free, time-limited membership access granted by staff."
        breadcrumbs={[
          { label: "Membership plans", to: "/admin/membership-plans" },
          { label: "Complimentary" },
        ]}
        actions={
          canManage &&
          published.length > 0 && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus aria-hidden /> Grant access
            </Button>
          )
        }
      />
      <SelectField
        className="mb-4 max-w-xs"
        label="Status"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        options={[
          { value: "", label: "All" },
          { value: "active", label: "Active" },
          { value: "expired", label: "Expired" },
          { value: "revoked", label: "Revoked" },
        ]}
      />
      {error ? (
        <ErrorState title="We couldn't load complimentary memberships" onRetry={reload} />
      ) : (
        <DataTable
          caption="Complimentary memberships"
          rows={data}
          loading={loading}
          empty={{ icon: Gift, title: "No complimentary memberships", description: "" }}
          columns={[
            { key: "customer", header: "Customer", render: (g) => g.customer.email },
            { key: "plan", header: "Plan", render: (g) => g.plan.name },
            { key: "until", header: "Until", render: (g) => formatDate(g.expires_at) },
            { key: "status", header: "Status", render: (g) => <StatusBadge status={g.status} /> },
            {
              key: "reason",
              header: "Reason",
              render: (g) => (
                <span>
                  {g.reason}
                  <span className="block text-xs text-muted">
                    by {g.granted_by ?? "—"}
                    {g.revoked_by && ` · revoked by ${g.revoked_by}: ${g.revoke_reason}`}
                  </span>
                </span>
              ),
            },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              render: (g) =>
                canManage && g.status === "active" ? (
                  <Button size="sm" variant="outline" onClick={() => revoke(g)}>
                    Revoke
                  </Button>
                ) : null,
            },
          ]}
        />
      )}
      {creating && (
        <GrantForm
          plans={published}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            notify("Complimentary access granted.");
            reload();
          }}
        />
      )}
    </>
  );
}

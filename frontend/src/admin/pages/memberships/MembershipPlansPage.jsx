import { Crown, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

const priceText = (price) => price?.price.formatted ?? "—";

/** Membership plans (tiers): content, prices and included products. */
export function MembershipPlansPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canManage = can("memberships.manage");
  const { data, error, loading, reload } = useAdminQuery(() => api.memberships.list(), []);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [createError, setCreateError] = useState(null);
  const create = async (event) => {
    event.preventDefault();
    setCreateError(null);
    try {
      const res = await api.memberships.create({ name });
      notify("Plan created as a draft.");
      navigate(`/admin/membership-plans/${res.data.id}`);
    } catch (err) {
      setCreateError(err);
    }
  };
  const columns = [
    {
      key: "name",
      header: "Plan",
      render: (p) => (
        <Link
          to={`/admin/membership-plans/${p.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {p.name}
          <span className="block text-xs font-normal text-muted">
            /membership · tier {p.tier_rank}
          </span>
        </Link>
      ),
    },
    { key: "month", header: "Monthly", render: (p) => priceText(p.prices.month) },
    { key: "year", header: "Yearly", render: (p) => priceText(p.prices.year) },
    { key: "included", header: "Included", render: (p) => `${p.included_count} items` },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
  ];
  return (
    <>
      <AdminPageHeader
        title="Membership plans"
        description="Plans, prices and benefits shown on the public membership page."
        actions={
          canManage && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus aria-hidden /> New plan
            </Button>
          )
        }
      />
      <p role="note" className="mb-4 rounded-xl bg-cream p-3 text-sm">
        Joining is only possible in Paystack test mode once billing is enabled and each plan is
        synced with Paystack; otherwise the membership page shows a “coming soon” notice. Members
        get access only after Paystack confirms their first payment.
      </p>
      {error ? (
        <ErrorState title="We couldn't load the membership plans" onRetry={reload} />
      ) : (
        <DataTable
          caption="Membership plans"
          columns={columns}
          rows={data}
          loading={loading}
          empty={{
            icon: Crown,
            title: "No membership plans yet",
            description: canManage ? "Create the first plan to start." : "",
          }}
        />
      )}
      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New membership plan"
        footer={
          <>
            <Button variant="outline" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" form="new-plan" disabled={!name.trim()}>
              Create draft
            </Button>
          </>
        }
      >
        <form id="new-plan" onSubmit={create} className="space-y-3">
          <ErrorSummary error={createError} />
          <TextField
            label="Plan name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </form>
      </Modal>
    </>
  );
}

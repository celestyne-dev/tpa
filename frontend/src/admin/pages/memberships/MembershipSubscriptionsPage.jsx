import { Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { SelectField, TextField } from "../../components/Fields";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { SUBSCRIPTION_STATUS } from "./subscriptionLabels";

const PAGE_SIZE = 25;
const NEXT_LABEL = { renewal: "Renews", cancellation: "Ends (cancelled)", expiry: "Access ends" };

function NextDate({ next }) {
  if (!next?.at) return "—";
  return `${NEXT_LABEL[next.type]} ${formatDate(next.at)}`;
}

/** Subscribers: search, status and interval filters, payment-problem indicators. */
export function MembershipSubscriptionsPage() {
  const api = useAdminApi();
  const [filters, setFilters] = useState({ q: "", status: "", interval: "", flag: "" });
  const [page, setPage] = useState(1);
  const params = Object.fromEntries(Object.entries({ ...filters, page }).filter(([, v]) => v));
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.memberships.subscriptions(params),
    [JSON.stringify(params)],
  );
  const total = meta?.total ?? 0;
  const set = (patch) => {
    setPage(1);
    setFilters((f) => ({ ...f, ...patch }));
  };
  return (
    <>
      <AdminPageHeader
        title="Subscribers"
        description="Membership subscriptions, their billing state and upcoming dates."
        breadcrumbs={[
          { label: "Membership plans", to: "/admin/membership-plans" },
          { label: "Subscribers" },
        ]}
      />
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <TextField
          label="Search email, name or subscription"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
          options={[
            { value: "", label: "Any status" },
            ...Object.entries(SUBSCRIPTION_STATUS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <SelectField
          label="Billing interval"
          value={filters.interval}
          onChange={(e) => set({ interval: e.target.value })}
          options={[
            { value: "", label: "Monthly and yearly" },
            { value: "month", label: "Monthly" },
            { value: "year", label: "Yearly" },
          ]}
        />
        <SelectField
          label="Show"
          value={filters.flag}
          onChange={(e) => set({ flag: e.target.value })}
          options={[
            { value: "", label: "Everything" },
            { value: "payment_problem", label: "Failed payments / grace" },
            { value: "cancelling", label: "Cancelling at period end" },
            { value: "renewing_soon", label: "Renewing within 7 days" },
            { value: "unlinked", label: "Not linked to Paystack" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load subscribers" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Subscribers"
            rows={data}
            loading={loading}
            empty={{ icon: Users, title: "No subscriptions match", description: "" }}
            columns={[
              {
                key: "customer",
                header: "Member",
                render: (s) => (
                  <div>
                    <Link
                      to={`/admin/membership-subscriptions/${s.id}`}
                      className="font-medium hover:underline"
                    >
                      {s.customer.email}
                    </Link>
                    <p className="text-xs text-muted">{s.customer.name}</p>
                  </div>
                ),
              },
              {
                key: "plan",
                header: "Plan",
                render: (s) =>
                  `${s.plan.name} · ${s.interval === "month" ? "Monthly" : "Yearly"} · ${s.price.formatted}`,
              },
              {
                key: "status",
                header: "Status",
                render: (s) => (
                  <span className="flex flex-wrap items-center gap-1">
                    <StatusBadge status={s.status} />
                    {s.cancel_at_period_end && s.status !== "ended" && (
                      <span className="text-xs text-muted">cancelling</span>
                    )}
                    {s.test_mode && <span className="text-xs text-muted">test</span>}
                  </span>
                ),
              },
              { key: "next", header: "Next", render: (s) => <NextDate next={s.next} /> },
            ]}
          />
          <Pagination
            pagination={{
              page,
              page_size: PAGE_SIZE,
              total,
              total_pages: Math.max(1, Math.ceil(total / PAGE_SIZE)),
              has_prev: page > 1,
              has_next: page * PAGE_SIZE < total,
            }}
            onPage={setPage}
          />
        </>
      )}
    </>
  );
}

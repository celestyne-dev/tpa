import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { TextField } from "../../components/Fields";
import { useAdminQuery } from "../../hooks/useAdminQuery";

const END_REASON = {
  cancelled: "Cancelled",
  payment_failed: "Payment failed",
  refunded: "Refunded",
  account_deleted: "Account deleted",
};

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function MoneyList({ label, rows }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-lg">None in this period</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {rows.map((r) => (
            <li key={`${r.mode}-${r.amount.currency}`} className="text-lg font-semibold">
              {r.amount.formatted}
              {r.mode === "test" && <span className="ml-2 text-xs font-normal">test mode</span>}
              {r.count != null && (
                <span className="ml-2 text-xs font-normal text-muted">{r.count} payments</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Membership reports from verified payments and subscription records. */
export function MembershipReportsPage() {
  const api = useAdminApi();
  const [range, setRange] = useState({ date_from: "", date_to: "" });
  const params = Object.fromEntries(Object.entries(range).filter(([, v]) => v));
  const { data, error, loading, reload } = useAdminQuery(
    () => api.memberships.reports(params),
    [range.date_from, range.date_to],
  );
  return (
    <>
      <AdminPageHeader
        title="Membership reports"
        description="Subscribers, renewals, churn and verified membership revenue."
        breadcrumbs={[
          { label: "Membership plans", to: "/admin/membership-plans" },
          { label: "Reports" },
        ]}
      />
      <div className="mb-6 flex flex-wrap gap-3">
        <TextField
          label="From"
          type="date"
          value={range.date_from}
          onChange={(e) => setRange((r) => ({ ...r, date_from: e.target.value }))}
        />
        <TextField
          label="To"
          type="date"
          value={range.date_to}
          onChange={(e) => setRange((r) => ({ ...r, date_to: e.target.value }))}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load the reports" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : !data.has_data && data.current.complimentary === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No membership data yet"
          description="Reports fill in once members join through verified checkout."
        />
      ) : (
        <div className="space-y-8">
          <section aria-labelledby="r-now">
            <h2 id="r-now" className="mb-3 text-lg font-medium">
              Right now
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Paid subscribers"
                value={data.current.paid_subscribers}
                hint={`${data.current.monthly} monthly · ${data.current.yearly} yearly`}
              />
              <Stat
                label="Failed payment / grace"
                value={data.current.past_due + data.current.grace}
              />
              <Stat label="Cancelling at period end" value={data.current.cancelling} />
              <Stat
                label="Complimentary"
                value={data.current.complimentary}
                hint="Not counted as paid"
              />
            </div>
          </section>
          <section aria-labelledby="r-period">
            <h2 id="r-period" className="mb-3 text-lg font-medium">
              {data.range.from} to {data.range.to}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="New subscriptions" value={data.period.new_subscriptions} />
              <Stat label="Renewals" value={data.period.renewals} />
              <Stat label="Cancellations requested" value={data.period.cancellations_requested} />
              <Stat
                label="Ended"
                value={Object.values(data.period.ended).reduce((a, b) => a + b, 0)}
                hint={
                  Object.entries(data.period.ended)
                    .map(([k, v]) => `${END_REASON[k] ?? k}: ${v}`)
                    .join(" · ") || undefined
                }
              />
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <MoneyList label="Verified revenue" rows={data.revenue} />
              <MoneyList label="Refunds" rows={data.refunds} />
              <MoneyList label="Net" rows={data.net_revenue} />
            </div>
          </section>
          <section aria-labelledby="r-trend">
            <h2 id="r-trend" className="mb-3 text-lg font-medium">
              Monthly trend
            </h2>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Monthly membership trend</caption>
              <thead className="text-muted">
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Active at start</th>
                  <th scope="col">New</th>
                  <th scope="col">Renewals</th>
                  <th scope="col">Ended</th>
                  <th scope="col">Churn</th>
                </tr>
              </thead>
              <tbody>
                {data.trend.map((m) => (
                  <tr key={m.month} className="border-t border-charcoal/10">
                    <td className="py-1">{m.month}</td>
                    <td>{m.active_at_start}</td>
                    <td>{m.new}</td>
                    <td>{m.renewals}</td>
                    <td>{m.ended}</td>
                    <td>
                      {m.churn_rate == null
                        ? "Not enough data"
                        : `${(m.churn_rate * 100).toFixed(1)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section aria-labelledby="r-access">
            <h2 id="r-access" className="mb-3 text-lg font-medium">
              Membership access
            </h2>
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="Members with access" value={data.access.members_with_access} />
              <Stat
                label="Active membership entitlements"
                value={data.access.entitlements}
                hint={data.access.by_product_type.map((t) => `${t.type}: ${t.count}`).join(" · ")}
              />
              <Stat
                label="Course enrolments via membership"
                value={data.access.course_enrollments}
              />
            </div>
          </section>
          <ul className="list-disc pl-5 text-xs text-muted">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

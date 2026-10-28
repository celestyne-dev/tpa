import { Crown } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { RankTable, Stat } from "./analyticsParts";

const PRESETS = [
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "365d", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
];
const modeLabel = (m) => (m === "test" ? "Test" : "Live");
const moneyList = (rows, key) =>
  rows.length
    ? rows.map((r) => `${r[key].formatted}${r.mode === "test" ? " (test)" : ""}`).join(" · ")
    : "—";

/** Membership growth, churn, realised revenue and recurring estimates. */
export function MembershipAnalytics() {
  const api = useAdminApi();
  const [preset, setPreset] = useState("90d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [plan, setPlan] = useState("");
  const params = {
    ...(preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset }),
    ...(plan ? { plan } : {}),
  };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.membershipAnalytics(params),
    [JSON.stringify(params)],
  );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Membership period"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="Membership from"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="Membership to"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        <SelectField
          label="Plan"
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
          options={[
            { value: "", label: "All plans" },
            ...(data?.plan_options ?? []).map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load membership analytics" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : !data.has_data && data.current.complimentary === 0 ? (
        <EmptyState
          icon={Crown}
          title="No memberships yet"
          description="Figures appear once members join through verified checkout or receive complimentary access."
        />
      ) : (
        <>
          <section
            aria-label="Membership overview"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Stat
              label="Paid members"
              value={data.current.paid_subscribers}
              hint={`${data.current.monthly} monthly · ${data.current.yearly} yearly`}
            />
            <Stat
              label="Complimentary"
              value={data.current.complimentary}
              hint="Not counted as paid"
            />
            <Stat
              label="Past due / grace"
              value={data.current.past_due + data.current.grace}
              hint={`${data.current.cancelling} cancelling`}
            />
            <Stat
              label="MRR (estimate)"
              value={moneyList(data.recurring_estimate, "mrr")}
              hint="Active, non-cancelling subscriptions"
            />
          </section>
          <section
            aria-label="Membership period"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Stat label="New subscriptions" value={data.period.new_subscriptions} />
            <Stat label="Renewals" value={data.period.renewals} />
            <Stat label="Cancellations requested" value={data.period.cancellations_requested} />
            <Stat
              label="Ended"
              value={Object.values(data.period.ended).reduce((a, b) => a + b, 0)}
            />
          </section>
          <section aria-label="Realised membership revenue" className="grid gap-3 md:grid-cols-3">
            <Stat label="Verified revenue" value={moneyList(data.revenue, "amount")} />
            <Stat label="Refunds" value={moneyList(data.refunds, "amount")} />
            <Stat label="Net" value={moneyList(data.net_revenue, "amount")} />
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            <RankTable
              caption="Paid members by plan"
              rows={data.by_plan}
              columns={[
                { header: "Plan", render: (r) => r.plan },
                {
                  header: "Interval",
                  render: (r) => (r.interval === "month" ? "Monthly" : "Yearly"),
                },
                { header: "Mode", render: (r) => modeLabel(r.mode) },
                { header: "Members", numeric: true, render: (r) => r.paid_members },
              ]}
            />
            <RankTable
              caption="Revenue by plan"
              rows={data.revenue_by_plan}
              empty="No verified membership payments in this period."
              columns={[
                { header: "Plan", render: (r) => `${r.plan}${r.mode === "test" ? " (test)" : ""}` },
                { header: "Gross", numeric: true, render: (r) => r.gross.formatted },
                { header: "Refunds", numeric: true, render: (r) => r.refunds.formatted },
                { header: "Net", numeric: true, render: (r) => r.net.formatted },
              ]}
            />
            <RankTable
              caption="Recurring revenue estimate"
              rows={data.recurring_estimate}
              empty="No active, non-cancelling subscriptions."
              columns={[
                { header: "Mode", render: (r) => modeLabel(r.mode) },
                { header: "Subscriptions", numeric: true, render: (r) => r.subscriptions },
                { header: "MRR", numeric: true, render: (r) => r.mrr.formatted },
                { header: "ARR", numeric: true, render: (r) => r.arr.formatted },
              ]}
            />
            <RankTable
              caption="Membership trend"
              rows={data.trend}
              columns={[
                { header: "Month", render: (r) => r.month },
                { header: "New", numeric: true, render: (r) => r.new },
                { header: "Renewals", numeric: true, render: (r) => r.renewals },
                { header: "Ended", numeric: true, render: (r) => r.ended },
                {
                  header: "Churn",
                  numeric: true,
                  render: (r) =>
                    r.churn_rate == null
                      ? "Not enough data"
                      : `${(r.churn_rate * 100).toFixed(1)}%`,
                },
              ]}
            />
          </div>
          <section aria-label="Membership access" className="grid gap-3 sm:grid-cols-3">
            <Stat label="Members with access" value={data.access.members_with_access} />
            <Stat
              label="Membership entitlements"
              value={data.access.entitlements}
              hint={`${data.access.complimentary_entitlements} complimentary`}
            />
            <Stat label="Course enrolments via membership" value={data.access.course_enrollments} />
          </section>
        </>
      )}
      {data && (
        <section aria-label="Membership definitions" className="rounded-xl bg-cream p-4 text-sm">
          <h2 className="font-semibold">How these are defined</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {Object.values(data.definitions).map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

import { Download } from "lucide-react";
import { useState } from "react";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { label, money } from "../../components/partnerships/formValues";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

const COLUMNS = [
  ["pipeline_expected_minor", "Pipeline (expected, not revenue)"],
  ["contracted_minor", "Contracted"],
  ["completed_value_minor", "Completed campaigns"],
  ["invoiced_minor", "Invoiced (manual)"],
  ["received_verified_minor", "Received (verified)"],
  ["received_unverified_minor", "Received (unverified)"],
  ["outstanding_minor", "Outstanding"],
  ["affiliate_reported_minor", "Affiliate commissions reported"],
  ["affiliate_paid_minor", "Affiliate commissions paid"],
];

export function PartnershipReportsPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ date_from: "", date_to: "", currency: "", channel: "" });
  const { data, error, loading, reload } = useAdminQuery(
    () => api.partnershipReports.get(filters),
    [JSON.stringify(filters)],
  );
  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));
  return (
    <>
      <AdminPageHeader
        title="Partnership reports"
        description="Each currency and each category is reported separately. Nothing is converted, estimated or inferred from clicks."
        breadcrumbs={[{ label: "Partnership reports" }]}
        actions={
          can("partnership_reports.export") && (
            <a
              className={buttonStyles({ variant: "outline" })}
              href={api.partnershipReports.exportUrl(filters)}
            >
              <Download aria-hidden className="size-4" /> Export CSV
            </a>
          )
        }
      />
      <div className="mb-5 flex flex-wrap gap-3 text-sm">
        <label>
          From{" "}
          <input
            type="date"
            className="ml-1 rounded border px-2 py-1"
            value={filters.date_from}
            onChange={set("date_from")}
          />
        </label>
        <label>
          To{" "}
          <input
            type="date"
            className="ml-1 rounded border px-2 py-1"
            value={filters.date_to}
            onChange={set("date_to")}
          />
        </label>
        <label>
          Currency
          <select
            className="ml-1 rounded border px-2 py-1"
            value={filters.currency}
            onChange={set("currency")}
          >
            {["", "USD", "KES", "EUR", "GBP"].map((c) => (
              <option key={c} value={c}>
                {c || "All (separately)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Channel
          <select
            className="ml-1 rounded border px-2 py-1"
            value={filters.channel}
            onChange={set("channel")}
          >
            {["", "website", "newsletter", "social", "other"].map((c) => (
              <option key={c} value={c}>
                {c || "All"}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? (
        <ErrorState title="We couldn't load the report" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Totals by currency"
            rows={data?.by_currency}
            loading={loading}
            rowKey={(r) => r.currency}
            empty={{ title: "No figures recorded for this period" }}
            columns={[
              { key: "currency", header: "Currency", render: (r) => r.currency },
              ...COLUMNS.map(([key, text]) => ({
                key,
                header: text,
                render: (r) => money(r[key], r.currency),
              })),
            ]}
          />
          {data && (
            <div className="mt-6 grid gap-6 md:grid-cols-3">
              <section>
                <h2 className="font-medium">Campaigns by status</h2>
                <ul className="mt-2 text-sm">
                  {Object.entries(data.campaigns_by_status).map(([k, v]) => (
                    <li key={k}>
                      {label(k)}: {v}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h2 className="font-medium">Bookings by state</h2>
                <ul className="mt-2 text-sm">
                  {Object.entries(data.bookings_by_state).map(([k, v]) => (
                    <li key={k}>
                      {label(k)}: {v}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h2 className="font-medium">Placement utilisation</h2>
                <ul className="mt-2 text-sm">
                  {data.booking_utilization.map((u) => (
                    <li key={u.key}>
                      {u.placement}: {u.booked_days} of {u.capacity_days} days booked
                      {u.utilization_percent != null && ` (${u.utilization_percent}%)`}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
          <ul className="mt-6 list-disc pl-5 text-sm text-muted">
            {(data?.notes ?? []).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

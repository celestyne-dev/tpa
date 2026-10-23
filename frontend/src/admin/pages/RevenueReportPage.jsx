import { Download } from "lucide-react";
import { useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

export function RevenueReportPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ mode: "live", date_from: "", date_to: "" });
  const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
  const { data, error, loading, reload } = useAdminQuery(
    () => api.reports.revenue(params),
    [JSON.stringify(params)],
  );
  return (
    <>
      <AdminPageHeader
        title="Revenue Reports"
        description="Figures come only from payments verified with Paystack. Each currency is reported separately."
        breadcrumbs={[{ label: "Revenue Reports" }]}
        actions={
          can("finance.export") && (
            <a
              href={api.reports.revenueExportUrl(params)}
              className="inline-flex items-center gap-2 rounded-full border border-charcoal/20 px-4 py-2 text-sm"
            >
              <Download aria-hidden className="size-4" /> Export CSV
            </a>
          )
        }
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <SelectField
          label="Payments"
          value={filters.mode}
          onChange={(e) => setFilters({ ...filters, mode: e.target.value })}
          options={[
            { value: "live", label: "Live (real money)" },
            { value: "test", label: "Test mode" },
          ]}
        />
        <TextField
          type="date"
          label="From"
          value={filters.date_from}
          onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
        />
        <TextField
          type="date"
          label="To"
          value={filters.date_to}
          onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load the report" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading report…
        </p>
      ) : (
        <div className="space-y-8">
          {data.mode === "test" && (
            <p className="rounded-xl bg-gold-100/60 p-3 text-sm">
              Test-mode figures: no real money was received.
            </p>
          )}
          {data.currencies.length === 0 ? (
            <p className="rounded-xl border border-dashed border-charcoal/20 p-6 text-center text-muted">
              No {data.mode} orders in this period.
            </p>
          ) : (
            data.currencies.map((c) => (
              <section key={c.currency} aria-labelledby={`cur-${c.currency}`}>
                <h2 id={`cur-${c.currency}`} className="text-lg font-medium">
                  {c.currency}
                </h2>
                <dl className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ["Orders", c.orders],
                    ["Paid orders", c.paid_orders],
                    ["Failed orders", c.failed_orders],
                    ["Gross sales", c.gross.formatted],
                    ["Refunds", c.refunds.formatted],
                    ["Net (before fees)", c.net.formatted],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-charcoal/10 bg-white p-4">
                      <dt className="text-xs text-muted">{label}</dt>
                      <dd className="mt-1 text-xl font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))
          )}
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-xl border border-charcoal/10 bg-white p-5">
              <h2 className="text-lg font-medium">Revenue by product</h2>
              {data.by_product.length === 0 ? (
                <p className="mt-3 text-sm text-muted">No paid orders.</p>
              ) : (
                <table className="mt-3 w-full text-sm">
                  <caption className="sr-only">Revenue by product</caption>
                  <thead className="text-left text-xs text-muted">
                    <tr>
                      <th className="py-1 font-medium">Product</th>
                      <th className="font-medium">Units</th>
                      <th className="text-right font-medium">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_product.map((r) => (
                      <tr
                        key={`${r.product_id}-${r.currency}`}
                        className="border-t border-charcoal/5"
                      >
                        <td className="py-2">{r.title}</td>
                        <td>{r.units}</td>
                        <td className="text-right">{r.revenue.formatted}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
            <section className="rounded-xl border border-charcoal/10 bg-white p-5">
              <h2 className="text-lg font-medium">Downloads</h2>
              <p className="mt-1 text-sm text-muted">
                {data.total_downloads} file download(s) · {data.free_claims} free resource claim(s)
                · {data.failed_payment_attempts} failed or abandoned payment attempt(s)
              </p>
              <ul className="mt-3 space-y-1 text-sm">
                {data.downloads.map((d) => (
                  <li key={d.product_id ?? "none"} className={cn("flex justify-between")}>
                    <span>{d.title}</span>
                    <span>{d.downloads}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

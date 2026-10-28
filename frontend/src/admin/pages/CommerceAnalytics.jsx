import { ShoppingBag } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";
import { RankTable, Stat } from "./analyticsParts";
import { ANALYTICS_PRESETS } from "./analyticsPresets";

const PRESETS = ANALYTICS_PRESETS;
const STATUS_LABEL = {
  pending: "Pending",
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  partially_refunded: "Partly refunded",
  refunded: "Refunded",
  failed: "Failed",
  cancelled: "Cancelled / expired",
};
const GROUP_LABEL = { course: "Courses", resource: "Premium resources", bundle: "Bundles" };

/** One currency's money trend; bars scale to that currency only (never mixed). */
function CurrencyTrend({ series }) {
  const max = Math.max(1, ...series.points.map((p) => p.gross.amount_minor));
  return (
    <section
      aria-label={`Revenue trend (${series.currency})`}
      className="rounded-xl border border-charcoal/10 bg-white p-4"
    >
      <h3 className="mb-2 text-base font-semibold">Revenue and orders ({series.currency})</h3>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Revenue per period in {series.currency}</caption>
        <thead className="text-muted">
          <tr>
            <th scope="col" className="w-28">
              Period
            </th>
            <th scope="col">Gross</th>
            <th scope="col" className="text-right">
              Refunds
            </th>
            <th scope="col" className="text-right">
              Orders
            </th>
          </tr>
        </thead>
        <tbody>
          {series.points.map((p) => (
            <tr key={p.period}>
              <td className="py-0.5 pr-2 whitespace-nowrap">{p.period}</td>
              <td className="py-0.5">
                <div className="flex items-center gap-2">
                  <div
                    aria-hidden
                    className="h-3 rounded bg-gold-500"
                    style={{
                      width: `${(p.gross.amount_minor / max) * 100}%`,
                      minWidth: p.gross.amount_minor ? 2 : 0,
                    }}
                  />
                  <span>{p.gross.formatted}</span>
                </div>
              </td>
              <td className="py-0.5 text-right">{p.refunds.formatted}</td>
              <td className="py-0.5 text-right">{p.orders}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Conversion({ conversion }) {
  return (
    <section aria-label="Conversion" className="rounded-xl bg-cream p-4 text-sm">
      <h2 className="font-semibold">Traffic and sales</h2>
      {conversion.available ? (
        <>
          <p className="mt-2">
            <strong>{conversion.orders_per_1000_page_views}</strong> paid orders per 1,000 measured
            page views ({conversion.orders} orders, {conversion.page_views} page views over{" "}
            {conversion.measured_days} measured days).
          </p>
          <p className="mt-1 text-muted">{conversion.explanation}</p>
          {conversion.product_pages.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {conversion.product_pages.map((p) => (
                <li key={`${p.product_id}-${p.currency}`}>
                  {p.title}: {p.units} sold, {p.product_page_views} product page views
                  {p.units_per_100_views != null && ` (${p.units_per_100_views} per 100 views)`}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="mt-2">Sales per page view: unavailable. {conversion.reason}</p>
      )}
      <p className="mt-2">
        Purchase conversion rate: unavailable. {conversion.purchase_conversion.reason}
      </p>
    </section>
  );
}

const money = (key) => ({
  header: key[0].toUpperCase() + key.slice(1),
  numeric: true,
  render: (r) => r[key].formatted,
});

/** Sales, refunds and product performance from verified payment records (finance.view). */
export function CommerceAnalytics() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [preset, setPreset] = useState("30d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [filters, setFilters] = useState({ mode: "live", currency: "", granularity: "" });
  const params = {
    ...(preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset }),
    ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
  };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.commerceAnalytics(params),
    [JSON.stringify(params)],
  );
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }));
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Period"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="Start date"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="End date"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        <SelectField
          label="Payment mode"
          value={filters.mode}
          onChange={(e) => set({ mode: e.target.value })}
          options={[
            { value: "live", label: "Live payments" },
            { value: "test", label: "Test payments" },
          ]}
        />
        <TextField
          label="Currency"
          placeholder="All"
          maxLength={3}
          value={filters.currency}
          onChange={(e) => set({ currency: e.target.value.toUpperCase() })}
        />
        <SelectField
          label="Trend by"
          value={filters.granularity}
          onChange={(e) => set({ granularity: e.target.value })}
          options={[
            { value: "", label: "Automatic" },
            { value: "day", label: "Day" },
            { value: "week", label: "Week" },
            { value: "month", label: "Month" },
          ]}
        />
        {can("finance.export") && (
          <a
            href={api.commerceAnalyticsExportUrl(params)}
            className="rounded-full border border-charcoal/20 px-4 py-2 text-sm"
          >
            Download CSV
          </a>
        )}
      </div>
      {error ? (
        <ErrorState title="We couldn't load commerce analytics" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : !data.has_data ? (
        <EmptyState
          icon={ShoppingBag}
          title="No sales or orders in this period"
          description={
            data.filters.mode === "live"
              ? "Only verified live payments are counted. Switch to test payments to see test-mode activity."
              : "No test-mode orders in this period."
          }
        />
      ) : (
        <>
          {data.filters.mode === "test" && (
            <p role="note" className="rounded-xl border border-gold-300 bg-gold-100/40 p-3 text-sm">
              Test payments: Paystack test-mode transactions, not real money.
            </p>
          )}
          {data.currencies.map((c) => (
            <section
              key={c.currency}
              aria-label={`Sales in ${c.currency}`}
              className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
            >
              <Stat
                label={`Gross revenue (${c.currency})`}
                value={c.gross.formatted}
                hint={`${c.verified_sales} verified payments`}
              />
              <Stat
                label="Refunds"
                value={c.refunds.formatted}
                hint={`${c.refund_count} refunds`}
              />
              <Stat label="Net revenue" value={c.net.formatted} hint="Before provider fees" />
              <Stat label="Paid orders" value={c.orders} />
              <Stat label="Average order value" value={c.average_order_value?.formatted ?? "—"} />
            </section>
          ))}
          {data.series.map((s) => (
            <CurrencyTrend key={s.currency} series={s} />
          ))}
          <div className="grid gap-4 lg:grid-cols-2">
            <RankTable
              caption="Best-selling products"
              rows={data.products}
              columns={[
                { header: "Product", render: (r) => r.title },
                { header: "Units", numeric: true, render: (r) => r.units },
                money("revenue"),
                money("refunds"),
              ]}
            />
            <RankTable
              caption="Courses and premium resources"
              rows={data.groups}
              columns={[
                { header: "Type", render: (r) => GROUP_LABEL[r.group] ?? r.group },
                { header: "Units", numeric: true, render: (r) => r.units },
                money("revenue"),
              ]}
            />
            <RankTable
              caption="Sales by category"
              rows={data.categories}
              columns={[
                { header: "Category", render: (r) => r.category },
                { header: "Units", numeric: true, render: (r) => r.units },
                money("revenue"),
              ]}
            />
            <RankTable
              caption="Sales by product type"
              rows={data.product_types}
              columns={[
                { header: "Product type", render: (r) => r.type_label },
                { header: "Units", numeric: true, render: (r) => r.units },
                money("revenue"),
              ]}
            />
            <RankTable
              caption="Refunds by product"
              rows={data.refunds_by_product}
              empty="No refunds that can be attributed to a single product."
              columns={[
                { header: "Product", render: (r) => r.title },
                { header: "Count", numeric: true, render: (r) => r.refund_count },
                money("refunds"),
              ]}
            />
            <RankTable
              caption="Orders by status"
              rows={Object.entries(data.order_statuses).map(([status, count]) => ({
                status,
                count,
              }))}
              columns={[
                { header: "Status", render: (r) => STATUS_LABEL[r.status] ?? r.status },
                { header: "Orders", numeric: true, render: (r) => r.count },
              ]}
            />
            <RankTable
              caption="Test and live payments"
              rows={data.modes}
              columns={[
                { header: "Mode", render: (r) => (r.mode === "live" ? "Live" : "Test") },
                { header: "Payments", numeric: true, render: (r) => r.verified_sales },
                money("gross"),
              ]}
            />
            <RankTable
              caption="Products with no sales"
              rows={data.unsold_products}
              empty="Every published paid product sold at least once."
              columns={[
                { header: "Product", render: (r) => r.title },
                { header: "Type", render: (r) => r.type_label },
              ]}
            />
          </div>
          {data.unattributed_refunds.length > 0 && (
            <p className="text-sm text-muted">
              Refunds on multi-product orders aren&apos;t attributed to a product:{" "}
              {data.unattributed_refunds.map((m) => m.formatted).join(", ")}.
            </p>
          )}
          <Conversion conversion={data.conversion} />
        </>
      )}
      {data && (
        <ul className="list-disc pl-5 text-xs text-muted">
          {data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

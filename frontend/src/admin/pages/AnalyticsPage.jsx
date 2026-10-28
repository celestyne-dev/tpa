import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";

const PRESETS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "365d", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
];
const SOURCE_LABEL = {
  direct: "Direct",
  search: "Search engines",
  social: "Social networks",
  email: "Email",
  referral: "Other websites",
  campaign: "Campaigns (UTM)",
  internal: "Internal navigation",
};
const PAGE_TYPE_LABEL = {
  home: "Homepage",
  article: "Articles",
  article_index: "Article listing",
  topic: "Topic pages",
  shop: "Shop",
  product: "Product pages",
  course: "Courses",
  membership: "Membership",
  resource: "Resources",
  page: "Other pages",
};
const fmt = (n) => new Intl.NumberFormat("en").format(n);

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Bars drawn from the reported numbers only, with the figures as text for everyone. */
function TrendChart({ series }) {
  const max = Math.max(1, ...series.map((s) => s.views));
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Page views per period</caption>
      <thead className="text-muted">
        <tr>
          <th scope="col" className="w-28">
            Period
          </th>
          <th scope="col">Page views</th>
          <th scope="col" className="w-36 text-right">
            Daily visitors (sum)
          </th>
        </tr>
      </thead>
      <tbody>
        {series.map((s) => (
          <tr key={s.period}>
            <td className="py-0.5 pr-2 whitespace-nowrap">{s.period}</td>
            <td className="py-0.5">
              <div className="flex items-center gap-2">
                <div
                  aria-hidden
                  className="h-3 rounded bg-sage-600"
                  style={{ width: `${(s.views / max) * 100}%`, minWidth: s.views ? 2 : 0 }}
                />
                <span>{fmt(s.views)}</span>
              </div>
            </td>
            <td className="py-0.5 text-right">{fmt(s.visitors)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RankTable({ caption, rows, columns, empty = "Nothing recorded in this period." }) {
  return (
    <section aria-label={caption} className="rounded-xl border border-charcoal/10 bg-white p-4">
      <h2 className="text-base font-semibold">{caption}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{empty}</p>
      ) : (
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.header} scope="col" className={c.numeric ? "text-right" : undefined}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-charcoal/10">
                {columns.map((c) => (
                  <td key={c.header} className={c.numeric ? "py-1 text-right" : "py-1 pr-2"}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const views = { header: "Views", numeric: true, render: (r) => fmt(r.views) };

/** Website traffic and content performance from first-party, cookieless page views. */
export function AnalyticsPage() {
  const api = useAdminApi();
  const [preset, setPreset] = useState("30d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [granularity, setGranularity] = useState("");
  const params = {
    ...(preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset }),
    ...(granularity ? { granularity } : {}),
  };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.traffic(params),
    [JSON.stringify(params)],
  );
  return (
    <>
      <AdminPageHeader
        title="Analytics"
        description="Website traffic and content performance, measured first-party without cookies."
        breadcrumbs={[{ label: "Analytics" }]}
      />
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <SelectField
          label="Date range"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="From"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="To"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        <SelectField
          label="Group by"
          value={granularity}
          onChange={(e) => setGranularity(e.target.value)}
          options={[
            { value: "", label: "Automatic" },
            { value: "day", label: "Day" },
            { value: "week", label: "Week" },
            { value: "month", label: "Month" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load analytics" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : (
        <div className="space-y-6">
          {!data.tracking.enabled && (
            <p role="note" className="rounded-xl border border-gold-300 bg-gold-100/40 p-3 text-sm">
              Tracking is turned off (ANALYTICS_TRACKING=disabled). No new page views are recorded.
            </p>
          )}
          {!data.has_data ? (
            <EmptyState
              icon={BarChart3}
              title="No page views in this period"
              description="Figures appear once visitors browse the public site. Admin, account and checkout pages are never counted."
            />
          ) : (
            <>
              <section
                aria-label="Traffic overview"
                className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
              >
                <Stat label="Page views" value={fmt(data.totals.views)} />
                <Stat
                  label="Daily visitors (sum)"
                  value={fmt(data.totals.visitors_daily_sum)}
                  hint="Estimated per day; not unique people across days."
                />
                <Stat label="Average views per day" value={fmt(data.totals.average_daily_views)} />
                <Stat label="Days with traffic" value={fmt(data.totals.days_with_data)} />
              </section>
              <section
                aria-labelledby="trend-heading"
                className="rounded-xl border border-charcoal/10 bg-white p-4"
              >
                <h2 id="trend-heading" className="mb-2 text-base font-semibold">
                  Page views by {data.range.granularity} ({data.range.from} to {data.range.to})
                </h2>
                <TrendChart series={data.series} />
              </section>
              <div className="grid gap-4 lg:grid-cols-2">
                <RankTable
                  caption="Popular articles"
                  rows={data.articles}
                  columns={[
                    { header: "Article", render: (r) => r.title },
                    { header: "Topic", render: (r) => r.topic ?? "—" },
                    views,
                  ]}
                />
                <RankTable
                  caption="Top content categories"
                  rows={data.categories}
                  columns={[
                    { header: "Topic", render: (r) => r.topic },
                    {
                      header: "Articles / topic page",
                      numeric: true,
                      render: (r) => `${fmt(r.article_views)} / ${fmt(r.topic_page_views)}`,
                    },
                    views,
                  ]}
                />
                <RankTable
                  caption="Traffic sources"
                  rows={data.sources}
                  columns={[
                    { header: "Source", render: (r) => SOURCE_LABEL[r.source] ?? r.source },
                    views,
                  ]}
                />
                <RankTable
                  caption="Referring websites"
                  rows={data.referrers}
                  columns={[{ header: "Website", render: (r) => r.host }, views]}
                />
                <RankTable
                  caption="Campaign performance"
                  rows={data.campaigns}
                  empty="No visits with UTM campaign parameters in this period."
                  columns={[
                    { header: "Campaign", render: (r) => r.campaign },
                    {
                      header: "Source / medium",
                      render: (r) => `${r.utm_source} / ${r.utm_medium}`,
                    },
                    views,
                  ]}
                />
                <RankTable
                  caption="Top pages"
                  rows={data.pages}
                  columns={[
                    { header: "Page", render: (r) => r.path },
                    { header: "Type", render: (r) => PAGE_TYPE_LABEL[r.page_type] ?? r.page_type },
                    views,
                  ]}
                />
              </div>
            </>
          )}
          <section aria-label="How this is measured" className="rounded-xl bg-cream p-4 text-sm">
            <h2 className="font-semibold">How this is measured</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>{data.measurement.visitors}</li>
              <li>{data.measurement.sessions}</li>
              <li>{data.measurement.exclusions}</li>
              <li>
                Raw page views are kept for {data.tracking.raw_retention_days} days and daily totals
                for {data.tracking.aggregate_retention_days} days. No IP addresses, cookies or query
                strings (other than UTM campaign tags) are stored.
              </li>
              {data.tracking.pending_rollup_days > 0 && (
                <li>
                  {data.tracking.pending_rollup_days} completed day(s) are waiting for the hourly
                  rollup job (still included here from raw records).
                </li>
              )}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}

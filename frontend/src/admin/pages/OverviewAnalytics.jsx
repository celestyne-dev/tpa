import { useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";
import { ANALYTICS_PRESETS } from "./analyticsPresets";

const fmt = (n) => (n == null ? "—" : new Intl.NumberFormat("en").format(n));

/** "▲ 12% vs previous period" for period metrics; nothing for point-in-time figures. */
function Change({ metric }) {
  if (!metric || metric.kind !== "period") return null;
  if (metric.change == null) return <span className="text-xs text-muted">No comparison</span>;
  if (metric.change_pct == null)
    return (
      <span className="text-xs text-muted">
        {metric.change >= 0 ? "+" : ""}
        {fmt(metric.change)} vs previous period (was 0)
      </span>
    );
  const up = metric.change_pct >= 0;
  return (
    <span className={`text-xs ${up ? "text-sage-800" : "text-red-800"}`}>
      <span aria-hidden>{up ? "▲" : "▼"}</span> {Math.abs(metric.change_pct)}%{" "}
      <span className="sr-only">{up ? "increase" : "decrease"}</span> vs previous period
    </span>
  );
}

function Kpi({ label, metric, display, note }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{display ?? fmt(metric?.value)}</p>
      <div className="mt-1 flex flex-col gap-0.5">
        <Change metric={metric} />
        {metric?.kind === "point_in_time" && <span className="text-xs text-muted">Right now</span>}
        {note && <span className="text-xs text-muted">{note}</span>}
      </div>
    </div>
  );
}

function MoneyKpis({ label, rows }) {
  if (!rows.length) return <Kpi label={label} display="None in this period" />;
  return rows.map((r) => (
    <Kpi
      key={`${label}-${r.mode}-${r.currency}`}
      label={`${label} (${r.currency}${r.mode === "test" ? ", test mode" : ""})`}
      metric={r}
      display={r.formatted ?? `${r.currency} 0.00`}
    />
  ));
}

function Section({ title, children }) {
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}

/** Permission-aware overview: only the modules the user may see are returned. */
export function OverviewAnalytics() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [preset, setPreset] = useState("30d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [mode, setMode] = useState("live");
  const range =
    preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset };
  const params = { ...range, ...(mode !== "live" ? { mode } : {}) };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.analyticsOverview(params),
    [JSON.stringify(params)],
  );
  const s = data?.sections ?? {};
  const exports = [
    { report: "overview", label: "Overview", allowed: true },
    { report: "website", label: "Website", allowed: can("analytics.view") },
    { report: "learning", label: "Learning", allowed: can("courses.view_reports") },
    {
      report: "membership",
      label: "Membership",
      allowed: can("memberships.view_reports") && can("finance.export"),
    },
    { report: "audience", label: "Audience", allowed: can("newsletters.reports") },
  ].filter((e) => e.allowed);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Overview period"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={ANALYTICS_PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="Overview from"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="Overview to"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        {s.commerce && (
          <SelectField
            label="Sales mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            options={[
              { value: "live", label: "Live payments" },
              { value: "test", label: "Test payments" },
            ]}
          />
        )}
      </div>
      {error ? (
        <ErrorState title="We couldn't load the overview" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : (
        <>
          <p className="text-sm text-muted">
            {data.range.from} to {data.range.to}, compared with {data.previous_range.from} to{" "}
            {data.previous_range.to}.
          </p>
          {s.website && (
            <Section title="Website">
              <Kpi label="Page views" metric={s.website.page_views} />
              <Kpi
                label="Daily visitors (sum)"
                metric={s.website.visitors_daily_sum}
                note="Estimate; not unique people across days"
              />
              <div className="rounded-xl border border-charcoal/10 bg-white p-4 sm:col-span-2">
                <p className="text-sm text-muted">Popular articles</p>
                {s.website.top_articles.length ? (
                  <ol className="mt-1 list-decimal pl-5 text-sm">
                    {s.website.top_articles.map((a) => (
                      <li key={a.title}>
                        {a.title} · {fmt(a.views)} views
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-1 text-sm">No article views in this period.</p>
                )}
              </div>
            </Section>
          )}
          {s.commerce && (
            <Section
              title={`Commerce (${s.commerce.mode === "test" ? "test payments" : "live payments"})`}
            >
              <MoneyKpis label="Verified revenue" rows={s.commerce.gross} />
              <MoneyKpis label="Refunds" rows={s.commerce.refunds} />
              <MoneyKpis label="Net revenue" rows={s.commerce.net} />
              {s.commerce.paid_orders.map((o) => (
                <Kpi
                  key={`orders-${o.currency}`}
                  label={`Paid orders (${o.currency})`}
                  metric={o}
                />
              ))}
              {s.commerce.other_mode_payments > 0 && (
                <Kpi
                  label={s.commerce.mode === "live" ? "Test-mode payments" : "Live payments"}
                  display={fmt(s.commerce.other_mode_payments)}
                  note="Not included above"
                />
              )}
            </Section>
          )}
          {s.learning && (
            <Section title="Learning">
              <Kpi label="New enrollments" metric={s.learning.new_enrollments} />
              <Kpi label="Course completions" metric={s.learning.completions} />
              <Kpi label="Current enrollments" metric={s.learning.current_enrollments} />
              <Kpi
                label="Active learners"
                metric={s.learning.active_learners}
                note="At least this many"
              />
            </Section>
          )}
          {s.membership && (
            <Section title="Membership">
              <Kpi label="Paid members" metric={s.membership.paid_members} />
              <Kpi label="Complimentary members" metric={s.membership.complimentary} />
              <Kpi label="New subscriptions" metric={s.membership.new_subscriptions} />
              <MoneyKpis label="Membership revenue" rows={s.membership.revenue} />
              {s.membership.mrr_estimate.map((m) => (
                <Kpi
                  key={`mrr-${m.mode}-${m.value.currency}`}
                  label={`MRR estimate (${m.value.currency}${m.mode === "test" ? ", test mode" : ""})`}
                  display={m.value.formatted}
                  note="Estimate, not revenue"
                />
              ))}
            </Section>
          )}
          {s.audience && (
            <Section title="Audience">
              <Kpi label="Subscribed contacts" metric={s.audience.subscribed} />
              <Kpi label="Signups" metric={s.audience.signups} />
              <Kpi label="New subscriptions" metric={s.audience.new_subscriptions} />
              <Kpi label="Unsubscriptions" metric={s.audience.unsubscriptions} />
            </Section>
          )}
          {data.health && (
            <section
              aria-label="Analytics health"
              className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm"
            >
              <h2 className="text-base font-semibold">Analytics health</h2>
              <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                <dt>Traffic tracking</dt>
                <dd>{data.health.tracking_enabled ? "On" : "Off"}</dd>
                <dt>Latest daily rollup</dt>
                <dd>
                  {data.health.latest_rollup_day
                    ? `${data.health.latest_rollup_day} (built ${data.health.latest_rollup_at})`
                    : "None yet"}
                </dd>
                <dt>Days waiting for rollup</dt>
                <dd>{data.health.pending_rollup_days}</dd>
                <dt>Retention</dt>
                <dd>
                  Raw {data.health.raw_retention_days} days · daily totals{" "}
                  {data.health.aggregate_retention_days} days
                </dd>
                <dt>Page views today</dt>
                <dd>{fmt(data.health.page_views_today)}</dd>
              </dl>
              <p className="mt-2 text-xs text-muted">
                Maintenance job runs aren&apos;t recorded; the newest rollup is the best evidence
                that it ran.
              </p>
              <ul className="mt-2 list-disc pl-5">
                {data.health.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </section>
          )}
          <section aria-label="Exports" className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold">Download CSV:</span>
            {exports.map((e) => (
              <a
                key={e.report}
                href={api.analyticsExportUrl(e.report, range)}
                className="rounded-full border border-charcoal/20 px-3 py-1"
              >
                {e.label}
              </a>
            ))}
          </section>
          <ul className="list-disc pl-5 text-xs text-muted">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

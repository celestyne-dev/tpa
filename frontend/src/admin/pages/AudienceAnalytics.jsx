import { Mail } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { RankTable, Stat } from "./analyticsParts";
import { ANALYTICS_PRESETS } from "./analyticsPresets";

const PRESETS = ANALYTICS_PRESETS;
const SOURCE_LABEL = {
  homepage: "Homepage",
  footer: "Footer",
  newsletter_page: "Newsletter page",
  article: "Articles",
  page_section: "Page sections",
  lead_magnet: "Lead magnets",
  resource_page: "Resource pages",
  account: "Customer accounts",
  import: "Imported",
  admin: "Added by staff",
  other: "Other",
};

/** Newsletter audience: growth, sources, campaigns and lead magnets. */
export function AudienceAnalytics() {
  const api = useAdminApi();
  const [preset, setPreset] = useState("30d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [campaign, setCampaign] = useState("");
  const params = {
    ...(preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset }),
    ...(campaign ? { campaign } : {}),
  };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.audienceAnalytics(params),
    [JSON.stringify(params)],
  );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Audience period"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="Audience from"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="Audience to"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        <SelectField
          label="Campaign"
          value={campaign}
          onChange={(e) => setCampaign(e.target.value)}
          options={[
            { value: "", label: "Campaigns sent in this period" },
            ...(data?.campaign_options ?? []).map((c) => ({ value: c.id, label: c.name })),
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load audience analytics" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : !data.has_data ? (
        <EmptyState
          icon={Mail}
          title="No newsletter contacts yet"
          description="Figures appear once people sign up for the newsletter."
        />
      ) : (
        <>
          <section
            aria-label="Audience overview"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Stat
              label="Subscribed contacts"
              value={data.current.subscribed}
              hint={`${data.current.pending} awaiting confirmation`}
            />
            <Stat
              label="New subscriptions"
              value={data.period.new_subscriptions}
              hint={`${data.period.signups} signups in this period`}
            />
            <Stat label="Unsubscriptions" value={data.period.unsubscriptions} />
            <Stat label="Net growth" value={data.period.net_growth} />
          </section>
          <RankTable
            caption="Subscriber growth"
            rows={data.trend}
            columns={[
              { header: "Period", render: (r) => r.period },
              { header: "Signups", numeric: true, render: (r) => r.signups },
              { header: "New", numeric: true, render: (r) => r.new_subscriptions },
              { header: "Unsubscribed", numeric: true, render: (r) => r.unsubscriptions },
              { header: "Net", numeric: true, render: (r) => r.net_growth },
            ]}
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <RankTable
              caption="Subscription sources"
              rows={data.sources}
              columns={[
                { header: "Source", render: (r) => SOURCE_LABEL[r.source] ?? r.source },
                { header: "New (period)", numeric: true, render: (r) => r.new_subscriptions },
                { header: "Subscribed now", numeric: true, render: (r) => r.subscribed_now },
              ]}
            />
            <RankTable
              caption="Lead magnets"
              rows={data.lead_magnets}
              empty="No lead magnet claims in this period."
              columns={[
                { header: "Lead magnet", render: (r) => r.title },
                { header: "Claims", numeric: true, render: (r) => r.claims },
                {
                  header: "Confirmed subscribers",
                  numeric: true,
                  render: (r) => r.confirmed_subscribers,
                },
              ]}
            />
          </div>
          <RankTable
            caption="Campaigns"
            rows={data.campaigns}
            empty="No campaigns finished sending in this period."
            columns={[
              {
                header: "Campaign",
                render: (r) => `${r.name}${r.send_mode === "test" ? " (test send)" : ""}`,
              },
              { header: "Eligible", numeric: true, render: (r) => r.eligible ?? "—" },
              { header: "Accepted", numeric: true, render: (r) => r.accepted },
              {
                header: "Delivered (confirmed)",
                numeric: true,
                render: (r) => r.delivered_confirmed,
              },
              { header: "Bounced", numeric: true, render: (r) => r.bounced },
              { header: "Complaints", numeric: true, render: (r) => r.complained },
            ]}
          />
          <p role="note" className="rounded-xl border border-charcoal/10 bg-white p-3 text-sm">
            Opens and clicks: not measured. {data.engagement.explanation}
          </p>
        </>
      )}
      {data && (
        <section aria-label="Audience definitions" className="rounded-xl bg-cream p-4 text-sm">
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

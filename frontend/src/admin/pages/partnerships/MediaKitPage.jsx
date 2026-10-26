import { BarChart3, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { useNotify } from "../../components/notifyContext";
import { RecordDialog } from "../../components/partnerships/RecordDialog";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { METRIC_TYPES } from "./options";

const TEXT_FIELDS = [
  ["about", "About the brand"],
  ["editorial_focus", "Editorial focus"],
  [
    "audience_summary",
    "Audience summary",
    "Describe readers in words; figures go in measurements below.",
  ],
  ["audience_geography", "Audience geography"],
  ["placements_intro", "Placements introduction"],
  ["collaboration_guidelines", "Collaboration guidelines"],
  ["sponsorship_policies", "Sponsorship and disclosure policy"],
];

function MediaKitForm({ initial, published, hasChanges, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [doc, setDoc] = useState(initial);
  const [error, setError] = useState(null);
  const set = (k, v) => setDoc((d) => ({ ...d, [k]: v }));
  const save = async () => {
    setError(null);
    try {
      const body = {
        ...doc,
        content_categories: String(doc.content_categories_text ?? doc.content_categories.join("\n"))
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        campaign_formats: String(
          doc.formats_text ??
            doc.campaign_formats.map((f) => `${f.name} | ${f.description}`).join("\n"),
        )
          .split("\n")
          .filter((x) => x.trim())
          .map((line) => {
            const [name, ...rest] = line.split("|");
            return { name: name.trim(), description: rest.join("|").trim() };
          }),
        brand_asset_ids: String(doc.assets_text ?? doc.brand_asset_ids.join(", "))
          .split(",")
          .map((x) => Number(x.trim()))
          .filter(Boolean),
      };
      delete body.content_categories_text;
      delete body.formats_text;
      delete body.assets_text;
      await api.mediaKit.save(body);
      notify("Draft saved.");
      onSaved();
    } catch (err) {
      setError(err);
    }
  };
  const publish = async () => {
    try {
      await api.mediaKit.publish();
      notify("Media kit published. The site will rebuild shortly.");
      onSaved();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const area = (key, text, hint) => (
    <label key={key} className="block text-sm font-medium">
      {text}
      {hint && <span className="block text-xs font-normal text-muted">{hint}</span>}
      <textarea
        rows={4}
        className="mt-1 w-full rounded-lg border px-3 py-2 font-normal"
        value={doc[key] ?? ""}
        onChange={(e) => set(key, e.target.value)}
      />
      {error?.details?.[key] && <span className="text-xs text-red-800">{error.details[key]}</span>}
    </label>
  );
  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted">
        Status: {published ? "published" : "not published yet"}
        {hasChanges && published ? " · draft has unpublished changes" : ""}.
      </p>
      {TEXT_FIELDS.map(([k, t, h]) => area(k, t, h))}
      {area("content_categories_text", "Content categories (one per line)")}
      {area("formats_text", "Campaign formats (one per line: Name | description)")}
      <label className="block text-sm font-medium">
        Brand asset media IDs (comma separated)
        <input
          className="mt-1 w-full rounded-lg border px-3 py-2 font-normal"
          value={doc.assets_text ?? doc.brand_asset_ids.join(", ")}
          onChange={(e) => set("assets_text", e.target.value)}
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium">
          Contact button label
          <input
            className="mt-1 w-full rounded-lg border px-3 py-2 font-normal"
            value={doc.contact_cta.label}
            onChange={(e) => set("contact_cta", { ...doc.contact_cta, label: e.target.value })}
          />
        </label>
        <label className="text-sm font-medium">
          Contact button link
          <input
            className="mt-1 w-full rounded-lg border px-3 py-2 font-normal"
            value={doc.contact_cta.href}
            onChange={(e) => set("contact_cta", { ...doc.contact_cta, href: e.target.value })}
          />
          {error?.details?.contact_cta && (
            <span className="text-xs text-red-800">{error.details.contact_cta}</span>
          )}
        </label>
      </div>
      {[
        ["show_metrics", "Show verified audience measurements"],
        ["show_placements", "List active placements"],
        ["show_rate_card", "Show public (indicative) rates"],
      ].map(([k, t]) => (
        <label key={k} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(doc[k])}
            onChange={(e) => set(k, e.target.checked)}
          />{" "}
          {t}
        </label>
      ))}
      {error && !Object.keys(error.details ?? {}).length && (
        <p role="alert" className="text-sm text-red-800">
          {error.message}
        </p>
      )}
      <div className="flex gap-2">
        <Button onClick={save}>Save draft</Button>
        <Button variant="outline" onClick={publish}>
          Publish
        </Button>
      </div>
    </div>
  );
}

function Metrics() {
  const api = useAdminApi();
  const { data, error, loading, reload } = useAdminQuery(() => api.audienceMetrics.list(), []);
  const [editing, setEditing] = useState(null);
  const notify = useNotify();
  const fields = [
    {
      name: "metric_type",
      label: "Measurement",
      type: "select",
      required: true,
      options: METRIC_TYPES,
    },
    { name: "value", label: "Value", type: "number", required: true },
    {
      name: "platform",
      label: "Platform",
      required: true,
      hint: "e.g. LinkedIn, Website, Newsletter",
    },
    { name: "period_label", label: "Period", hint: "e.g. September 2026, last 30 days" },
    {
      name: "source",
      label: "Source",
      required: true,
      hint: "e.g. LinkedIn page analytics export",
    },
    { name: "measured_on", label: "Date measured", type: "date", required: true },
    { name: "verified", label: "I have checked this figure against the source", type: "checkbox" },
    { name: "is_public", label: "Show publicly (verified figures only)", type: "checkbox" },
    { name: "notes", label: "Notes", type: "textarea" },
  ];
  if (error) return <ErrorState title="We couldn't load measurements" onRetry={reload} />;
  return (
    <>
      <p className="mb-3 text-sm text-muted">
        Enter only figures you measured yourself, with their source and date. They are always shown
        as “measured on …”, never as live numbers. Social followers are not website traffic.
      </p>
      <Button className="mb-4" onClick={() => setEditing({ metric_type: "social_followers" })}>
        <Plus aria-hidden className="size-4" /> Add measurement
      </Button>
      <DataTable
        caption="Audience measurements"
        rows={data}
        loading={loading}
        empty={{ icon: BarChart3, title: "No measurements entered" }}
        columns={[
          {
            key: "label",
            header: "Measurement",
            render: (m) => (
              <button
                type="button"
                className="font-medium hover:underline"
                onClick={() => setEditing(m)}
              >
                {m.label} · {m.platform}
              </button>
            ),
          },
          { key: "value", header: "Value", render: (m) => m.value.toLocaleString("en-US") },
          { key: "measured", header: "Measured", render: (m) => m.measured_on },
          { key: "source", header: "Source", render: (m) => m.source },
          {
            key: "public",
            header: "Public",
            render: (m) => (m.is_public ? "Yes" : m.verified ? "No" : "Unverified"),
          },
          {
            key: "del",
            header: "",
            render: (m) => (
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  if (!window.confirm("Delete this measurement?")) return;
                  await api.audienceMetrics.remove(m.id);
                  notify("Measurement deleted.");
                  reload();
                }}
              >
                Delete
              </Button>
            ),
          },
        ]}
      />
      {editing && (
        <RecordDialog
          title="Audience measurement"
          fields={fields}
          record={editing}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            if (editing.id) await api.audienceMetrics.update(editing.id, body);
            else await api.audienceMetrics.create(body);
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

export function MediaKitPage() {
  const api = useAdminApi();
  const { data, error, loading, reload } = useAdminQuery(() => api.mediaKit.get(), []);
  return (
    <>
      <AdminPageHeader
        title="Media kit"
        description="The public media kit at /advertise. Save a draft, then publish; a CMS page at /advertise replaces it if you prefer the page builder."
        breadcrumbs={[{ label: "Media kit" }]}
      />
      {error ? (
        <ErrorState title="We couldn't load the media kit" onRetry={reload} />
      ) : loading && !data ? (
        <p role="status">Loading…</p>
      ) : (
        <MediaKitForm
          key={JSON.stringify(data.draft)}
          initial={data.draft}
          published={data.published}
          hasChanges={data.has_changes}
          onSaved={reload}
        />
      )}
      <h2 className="mt-10 mb-3 text-xl font-medium">Audience measurements</h2>
      <Metrics />
    </>
  );
}

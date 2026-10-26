import { Link2, Plus, Upload } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { useNotify } from "../../components/notifyContext";
import { CURRENCIES, label, money } from "../../components/partnerships/formValues";
import { RecordDialog, Tabs } from "../../components/partnerships/RecordDialog";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { ACCOUNT_STATUSES, COMMISSION_STATUSES, toOptions } from "./options";

function Programs() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.affiliatePrograms.list(), []);
  const [editing, setEditing] = useState(null);
  const manage = can("affiliates.manage");
  const fields = [
    { name: "name", label: "Program", required: true },
    { name: "merchant", label: "Merchant", required: true },
    { name: "network", label: "Network" },
    { name: "category", label: "Category" },
    { name: "website", label: "Website (https://)" },
    { name: "terms_url", label: "Program terms (https://)" },
    { name: "commission_model", label: "Commission model", hint: "e.g. % of sale, fixed per sale" },
    { name: "commission_rate", label: "Rate (only once confirmed)" },
    { name: "currency", label: "Currency", type: "select", required: true, options: CURRENCIES },
    { name: "payout_threshold_minor", label: "Payout threshold", type: "money" },
    {
      name: "account_status",
      label: "Account status",
      type: "select",
      required: true,
      options: ACCOUNT_STATUSES,
      hint: "Record what is true; this system never applies to programs for you.",
    },
    { name: "last_verified_on", label: "Details last verified", type: "date" },
    { name: "account_identifier", label: "Account / publisher ID (private)" },
    { name: "notes", label: "Private notes", type: "textarea" },
  ];
  if (error) return <ErrorState title="We couldn't load programs" onRetry={reload} />;
  return (
    <>
      {manage && (
        <Button
          className="mb-4"
          onClick={() => setEditing({ currency: "USD", account_status: "not_applied" })}
        >
          <Plus aria-hidden className="size-4" /> New program
        </Button>
      )}
      <DataTable
        caption="Affiliate programs"
        rows={data}
        loading={loading}
        empty={{ icon: Link2, title: "No programs recorded" }}
        columns={[
          {
            key: "name",
            header: "Program",
            render: (p) => (
              <div>
                <button
                  type="button"
                  className="font-medium hover:underline"
                  disabled={!manage}
                  onClick={() => setEditing(p)}
                >
                  {p.name}
                </button>
                <p className="text-xs text-muted">
                  {[p.merchant, p.network].filter(Boolean).join(" · ")}
                </p>
              </div>
            ),
          },
          {
            key: "status",
            header: "Account",
            render: (p) => <StatusBadge status={label(p.account_status)} />,
          },
          {
            key: "rate",
            header: "Commission",
            render: (p) => p.commission_rate || "Not confirmed",
          },
          { key: "verified", header: "Verified", render: (p) => p.last_verified_on ?? "—" },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.id ? `Edit ${editing.name}` : "New program"}
          fields={fields}
          record={editing}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            if (editing.id) await api.affiliatePrograms.update(editing.id, body);
            else await api.affiliatePrograms.create(body);
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function Commissions() {
  const api = useAdminApi();
  const notify = useNotify();
  const { canAny } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(
    () => api.affiliateCommissions.list({}),
    [],
  );
  const programs = useAdminQuery(() => api.affiliatePrograms.list(), []);
  const [mode, setMode] = useState(null);
  const [programId, setProgramId] = useState("");
  const manage = canAny("affiliates.manage", "partnership_finance.manage");
  const importFile = async (file) => {
    try {
      const res = await api.affiliateCommissions.importCsv(file, programId);
      const r = res.data;
      notify(
        `Imported ${r.imported}; ${r.duplicates} duplicate(s) skipped; ${r.errors.length} row(s) with problems.`,
      );
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  if (error) return <ErrorState title="We couldn't load commissions" onRetry={reload} />;
  return (
    <>
      <p className="mb-3 text-sm text-muted">
        Commissions come only from network reports you import or manual entries with evidence.
        Clicks are never counted as earnings.
      </p>
      {manage && (
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Program
            <select
              className="ml-2 rounded-full border px-3 py-1.5"
              value={programId}
              onChange={(e) => setProgramId(e.target.value)}
            >
              <option value="">Choose…</option>
              {(programs.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label
            className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2 text-sm ${programId ? "" : "pointer-events-none opacity-50"}`}
          >
            <Upload aria-hidden className="size-4" /> Import CSV
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              disabled={!programId}
              onChange={(e) => e.target.files[0] && importFile(e.target.files[0])}
            />
          </label>
          <Button variant="outline" onClick={() => setMode("manual")}>
            Add manual entry
          </Button>
          <span className="text-xs text-muted">
            CSV columns: reference, date, amount, currency, status (optional), link (optional)
          </span>
        </div>
      )}
      <DataTable
        caption="Commissions"
        rows={data}
        loading={loading}
        empty={{ icon: Link2, title: "No commissions recorded" }}
        columns={[
          { key: "date", header: "Date", render: (c) => c.occurred_on },
          { key: "ref", header: "Reference", render: (c) => c.external_reference },
          { key: "amount", header: "Amount", render: (c) => money(c.amount_minor, c.currency) },
          {
            key: "source",
            header: "Source",
            render: (c) => (c.source === "manual" ? "Manual entry" : "Imported"),
          },
          {
            key: "status",
            header: "Status",
            render: (c) =>
              manage ? (
                <select
                  aria-label="Commission status"
                  className="rounded-full border px-2 py-1 text-sm"
                  value={c.status}
                  onChange={async (e) => {
                    await api.affiliateCommissions.setStatus(c.id, e.target.value);
                    reload();
                  }}
                >
                  {COMMISSION_STATUSES.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <StatusBadge status={c.status} />
              ),
          },
        ]}
      />
      {mode === "manual" && (
        <RecordDialog
          title="Manual commission entry"
          fields={[
            {
              name: "program_id",
              label: "Program",
              type: "id",
              required: true,
              options: toOptions(programs.data),
            },
            { name: "external_reference", label: "Reference", required: true },
            { name: "occurred_on", label: "Date", type: "date", required: true },
            {
              name: "currency",
              label: "Currency",
              type: "select",
              required: true,
              default: "USD",
              options: CURRENCIES,
            },
            { name: "amount_minor", label: "Amount", type: "money", required: true },
            {
              name: "status",
              label: "Status",
              type: "select",
              required: true,
              default: "reported",
              options: COMMISSION_STATUSES,
            },
            {
              name: "notes",
              label: "Evidence (required)",
              type: "textarea",
              required: true,
              hint: "e.g. statement name and date from the network dashboard.",
            },
          ]}
          onClose={() => setMode(null)}
          onSave={async (body) => {
            await api.affiliateCommissions.create(body);
            setMode(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function Disclosure() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const { data, reload } = useAdminQuery(() => api.affiliateDisclosure.get(), []);
  const [text, setText] = useState(null);
  const value = text ?? data?.text ?? "";
  return (
    <div className="max-w-2xl">
      <p className="mb-3 text-sm text-muted">
        Shown beside every affiliate recommendation section (never only in the footer). It must
        mention affiliate links or commission.
      </p>
      <textarea
        className="w-full rounded-lg border px-3 py-2"
        rows={4}
        value={value}
        disabled={!can("affiliates.manage")}
        aria-label="Affiliate disclosure"
        onChange={(e) => setText(e.target.value)}
      />
      {can("affiliates.manage") && (
        <Button
          className="mt-3"
          onClick={async () => {
            try {
              await api.affiliateDisclosure.update(value);
              notify("Disclosure saved.");
              setText(null);
              reload();
            } catch (err) {
              notify(err.details?.text?.[0] ?? err.message, "error");
            }
          }}
        >
          Save disclosure
        </Button>
      )}
    </div>
  );
}

export function AffiliatesPage() {
  const { canAny } = usePermissions();
  const tabs = [
    ["programs", "Programs"],
    canAny("affiliates.manage", "partnership_finance.view") && ["commissions", "Commissions"],
    ["disclosure", "Disclosure"],
  ].filter(Boolean);
  const [tab, setTab] = useState("programs");
  const View = { programs: Programs, commissions: Commissions, disclosure: Disclosure }[tab];
  return (
    <>
      <AdminPageHeader
        title="Affiliates"
        description="Affiliate programs you belong to, reported commissions and the reader disclosure."
        breadcrumbs={[{ label: "Affiliates" }]}
      />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      <View />
    </>
  );
}

export function AffiliateLinksPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.affiliateLinks.list({}), []);
  const programs = useAdminQuery(() => api.affiliatePrograms.list(), []);
  const clicks = useAdminQuery(() => api.affiliateClicks({}), []);
  const [editing, setEditing] = useState(null);
  const manage = can("affiliates.manage_links");
  const fields = [
    { name: "name", label: "Name", required: true },
    { name: "slug", label: "Short name", hint: "Public link: /api/v1/go/<short name>" },
    { name: "target_url", label: "Destination (https://)", required: true, wide: true },
    { name: "program_id", label: "Program", type: "id", options: toOptions(programs.data) },
    { name: "merchant", label: "Merchant" },
    { name: "campaign", label: "Campaign" },
    { name: "article_id", label: "Related article ID", type: "number" },
    { name: "product_id", label: "Related product ID", type: "number" },
    { name: "utm_source", label: "utm_source" },
    { name: "utm_medium", label: "utm_medium" },
    { name: "utm_campaign", label: "utm_campaign" },
    { name: "expires_at", label: "Expires", type: "datetime" },
    { name: "is_active", label: "Active", type: "checkbox", default: true },
  ];
  return (
    <>
      <AdminPageHeader
        title="Affiliate links"
        description="Links go through a redirect that only ever sends readers to the saved, validated destination. Clicks are counted per day and page, without tracking individuals."
        breadcrumbs={[{ label: "Affiliate links" }]}
        actions={
          manage && (
            <Button onClick={() => setEditing({})}>
              <Plus aria-hidden className="size-4" /> New link
            </Button>
          )
        }
      />
      {error ? (
        <ErrorState title="We couldn't load links" onRetry={reload} />
      ) : (
        <DataTable
          caption="Affiliate links"
          rows={data}
          loading={loading}
          empty={{ icon: Link2, title: "No affiliate links yet" }}
          columns={[
            {
              key: "name",
              header: "Link",
              render: (l) => (
                <div>
                  <button
                    type="button"
                    className="font-medium hover:underline"
                    disabled={!manage}
                    onClick={() => setEditing(l)}
                  >
                    {l.name}
                  </button>
                  <p className="text-xs text-muted">{l.public_url}</p>
                </div>
              ),
            },
            {
              key: "dest",
              header: "Destination",
              render: (l) => <span className="text-xs break-all">{l.target_url}</span>,
            },
            { key: "clicks", header: "Clicks", render: (l) => l.total_clicks },
            {
              key: "status",
              header: "Status",
              render: (l) => <StatusBadge status={l.is_active ? "active" : "inactive"} />,
            },
          ]}
        />
      )}
      <h2 className="mt-8 mb-2 text-lg font-medium">Clicks by day and page</h2>
      <p className="mb-3 text-sm text-muted">
        Clicks are not purchases and are never used to estimate earnings.
      </p>
      <DataTable
        caption="Clicks"
        rows={clicks.data}
        loading={clicks.loading}
        rowKey={(r) => `${r.link_id}-${r.day}-${r.source_path}`}
        empty={{ icon: Link2, title: "No clicks recorded" }}
        columns={[
          { key: "day", header: "Day", render: (r) => r.day },
          { key: "link", header: "Link", render: (r) => r.link },
          { key: "program", header: "Program", render: (r) => r.program || "—" },
          { key: "campaign", header: "Campaign", render: (r) => r.campaign || "—" },
          { key: "page", header: "Source page", render: (r) => r.source_path || "(unknown)" },
          { key: "clicks", header: "Clicks", render: (r) => r.clicks },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.id ? `Edit ${editing.name}` : "New affiliate link"}
          fields={fields}
          record={editing}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            if (editing.id) await api.affiliateLinks.update(editing.id, body);
            else await api.affiliateLinks.create(body);
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

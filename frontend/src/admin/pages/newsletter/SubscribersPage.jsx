import { Download, Inbox, Plus, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import {
  PREFERENCES,
  SEGMENT_FIELDS,
  SIGNUP_SOURCES,
  SUBSCRIBER_STATUS,
} from "../../components/newsletterLabels";
import { useNotify } from "../../components/notifyContext";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

const TABS = [
  ["list", "Subscribers"],
  ["segments", "Segments"],
  ["tags", "Tags"],
  ["suppressions", "Suppression list"],
  ["import", "Import"],
];

const options = (labels, any = "Any") => [
  { value: "", label: any },
  ...Object.entries(labels).map(([value, label]) => ({ value, label })),
];

function SubscriberList() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({
    q: "",
    status: "",
    source: "",
    tag: "",
    segment_id: "",
  });
  const [page, setPage] = useState(1);
  const params = Object.fromEntries(Object.entries({ ...filters, page }).filter(([, v]) => v));
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.subscribers.list(params),
    [JSON.stringify(params)],
  );
  const tags = useAdminQuery(() => api.subscriberTags.list(), []);
  const segments = useAdminQuery(() => api.segments.list(), []);
  const set = (patch) => {
    setPage(1);
    setFilters({ ...filters, ...patch });
  };
  const total = meta?.total ?? 0;
  const counts = meta?.status_counts ?? {};
  return (
    <>
      <dl className="mb-4 flex flex-wrap gap-3 text-sm">
        {Object.entries(SUBSCRIBER_STATUS).map(([key, label]) => (
          <div key={key} className="rounded-xl bg-white px-3 py-2 shadow-sm">
            <dt className="text-muted">{label}</dt>
            <dd className="font-semibold">{counts[key] ?? 0}</dd>
          </div>
        ))}
      </dl>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <TextField
          label="Search email or name"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
          options={options(SUBSCRIBER_STATUS)}
        />
        <SelectField
          label="Signup source"
          value={filters.source}
          onChange={(e) => set({ source: e.target.value })}
          options={options(SIGNUP_SOURCES)}
        />
        <SelectField
          label="Tag"
          value={filters.tag}
          onChange={(e) => set({ tag: e.target.value })}
          options={[
            { value: "", label: "Any" },
            ...(tags.data ?? []).map((t) => ({ value: t.slug, label: t.name })),
          ]}
        />
        <SelectField
          label="Segment"
          value={filters.segment_id}
          onChange={(e) => set({ segment_id: e.target.value })}
          options={[
            { value: "", label: "Any" },
            ...(segments.data ?? []).map((s) => ({ value: String(s.id), label: s.name })),
          ]}
        />
      </div>
      {can("subscribers.export") && (
        <p className="mb-4">
          <a
            href={api.subscribers.exportUrl(params)}
            className="inline-flex items-center gap-2 rounded-full border border-charcoal/20 px-4 py-2 text-sm"
          >
            <Download aria-hidden className="size-4" /> Export matching subscribers (CSV)
          </a>
          <span className="ml-3 text-xs text-muted">
            Exports contain personal data and are audited.
          </span>
        </p>
      )}
      {error ? (
        <ErrorState title="We couldn't load subscribers" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Subscribers"
            rows={data}
            loading={loading}
            empty={{ icon: Inbox, title: "No subscribers found" }}
            columns={[
              {
                key: "email",
                header: "Subscriber",
                render: (s) => (
                  <div>
                    <Link to={`/admin/subscribers/${s.id}`} className="font-medium hover:underline">
                      {s.email}
                    </Link>
                    {s.first_name && <p className="text-xs text-muted">{s.first_name}</p>}
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (s) => <StatusBadge status={SUBSCRIBER_STATUS[s.status] ?? s.status} />,
              },
              {
                key: "source",
                header: "Source",
                render: (s) => SIGNUP_SOURCES[s.source] ?? s.source,
              },
              {
                key: "tags",
                header: "Tags",
                render: (s) => s.tags.map((t) => t.name).join(", ") || "—",
              },
              {
                key: "consent",
                header: "Consent",
                render: (s) => (s.consent_at ? formatDateTime(s.consent_at) : "—"),
              },
            ]}
          />
          <Pagination
            pagination={{
              page,
              page_size: 25,
              total,
              total_pages: Math.max(1, Math.ceil(total / 25)),
              has_next: page * 25 < total,
              has_prev: page > 1,
            }}
            onPage={setPage}
          />
        </>
      )}
    </>
  );
}

function RuleRow({ rule, onChange, onRemove, tags }) {
  const field = SEGMENT_FIELDS[rule.field];
  const valueInput = () => {
    if (rule.field === "source")
      return (
        <SelectField
          label="Value"
          value={rule.value?.[0] ?? ""}
          onChange={(e) => onChange({ ...rule, value: [e.target.value] })}
          options={options(SIGNUP_SOURCES, "Choose…")}
        />
      );
    if (rule.field === "preference")
      return (
        <SelectField
          label="Value"
          value={rule.value ?? ""}
          onChange={(e) => onChange({ ...rule, value: e.target.value })}
          options={options(PREFERENCES, "Choose…")}
        />
      );
    if (rule.field === "tag")
      return (
        <SelectField
          label="Value"
          value={rule.value ?? ""}
          onChange={(e) => onChange({ ...rule, value: e.target.value })}
          options={[
            { value: "", label: "Choose…" },
            ...tags.map((t) => ({ value: t.slug, label: t.name })),
          ]}
        />
      );
    const numeric = rule.field === "engaged" || rule.field === "purchased_product";
    return (
      <TextField
        label="Value"
        type={["confirmed", "consent"].includes(rule.field) ? "date" : numeric ? "number" : "text"}
        value={rule.value ?? ""}
        onChange={(e) =>
          onChange({ ...rule, value: numeric ? Number(e.target.value) : e.target.value })
        }
      />
    );
  };
  return (
    <div className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
      <SelectField
        label="Field"
        value={rule.field}
        onChange={(e) => {
          const key = e.target.value;
          onChange({ field: key, op: Object.keys(SEGMENT_FIELDS[key].ops)[0], value: "" });
        }}
        options={Object.entries(SEGMENT_FIELDS).map(([value, f]) => ({ value, label: f.label }))}
      />
      <SelectField
        label="Condition"
        value={rule.op}
        onChange={(e) => onChange({ ...rule, op: e.target.value })}
        options={Object.entries(field.ops).map(([value, label]) => ({ value, label }))}
      />
      {valueInput()}
      <Button variant="ghost" onClick={onRemove} aria-label="Remove rule">
        <Trash2 aria-hidden className="size-4" />
      </Button>
    </div>
  );
}

function Segments() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const { data, error, reload } = useAdminQuery(() => api.segments.list(), []);
  const tags = useAdminQuery(() => api.subscriberTags.list(), []);
  const [form, setForm] = useState(null);
  const [preview, setPreview] = useState(null);
  const [formError, setFormError] = useState(null);
  const save = async () => {
    setFormError(null);
    try {
      if (form.id) await api.segments.update(form.id, form);
      else await api.segments.create(form);
      notify("Segment saved.");
      setForm(null);
      reload();
    } catch (err) {
      setFormError(err);
    }
  };
  const count = async () => {
    try {
      setPreview((await api.segments.preview(form.rules)).data.count);
    } catch (err) {
      setFormError(err);
    }
  };
  if (error) return <ErrorState title="We couldn't load segments" onRetry={reload} />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Segments only ever narrow the audience of confirmed, consenting subscribers. Counts are
        calculated live.
      </p>
      {can("subscribers.manage") && !form && (
        <Button onClick={() => setForm({ name: "", description: "", rules: [] })}>
          <Plus aria-hidden className="size-4" /> New segment
        </Button>
      )}
      {form && (
        <div className="space-y-3 rounded-2xl bg-white p-5 shadow-sm">
          <TextField
            label="Name"
            required
            value={form.name}
            error={fieldError(formError, "name")}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextField
            label="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          {form.rules.map((rule, i) => (
            <RuleRow
              key={i}
              rule={rule}
              tags={tags.data ?? []}
              onChange={(next) =>
                setForm({ ...form, rules: form.rules.map((r, j) => (j === i ? next : r)) })
              }
              onRemove={() => setForm({ ...form, rules: form.rules.filter((_, j) => j !== i) })}
            />
          ))}
          {fieldError(formError, "rules") && (
            <p role="alert" className="text-sm text-red-800">
              {fieldError(formError, "rules")}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() =>
                setForm({
                  ...form,
                  rules: [...form.rules, { field: "preference", op: "has", value: "weekly" }],
                })
              }
            >
              Add rule
            </Button>
            <Button variant="outline" onClick={count}>
              Count matching subscribers
            </Button>
            <Button onClick={save}>Save segment</Button>
            <Button variant="ghost" onClick={() => setForm(null)}>
              Cancel
            </Button>
          </div>
          {preview !== null && (
            <p role="status" className="text-sm">
              {preview} confirmed subscriber{preview === 1 ? "" : "s"} match right now.
            </p>
          )}
        </div>
      )}
      <ul className="space-y-2">
        {(data ?? []).map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between rounded-xl bg-white p-4 shadow-sm"
          >
            <div>
              <p className="font-medium">{s.name}</p>
              <p className="text-sm text-muted">
                {s.count} matching · {s.rules.length} rule{s.rules.length === 1 ? "" : "s"}
              </p>
            </div>
            {can("subscribers.manage") && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setForm(s)}>
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    try {
                      await api.segments.remove(s.id);
                      reload();
                    } catch (err) {
                      notify(err.message, "error");
                    }
                  }}
                >
                  Delete
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Tags() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const notify = useNotify();
  const { data, error, reload } = useAdminQuery(() => api.subscriberTags.list(), []);
  const [name, setName] = useState("");
  if (error) return <ErrorState title="We couldn't load tags" onRetry={reload} />;
  return (
    <div className="space-y-4">
      {can("subscribers.manage") && (
        <form
          className="flex items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api.subscriberTags.create({ name });
              setName("");
              reload();
            } catch (err) {
              notify(err.message, "error");
            }
          }}
        >
          <TextField label="New tag" value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit">Add tag</Button>
        </form>
      )}
      <ul className="space-y-2">
        {(data ?? []).map((t) => (
          <li
            key={t.id}
            className="flex items-center justify-between rounded-xl bg-white p-3 shadow-sm"
          >
            <span>
              {t.name} <span className="text-sm text-muted">({t.count})</span>
            </span>
            {can("subscribers.manage") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await api.subscriberTags.remove(t.id);
                  reload();
                }}
              >
                Delete
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Suppressions() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const notify = useNotify();
  const [page, setPage] = useState(1);
  const [form, setForm] = useState({ email: "", note: "" });
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.suppressions.list({ page }),
    [page],
  );
  const total = meta?.total ?? 0;
  if (error) return <ErrorState title="We couldn't load the suppression list" onRetry={reload} />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Suppressed addresses are never emailed. Only a fingerprint (hash) of each address is kept,
        so erased contacts stay protected without storing their email.
      </p>
      {can("subscribers.manage") && (
        <form
          className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api.suppressions.add(form);
              setForm({ email: "", note: "" });
              notify("Address blocked.");
              reload();
            } catch (err) {
              notify(err.message, "error");
            }
          }}
        >
          <TextField
            label="Block an address"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <TextField
            label="Note (optional)"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
          <Button type="submit">Block</Button>
        </form>
      )}
      <DataTable
        caption="Suppression list"
        rows={data}
        loading={loading}
        empty={{ icon: Inbox, title: "No suppressed addresses" }}
        columns={[
          { key: "hash", header: "Fingerprint", render: (r) => <code>{r.email_hash}</code> },
          { key: "reason", header: "Reason", render: (r) => r.reason },
          { key: "source", header: "Source", render: (r) => r.source || "—" },
          { key: "created", header: "Added", render: (r) => formatDateTime(r.created_at) },
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            render: (r) =>
              r.reason === "manual" && can("subscribers.manage") ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await api.suppressions.remove(r.id);
                    reload();
                  }}
                >
                  Remove
                </Button>
              ) : null,
          },
        ]}
      />
      <Pagination
        pagination={{
          page,
          page_size: 25,
          total,
          total_pages: Math.max(1, Math.ceil(total / 25)),
          has_next: page * 25 < total,
          has_prev: page > 1,
        }}
        onPage={setPage}
      />
    </div>
  );
}

function ImportPanel() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [file, setFile] = useState(null);
  const [form, setForm] = useState({ consent_attested: false, consent_source: "", tag: "" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  if (!can("subscribers.manage"))
    return <p className="text-sm text-muted">You don't have permission to import subscribers.</p>;
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    try {
      const content = await file.text();
      setResult((await api.subscribers.import({ ...form, content })).data);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form onSubmit={submit} className="max-w-2xl space-y-4 rounded-2xl bg-white p-5 shadow-sm">
      <p className="text-sm text-muted">
        CSV with an <code>email</code> column (optional <code>first_name</code>,{" "}
        <code>consent_at</code>, <code>consent_text</code>). Imported contacts are{" "}
        <strong>quarantined</strong>: they are never emailed until they confirm through a
        confirmation request, unless you attest below that they gave recorded consent. Existing
        subscribers and suppressed addresses are never changed.
      </p>
      <label className="block text-sm font-medium">
        CSV file
        <input
          type="file"
          accept=".csv,text/csv"
          className="mt-2 block w-full text-sm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <CheckboxField
        label="These contacts gave recorded opt-in consent to receive this newsletter"
        hint="Rows also need a consent_at date. Without both, contacts stay quarantined."
        checked={form.consent_attested}
        onChange={(e) => setForm({ ...form, consent_attested: e.target.checked })}
      />
      {form.consent_attested && (
        <TextAreaField
          label="Where and how was consent collected?"
          required
          value={form.consent_source}
          error={fieldError(error, "consent_source")}
          onChange={(e) => setForm({ ...form, consent_source: e.target.value })}
        />
      )}
      <TextField
        label="Add a tag (slug, optional)"
        value={form.tag}
        error={fieldError(error, "tag")}
        onChange={(e) => setForm({ ...form, tag: e.target.value })}
      />
      {error && !fieldError(error, "consent_source") && (
        <p role="alert" className="text-sm text-red-800">
          {fieldError(error, "file") || error.message}
        </p>
      )}
      <Button type="submit" disabled={!file}>
        <Upload aria-hidden className="size-4" /> Import
      </Button>
      {result && (
        <p role="status" className="text-sm">
          Created {result.created} ({result.subscribed} subscribed, {result.quarantined}{" "}
          quarantined). Skipped: {result.existing} existing, {result.suppressed} suppressed,{" "}
          {result.invalid} invalid. Batch {result.batch}.
        </p>
      )}
    </form>
  );
}

export function SubscribersPage() {
  const [tab, setTab] = useState("list");
  return (
    <>
      <AdminPageHeader
        title="Subscribers"
        description="The Positive Reset audience. Only confirmed (double opt-in) subscribers receive newsletters."
        breadcrumbs={[{ label: "Subscribers" }]}
      />
      <div role="tablist" aria-label="Subscriber sections" className="mb-6 flex flex-wrap gap-2">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={
              tab === key
                ? "rounded-full bg-sage-700 px-4 py-2 text-sm font-medium text-ivory"
                : "rounded-full border border-charcoal/15 bg-white px-4 py-2 text-sm"
            }
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "list" && <SubscriberList />}
        {tab === "segments" && <Segments />}
        {tab === "tags" && <Tags />}
        {tab === "suppressions" && <Suppressions />}
        {tab === "import" && <ImportPanel />}
      </div>
    </>
  );
}

export function SubscriberDetailPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const { data: s, error, reload } = useAdminQuery(() => api.subscribers.get(id), [id]);
  const tags = useAdminQuery(() => api.subscriberTags.list(), []);
  const [confirm, setConfirm] = useState(null);
  if (error) return <ErrorState title="We couldn't load this subscriber" onRetry={reload} />;
  if (!s) return <p className="text-muted">Loading…</p>;
  const act = async (action) => {
    try {
      await api.subscribers.action(s.id, action, {});
      setConfirm(null);
      if (action === "erase") {
        notify("Subscriber data erased.");
        navigate("/admin/subscribers");
        return;
      }
      notify("Done.");
      reload();
    } catch (err) {
      setConfirm(null);
      notify(err.message, "error");
    }
  };
  const toggleTag = async (slug) => {
    const current = s.tags.map((t) => t.slug);
    const next = current.includes(slug) ? current.filter((t) => t !== slug) : [...current, slug];
    await api.subscribers.setTags(s.id, next);
    reload();
  };
  return (
    <>
      <AdminPageHeader
        title={s.email}
        description={SUBSCRIBER_STATUS[s.status]}
        breadcrumbs={[{ label: "Subscribers", to: "/admin/subscribers" }, { label: s.email }]}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl bg-white p-5 shadow-sm" aria-labelledby="consent-h">
          <h2 id="consent-h" className="text-lg font-medium">
            Consent record
          </h2>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">Given</dt>
            <dd>{s.consent.at ? formatDateTime(s.consent.at) : "Not recorded"}</dd>
            <dt className="text-muted">Version</dt>
            <dd>{s.consent.version || "—"}</dd>
            <dt className="text-muted">Wording</dt>
            <dd>{s.consent.text || "—"}</dd>
            <dt className="text-muted">Source</dt>
            <dd>
              {SIGNUP_SOURCES[s.consent.source] ?? s.consent.source}
              {s.consent.source_detail && ` · ${s.consent.source_detail}`}
            </dd>
            <dt className="text-muted">Confirmed</dt>
            <dd>{s.consent.confirmed_at ? formatDateTime(s.consent.confirmed_at) : "Not yet"}</dd>
            <dt className="text-muted">IP evidence</dt>
            <dd>{s.consent.ip_hash_recorded ? "Hashed IP recorded" : "None"}</dd>
            <dt className="text-muted">Preferences</dt>
            <dd>{s.preferences.map((p) => PREFERENCES[p] ?? p).join(", ") || "—"}</dd>
            {s.suppressed && (
              <>
                <dt className="text-muted">Suppressed</dt>
                <dd>{s.suppressed}</dd>
              </>
            )}
          </dl>
          {can("subscribers.manage") && (
            <div className="mt-5 flex flex-wrap gap-2">
              {["subscribed", "pending"].includes(s.status) && (
                <Button variant="outline" size="sm" onClick={() => setConfirm("unsubscribe")}>
                  Unsubscribe
                </Button>
              )}
              {["pending", "quarantined"].includes(s.status) && (
                <Button variant="outline" size="sm" onClick={() => act("resend-confirmation")}>
                  {s.status === "quarantined"
                    ? "Ask to confirm (opt-in request)"
                    : "Resend confirmation"}
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => setConfirm("erase")}>
                Erase personal data
              </Button>
            </div>
          )}
        </section>
        <section className="rounded-2xl bg-white p-5 shadow-sm" aria-labelledby="tags-h">
          <h2 id="tags-h" className="text-lg font-medium">
            Tags
          </h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {(tags.data ?? []).map((t) => {
              const on = s.tags.some((x) => x.slug === t.slug);
              return (
                <button
                  key={t.slug}
                  type="button"
                  aria-pressed={on}
                  disabled={!can("subscribers.manage")}
                  onClick={() => toggleTag(t.slug)}
                  className={
                    on
                      ? "rounded-full bg-sage-700 px-3 py-1 text-sm text-ivory"
                      : "rounded-full border border-charcoal/15 px-3 py-1 text-sm"
                  }
                >
                  {t.name}
                </button>
              );
            })}
            {(tags.data ?? []).length === 0 && <p className="text-sm text-muted">No tags yet.</p>}
          </div>
          <h2 className="mt-6 text-lg font-medium">Email activity</h2>
          <p className="mt-2 text-sm text-muted">
            {Object.entries(s.messages).length
              ? Object.entries(s.messages)
                  .map(([status, n]) => `${n} ${status}`)
                  .join(" · ")
              : "No emails yet."}
          </p>
        </section>
        <section
          className="rounded-2xl bg-white p-5 shadow-sm lg:col-span-2"
          aria-labelledby="act-h"
        >
          <h2 id="act-h" className="text-lg font-medium">
            Activity and consent history
          </h2>
          <ol className="mt-3 space-y-2 text-sm">
            {s.activity.map((a, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-44 shrink-0 text-muted">{formatDateTime(a.at)}</span>
                <span>
                  <strong>{a.event.replaceAll("_", " ")}</strong>
                  {a.details?.via && ` · via ${a.details.via}`}
                  {a.details?.source && ` · ${a.details.source}`}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "erase" ? "Erase this subscriber?" : "Unsubscribe this person?"}
        message={
          confirm === "erase"
            ? "Their details and history are deleted. The address stays on the suppression list (as a fingerprint) so it is never emailed again."
            : "They will stop receiving all newsletters and automations immediately."
        }
        confirmLabel={confirm === "erase" ? "Erase" : "Unsubscribe"}
        tone="danger"
        onConfirm={() => act(confirm)}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}

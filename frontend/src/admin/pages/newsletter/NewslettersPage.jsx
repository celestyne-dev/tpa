import { Plus, Send } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BlockEditor } from "../../components/BlockEditor";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { SelectField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { CAMPAIGN_STATUS, EMAIL_BLOCKS } from "../../components/newsletterLabels";
import { SendingModeNotice } from "../../components/SendingModeNotice";
import { useNotify } from "../../components/notifyContext";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

function NewCampaignDialog({ onClose }) {
  const api = useAdminApi();
  const navigate = useNavigate();
  const templates = useAdminQuery(() => api.emailTemplates.list(), []);
  const [form, setForm] = useState({ name: "", template_key: "weekly_edition" });
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    try {
      const res = await api.newsletters.create({
        name: form.name || undefined,
        template_key: form.template_key || undefined,
      });
      navigate(`/admin/newsletters/${res.data.id}`);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="New campaign"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="new-campaign">
            Create draft
          </Button>
        </>
      }
    >
      <form id="new-campaign" onSubmit={submit} className="grid gap-4">
        <TextField
          label="Internal name"
          value={form.name}
          error={fieldError(error, "name")}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <SelectField
          label="Start from"
          value={form.template_key}
          onChange={(e) => setForm({ ...form, template_key: e.target.value })}
          options={[
            { value: "", label: "Blank email" },
            ...(templates.data ?? []).map((t) => ({ value: t.key, label: t.name })),
          ]}
        />
        {error && !fieldError(error, "name") && (
          <p role="alert" className="text-sm text-red-800">
            {error.message}
          </p>
        )}
      </form>
    </Modal>
  );
}

function TemplatesPanel() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const { data, error, reload } = useAdminQuery(() => api.emailTemplates.list(), []);
  const [editing, setEditing] = useState(null);
  const [formError, setFormError] = useState(null);
  if (error) return <ErrorState title="We couldn't load templates" onRetry={reload} />;
  const save = async () => {
    setFormError(null);
    const body = {
      name: editing.name,
      description: editing.description,
      subject: editing.subject,
      preheader: editing.preheader,
      blocks: editing.blocks,
    };
    try {
      if (editing.id) await api.emailTemplates.update(editing.id, body);
      else await api.emailTemplates.create(body);
      notify("Template saved.");
      setEditing(null);
      reload();
    } catch (err) {
      setFormError(err);
    }
  };
  return (
    <div className="space-y-4">
      {can("email_templates.manage") && (
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() =>
              setEditing({ name: "", description: "", subject: "", preheader: "", blocks: [] })
            }
          >
            <Plus aria-hidden className="size-4" /> New template
          </Button>
          {(data ?? []).length === 0 && (
            <Button
              variant="outline"
              onClick={async () => {
                await api.emailTemplates.addStarters();
                reload();
              }}
            >
              Add the starter templates
            </Button>
          )}
        </div>
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {(data ?? []).map((t) => (
          <li key={t.id} className="rounded-2xl bg-white p-4 shadow-sm">
            <p className="font-medium">{t.name}</p>
            <p className="text-sm text-muted">{t.description}</p>
            {can("email_templates.manage") && (
              <Button variant="outline" size="sm" className="mt-3" onClick={() => setEditing(t)}>
                Edit
              </Button>
            )}
          </li>
        ))}
      </ul>
      {editing && (
        <Modal
          open
          size="lg"
          onClose={() => setEditing(null)}
          title={editing.id ? `Edit “${editing.name}”` : "New template"}
          footer={
            <>
              <Button variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button onClick={save}>Save template</Button>
            </>
          }
        >
          <div className="grid gap-4">
            <TextField
              label="Name"
              value={editing.name}
              error={fieldError(formError, "name")}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
            <TextField
              label="Subject"
              value={editing.subject}
              onChange={(e) => setEditing({ ...editing, subject: e.target.value })}
            />
            <TextField
              label="Preheader"
              value={editing.preheader}
              onChange={(e) => setEditing({ ...editing, preheader: e.target.value })}
            />
            <BlockEditor
              legend="Email content"
              allowed={EMAIL_BLOCKS}
              blocks={editing.blocks}
              errors={formError?.details?.body}
              onChange={(blocks) => setEditing({ ...editing, blocks })}
            />
          </div>
        </Modal>
      )}
    </div>
  );
}

export function NewslettersPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [tab, setTab] = useState("campaigns");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const params = Object.fromEntries(Object.entries({ status, page }).filter(([, v]) => v));
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.newsletters.list(params),
    [JSON.stringify(params)],
  );
  const total = meta?.total ?? 0;
  return (
    <>
      <AdminPageHeader
        title="Newsletters"
        description="Campaigns for The Positive Reset: draft, preview, test, approve, schedule and send."
        breadcrumbs={[{ label: "Newsletters" }]}
        actions={
          can("newsletters.create") && (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden className="size-4" /> New campaign
            </Button>
          )
        }
      />
      <SendingModeNotice mode={meta?.sending_mode} />
      <div role="tablist" aria-label="Newsletter sections" className="mb-6 flex gap-2">
        {[
          ["campaigns", "Campaigns"],
          ["templates", "Templates"],
        ].map(([key, label]) => (
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
      {tab === "templates" ? (
        <TemplatesPanel />
      ) : error ? (
        <ErrorState title="We couldn't load campaigns" onRetry={reload} />
      ) : (
        <>
          <SelectField
            className="mb-4 max-w-xs"
            label="Status"
            value={status}
            onChange={(e) => {
              setPage(1);
              setStatus(e.target.value);
            }}
            options={[
              { value: "", label: "Any" },
              ...Object.entries(CAMPAIGN_STATUS).map(([value, label]) => ({ value, label })),
            ]}
          />
          <DataTable
            caption="Campaigns"
            rows={data}
            loading={loading}
            empty={{ icon: Send, title: "No campaigns yet" }}
            columns={[
              {
                key: "name",
                header: "Campaign",
                render: (c) => (
                  <div>
                    <Link to={`/admin/newsletters/${c.id}`} className="font-medium hover:underline">
                      {c.name}
                    </Link>
                    <p className="text-xs text-muted">{c.subject || "No subject yet"}</p>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (c) => <StatusBadge status={CAMPAIGN_STATUS[c.status] ?? c.status} />,
              },
              {
                key: "audience",
                header: "Audience",
                render: (c) => c.segment?.name ?? "All subscribers",
              },
              {
                key: "when",
                header: "Scheduled / sent",
                render: (c) =>
                  c.completed_at
                    ? `Sent ${formatDateTime(c.completed_at)}`
                    : c.scheduled_at
                      ? formatDateTime(c.scheduled_at)
                      : "—",
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
      {creating && <NewCampaignDialog onClose={() => setCreating(false)} />}
    </>
  );
}

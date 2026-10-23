import { Eye, Send } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BlockEditor } from "../../components/BlockEditor";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { SelectField, TextField } from "../../components/Fields";
import { CAMPAIGN_STATUS, EMAIL_BLOCKS, MESSAGE_STATUS } from "../../components/newsletterLabels";
import { useNotify } from "../../components/notifyContext";
import { SendingModeNotice } from "../../components/SendingModeNotice";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

const FIELDS = [
  "name",
  "subject",
  "preheader",
  "from_name",
  "reply_to",
  "blocks",
  "article_ids",
  "product_ids",
  "ctas",
  "segment_id",
];

function Picker({ label, items, selected, onChange, disabled, max }) {
  return (
    <fieldset disabled={disabled} className="space-y-2">
      <legend className="text-sm font-semibold">
        {label} <span className="font-normal text-muted">(up to {max})</span>
      </legend>
      {items.length === 0 && <p className="text-sm text-muted">Nothing available to choose.</p>}
      <div className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-charcoal/10 p-2">
        {items.map((item) => {
          const on = selected.includes(item.id);
          return (
            <label key={item.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-sage-700"
                checked={on}
                disabled={!on && selected.length >= max}
                onChange={() =>
                  onChange(on ? selected.filter((x) => x !== item.id) : [...selected, item.id])
                }
              />
              {item.title}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function Report({ id }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const report = useAdminQuery(() => api.newsletters.report(id), [id]);
  const [status, setStatus] = useState("");
  const messages = useAdminQuery(
    () => api.newsletters.messages(id, status ? { status } : {}),
    [id, status],
  );
  const r = report.data;
  if (report.error)
    return <ErrorState title="We couldn't load the report" onRetry={report.reload} />;
  if (!r) return null;
  const rows = [
    ["Eligible recipients", r.eligible ?? "Not queued yet"],
    ["Queued", r.queued],
    ["Attempted", r.attempted],
    ["Accepted by provider", r.accepted],
    ["Delivered (confirmed by provider)", r.delivered_confirmed],
    ["Failed", r.failed],
    ["Bounced", r.bounced],
    ["Complaints", r.complained],
    ["Unknown (interrupted)", r.unknown],
    ["Suppressed before sending", r.suppressed],
    ["Skipped (test mode)", r.skipped_test_mode],
    ["Cancelled", r.cancelled],
    ["Unsubscribed from this campaign", r.unsubscribed_from_campaign],
  ];
  return (
    <section aria-labelledby="report-h" className="space-y-4">
      <h2 id="report-h" className="text-xl font-medium">
        Delivery report {r.send_mode === "test" && <span className="text-sm">(test mode)</span>}
      </h2>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-white p-3 shadow-sm">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <ul className="list-disc pl-5 text-sm text-muted">
        {r.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <SelectField
        className="max-w-xs"
        label="Recipients by status"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        options={[
          { value: "", label: "All" },
          ...Object.entries(MESSAGE_STATUS).map(([value, label]) => ({ value, label })),
        ]}
      />
      <DataTable
        caption="Recipients"
        rows={messages.data}
        loading={messages.loading}
        empty={{ icon: Send, title: "No messages" }}
        columns={[
          { key: "to", header: "Recipient", render: (m) => m.to },
          {
            key: "status",
            header: "Status",
            render: (m) => <StatusBadge status={MESSAGE_STATUS[m.status] ?? m.status} />,
          },
          { key: "attempts", header: "Attempts", render: (m) => m.attempts },
          { key: "error", header: "Details", render: (m) => m.error || "—" },
          {
            key: "retry",
            header: <span className="sr-only">Actions</span>,
            render: (m) =>
              ["failed", "unknown"].includes(m.status) && can("newsletters.send") ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await api.newsletters.retryMessage(m.id);
                    notify("Queued for another attempt.");
                    messages.reload();
                  }}
                >
                  Retry
                </Button>
              ) : null,
          },
        ]}
      />
    </section>
  );
}

export function NewsletterEditorPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const { data, error, reload, setData } = useAdminQuery(() => api.newsletters.get(id), [id]);
  if (error) return <ErrorState title="We couldn't load this campaign" onRetry={reload} />;
  if (!data) return <p className="text-muted">Loading…</p>;
  return (
    <CampaignEditor
      key={`${data.id}:${data.lock_version}:${data.status}`}
      data={data}
      setData={setData}
    />
  );
}

function CampaignEditor({ data, setData }) {
  const id = data.id;
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const segments = useAdminQuery(() => api.segments.list(), []);
  const articles = useAdminQuery(
    () => api.articles.list({ status: "published", page_size: 100 }),
    [],
  );
  const products = useAdminQuery(
    () => api.products.list({ status: "published", page_size: 100 }),
    [],
  );
  const settings = useAdminQuery(() => api.newsletters.list({ page_size: 1 }), []);
  const [form, setForm] = useState(() => Object.fromEntries(FIELDS.map((f) => [f, data[f]])));
  const [saveError, setSaveError] = useState(null);
  const [preview, setPreview] = useState(null);
  const [scheduleAt, setScheduleAt] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);

  const editable = ["draft", "approved"].includes(data.status) && can("newsletters.edit");
  const dirty = FIELDS.some((f) => JSON.stringify(form[f]) !== JSON.stringify(data[f]));

  const save = async () => {
    setSaveError(null);
    try {
      const res = await api.newsletters.update(id, { ...form, lock_version: data.lock_version });
      setData(res.data);
      notify(data.status === "approved" ? "Saved. Editing withdrew the approval." : "Draft saved.");
      return true;
    } catch (err) {
      setSaveError(err);
      return false;
    }
  };
  const act = async (action, body) => {
    setBusy(true);
    try {
      if (dirty && editable && !(await save())) return;
      const res = await api.newsletters.action(id, action, body);
      setConfirm(null);
      if (action === "test") {
        notify(
          res.data.status === "accepted"
            ? `Test email handed to the provider for ${res.data.to}.`
            : `Test email failed: ${res.data.error}`,
          res.data.status === "accepted" ? "success" : "error",
        );
      } else if (action === "duplicate") {
        notify("Copied as a new draft.");
      } else {
        notify("Done.");
      }
      setData(res.data.campaign);
    } catch (err) {
      setConfirm(null);
      setSaveError(err);
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const showPreview = async () => {
    try {
      setPreview((await api.newsletters.preview(id, form)).data);
    } catch (err) {
      setSaveError(err);
    }
  };
  const segmentName =
    (segments.data ?? []).find((s) => s.id === form.segment_id)?.name ??
    "All confirmed subscribers";
  const audienceCount = (segments.data ?? []).find((s) => s.id === form.segment_id)?.count;

  return (
    <>
      <AdminPageHeader
        title={data.name}
        description={`${CAMPAIGN_STATUS[data.status]}${data.scheduled_at ? ` · scheduled for ${formatDateTime(data.scheduled_at)}` : ""}`}
        breadcrumbs={[{ label: "Newsletters", to: "/admin/newsletters" }, { label: data.name }]}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={showPreview}>
              <Eye aria-hidden className="size-4" /> Preview
            </Button>
            {editable && (
              <Button onClick={save} disabled={!dirty}>
                Save draft
              </Button>
            )}
          </div>
        }
      />
      <SendingModeNotice mode={settings.meta?.sending_mode} />
      {saveError && (
        <div role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-900">
          <p>{saveError.message}</p>
          {saveError.details?.campaign && (
            <ul className="mt-2 list-disc pl-5">
              {saveError.details.campaign.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="space-y-5 rounded-2xl bg-white p-5 shadow-sm">
          <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Internal name"
              value={form.name}
              error={fieldError(saveError, "name")}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <TextField
              label="Email subject"
              value={form.subject}
              error={fieldError(saveError, "subject")}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
            />
            <TextField
              className="sm:col-span-2"
              label="Preheader (inbox preview text)"
              value={form.preheader}
              error={fieldError(saveError, "preheader")}
              onChange={(e) => setForm({ ...form, preheader: e.target.value })}
            />
            <TextField
              label="Sender name"
              hint="Leave empty to use the default from Email settings."
              value={form.from_name}
              onChange={(e) => setForm({ ...form, from_name: e.target.value })}
            />
            <TextField
              label="Reply-to address"
              type="email"
              value={form.reply_to}
              error={fieldError(saveError, "reply_to")}
              onChange={(e) => setForm({ ...form, reply_to: e.target.value })}
            />
          </fieldset>
          <p className="text-xs text-muted">
            Use <code>{"{{first_name}}"}</code> to greet subscribers by name (“friend” when
            unknown). Images come from the media library. Every email ends with the unsubscribe and
            preference links automatically.
          </p>
          <BlockEditor
            legend="Newsletter body"
            allowed={EMAIL_BLOCKS}
            disabled={!editable}
            blocks={form.blocks}
            errors={saveError?.details?.body}
            onChange={(blocks) => setForm({ ...form, blocks })}
          />
          <fieldset disabled={!editable} className="space-y-3">
            <legend className="text-sm font-semibold">Buttons (up to 3)</legend>
            {form.ctas.map((cta, i) => (
              <div key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <TextField
                  label="Label"
                  value={cta.label}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      ctas: form.ctas.map((c, j) =>
                        j === i ? { ...c, label: e.target.value } : c,
                      ),
                    })
                  }
                />
                <TextField
                  label="Link (site path or https)"
                  value={cta.href}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      ctas: form.ctas.map((c, j) => (j === i ? { ...c, href: e.target.value } : c)),
                    })
                  }
                />
                <Button
                  variant="ghost"
                  onClick={() => setForm({ ...form, ctas: form.ctas.filter((_, j) => j !== i) })}
                >
                  Remove
                </Button>
              </div>
            ))}
            {fieldError(saveError, "ctas") && (
              <p role="alert" className="text-sm text-red-800">
                {fieldError(saveError, "ctas")}
              </p>
            )}
            {form.ctas.length < 3 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setForm({ ...form, ctas: [...form.ctas, { label: "", href: "/" }] })}
              >
                Add button
              </Button>
            )}
          </fieldset>
        </div>
        <aside className="space-y-5">
          <section className="space-y-3 rounded-2xl bg-white p-5 shadow-sm">
            <h2 className="font-medium">Audience</h2>
            <SelectField
              label="Target segment"
              disabled={!editable}
              value={form.segment_id ? String(form.segment_id) : ""}
              onChange={(e) =>
                setForm({ ...form, segment_id: e.target.value ? Number(e.target.value) : null })
              }
              options={[
                { value: "", label: "All confirmed subscribers" },
                ...(segments.data ?? []).map((s) => ({ value: String(s.id), label: s.name })),
              ]}
            />
            <p className="text-xs text-muted">
              Only confirmed subscribers who have not unsubscribed or been suppressed are included.
              The audience is fixed when sending starts.
            </p>
          </section>
          <section className="space-y-4 rounded-2xl bg-white p-5 shadow-sm">
            <Picker
              label="Featured articles"
              max={6}
              disabled={!editable}
              items={(articles.data ?? []).map((a) => ({ id: a.id, title: a.title }))}
              selected={form.article_ids}
              onChange={(article_ids) => setForm({ ...form, article_ids })}
            />
            <Picker
              label="Selected products"
              max={4}
              disabled={!editable}
              items={(products.data ?? []).map((p) => ({ id: p.id, title: p.title }))}
              selected={form.product_ids}
              onChange={(product_ids) => setForm({ ...form, product_ids })}
            />
            <p className="text-xs text-muted">
              Only published items appear in the email; product prices show only when on sale.
            </p>
          </section>
          <section className="space-y-3 rounded-2xl bg-white p-5 shadow-sm">
            <h2 className="font-medium">Publish</h2>
            {can("newsletters.edit") && (
              <Button
                variant="outline"
                className="w-full"
                disabled={busy}
                onClick={() => act("test")}
              >
                Send a test to me
              </Button>
            )}
            {can("newsletters.create") && (
              <Button variant="ghost" className="w-full" onClick={() => act("duplicate")}>
                Duplicate
              </Button>
            )}
            {data.status === "draft" && can("newsletters.publish") && (
              <Button className="w-full" disabled={busy} onClick={() => act("approve")}>
                Approve for sending
              </Button>
            )}
            {data.status === "approved" && can("newsletters.publish") && (
              <Button variant="outline" className="w-full" onClick={() => act("withdraw-approval")}>
                Withdraw approval
              </Button>
            )}
            {data.status === "approved" && can("newsletters.schedule") && (
              <div className="space-y-2">
                <TextField
                  label="Send at (your local time)"
                  type="datetime-local"
                  value={scheduleAt}
                  error={fieldError(saveError, "scheduled_at")}
                  onChange={(e) => setScheduleAt(e.target.value)}
                />
                <Button
                  variant="outline"
                  className="w-full"
                  disabled={!scheduleAt}
                  onClick={() =>
                    act("schedule", { scheduled_at: new Date(scheduleAt).toISOString() })
                  }
                >
                  Schedule
                </Button>
              </div>
            )}
            {data.status === "approved" && can("newsletters.send") && (
              <Button className="w-full" onClick={() => setConfirm("send")}>
                <Send aria-hidden className="size-4" /> Send now…
              </Button>
            )}
            {["scheduled", "sending"].includes(data.status) &&
              (can("newsletters.send") ||
                (data.status === "scheduled" && can("newsletters.schedule"))) && (
                <Button variant="outline" className="w-full" onClick={() => setConfirm("cancel")}>
                  {data.status === "scheduled" ? "Cancel schedule" : "Stop sending"}
                </Button>
              )}
          </section>
        </aside>
      </div>
      {preview && (
        <section aria-labelledby="preview-h" className="mt-8 space-y-3">
          <h2 id="preview-h" className="text-xl font-medium">
            Preview: {preview.subject}
          </h2>
          <p className="text-sm text-muted">
            Rendered exactly as sent (links in the footer are disabled in previews). Nothing is sent
            by previewing.
          </p>
          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <iframe
              title="Email preview"
              sandbox=""
              srcDoc={preview.html}
              className="h-[640px] w-full rounded-2xl border border-charcoal/10 bg-white"
            />
            <pre className="h-[640px] overflow-auto rounded-2xl bg-white p-4 text-xs whitespace-pre-wrap">
              {preview.text}
            </pre>
          </div>
        </section>
      )}
      {can("newsletters.reports") && ["sending", "sent", "cancelled"].includes(data.status) && (
        <div className="mt-8">
          <Report id={id} />
        </div>
      )}
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "send" ? "Send this campaign now?" : "Stop this campaign?"}
        message={
          confirm === "send"
            ? `It goes to: ${segmentName}${audienceCount != null ? ` (${audienceCount} right now)` : ""}. Sending can be stopped, but emails already handed to the provider can't be recalled.`
            : "Unsent emails are cancelled. Emails already handed to the provider can't be recalled."
        }
        confirmLabel={confirm === "send" ? "Send now" : "Stop"}
        tone={confirm === "send" ? "primary" : "danger"}
        busy={busy}
        onConfirm={() => act(confirm === "send" ? "send" : "cancel")}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}

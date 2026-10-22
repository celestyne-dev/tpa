import { ArrowDown, ArrowUp, Megaphone, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BuilderLookups } from "../components/builder/BuilderLookups";
import { fromLocalInput, toLocalInput } from "../components/builder/draft";
import { LinkField } from "../components/builder/SectionFields";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

const VARIANTS = {
  sage: { label: "Deep sage", className: "bg-sage-800 text-ivory" },
  gold: { label: "Soft gold", className: "bg-gold-100 text-charcoal" },
  charcoal: { label: "Charcoal", className: "bg-charcoal text-ivory" },
  ivory: { label: "Cream", className: "bg-cream text-charcoal border border-charcoal/10" },
};
const STATES = {
  active: "bg-sage-100 text-sage-800",
  scheduled: "bg-gold-100 text-charcoal",
  ended: "bg-charcoal/10 text-muted",
  disabled: "bg-beige text-muted",
};

const blank = {
  name: "",
  message: "",
  cta_label: "",
  cta_url: "",
  variant: "sage",
  target: "all",
  target_paths: [],
  starts_at: null,
  ends_at: null,
  is_enabled: false,
  is_dismissible: true,
};

function AnnouncementForm({ initial, onClose, onSaved }) {
  const api = useAdminApi();
  const [form, setForm] = useState({ ...blank, ...initial });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: form.name,
      message: form.message,
      cta_label: form.cta_label || null,
      cta_url: form.cta_url || null,
      variant: form.variant,
      target: form.target,
      target_paths: form.target === "paths" ? form.target_paths : [],
      starts_at: form.starts_at,
      ends_at: form.ends_at,
      is_enabled: form.is_enabled,
      is_dismissible: form.is_dismissible,
    };
    try {
      const res = initial?.id
        ? await api.announcements.update(initial.id, body)
        : await api.announcements.create(body);
      onSaved(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      title={initial?.id ? "Edit announcement" : "New announcement"}
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="announcement-form" disabled={busy}>
            {form.is_enabled ? "Save and publish" : "Save (not shown)"}
          </Button>
        </>
      }
    >
      <form id="announcement-form" onSubmit={submit} className="space-y-4">
        <div
          aria-hidden
          className={cn(
            "rounded-lg px-4 py-2.5 text-center text-sm",
            VARIANTS[form.variant].className,
          )}
        >
          {form.message || "Your announcement message"}
          {form.cta_label && (
            <span className="ml-3 font-semibold underline">{form.cta_label} →</span>
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Internal name"
            required
            value={form.name}
            maxLength={120}
            error={fieldError(error, "name")}
            onChange={(e) => set({ name: e.target.value })}
          />
          <SelectField
            label="Colour"
            value={form.variant}
            options={Object.entries(VARIANTS).map(([value, v]) => ({ value, label: v.label }))}
            onChange={(e) => set({ variant: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Message"
            required
            rows={2}
            maxLength={240}
            value={form.message}
            hint="One short sentence works best."
            error={fieldError(error, "message")}
            onChange={(e) => set({ message: e.target.value })}
          />
          <TextField
            label="Link text (optional)"
            value={form.cta_label ?? ""}
            maxLength={60}
            error={fieldError(error, "cta_label")}
            onChange={(e) => set({ cta_label: e.target.value })}
          />
          <LinkField
            label="Link (optional)"
            value={form.cta_url}
            error={fieldError(error, "cta_url")}
            onChange={(cta_url) => set({ cta_url })}
          />
          <SelectField
            label="Show on"
            value={form.target}
            options={[
              { value: "all", label: "Every page" },
              { value: "home", label: "Homepage only" },
              { value: "paths", label: "Chosen pages" },
            ]}
            onChange={(e) => set({ target: e.target.value })}
          />
          {form.target === "paths" && (
            <TextAreaField
              label="Page addresses"
              rows={3}
              value={form.target_paths.join("\n")}
              hint="One site path per line, e.g. /articles"
              error={fieldError(error, "target_paths")}
              onChange={(e) =>
                set({
                  target_paths: e.target.value
                    .split("\n")
                    .map((p) => p.trim())
                    .filter(Boolean),
                })
              }
            />
          )}
          <TextField
            type="datetime-local"
            label="Start (optional)"
            value={toLocalInput(form.starts_at)}
            error={fieldError(error, "starts_at")}
            onChange={(e) => set({ starts_at: fromLocalInput(e.target.value) })}
          />
          <TextField
            type="datetime-local"
            label="End (optional)"
            value={toLocalInput(form.ends_at)}
            error={fieldError(error, "ends_at")}
            onChange={(e) => set({ ends_at: fromLocalInput(e.target.value) })}
          />
          <CheckboxField
            label="Enabled"
            hint="Shown on the website (within its dates) after the next rebuild."
            checked={form.is_enabled}
            onChange={(e) => set({ is_enabled: e.target.checked })}
          />
          <CheckboxField
            label="Readers can dismiss it"
            checked={form.is_dismissible}
            onChange={(e) => set({ is_dismissible: e.target.checked })}
          />
        </div>
      </form>
    </Modal>
  );
}

export function AnnouncementsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, loading, error, reload, setData } = useAdminQuery(
    () => api.announcements.list(),
    [],
  );
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);

  const reorder = async (index, delta) => {
    const ids = data.map((a) => a.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(index + delta, 0, moved);
    try {
      const res = await api.announcements.reorder(ids);
      setData(res.data);
    } catch (err) {
      notify(err.message, "error");
    }
  };

  return (
    <BuilderLookups>
      <AdminPageHeader
        title="Announcements"
        description="A slim banner above the header for news, launches and campaigns. Only the first matching announcement is shown; it is never a popup."
        breadcrumbs={[{ label: "Announcements" }]}
        actions={
          <Button onClick={() => setEditing({})}>
            <Plus aria-hidden />
            New announcement
          </Button>
        }
      />
      {error ? (
        <ErrorState title="We couldn't load announcements" onRetry={reload} />
      ) : (
        <DataTable
          caption="Announcements"
          rows={data}
          loading={loading}
          empty={{
            icon: Megaphone,
            title: "No announcements",
            description: "Create one to highlight an upcoming release or series.",
          }}
          columns={[
            {
              key: "name",
              header: "Announcement",
              render: (a) => (
                <div>
                  <p className="font-medium">{a.name}</p>
                  <p className="text-sm text-muted">{a.message}</p>
                </div>
              ),
            },
            {
              key: "state",
              header: "Status",
              render: (a) => (
                <span
                  className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATES[a.state])}
                >
                  {
                    { active: "Live", scheduled: "Scheduled", ended: "Ended", disabled: "Off" }[
                      a.state
                    ]
                  }
                </span>
              ),
            },
            {
              key: "dates",
              header: "Dates",
              render: (a) => (
                <span className="text-sm">
                  {a.starts_at ? formatDateTime(a.starts_at) : "Now"} →{" "}
                  {a.ends_at ? formatDateTime(a.ends_at) : "No end"}
                </span>
              ),
            },
            {
              key: "target",
              header: "Shown on",
              render: (a) =>
                a.target === "paths"
                  ? a.target_paths.join(", ")
                  : a.target === "home"
                    ? "Homepage"
                    : "Every page",
            },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              render: (a) => {
                const i = data.findIndex((x) => x.id === a.id);
                return (
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Move ${a.name} up`}
                      disabled={i === 0}
                      onClick={() => reorder(i, -1)}
                    >
                      <ArrowUp aria-hidden />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Move ${a.name} down`}
                      disabled={i === data.length - 1}
                      onClick={() => reorder(i, 1)}
                    >
                      <ArrowDown aria-hidden />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Edit ${a.name}`}
                      onClick={() => setEditing(a)}
                    >
                      <Pencil aria-hidden />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Delete ${a.name}`}
                      onClick={() => setRemoving(a)}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </div>
                );
              },
            },
          ]}
        />
      )}
      {editing && (
        <AnnouncementForm
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            reload();
            notify(
              saved.is_enabled
                ? "Saved. The banner updates after the queued rebuild."
                : "Saved. It is not shown while switched off.",
            );
          }}
        />
      )}
      <ConfirmDialog
        open={Boolean(removing)}
        title={removing ? `Delete “${removing.name}”?` : ""}
        message="It is removed from the website after the next rebuild."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={async () => {
          try {
            await api.announcements.remove(removing.id);
            notify("Announcement deleted.");
            reload();
          } catch (err) {
            notify(err.message, "error");
          } finally {
            setRemoving(null);
          }
        }}
        onCancel={() => setRemoving(null)}
      />
    </BuilderLookups>
  );
}

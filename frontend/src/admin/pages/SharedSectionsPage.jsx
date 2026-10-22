import { Blocks, Link2, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BuilderLookups } from "../components/builder/BuilderLookups";
import { errorText } from "../components/builder/draft";
import { useBuilderLookups } from "../components/builder/lookups";
import { LinkField, SectionFields } from "../components/builder/SectionFields";
import { DesignControls } from "../components/builder/StyleControls";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const STYLES = [
  { value: "primary", label: "Sage (primary)" },
  { value: "secondary", label: "Charcoal" },
  { value: "outline", label: "Outline" },
  { value: "light", label: "Light" },
];

function UsageList({ usage }) {
  if (!usage?.length) return <p className="text-sm text-muted">Not used on any page yet.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {usage.map((u) => (
        <li key={`${u.type}-${u.id}`}>
          {u.title} {u.path && <span className="text-muted">({u.path})</span>}
          {u.live && (
            <span className="ml-1 rounded-full bg-sage-100 px-2 text-xs text-sage-800">live</span>
          )}
          {u.type === "group" && <span className="ml-1 text-xs text-muted">(group)</span>}
        </li>
      ))}
    </ul>
  );
}

function SharedEditor({ types, initial, onClose, onSaved }) {
  const api = useAdminApi();
  const { reload } = useBuilderLookups();
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const type = types.find((t) => t.type === form.section_type);
  const live = initial.live_pages ?? 0;

  const save = async (propagate) => {
    setAsk(false);
    setBusy(true);
    setErrors({});
    const body = {
      name: form.name,
      description: form.description ?? null,
      variant: form.variant,
      content: form.content,
      design: form.design,
    };
    try {
      const res = form.id
        ? await api.shared.update(form.id, { ...body, lock_version: form.lock_version, propagate })
        : await api.shared.create({ ...body, section_type: form.section_type });
      reload();
      onSaved(res.data);
    } catch (err) {
      setErrors(err.details ?? {});
      if (err.status !== 400) setErrors({ name: [err.message] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      size="lg"
      title={form.id ? `Edit shared section: ${initial.name}` : "New shared section"}
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => (form.id && live > 0 ? setAsk(true) : save(true))}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Name"
            required
            value={form.name}
            maxLength={120}
            error={errorText(errors.name)}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextField
            label="Description (optional)"
            value={form.description ?? ""}
            maxLength={300}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        {form.id && (
          <section aria-label="Where it is used" className="rounded-lg bg-cream p-3">
            <h3 className="mb-1 font-sans text-sm font-semibold">Used on</h3>
            <UsageList usage={initial.usage} />
          </section>
        )}
        {type ? (
          <>
            <SectionFields
              type={type}
              section={form}
              errors={errors}
              disabled={busy}
              onChange={(next) =>
                setForm({ ...form, variant: next.variant, content: next.content })
              }
            />
            {type.design.length > 0 && (
              <details className="rounded-lg border border-charcoal/10 p-3" open>
                <summary className="cursor-pointer text-sm font-semibold">Appearance</summary>
                <div className="mt-3">
                  <DesignControls
                    type={type}
                    design={form.design ?? {}}
                    errors={errors}
                    onChange={(design) => setForm({ ...form, design })}
                  />
                </div>
              </details>
            )}
          </>
        ) : (
          <p className="text-muted">Loading section fields…</p>
        )}
      </div>
      <Modal
        open={ask}
        title="Update the pages that use it?"
        onClose={() => setAsk(false)}
        footer={
          <>
            <Button variant="outline" onClick={() => save(false)}>
              Keep those pages unchanged
            </Button>
            <Button onClick={() => save(true)}>Update all {live} live page(s)</Button>
          </>
        }
      >
        <p className="text-sm">
          This shared section is live on {live} page(s). Update them all (a site rebuild is queued),
          or keep those pages exactly as they are: they get their own copy of the current version
          and only new uses get your changes.
        </p>
      </Modal>
    </Modal>
  );
}

function CtaForm({ initial, onClose, onSaved }) {
  const api = useAdminApi();
  const [form, setForm] = useState({
    name: "",
    label: "",
    url: "",
    style: "primary",
    description: "",
    ...initial,
  });
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    try {
      const body = {
        name: form.name,
        label: form.label,
        url: form.url,
        style: form.style,
        description: form.description || null,
      };
      const res = initial.id
        ? await api.ctas.update(initial.id, body)
        : await api.ctas.create(body);
      onSaved(res.data);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      title={initial.id ? "Edit call to action" : "New call to action"}
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="cta-form">
            Save
          </Button>
        </>
      }
    >
      <form id="cta-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Name"
          required
          value={form.name}
          maxLength={120}
          error={fieldError(error, "name")}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          hint="e.g. Subscribe to The Positive Reset"
        />
        <TextField
          label="Button text"
          required
          value={form.label}
          maxLength={60}
          error={fieldError(error, "label")}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
        />
        <LinkField
          label="Link"
          value={form.url}
          error={fieldError(error, "url")}
          onChange={(url) => setForm({ ...form, url })}
        />
        <SelectField
          label="Default style"
          value={form.style}
          options={STYLES}
          onChange={(e) => setForm({ ...form, style: e.target.value })}
        />
        <TextField
          className="sm:col-span-2"
          label="Note (optional)"
          value={form.description ?? ""}
          maxLength={300}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </form>
    </Modal>
  );
}

function SharedTab({ canManage }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, loading, error, reload } = useAdminQuery(() => api.shared.list(), []);
  const [types, setTypes] = useState([]);
  const [editing, setEditing] = useState(null);
  const [choosing, setChoosing] = useState(false);
  const [removing, setRemoving] = useState(null);
  useEffect(() => {
    api.pages
      .sectionTypes()
      .then((res) => setTypes(res.data))
      .catch(() => {});
  }, [api]);
  const shareable = types.filter((t) => !["hero", "page_header"].includes(t.type));

  if (error) return <ErrorState title="We couldn't load shared sections" onRetry={reload} />;
  return (
    <>
      {canManage && (
        <Button className="mb-4" onClick={() => setChoosing(true)}>
          <Plus aria-hidden />
          New shared section
        </Button>
      )}
      <DataTable
        caption="Shared sections"
        rows={data}
        loading={loading}
        empty={{
          icon: Blocks,
          title: "No shared sections yet",
          description: "Shared sections are edited once and reused on many pages.",
        }}
        columns={[
          {
            key: "name",
            header: "Shared section",
            render: (s) => (
              <div>
                <p className="flex items-center gap-1.5 font-medium">
                  <Link2 aria-hidden className="size-4 text-sage-700" />
                  {s.name}
                </p>
                <p className="text-xs text-muted">{s.type_label}</p>
              </div>
            ),
          },
          {
            key: "usage",
            header: "Used on",
            render: (s) => `${s.usage.length} place(s), ${s.live_pages} live`,
          },
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            render: (s) =>
              canManage && (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Edit ${s.name}`}
                    onClick={() => setEditing(s)}
                  >
                    <Pencil aria-hidden />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${s.name}`}
                    onClick={() => setRemoving(s)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              ),
          },
        ]}
      />
      <Modal
        open={choosing}
        title="Choose a section type"
        onClose={() => setChoosing(false)}
        size="lg"
      >
        <ul className="grid gap-2 sm:grid-cols-2">
          {shareable.map((t) => (
            <li key={t.type}>
              <button
                type="button"
                onClick={() => {
                  setChoosing(false);
                  setEditing({ name: "", section_type: t.type, ...structuredClone(t.defaults) });
                }}
                className="h-full w-full rounded-xl border border-charcoal/10 bg-white p-3 text-left hover:border-sage-600"
              >
                <span className="block font-medium">{t.label}</span>
                <span className="block text-sm text-muted">{t.description}</span>
              </button>
            </li>
          ))}
        </ul>
      </Modal>
      {editing && (
        <SharedEditor
          types={types}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            reload();
            notify(
              saved.detached
                ? `Saved. ${saved.detached} page(s) kept their previous version.`
                : saved.live_pages
                  ? "Saved. Live pages update after the queued rebuild."
                  : "Shared section saved.",
            );
          }}
        />
      )}
      <ConfirmDialog
        open={Boolean(removing)}
        title={removing ? `Delete “${removing.name}”?` : ""}
        message={
          removing?.usage.length
            ? "It is still in use, so it cannot be deleted. Remove it from those pages first."
            : "This cannot be undone."
        }
        confirmLabel="Delete"
        tone="danger"
        onConfirm={async () => {
          try {
            await api.shared.remove(removing.id);
            notify("Shared section deleted.");
            reload();
          } catch (err) {
            notify(err.message, "error");
          } finally {
            setRemoving(null);
          }
        }}
        onCancel={() => setRemoving(null)}
      />
    </>
  );
}

function CtaTab({ canManage }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, loading, error, reload } = useAdminQuery(() => api.ctas.list(), []);
  const [editing, setEditing] = useState(null);
  if (error) return <ErrorState title="We couldn't load calls to action" onRetry={reload} />;
  return (
    <>
      {canManage && (
        <Button className="mb-4" onClick={() => setEditing({})}>
          <Plus aria-hidden />
          New call to action
        </Button>
      )}
      <DataTable
        caption="Calls to action"
        rows={data}
        loading={loading}
        empty={{
          icon: Link2,
          title: "No saved calls to action",
          description: "Write a button once (text and link) and reuse it in sections.",
        }}
        columns={[
          {
            key: "name",
            header: "Name",
            render: (c) => <span className="font-medium">{c.name}</span>,
          },
          { key: "label", header: "Button", render: (c) => `“${c.label}” → ${c.url}` },
          { key: "usage", header: "Used in", render: (c) => `${c.usage.length} place(s)` },
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            render: (c) =>
              canManage && (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Edit ${c.name}`}
                    onClick={() => setEditing(c)}
                  >
                    <Pencil aria-hidden />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${c.name}`}
                    onClick={async () => {
                      try {
                        await api.ctas.remove(c.id);
                        notify("Call to action deleted.");
                        reload();
                      } catch (err) {
                        notify(err.message, "error");
                      }
                    }}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              ),
          },
        ]}
      />
      {editing && (
        <CtaForm
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
            notify("Call to action saved. Sections using it update after the next rebuild.");
          }}
        />
      )}
    </>
  );
}

export function SharedSectionsPage() {
  const { can } = usePermissions();
  const [tab, setTab] = useState("sections");
  const canManage = can("reusable_sections.manage");
  return (
    <BuilderLookups>
      <AdminPageHeader
        title="Shared sections"
        description="Edit once, reuse everywhere: shared sections and saved calls to action."
        breadcrumbs={[{ label: "Shared sections" }]}
      />
      <div
        role="tablist"
        aria-label="Shared content"
        className="mb-4 flex gap-1 border-b border-charcoal/10"
      >
        {[
          ["sections", "Shared sections"],
          ["ctas", "Calls to action"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium",
              tab === key
                ? "border-sage-700 text-sage-800"
                : "border-transparent text-muted hover:text-charcoal",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "sections" ? <SharedTab canManage={canManage} /> : <CtaTab canManage={canManage} />}
    </BuilderLookups>
  );
}

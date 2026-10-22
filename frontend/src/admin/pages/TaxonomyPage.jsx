import { Archive, Pencil, Plus, Shuffle, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { fieldError } from "../components/fieldError";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const ICONS = [
  "sun",
  "sprout",
  "gem",
  "sunrise",
  "heart-handshake",
  "calendar-check",
  "flame",
  "leaf",
];

const CONFIG = {
  topics: {
    title: "Topics",
    singular: "topic",
    description: "Organise articles into the themes readers browse on the website.",
    nameField: "name",
    reassign: true,
    archiveStatus: "archived",
    fields: [
      { name: "name", label: "Name", required: true },
      { name: "slug", label: "Slug", hint: "Leave empty to generate from the name." },
      { name: "description", label: "Short description", type: "textarea" },
      { name: "intro", label: "Topic page introduction", type: "textarea", rows: 4 },
      {
        name: "icon",
        label: "Icon",
        type: "select",
        options: ICONS.map((i) => ({ value: i, label: i })),
      },
      { name: "display_order", label: "Display order", type: "number" },
      {
        name: "status",
        label: "Visibility",
        type: "select",
        options: [
          { value: "active", label: "Active (public)" },
          { value: "hidden", label: "Hidden" },
          { value: "archived", label: "Archived" },
        ],
      },
      { name: "featured", label: "Feature on the homepage", type: "checkbox" },
      { name: "seo_title", label: "SEO title" },
      { name: "seo_description", label: "SEO description", type: "textarea" },
    ],
    defaults: {
      name: "",
      slug: "",
      description: "",
      intro: "",
      icon: "sun",
      display_order: 0,
      status: "active",
      featured: false,
      seo_title: "",
      seo_description: "",
    },
  },
  authors: {
    title: "Authors",
    singular: "author",
    description: "People and teams credited on articles.",
    nameField: "display_name",
    reassign: true,
    archiveStatus: "archived",
    fields: [
      { name: "display_name", label: "Display name", required: true },
      { name: "slug", label: "Slug", hint: "Leave empty to generate from the name." },
      { name: "bio", label: "Short biography", type: "textarea", rows: 4 },
      {
        name: "status",
        label: "Status",
        type: "select",
        options: [
          { value: "active", label: "Active" },
          { value: "archived", label: "Archived" },
        ],
      },
    ],
    defaults: { display_name: "", slug: "", bio: "", status: "active" },
  },
  tags: {
    title: "Tags",
    singular: "tag",
    description: "Keywords that connect related articles.",
    nameField: "name",
    reassign: false,
    fields: [
      { name: "name", label: "Name", required: true },
      { name: "slug", label: "Slug", hint: "Leave empty to generate from the name." },
      { name: "description", label: "Description", type: "textarea" },
    ],
    defaults: { name: "", slug: "", description: "" },
  },
};

function FormFields({ fields, form, setForm, error }) {
  return fields.map((f) => {
    const common = {
      label: f.label,
      hint: f.hint,
      required: f.required,
      error: fieldError(error, f.name),
    };
    const onChange = (e) =>
      setForm((v) => ({
        ...v,
        [f.name]:
          f.type === "checkbox"
            ? e.target.checked
            : f.type === "number"
              ? Number(e.target.value)
              : e.target.value,
      }));
    if (f.type === "textarea")
      return (
        <TextAreaField
          key={f.name}
          {...common}
          rows={f.rows ?? 3}
          value={form[f.name] ?? ""}
          onChange={onChange}
        />
      );
    if (f.type === "select")
      return (
        <SelectField
          key={f.name}
          {...common}
          options={f.options}
          value={form[f.name]}
          onChange={onChange}
        />
      );
    if (f.type === "checkbox")
      return (
        <CheckboxField
          key={f.name}
          label={f.label}
          checked={Boolean(form[f.name])}
          onChange={onChange}
        />
      );
    return (
      <TextField
        key={f.name}
        {...common}
        type={f.type === "number" ? "number" : "text"}
        value={form[f.name] ?? ""}
        onChange={onChange}
      />
    );
  });
}

/** Shared CRUD screen for topics, authors and tags. */
export function TaxonomyPage({ kind }) {
  const config = CONFIG[kind];
  const api = useAdminApi()[kind];
  const notify = useNotify();
  const { can } = usePermissions();
  const canWrite = can("content.write");
  const { data, loading, error, reload } = useAdminQuery(() => api.list(), [kind]);

  const [editing, setEditing] = useState(null); // { id?, form }
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [reassigning, setReassigning] = useState(null);
  const [target, setTarget] = useState("");

  const openForm = (item) => {
    setFormError(null);
    setEditing({
      id: item?.id,
      form: item
        ? Object.fromEntries(
            Object.keys(config.defaults).map((k) => [k, item[k] ?? config.defaults[k]]),
          )
        : { ...config.defaults },
    });
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = { ...editing.form };
      if (!payload.slug) delete payload.slug;
      if (editing.id) await api.update(editing.id, payload);
      else await api.create(payload);
      notify(`${config.singular[0].toUpperCase()}${config.singular.slice(1)} saved.`);
      setEditing(null);
      reload();
    } catch (err) {
      setFormError(err);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await api.remove(deleting.id);
      notify(`Deleted ${deleting[config.nameField]}.`);
      reload();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setDeleting(null);
    }
  };

  const archive = async (item) => {
    try {
      await api.update(item.id, { status: config.archiveStatus });
      notify(`Archived ${item[config.nameField]}.`);
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };

  const doReassign = async () => {
    setBusy(true);
    try {
      const res = await api.reassign(reassigning.id, Number(target));
      notify(`Moved ${res.data.moved} article link(s).`);
      setReassigning(null);
      reload();
    } catch (err) {
      notify(err.details?.target_id?.[0] ?? err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    {
      key: "name",
      header: "Name",
      render: (item) => (
        <div>
          <p className="font-medium">{item[config.nameField]}</p>
          <p className="text-xs text-muted">/{item.slug}</p>
        </div>
      ),
    },
    ...(config.archiveStatus
      ? [{ key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> }]
      : []),
    { key: "article_count", header: "Articles" },
    ...(canWrite
      ? [
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            className: "text-right",
            render: (item) => (
              <div className="flex justify-end gap-1">
                <RowButton
                  label={`Edit ${item[config.nameField]}`}
                  icon={Pencil}
                  onClick={() => openForm(item)}
                />
                {config.reassign && item.article_count > 0 && (
                  <RowButton
                    label={`Reassign articles from ${item[config.nameField]}`}
                    icon={Shuffle}
                    onClick={() => {
                      setTarget("");
                      setReassigning(item);
                    }}
                  />
                )}
                {config.archiveStatus && item.status !== config.archiveStatus && (
                  <RowButton
                    label={`Archive ${item[config.nameField]}`}
                    icon={Archive}
                    onClick={() => archive(item)}
                  />
                )}
                <RowButton
                  label={`Delete ${item[config.nameField]}`}
                  icon={Trash2}
                  onClick={() => setDeleting(item)}
                  danger
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <>
      <AdminPageHeader
        title={config.title}
        description={config.description}
        breadcrumbs={[{ label: config.title }]}
        actions={
          canWrite && (
            <Button size="sm" onClick={() => openForm(null)}>
              <Plus aria-hidden />
              New {config.singular}
            </Button>
          )
        }
      />
      {error ? (
        <ErrorState title={`We couldn't load ${kind}`} onRetry={reload} />
      ) : (
        <DataTable
          caption={config.title}
          columns={columns}
          rows={data}
          loading={loading}
          empty={{
            title: `No ${kind} yet`,
            description: `Create the first ${config.singular} to get started.`,
          }}
        />
      )}

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing?.id ? `Edit ${config.singular}` : `New ${config.singular}`}
        footer={
          <>
            <Button variant="outline" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button type="submit" form="taxonomy-form" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        {editing && (
          <form id="taxonomy-form" onSubmit={submit} className="space-y-4">
            {formError && !formError.details && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
                {formError.message}
              </p>
            )}
            <FormFields
              fields={config.fields}
              form={editing.form}
              setForm={(fn) => setEditing((e) => ({ ...e, form: fn(e.form) }))}
              error={formError}
            />
          </form>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title={`Delete ${deleting?.[config.nameField] ?? ""}?`}
        message={
          deleting?.article_count
            ? `This ${config.singular} is used by ${deleting.article_count} article(s) and cannot be deleted. ${config.reassign ? "Reassign the articles or archive it instead." : "Remove it from those articles first."}`
            : "This cannot be undone."
        }
        confirmLabel="Delete"
        tone="danger"
        busy={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={doDelete}
      />

      <Modal
        open={Boolean(reassigning)}
        onClose={() => setReassigning(null)}
        title={`Reassign articles from ${reassigning?.[config.nameField] ?? ""}`}
        size="sm"
        footer={
          <>
            <Button variant="outline" onClick={() => setReassigning(null)}>
              Cancel
            </Button>
            <Button onClick={doReassign} disabled={!target || busy}>
              Reassign
            </Button>
          </>
        }
      >
        <SelectField
          label={`Move articles to`}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          options={[
            { value: "", label: "— Select —" },
            ...(data ?? [])
              .filter((i) => reassigning && i.id !== reassigning.id && i.status !== "archived")
              .map((i) => ({ value: String(i.id), label: i[config.nameField] })),
          ]}
        />
      </Modal>
    </>
  );
}

function RowButton({ label, icon: Icon, danger, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={
        danger
          ? "rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-800"
          : "rounded p-1.5 text-muted hover:bg-beige hover:text-charcoal"
      }
      {...props}
    >
      <Icon aria-hidden className="size-4" />
    </button>
  );
}

import { Copy, LayoutTemplate, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const slugify = (value) =>
  value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);

function CreatePageDialog({ open, onClose, pages }) {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({ title: "", slug: "", template: "landing", parent_id: "" });
  const [slugEdited, setSlugEdited] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || templates.length) return;
    api.pages
      .templates()
      .then((res) => setTemplates(res.data))
      .catch(() => {});
  }, [api, open, templates.length]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.pages.create({
        title: form.title,
        slug: form.slug || undefined,
        template: form.template,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
      });
      notify("Page created as a draft. Nothing is public until you publish it.");
      navigate(`/admin/pages/${res.data.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Create a page"
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-page" disabled={busy || !form.title.trim()}>
            Create draft
          </Button>
        </>
      }
    >
      <form id="create-page" onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Title"
            required
            value={form.title}
            maxLength={200}
            error={fieldError(error, "title")}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                title: e.target.value,
                slug: slugEdited ? f.slug : slugify(e.target.value),
              }))
            }
          />
          <TextField
            label="Address (slug)"
            value={form.slug}
            maxLength={120}
            error={fieldError(error, "slug")}
            hint={form.slug ? `/${form.slug}` : "Filled in from the title."}
            onChange={(e) => {
              setSlugEdited(true);
              setForm((f) => ({ ...f, slug: e.target.value.toLowerCase() }));
            }}
          />
          <SelectField
            label="Parent page (optional)"
            className="sm:col-span-2"
            value={form.parent_id}
            error={fieldError(error, "parent_id")}
            options={[
              { value: "", label: "None (top level)" },
              ...pages
                .filter((p) => !p.is_home)
                .map((p) => ({ value: p.id, label: `${p.title} (${p.path})` })),
            ]}
            onChange={(e) => setForm((f) => ({ ...f, parent_id: e.target.value }))}
          />
        </div>
        <fieldset>
          <legend className="text-sm font-semibold text-charcoal">Template</legend>
          <p className="text-sm text-muted">
            Starter sections only: you can change everything afterwards.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {templates.map((t) => (
              <label
                key={t.key}
                className={cn(
                  "cursor-pointer rounded-xl border p-3 has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-sage-600/40",
                  form.template === t.key
                    ? "border-sage-700 bg-sage-50"
                    : "border-charcoal/10 bg-white",
                )}
              >
                <input
                  type="radio"
                  name="template"
                  value={t.key}
                  checked={form.template === t.key}
                  onChange={() => setForm((f) => ({ ...f, template: t.key }))}
                  className="sr-only"
                />
                <span className="block font-medium text-charcoal">{t.label}</span>
                <span className="mt-1 block text-sm text-muted">{t.description}</span>
                <span className="mt-1 block text-xs text-muted">{t.sections.join(" · ")}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}

export function PagesPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const { data, loading, error, reload } = useAdminQuery(
    () => api.pages.list({ status: status || undefined, q: q || undefined }),
    [status, q],
  );
  const canCreate = can("pages.create");

  const duplicate = async (page) => {
    try {
      const res = await api.pages.duplicate(page.id);
      notify("Copy created as a draft.");
      navigate(`/admin/pages/${res.data.id}`);
    } catch (err) {
      notify(err.message, "error");
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Pages"
        description="Landing pages, campaign pages and other website pages built from sections."
        breadcrumbs={[{ label: "Pages" }]}
        actions={
          canCreate && (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden />
              Create page
            </Button>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <TextField
          label="Search"
          type="search"
          value={q}
          placeholder="Title or address"
          onChange={(e) => setQ(e.target.value)}
        />
        <SelectField
          label="Status"
          value={status}
          options={[
            { value: "", label: "Drafts and published" },
            { value: "draft", label: "Drafts" },
            { value: "published", label: "Published" },
            { value: "archived", label: "Archived" },
          ]}
          onChange={(e) => setStatus(e.target.value)}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load pages" onRetry={reload} />
      ) : (
        <DataTable
          caption="Pages"
          rows={data}
          loading={loading}
          empty={{
            icon: LayoutTemplate,
            title: "No pages yet",
            description: canCreate
              ? "Create your first landing page from a template."
              : "No pages match.",
          }}
          columns={[
            {
              key: "title",
              header: "Page",
              render: (p) => (
                <div>
                  <Link
                    to={p.is_home ? "/admin/homepage" : `/admin/pages/${p.id}`}
                    className="font-medium hover:text-sage-700"
                  >
                    {p.title}
                  </Link>
                  <p className="text-xs text-muted">
                    {p.path}
                    {p.overrides_builtin && " · replaces a built-in page"}
                  </p>
                </div>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (p) => (
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={p.status} />
                  {p.status === "published" && p.has_unpublished_changes && (
                    <span className="rounded-full bg-gold-100 px-2 py-0.5 text-xs text-charcoal">
                      Unpublished changes
                    </span>
                  )}
                  {p.scheduled_at && (
                    <span className="rounded-full bg-sage-50 px-2 py-0.5 text-xs text-sage-800">
                      Scheduled
                    </span>
                  )}
                </div>
              ),
            },
            { key: "template", header: "Template", render: (p) => p.template_label },
            {
              key: "updated",
              header: "Last edited",
              render: (p) => (
                <span className="text-sm">
                  {formatDateTime(p.draft_updated_at ?? p.updated_at)}
                  {p.updated_by && (
                    <span className="block text-xs text-muted">{p.updated_by.name}</span>
                  )}
                </span>
              ),
            },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              render: (p) =>
                canCreate &&
                !p.is_home && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => duplicate(p)}
                    aria-label={`Duplicate ${p.title}`}
                  >
                    <Copy aria-hidden />
                    Duplicate
                  </Button>
                ),
            },
          ]}
        />
      )}
      <CreatePageDialog open={creating} onClose={() => setCreating(false)} pages={data ?? []} />
    </>
  );
}

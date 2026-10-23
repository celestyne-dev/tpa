import { Gift, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";

function EditDialog({ initial, products, onClose, onSaved }) {
  const api = useAdminApi();
  const [form, setForm] = useState({
    title: "",
    slug: "",
    description: "",
    product_id: "",
    status: "draft",
    newsletter_optin: "optional",
    optin_notice: "",
    link_ttl_hours: "",
    max_downloads: "",
    ...initial,
  });
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    const body = {
      title: form.title,
      slug: form.slug || undefined,
      description: form.description,
      product_id: Number(form.product_id) || null,
      status: form.status,
      newsletter_optin: form.newsletter_optin,
      optin_notice: form.optin_notice,
      link_ttl_hours: form.link_ttl_hours ? Number(form.link_ttl_hours) : null,
      max_downloads: form.max_downloads ? Number(form.max_downloads) : null,
    };
    try {
      if (initial?.id) await api.leadMagnets.update(initial.id, body);
      else await api.leadMagnets.create(body);
      onSaved();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={initial?.id ? `Edit “${initial.title}”` : "New lead magnet"}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="lead-magnet-form">
            Save
          </Button>
        </>
      }
    >
      <form id="lead-magnet-form" onSubmit={submit} className="grid gap-4">
        <TextField
          label="Title"
          required
          value={form.title}
          error={fieldError(error, "title")}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <TextField
          label="Address (slug)"
          value={form.slug}
          error={fieldError(error, "slug")}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
        />
        <TextAreaField
          label="Description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <SelectField
          label="Free product with the files"
          required
          value={String(form.product_id ?? "")}
          error={fieldError(error, "product_id")}
          hint="Create a free product with real files under Products first. Nothing is delivered without a real file."
          onChange={(e) => setForm({ ...form, product_id: e.target.value })}
          options={[
            { value: "", label: "Choose…" },
            ...products.map((p) => ({ value: String(p.id), label: p.title })),
          ]}
        />
        <SelectField
          label="Newsletter"
          value={form.newsletter_optin}
          onChange={(e) => setForm({ ...form, newsletter_optin: e.target.value })}
          options={[
            { value: "optional", label: "Optional (unticked checkbox) — recommended" },
            {
              value: "required",
              label: "Offered in exchange for subscribing (clear notice required)",
            },
          ]}
        />
        {form.newsletter_optin === "required" && (
          <TextAreaField
            label="Notice shown next to the form"
            required
            value={form.optin_notice}
            error={fieldError(error, "optin_notice")}
            hint="Say plainly that the resource comes with a subscription to The Positive Reset, and that people can unsubscribe at any time."
            onChange={(e) => setForm({ ...form, optin_notice: e.target.value })}
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Link valid for (hours)"
            type="number"
            value={form.link_ttl_hours ?? ""}
            hint="Empty uses the server default."
            onChange={(e) => setForm({ ...form, link_ttl_hours: e.target.value })}
          />
          <TextField
            label="Downloads per link"
            type="number"
            value={form.max_downloads ?? ""}
            hint="Empty uses the server default."
            onChange={(e) => setForm({ ...form, max_downloads: e.target.value })}
          />
        </div>
        <SelectField
          label="Status"
          value={form.status}
          error={fieldError(error, "status")}
          onChange={(e) => setForm({ ...form, status: e.target.value })}
          options={[
            { value: "draft", label: "Draft" },
            { value: "active", label: "Active" },
            { value: "archived", label: "Archived" },
          ]}
        />
        {error && !Object.keys(error.details ?? {}).length && (
          <p role="alert" className="text-sm text-red-800">
            {error.message}
          </p>
        )}
      </form>
    </Modal>
  );
}

export function LeadMagnetsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, error, loading, reload } = useAdminQuery(() => api.leadMagnets.list(), []);
  const products = useAdminQuery(() => api.products.list({ page_size: 100 }), []);
  const [editing, setEditing] = useState(null);
  const freeProducts = (products.data ?? []).filter((p) => p.pricing_model === "free" || p.is_free);
  return (
    <>
      <AdminPageHeader
        title="Lead magnets"
        description="Free resources delivered by secure, expiring email links. Connect them to signup sections in the page builder."
        breadcrumbs={[{ label: "Lead magnets" }]}
        actions={
          <Button onClick={() => setEditing({})}>
            <Plus aria-hidden className="size-4" /> New lead magnet
          </Button>
        }
      />
      {error ? (
        <ErrorState title="We couldn't load lead magnets" onRetry={reload} />
      ) : (
        <DataTable
          caption="Lead magnets"
          rows={data}
          loading={loading}
          empty={{ icon: Gift, title: "No lead magnets yet" }}
          columns={[
            {
              key: "title",
              header: "Resource",
              render: (m) => (
                <div>
                  <button
                    type="button"
                    className="font-medium hover:underline"
                    onClick={() => setEditing(m)}
                  >
                    {m.title}
                  </button>
                  <p className="text-xs text-muted">
                    {m.product_title} · {m.formats.join(", ") || "no files"}
                  </p>
                  {m.problems.length > 0 && (
                    <p className="text-xs text-red-800">{m.problems.join(" ")}</p>
                  )}
                </div>
              ),
            },
            { key: "status", header: "Status", render: (m) => <StatusBadge status={m.status} /> },
            {
              key: "optin",
              header: "Newsletter",
              render: (m) =>
                m.newsletter_optin === "required" ? "Required (notice shown)" : "Optional",
            },
            { key: "claims", header: "Requests", render: (m) => m.claims },
          ]}
        />
      )}
      {editing && (
        <EditDialog
          initial={editing.id ? editing : null}
          products={freeProducts}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            notify("Lead magnet saved.");
            reload();
          }}
        />
      )}
    </>
  );
}

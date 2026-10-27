import { BookOpenText, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
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

function accessLabel(item) {
  const kind = item.pricing_model === "free" ? "Free" : "Premium";
  const period = item.access_days ? `${item.access_days}-day access` : "Lifetime access";
  return `${kind} · ${period}`;
}

function CreateResourceDialog({ open, onClose, types }) {
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const [form, setForm] = useState({ title: "", product_type: types[0]?.value ?? "ebook" });
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const res = await api.products.create(form);
      notify("Resource created as a draft. Add files, a price or free access, then publish.");
      navigate(`/admin/products/${res.data.id}`);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New resource"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-resource" disabled={!form.title.trim()}>
            Create draft
          </Button>
        </>
      }
    >
      <form id="create-resource" onSubmit={submit} className="space-y-4">
        <TextField
          label="Title"
          required
          value={form.title}
          error={fieldError(error, "title")}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <SelectField
          label="Resource type"
          value={form.product_type}
          error={fieldError(error, "product_type")}
          onChange={(e) => setForm({ ...form, product_type: e.target.value })}
          options={types.map((t) => ({ value: t.value, label: t.label }))}
        />
      </form>
    </Modal>
  );
}

/**
 * Premium resources: written downloads (eBooks, workbooks, planners, templates …). They are
 * products underneath, so prices, checkout, guest purchases and entitlements are shared with
 * the shop; this view focuses on what matters for resources.
 */
export function ResourcesPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ q: "", type: "", access: "", status: "" });
  const [creating, setCreating] = useState(false);
  const { data, error, loading, reload } = useAdminQuery(
    () =>
      api.products.list({
        group: "resources",
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      }),
    [filters.q, filters.type, filters.access, filters.status],
  );
  const options = useAdminQuery(() => api.products.options(), []);
  const types = (options.data?.types ?? []).filter((t) => t.available && t.delivery === "files");
  const typeLabel = Object.fromEntries(types.map((t) => [t.value, t.label]));

  return (
    <>
      <AdminPageHeader
        title="Premium resources"
        description="Written resources buyers download: eBooks, workbooks, planners, worksheets, guides, templates, checklists and learning packs. Files stay in private storage and are delivered only through checked, short-lived links."
        breadcrumbs={[{ label: "Premium resources" }]}
        actions={
          can("products.create") && (
            <Button onClick={() => setCreating(true)} disabled={!types.length}>
              <Plus aria-hidden /> New resource
            </Button>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextField
          label="Search"
          type="search"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })}
        />
        <SelectField
          label="Type"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
          options={[
            { value: "", label: "All types" },
            ...types.map((t) => ({ value: t.value, label: t.label })),
          ]}
        />
        <SelectField
          label="Access"
          value={filters.access}
          onChange={(e) => setFilters({ ...filters, access: e.target.value })}
          options={[
            { value: "", label: "Free and premium" },
            { value: "free", label: "Free" },
            { value: "premium", label: "Premium (paid)" },
          ]}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          options={[
            { value: "", label: "All (not archived)" },
            { value: "draft", label: "Drafts" },
            { value: "published", label: "Published" },
            { value: "archived", label: "Archived" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load resources" onRetry={reload} />
      ) : (
        <DataTable
          caption="Premium resources"
          loading={loading}
          rows={data}
          empty={{
            icon: BookOpenText,
            title: "No resources yet",
            description: "Create a resource, upload its files and publish it.",
          }}
          columns={[
            {
              key: "title",
              header: "Resource",
              render: (r) => (
                <Link to={`/admin/products/${r.id}`} className="font-medium hover:underline">
                  {r.title}
                  <span className="block text-xs font-normal text-muted">
                    {typeLabel[r.product_type] ?? r.product_type}
                  </span>
                </Link>
              ),
            },
            { key: "access", header: "Access", render: accessLabel },
            {
              key: "files",
              header: "Files",
              render: (r) =>
                r.file_count
                  ? `${r.file_count} · ${r.formats.map((f) => f.toUpperCase()).join(", ")}`
                  : "No files yet",
            },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <span className="flex flex-wrap gap-1">
                  <StatusBadge status={r.status} />
                  {r.purchasable && <StatusBadge status="on sale" />}
                </span>
              ),
            },
            { key: "updated", header: "Updated", render: (r) => formatDateTime(r.updated_at) },
          ]}
        />
      )}
      {creating && types.length > 0 && (
        <CreateResourceDialog open onClose={() => setCreating(false)} types={types} />
      )}
    </>
  );
}

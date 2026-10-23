import { AlertTriangle, Package, Plus } from "lucide-react";
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

function CreateProductDialog({ open, onClose, types, bundle }) {
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const [form, setForm] = useState({ title: "", product_type: bundle ? "bundle" : "ebook" });
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const res = await api.products.create(form);
      notify("Product created as a draft. It is not public until you publish it.");
      navigate(`/admin/products/${res.data.id}`);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={bundle ? "New bundle" : "New product"}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-product" disabled={!form.title.trim()}>
            Create draft
          </Button>
        </>
      }
    >
      <form id="create-product" onSubmit={submit} className="space-y-4">
        <TextField
          label="Title"
          required
          value={form.title}
          error={fieldError(error, "title")}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <SelectField
          label="Product type"
          value={form.product_type}
          error={fieldError(error, "product_type")}
          onChange={(e) => setForm({ ...form, product_type: e.target.value })}
          options={types.map((t) => ({
            value: t.value,
            label: t.available ? t.label : `${t.label} (planned)`,
            disabled: !t.available,
          }))}
        />
      </form>
    </Modal>
  );
}

export function ProductsPage({ bundles = false }) {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ q: "", status: "", issues: "" });
  const [creating, setCreating] = useState(false);
  const params = { ...filters, ...(bundles && { type: "bundle" }) };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.products.list(Object.fromEntries(Object.entries(params).filter(([, v]) => v))),
    [filters.q, filters.status, filters.issues, bundles],
  );
  const options = useAdminQuery(() => api.products.options(), []);
  const types = options.data?.types ?? [];
  return (
    <>
      <AdminPageHeader
        title={bundles ? "Bundles" : "Products"}
        description={
          bundles
            ? "Bundles sell several products together. Buyers get every included product's files."
            : "Digital products: drafts are private until published; only products marked on sale with files and an approved price can be bought."
        }
        breadcrumbs={[{ label: bundles ? "Bundles" : "Products" }]}
        actions={
          can("products.create") && (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> {bundles ? "New bundle" : "New product"}
            </Button>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <TextField
          label="Search"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })}
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
        <SelectField
          label="Problems"
          value={filters.issues}
          onChange={(e) => setFilters({ ...filters, issues: e.target.value })}
          options={[
            { value: "", label: "All products" },
            { value: "1", label: "Missing files or invalid setup" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load products" onRetry={reload} />
      ) : (
        <DataTable
          caption={bundles ? "Bundles" : "Products"}
          rows={data}
          loading={loading}
          empty={{
            icon: Package,
            title: "No products yet",
            description: "Create your first product.",
          }}
          columns={[
            {
              key: "title",
              header: "Product",
              render: (p) => (
                <div>
                  <Link to={`/admin/products/${p.id}`} className="font-medium hover:underline">
                    {p.title}
                  </Link>
                  <p className="text-xs text-muted">
                    {types.find((t) => t.value === p.product_type)?.label ?? p.product_type} ·
                    /shop/
                    {p.published_slug ?? p.slug}
                  </p>
                </div>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (p) => (
                <div className="flex flex-wrap gap-1">
                  <StatusBadge status={p.status} />
                  {p.status === "published" && (
                    <StatusBadge
                      status={
                        p.purchasable
                          ? "on sale"
                          : p.sales_status === "on_sale"
                            ? "blocked"
                            : "coming soon"
                      }
                    />
                  )}
                  {p.has_unpublished_changes && <StatusBadge status="unpublished changes" />}
                </div>
              ),
            },
            {
              key: "price",
              header: "Price",
              render: (p) =>
                p.pricing_model === "free"
                  ? "Free"
                  : p.prices.length
                    ? p.prices.map((x) => x.formatted).join(" · ")
                    : "—",
            },
            {
              key: "issues",
              header: "Setup",
              render: (p) =>
                p.issues.length ? (
                  <span
                    className="inline-flex items-center gap-1 text-sm text-gold-700"
                    title={p.issues.join("\n")}
                  >
                    <AlertTriangle aria-hidden className="size-4" /> {p.issues[0]}
                    {p.issues.length > 1 ? ` (+${p.issues.length - 1})` : ""}
                  </span>
                ) : (
                  <span className="text-sm text-sage-800">Ready</span>
                ),
            },
            { key: "updated", header: "Updated", render: (p) => formatDateTime(p.updated_at) },
          ]}
        />
      )}
      {creating && (
        <CreateProductDialog
          open
          onClose={() => setCreating(false)}
          types={types}
          bundle={bundles}
        />
      )}
    </>
  );
}

export function BundlesPage() {
  return <ProductsPage bundles />;
}

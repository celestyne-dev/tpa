import { Layers, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { CheckboxField, TextAreaField, TextField } from "../components/Fields";
import { ImageChooser } from "../components/media/ImageChooser";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

function EditDialog({ kind, initial, products, onClose, onSaved }) {
  const api = useAdminApi();
  const [form, setForm] = useState({
    name: "",
    slug: "",
    description: "",
    is_active: true,
    is_featured: false,
    product_ids: [],
    cover_media_id: null,
    ...initial,
  });
  const [error, setError] = useState(null);
  const collection = kind === "collection";
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    const body = {
      name: form.name,
      slug: form.slug || undefined,
      description: form.description,
      is_active: form.is_active,
    };
    if (collection)
      Object.assign(body, {
        is_featured: form.is_featured,
        product_ids: form.product_ids,
        cover_media_id: form.cover_media_id,
      });
    const target = collection ? api.productCollections : api.productCategories;
    try {
      if (initial?.id) await target.update(initial.id, body);
      else await target.create(body);
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
      title={`${initial?.id ? "Edit" : "New"} ${collection ? "collection" : "category"}`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="taxonomy-form">
            Save
          </Button>
        </>
      }
    >
      <form id="taxonomy-form" onSubmit={submit} className="grid gap-4">
        <TextField
          label="Name"
          required
          value={form.name}
          error={fieldError(error, "name")}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <TextField
          label="Address (slug)"
          value={form.slug}
          hint={collection ? `/shop/collections/${form.slug || "…"}` : "Used in shop filters."}
          error={fieldError(error, "slug")}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
        />
        <TextAreaField
          label="Description"
          rows={3}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <CheckboxField
          label="Active (shown on the website)"
          checked={form.is_active}
          onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
        />
        {collection && (
          <>
            <CheckboxField
              label="Featured collection"
              checked={form.is_featured}
              onChange={(e) => setForm({ ...form, is_featured: e.target.checked })}
            />
            <ImageChooser
              label="collection image"
              mediaId={form.cover_media_id}
              onChange={(v) => setForm({ ...form, cover_media_id: v })}
            />
            <fieldset>
              <legend className="text-sm font-medium">
                Products (only published ones appear publicly)
              </legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {products.map((p) => (
                  <CheckboxField
                    key={p.id}
                    label={`${p.title}${p.status === "published" ? "" : ` (${p.status})`}`}
                    checked={form.product_ids.includes(p.id)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        product_ids: e.target.checked
                          ? [...form.product_ids, p.id]
                          : form.product_ids.filter((x) => x !== p.id),
                      })
                    }
                  />
                ))}
              </div>
            </fieldset>
          </>
        )}
      </form>
    </Modal>
  );
}

export function ProductCollectionsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const categories = useAdminQuery(() => api.productCategories.list(), []);
  const collections = useAdminQuery(() => api.productCollections.list(), []);
  const options = useAdminQuery(() => api.products.options(), []);
  const [editing, setEditing] = useState(null);
  const editable = can("products.edit");
  const remove = async (kind, item) => {
    try {
      await (kind === "collection" ? api.productCollections : api.productCategories).remove(
        item.id,
      );
      notify("Deleted.");
      (kind === "collection" ? collections : categories).reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const actions = (kind) => ({
    key: "actions",
    header: <span className="sr-only">Actions</span>,
    render: (item) =>
      editable && (
        <div className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Edit ${item.name}`}
            onClick={() => setEditing({ kind, item })}
          >
            <Pencil aria-hidden />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Delete ${item.name}`}
            onClick={() => remove(kind, item)}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      ),
  });
  return (
    <>
      <AdminPageHeader
        title="Categories & Collections"
        description="Categories filter the shop. Collections are curated sets with their own page and can be featured on the homepage."
        breadcrumbs={[{ label: "Categories & Collections" }]}
      />
      <section className="mb-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-medium">Collections</h2>
          {editable && (
            <Button size="sm" onClick={() => setEditing({ kind: "collection", item: null })}>
              <Plus aria-hidden /> New collection
            </Button>
          )}
        </div>
        {collections.error ? (
          <ErrorState onRetry={collections.reload} title="We couldn't load collections" />
        ) : (
          <DataTable
            caption="Collections"
            rows={collections.data}
            loading={collections.loading}
            empty={{ icon: Layers, title: "No collections yet" }}
            columns={[
              {
                key: "name",
                header: "Collection",
                render: (c) => <span className="font-medium">{c.name}</span>,
              },
              { key: "slug", header: "Address", render: (c) => `/shop/collections/${c.slug}` },
              {
                key: "products",
                header: "Products",
                render: (c) => c.products.map((p) => p.title).join(", ") || "—",
              },
              {
                key: "active",
                header: "Status",
                render: (c) =>
                  c.is_active ? (c.is_featured ? "Active · featured" : "Active") : "Hidden",
              },
              actions("collection"),
            ]}
          />
        )}
      </section>
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-medium">Categories</h2>
          {editable && (
            <Button size="sm" onClick={() => setEditing({ kind: "category", item: null })}>
              <Plus aria-hidden /> New category
            </Button>
          )}
        </div>
        {categories.error ? (
          <ErrorState onRetry={categories.reload} title="We couldn't load categories" />
        ) : (
          <DataTable
            caption="Categories"
            rows={categories.data}
            loading={categories.loading}
            empty={{ icon: Layers, title: "No categories yet" }}
            columns={[
              {
                key: "name",
                header: "Category",
                render: (c) => <span className="font-medium">{c.name}</span>,
              },
              { key: "slug", header: "Slug" },
              { key: "count", header: "Products", render: (c) => c.product_count },
              {
                key: "active",
                header: "Status",
                render: (c) => (c.is_active ? "Active" : "Hidden"),
              },
              actions("category"),
            ]}
          />
        )}
      </section>
      {editing && (
        <EditDialog
          kind={editing.kind}
          initial={
            editing.item ? { ...editing.item, product_ids: editing.item.product_ids ?? [] } : null
          }
          products={options.data?.products ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            notify("Saved. The shop updates after the queued rebuild.");
            categories.reload();
            collections.reload();
          }}
        />
      )}
    </>
  );
}

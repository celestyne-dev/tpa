import { ArrowDown, ArrowUp, Eye, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BlockEditor } from "../components/BlockEditor";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { fieldError } from "../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { ImageChooser } from "../components/media/ImageChooser";
import { useNotify } from "../components/notifyContext";
import { ProductFilesPanel } from "../components/products/ProductFilesPanel";
import { ProductPricingPanel } from "../components/products/ProductPricingPanel";
import { fromLocalInput, toLocalInput } from "../components/products/money";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

const CONTENT_KEYS = [
  "title",
  "slug",
  "subtitle",
  "short_description",
  "description",
  "benefits",
  "included",
  "faq",
  "audience",
  "format_label",
  "language",
  "edition",
  "page_count",
  "sample_text",
  "author_id",
  "cover_media_id",
  "cover_theme",
  "gallery",
  "social_image_id",
  "seo_title",
  "meta_description",
  "noindex",
  "tax_category",
  "category_ids",
  "tag_ids",
  "collection_ids",
  "is_featured",
  "featured_order",
];

const TABS = [
  ["details", "Details"],
  ["content", "Description & FAQ"],
  ["images", "Images"],
  ["files", "Files"],
  ["pricing", "Pricing"],
  ["bundle", "Bundle"],
  ["seo", "SEO"],
  ["sales", "Sales & publishing"],
  ["history", "History"],
];

const pick = (product) => Object.fromEntries(CONTENT_KEYS.map((k) => [k, product[k]]));

function ListEditor({ label, items, onChange, fields, addLabel, disabled }) {
  const update = (i, patch) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const move = (i, d) => {
    const next = [...items];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium">{label}</legend>
      {items.map((item, i) => (
        <div
          key={i}
          className="grid gap-2 rounded-xl border border-charcoal/10 p-3 sm:grid-cols-[1fr_auto]"
        >
          <div className="grid gap-2">
            {fields.map(([key, fieldLabel, multiline]) =>
              multiline ? (
                <TextAreaField
                  key={key}
                  label={fieldLabel}
                  rows={3}
                  value={item[key] ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(i, { [key]: e.target.value })}
                />
              ) : (
                <TextField
                  key={key}
                  label={fieldLabel}
                  value={item[key] ?? ""}
                  disabled={disabled}
                  onChange={(e) => update(i, { [key]: e.target.value })}
                />
              ),
            )}
          </div>
          <div className="flex gap-1 sm:flex-col">
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Move item ${i + 1} up`}
              disabled={disabled || i === 0}
              onClick={() => move(i, -1)}
            >
              <ArrowUp aria-hidden />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Move item ${i + 1} down`}
              disabled={disabled || i === items.length - 1}
              onClick={() => move(i, 1)}
            >
              <ArrowDown aria-hidden />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Remove item ${i + 1}`}
              disabled={disabled}
              onClick={() => onChange(items.filter((_, j) => j !== i))}
            >
              <Trash2 aria-hidden />
            </Button>
          </div>
        </div>
      ))}
      <Button
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => onChange([...items, Object.fromEntries(fields.map(([k]) => [k, ""]))])}
      >
        <Plus aria-hidden /> {addLabel}
      </Button>
    </fieldset>
  );
}

function MultiCheck({ label, options, value, onChange, disabled }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">{label}</legend>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
        {options.length === 0 && <span className="text-sm text-muted">None yet.</span>}
        {options.map((o) => (
          <CheckboxField
            key={o.id}
            label={o.name}
            checked={value.includes(o.id)}
            disabled={disabled}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, o.id] : value.filter((v) => v !== o.id))
            }
          />
        ))}
      </div>
    </fieldset>
  );
}

function BundlePanel({ product, options, canEdit, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [ids, setIds] = useState(product.bundle_items.map((i) => i.product_id));
  const [error, setError] = useState(null);
  const choices = options.products.filter((p) => p.id !== product.id);
  const title = (id) => choices.find((p) => p.id === id)?.title ?? `#${id}`;
  const save = async () => {
    setError(null);
    try {
      await api.products.setBundleItems(product.id, ids);
      notify("Bundle contents saved. Past buyers keep what they bought.");
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Buyers of this bundle get access to every included product. Changing the contents never
        removes access from people who already bought the bundle, and doesn't add new products to
        past purchases.
      </p>
      <ol className="space-y-2">
        {ids.map((id, i) => (
          <li
            key={id}
            className="flex items-center justify-between rounded-lg border border-charcoal/10 px-3 py-2 text-sm"
          >
            <span>{title(id)}</span>
            {canEdit && (
              <span className="flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Move ${title(id)} up`}
                  disabled={i === 0}
                  onClick={() => {
                    const n = [...ids];
                    [n[i - 1], n[i]] = [n[i], n[i - 1]];
                    setIds(n);
                  }}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${title(id)}`}
                  onClick={() => setIds(ids.filter((x) => x !== id))}
                >
                  <Trash2 aria-hidden />
                </Button>
              </span>
            )}
          </li>
        ))}
      </ol>
      {canEdit && (
        <>
          <SelectField
            label="Add a product"
            value=""
            onChange={(e) => e.target.value && setIds([...ids, Number(e.target.value)])}
            options={[
              { value: "", label: "Choose…" },
              ...choices
                .filter((p) => !ids.includes(p.id))
                .map((p) => ({ value: p.id, label: `${p.title} (${p.status})` })),
            ]}
          />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {fieldError(error, "items") ?? error.message}
            </p>
          )}
          <Button size="sm" onClick={save}>
            Save bundle contents
          </Button>
        </>
      )}
    </div>
  );
}

function HistoryPanel({ productId, canRestore, onRestored }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, loading } = useAdminQuery(() => api.products.revisions(productId), [productId]);
  if (loading || !data) return <p className="text-sm text-muted">Loading history…</p>;
  return (
    <ul className="divide-y divide-charcoal/10 text-sm">
      {data.map((r) => (
        <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <span>
            <strong>#{r.number}</strong> {r.summary} · {r.created_by ?? "System"} ·{" "}
            {formatDateTime(r.created_at)}
          </span>
          {canRestore && (
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                try {
                  await api.products.restoreRevision(productId, r.id);
                  notify(`Revision #${r.number} loaded into the draft.`);
                  onRestored();
                } catch (err) {
                  notify(err.message, "error");
                }
              }}
            >
              Restore to draft
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ProductEditorPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const {
    data: product,
    error,
    loading,
    reload,
    setData,
  } = useAdminQuery(() => api.products.get(id), [id]);
  const { data: options } = useAdminQuery(() => api.products.options(), []);
  const [tab, setTab] = useState("details");
  const [draft, setDraft] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [files, setFiles] = useState(null);

  const base = useMemo(() => (product ? pick(product) : null), [product]);
  const form = draft ?? base;
  const dirty = Boolean(draft) && JSON.stringify(draft) !== JSON.stringify(base);
  useUnsavedChanges(dirty);
  const set = (patch) => setDraft({ ...form, ...patch });

  if (error) return <ErrorState title="We couldn't load this product" onRetry={reload} />;
  if (loading || !product || !options || !form)
    return (
      <p role="status" className="text-muted">
        Loading product…
      </p>
    );
  const can = product.can;
  const editable = can.edit && product.status !== "archived";
  const err = (name) => fieldError(saveError, name);

  const refresh = async () => {
    const res = await api.products.get(id);
    setData(res.data);
    setDraft(null);
    if (tab === "files") setFiles(null);
  };
  const save = async () => {
    setBusy(true);
    setSaveError(null);
    try {
      const changes = Object.fromEntries(
        Object.entries(form).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(base[k])),
      );
      const res = await api.products.update(product.id, {
        ...changes,
        lock_version: product.lock_version,
      });
      setData(res.data);
      setDraft(null);
      notify(
        product.status === "published"
          ? "Draft saved. Publish to update the live page."
          : "Draft saved.",
      );
    } catch (e) {
      setSaveError(e);
      notify(
        e.status === 409
          ? "Someone else saved this product. Reload to see their changes."
          : "Please fix the highlighted fields.",
        "error",
      );
    } finally {
      setBusy(false);
    }
  };
  const action = async (name, message) => {
    setBusy(true);
    try {
      const res = await api.products.action(product.id, name);
      if (name === "duplicate") {
        notify("Copy created as a draft.");
        navigate(`/admin/products/${res.data.id}`);
        return;
      }
      setData(res.data);
      setDraft(null);
      notify(message);
    } catch (e) {
      const details = e.details?.publish;
      notify(details ? `${e.message} ${details.join(" ")}` : e.message, "error");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };
  const setSales = async (patch) => {
    try {
      const res = await api.products.update(product.id, patch);
      setData(res.data);
      notify("Saved.");
    } catch (e) {
      notify(e.details?.sales_status?.join(" ") ?? e.message, "error");
    }
  };
  const loadFiles = async () => {
    if (files) return;
    const res = await api.products.files(product.id);
    setFiles(res.data);
  };
  const visibleTabs = TABS.filter(([key]) => key !== "bundle" || product.product_type === "bundle");

  return (
    <>
      <AdminPageHeader
        title={product.title}
        breadcrumbs={[{ label: "Products", to: "/admin/products" }, { label: product.title }]}
        description={
          product.public_path ? (
            <>
              Live at{" "}
              <a href={product.public_path} className="underline" target="_blank" rel="noreferrer">
                {product.public_path}
              </a>
            </>
          ) : (
            "Not published: this product is private."
          )
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to={`/admin/products/${product.id}/preview`}
              className="inline-flex items-center gap-1 rounded-full border border-charcoal/20 px-4 py-2 text-sm"
            >
              <Eye aria-hidden className="size-4" /> Preview
            </Link>
            {editable && (
              <Button onClick={save} disabled={!dirty || busy}>
                Save draft
              </Button>
            )}
            {can.publish && product.status !== "archived" && (
              <Button
                variant={dirty ? "outline" : "primary"}
                disabled={busy || dirty}
                title={dirty ? "Save the draft first" : undefined}
                onClick={() =>
                  action("publish", "Published. The shop page updates after the queued rebuild.")
                }
              >
                {product.status === "published" ? "Publish changes" : "Publish"}
              </Button>
            )}
          </div>
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <StatusBadge status={product.status} />
        <StatusBadge
          status={
            product.purchasable
              ? "on sale"
              : product.sales_status === "on_sale"
                ? "blocked"
                : "coming soon"
          }
        />
        {product.has_unpublished_changes && <StatusBadge status="unpublished changes" />}
        {dirty && <span className="text-sm text-gold-700">Unsaved changes</span>}
      </div>
      {product.issues.length > 0 && (
        <div className="mb-5 rounded-xl bg-gold-100/60 p-4 text-sm" role="status">
          <p className="font-medium">Before this product can be sold:</p>
          <ul className="mt-1 list-disc pl-5">
            {product.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </div>
      )}
      <div
        role="tablist"
        aria-label="Product sections"
        className="mb-6 flex flex-wrap gap-1 border-b border-charcoal/10"
      >
        {visibleTabs.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key);
              if (key === "files") loadFiles();
            }}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              tab === key
                ? "border-sage-700 text-charcoal"
                : "border-transparent text-muted hover:text-charcoal",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="max-w-4xl space-y-5">
        {tab === "details" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Title"
              required
              value={form.title}
              disabled={!editable}
              error={err("title")}
              onChange={(e) => set({ title: e.target.value })}
            />
            <TextField
              label="Address (slug)"
              value={form.slug}
              disabled={!editable}
              hint={
                product.published_slug && form.slug !== product.published_slug
                  ? "Publishing will redirect the old address."
                  : `/shop/${form.slug}`
              }
              error={err("slug")}
              onChange={(e) => set({ slug: e.target.value })}
            />
            <TextField
              label="Subtitle"
              value={form.subtitle}
              disabled={!editable}
              error={err("subtitle")}
              onChange={(e) => set({ subtitle: e.target.value })}
            />
            <TextField
              label="Format shown on the cover"
              value={form.format_label}
              disabled={!editable}
              onChange={(e) => set({ format_label: e.target.value })}
            />
            <TextAreaField
              className="sm:col-span-2"
              label="Short description"
              required
              rows={3}
              maxLength={400}
              value={form.short_description}
              disabled={!editable}
              error={err("short_description")}
              onChange={(e) => set({ short_description: e.target.value })}
            />
            <TextField
              label="Language"
              value={form.language}
              disabled={!editable}
              hint="e.g. en, en-GB"
              error={err("language")}
              onChange={(e) => set({ language: e.target.value })}
            />
            <TextField
              label="Edition / version"
              value={form.edition}
              disabled={!editable}
              onChange={(e) => set({ edition: e.target.value })}
            />
            <TextField
              label="Page count"
              type="number"
              min={1}
              value={form.page_count ?? ""}
              disabled={!editable}
              hint="Only enter the real number of pages."
              error={err("page_count")}
              onChange={(e) =>
                set({ page_count: e.target.value === "" ? null : Number(e.target.value) })
              }
            />
            <SelectField
              label="Author / creator"
              value={form.author_id ?? ""}
              disabled={!editable}
              onChange={(e) => set({ author_id: e.target.value ? Number(e.target.value) : null })}
              options={[
                { value: "", label: "None" },
                ...options.authors.map((a) => ({ value: a.id, label: a.name })),
              ]}
            />
            <SelectField
              label="Tax classification"
              value={form.tax_category}
              disabled={!editable}
              hint={options.tax_note}
              onChange={(e) => set({ tax_category: e.target.value })}
              options={options.tax_categories}
            />
            <div className="sm:col-span-2">
              <MultiCheck
                label="Categories"
                options={options.categories}
                value={form.category_ids}
                disabled={!editable}
                onChange={(v) => set({ category_ids: v })}
              />
            </div>
            <div className="sm:col-span-2">
              <MultiCheck
                label="Collections"
                options={options.collections}
                value={form.collection_ids}
                disabled={!editable}
                onChange={(v) => set({ collection_ids: v })}
              />
            </div>
            <div className="sm:col-span-2">
              <MultiCheck
                label="Tags"
                options={options.tags}
                value={form.tag_ids}
                disabled={!editable}
                onChange={(v) => set({ tag_ids: v })}
              />
            </div>
            <CheckboxField
              label="Featured product"
              hint="Shown first in the shop and in the homepage showcase."
              checked={form.is_featured}
              disabled={!editable}
              onChange={(e) => set({ is_featured: e.target.checked })}
            />
            <TextField
              label="Featured order"
              type="number"
              min={0}
              value={form.featured_order}
              disabled={!editable}
              onChange={(e) => set({ featured_order: Number(e.target.value) || 0 })}
            />
          </div>
        )}
        {tab === "content" && (
          <>
            <div>
              <p className="mb-2 text-sm font-medium">Full description</p>
              <BlockEditor
                blocks={form.description}
                disabled={!editable}
                errors={saveError?.details?.description}
                onChange={(blocks) => set({ description: blocks })}
              />
            </div>
            <TextAreaField
              label="Benefits (one per line)"
              rows={4}
              disabled={!editable}
              value={(form.benefits ?? []).join("\n")}
              error={err("benefits")}
              onChange={(e) => set({ benefits: e.target.value.split("\n") })}
            />
            <ListEditor
              label="What's included"
              addLabel="Add included item"
              disabled={!editable}
              items={form.included}
              onChange={(v) => set({ included: v })}
              fields={[
                ["title", "Title"],
                ["format", "Format (e.g. PDF, 42 pages)"],
                ["description", "Description", true],
              ]}
            />
            <TextAreaField
              label="Who it's for"
              rows={3}
              disabled={!editable}
              value={form.audience}
              onChange={(e) => set({ audience: e.target.value })}
            />
            <TextAreaField
              label="Sample text (optional)"
              rows={5}
              disabled={!editable}
              hint="A real excerpt from the product, shown on the product page."
              value={form.sample_text}
              onChange={(e) => set({ sample_text: e.target.value })}
            />
            <ListEditor
              label="Frequently asked questions"
              addLabel="Add question"
              disabled={!editable}
              items={form.faq}
              onChange={(v) => set({ faq: v })}
              fields={[
                ["question", "Question"],
                ["answer", "Answer", true],
              ]}
            />
          </>
        )}
        {tab === "images" && (
          <div className="grid gap-6 sm:grid-cols-2">
            <ImageChooser
              label="cover image"
              mediaId={form.cover_media_id}
              disabled={!editable}
              onChange={(v) => set({ cover_media_id: v })}
            />
            <SelectField
              label="Placeholder artwork colour"
              hint="Used when there is no cover image."
              value={form.cover_theme}
              disabled={!editable}
              onChange={(e) => set({ cover_theme: e.target.value })}
              options={options.cover_themes.map((t) => ({ value: t, label: t }))}
            />
            <div className="sm:col-span-2">
              <p className="text-sm font-medium">Preview pages / gallery</p>
              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                {form.gallery.map((mediaId, i) => (
                  <ImageChooser
                    key={`${mediaId}-${i}`}
                    label={`gallery image ${i + 1}`}
                    mediaId={mediaId}
                    disabled={!editable}
                    onChange={(v) =>
                      set({
                        gallery: v
                          ? form.gallery.map((g, j) => (j === i ? v : g))
                          : form.gallery.filter((_, j) => j !== i),
                      })
                    }
                  />
                ))}
                {editable && form.gallery.length < 12 && (
                  <ImageChooser
                    label="gallery image"
                    mediaId={null}
                    onChange={(v) => v && set({ gallery: [...form.gallery, v] })}
                  />
                )}
              </div>
            </div>
          </div>
        )}
        {tab === "files" &&
          (files ? (
            <ProductFilesPanel
              product={{ ...product, files: files.files }}
              canManage={can.files}
              scanner={files.scanner_configured}
              maxMb={files.max_mb}
              onChanged={async () => {
                setFiles(null);
                const res = await api.products.files(product.id);
                setFiles(res.data);
                refresh();
              }}
            />
          ) : (
            <p className="text-sm text-muted">Loading files…</p>
          ))}
        {tab === "pricing" && (
          <ProductPricingPanel
            product={product}
            options={options}
            canPrice={can.prices}
            onChanged={refresh}
          />
        )}
        {tab === "bundle" && (
          <BundlePanel
            product={product}
            options={options}
            canEdit={can.bundles}
            onChanged={refresh}
          />
        )}
        {tab === "seo" && (
          <div className="grid gap-4">
            <TextField
              label="SEO title"
              value={form.seo_title ?? ""}
              disabled={!editable}
              hint="Defaults to the product title."
              onChange={(e) => set({ seo_title: e.target.value })}
            />
            <TextAreaField
              label="Meta description"
              rows={3}
              value={form.meta_description ?? ""}
              disabled={!editable}
              hint="Defaults to the short description."
              onChange={(e) => set({ meta_description: e.target.value })}
            />
            <ImageChooser
              label="social sharing image"
              mediaId={form.social_image_id}
              disabled={!editable}
              onChange={(v) => set({ social_image_id: v })}
            />
            <CheckboxField
              label="Hide from search engines (noindex)"
              checked={form.noindex}
              disabled={!editable}
              onChange={(e) => set({ noindex: e.target.checked })}
            />
          </div>
        )}
        {tab === "sales" && (
          <div className="space-y-5">
            <div className="rounded-xl border border-charcoal/10 bg-white p-4">
              <p className="font-medium">Availability</p>
              <p className="mt-1 text-sm text-muted">
                “Coming soon” products are shown as previews with no price or buy button. “On sale”
                requires files and an approved price (or free).
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {[
                  ["coming_soon", "Coming soon"],
                  ["on_sale", "On sale"],
                ].map(([value, label]) => (
                  <Button
                    key={value}
                    size="sm"
                    variant={product.sales_status === value ? "primary" : "outline"}
                    disabled={!can.publish || product.sales_status === value}
                    onClick={() => setSales({ sales_status: value })}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              {product.blockers.length > 0 && product.sales_status === "on_sale" && (
                <ul className="mt-3 list-disc pl-5 text-sm text-gold-700">
                  {product.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField
                type="datetime-local"
                label="Purchasing opens (optional)"
                value={toLocalInput(product.available_from)}
                disabled={!can.publish}
                onChange={(e) => setSales({ available_from: fromLocalInput(e.target.value) })}
              />
              <TextField
                type="datetime-local"
                label="Purchasing closes (optional)"
                value={toLocalInput(product.available_until)}
                disabled={!can.publish}
                onChange={(e) => setSales({ available_until: fromLocalInput(e.target.value) })}
              />
            </div>
            <div className="flex flex-wrap gap-2 border-t border-charcoal/10 pt-5">
              {can.publish && product.status === "published" && (
                <Button variant="outline" onClick={() => setConfirm("unpublish")}>
                  Unpublish
                </Button>
              )}
              {can.edit && product.has_unpublished_changes && (
                <Button variant="outline" onClick={() => setConfirm("discard")}>
                  Discard unpublished changes
                </Button>
              )}
              {can.create && (
                <Button variant="outline" onClick={() => action("duplicate")}>
                  Duplicate
                </Button>
              )}
              {can.archive && (
                <Button
                  variant="outline"
                  onClick={() => setConfirm(product.status === "archived" ? "restore" : "archive")}
                >
                  {product.status === "archived" ? "Restore" : "Archive"}
                </Button>
              )}
            </div>
            <div className="rounded-xl bg-cream/60 p-4 text-sm">
              <p className="font-medium">Sales</p>
              <p className="mt-1 text-muted">
                {product.sales.active_entitlements} customer(s) currently have access.
                {product.sales.orders
                  .map((o) => ` ${o.count} paid ${o.mode} order(s) in ${o.currency}.`)
                  .join("")}
              </p>
            </div>
          </div>
        )}
        {tab === "history" && (
          <HistoryPanel productId={product.id} canRestore={editable} onRestored={refresh} />
        )}
      </div>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={
          {
            unpublish: "Unpublish this product?",
            archive: "Archive this product?",
            restore: "Restore this product?",
            discard: "Discard unpublished changes?",
          }[confirm] ?? ""
        }
        message={
          {
            unpublish:
              "Its page disappears from the shop after the next rebuild. Customers who bought it keep their downloads.",
            archive:
              "It is removed from the shop and can't be bought. Existing customers keep their downloads.",
            restore: "It returns as a draft.",
            discard: "The draft goes back to the live version.",
          }[confirm] ?? ""
        }
        tone={confirm === "archive" ? "danger" : "primary"}
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() =>
          action(
            confirm === "discard" ? "discard" : confirm,
            {
              unpublish: "Unpublished.",
              archive: "Archived.",
              restore: "Restored as a draft.",
              discard: "Unpublished changes discarded.",
            }[confirm],
          )
        }
      />
    </>
  );
}

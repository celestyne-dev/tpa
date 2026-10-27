import { Archive, Copy, Crosshair, RefreshCw, RotateCcw, Save, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatBytes, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { ConfirmDialog } from "../ConfirmDialog";
import { fieldError } from "../fieldError";
import { SelectField, TextAreaField, TextField } from "../Fields";
import { Modal } from "../Modal";
import { useNotify } from "../notifyContext";

const FIELDS = ["alt_text", "title", "caption", "credit", "source_url", "category"];
// Fallback when the library's category list hasn't been loaded (e.g. in the picker).
const DEFAULT_CATEGORIES = [
  { key: "general", label: "General" },
  { key: "articles", label: "Articles" },
  { key: "resources", label: "Resource covers & previews" },
  { key: "pages", label: "Pages & homepage" },
  { key: "branding", label: "Branding" },
  { key: "people", label: "Authors & people" },
  { key: "marketing", label: "Marketing & social" },
];

function toForm(asset) {
  return Object.fromEntries(FIELDS.map((f) => [f, asset?.[f] ?? ""]));
}

/** Image details: preview + focal point, metadata, variants, replace/archive/delete. */
export function MediaDetail({ mediaId, onClose, onChanged, categories = DEFAULT_CATEGORIES }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const query = useAdminQuery(() => api.media.get(mediaId), [mediaId]);
  const asset = query.data;
  const [form, setForm] = useState(null);
  const [loadedFor, setLoadedFor] = useState(null);
  if (asset && loadedFor !== `${asset.id}-${asset.updated_at}-${asset.version}`) {
    setLoadedFor(`${asset.id}-${asset.updated_at}-${asset.version}`);
    setForm(toForm(asset));
  }
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [replaceProgress, setReplaceProgress] = useState(null);
  const replaceInput = useRef(null);
  const canEdit = can("media.edit");

  const run = async (fn, message) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      if (res?.data?.id) query.setData(res.data);
      notify(message);
      onChanged?.();
      return res;
    } catch (err) {
      setError(err);
      notify(err.message, "error");
      return null;
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const save = (event) => {
    event.preventDefault();
    run(() => api.media.update(mediaId, form), "Image details saved.");
  };

  const setFocal = (event) => {
    if (!canEdit || !asset?.managed) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    run(
      () =>
        api.media.update(mediaId, {
          focal_x: Math.round(x * 100) / 100,
          focal_y: Math.round(y * 100) / 100,
        }),
      "Focal point updated. Crops were regenerated.",
    );
  };

  const replace = async (file) => {
    setReplaceProgress(0);
    await run(
      () => api.media.replace(mediaId, file, setReplaceProgress),
      "Image replaced with a newly optimised version.",
    );
    setReplaceProgress(null);
  };

  const copyUrl = async (url) => {
    const absolute = new URL(url, window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(absolute);
      notify("Image URL copied.");
    } catch {
      notify(absolute);
    }
  };

  const usage = asset?.usage ?? [];
  const focal = asset?.focal_point ?? { x: 0.5, y: 0.5 };

  return (
    <Modal
      open
      onClose={onClose}
      title={asset ? asset.title || asset.filename : "Image details"}
      description={asset ? `${asset.width}×${asset.height} · ${asset.mime_type}` : undefined}
      size="lg"
    >
      {!asset || !form ? (
        query.error ? (
          <p role="alert" className="text-sm text-red-800">
            {query.error.message}
          </p>
        ) : (
          <Skeleton className="h-64 w-full" />
        )
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="min-w-0 space-y-4">
            <figure>
              <button
                type="button"
                onClick={setFocal}
                disabled={!canEdit || !asset.managed || busy}
                aria-label="Set focal point (click on the most important part of the image)"
                className="relative block w-full overflow-hidden rounded-xl bg-beige disabled:cursor-default"
              >
                <img
                  src={asset.image?.src ?? asset.url}
                  alt={asset.alt_text}
                  width={asset.width ?? undefined}
                  height={asset.height ?? undefined}
                  className="h-auto w-full"
                />
                {asset.managed && (
                  <span
                    aria-hidden
                    className="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-ivory bg-sage-700/70 text-ivory shadow"
                    style={{ left: `${focal.x * 100}%`, top: `${focal.y * 100}%` }}
                  >
                    <Crosshair className="size-4" />
                  </span>
                )}
              </button>
              {asset.managed && canEdit && (
                <figcaption className="mt-1 text-xs text-muted">
                  Click the image to set the focal point used for crops (cards, social images,
                  portraits).
                </figcaption>
              )}
            </figure>

            <form onSubmit={save} className="space-y-3">
              <fieldset disabled={!canEdit || busy} className="space-y-3">
                <legend className="sr-only">Image details</legend>
                <TextAreaField
                  label="Alt text"
                  rows={2}
                  hint="Describe what the image shows for people using screen readers. Leave empty only for purely decorative images."
                  value={form.alt_text}
                  onChange={(e) => setForm({ ...form, alt_text: e.target.value })}
                  error={fieldError(error, "alt_text")}
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <TextField
                    label="Title"
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    error={fieldError(error, "title")}
                  />
                  <TextField
                    label="Credit / source"
                    value={form.credit}
                    onChange={(e) => setForm({ ...form, credit: e.target.value })}
                    error={fieldError(error, "credit")}
                  />
                </div>
                <TextField
                  label="Caption"
                  value={form.caption}
                  onChange={(e) => setForm({ ...form, caption: e.target.value })}
                  error={fieldError(error, "caption")}
                />
                <SelectField
                  label="Category"
                  value={form.category || "general"}
                  options={categories.map((c) => ({ value: c.key, label: c.label }))}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  error={fieldError(error, "category")}
                />
                <TextField
                  label="Source URL (optional)"
                  placeholder="https://"
                  value={form.source_url}
                  onChange={(e) => setForm({ ...form, source_url: e.target.value })}
                  error={fieldError(error, "source_url")}
                />
              </fieldset>
              {canEdit && (
                <Button type="submit" size="sm" disabled={busy}>
                  <Save aria-hidden />
                  Save details
                </Button>
              )}
            </form>
          </div>

          <aside className="space-y-4 text-sm">
            <section aria-labelledby="file-heading" className="rounded-xl bg-cream/60 p-4">
              <h3 id="file-heading" className="font-sans text-sm font-semibold">
                File
              </h3>
              <dl className="mt-2 space-y-1">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Dimensions</dt>
                  <dd>
                    {asset.width}×{asset.height}
                  </dd>
                </div>
                {asset.original?.size_bytes != null && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Uploaded file</dt>
                    <dd>{formatBytes(asset.original.size_bytes)}</dd>
                  </div>
                )}
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Served (fallback)</dt>
                  <dd>
                    {formatBytes(
                      asset.variants.find((v) => v.url === asset.image?.src)?.size_bytes ??
                        asset.size_bytes,
                    )}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Uploaded</dt>
                  <dd>{formatDateTime(asset.created_at)}</dd>
                </div>
              </dl>
              <Button
                variant="outline"
                size="sm"
                className="mt-3 w-full"
                onClick={() => copyUrl(asset.url)}
              >
                <Copy aria-hidden />
                Copy image URL
              </Button>
            </section>

            {asset.variants.length > 0 && (
              <details className="rounded-xl border border-charcoal/10 p-4">
                <summary className="cursor-pointer font-semibold">
                  {asset.variants.length} optimised versions (
                  {formatBytes(asset.variants_size_bytes)})
                </summary>
                <table className="mt-2 w-full text-xs">
                  <thead className="text-muted">
                    <tr>
                      <th className="text-left font-normal">Use</th>
                      <th className="text-left font-normal">Format</th>
                      <th className="text-right font-normal">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {asset.variants.map((v) => (
                      <tr key={v.url}>
                        <td>
                          {v.preset} {v.width}w
                        </td>
                        <td className="uppercase">{v.format}</td>
                        <td className="text-right">{formatBytes(v.size_bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}

            <section aria-labelledby="usage-heading">
              <h3 id="usage-heading" className="font-sans text-sm font-semibold">
                Used in
              </h3>
              {usage.length === 0 ? (
                <p className="mt-1 text-muted">Not used anywhere yet.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {usage.map((u, i) => (
                    <li key={i}>
                      <span className="font-medium">{u.label}</span>{" "}
                      <span className="text-muted">
                        ({u.type.replace("_", " ")}, {u.field}
                        {u.public ? ", public" : ""})
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="space-y-2">
              {can("media.replace") && asset.managed && asset.status === "active" && (
                <>
                  <input
                    ref={replaceInput}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/avif,image/gif"
                    className="sr-only"
                    aria-label="Replacement image file"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) replace(file);
                    }}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={busy}
                    onClick={() => replaceInput.current?.click()}
                  >
                    <RefreshCw aria-hidden />
                    {replaceProgress != null ? `Replacing… ${replaceProgress}%` : "Replace image"}
                  </Button>
                </>
              )}
              {can("media.delete") &&
                (asset.status === "active" ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    disabled={busy}
                    onClick={() =>
                      run(
                        () => api.media.archive(mediaId),
                        "Image archived. It keeps working where it is already used.",
                      )
                    }
                  >
                    <Archive aria-hidden />
                    Archive
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    disabled={busy}
                    onClick={() => run(() => api.media.restore(mediaId), "Image restored.")}
                  >
                    <RotateCcw aria-hidden />
                    Restore
                  </Button>
                ))}
              {can("media.delete") && asset.managed && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-red-800"
                  disabled={busy || usage.length > 0}
                  title={usage.length ? "Images that are in use cannot be deleted." : undefined}
                  onClick={() => setConfirm("delete")}
                >
                  <Trash2 aria-hidden />
                  Delete permanently
                </Button>
              )}
              {usage.length > 0 && can("media.delete") && (
                <p className="text-xs text-muted">In-use images can be archived but not deleted.</p>
              )}
            </div>
          </aside>
        </div>
      )}
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this image permanently?"
        message="All optimised versions and the retained original are removed. This cannot be undone."
        confirmLabel="Delete image"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          setBusy(true);
          try {
            await api.media.remove(mediaId);
            notify("Image deleted.");
            onChanged?.();
            onClose();
          } catch (err) {
            notify(err.message, "error");
          } finally {
            setBusy(false);
            setConfirm(null);
          }
        }}
      />
    </Modal>
  );
}

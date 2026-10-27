import { Archive, FileLock2, RotateCcw, Trash2, UploadCloud } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatBytes, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { ConfirmDialog } from "../ConfirmDialog";
import { DataTable } from "../DataTable";
import { SelectField, TextField } from "../Fields";
import { Modal } from "../Modal";
import { useNotify } from "../notifyContext";
import { StatusBadge } from "../StatusBadge";

const CATEGORY_LABELS = {
  ebooks: "eBooks",
  workbooks: "Workbooks & planners",
  templates: "Templates & checklists",
  courses: "Courses",
  downloads: "Other downloads",
};
const FORMAT_OPTIONS = [
  { value: "", label: "All formats" },
  { value: "pdf", label: "PDF" },
  { value: "epub", label: "EPUB" },
  { value: "docx", label: "DOCX" },
  { value: "xlsx", label: "XLSX" },
  { value: "zip", label: "ZIP" },
];
const ACCEPT = ".pdf,.epub,.docx,.xlsx,.zip";

function UploadToResource({ onUploaded }) {
  const api = useAdminApi();
  const notify = useNotify();
  const inputId = useId();
  const resources = useAdminQuery(() => api.products.list({ group: "resources" }), []);
  const [productId, setProductId] = useState("");
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setProgress(0);
    try {
      await api.products.uploadFile(
        Number(productId),
        file,
        title.trim() ? { title: title.trim() } : {},
        (p) => setProgress(p ?? 50),
      );
      notify("File stored privately. It is only delivered through download links.");
      setFile(null);
      setTitle("");
      event.target.reset();
      onUploaded?.();
    } catch (err) {
      setError(err.details?.file?.join(" ") ?? err.message);
    } finally {
      setProgress(null);
    }
  };

  return (
    <form
      onSubmit={submit}
      aria-label="Upload a premium file"
      className="grid gap-3 rounded-xl border border-dashed border-charcoal/20 bg-white p-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto]"
    >
      <SelectField
        label="Resource"
        required
        value={productId}
        onChange={(e) => setProductId(e.target.value)}
        options={[
          { value: "", label: resources.loading ? "Loading…" : "Choose a resource" },
          ...(resources.data ?? []).map((p) => ({ value: String(p.id), label: p.title })),
        ]}
      />
      <div>
        <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
          File (PDF, EPUB, DOCX, XLSX or ZIP)
        </label>
        <input
          id={inputId}
          type="file"
          accept={ACCEPT}
          required
          className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-beige file:px-3 file:py-1.5"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
      <TextField
        label="Title shown to buyers (optional)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="flex items-end">
        <Button type="submit" disabled={!productId || !file || progress !== null}>
          <UploadCloud aria-hidden />
          {progress !== null ? `Uploading ${Math.round(progress)}%` : "Upload"}
        </Button>
      </div>
      {progress !== null && (
        <progress
          className="h-2 w-full sm:col-span-2 lg:col-span-4"
          max={100}
          value={progress}
          aria-label="Upload progress"
        />
      )}
      {error && (
        <p role="alert" className="text-sm text-red-800 sm:col-span-2 lg:col-span-4">
          {error}
        </p>
      )}
    </form>
  );
}

function FileDetail({ fileId, onClose, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const query = useAdminQuery(() => api.premiumFiles.get(fileId), [fileId]);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const file = query.data;
  const canManage = can("products.manage_files");

  const run = async (fn, message, { close = false } = {}) => {
    setBusy(true);
    try {
      const res = await fn();
      notify(message);
      onChanged?.();
      if (close) onClose();
      else if (res?.data?.versions) query.setData(res.data);
      else query.reload();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const replace = async (event) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    setProgress(0);
    await run(
      () =>
        api.products.uploadVersion(file.product.id, file.id, chosen, {}, (p) =>
          setProgress(p ?? 50),
        ),
      "New version uploaded. New buyers get it; existing buyers can download it too.",
    );
    setProgress(null);
  };

  return (
    <Modal open title={file ? file.title : "Premium file"} onClose={onClose} size="lg">
      {query.error ? (
        <ErrorState title="We couldn't load this file" onRetry={query.reload} />
      ) : !file ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : (
        <div className="space-y-5">
          <p className="text-sm">
            Part of{" "}
            <Link to={`/admin/products/${file.product.id}`} className="underline">
              {file.product.title}
            </Link>{" "}
            · {file.downloads} download{file.downloads === 1 ? "" : "s"} ·{" "}
            <StatusBadge status={file.status} />
          </p>
          <p className="rounded-lg bg-cream/70 p-3 text-sm text-muted">
            Premium files are never available at a public address. Buyers download them through
            short-lived links after their access is checked, so there is no file preview here;
            download a version below to check it.
          </p>
          <ul className="divide-y divide-charcoal/10 rounded-xl border border-charcoal/10">
            {file.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                <div className="text-sm">
                  <p className="font-medium">
                    Version {v.version}
                    {file.current_version?.id === v.id && (
                      <span className="ml-2 rounded-full bg-sage-100 px-2 py-0.5 text-xs">
                        current
                      </span>
                    )}
                  </p>
                  <p className="text-muted">
                    {v.format.toUpperCase()} · {formatBytes(v.size_bytes)} · {v.original_filename} ·{" "}
                    {formatDateTime(v.created_at)} · received by {v.purchases} buyer
                    {v.purchases === 1 ? "" : "s"}
                  </p>
                  {v.delete_blocked_reason && (
                    <p className="text-xs text-muted">{v.delete_blocked_reason}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <a
                    className="inline-flex items-center rounded-full border border-charcoal/20 px-3 py-1.5 text-sm"
                    href={api.products.fileDownloadUrl(file.product.id, file.id, v.id)}
                  >
                    Download
                  </a>
                  {canManage && v.deletable && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        setConfirm({
                          title: `Delete version ${v.version}?`,
                          message:
                            "Nobody received or downloaded this version. It will be removed from storage permanently.",
                          action: () =>
                            run(
                              () => api.premiumFiles.removeVersion(file.id, v.id),
                              `Version ${v.version} deleted.`,
                            ),
                        })
                      }
                    >
                      <Trash2 aria-hidden />
                      Delete
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {canManage && (
            <div className="flex flex-wrap gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-sage-700 px-4 py-2 text-sm font-medium text-ivory">
                <UploadCloud aria-hidden className="size-4" />
                {progress !== null ? `Uploading ${Math.round(progress)}%` : "Upload new version"}
                <input type="file" accept={ACCEPT} className="sr-only" onChange={replace} />
              </label>
              {file.status === "active" ? (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () =>
                        api.products.updateFile(file.product.id, file.id, { status: "inactive" }),
                      "Archived. Existing buyers keep access; new buyers won't get it.",
                    )
                  }
                >
                  <Archive aria-hidden />
                  Archive
                </Button>
              ) : (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api.products.updateFile(file.product.id, file.id, { status: "active" }),
                      "Restored.",
                    )
                  }
                >
                  <RotateCcw aria-hidden />
                  Restore
                </Button>
              )}
              {file.deletable ? (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    setConfirm({
                      title: "Delete this file?",
                      message:
                        "It was never sold or downloaded. All its versions will be removed from storage permanently.",
                      action: () =>
                        run(() => api.premiumFiles.remove(file.id), "File deleted.", {
                          close: true,
                        }),
                    })
                  }
                >
                  <Trash2 aria-hidden />
                  Delete file
                </Button>
              ) : (
                <p className="self-center text-xs text-muted">{file.delete_blocked_reason}</p>
              )}
            </div>
          )}
          <ConfirmDialog
            open={Boolean(confirm)}
            title={confirm?.title}
            message={confirm?.message}
            confirmLabel="Delete permanently"
            tone="danger"
            busy={busy}
            onConfirm={() => confirm?.action()}
            onCancel={() => setConfirm(null)}
          />
        </div>
      )}
    </Modal>
  );
}

/** Media library "Premium files": protected resource files across every resource. */
export function PremiumFilesPanel() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({
    q: "",
    format: "",
    category: "",
    status: "",
    sort: "newest",
  });
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState(null);
  const query = useAdminQuery(
    () => api.premiumFiles.list(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))),
    [JSON.stringify(filters)],
  );
  const summary = query.meta?.summary;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        eBooks, workbooks, templates and other paid or free downloads. They are stored in private
        storage on the server and only ever delivered through authorised, short-lived download
        links.
      </p>
      {can("products.manage_files") && <UploadToResource onUploaded={query.reload} />}
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters({ ...filters, q: search.trim() });
        }}
        className="grid gap-3 rounded-xl border border-charcoal/10 bg-white p-4 sm:grid-cols-2 lg:grid-cols-5"
      >
        <TextField
          label="Search premium files"
          type="search"
          placeholder="File or resource title"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SelectField
          label="Format"
          options={FORMAT_OPTIONS}
          value={filters.format}
          onChange={(e) => setFilters({ ...filters, format: e.target.value })}
        />
        <SelectField
          label="Category"
          options={[
            { value: "", label: "All categories" },
            ...Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
          ]}
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        />
        <SelectField
          label="Status"
          options={[
            { value: "", label: "Active and archived" },
            { value: "active", label: "Active" },
            { value: "inactive", label: "Archived" },
          ]}
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        />
        <SelectField
          label="Sort"
          options={[
            { value: "newest", label: "Recently updated" },
            { value: "title", label: "Title" },
            { value: "size", label: "Largest first" },
            { value: "downloads", label: "Most downloaded" },
          ]}
          value={filters.sort}
          onChange={(e) => setFilters({ ...filters, sort: e.target.value })}
        />
      </form>
      {summary && (
        <p className="text-sm text-muted">
          {summary.files} file{summary.files === 1 ? "" : "s"} · {formatBytes(summary.total_bytes)}{" "}
          including all versions
        </p>
      )}
      {query.error ? (
        <ErrorState title="We couldn't load premium files" onRetry={query.reload} />
      ) : (
        <DataTable
          caption="Premium files"
          loading={query.loading}
          rows={query.data}
          empty={{
            icon: FileLock2,
            title: "No premium files yet",
            description: "Upload a file to a resource to see it here.",
          }}
          columns={[
            {
              key: "title",
              header: "File",
              render: (f) => (
                <button
                  type="button"
                  className="text-left font-medium underline-offset-4 hover:underline"
                  onClick={() => setOpenId(f.id)}
                >
                  {f.title}
                  <span className="block text-xs font-normal text-muted">{f.product.title}</span>
                </button>
              ),
            },
            { key: "category", header: "Category", render: (f) => CATEGORY_LABELS[f.category] },
            {
              key: "format",
              header: "Format",
              render: (f) => f.current_version?.format.toUpperCase() ?? "—",
            },
            {
              key: "size",
              header: "Size",
              render: (f) => (f.current_version ? formatBytes(f.current_version.size_bytes) : "—"),
            },
            { key: "versions", header: "Versions" },
            { key: "downloads", header: "Downloads" },
            { key: "status", header: "Status", render: (f) => <StatusBadge status={f.status} /> },
          ]}
        />
      )}
      {openId && (
        <FileDetail fileId={openId} onClose={() => setOpenId(null)} onChanged={query.reload} />
      )}
    </div>
  );
}
